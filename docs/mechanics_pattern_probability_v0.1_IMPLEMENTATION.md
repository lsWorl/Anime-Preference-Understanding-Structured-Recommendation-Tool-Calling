# D5B. Mechanics Pattern Conditional Probability Contract v0.1 实现报告

## 1. 本阶段目标

D5B 只计算：

```text
P(StructuralPatternPlan | family, complexity, selected signature)
```

输入 family/complexity 已由 B 确定，signature 已由 D5A 的逻辑层选定。D5B 不读取这些上游概率，也不执行 RNG。

## 2. 新增文件

- `src/anime_pref/sampling/mechanics_probability.py`
  - mechanics candidate restriction；
  - feasible support helpers；
  - operator/cardinality/numeric local conditional probabilities；
  - sequential survivor-state probability propagation。
- `tests/test_mechanics_probability.py`
  - D5B 合同测试。

## 3. Candidate space

### `mechanics_candidates(family_complexity_plan, signature)`

函数依次：

1. 验证 B `FamilyComplexityPlan`；
2. 验证 D5A `StructuralSignature`；
3. 确认 signature 属于该 context 的 D4 eligible signatures；
4. 从 D4 canonical patterns 中保留 signature 相等的项；
5. 保持 D4 顺序并返回 immutable tuple。

定义正好是：

```text
M(F,C,S) = {p ∈ D4(F,C) | structural_signature(p) == S}
```

Signature 不合法、context-ineligible 或没有 completion 时直接失败，不添加 fallback。

## 4. Feasible-support helpers

### `feasible_set_operators(survivors, atom_kind)`

按 Phase A `SET_OPERATOR_ORDER` 返回至少存在一个 survivor completion 的 operator。每个 operator 只出现一次；completion 数量不进入结果。

### `feasible_set_cardinalities(survivors, atom_kind, operator)`

固定 operator 后，按对应 `OPERATOR_CARDINALITY_ORDER` 返回有 completion 的 cardinalities。

### `feasible_numeric_patterns(survivors, atom_kind)`

对 year/episodes 按：

```text
min_only → max_only → bounded_range
```

返回有 completion 的 range patterns。

## 5. Local conditional probability helpers

### `conditional_operator_probabilities(...)`

只在当前 feasible operators 内归一化：

```text
P(O=o | state) = operator_weight[o] / Σ feasible operator weights
```

### `conditional_cardinality_probabilities(...)`

只在已选 operator 的 feasible cardinalities 内归一化：

```text
P(K=k | O=o,state)
= cardinality_weight[o][k] / Σ feasible cardinality weights for o
```

不同 operator 的 cardinality table 不跨 operator 归一化。

### `conditional_numeric_pattern_probabilities(...)`

- `year_range` 只读 `config.year_sampling.pattern_weights`；
- `episodes_range` 只读 `config.episode_sampling.pattern_weights`。

函数不读取 pool weights 或 numeric value pools。

## 6. Sequential survivor algorithm

### `mechanics_pattern_probabilities(config, family_plan, signature)`

初始状态：

```text
states = [(M(F,C,S), probability=1.0)]
```

函数按 signature 已有的 D3 canonical atom order 遍历：

- payload-free atom 直接跳过，local factor 为 1；
- set atom 先按 feasible operator 分支，再在每个 operator 分支按 feasible cardinality 分支；
- numeric atom 按 feasible range pattern 分支；
- 每次选择 mechanics 后过滤 survivors；
- path probability 乘以该步 local conditional probability。

所有 mechanics-bearing atoms 处理完后，每条 path 必须对应唯一 D4 pattern。结果再按原 D4 candidate order构造 mapping。

最终检查：

- 每个 probability finite 且大于 0；
- 总和在浮点 tolerance 内等于 1。

## 7. 完整复杂度耦合示例

输入：

```python
family_plan = FamilyComplexityPlan(
    "cross_field_composition",
    "4",
)
selected_signature = StructuralSignature(
    ("genre_set", "year_range")
)

probabilities = mechanics_pattern_probabilities(
    config,
    family_plan,
    selected_signature,
)
```

D4 restrictions 得到四个 mechanics completions：

```text
genre all_of/2 + year bounded_range
genre all_of/3 + year min_only
genre all_of/3 + year max_only
genre none_of/2 + year bounded_range
```

