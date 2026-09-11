"""Validate human tag audits and derive the executable tag subset."""

# 本模块实现严格 audit 校验、批准子集构建、稳定哈希以及不可覆盖的 bundle 写入。
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from collections.abc import Mapping
from anime_pref.schemas.taxonomy import (
    CanonicalTaxonomySnapshot,
    ExecutableTagSpec,
    ExecutableTagSubset,
    ExecutableTagSubsetManifest,
    TagAuditRecordSpec,
)
from anime_pref.data.taxonomy_snapshot import taxonomy_snapshot_sha256

if TYPE_CHECKING:
    from anime_pref.data.query_builder import DomainRules


def load_tag_audit(path: Path) -> tuple[TagAuditRecordSpec, ...]:
    """Load the reviewed audit JSON without approving missing records."""
    # - 文件必须是 JSON list；每项精确包含 TagAuditRecordSpec 字段；
    # - 严格检查类型、非空 identifier/reason、aliases tuple 语义和 SHA-256 格式；
    # - approved/is_general_spoiler/is_adult 必须是 bool；tag_id 正 int；
    # - 不给缺失 approved 默认值，不根据 reason/aliases 自动批准。
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")

    def reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value

        return result

    try:
        json_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"failed to read tag audit file: {path}") from exc

    try:
        raw_records = json.loads(
            json_text,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid tag audit JSON: {path}") from exc

    if not isinstance(raw_records, list):
        raise ValueError("tag audit root must be a JSON list")

    expected_record_keys = {
        "tag_id",
        "tag_name",
        "category",
        "approved",
        "reason",
        "aliases",
        "is_general_spoiler",
        "is_adult",
        "source_snapshot_hash",
    }

    parsed_records: list[TagAuditRecordSpec] = []

    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            raise ValueError(f"tag audit record[{index}] must be a JSON object")

        actual_keys = set(raw_record.keys())

        if actual_keys != expected_record_keys:
            missing_keys = sorted(expected_record_keys - actual_keys)
            unexpected_keys = sorted(actual_keys - expected_record_keys)

            raise ValueError(
                f"tag audit record[{index}] has invalid keys; "
                f"missing={missing_keys}, "
                f"unexpected={unexpected_keys}"
            )

        tag_id = raw_record["tag_id"]
        tag_name = raw_record["tag_name"]
        category = raw_record["category"]
        approved = raw_record["approved"]
        reason = raw_record["reason"]
        aliases = raw_record["aliases"]
        is_general_spoiler = raw_record["is_general_spoiler"]
        is_adult = raw_record["is_adult"]
        source_snapshot_hash = raw_record["source_snapshot_hash"]

        if isinstance(tag_id, bool) or not isinstance(tag_id, int) or tag_id <= 0:
            raise ValueError(
                f"tag audit record[{index}].tag_id " "must be a positive integer"
            )

        for field_name, value in (
            ("tag_name", tag_name),
            ("category", category),
            ("reason", reason),
        ):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    f"tag audit record[{index}].{field_name} "
                    "must be a non-empty string without leading "
                    "or trailing whitespace"
                )

        for field_name, value in (
            ("approved", approved),
            ("is_general_spoiler", is_general_spoiler),
            ("is_adult", is_adult),
        ):
            if not isinstance(value, bool):
                raise ValueError(
                    f"tag audit record[{index}].{field_name} " "must be a boolean"
                )

        if not isinstance(aliases, list):
            raise ValueError(f"tag audit record[{index}].aliases must be a list")

        parsed_aliases: list[str] = []

        for alias_index, alias in enumerate(aliases):
            if not isinstance(alias, str) or not alias or alias != alias.strip():
                raise ValueError(
                    f"tag audit record[{index}].aliases[{alias_index}] "
                    "must be a non-empty string without leading "
                    "or trailing whitespace"
                )
            parsed_aliases.append(alias)

        if (
            not isinstance(source_snapshot_hash, str)
            or len(source_snapshot_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in source_snapshot_hash
            )
        ):
            raise ValueError(
                f"tag audit record[{index}].source_snapshot_hash "
                "must be a 64-character lowercase SHA-256 hex string"
            )

        parsed_records.append(
            TagAuditRecordSpec(
                tag_id=tag_id,
                tag_name=tag_name,
                category=category,
                approved=approved,
                reason=reason,
                aliases=tuple(parsed_aliases),
                is_general_spoiler=is_general_spoiler,
                is_adult=is_adult,
                source_snapshot_hash=source_snapshot_hash,
            )
        )
    return tuple(parsed_records)


