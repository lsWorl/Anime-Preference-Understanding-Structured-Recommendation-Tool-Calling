# D5C2. Mechanics Pattern RNG Sampler v0.1 实现报告

## 1. 模块目标

本模块实现冻结后的条件抽样：

```text
SemanticSamplerConfigSpec
+ FamilyComplexityPlan
+ 已选择的 StructuralSignature
+ 调用方持有的 RNG
        ↓
StructuralPatternPlan
```

概率含义是：

```text
M ~ P(M | F,C,S)
```

其中 `F` 是 semantic family，`C` 是 complexity bucket，`S` 是 D5C1 已经选择的 structural signature，`M` 是本模块选择的 value-free mechanics pattern。

实现文件：

- `src/anime_pref/sampling/mechanics_sampler.py`
- `tests/test_mechanics_sampler.py`

本模块不读取 D5A policy，不重新选择 signature，也不生成 genre、tag、year 等具体值。

## 2. Public API

```python
sample_mechanics_pattern(
    sampler_config,
    family_complexity_plan,
    structural_signature,
    rng,
) -> StructuralPatternPlan
```

### 参数职责

- `sampler_config`：提供 Phase A 冻结的 operator、cardinality 和 numeric-pattern relative weights。
- `family_complexity_plan`：提供已经选择的 family 和 complexity bucket。
- `structural_signature`：提供已经选择且按 D3 canonical order 排列的 atom kinds。
- `rng`：调用方持有的、具有可调用 `random()` 方法的随机数源。

### 返回值

直接返回一个 `StructuralPatternPlan`。它只包含：

```text
semantic_family
complexity_bucket
value-free structural atoms and mechanics payloads
```

## 3. 主要函数

### `sample_mechanics_pattern()`

Public entrypoint，调用流程为：

```text
validate_sampler_config
→ validate_family_complexity_plan
→ validate_structural_signature
→ validate RNG interface
→ mechanics_candidates
→ 按 signature canonical atom order 遍历
→ 每个有 payload 的 stage 计算 D5B conditional probabilities
→ singleton 直接选；multi-candidate 用一次 _weighted_choice
→ 过滤 survivors
→ 要求唯一 survivor
→ validate_structural_pattern_plan
→ 返回结果
```

调用方输入导致的错误全部在第一次可能的 RNG draw 前被拒绝。

### `_choose_probability_candidate()`

统一执行 conditional mapping 的选择规则：

```text
0 candidates → ValueError
1 candidate  → 直接返回，0 draw
2+ candidates → 调用已有 _weighted_choice，1 draw
```

函数直接使用 mapping insertion order，不重新排序，也没有第二套累计概率实现。

### `_filter_operator_survivors()`

在 set atom 的 operator stage 后，只保留携带所选 operator 的 D4 completions。随后 cardinality helper 只会在这个缩小后的 survivor state 上计算条件概率。

Cardinality 和 numeric-pattern 过滤直接复用 D5B 的 survivor helpers，避免建立另一套 completion 语义。

## 4. 为什么是 sequential survivor process

D5B 定义的不是“对最终 D4 patterns 做一次均匀或全局加权抽样”，而是以下层级过程：

```text
set atom:     operator → cardinality
numeric atom: numeric range pattern
```

每个阶段只在仍然存在合法 D4 completion 的选项中归一化。选中一个选项后，survivors 只会缩小，不会重新枚举或 retry。

这种实现保证：

- 每次选择都有至少一个合法 completion；
- exact complexity 在整个路径中保持成立；
- RNG consumption 与实际 conditional stages 对齐；
- 同一输入和 RNG state 可复现相同结果与相同 state advancement。

## 5. 完整参数示例：三次 draw 路径

输入：

