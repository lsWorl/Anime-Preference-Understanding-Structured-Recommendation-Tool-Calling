"""Domain/executable-vocabulary validation for AnimePreferenceQuery v0.1.1."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anime_pref.data.query_builder import DomainRules, NumericRule
from anime_pref.data.query_validation import SET_OPERATOR_KEY_ORDER,validate_query_structure

if TYPE_CHECKING:
    from anime_pref.data.query_builder import DomainRules


# 结构校验通过后，按当前 DomainRules 检查可执行词表和数值上下界。
# 局部导入 DomainRules 用于运行时 isinstance，避免模块加载时的循环导入。
# reference/unresolved 没有可执行词表；此函数不解释这些文本，也不修改 query。
def validate_query_domain(
    query: Mapping[str, Any],
    rules: "DomainRules",
) -> None:
    """Validate a structurally valid query against executable domain rules."""
    # 已完成的领域校验（原 TODO-19）：
    # 1. 首先调用 validate_query_structure(query)，但不要捕获并改写其 ValueError；
    # 2. rules 必须是 DomainRules；
    # 3. genres/tags 三个 operator 的每个值分别属于 rules.genres/rules.tags；
    # 4. formats/status 分别属于 rules.formats/rules.statuses；
    # 5. soft_preferences 必须属于 rules.soft_preferences；
    # 6. year/episodes 的每个非 None bound 必须满足对应 NumericRule；
    # 7. reference_titles/unresolved_preferences 没有 executable vocabulary，不在这里映射；
    # 8. 成功返回 None；失败抛 ValueError；不得 strip、删除、排序或修改 query。
    validate_query_structure(query)

    from anime_pref.data.query_builder import DomainRules

    if not isinstance(rules,DomainRules):
        raise ValueError("rules must be a DomainRules instance")

    hard_constraints = query["hard_constraints"]
    #辅助函数判断是否有未知句段名字
    # 保留未知值列表便于定位错误；只检验精确成员关系，不做近似匹配或 alias 展开。
    def require_allowed_values(values: list[str],allowed_values: frozenset[str],name: str,) -> None:
        unknown_values  = [value for value in values if value not in allowed_values]

        if unknown_values:
            raise ValueError(f"{name} contains values outside domain rules: {unknown_values}")

    for field_name, allowed_values in (("genres", rules.genres),("tags", rules.tags),):
        constraint = hard_constraints[field_name]
        for operator in SET_OPERATOR_KEY_ORDER:
            require_allowed_values(constraint[operator],allowed_values,f"hard_constraints.{field_name}.{operator}",)

    for field_name, allowed_values in (("formats", rules.formats),("status", rules.statuses),):
        require_allowed_values(hard_constraints[field_name],allowed_values,f"hard_constraints.{field_name}",)

    require_allowed_values(query["soft_preferences"],rules.soft_preferences,"soft_preferences",)

    #判断数值的边界
    # 结构层已检查类型与区间顺序；这里再应用配置边界。
    # 跳过 None，因为“没表达限制”不等于使用规则边界作为用户偏好。
    def require_bounds_within_rule(bounds: Mapping[str, int | None],rule: "NumericRule",name: str,) -> None:
        for bound_name in ("min", "max"):
            bound = bounds[bound_name]

            if bound is None:
                continue

            if rule.minimum is not None and bound < rule.minimum:
                raise ValueError(f"{name}.{bound_name} must be greater than or equal to {rule.minimum}")

            if rule.maximum is not None and bound > rule.maximum:
                raise ValueError(f"{name}.{bound_name} must be less than or equal to {rule.maximum}")

    for field_name, rule in (("year", rules.year),("episodes", rules.episodes),):
        require_bounds_within_rule(hard_constraints[field_name],rule,f"hard_constraints.{field_name}",)
    

    

