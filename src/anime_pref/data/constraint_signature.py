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
    # TODO-16 (Schema Contract v0.1.1): 调用统一 validate_query(query)，删除本函数
    # 内重复且较弱的结构验证。signature 继续只读取 hard constraints，token 规则不变。
    # TODO-10: 严格检查完整 hard_constraints 结构，根据非空列表/非 None bound
    # 选择 token，并按 SIGNATURE_ORDER 用 " + " 连接。
    # signature 只描述 hard constraints，不读取 reference_titles、soft_preferences
    # 或 unresolved_preferences。完全没有 hard constraint 时返回 "NO_HARD_CONSTRAINT"。
    # 结构错误抛 ValueError，不要把错误输入当成空约束。

    #验证顶层结构
    if not isinstance(query, Mapping):
        raise ValueError("query must be a Mapping")
    if "hard_constraints" not in query:
        raise ValueError("query missing 'hard_constraints'")
    hard = query["hard_constraints"]
    if not isinstance(hard, dict):
        raise ValueError("hard_constraints must be a dict")
    
    #hard_constraints
    required = {"genres", "tags", "year", "episodes", "formats", "status"}
    if set(hard) != required:
        missing = required - set(hard)
        extra = set(hard) - required
        if missing:
            raise ValueError(f"hard_constraints missing fields: {missing}")
        if extra:
            raise ValueError(f"hard_constraints has unexpected fields: {extra}")

    #验证字符串列表
    def check_string_list(val: Any, name: str) -> None:
        if not isinstance(val, list):
            raise ValueError(f"{name} must be a list")
        for idx, item in enumerate(val):
            if not isinstance(item, str):
                raise ValueError(f"{name}[{idx}] must be a string, got {type(item).__name__}")

    # 验证 genres 和 tags（包含 all_of / any_of / none_of
    for field in ("genres", "tags"):
        obj = hard.get(field)
        if not isinstance(obj, dict):
            raise ValueError(f"hard_constraints.{field} must be a dict")
        expected_keys = {"all_of", "any_of", "none_of"}
        if set(obj) != expected_keys:
            raise ValueError(f"hard_constraints.{field} keys must be {expected_keys}")
        for op in ("all_of", "any_of", "none_of"):
            check_string_list(obj.get(op), f"hard_constraints.{field}.{op}")

    # 验证 year 和 episodes（min / max）
    for field in ("year", "episodes"):
        obj = hard.get(field)
        if not isinstance(obj, dict):
            raise ValueError(f"hard_constraints.{field} must be a dict")
        expected_keys = {"min", "max"}
        if set(obj) != expected_keys:
            raise ValueError(f"hard_constraints.{field} keys must be {expected_keys}")
        for bound in ("min", "max"):
            val = obj.get(bound)
            if val is not None and (not isinstance(val, int) or isinstance(val, bool)):
                raise ValueError(f"hard_constraints.{field}.{bound} must be an int or None")

    # 验证 formats 和 status（字符串列表）
    for field in ("formats", "status"):
        check_string_list(hard.get(field), f"hard_constraints.{field}")

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