```python
family_plan = FamilyComplexityPlan(
    semantic_family="cross_field_composition",
    complexity_bucket="4",
)
selected_signature = StructuralSignature(
    atom_kinds=("genre_set", "year_range"),
)
rng = CountingRandom([0.10, 0.90, 0.90])

result = sample_mechanics_pattern(
    sampler_config=config,
    family_complexity_plan=family_plan,
    structural_signature=selected_signature,
    rng=rng,
)
```

初始 D5B survivors 是：

```text
1. genre all_of/2  + year bounded_range
2. genre all_of/3  + year min_only
3. genre all_of/3  + year max_only
4. genre none_of/2 + year bounded_range
```

### 第一步：`genre_set.operator`

D5B 根据有 completion 的 operator 和 Phase A weights 返回：

```python
{
    "all_of": 45 / 70,
    "none_of": 25 / 70,
}
```

第一个 draw 是 `0.10`，落入 `all_of` 区间。Survivors 缩小为前三项。

### 第二步：`genre_set.cardinality`

在 `all_of` survivors 上，cardinality 2 和 3 都有 completion。相对权重为 `30:5`：

```python
{
    2: 30 / 35,
    3: 5 / 35,
}
```

第二个 draw 是 `0.90`，选择 cardinality `3`。Survivors 变成：

```text
genre all_of/3 + year min_only
genre all_of/3 + year max_only
```

### 第三步：`year_range.pattern`

D5B 在剩余 completions 上返回 year pattern 权重 `4:3`：

```python
{
    "min_only": 4 / 7,
    "max_only": 3 / 7,
}
```

第三个 draw 是 `0.90`，选择 `max_only`。Survivors 只剩一个最终 pattern：

```python
StructuralPatternPlan(
    semantic_family="cross_field_composition",
    complexity_bucket="4",
    atoms=(
        StructuralAtom(
            kind="genre_set",
            operator_plan=OperatorCardinalityPlan(
                operator="all_of",
                cardinality=3,
            ),
        ),
        StructuralAtom(
            kind="year_range",
            range_pattern="max_only",
        ),
    ),
)
```

该结果的 hard clause count 是：

```text
genre all_of/3 → 3
year max_only  → 1
total          → 4
```

总 RNG consumption 为 3 draws。

## 6. 一次 draw 路径

相同 context 下，若第一个 draw 选择 `none_of`：

```python
rng = CountingRandom([0.90])
```

则：

```text
operator: none_of        → 1 draw
cardinality: only 2      → 0 draw
year pattern: bounded    → 0 draw
total                    → 1 draw
```

最终结果是：

```text
genre none_of/2 + year bounded_range
```

## 7. 零 draw 路径

`reference_only / 0`：

```python
sample_mechanics_pattern(
    config,
    FamilyComplexityPlan("reference_only", 0),
    StructuralSignature(("reference",)),
    CountingRandom([]),
)
```

`reference` 没有 mechanics payload，且整个 candidate space 是 singleton，因此直接返回并消耗 0 draws。

`cross_field_composition / 5_plus` 配合签名 `("genre_set", "year_range")` 也只有一个 completion：

```text
genre all_of/3 + year bounded_range
```

每个 conditional stage 都是 singleton，总计同样为 0 draws。

## 8. 与 Phase C 的一致性

对 `same_field_logic` 的单 set signature，D5C2 使用相同的：

- canonical operator order；
- hierarchical operator → cardinality 顺序；
- Phase A weight tables；
- singleton-zero-draw 规则；
- `_weighted_choice()`。

自动测试使用相同 config、family plan、seed 和初始 RNG state 同时调用 Phase C 与 D5C2，并验证：

```text
OperatorCardinalityPlan 相同
最终 RNG state 相同
```

## 9. 明确边界

本模块未实现：

- D5A policy 或 signature 抽样；
- 对最终 pattern 的额外一次抽样；
- rejection/retry；
- categorical/numeric concrete values；
- DomainRules、subset 或 catalog 绑定；
- tag-group identity 或 reference-title binding；
- SemanticSpec、DatasetRecord 或 user text；
- E～G 以及 production generation。