Phase A synthetic weights：

```text
operator: all_of=45, any_of=30, none_of=25
all_of cardinality: 1=65, 2=30, 3=5
none_of cardinality: 1=75, 2=25
year pattern: min_only=4, max_only=3, bounded_range=2
```

### 第一步：genre operator

当前 feasible operators 只有：

```text
all_of, none_of
```

虽然 all_of 后面有三个 completions，而 none_of 只有一个，概率仍是：

```text
P(all_of) = 45 / (45 + 25) = 9/14
P(none_of) = 25 / (45 + 25) = 5/14
```

`any_of` 没有满足 exact complexity 4 的 completion，所以不会先选中再 retry。

### 第二步：genre cardinality

在 all_of 分支：

```text
feasible cardinalities = 2, 3
P(2 | all_of) = 30 / (30 + 5) = 6/7
P(3 | all_of) = 5 / (30 + 5) = 1/7
```

在 none_of 分支只有 cardinality 2：

```text
P(2 | none_of) = 1
```

### 第三步：year range pattern

若已选 `all_of/2`，为了达到 exact count 4，year 只能 bounded：

```text
P(bounded | all_of/2) = 1
```

若已选 `all_of/3`，year 只能贡献 1：

```text
P(min | all_of/3) = 4/7
P(max | all_of/3) = 3/7
```

若已选 `none_of/2`，year 只能 bounded：

```text
P(bounded | none_of/2) = 1
```

### 最终 pattern probability

```text
all_of/2 + bounded
= 9/14 × 6/7 × 1
= 0.5510204082

all_of/3 + min
= 9/14 × 1/7 × 4/7
= 0.0524781341

all_of/3 + max
= 9/14 × 1/7 × 3/7
= 0.0393586006

none_of/2 + bounded
= 5/14 × 1 × 1
= 0.3571428571
```

总和为 1。这个结果不是所有 local raw weights 相乘后的 global normalization。

## 8. TAG ANY aggregate coupling

Context：

```text
normalization / 1
signature = (tag_set, tag_group_any)
```

D3 将 direct tag ANY 和 group ANY 合并为一个 hard clause。因此 D4 completion 中，direct tag set 只能是：

```text
any_of/2
any_of/3
```

Operator singleton：

```text
P(any_of) = 1
```

Cardinality 按 Phase A `80:20`：

```text
P(any_of/2) = 0.8
P(any_of/3) = 0.2
```

## 9. 与 Phase C 的一致性

对 `same_field_logic` 的单 `genre_set` 或 `tag_set` signature，测试把 D5B mapping 按 `(operator, cardinality)` 投影，并与 Phase C `joint_operator_cardinality_probabilities()` 比较。

Complexity 1、2、3 全部一致。尤其 complexity 3 只有：

```text
all_of/3 → probability 1
```

## 10. `5_plus` 与 singleton mechanics

对于：

```text
cross_field_composition / 5_plus
signature = (genre_set, year_range)
```

当前唯一 completion 是：

```text
genre all_of/3 + year bounded_range
```

其 probability 为 1。这里 `5_plus` 通过 D4 actual completion 处理，没有被提前改写成 exact 5。

Payload-free `format_any`、`tag_group_none`、`reference_only` 等 singleton mechanics 同样自然得到 1，没有 magic factor。

## 11. Scale invariance 与层隔离

测试分别确认：

- operator table 整体缩放不变；
- all_of/any_of/none_of 各自 cardinality table 独立缩放不变；
- year pattern table 整体缩放不变；
- episode pattern table 整体缩放不变；
- 改变 numeric pool weights 不影响 D5B；
- 改变 categorical value weights 不影响 D5B。

Operator、cardinality 和 numeric pattern 不进入同一个全局归一化分母。

## 12. 阶段边界

D5B mathematically defined 不等于 D5A sampling-enabled。Operational 调用链必须先完成 D5A policy binding 与 signature selection，之后才调用 D5B。

本模块没有：

- D5A signature weights；
- RNG、rejection loop 或 sampling API；
- completion-count multiplier；
- D1 categorical weights；
- D2 pool weights/value pools；
- group identity/HAREM、format/status/reference values；
- DomainRules/subset/catalog；
- SemanticSpec/DatasetRecord/user_text；
- E～G 或 production generation。

