# E1. Structural Pattern Domain Bindability Preflight v0.1 Review Bundle

## 审查范围

```text
StructuralPatternPlan
+ SemanticSamplerConfigSpec
+ actual DomainRules
+ actual ExecutableTagSubset
+ reference-title pool
        ↓
deterministic bindability decision
```

无 RNG，不生成 concrete values，不检查 catalog results。

## 核心文件

- `src/anime_pref/schemas/domain_bindability.py`
- `src/anime_pref/data/reference_title_pool.py`
- `src/anime_pref/sampling/domain_bindability.py`
- `tests/fixtures/reference_titles.synthetic.v0.1.json`
- `tests/test_domain_bindability.py`
- `docs/domain_bindability_v0.1_IMPLEMENTATION.md`

## 合同落实

- Public validation 先验证 D4 pattern，再执行 config/rules/subset full binding。
- Reference pool 有最小 versioned immutable contract。
- 空 title pool 对 non-reference pattern 合法，reference pattern 要求至少一个 title。
- Genre capacity 使用 active `rules.genres` 与 direct cardinality。
- Year/episodes 复用 D2 `validate_numeric_sampling_binding()`。
- Format/status atom 要求对应 active vocabulary 非空。
- Group candidates 完全来自 actual `rules.tag_groups`，无 HAREM 硬编码。
- Group identity 按 canonical group-name order 枚举。
- Group any/none 分别要求对应 operator support。
- Opposing group slots 要求不同 identity 且 expansion 不相交。
- 所有 selected group expansions 的 union 从 direct tag universe 中保留。
- Direct tag capacity 只使用 `rules.tags - reserved_tags`。
- Approved 但 inactive subset tag 不增加容量。
- 至少一个可行 assignment 即通过；空 support 则失败。
- 不 retry，不改变 D5 distribution。

## Synthetic capacity finding

当前 synthetic active tags 正好等于 HAREM expansion：

```text
Female Harem
Male Harem
Mixed Gender Harem
```

因此包含 direct `tag_set` 和 HAREM group 的 pattern 在当前 rules 下没有 direct-tag capacity，E1 正确判定为不可绑定。

将 subset 中已批准的 `Ensemble Cast` 显式激活进新的 rules identity 后，cardinality-1 direct tag + HAREM group 才变为可绑定。

## 自动测试覆盖

- valid StructuralPatternPlan；
- config/rules/subset full binding 与 identity mismatch；
- genre cardinality capacity；
- year/episodes D2 binding；
- format/status nonempty capacity；
- reference/non-reference title requirements；
- title resource canonical validation/loading；
- group any/none operator support；
- opposing groups distinct identity 与 disjoint expansions；
- at least one feasible group assignment；
- deterministic group support order；
- direct tag capacity without groups；
- same-operator duplicate prevention；
- cross-operator overlap prevention；
- active rules 与 approved-but-inactive subset 边界；
- no RNG/value sampling/SemanticSpec/catalog/downstream dependencies。

## 验收结果

```text
E1 专项测试
Ran 24 tests in 0.010s
OK

完整工程测试
Ran 317 tests in 17.319s
OK

compileall: PASS
git diff --check: PASS
skip / expectedFailure 搜索结果: 0
```

`git diff --check` 仅显示两个既有文件的 LF/CRLF 转换提示，退出码为 0，未发现 whitespace error：

- `src/anime_pref/sampling/config.py`
- `tests/test_categorical_value_sampler.py`

## 请理论侧确认

1. Reference pool 的 canonical deterministic tuple order 使用字符串升序并拒绝静默排序，是否冻结。
2. `feasible_tag_group_bindings()` 是否完整表达 group operator、identity、expansion 与 direct-tag joint capacity。
3. 当前 synthetic HAREM capacity gap 是否应保留为显式 unbindable finding。
4. E1 是否可以判定 PASS，并决定下一阶段如何处理 unbindable structural support。

## 未实现

- concrete value/group/reference sampling；
- retry 或 structural resampling；
- catalog satisfiability；
- SemanticSpec assembly；
- dataset generation。