def validate_tag_audit(
    records: tuple[TagAuditRecordSpec, ...],
    snapshot: CanonicalTaxonomySnapshot,
) -> None:
    """Validate audit identity and provenance against one snapshot."""
    # - 验证 snapshot 并计算其 canonical hash；
    # - 每个 record.source_snapshot_hash 必须等于该 hash；
    # - record tag_id/name/category/spoiler/adult 必须与 snapshot 中同一 tag 完全一致；
    # - duplicate audit tag ID 或 name 拒绝；aliases 内部、跨 approved records、与 canonical
    #   tag names 的冲突均拒绝；
    # - snapshot 中未出现的 tag、ID/name 交叉错配均拒绝；不得修改 records。
    if not isinstance(records, tuple):
        raise ValueError("records must be a tuple of TagAuditRecordSpec")
    for index, record in enumerate(records):
        if not isinstance(record, TagAuditRecordSpec):
            raise ValueError(f"records[{index}] must be a TagAuditRecordSpec")

    # 每条 audit record 必须绑定由 canonical 内容计算出的同一个 provenance hash。
    snapshot_hash = taxonomy_snapshot_sha256(snapshot)

    snapshot_tags_by_id = {tag.id: tag for tag in snapshot.tags}

    snapshot_tags_by_name = {tag.name: tag for tag in snapshot.tags}

    canonical_tag_names = set(snapshot_tags_by_name)

    seen_audit_ids: set[int] = set()
    seen_audit_names: set[str] = set()

    approved_alias_owners: dict[str, str] = {}

    for index, record in enumerate(records):
        if (
            isinstance(record.tag_id, bool)
            or not isinstance(record.tag_id, int)
            or record.tag_id <= 0
        ):
            raise ValueError(f"records[{index}].tag_id must be a positive integer")

        for field_name, value in (
            ("tag_name", record.tag_name),
            ("category", record.category),
            ("reason", record.reason),
        ):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    f"records[{index}].{field_name} must be a "
                    "non-empty string without leading or trailing "
                    "whitespace"
                )

        for field_name, value in (
            ("approved", record.approved),
            (
                "is_general_spoiler",
                record.is_general_spoiler,
            ),
            ("is_adult", record.is_adult),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"records[{index}].{field_name} must be a boolean")

        if not isinstance(record.aliases, tuple):
            raise ValueError(f"records[{index}].aliases must be a tuple")

        if (
            not isinstance(record.source_snapshot_hash, str)
            or len(record.source_snapshot_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in record.source_snapshot_hash
            )
        ):
            raise ValueError(
                f"records[{index}].source_snapshot_hash must be a "
                "64-character lowercase SHA-256 hex string"
            )

        if record.tag_id in seen_audit_ids:
            raise ValueError(f"duplicate audit tag_id: {record.tag_id}")

        if record.tag_name in seen_audit_names:
            raise ValueError(f"duplicate audit tag_name: {record.tag_name!r}")

        if record.source_snapshot_hash != snapshot_hash:
            raise ValueError(
                f"records[{index}].source_snapshot_hash does not "
                "match the canonical snapshot"
            )

        snapshot_tag_from_id = snapshot_tags_by_id.get(record.tag_id)
        if snapshot_tag_from_id is None:
            raise ValueError(
                f"records[{index}].tag_id {record.tag_id} "
                "does not exist in the canonical snapshot"
            )

        snapshot_tag_from_name = snapshot_tags_by_name.get(record.tag_name)
        if snapshot_tag_from_name is None:
            raise ValueError(
                f"records[{index}].tag_name {record.tag_name!r} "
                "does not exist in the canonical snapshot"
            )

        if snapshot_tag_from_id.id != snapshot_tag_from_name.id:
            raise ValueError(
                f"records[{index}] tag_id and tag_name refer "
                "to different snapshot tags"
            )

        if record.category != snapshot_tag_from_id.category:
            raise ValueError(
                f"records[{index}].category does not match " "the canonical snapshot"
            )

        if record.is_general_spoiler != snapshot_tag_from_id.is_general_spoiler:
            raise ValueError(
                f"records[{index}].is_general_spoiler does not "
                "match the canonical snapshot"
            )

        if record.is_adult != snapshot_tag_from_id.is_adult:
            raise ValueError(
                f"records[{index}].is_adult does not match " "the canonical snapshot"
            )

        aliases_in_record: set[str] = set()

        for alias_index, alias in enumerate(record.aliases):
            if not isinstance(alias, str) or not alias or alias != alias.strip():
                raise ValueError(
                    f"records[{index}].aliases[{alias_index}] "
                    "must be a non-empty string without leading "
                    "or trailing whitespace"
                )

            if alias in aliases_in_record:
                raise ValueError(
                    f"duplicate alias within records[{index}]: " f"{alias!r}"
                )

            if alias in canonical_tag_names:
                raise ValueError(
                    f"records[{index}] alias {alias!r} conflicts "
                    "with a canonical tag name"
                )

            aliases_in_record.add(alias)

        if record.approved:
            for alias in record.aliases:
                existing_owner = approved_alias_owners.get(alias)

                if existing_owner is not None:
                    raise ValueError(
                        f"approved alias {alias!r} is shared by "
                        f"{existing_owner!r} and "
                        f"{record.tag_name!r}"
                    )

            for alias in record.aliases:
                approved_alias_owners[alias] = record.tag_name

        # 仅在整条记录通过身份与 alias 检查后登记，避免部分状态污染后续检查。
        seen_audit_ids.add(record.tag_id)
        seen_audit_names.add(record.tag_name)

    return None


