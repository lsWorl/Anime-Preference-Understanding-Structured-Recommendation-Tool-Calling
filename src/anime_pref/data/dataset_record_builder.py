"""Build and validate deterministic dataset records from canonical semantics."""

from collections.abc import Mapping
from typing import Any

from anime_pref.data.constraint_signature import build_constraint_signature
from anime_pref.data.query_builder import DomainRules, build_query
from anime_pref.data.domain_validation import validate_query_domain
from anime_pref.data.query_validation import (
    SET_OPERATOR_KEY_ORDER,
    canonicalize_query,
    validate_query_structure,
)
from anime_pref.schemas.dataset_record import DatasetRecordSpec
from anime_pref.schemas.preference_query import (
    SemanticSpec,
    SetConstraintSpec,
    RangeConstraintSpec,
)


import hashlib
import json


def count_hard_semantic_clauses(spec: SemanticSpec) -> int:
    """Count user-expressed hard clauses before tag-group expansion."""
    # - 对 genres、tags、tag_groups 分别按 SetConstraintSpec 计数：
    #   all_of += len(all_of)，any_of 非空 += 1，none_of += len(none_of)；
    # - tag group 必须在 pre-expansion spec 上计数，HAREM 一个 concept 只能计 1；
    # - year/episodes 每个非 None bound +1；
    # - formats/status 每个非空 OR list +1；
    # - reference/soft/unresolved 不计数；
    # - 本函数不修复 spec。类型或结构错误抛 ValueError。
    if not isinstance(spec, SemanticSpec):
        raise ValueError("spec must be a SemanticSpec instance")

    def count_set_constraint(constraint: SetConstraintSpec, name: str) -> int:
        if not isinstance(constraint, SetConstraintSpec):
            raise ValueError(f"{name} must be a SetConstraintSpec")
        operators = ("all_of", "any_of", "none_of")
        for operator in operators:
            values = getattr(constraint, operator)
            if not isinstance(values, tuple):
                raise ValueError(f"{name}.{operator} must be a tuple")
            for value in values:
                if not isinstance(value, str):
                    raise ValueError(f"{name}.{operator} must contain only strings")
                if not value:
                    raise ValueError(
                        f"{name}.{operator} must not contain empty strings"
                    )

                if value != value.strip():
                    raise ValueError(
                        f"{name}.{operator} values must not have leading/trailing whitespace"
                    )

            if len(values) != len(set(values)):
                raise ValueError(f"{name}.{operator} contains duplicate values")

        operator_sets = {
            operator: set(getattr(constraint, operator)) for operator in operators
        }

        for left, right in (
            ("all_of", "any_of"),
            ("all_of", "none_of"),
            ("any_of", "none_of"),
        ):
            overlap = operator_sets[left] & operator_sets[right]
            if overlap:
                raise ValueError(f"{name}.{left} and {name}.{right} overlap: {overlap}")
        return (
            len(constraint.all_of)
            + (1 if constraint.any_of else 0)
            + len(constraint.none_of)
        )

    def count_range_constraint(
        constraint: RangeConstraintSpec,
        name: str,
    ) -> int:
        if not isinstance(constraint, RangeConstraintSpec):
            raise ValueError(f"{name} must be a RangeConstraintSpec")

        for bound_name, bound in (
            ("min", constraint.min),
            ("max", constraint.max),
        ):
            if bound is not None and (
                not isinstance(bound, int) or isinstance(bound, bool)
            ):
                raise ValueError(f"{name}.{bound_name} must be an integer or None")

        if (
            constraint.min is not None
            and constraint.max is not None
            and constraint.min > constraint.max
        ):
            raise ValueError(f"{name}.min must not be greater than {name}.max")

        return int(constraint.min is not None) + int(constraint.max is not None)

    def validate_string_tuple(
        values: tuple[str, ...],
        name: str,
    ) -> None:
        if not isinstance(values, tuple):
            raise ValueError(f"{name} must be a tuple")

        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"{name} must contain only strings")

            if not value:
                raise ValueError(f"{name} must not contain empty strings")

            if value != value.strip():
                raise ValueError(
                    f"{name} values must not have leading/trailing whitespace"
                )

        if len(values) != len(set(values)):
            raise ValueError(f"{name} contains duplicate values")

    count = 0
    # genres、tags、tag_groups 分别按 SetConstraintSpec 计数
    for field_name in ("genres", "tags", "tag_groups"):
        count += count_set_constraint(getattr(spec, field_name), field_name)

    # year/episodes 每个非 None bound +1
    for field_name in ("year", "episodes"):
        count += count_range_constraint(getattr(spec, field_name), field_name)

    for field_name in (
        "formats",
        "status",
        "reference_titles",
        "soft_preferences",
        "unresolved_preferences",
    ):
        validate_string_tuple(getattr(spec, field_name), field_name)

    for field_name in ("formats", "status"):
        values = getattr(spec, field_name)
        if values:
            count += 1

    return count


