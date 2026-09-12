# B. Family + Complexity Planner v0.1

> 状态核对（2026-09-12）：TODO-B01～B08 已实现；B 专项测试 35 项、完整离线测试
> 89 项全部通过，无失败或跳过。

本工作块只把已验证的 `SemanticSamplerConfigSpec` 转成
`FamilyComplexityPlan(semantic_family, complexity_bucket)`。它不创建
`SemanticSpec`、DatasetRecord、operator、value、numeric bound 或自然语言。

## 文件职责

- `src/anime_pref/schemas/family_complexity.py`：不可变输出对象和类型别名。
- `src/anime_pref/sampling/family_complexity.py`：兼容矩阵、理论概率纯函数、显式 RNG 采样入口。
- `tests/test_family_complexity_planner.py`：B 阶段完整合同测试。
- `docs/family_complexity_planner_v0.1.md`：实现顺序、公式和边界说明。

## 冻结的概率语义

先归一化 family relative weights：

```text
P(F=f) = w_F(f) / sum_j(w_F(j))
```

对 hard-bearing family，只在其兼容 bucket 内重新归一化 complexity：

```text
P(C=c | F=f) = w_C(c) / sum_{k in C_f}(w_C(k))
P(F=f, C=c) = P(F=f) * P(C=c | F=f)
```

`reference_only` 固定得到 `{0: 1.0}`。`0` 不进入全局 count table，也没有虚拟权重。
因此 family 表、count 表各自乘任意正数都不改变最终 joint distribution。

## Compatibility Matrix v0.1

```text
single_constraint       -> 1
same_field_logic        -> 1 / 2 / 3
cross_field_composition -> 2 / 3 / 4 / 5_plus
normalization           -> 1 / 2 / 3 / 4 / 5_plus
reference_only          -> 0
reference_composition   -> 1 / 2 / 3 / 4 / 5_plus
```

`5_plus` 是 `>= 5` 的 bucket，不是 exact integer `5`。B 阶段不能生成最终的整数
`constraint_count`。

## 已完成的实现

1. **TODO-B01 `normalize_relative_weights`**：先完成通用正权重归一化。它必须拒绝 empty、bool、非数值、非 finite、零和负数；不得修改输入或四舍五入。
2. **TODO-B02 `compatible_complexity_buckets`**：只查冻结矩阵，未知 family 直接报错。
3. **TODO-B03 `family_probabilities`**：验证 config，并按 `SEMANTIC_FAMILY_ORDER` 构造有序权重表后调用 B01。
4. **TODO-B04 `conditional_complexity_probabilities`**：`reference_only` 直接返回 `{0: 1.0}`；其他 family 从全局 count table 取兼容项，再调用 B01。
5. **TODO-B05 `joint_family_complexity_probabilities`**：按条件概率公式相乘。禁止回到旧的 raw-product 全局归一化。
6. **TODO-B06 `complexity_marginal_probabilities`**：对 joint 按 bucket 求和，只提供理论分布，不写 G 阶段 audit。
7. **TODO-B07 `_weighted_choice`**：显式调用一次 `rng.random()`，按传入 choices 顺序走 cumulative probability。浮点尾差落到最后一个 choice。
8. **TODO-B08 `sample_family_complexity_plan`**：先抽 family；若为 `reference_only` 立即返回，否则再抽一次兼容 complexity。

上述编号保留为本模块的实现与审查索引。目前全部函数均已完成，测试中不存在
`@unittest.skip`、`skipTest` 或 `expectedFailure`。

## 代码逐段说明

`family_complexity.py` 中两个 order 常量提供稳定的 cumulative traversal 顺序。概率字典即使
数学上与顺序无关，带 seed 的抽样结果仍依赖候选遍历顺序，所以不能从 `frozenset` 构造抽样顺序。

`FAMILY_COMPLEXITY_COMPATIBILITY` 用 `MappingProxyType` 包装，value 使用 tuple。这样调用者
不能在运行时改变冻结矩阵，planner 也不需要通过“抽到非法 pair 后重试”来实现兼容性。

所有理论概率函数都接收 config 并返回新字典，不读写 RNG。只有
`sample_family_complexity_plan` 和 `_weighted_choice` 消耗调用方传入的 RNG 状态。

随机数消耗合同固定为：hard-bearing family 每个 plan 两次 draw；`reference_only` 每个 plan
一次 draw。函数内部不能创建 `Random(seed)`，否则连续调用会反复从同一状态开始；也不能调用
模块级 `random`，否则结果依赖隐藏全局状态。

## 当前边界

fixture 和 config 都是 offline synthetic identity，只供合同与自动测试。B 完成后应整理
review bundle 返回理论分支。本工作块不允许开始 C～G 或 production dataset generation。