def build_executable_tag_subset(
    records: tuple[TagAuditRecordSpec, ...],
    snapshot: CanonicalTaxonomySnapshot,
    *,
    subset_version: str,
) -> ExecutableTagSubset:
    """Include only explicitly reviewed records whose approved flag is true."""
    # Executable content policy:
    # - v0.1 executable policy 必须拒绝 approved=True 且 is_adult=True 的记录；
    # - v0.1 暂无 spoiler override 字段，因此也拒绝 approved=True 且
    #   is_general_spoiler=True 的记录；
    # - approved=False 的此类记录可以保留在 audit 中，但不会进入 subset；
    # - category 不能触发自动批准，仍只选择显式 approved is True。
    # - 先 validate_tag_audit；subset_version 是独立非空版本且无首尾 whitespace；
    # - 只选择 approved is True；false 或缺失审核记录绝不进入 subset；
    # - 按 (tag_id, tag_name) canonical sort；aliases canonical sort；
    # - derived_from_snapshot_hash 使用 canonical snapshot hash；不保留 audit reason。
    validate_tag_audit(records, snapshot)

    if (
        not isinstance(subset_version, str)
        or not subset_version
        or subset_version != subset_version.strip()
    ):
        raise ValueError(
            "subset_version must be a non-empty string without "
            "leading or trailing whitespace"
        )

    approved_tags: list[ExecutableTagSpec] = []

    for record in records:
        if record.approved is not True:
            continue

        if record.is_adult is True:
            raise ValueError(
                f"approved tag {record.tag_name!r} cannot "
                "enter the executable subset because "
                "is_adult is true"
            )

        if record.is_general_spoiler is True:
            raise ValueError(
                f"approved tag {record.tag_name!r} cannot "
                "enter the executable subset because "
                "is_general_spoiler is true"
            )

        approved_tags.append(
            ExecutableTagSpec(
                tag_id=record.tag_id,
                tag_name=record.tag_name,
                category=record.category,
                aliases=tuple(sorted(record.aliases)),
                is_general_spoiler=record.is_general_spoiler,
                is_adult=record.is_adult,
            )
        )

    canonical_tags = tuple(
        sorted(
            approved_tags,
            key=lambda tag: (
                tag.tag_id,
                tag.tag_name,
            ),
        )
    )

    derived_from_snapshot_hash = taxonomy_snapshot_sha256(snapshot)

    return ExecutableTagSubset(
        subset_version=subset_version,
        derived_from_snapshot_hash=derived_from_snapshot_hash,
        tags=canonical_tags,
    )


