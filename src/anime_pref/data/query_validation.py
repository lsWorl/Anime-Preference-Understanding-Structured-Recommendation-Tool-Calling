"""Shared semantic validation and canonical ordering for Gold Query v0.1.1."""

from collections.abc import Mapping
from typing import Any


TOP_LEVEL_KEY_ORDER = (
    "hard_constraints",
    "reference_titles",
    "soft_preferences",
    "unresolved_preferences",
)

HARD_CONSTRAINT_KEY_ORDER = (
    "genres",
    "tags",
    "year",
    "episodes",
    "formats",
    "status",
)

SET_OPERATOR_KEY_ORDER = ("all_of", "any_of", "none_of")
RANGE_KEY_ORDER = ("min", "max")


def validate_query(query: Mapping[str, Any]) -> None:
    """Validate Schema v0.1.1 semantics without treating key order as meaning."""
    # - 严格检查每层 key 集合、字段类型、非空字符串、重复/跨 operator 冲突；
    # - 检查 range int（排除 bool）、min <= max、episodes 的非空 bound >= 1；
    # - formats/status 是 acceptable-value OR lists；不增加 NOT 结构；
    # - 接受任意 JSON object key order，也接受 set-like 列表的任意输入顺序；
    # - 不检查 taxonomy membership（该职责仍属于 semantic spec builder）；
    # - 非法输入统一抛 ValueError；有效输入返回 None；不得修改 query。

    #校验key是否和expected_keys严格相等
    def require_mapping_with_keys(value:Any,name:str,expected_keys:tuple[str,...])->Mapping[str,Any]:
        if not isinstance(value,Mapping):
            raise ValueError(f"{name} must be a mapping")

        actual_keys = set(value.keys())
        required_keys = set(expected_keys)

        if actual_keys != required_keys:
            missing = required_keys - actual_keys
            extra = actual_keys - required_keys
            raise ValueError(f"{name} has invalid keys; missing={missing}, extra={extra}")

        return value

    def require_string_list(value: Any, name: str) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"{name} must be a list")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in value
        ):
            raise ValueError(f"{name} must contain only non-empty strings")

        for item in value:
            if item != item.strip():
                raise ValueError(
                    f"{name} values must not have leading/trailing whitespace"
                )

        if len(value) != len(set(value)):
            raise ValueError(f"{name} contains duplicate values")

        return value

    root = require_mapping_with_keys(query,"query",TOP_LEVEL_KEY_ORDER)

    hard_constraints = require_mapping_with_keys(root['hard_constraints'],'hard_constraints',HARD_CONSTRAINT_KEY_ORDER)

    # genres/tags：检查 operator 结构、列表和跨 operator 重叠。
    for field_name in ("genres", "tags"):
        constraint = require_mapping_with_keys(
            hard_constraints[field_name],
            f"hard_constraints.{field_name}",
            SET_OPERATOR_KEY_ORDER
        )

        operator_sets: dict[str,set[str]] = {}

        for operator in SET_OPERATOR_KEY_ORDER:
            values = require_string_list(
                constraint[operator],
                f"hard_constraints.{field_name}.{operator}",
            )
            operator_sets[operator] = set(values)

        for left, right in (
            ("all_of", "any_of"),
            ("all_of", "none_of"),
            ("any_of", "none_of"),
        ):
            overlap = operator_sets[left] & operator_sets[right]
            if overlap:
                raise ValueError(
                    f"hard_constraints.{field_name}.{left} and "
                    f"{right} overlap: {overlap}"
                )
            
    # year/episodes：检查 range
    for field_name in ("year", "episodes"):
        bounds = require_mapping_with_keys(
        hard_constraints[field_name],
        f"hard_constraints.{field_name}",
        RANGE_KEY_ORDER,
        )
        for bound_name in RANGE_KEY_ORDER:
            bound = bounds[bound_name]

            if bound is not None and (not isinstance(bound, int)or isinstance(bound, bool)):
                raise ValueError(
                    f"hard_constraints.{field_name}.{bound_name} "
                    "must be an integer or None"
                )

            if field_name == "episodes" and bound is not None and bound < 1:
                raise ValueError(
                    f"hard_constraints.episodes.{bound_name} "
                    "must be at least 1"
                )
        if (
            bounds["min"] is not None
            and bounds["max"] is not None
            and bounds["min"] > bounds["max"]
        ):
            raise ValueError(f"hard_constraints.{field_name}.min must not exceed max")

    # formats/status 是普通 OR 列表，没有 all/any/none 结构。
    for field_name in ('formats','status'):
        require_string_list(hard_constraints[field_name],f"hard_constraints.{field_name}")

    for field_name in ("reference_titles","soft_preferences","unresolved_preferences"):
        require_string_list(root[field_name],field_name)
    

def canonicalize_query(query: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new full-schema query in the one canonical serialization order."""
    # - 先调用 validate_query(query)；
    # - 按上方四组 *_KEY_ORDER 重建全新 dict；
    # - genres/tags 的集合值以及 formats/status 使用字符串升序；
    # - reference_titles/soft_preferences/unresolved_preferences 保持原顺序和原值；
    # - 保留所有空列表和 None bound；不能修改调用方对象。
    validate_query(query)

    source_hard = query["hard_constraints"]
    canonical_hard: dict[str, Any] = {}
    for field_name in HARD_CONSTRAINT_KEY_ORDER:
        if field_name in ("genres", "tags"):
            source_constraint = source_hard[field_name]
            canonical_hard[field_name] = {
                operator: sorted(source_constraint[operator])
                for operator in SET_OPERATOR_KEY_ORDER
            }

        elif field_name in ("year","episodes"):
            source_bounds = source_hard[field_name]
            canonical_hard[field_name] = {
                bound_name: source_bounds[bound_name]
                for bound_name in RANGE_KEY_ORDER
            }
        elif field_name in ("formats", "status"):
            canonical_hard[field_name] = sorted(source_hard[field_name])

    canonical: dict[str,Any] = {}

    for field_name in TOP_LEVEL_KEY_ORDER:
        if field_name == 'hard_constraints':
            canonical[field_name] = canonical_hard
        else:
            canonical[field_name] = list(query[field_name])

    return canonical
