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
    # TODO-14a:
    # - 严格检查每层 key 集合、字段类型、非空字符串、重复/跨 operator 冲突；
    # - 检查 range int（排除 bool）、min <= max、episodes 的非空 bound >= 1；
    # - formats/status 是 acceptable-value OR lists；不增加 NOT 结构；
    # - 接受任意 JSON object key order，也接受 set-like 列表的任意输入顺序；
    # - 不检查 taxonomy membership（该职责仍属于 semantic spec builder）；
    # - 非法输入统一抛 ValueError；有效输入返回 None；不得修改 query。
    raise NotImplementedError("TODO-14a: implement order-insensitive query validation")


def canonicalize_query(query: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new full-schema query in the one canonical serialization order."""
    # TODO-14b:
    # - 先调用 validate_query(query)；
    # - 按上方四组 *_KEY_ORDER 重建全新 dict；
    # - genres/tags 的集合值以及 formats/status 使用字符串升序；
    # - reference_titles/soft_preferences/unresolved_preferences 保持原顺序和原值；
    # - 保留所有空列表和 None bound；不能修改调用方对象。
    raise NotImplementedError("TODO-14b: implement canonical query rebuilding")
