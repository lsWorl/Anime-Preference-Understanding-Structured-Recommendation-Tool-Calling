"""Build deterministic AnimePreferenceQuery v0.1 Gold JSON.

This module must only validate, expand approved rules, and serialize semantics.
It must never infer a preference or silently repair an invalid specification.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any
from anime_pref.data.query_validation import canonicalize_query
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
    schema_version: str
    genres: frozenset[str]
    tags: frozenset[str]
    formats: frozenset[str]
    statuses: frozenset[str]
    tag_groups: Mapping[str, TagGroupRule]
    soft_preferences: frozenset[str]
    episodes: NumericRule
    year: NumericRule

def load_domain_rules(path: Path) -> DomainRules:
    """Load and validate one versioned domain-rules JSON file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Failed to read or parse domain rules") from exc

    if not isinstance(data, dict):
        raise ValueError("Domain rules must be a JSON object (dict)")

    allowed_top_keys = {
        "schema_version",
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

    schema_version = data["schema_version"]
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("schema_version must be a non-empty string")

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

    # 如果 soft_preferences 在 taxonomy 内部，在此提取
    if raw_soft_preferences is None:
        raw_soft_preferences = taxonomy["soft_preferences"]

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

    # 1. 校验 tag_groups 与 TagGroupRule
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

    # 2. 校验 numeric_rules (null 表示尚未冻结详细 bound)
    raw_numeric = data["numeric_rules"]
    if not isinstance(raw_numeric, dict):
        raise ValueError("numeric_rules must be a dict")
    if set(raw_numeric) != {"episodes", "year"}:
        extra = set(raw_numeric) - {"episodes", "year"}
        missing = {"episodes", "year"} - set(raw_numeric)
        if extra:
            raise ValueError(f"numeric_rules[{raw_numeric}] contains unknown bound keys: {extra}")
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
                    raise ValueError(f"numeric_rules[{rule_name}] contains unknown bound keys: {extra}")
                raise ValueError(f"numeric_rules[{rule_name}] is missing keys: {missing}")
            
            minimum = raw_rule_val["minimum"]
            maximum = raw_rule_val["maximum"]
            for bound_name, bound in (("minimum", minimum),("maximum", maximum)):
                if bound is not None and (not isinstance(bound, int) or isinstance(bound, bool)):
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
            raise ValueError(
                f"numeric_rules[{rule_name}] must be a dict"
            )

    return DomainRules(
        schema_version=schema_version,
        genres=frozenset(genres),
        tags=frozenset(tags),
        formats=frozenset(formats),
        statuses=frozenset(statuses),
        tag_groups=MappingProxyType(tag_groups),
        soft_preferences=frozenset(soft_preferences),
        episodes=numeric_rules["episodes"],
        year=numeric_rules["year"],
    )


def build_query(spec: SemanticSpec, rules: DomainRules) -> dict[str, Any]:
    """Validate a semantic spec and deterministically build Gold JSON v0.1."""
    if not isinstance(spec, SemanticSpec):
        raise ValueError("spec must be a SemanticSpec instance")
    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")

    operators = ("all_of", "any_of", "none_of")
    def validate_string_tuple(
        value: Any,
        name: str,
        *,
        allowlist: frozenset[str] | set[str] | None = None,
        sort_output: bool,
    ) -> list[str]:
        # value必须是tuple，每项必须是str 不允许有空字符串 不允许首尾 whitespace 不允许重复
        # 有 allowlist 时必须全部命中 set-like 字段按需排序
        if not isinstance(value, tuple):
            raise ValueError(f"{name} must be a tuple")
        for item in value:
            if not isinstance(item,str):
                raise ValueError('content must is str')
            if not item:
                raise ValueError('content must is not empty')
            if item != item.strip():
                raise ValueError('content must is not empty whitespace')
        if len(value) != len(set(value)):
            raise ValueError(f"{name} contains duplicate values")
        if allowlist is not None:
            unknown = [item for item in value if item not in allowlist]
            if unknown:
                raise ValueError(f"{name} contains values outside its allowlist: {unknown}")
        result = list(value)
        return sorted(result) if sort_output else result

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
                raise ValueError(f"tag group {group_name} does not allow operator {operator}")
            combined.extend(group_rule.tags)
        if len(combined) != len(set(combined)):
            raise ValueError(f"tags.{operator} contains duplicates after group expansion")
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

    def validate_range(value: Any, name: str,rule: NumericRule,) -> dict[str, int | None]:
        if not isinstance(value, RangeConstraintSpec):
            raise ValueError(f"{name} must be a RangeConstraintSpec")
        for bound_name, bound in (("min", value.min), ("max", value.max)):
            if bound is None:
                continue
            if not isinstance(bound,int) or isinstance(bound,bool):
                raise ValueError(f'{name}.{bound_name} must be an integer or None')
            if rule.minimum is not None and bound < rule.minimum:
                raise ValueError('must > rule.minimum')

            if rule.maximum is not None and bound > rule.maximum:
                raise ValueError('must < rule.maximum')
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

    # User-facing semantic payload is copied exactly. Whitespace is used only
    # to reject empty values; it is never stripped from accepted expressions.
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

    # TODO-19b: 构造 query 后显式调用 validate_query_structure(query) 和
    # validate_query_domain(query, rules)，再返回 query。不要依赖“builder 前面已经检查过”
    # 作为两层 validation 的替代，也不要在验证失败时修复输出。
    return {
        "hard_constraints": {
            "genres": genres,
            "tags": expanded_tags,
            "year": validate_range(spec.year, "year", rules.year),
            "episodes": validate_range(spec.episodes, "episodes",rules.episodes),
            "formats": formats,
            "status": status,
        },
        "reference_titles": reference_titles,
        "soft_preferences": soft_preferences,
        "unresolved_preferences": unresolved_preferences,
    }


def dumps_query(query: Mapping[str, Any]) -> str:
    """Serialize a validated query in one canonical, Unicode-preserving form."""
    canonical_query = canonicalize_query(query)

    try:
        # 序列化 canonical_query
        return json.dumps(
            canonical_query,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("query is not JSON serializable") from exc
