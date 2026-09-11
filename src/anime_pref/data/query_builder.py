"""Build deterministic AnimePreferenceQuery v0.1.1 Gold JSON.

This module must only validate, expand approved rules, and serialize semantics.
It must never infer a preference or silently repair an invalid specification.
"""

from anime_pref.data.domain_validation import validate_query_domain
from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any
from anime_pref.data.query_validation import (
    canonicalize_query,
    validate_query_structure,
)
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)


@dataclass(frozen=True)
class TagGroupRule:
    """不可变标签组规则，用于配置驱动的标签组展开。"""

    tags: tuple[str, ...]
    allowed_operators: frozenset[str]
    normalization_rule_id: str


@dataclass(frozen=True)
class NumericRule:
    """不可变数值边界规则"""

    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True)
class DomainRules:
    """Validated executable vocabulary and numeric guards for one schema version.

    Use :func:`load_domain_rules` for construction so nested collections are
    normalized and exposed as immutable tuples, frozensets, and a read-only map.
    """

    # DomainRules 自身的人工版本。
    rules_version: str
    # canonical rules document 的派生 SHA-256；输入 JSON 不提供。
    rules_hash: str
    # 模型 Gold JSON 的结构契约版本。
    schema_version: str
    # 当前规则声明绑定的 approved executable subset。
    executable_subset_version: str
    executable_subset_hash: str

    genres: frozenset[str]
    tags: frozenset[str]
    formats: frozenset[str]
    statuses: frozenset[str]
    tag_groups: Mapping[str, TagGroupRule]
    # 批准的 canonical soft 词表；空集合表示当前不接受任何非空 soft 值。
    soft_preferences: frozenset[str]
    episodes: NumericRule
    year: NumericRule


