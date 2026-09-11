# Semantic Sampler Config / Contract v0.1

> 状态核对（2026-09-12）：A 阶段已经实现，6 项 sampler-config 测试全部启用并通过；
> 完整离线测试为 54 项，全部通过且无跳过。

本阶段只定义离线 sampler 配置，不生成 `SemanticSpec`、DatasetRecord 或自然语言文本。

## 文件职责

- `src/anime_pref/schemas/sampler_config.py`：不可变 sampler config 数据结构。
- `src/anime_pref/sampling/config.py`：严格 JSON loader、独立 contract validation，以及与实际 rules/subset 的绑定验证。
- `tests/fixtures/semantic_sampler.synthetic.v0.1.json`：仅用于离线测试的完整配置。family/cardinality/value/numeric/tolerance 中尚未被理论冻结的具体数字都是 synthetic mechanics fixtures，不是 production prior。
- `tests/test_sampler_config.py`：配置完整性、不可变性、严格失败行为和 domain binding 的待启用测试。

## 配置结构

```text
sampler_version
seed
family_weights
constraint_count_weights
operator_weights
operator_cardinality
genre_sampling
tag_sampling
numeric_sampling.year / episodes
combination_policy_version
audit_tolerances
```

权重统一解释为正的相对权重，使用者在采样时归一化，因此不要求浮点和恰好为 1。冻结的 complexity/operator 百分比可以直接写作 `35/30/...` 与 `45/30/25`，避免浮点求和误差。

`operator_cardinality` 描述的是 pre-expansion semantic item 数量。HAREM 展开后的三个 leaf tags 不参与这里的 cardinality。

`numeric_sampling` 分开记录 range pattern 与 value pool：

```text
pattern: min_only / max_only / bounded_range
pool: common / catalog_region / long_tail
```

fixture 中的 numeric values 只验证 configurable policy 和 validity binding。它们不是 catalog-informed production cutoffs。

`combination_policy_version` 当前只预留对后续静态 plausibility contract 的版本引用。具体组合规则将在阶段 E 冻结和实现，A 阶段不提前发明规则。

## Production boundary

当前 fixture 的文件名、`sampler_version`、rules/subset identity 都明确包含 `synthetic`。它只用于离线测试，不能生成或发布 production dataset。

真正的 production sampler config 必须等待：

```text
real AniList taxonomy
→ human reviewed subset
→ production DomainRules
→ catalog statistics / title pool
→ production sampling values and weights
```

## 已完成的实现

1. 精确 JSON shape loader，将嵌套 mapping 转成只读结构且不静默排序 numeric pools。
2. Standalone config invariants：版本、seed、weight、cardinality、coverage、tier、numeric pool 和 audit tolerance。
3. Rules/subset domain binding：active value、numeric validity 与 normalization availability。
4. 全部回归测试和 A 阶段 review bundle。

本阶段不验证 family/count compatibility，也不选择 operator、value 或 numeric range。那些职责分别属于后续 B、C、D 阶段。
