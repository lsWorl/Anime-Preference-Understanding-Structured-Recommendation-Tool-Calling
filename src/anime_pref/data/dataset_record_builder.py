"""Build and validate deterministic dataset records from canonical semantics."""

from collections.abc import Mapping
from typing import Any

from anime_pref.data.query_builder import DomainRules
from anime_pref.schemas.dataset_record import DatasetRecordSpec
from anime_pref.schemas.preference_query import SemanticSpec,SetConstraintSpec,RangeConstraintSpec


def count_hard_semantic_clauses(spec: SemanticSpec) -> int:
    """Count user-expressed hard clauses before tag-group expansion."""
    # TODO-20:
    # - 对 genres、tags、tag_groups 分别按 SetConstraintSpec 计数：
    #   all_of += len(all_of)，any_of 非空 += 1，none_of += len(none_of)；
    # - tag group 必须在 pre-expansion spec 上计数，HAREM 一个 concept 只能计 1；
    # - year/episodes 每个非 None bound +1；
    # - formats/status 每个非空 OR list +1；
    # - reference/soft/unresolved 不计数；
    # - 本函数不修复 spec。类型或结构错误抛 ValueError。
    if not isinstance(spec, SemanticSpec):
        raise ValueError("spec must be a SemanticSpec instance")
    
    def count_set_constraint(constraint:SetConstraintSpec,name:str) -> int:
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
                    raise ValueError(f"{name}.{operator} must not contain empty strings")

                if value != value.strip():
                    raise ValueError(f"{name}.{operator} values must not have leading/trailing whitespace")

            if len(values) != len(set(values)):
                raise ValueError(f"{name}.{operator} contains duplicate values")
            
        operator_sets = {operator: set(getattr(constraint, operator)) for operator in operators}

        for left, right in (("all_of", "any_of"),("all_of", "none_of"),("any_of", "none_of"),):
            overlap = operator_sets[left] & operator_sets[right]
            if overlap:
                raise ValueError(f"{name}.{left} and {name}.{right} overlap: {overlap}")
        return (len(constraint.all_of) + (1 if constraint.any_of else 0)+ len(constraint.none_of))

    def count_range_constraint(constraint: RangeConstraintSpec,name: str,) -> int:
        if not isinstance(constraint, RangeConstraintSpec):
            raise ValueError(f"{name} must be a RangeConstraintSpec")

        for bound_name, bound in (("min", constraint.min),("max", constraint.max),):
            if bound is not None and (not isinstance(bound, int) or isinstance(bound, bool)):
                raise ValueError(f"{name}.{bound_name} must be an integer or None")

        if (constraint.min is not None and constraint.max is not None and constraint.min > constraint.max):
            raise ValueError(f"{name}.min must not be greater than {name}.max")

        return (int(constraint.min is not None) + int(constraint.max is not None))

    def validate_string_tuple(values: tuple[str, ...],name: str,) -> None:
        if not isinstance(values, tuple):
            raise ValueError(f"{name} must be a tuple")

        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"{name} must contain only strings")

            if not value:
                raise ValueError(f"{name} must not contain empty strings")

            if value != value.strip():
                raise ValueError(f"{name} values must not have leading/trailing whitespace")

        if len(values) != len(set(values)):
            raise ValueError(f"{name} contains duplicate values")


    count = 0
    #genres、tags、tag_groups 分别按 SetConstraintSpec 计数
    for field_name in ("genres", "tags", "tag_groups"):
        count += count_set_constraint(getattr(spec, field_name),field_name)

    #year/episodes 每个非 None bound +1
    for field_name in ("year", "episodes"):
        count += count_range_constraint(getattr(spec, field_name),field_name)

    for field_name in ("formats","status","reference_titles","soft_preferences","unresolved_preferences"):
        validate_string_tuple(getattr(spec, field_name),field_name)

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
    # TODO-21:
    # - 先通过 build_query(spec, rules) 验证完整 semantic spec；
    # - 收集 all_of/any_of/none_of 中实际使用 group 的 normalization_rule_id；
    # - 不按 expansion 后 tag 数量重复记录；
    # - 返回去重后的字符串升序 tuple；如果输入本身造成重复/冲突，应报错而非掩盖。
    raise NotImplementedError("TODO-21: collect normalization provenance")


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
    # TODO-22:
    # - 对标识字段做严格类型/非空/首尾 whitespace 检查；seed 接受 int 但排除 bool；
    # - semantic_spec 转为只含 JSON types 的完整 deterministic mapping；
    # - gold_query 在这里做 structural validation 并 canonicalize；调用方必须已结合 rules
    #   完成 domain validation；normalization_rule_ids 必须已排序、唯一且无首尾 whitespace；
    # - identity payload 包含本函数全部参数；None 也显式保留；
    # - 使用 sort_keys=True、紧凑 separators、ensure_ascii=False、allow_nan=False；
    # - 对 UTF-8 bytes 计算 SHA-256，返回 ``sample_`` + 64 位小写 hex；
    # - 不使用 Python hash()、时间、随机数、对象 repr 或 dict 插入顺序。
    raise NotImplementedError("TODO-22: build deterministic sample ID")


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
    # TODO-23:
    # - schema_version 必须取 rules.schema_version，调用方不能另传；
    # - 调用 build_query，并让结果同时通过 structural 和 domain validation；
    # - 计算 signature、pre-expansion constraint_count、normalization_rule_ids；
    # - 使用 make_sample_id 计算 ID；
    # - user_text 是 raw utterance：要求 str 且 strip 后非空，但不得改写保存值；
    # - optional paraphrase_model/prompt_version 要么同时为 None，要么同时是合法非空 ID；
    # - 返回 DatasetRecordSpec；不得接受调用方覆盖任何 derived field。
    raise NotImplementedError("TODO-23: build DatasetRecordSpec")


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
    raise NotImplementedError("TODO-24: validate DatasetRecordSpec consistency")