def executable_subset_to_mapping(subset: ExecutableTagSubset) -> dict[str, Any]:
    """Return the fixed canonical JSON shape for an executable subset."""
    if not isinstance(subset, ExecutableTagSubset):
        raise ValueError("subset must be an ExecutableTagSubset")

    if (
        not isinstance(subset.subset_version, str)
        or not subset.subset_version
        or subset.subset_version != subset.subset_version.strip()
    ):
        raise ValueError(
            "subset_version must be a non-empty string without "
            "leading or trailing whitespace"
        )

    if (
        not isinstance(subset.derived_from_snapshot_hash, str)
        or len(subset.derived_from_snapshot_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in subset.derived_from_snapshot_hash
        )
    ):
        raise ValueError(
            "derived_from_snapshot_hash must be a 64-character "
            "lowercase SHA-256 hex string"
        )

    if not isinstance(subset.tags, tuple):
        raise ValueError("subset.tags must be a tuple")

    seen_tag_ids: set[int] = set()
    seen_tag_names: set[str] = set()
    tag_sort_keys: list[tuple[int, str]] = []

    for index, tag in enumerate(subset.tags):
        if not isinstance(tag, ExecutableTagSpec):
            raise ValueError(f"subset.tags[{index}] must be an ExecutableTagSpec")

        if (
            isinstance(tag.tag_id, bool)
            or not isinstance(tag.tag_id, int)
            or tag.tag_id <= 0
        ):
            raise ValueError(
                f"subset.tags[{index}].tag_id must be " "a positive integer"
            )

        for field_name, value in (
            ("tag_name", tag.tag_name),
            ("category", tag.category),
        ):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    f"subset.tags[{index}].{field_name} must be "
                    "a non-empty string without leading or "
                    "trailing whitespace"
                )

        if not isinstance(tag.aliases, tuple):
            raise ValueError(f"subset.tags[{index}].aliases must be a tuple")

        for field_name, value in (
            (
                "is_general_spoiler",
                tag.is_general_spoiler,
            ),
            ("is_adult", tag.is_adult),
        ):
            if not isinstance(value, bool):
                raise ValueError(
                    f"subset.tags[{index}].{field_name} " "must be a boolean"
                )

        if tag.tag_id in seen_tag_ids:
            raise ValueError(f"duplicate executable tag_id: {tag.tag_id}")

        if tag.tag_name in seen_tag_names:
            raise ValueError(f"duplicate executable tag_name: {tag.tag_name!r}")

        seen_tag_ids.add(tag.tag_id)
        seen_tag_names.add(tag.tag_name)
        tag_sort_keys.append(
            (
                tag.tag_id,
                tag.tag_name,
            )
        )

    if tag_sort_keys != sorted(tag_sort_keys):
        raise ValueError("subset.tags must be sorted by " "(tag_id, tag_name)")

    canonical_tag_names = set(seen_tag_names)

    alias_owners: dict[str, str] = {}

    for tag_index, tag in enumerate(subset.tags):
        aliases_in_tag: set[str] = set()

        for alias_index, alias in enumerate(tag.aliases):
            if not isinstance(alias, str) or not alias or alias != alias.strip():
                raise ValueError(
                    f"subset.tags[{tag_index}].aliases[{alias_index}] "
                    "must be a non-empty string without leading "
                    "or trailing whitespace"
                )

            if alias in aliases_in_tag:
                raise ValueError(
                    f"duplicate alias in subset.tags[{tag_index}]: " f"{alias!r}"
                )

            if alias in canonical_tag_names:
                raise ValueError(
                    f"alias {alias!r} conflicts with an executable "
                    "canonical tag name"
                )

            existing_owner = alias_owners.get(alias)
            if existing_owner is not None:
                raise ValueError(
                    f"alias {alias!r} is shared by "
                    f"{existing_owner!r} and {tag.tag_name!r}"
                )

            aliases_in_tag.add(alias)
            alias_owners[alias] = tag.tag_name

        if tag.aliases != tuple(sorted(tag.aliases)):
            raise ValueError(
                f"subset.tags[{tag_index}].aliases must be " "canonically sorted"
            )

    return {
        "subset_version": subset.subset_version,
        "derived_from_snapshot_hash": (subset.derived_from_snapshot_hash),
        "tags": [
            {
                "tag_id": tag.tag_id,
                "tag_name": tag.tag_name,
                "category": tag.category,
                "aliases": list(tag.aliases),
                "is_general_spoiler": tag.is_general_spoiler,
                "is_adult": tag.is_adult,
            }
            for tag in subset.tags
        ],
    }


