# E2A. Domain-Conditioned Structural Support Contract v0.1 实现报告

## 1. 模块目标

E2A 在冻结的 domain-independent D4/D5 structural model 之上增加一个确定性 support 查询层：

```text
FamilyComplexityPlan
+ validated D5A policy
+ SemanticSamplerConfigSpec
+ actual DomainRules
+ actual ExecutableTagSubset
+ ReferenceTitlePoolSpec
        ↓
domain-bindable signatures
+ domain-bindable mechanics patterns
```

本阶段没有 RNG，不抽样，不绑定具体值，也不改变 D5A/D5B prior。

实现文件：

- `src/anime_pref/sampling/domain_conditioned_support.py`
- `tests/test_domain_conditioned_support.py`

## 2. Public API

### `bindable_mechanics_candidates()`

```python
bindable_mechanics_candidates(
    family_complexity_plan,
    structural_signature,
    sampler_config,
    rules,
    subset,
    reference_title_pool,
) -> tuple[StructuralPatternPlan, ...]
```

其数学含义为：

```text
M_bind(F,C,S,D)
= {m in M_D5(F,C,S) | E1_bindable(m,D)}
```

调用流程：

```text
validate actual config/rules/subset binding
→ validate reference-title resource
→ D5B mechanics_candidates(F,C,S)
→ 按原顺序逐项调用 E1 validator
→ 保留 E1 PASS 的 patterns
→ 返回 immutable tuple
```

结果严格保持 D5B canonical mechanics order。

### `bindable_structural_signatures()`

```python
bindable_structural_signatures(
    policy,
    sampler_config,
    family_complexity_plan,
    rules,
    subset,
    reference_title_pool,
) -> tuple[StructuralSignature, ...]
```

调用流程：

```text
validate D5A policy binding
→ validate actual config/rules/subset binding
→ validate reference-title resource
→ signature_probabilities(policy,F,C)
→ 按 D5A enabled canonical order 遍历 signatures
→ 对每个 signature 查询 bindable mechanics
→ mechanics support 非空才保留 signature
→ 返回 immutable tuple
```

`signature_probabilities()` 在此只提供 explicit enabled support 和 canonical order。E2A 不读取其 probability values，不做 renormalization。

## 3. 内部函数

### `_validate_domain_resources()`

集中验证：

```text
sampler config ↔ DomainRules ↔ ExecutableTagSubset
reference-title pool contract
```

这样错误的 rules hash、subset identity 或 title resource 会直接抛出错误，不会被误解释成 zero-capacity support。

### `_filter_bindable_mechanics_candidates()`

内部过滤器首先取得 D5B canonical candidate tuple，然后对每个 candidate 调用冻结的 E1：

```python
validate_structural_pattern_bindability(...)
```

- `ValueError` 表示该 valid D5B pattern 在当前 domain 下没有 concrete assignment，因此不进入 support。
- 其他异常类型会继续向上传播，避免吞掉 programmer/invariant errors。

E2A 没有复制 genre、numeric、group expansion、tag reservation 或 reference capacity 规则。

## 4. 完整参数示例：Synthetic HAREM capacity gap

输入 context：

```python
family_plan = FamilyComplexityPlan(
    semantic_family="normalization",
    complexity_bucket="5_plus",
)

selected_signature = StructuralSignature(
    atom_kinds=(
        "genre_set",
        "tag_set",
        "tag_group_none",
    ),
)
```

D5A policy 启用了这个 signature，D5B 也能产生合法的 abstract mechanics candidates。因此它在 domain-independent structural model 中有效。

调用：

```python
mechanics = bindable_mechanics_candidates(
    family_plan,
    selected_signature,
    sampler_config,
    rules,
    executable_subset,
    reference_title_pool,
)
```

当前 synthetic domain 中：

```text
rules.tags
= {Female Harem, Male Harem, Mixed Gender Harem}

HAREM expansion
= {Female Harem, Male Harem, Mixed Gender Harem}
```

E1 对每个含 direct tag + HAREM group 的 mechanics candidate 计算：

```text
available_direct_tags
= rules.tags - HAREM expansion
= empty set
```

因此 E2A 输出：

```python
mechanics == ()
```

随后 signature 查询：

```python
signatures = bindable_structural_signatures(
    policy,
    sampler_config,
    family_plan,
    rules,
    executable_subset,
    reference_title_pool,
)
```

输出同样明确暴露 zero-capacity context：

```python
signatures == ()
```

没有 fallback、降低 complexity、启用 disabled signature 或 retry。

## 5. 激活 approved tag 后的对照流程

测试建立一个新的、重新计算 identity 的 rules contract：

```python
activated_rules.tags
= original_rules.tags | {"Ensemble Cast"}
```

`Ensemble Cast` 已存在于 approved subset，但只有显式加入 active rules 后才产生容量：

```text
available_direct_tags = {Ensemble Cast}
```

同样调用 `bindable_mechanics_candidates()` 后，结果包含两个 D5B mechanics：

```text
1. genre all_of/3
   + direct tag all_of/1
   + tag_group_none

2. genre all_of/3
   + direct tag none_of/1
   + tag_group_none
```

因此：

```python
len(mechanics) == 2
```

但 `bindable_structural_signatures()` 只返回一次 signature：

```python
(
    StructuralSignature(
        ("genre_set", "tag_set", "tag_group_none")
    ),
)
```

两个 mechanics candidates 不会使 signature 获得两倍权重。E2A 只表达 support membership。

## 6. D5A disabled signature 示例

在 `single_constraint / 1` 中，`status_any` 是 D4 mechanically eligible，并且当前 domain 可绑定；但 synthetic D5A policy 没有启用它。

因此：

```text
bindable_mechanics_candidates(... status_any ...) → nonempty
bindable_structural_signatures(policy, ...)       → 不包含 status_any
```

E2A 不会从全部 D4 signatures 扫描并重新启用它。

## 7. Reference pool 示例

对于空但 contract-valid 的 title pool：

```python
ReferenceTitlePoolSpec(
    pool_version="offline-empty-reference-titles-v0.1",
    titles=(),
)
```

结果：

```text
reference_only patterns       → filtered
reference_composition patterns → filtered
non-reference support          → unchanged
```

## 8. 顺序和确定性

- Mechanics tuple 按 D5B `mechanics_candidates()` 原顺序过滤。
- Signature tuple 按 D5A `signature_probabilities()` mapping insertion order 过滤。
- 相同 policy/config/domain/resources/context 得到相同 immutable tuples。
- 不按 capacity、candidate count 或 failure reason 排序。

## 9. 明确停止边界

E2A 未实现：

- domain-conditioned probability normalization；
- RNG 或 weighted choice；
- concrete values；
- group/format/status/reference selection；
- SemanticSpec 或 DatasetRecord；
- higher-level family fallback/resampling；
- catalog/API satisfiability；
- dataset generation。

