# E1. Structural Pattern Domain Bindability Preflight v0.1 实现报告

## 1. 本阶段解决的问题

D4/D5 已经能产生合法的 value-free `StructuralPatternPlan`，但结构合法不保证当前 active domain vocabulary 能填入具体值。E1 在任何 value sampling 之前执行确定性预检：

```text
StructuralPatternPlan
+ SemanticSamplerConfigSpec
+ DomainRules
+ ExecutableTagSubset
+ ReferenceTitlePoolSpec
        ↓
至少存在一个合法 concrete assignment：PASS
不存在合法 assignment：ValueError
```

E1 只证明存在性：

```text
∃ concrete SemanticSpec assignment
```

它不生成这个 assignment，不消费 RNG，也不检查 AniList catalog 是否真的有匹配作品。

## 2. 新增文件

- `src/anime_pref/schemas/domain_bindability.py`
- `src/anime_pref/data/reference_title_pool.py`
- `src/anime_pref/sampling/domain_bindability.py`
- `tests/fixtures/reference_titles.synthetic.v0.1.json`
- `tests/test_domain_bindability.py`

## 3. 数据结构

### `ReferenceTitlePoolSpec`

```python
ReferenceTitlePoolSpec(
    pool_version: str,
    titles: tuple[str, ...],
)
```

这是 reference slot 的最小 offline resource contract。`pool_version` 必须是无首尾空白的非空字符串；title 必须是 canonical nonempty string、唯一并按字符串 canonical order 排列。空 titles tuple 本身合法，因为不含 reference atom 的 pattern 不需要 title。

Synthetic fixture 中的少量真实标题只用于离线 mechanics 测试，不代表 production title universe。

### `TagGroupBindingPlan`

```python
TagGroupBindingPlan(
    any_of_group: str | None,
    none_of_group: str | None,
)
```

该对象只描述 group identity 对 structural slots 的一种可行赋值，不带概率，也不展开成最终 Gold JSON。

## 4. 主要函数

### `validate_reference_title_pool()`

验证：

- dataclass 类型；
- canonical pool version；
- titles 必须是 tuple；
- title 是 canonical nonempty string；
- 无重复；
- tuple 使用稳定的 canonical sorted order。

函数拒绝错误输入，不静默 strip、排序或去重。

### `load_reference_title_pool()`

读取仅包含 `pool_version` 和 `titles` 的 JSON resource，构造不可变 contract 并调用统一 validator。

### `feasible_tag_group_bindings()`

纯 support enumeration helper。执行过程：

```text
validate structural pattern
→ validate standalone rules identity
→ 找出 any/none group slots
→ 按 canonical group-name order 找 operator-compatible groups
→ 枚举 group identity assignment
→ 拒绝 opposing slots 使用相同 group
→ 拒绝 opposing group expansions overlap
→ union 所有 group expansions 为 reserved_tags
→ 检查 rules.tags - reserved_tags 是否容纳 direct cardinality
→ 返回全部可行 TagGroupBindingPlan
```

它不使用 HAREM 名称特例。HAREM 只是当前 actual `rules.tag_groups` 中的一项。

### `validate_structural_pattern_bindability()`

Public preflight，固定调用顺序：

```text
validate_structural_pattern_plan
→ validate_sampler_config_against_domain(config, rules, subset)
→ validate_reference_title_pool
→ genre capacity
→ D2 numeric binding for present numeric fields
→ format/status nonempty capacity
→ reference-title capacity
→ joint tag/group feasible support
```

所有检查通过返回 `None`；任一资源或容量不存在则抛出 `ValueError`。

## 5. 完整例子：当前 synthetic rules 的真实容量缺口

输入 pattern：

```python
structural_pattern = StructuralPatternPlan(
    semantic_family="normalization",
    complexity_bucket="2",
    atoms=(
        StructuralAtom(
            kind="tag_set",
            operator_plan=OperatorCardinalityPlan(
                operator="all_of",
                cardinality=1,
            ),
        ),
        StructuralAtom(kind="tag_group_any"),
    ),
)
```

当前 synthetic active domain：

```python
rules.tags = {
    "Female Harem",
    "Male Harem",
    "Mixed Gender Harem",
}

rules.tag_groups["HAREM"].tags = (
    "Female Harem",
    "Male Harem",
    "Mixed Gender Harem",
)
```

调用：

```python
validate_structural_pattern_bindability(
    structural_pattern,
    sampler_config,
    rules,
    executable_subset,
    reference_title_pool,
)
```

内部 group assignment 是：

```python
TagGroupBindingPlan(
    any_of_group="HAREM",
    none_of_group=None,
)
```

Capacity 计算：

```text
reserved_tags
= HAREM expansion
= {Female Harem, Male Harem, Mixed Gender Harem}

available_direct_tags
= rules.tags - reserved_tags
= empty set

required direct cardinality = 1
actual available capacity   = 0
```

因此：

```python
feasible_tag_group_bindings(structural_pattern, rules) == ()
```

Public preflight 抛出 `ValueError`。它不会使用 subset 中已批准但 inactive 的 `Ensemble Cast`。

## 6. 显式激活 approved tag 后的对照

如果建立一个新的、正确重新 hash 的 rules identity，并显式激活：

```python
rules.tags += {"Ensemble Cast"}
```

则：

```text
available_direct_tags = {Ensemble Cast}
required cardinality  = 1
```

Support 变为：

```python
(
    TagGroupBindingPlan("HAREM", None),
)
```

同一个 structural pattern 通过 bindability preflight。这说明容量只来自当前 `DomainRules.tags`，approved subset 本身不会自动扩大 active vocabulary。

## 7. Opposing group 示例

对于同时含：

```text
tag_group_any
tag_group_none
```

候选 assignment 必须满足：

```text
any group identity != none group identity
expanded(any) ∩ expanded(none) = empty set
```

例如：

```text
A_ANY  → {Female Harem}
B_NONE → {Male Harem}
```

可行；而两个不同名称都展开到 `{Female Harem}` 时仍然不可行。

## 8. 其他字段容量

- `genre_set`：`len(rules.genres) >= cardinality`。
- `year_range`：复用 `validate_numeric_sampling_binding("year", ...)`。
- `episodes_range`：复用 `validate_numeric_sampling_binding("episodes", ...)`。
- `format_any`：active formats 非空。
- `status_any`：active statuses 非空。
- `reference`：title pool 至少含一个 title。

E1 不冻结 format/status cardinality 或概率。

## 9. 阶段边界

本模块没有：

- RNG 或抽样；
- concrete genre/tag/numeric/format/status values；
- group RNG selection；
- reference-title selection；
- SemanticSpec 或 DatasetRecord assembly；
- retry/resampling；
- catalog/API 查询；
- dataset generation。

