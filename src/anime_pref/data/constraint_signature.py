"""Create structural signatures for distribution and leakage audits."""

from typing import Any, Mapping
from anime_pref.data.query_validation import validate_query

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
    validate_query(query)

    hard = query["hard_constraints"]

    # 提取约束状态并用映射生成 token
    constraint_flags = {
        "GENRE_ALL": bool(hard["genres"]["all_of"]),
        "GENRE_ANY": bool(hard["genres"]["any_of"]),
        "GENRE_NONE": bool(hard["genres"]["none_of"]),
        "TAG_ALL": bool(hard["tags"]["all_of"]),
        "TAG_ANY": bool(hard["tags"]["any_of"]),
        "TAG_NONE": bool(hard["tags"]["none_of"]),
        "YEAR_MIN": hard["year"]["min"] is not None,
        "YEAR_MAX": hard["year"]["max"] is not None,
        "EPISODE_MIN": hard["episodes"]["min"] is not None,
        "EPISODE_MAX": hard["episodes"]["max"] is not None,
        "FORMAT": bool(hard["formats"]),
        "STATUS": bool(hard["status"]),
    }

    tokens = [token for token in SIGNATURE_ORDER if constraint_flags[token]]
    if not tokens:
        return "NO_HARD_CONSTRAINT"
    return " + ".join(tokens)