def collect_normalization_rule_ids(
    spec: SemanticSpec,
    rules: DomainRules,
) -> tuple[str, ...]:
    """Return canonical rule IDs for tag groups used by the semantic spec."""
    # - 先通过 build_query(spec, rules) 验证完整 semantic spec；
    # - 收集 all_of/any_of/none_of 中实际使用 group 的 normalization_rule_id；
    # - 不按 expansion 后 tag 数量重复记录；
    # - 返回去重后的字符串升序 tuple；如果输入本身造成重复/冲突，应报错而非掩盖。

    # 通过 build_query(spec, rules) 验证完整 semantic spec
    build_query(spec, rules)

    # 收集 all_of/any_of/none_of 中实际使用 group 的 normalization_rule_id
    rule_ids: list[str] = []

    for operator in SET_OPERATOR_KEY_ORDER:
        group_names = getattr(spec.tag_groups, operator)

        for group_name in group_names:
            group_rule = rules.tag_groups[group_name]
            rule_ids.append(group_rule.normalization_rule_id)

    # 去重
    unique_rule_ids = set(rule_ids)
    if len(rule_ids) != len(unique_rule_ids):
        raise ValueError("normalization rule IDs contain duplicates")
    # 返回去重后的字符串升序 tuple；如果输入本身造成重复/冲突，应报错而非掩盖。
    return tuple(sorted(unique_rule_ids))


