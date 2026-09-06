"""Create structural signatures for distribution and leakage audits."""

from typing import Any, Mapping


# Signature order is part of the dataset contract, not alphabetical order.
SIGNATURE_ORDER = (
    "GENRE_ALL",
    "GENRE_ANY",
    "GENRE_NONE",
    "TAG_ALL",
    "TAG_ANY",
    "TAG_NONE",
    "YEAR_MIN",
    "YEAR_MAX",
    "EPISODE_MIN",
    "EPISODE_MAX",
    "FORMAT",
    "STATUS",
)


def build_constraint_signature(query: Mapping[str, Any]) -> str:
    """Return a stable signature such as ``GENRE_ANY + YEAR_MIN``."""
    # TODO-10: 严格检查完整 hard_constraints 结构，根据非空列表/非 None bound
    # 选择 token，并按 SIGNATURE_ORDER 用 " + " 连接。
    # signature 只描述 hard constraints，不读取 reference_titles、soft_preferences
    # 或 unresolved_preferences。完全没有 hard constraint 时返回 "NO_HARD_CONSTRAINT"。
    # 结构错误抛 ValueError，不要把错误输入当成空约束。
    raise NotImplementedError("TODO-10: build constraint signature")

