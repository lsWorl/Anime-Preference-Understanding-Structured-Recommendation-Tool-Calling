"""Canonical identity and executable-subset binding for DomainRules."""

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from anime_pref.data.query_builder import (
    DomainRules,
    NumericRule,
    TagGroupRule,
)
from anime_pref.schemas.taxonomy import ExecutableTagSubset
from anime_pref.data.tag_subset import (
    executable_tag_subset_sha256,
    validate_domain_rule_tag_targets,
)


def canonical_rules_to_mapping(rules: DomainRules) -> dict[str, Any]:
    """Return the complete canonical rules document, excluding rules_hash."""
    # Canonical rules mapping contract:
    # - 严格验证 DomainRules 的 identity、active vocab、groups 和 numeric rules；
    # - 输出 rules_version/schema_version/executable subset version+hash；
    # - genres/tags/formats/statuses/soft_preferences 全部 canonical sort；
    # - tag_groups 按 group name 排序，members/operators 排序，并保留 rule ID；
    # - numeric_rules 固定 episodes/year 与 minimum/maximum key order；
    # - rules.rules_hash 绝不进入 mapping，避免自引用；不修改 rules。
    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")

    for field_name, value in (
        ("rules_version", rules.rules_version),
        ("schema_version", rules.schema_version),
        (
            "executable_subset_version",
            rules.executable_subset_version,
        ),
    ):
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                f"rules.{field_name} must be a non-empty "
                "string without leading or trailing whitespace"
            )

    for field_name, value in (
        ("rules_hash", rules.rules_hash),
        (
            "executable_subset_hash",
            rules.executable_subset_hash,
        ),
    ):
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(
                f"rules.{field_name} must be a 64-character "
                "lowercase SHA-256 hex string"
            )

    vocabulary_fields = (
        ("genres", rules.genres, False),
        ("tags", rules.tags, False),
        ("formats", rules.formats, False),
        ("statuses", rules.statuses, False),
        (
            "soft_preferences",
            rules.soft_preferences,
            True,
        ),
    )

    canonical_taxonomy: dict[str, list[str]] = {}

    for field_name, values, allow_empty in vocabulary_fields:
        if not isinstance(values, frozenset):
            raise ValueError(f"rules.{field_name} must be a frozenset")

        if not allow_empty and not values:
            raise ValueError(f"rules.{field_name} must not be empty")

        for value in values:
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(
                    f"rules.{field_name} must contain only "
                    "non-empty strings without leading or "
                    "trailing whitespace"
                )

        canonical_taxonomy[field_name] = sorted(values)

    if not isinstance(rules.tag_groups, Mapping):
        raise ValueError("rules.tag_groups must be a mapping")

    valid_group_operators = {
        "all_of",
        "any_of",
        "none_of",
    }
    seen_normalization_rule_ids: set[str] = set()
    validated_groups: dict[str, dict[str, Any]] = {}

    for group_name, group_rule in rules.tag_groups.items():
        if (
            not isinstance(group_name, str)
            or not group_name
            or group_name != group_name.strip()
        ):
            raise ValueError(
                "rules.tag_groups keys must be non-empty "
                "strings without leading or trailing whitespace"
            )

        if not isinstance(group_rule, TagGroupRule):
            raise ValueError(
                f"rules.tag_groups[{group_name!r}] must be " "a TagGroupRule"
            )

        if not isinstance(group_rule.tags, tuple) or not group_rule.tags:
            raise ValueError(
                f"rules.tag_groups[{group_name!r}].tags " "must be a non-empty tuple"
            )

        seen_group_tags: set[str] = set()

        for tag in group_rule.tags:
            if not isinstance(tag, str) or not tag or tag != tag.strip():
                raise ValueError(
                    f"rules.tag_groups[{group_name!r}].tags "
                    "must contain canonical non-empty strings"
                )

            if tag in seen_group_tags:
                raise ValueError(
                    f"rules.tag_groups[{group_name!r}].tags "
                    f"contains duplicate tag {tag!r}"
                )

            if tag not in rules.tags:
                raise ValueError(
                    f"rules.tag_groups[{group_name!r}] target "
                    f"{tag!r} is not active in rules.tags"
                )

            seen_group_tags.add(tag)

        if (
            not isinstance(
                group_rule.allowed_operators,
                frozenset,
            )
            or not group_rule.allowed_operators
        ):
            raise ValueError(
                f"rules.tag_groups[{group_name!r}]"
                ".allowed_operators must be a non-empty "
                "frozenset"
            )

        for operator in group_rule.allowed_operators:
            if (
                not isinstance(operator, str)
                or not operator
                or operator != operator.strip()
            ):
                raise ValueError(
                    f"rules.tag_groups[{group_name!r}]"
                    ".allowed_operators must contain only "
                    "canonical non-empty strings"
                )

        invalid_operators = sorted(group_rule.allowed_operators - valid_group_operators)
        if invalid_operators:
            raise ValueError(
                f"rules.tag_groups[{group_name!r}] contains "
                f"invalid operators: {invalid_operators}"
            )

        normalization_rule_id = group_rule.normalization_rule_id
        if (
            not isinstance(normalization_rule_id, str)
            or not normalization_rule_id
            or normalization_rule_id != normalization_rule_id.strip()
        ):
            raise ValueError(
                f"rules.tag_groups[{group_name!r}]"
                ".normalization_rule_id must be a non-empty "
                "string without leading or trailing whitespace"
            )

        if normalization_rule_id in seen_normalization_rule_ids:
            raise ValueError(
                "duplicate normalization_rule_id: " f"{normalization_rule_id!r}"
            )

        seen_normalization_rule_ids.add(normalization_rule_id)

        validated_groups[group_name] = {
            "tags": sorted(group_rule.tags),
            "allowed_operators": sorted(group_rule.allowed_operators),
            "normalization_rule_id": (normalization_rule_id),
        }

    canonical_tag_groups = {
        group_name: validated_groups[group_name]
        for group_name in sorted(validated_groups)
    }

    canonical_numeric_rules: dict[
        str,
        dict[str, int | None],
    ] = {}

    for rule_name, numeric_rule in (
        ("episodes", rules.episodes),
        ("year", rules.year),
    ):
        if not isinstance(numeric_rule, NumericRule):
            raise ValueError(f"rules.{rule_name} must be a NumericRule")

        minimum = numeric_rule.minimum
        maximum = numeric_rule.maximum

        for bound_name, bound in (
            ("minimum", minimum),
            ("maximum", maximum),
        ):
            if bound is not None and (
                isinstance(bound, bool) or not isinstance(bound, int)
            ):
                raise ValueError(
                    f"rules.{rule_name}.{bound_name} " "must be an integer or None"
                )

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                f"rules.{rule_name}.minimum must not be " "greater than maximum"
            )

        canonical_numeric_rules[rule_name] = {
            "minimum": minimum,
            "maximum": maximum,
        }

    return {
        "rules_version": rules.rules_version,
        "schema_version": rules.schema_version,
        "executable_subset_version": (rules.executable_subset_version),
        "executable_subset_hash": (rules.executable_subset_hash),
        "taxonomy": canonical_taxonomy,
        "tag_groups": canonical_tag_groups,
        "numeric_rules": canonical_numeric_rules,
    }