# 将版本化 JSON 配置转换为 DomainRules；读取、解析、契约错误表现为 ValueError。
# 先检查精确键集合，再检查白名单、标签组和 numeric_rules；不调用外部 API。
# 白名单配置先 strip 后查重；这是配置加载政策，与 canonical spec 拒绝外部空白不同。
# tuple/frozenset/只读 mapping 限制后续修改，避免同一次构建中规则漂移。
def load_domain_rules(path: Path) -> DomainRules:
    """Load and validate one versioned domain-rules JSON file."""
    # Rules identity loading contract:
    # - 新配置必须精确包含 rules_version、schema_version、
    #   executable_subset_version、executable_subset_hash、taxonomy、tag_groups、numeric_rules；
    # - rules_hash 不允许出现在输入 JSON；它由 canonical document 计算；
    # - identity string 非空且无首尾 whitespace，subset hash 为 64 位小写 SHA-256；
    # - 构造 DomainRules 后计算并写入派生 rules_hash；不要使用 schema_version 代替它；
    # - production 配置在真实 subset 可用前保持 deferred，不填 synthetic hash。
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Failed to read or parse domain rules") from exc

    if not isinstance(data, dict):
        raise ValueError("Domain rules must be a JSON object (dict)")

    allowed_top_keys = {
        "rules_version",
        "schema_version",
        "executable_subset_version",
        "executable_subset_hash",
        "taxonomy",
        "tag_groups",
        "numeric_rules",
    }
    required_taxonomy_keys = {
        "genres",
        "tags",
        "formats",
        "statuses",
        "soft_preferences",
    }
    raw_soft_preferences = None
    soft_pref_source_name = "taxonomy.soft_preferences"

    top_keys = set(data)
    if top_keys != allowed_top_keys:
        extra = top_keys - allowed_top_keys
        missing = allowed_top_keys - top_keys
        if extra:
            raise ValueError(f"Unknown top-level keys: {extra}")
        raise ValueError(f"Missing top-level keys: {missing}")

    rules_version = data["rules_version"]
    schema_version = data["schema_version"]
    executable_subset_version = data["executable_subset_version"]
    executable_subset_hash = data["executable_subset_hash"]

    for field_name, value in (
        ("rules_version", rules_version),
        ("schema_version", schema_version),
        (
            "executable_subset_version",
            executable_subset_version,
        ),
    ):
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                f"{field_name} must be a non-empty string "
                "without leading or trailing whitespace"
            )

    if (
        not isinstance(executable_subset_hash, str)
        or len(executable_subset_hash) != 64
        or any(
            character not in "0123456789abcdef" for character in executable_subset_hash
        )
    ):
        raise ValueError(
            "executable_subset_hash must be a 64-character "
            "lowercase SHA-256 hex string"
        )

    taxonomy = data["taxonomy"]
    if not isinstance(taxonomy, dict):
        raise ValueError("taxonomy must be a dict")

    taxonomy_keys = set(taxonomy)
    if taxonomy_keys != required_taxonomy_keys:
        extra = taxonomy_keys - required_taxonomy_keys
        missing = required_taxonomy_keys - taxonomy_keys
        if extra:
            raise ValueError(f"Unknown taxonomy keys: {extra}")
        raise ValueError(f"Missing taxonomy keys: {missing}")

    # soft preferences 与其他可执行词表一起位于 taxonomy 节点；允许为空。
    if raw_soft_preferences is None:
        raw_soft_preferences = taxonomy["soft_preferences"]

    # 配置中的列表必须由非空字符串组成；清理首尾空白后检查重复。
    # allow_empty 仅放宽集合非空要求，例如尚未批准任何词条的 soft_preferences。
    def validate_allowlist(
        name: str, value: Any, *, allow_empty: bool = False
    ) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"{name} must be a list")
        if not allow_empty and not value:
            raise ValueError(f"{name} must be a non-empty list")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{name} must contain only non-empty strings")
            cleaned.append(item.strip())
        if len(cleaned) != len(set(cleaned)):
            raise ValueError(f"{name} contains duplicate values after stripping")
        return cleaned

    genres = validate_allowlist("taxonomy.genres", taxonomy["genres"])
    tags = validate_allowlist("taxonomy.tags", taxonomy["tags"])
    formats = validate_allowlist("taxonomy.formats", taxonomy["formats"])
    statuses = validate_allowlist("taxonomy.statuses", taxonomy["statuses"])
    # soft_preferences 允许为空列表
    soft_preferences = validate_allowlist(
        soft_pref_source_name, raw_soft_preferences, allow_empty=True
    )

    # 标签组是输入语义到实际 tag 的显式归一化规则，而不是 taxonomy 的别名猜测。
    raw_groups = data["tag_groups"]
    if not isinstance(raw_groups, dict):
        raise ValueError("tag_groups must be a dict")

    valid_group_operators = {"all_of", "any_of", "none_of"}
    tag_groups: dict[str, TagGroupRule] = {}
    seen_normalization_rule_ids: set[str] = set()

    for raw_group_name, raw_group_val in raw_groups.items():
        if not isinstance(raw_group_name, str) or not raw_group_name.strip():
            raise ValueError("tag_groups keys must be non-empty strings")
        group_name = raw_group_name.strip()
        if group_name in tag_groups:
            raise ValueError("duplicate tag group after stripping")

        if not isinstance(raw_group_val, dict):
            raise ValueError(f"tag_groups[{group_name}] must be a dict")

        allowed_group_keys = {"tags", "allowed_operators", "normalization_rule_id"}
        group_keys = set(raw_group_val)
        if group_keys != allowed_group_keys:
            extra = group_keys - allowed_group_keys
            missing = allowed_group_keys - group_keys
            if extra:
                raise ValueError(f"tag_groups[{group_name}] has unknown keys: {extra}")
            raise ValueError(f"tag_groups[{group_name}] is missing keys: {missing}")

        # 校验 tags
        raw_group_tags = raw_group_val["tags"]
        if not isinstance(raw_group_tags, list) or not raw_group_tags:
            raise ValueError(f"tag_groups[{group_name}].tags must be a non-empty list")
        group_tags: list[str] = []
        for raw_tag in raw_group_tags:
            if not isinstance(raw_tag, str) or not raw_tag.strip():
                raise ValueError(
                    f"tag_groups[{group_name}].tags must contain non-empty strings"
                )
            group_tags.append(raw_tag.strip())
        if len(group_tags) != len(set(group_tags)):
            raise ValueError(
                f"tag_groups[{group_name}].tags contains duplicate tags after stripping"
            )
        unknown = [t for t in group_tags if t not in tags]
        if unknown:
            raise ValueError(
                f"tag_groups[{group_name}].tags contains tags outside taxonomy.tags: {unknown}"
            )

        # 校验 allowed_operators (只能是 all_of/any_of/none_of)
        raw_ops = raw_group_val["allowed_operators"]
        if not isinstance(raw_ops, list) or not raw_ops:
            raise ValueError(
                f"tag_groups[{group_name}].allowed_operators must be a non-empty list"
            )
        group_ops: list[str] = []
        for raw_op in raw_ops:
            if not isinstance(raw_op, str) or not raw_op.strip():
                raise ValueError(
                    f"tag_groups[{group_name}].allowed_operators must contain non-empty strings"
                )
            op = raw_op.strip()
            if op not in valid_group_operators:
                raise ValueError(
                    f"tag_groups[{group_name}].allowed_operators contains invalid operator: {op}"
                )
            group_ops.append(op)
        if len(group_ops) != len(set(group_ops)):
            raise ValueError(
                f"tag_groups[{group_name}].allowed_operators contains duplicate operators"
            )

        # 校验 normalization_rule_id (唯一、非空且无首尾 whitespace)
        rule_id = raw_group_val["normalization_rule_id"]
        if not isinstance(rule_id, str):
            raise ValueError(
                f"tag_groups[{group_name}].normalization_rule_id must be a string"
            )
        if not rule_id or rule_id != rule_id.strip():
            raise ValueError(
                f"tag_groups[{group_name}].normalization_rule_id must be non-empty "
                f"and have no leading/trailing whitespace: {rule_id!r}"
            )
        if rule_id in seen_normalization_rule_ids:
            raise ValueError(f"duplicate normalization_rule_id: {rule_id}")
        seen_normalization_rule_ids.add(rule_id)

        tag_groups[group_name] = TagGroupRule(
            tags=tuple(group_tags),
            allowed_operators=frozenset(group_ops),
            normalization_rule_id=rule_id,
        )

    # null 表示该方向不设领域有效性边界，而不是把 null 填进用户偏好。
    raw_numeric = data["numeric_rules"]
    if not isinstance(raw_numeric, dict):
        raise ValueError("numeric_rules must be a dict")
    if set(raw_numeric) != {"episodes", "year"}:
        extra = set(raw_numeric) - {"episodes", "year"}
        missing = {"episodes", "year"} - set(raw_numeric)
        if extra:
            raise ValueError(
                f"numeric_rules[{raw_numeric}] contains unknown bound keys: {extra}"
            )
        raise ValueError(f"numeric_rules[{raw_numeric}] is missing keys: {missing}")

    numeric_rules: dict[str, NumericRule] = {}
    for raw_rule_name, raw_rule_val in raw_numeric.items():
        if not isinstance(raw_rule_name, str) or not raw_rule_name.strip():
            raise ValueError("numeric_rules keys must be non-empty strings")
        rule_name = raw_rule_name.strip()
        if rule_name in numeric_rules:
            raise ValueError(f"duplicate numeric rule key: {rule_name}")

        if isinstance(raw_rule_val, dict):
            required_bound_keys = {"minimum", "maximum"}
            bound_keys = set(raw_rule_val)

            if bound_keys != required_bound_keys:
                extra = bound_keys - required_bound_keys
                missing = required_bound_keys - bound_keys
                if extra:
                    raise ValueError(
                        f"numeric_rules[{rule_name}] contains unknown bound keys: {extra}"
                    )
                raise ValueError(
                    f"numeric_rules[{rule_name}] is missing keys: {missing}"
                )

            minimum = raw_rule_val["minimum"]
            maximum = raw_rule_val["maximum"]
            for bound_name, bound in (("minimum", minimum), ("maximum", maximum)):
                if bound is not None and (
                    not isinstance(bound, int) or isinstance(bound, bool)
                ):
                    raise ValueError(
                        f"numeric_rules[{rule_name}].{bound_name} "
                        "must be an integer or None"
                    )
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(
                    f"numeric_rules[{rule_name}].min must not be greater than max"
                )
            numeric_rules[rule_name] = NumericRule(minimum=minimum, maximum=maximum)
        else:
            raise ValueError(f"numeric_rules[{rule_name}] must be a dict")

    candidate_rules = DomainRules(
        rules_version=rules_version,
        rules_hash="0" * 64,
        schema_version=schema_version,
        executable_subset_version=(executable_subset_version),
        executable_subset_hash=executable_subset_hash,
        genres=frozenset(genres),
        tags=frozenset(tags),
        formats=frozenset(formats),
        statuses=frozenset(statuses),
        tag_groups=MappingProxyType(tag_groups),
        soft_preferences=frozenset(soft_preferences),
        episodes=numeric_rules["episodes"],
        year=numeric_rules["year"],
    )

    # Local import avoids a module-import cycle:
    # rules_identity imports DomainRules from this module.
    from anime_pref.data.rules_identity import (
        domain_rules_sha256,
    )

    computed_rules_hash = domain_rules_sha256(candidate_rules)

    return replace(
        candidate_rules,
        rules_hash=computed_rules_hash,
    )


