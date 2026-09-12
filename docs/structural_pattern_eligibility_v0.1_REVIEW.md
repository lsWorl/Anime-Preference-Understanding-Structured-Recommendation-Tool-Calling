# D4. Structural Pattern Eligibility Contract v0.1 Review Bundle

## 审查范围

本 bundle 仅覆盖：

```text
FamilyComplexityPlan
→ value-free structural eligibility
→ canonical StructuralPatternPlan candidate tuple
```

## 核心文件

- `src/anime_pref/schemas/structural_pattern.py`
- `src/anime_pref/sampling/structural_pattern.py`
- `src/anime_pref/sampling/config.py`
- `tests/test_structural_pattern.py`
- `docs/structural_pattern_eligibility_v0.1_IMPLEMENTATION.md`

## 合同落实情况

- `StructuralPatternPlan` 只保存 family、bucket、canonical atom tuple。
- 输入首先复用 B `validate_family_complexity_plan()`。
- 每个 atom 复用 D3 `validate_structural_atom()`。
- exact count 只复用 D3 `structural_constraint_count()`。
- exact 0～4 与 `5_plus >= 5` 分开匹配。
- `5_plus` 枚举空间包含 count 大于 5 的 pattern。
- 每种 direct/group/reference structural slot 最多一个。
- empty atom tuple 不属于任何当前 family。
- 六个 family-specific contracts 和 priority 已实现。
- canonical order 覆盖 kind、set payload 与 numeric payload。
- validator 拒绝 noncanonical 输入，不静默 repair。
- enumerator deterministic、去重、zero capacity 返回 `()`。
- 没有 RNG、weights、random choice 或 pattern probability。
- 没有调用 D1/D2 value sampler。
- 没有 domain/group identity binding、SemanticSpec 或后续 E～G。

## 候选空间摘要

- `reference_only/0`：1 个。
- `single_constraint/1`：14 个。
- `same_field_logic/1,2,3`：8、4、2 个。
- `cross_field_composition/2,3,4,5_plus`：77、276、595、3125 个。
- `normalization/1,2,3,4,5_plus`：8、98、520、1610、22340 个。
- `reference_composition/1,2,3,4,5_plus`：14、83、278、595、3125 个。

详细 exact-count 范围及参数调用过程见 implementation report。

## 测试覆盖

- 每个冻结 family/complexity pair；
- bucket 0/1/2/3/4 exact matching；
- `5_plus >=5` 且包含 count >5；
- direct/group slot multiplicity；
- empty atoms；
- family-specific requirements；
- family priority；
- TAG ANY aggregate semantics；
- canonical/noncanonical patterns；
- deterministic enumeration；
- candidate 去重与逐项 public validation；
- no RNG/value sampler/downstream imports or output fields。

实际测试结果：

```text
D4 专项测试：Ran 24 tests in 6.224s — OK
完整工程测试：Ran 205 tests in 6.248s — OK
compileall：PASS
git diff --check：PASS（仅有已有工作区文件的 LF/CRLF 提示）
skip / expectedFailure：0
```

## 请理论侧重点确认

1. 每个 D3 kind 在 D4 都采用单 structural slot，是否准确落实 direct uniqueness 与 group multiplicity。
2. D4 枚举完整 mechanics Cartesian space 后统一调用 public validator 筛选，是否符合“eligibility query”语义。
3. 当前所有冻结 B pair 都有非空 candidate space，是否可据此冻结 D4 capacity contract。
4. 候选数量绝不解释为概率，pattern selection/weighting 继续等待下一次理论冻结，边界是否正确。
5. `structurally eligible ≠ domain-bindable ≠ catalog-plausible` 的延期边界是否正确。

## 未实现

- pattern sampling/weights；
- group identity/domain binding；
- categorical/numeric/reference values；
- combination plausibility；
- SemanticSpec assembly；
- distribution audit；
- production dataset generation。