def dumps_canonical_rules(rules: DomainRules) -> str:
    """Serialize the canonical rules document as deterministic Unicode JSON."""
    # 复用 mapping；ensure_ascii=False、compact separators、allow_nan=False。
    canonical_mapping = canonical_rules_to_mapping(rules)

    return json.dumps(
        canonical_mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def domain_rules_sha256(rules: DomainRules) -> str:
    """Hash the canonical rules document as UTF-8 bytes."""
    canonical_json = dumps_canonical_rules(rules)
    canonical_bytes = canonical_json.encode("utf-8")

    return hashlib.sha256(canonical_bytes).hexdigest()


def validate_executable_rules_identity(
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> None:
    """Validate rules identity and active vocabulary against an actual subset."""
    # Executable rules/subset binding contract:
    # - 严格验证 subset，并重算 executable_tag_subset_sha256(subset)；
    # - rules 声明的 subset version/hash 必须与实际 subset 完全一致；
    # - rules.rules_hash 必须等于 domain_rules_sha256(rules)；
    # - 复用 validate_domain_rule_tag_targets 检查：
    #     group members ⊆ active rules.tags ⊆ approved subset tags；
    # - 失败直接 ValueError，不写回或修复任一对象。
    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")

    actual_subset_hash = executable_tag_subset_sha256(subset)

    if rules.executable_subset_version != subset.subset_version:
        raise ValueError(
            "rules executable subset version does not match "
            "the actual approved subset"
        )

    if rules.executable_subset_hash != actual_subset_hash:
        raise ValueError(
            "rules executable subset hash does not match " "the actual approved subset"
        )

    actual_rules_hash = domain_rules_sha256(rules)

    if rules.rules_hash != actual_rules_hash:
        raise ValueError(
            "rules.rules_hash does not match the canonical " "DomainRules content"
        )

    validate_domain_rule_tag_targets(
        subset,
        rules,
    )

    return None