def dumps_executable_tag_subset(subset: ExecutableTagSubset) -> str:
    """Serialize the approved subset deterministically."""
    canonical_mapping = executable_subset_to_mapping(subset)

    return json.dumps(
        canonical_mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def executable_tag_subset_sha256(subset: ExecutableTagSubset) -> str:
    """Return SHA-256 of canonical subset UTF-8 JSON."""
    # hash canonical serialization，不 hash audit/source file bytes。
    canonical_json = dumps_executable_tag_subset(subset)
    canonical_bytes = canonical_json.encode("utf-8")

    return hashlib.sha256(canonical_bytes).hexdigest()


def load_executable_tag_subset(path: Path) -> ExecutableTagSubset:
    """Load executable_tags.json without repairing non-canonical content."""
    # 精确检查 key/type/order/hash 格式，构造 dataclass；文件必须已 canonical。
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")

    def reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value

        return result

    try:
        json_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"failed to read executable tag subset: {path}") from exc

    try:
        raw_subset = json.loads(
            json_text,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid executable tag subset JSON: {path}") from exc

    if not isinstance(raw_subset, dict):
        raise ValueError("executable tag subset root must be a JSON object")

    expected_root_keys = (
        "subset_version",
        "derived_from_snapshot_hash",
        "tags",
    )

    if tuple(raw_subset.keys()) != expected_root_keys:
        raise ValueError(
            "executable tag subset keys must be exactly "
            f"{expected_root_keys} in that order"
        )

    if not isinstance(raw_subset["subset_version"], str):
        raise ValueError("subset_version must be a string")

    if not isinstance(
        raw_subset["derived_from_snapshot_hash"],
        str,
    ):
        raise ValueError("derived_from_snapshot_hash must be a string")

    if not isinstance(raw_subset["tags"], list):
        raise ValueError("tags must be a list")

    expected_tag_keys = (
        "tag_id",
        "tag_name",
        "category",
        "aliases",
        "is_general_spoiler",
        "is_adult",
    )

    tag_specs: list[ExecutableTagSpec] = []

    for index, raw_tag in enumerate(raw_subset["tags"]):
        if not isinstance(raw_tag, dict):
            raise ValueError(f"tags[{index}] must be a JSON object")

        if tuple(raw_tag.keys()) != expected_tag_keys:
            raise ValueError(
                f"tags[{index}] keys must be exactly "
                f"{expected_tag_keys} in that order"
            )

        if not isinstance(raw_tag["aliases"], list):
            raise ValueError(f"tags[{index}].aliases must be a list")

        tag_specs.append(
            ExecutableTagSpec(
                tag_id=raw_tag["tag_id"],
                tag_name=raw_tag["tag_name"],
                category=raw_tag["category"],
                aliases=tuple(raw_tag["aliases"]),
                is_general_spoiler=(raw_tag["is_general_spoiler"]),
                is_adult=raw_tag["is_adult"],
            )
        )

    candidate_subset = ExecutableTagSubset(
        subset_version=raw_subset["subset_version"],
        derived_from_snapshot_hash=(raw_subset["derived_from_snapshot_hash"]),
        tags=tuple(tag_specs),
    )

    try:
        canonical_mapping = executable_subset_to_mapping(candidate_subset)
    except ValueError as exc:
        raise ValueError("executable tag subset content is invalid") from exc

    if raw_subset != canonical_mapping:
        raise ValueError(
            "executable tag subset file does not match " "the canonical mapping"
        )

    return candidate_subset


def build_executable_subset_manifest(
    subset: ExecutableTagSubset,
) -> ExecutableTagSubsetManifest:
    """Build version/hash/provenance/count metadata for the subset."""
    # derived hash/version 从 subset 读取，count 计算，subset_hash 调统一 hash 函数。
    subset_hash = executable_tag_subset_sha256(subset)

    return ExecutableTagSubsetManifest(
        subset_version=subset.subset_version,
        subset_hash=subset_hash,
        derived_from_snapshot_hash=(subset.derived_from_snapshot_hash),
        approved_tag_count=len(subset.tags),
    )


def validate_domain_rule_tag_targets(
    subset: ExecutableTagSubset,
    rules: "DomainRules",
) -> None:
    """Validate group targets, active tags, and the approved subset hierarchy."""
    # Active rules/subset hierarchy contract:
    # - 将当前 exact-equality 改为 rules.tags ⊆ approved subset tag names；
    # - 每个 rules.tag_groups[*].tags 成员必须先属于 active rules.tags；
    # - 因而完整关系为 group targets ⊆ rules.tags ⊆ subset tag names；
    # - subset 中已批准但尚未 active 的额外 tag 合法；
    # - HAREM 不做名称特判，完全遍历配置；失败抛 ValueError。
    executable_subset_to_mapping(subset)

    try:
        rule_tag_names = rules.tags
        tag_groups = rules.tag_groups
    except AttributeError as exc:
        raise ValueError("rules must provide tags and tag_groups") from exc

    if not isinstance(rule_tag_names, frozenset) or not rule_tag_names:
        raise ValueError("rules.tags must be a non-empty frozenset")

    for tag_name in rule_tag_names:
        if (
            not isinstance(tag_name, str)
            or not tag_name
            or tag_name != tag_name.strip()
        ):
            raise ValueError(
                "rules.tags must contain non-empty strings "
                "without leading or trailing whitespace"
            )

    if not isinstance(tag_groups, Mapping):
        raise ValueError("rules.tag_groups must be a mapping")

    subset_tag_names = {tag.tag_name for tag in subset.tags}

    unapproved_active_tags = sorted(rule_tag_names - subset_tag_names)

    if unapproved_active_tags:
        raise ValueError(
            "rules.tags contains tags that are not present in "
            "the approved executable subset: "
            f"{unapproved_active_tags}"
        )

    for group_name, group_rule in tag_groups.items():
        if (
            not isinstance(group_name, str)
            or not group_name
            or group_name != group_name.strip()
        ):
            raise ValueError(
                "tag group names must be non-empty strings "
                "without leading or trailing whitespace"
            )

        try:
            group_targets = group_rule.tags
        except AttributeError as exc:
            raise ValueError(f"tag group {group_name!r} must provide tags") from exc

        if not isinstance(group_targets, tuple) or not group_targets:
            raise ValueError(
                f"tag group {group_name!r}.tags must be " "a non-empty tuple"
            )

        seen_group_targets: set[str] = set()

        for target_index, target in enumerate(group_targets):
            if not isinstance(target, str) or not target or target != target.strip():
                raise ValueError(
                    f"tag group {group_name!r}.tags[{target_index}] "
                    "must be a non-empty string without leading "
                    "or trailing whitespace"
                )

            if target in seen_group_targets:
                raise ValueError(
                    f"tag group {group_name!r} contains duplicate " f"target {target!r}"
                )

            if target not in rule_tag_names:
                raise ValueError(
                    f"tag group {group_name!r} target {target!r} "
                    "is not active in rules.tags"
                )

            seen_group_targets.add(target)

    return None


def write_executable_subset_bundle(
    subset: ExecutableTagSubset,
    *,
    output_dir: Path,
) -> ExecutableTagSubsetManifest:
    """Write canonical subset and manifest without overwriting files."""
    # 写 executable_tags.json 与 manifest.json；预检冲突、使用 UTF-8，并返回 manifest。
    if not isinstance(output_dir, Path):
        raise ValueError("output_dir must be a pathlib.Path")

    manifest = build_executable_subset_manifest(subset)
    subset_json = dumps_executable_tag_subset(subset)

    manifest_mapping = {
        "subset_version": manifest.subset_version,
        "subset_hash": manifest.subset_hash,
        "derived_from_snapshot_hash": (manifest.derived_from_snapshot_hash),
        "approved_tag_count": manifest.approved_tag_count,
    }

    manifest_json = (
        json.dumps(
            manifest_mapping,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    subset_path = output_dir / "executable_tags.json"
    manifest_path = output_dir / "manifest.json"

    target_paths = (
        subset_path,
        manifest_path,
    )

    existing_paths = [path for path in target_paths if path.exists()]

    if existing_paths:
        formatted_paths = ", ".join(str(path) for path in existing_paths)
        raise FileExistsError(
            "executable subset bundle target already exists: " f"{formatted_paths}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    files_to_write = (
        (subset_path, subset_json),
        (manifest_path, manifest_json),
    )

    for path, content in files_to_write:
        with path.open(
            mode="x",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(content)

    return manifest