def _validate_identifier(value: Any, name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value:
        raise ValueError(f"{name} must be non-empty")

    if value != value.strip():
        raise ValueError(f"{name} must not have leading/trailing whitespace")


def _validate_user_text(value: Any, name: str = "user_text") -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _validate_normalization_rule_ids(
    rule_ids: Any,
) -> None:
    if not isinstance(rule_ids, tuple):
        raise ValueError("normalization_rule_ids must be a tuple")

    for rule_id in rule_ids:
        _validate_identifier(
            rule_id,
            "normalization_rule_ids item",
        )

    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("normalization_rule_ids contains duplicates")

    if rule_ids != tuple(sorted(rule_ids)):
        raise ValueError("normalization_rule_ids must be sorted")


def _semantic_spec_to_json_mapping(
    spec: SemanticSpec,
) -> dict[str, Any]:
    # TODO-22a：复用现有函数验证 SemanticSpec 的基本结构。
    count_hard_semantic_clauses(spec)

    def set_constraint_to_mapping(
        constraint: SetConstraintSpec,
    ) -> dict[str, list[str]]:
        return {
            operator: sorted(getattr(constraint, operator))
            for operator in SET_OPERATOR_KEY_ORDER
        }

    return {
        "genres": set_constraint_to_mapping(spec.genres),
        "tags": set_constraint_to_mapping(spec.tags),
        "tag_groups": set_constraint_to_mapping(spec.tag_groups),
        "year": {
            "min": spec.year.min,
            "max": spec.year.max,
        },
        "episodes": {
            "min": spec.episodes.min,
            "max": spec.episodes.max,
        },
        "formats": sorted(spec.formats),
        "status": sorted(spec.status),
        "reference_titles": list(spec.reference_titles),
        "soft_preferences": list(spec.soft_preferences),
        "unresolved_preferences": list(spec.unresolved_preferences),
    }


def make_sample_id(
    *,
    schema_version: str,
    dataset_version: str,
    semantic_spec: SemanticSpec,
    gold_query: Mapping[str, Any],
    semantic_family: str,
    generation_family: str,
    template_id: str,
    normalization_rule_ids: tuple[str, ...],
    seed: int,
    user_text: str,
    paraphrase_model: str | None = None,
    prompt_version: str | None = None,
) -> str:
    """Create a deterministic ID from one canonical record identity payload."""
    # - 对标识字段做严格类型/非空/首尾 whitespace 检查；seed 接受 int 但排除 bool；
    # - semantic_spec 转为只含 JSON types 的完整 deterministic mapping；
    # - gold_query 在这里做 structural validation 并 canonicalize；调用方必须已结合 rules
    #   完成 domain validation；normalization_rule_ids 必须已排序、唯一且无首尾 whitespace；
    # - identity payload 包含本函数全部参数；None 也显式保留；
    # - 使用 sort_keys=True、紧凑 separators、ensure_ascii=False、allow_nan=False；
    # - 对 UTF-8 bytes 计算 SHA-256，返回 ``sample_`` + 64 位小写 hex；
    # - 不使用 Python hash()、时间、随机数、对象 repr 或 dict 插入顺序。

    # 对标识字段做严格类型/非空/首尾 whitespace 检查
    for name, value in (
        ("schema_version", schema_version),
        ("dataset_version", dataset_version),
        ("semantic_family", semantic_family),
        ("generation_family", generation_family),
        ("template_id", template_id),
    ):
        _validate_identifier(value, name)

    # seed 接受 int 但排除 bool
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    _validate_user_text(user_text)
    # 验证 optional paraphrase metadata 的配对关系
    if (paraphrase_model is None) != (prompt_version is None):
        raise ValueError(
            "paraphrase_model and prompt_version must both be None or both be provided"
        )

    if paraphrase_model is not None:
        _validate_identifier(paraphrase_model, "paraphrase_model")

        _validate_identifier(prompt_version, "prompt_version")

    _validate_normalization_rule_ids(normalization_rule_ids)

    semantic_spec_mapping = _semantic_spec_to_json_mapping(semantic_spec)

    canonical_gold_query = canonicalize_query(gold_query)

    identity_payload = {
        "schema_version": schema_version,
        "dataset_version": dataset_version,
        "semantic_spec": semantic_spec_mapping,
        "gold_query": canonical_gold_query,
        "semantic_family": semantic_family,
        "generation_family": generation_family,
        "template_id": template_id,
        "normalization_rule_ids": list(normalization_rule_ids),
        "seed": seed,
        "user_text": user_text,
        "paraphrase_model": paraphrase_model,
        "prompt_version": prompt_version,
    }
    identity_json = json.dumps(
        identity_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )

    identity_bytes = identity_json.encode("utf-8")
    digest = hashlib.sha256(identity_bytes).hexdigest()

    return f"sample_{digest}"


def build_dataset_record(
    *,
    semantic_spec: SemanticSpec,
    rules: DomainRules,
    dataset_version: str,
    semantic_family: str,
    generation_family: str,
    template_id: str,
    seed: int,
    user_text: str,
    paraphrase_model: str | None = None,
    prompt_version: str | None = None,
) -> DatasetRecordSpec:
    """Build one canonical record and all derived provenance fields."""
    gold_query = build_query(semantic_spec, rules)
    constraint_signature = build_constraint_signature(gold_query)
    constraint_count = count_hard_semantic_clauses(semantic_spec)
    normalization_rule_ids = collect_normalization_rule_ids(
        semantic_spec,
        rules,
    )

    sample_id = make_sample_id(
        schema_version=rules.schema_version,
        dataset_version=dataset_version,
        semantic_spec=semantic_spec,
        gold_query=gold_query,
        semantic_family=semantic_family,
        generation_family=generation_family,
        template_id=template_id,
        normalization_rule_ids=normalization_rule_ids,
        seed=seed,
        user_text=user_text,
        paraphrase_model=paraphrase_model,
        prompt_version=prompt_version,
    )

    return DatasetRecordSpec(
        sample_id=sample_id,
        schema_version=rules.schema_version,
        dataset_version=dataset_version,
        semantic_spec=semantic_spec,
        gold_query=gold_query,
        constraint_signature=constraint_signature,
        constraint_count=constraint_count,
        semantic_family=semantic_family,
        generation_family=generation_family,
        template_id=template_id,
        normalization_rule_ids=normalization_rule_ids,
        seed=seed,
        user_text=user_text,
        paraphrase_model=paraphrase_model,
        prompt_version=prompt_version,
    )


def validate_dataset_record(
    record: DatasetRecordSpec,
    rules: DomainRules,
) -> None:
    """Recompute derived fields and verify record provenance consistency."""
    # TODO-24:
    # - record/rules 类型错误抛 ValueError；schema_version 必须匹配 rules；
    # - 重新 build_query(record.semantic_spec, rules)，对 gold_query 做 structural/domain 检查；
    # - canonical 语义比较 expected Gold 与 record.gold_query，不依赖 key/list 输入顺序；
    # - 重算 signature、constraint_count、normalization_rule_ids 和 sample_id 并逐项比较；
    # - 验证 metadata 字符串、seed、user_text、optional paraphrase metadata；
    # - 任一不一致直接报错；不得修改 record 或静默替换字段。
    if not isinstance(record, DatasetRecordSpec):
        raise ValueError("record must be a DatasetRecordSpec instance")

    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")

    if record.schema_version != rules.schema_version:
        raise ValueError("record.schema_version does not match " "rules.schema_version")

    validate_query_structure(record.gold_query)
    validate_query_domain(record.gold_query, rules)

    expected_gold_query = build_query(
        record.semantic_spec,
        rules,
    )
    actual_canonical_gold = canonicalize_query(record.gold_query)
    expected_canonical_gold = canonicalize_query(expected_gold_query)

    if actual_canonical_gold != expected_canonical_gold:
        raise ValueError(
            "record.gold_query is inconsistent with " "record.semantic_spec"
        )
    expected_record = build_dataset_record(
        semantic_spec=record.semantic_spec,
        rules=rules,
        dataset_version=record.dataset_version,
        semantic_family=record.semantic_family,
        generation_family=record.generation_family,
        template_id=record.template_id,
        seed=record.seed,
        user_text=record.user_text,
        paraphrase_model=record.paraphrase_model,
        prompt_version=record.prompt_version,
    )

    if (
        not isinstance(record.constraint_count, int)
        or isinstance(record.constraint_count, bool)
        or record.constraint_count < 0
    ):
        raise ValueError("record.constraint_count must be a non-negative integer")

    for field_name in (
        "constraint_signature",
        "constraint_count",
        "normalization_rule_ids",
        "sample_id",
    ):
        actual_value = getattr(record, field_name)
        expected_value = getattr(expected_record, field_name)

        if actual_value != expected_value:
            raise ValueError(f"record.{field_name} is inconsistent; expected {expected_value!r}, got {actual_value!r}")

    return None
