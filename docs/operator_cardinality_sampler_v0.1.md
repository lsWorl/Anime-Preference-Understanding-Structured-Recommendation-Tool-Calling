# C. Direct Set-Logic Operator + Cardinality Sampler v0.1

## 实现范围

本模块只处理 `same_field_logic` family 的 direct genre/tag set-logic mechanics：

```text
FamilyComplexityPlan
→ 验证 family/complexity
→ 推导 eligible operator/cardinality pairs
→ 分层采样 operator 与 cardinality
→ OperatorCardinalityPlan
```

它不选择 genre/tag field，不选择具体 value，不处理 HAREM/tag group，不创建
`SemanticSpec`、DatasetRecord 或自然语言，也不实现 D～G。

## 数据对象

### `FamilyComplexityPlan`

B 阶段输出对象保持两个字段：`semantic_family` 和 `complexity_bucket`。本阶段新增
`validate_family_complexity_plan()`，因为 dataclass 类型标注不会在运行时阻止外部构造非法值。
validator 检查对象类型、family、bucket 类型及冻结 compatibility pair，并显式拒绝 bool 被当成
整数 `0`。

### `OperatorCardinalityPlan`

新对象只包含：

```text
operator
cardinality
```

cardinality 是 normalization expansion 之前的 semantic item 数量。对象没有 field 或 values。

## 主要函数

### `validate_operator_cardinality_plan(plan)`

验证任意直接构造的 C 输出对象。它允许的 generic contract 是：

```text
all_of  -> 1 / 2 / 3
any_of  -> 2 / 3
none_of -> 1 / 2
```

函数拒绝未知 operator、bool、非整数及 operator 不允许的 cardinality。

### `constraint_contribution(operator, cardinality)`

先复用 public validator 验证 pair，再计算 direct hard semantic clause contribution：

```text
all_of(k)  -> k
any_of(k)  -> 1
none_of(k) -> k
```

因此 any-of 的两个或三个 item 都属于同一个 OR clause。

### `eligible_operator_cardinality_pairs(family_plan)`

先验证 B plan，并明确要求 family 为 `same_field_logic`。函数按 canonical operator/cardinality
顺序枚举 generic pairs，保留 contribution 等于 B complexity 的 pair。由此得到：

```text
complexity 1 -> all_of/1, any_of/2, any_of/3, none_of/1
complexity 2 -> all_of/2, none_of/2
complexity 3 -> all_of/3
```

不存在抽到非法 pair 后重试的流程。其他 family 直接失败，因为它们需要尚未冻结的 structural
pattern contract。

### `operator_probabilities(config, family_plan)`

从 eligible pairs 提取至少拥有一个合法 cardinality 的 operator，按 canonical order 读取 Phase A
relative weights，并只在这些 operator 内归一化，得到 `P(O|context)`。

### `conditional_cardinality_probabilities(config, family_plan, operator)`

选择 operator 后，只读取该 operator 在当前 context 下的 eligible cardinalities，并在其 Phase A
cardinality relative weights内重新归一化，得到 `P(K|O,context)`。没有合法 cardinality 的
operator 不进入候选空间。

### `joint_operator_cardinality_probabilities(config, family_plan)`

按冻结公式计算理论 joint distribution：

```text
P(O,K|context) = P(O|context) × P(K|O,context)
```

该函数供自动测试和未来 G 使用；它不实现 sampled-distribution audit。代码没有使用旧的 raw
operator/cardinality product 全局归一化。

### `sample_operator_cardinality_plan(config, family_plan, rng)`

调用流程如下：

1. 验证 sampler config、B plan 和显式 RNG 接口。
2. 推导完整 eligible pair space。
3. 计算 operator distribution；只有一个 operator 时直接选择，否则消费一次 RNG draw。
4. 计算选中 operator 的 conditional cardinality distribution；只有一个 cardinality 时直接选择，
   否则消费一次 RNG draw。
5. 构造并验证 `OperatorCardinalityPlan`，再次确认输出 pair 属于当前 context。

## RNG 消费

```text
complexity=3:
  all_of/3 唯一确定，不消费 draw

complexity=2:
  all_of/2 或 none_of/2，operator 消费一次 draw，cardinality 不消费

complexity=1:
  operator 消费一次 draw
  选中 all_of/none_of：cardinality 唯一，不再消费
  选中 any_of：2/3 需要第二次 conditional draw
```

所有随机数来自调用方传入的 RNG。模块不创建内部 seed，也不读取全局 random state。

## Canonical mechanics

`SET_OPERATOR_ORDER` 和 `OPERATOR_CARDINALITY_ORDER` 固定 cumulative sampling 的候选遍历顺序。
顺序没有语义优先级，但修改顺序会改变相同 seed 的序列，因此未来调整必须 bump
`sampler_version`。

## 文件职责

- `src/anime_pref/schemas/operator_cardinality.py`：C 输出数据结构。
- `src/anime_pref/sampling/operator_cardinality.py`：validation、eligibility、概率与采样实现。
- `src/anime_pref/sampling/family_complexity.py`：新增 B plan public validator。
- `src/anime_pref/sampling/config.py`：新增 operator/cardinality canonical order。
- `tests/test_operator_cardinality_sampler.py`：C 合同和阶段边界回归测试。

当前配置和输出仍是 offline synthetic mechanics，不能解释为 production 数据分布。