# 把已明确的语义构建为完整 Gold 字典，不从 user_text 或 reference_titles 推断新偏好。
# 先验证输入 tuple，再按 group.allowed_operators 展开标签，最后执行结构与领域校验。
# HAREM 的 operator 限制来自配置；没有按名称特判。空数组与 None 边界始终保留。
def build_query(spec: SemanticSpec, rules: DomainRules) -> dict[str, Any]:
    """Validate a semantic spec and deterministically build Gold JSON v0.1.1."""
    if not isinstance(spec, SemanticSpec):
        raise ValueError("spec must be a SemanticSpec instance")
    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")

    operators = ("all_of", "any_of", "none_of")

    # 输入模型使用 tuple，输出 JSON 使用 list；此处同时执行 canonical 字符串和重复检查。
    # sort_output 只用于集合语义字段；文本字段保留原有顺序，不代表允许首尾空白。
    def validate_string_tuple(
        value: Any,
        name: str,
        *,
        allowlist: frozenset[str] | set[str] | None = None,
        sort_output: bool,
    ) -> list[str]:
        # SemanticSpec 使用 tuple；元素必须是唯一、非空且没有首尾空白的字符串。
        # 有 allowlist 时要求精确命中；集合语义字段按需排序，文本字段保留顺序。
        if not isinstance(value, tuple):
            raise ValueError(f"{name} must be a tuple")
        for item in value:
            if not isinstance(item, str):
                raise ValueError("content must is str")
            if not item:
                raise ValueError("content must is not empty")
            if item != item.strip():
                raise ValueError("content must is not empty whitespace")
        if len(value) != len(set(value)):
            raise ValueError(f"{name} contains duplicate values")
        if allowlist is not None:
            unknown = [item for item in value if item not in allowlist]
            if unknown:
                raise ValueError(
                    f"{name} contains values outside its allowlist: {unknown}"
                )
        result = list(value)
        return sorted(result) if sort_output else result

    # 逐个验证 all/any/none，再用集合交集拒绝跨 operator 重复。
    # 拒绝重叠是当前规格的输入政策，不是在求解查询能否匹配实际作品。
    def validate_set_constraint(
        value: Any,
        name: str,
        allowlist: frozenset[str] | set[str],
    ) -> dict[str, list[str]]:
        if not isinstance(value, SetConstraintSpec):
            raise ValueError(f"{name} must be a SetConstraintSpec")
        result = {
            operator: validate_string_tuple(
                getattr(value, operator),
                f"{name}.{operator}",
                allowlist=allowlist,
                sort_output=True,
            )
            for operator in operators
        }
        operator_sets = {key: set(items) for key, items in result.items()}
        for left, right in (
            ("all_of", "any_of"),
            ("all_of", "none_of"),
            ("any_of", "none_of"),
        ):
            overlap = operator_sets[left] & operator_sets[right]
            if overlap:
                raise ValueError(f"{name}.{left} and {name}.{right} overlap: {overlap}")
        return result

    genres = validate_set_constraint(spec.genres, "genres", rules.genres)
    tags = validate_set_constraint(spec.tags, "tags", rules.tags)
    tag_groups = validate_set_constraint(
        spec.tag_groups,
        "tag_groups",
        set(rules.tag_groups),
    )

    # Approved groups expand into the same operator. Repeated tags are invalid;
    # silently deduplicating them would hide a bad semantic specification.
    expanded_tags: dict[str, list[str]] = {}
    for operator in operators:
        combined = list(tags[operator])
        for group_name in tag_groups[operator]:
            group_rule = rules.tag_groups[group_name]
            if operator not in group_rule.allowed_operators:
                raise ValueError(
                    f"tag group {group_name} does not allow operator {operator}"
                )
            combined.extend(group_rule.tags)
        if len(combined) != len(set(combined)):
            raise ValueError(
                f"tags.{operator} contains duplicates after group expansion"
            )
        expanded_tags[operator] = sorted(combined)

    expanded_sets = {key: set(items) for key, items in expanded_tags.items()}
    for left, right in (
        ("all_of", "any_of"),
        ("all_of", "none_of"),
        ("any_of", "none_of"),
    ):
        overlap = expanded_sets[left] & expanded_sets[right]
        if overlap:
            raise ValueError(
                f"tags.{left} and tags.{right} overlap after group expansion: {overlap}"
            )

    # None 表示未表达，不补默认边界；非空值须为 int 且不能为 bool。
    # 版本化 minimum/maximum 是有效性边界，min/max 顺序另行检查；不是采样分布。
    def validate_range(
        value: Any,
        name: str,
        rule: NumericRule,
    ) -> dict[str, int | None]:
        if not isinstance(value, RangeConstraintSpec):
            raise ValueError(f"{name} must be a RangeConstraintSpec")
        for bound_name, bound in (("min", value.min), ("max", value.max)):
            if bound is None:
                continue
            if not isinstance(bound, int) or isinstance(bound, bool):
                raise ValueError(f"{name}.{bound_name} must be an integer or None")
            if rule.minimum is not None and bound < rule.minimum:
                raise ValueError("must > rule.minimum")

            if rule.maximum is not None and bound > rule.maximum:
                raise ValueError("must < rule.maximum")
        if value.min is not None and value.max is not None and value.min > value.max:
            raise ValueError(f"{name}.min must not be greater than {name}.max")
        return {"min": value.min, "max": value.max}

    formats = validate_string_tuple(
        spec.formats,
        "formats",
        allowlist=rules.formats,
        sort_output=True,
    )
    status = validate_string_tuple(
        spec.status,
        "status",
        allowlist=rules.statuses,
        sort_output=True,
    )

    # canonical 文本不允许首尾空白；合法值按原值和原顺序复制，不静默 strip。
    # soft_preferences 还必须属于批准词表，未知表达应由上游明确放入 unresolved。
    reference_titles = validate_string_tuple(
        spec.reference_titles,
        "reference_titles",
        sort_output=False,
    )
    soft_preferences = validate_string_tuple(
        spec.soft_preferences,
        "soft_preferences",
        allowlist=rules.soft_preferences,
        sort_output=False,
    )
    unresolved_preferences = validate_string_tuple(
        spec.unresolved_preferences,
        "unresolved_preferences",
        sort_output=False,
    )

    query = {
        "hard_constraints": {
            "genres": genres,
            "tags": expanded_tags,
            "year": validate_range(spec.year, "year", rules.year),
            "episodes": validate_range(spec.episodes, "episodes", rules.episodes),
            "formats": formats,
            "status": status,
        },
        "reference_titles": reference_titles,
        "soft_preferences": soft_preferences,
        "unresolved_preferences": unresolved_preferences,
    }
    validate_query_structure(query)
    validate_query_domain(query, rules)

    return query


# 共享 canonicalizer 先做结构校验，再重建键序与集合排序，因此接受合法的乱序输入。
# 此函数没有 rules 参数，不证明 taxonomy/domain 合法；构建 Gold 应先走 build_query。
# UTF-8/Unicode 紧凑 JSON 保持输出稳定；不修改原始 query。
def dumps_query(query: Mapping[str, Any]) -> str:
    """Serialize a validated query in one canonical, Unicode-preserving form."""
    canonical_query = canonicalize_query(query)

    try:
        # 这里不使用 sort_keys：键序由 canonicalize_query 的 schema 常量明确控制。
        return json.dumps(
            canonical_query,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("query is not JSON serializable") from exc
