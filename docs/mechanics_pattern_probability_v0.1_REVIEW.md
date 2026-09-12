# D5B. Mechanics Pattern Conditional Probability Contract v0.1 Review Bundle

## 审查范围

本阶段只实现：

```text
P(StructuralPatternPlan | family, complexity, selected signature)
```

## 核心文件

- `src/anime_pref/sampling/mechanics_probability.py`
- `tests/test_mechanics_probability.py`
- `docs/mechanics_pattern_probability_v0.1_IMPLEMENTATION.md`

## 合同落实情况

- Candidate set 严格等于对应 D4 patterns 按 selected signature 过滤。
- 输入验证 B plan、D5A signature、Phase A config 和 D4 membership。
- 按 D3 canonical atom order 顺序处理 mechanics。
- 每一步只保留具有至少一个 completion 的 option。
- Completion count 不进入 option probability。
- Set mechanics 使用 operator → per-operator cardinality hierarchical normalization。
- Numeric mechanics只使用对应 field 的 pattern weights。
- Payload-free atom local factor 为 1。
- 输出保持 D4 canonical pattern order。
- 每个 probability finite positive，总和为 1。
- Phase C same-field distribution equivalence 已验证。
- TAG ANY aggregate complexity coupling 已验证。
- `5_plus` 使用 D4 actual completions，不强制 exact 5。
- Operator、各 operator cardinality、year/episode pattern scale invariance 已验证。
- 不使用 numeric pools、D1 categorical weights 或 D5A signature weights。
- 无 RNG、selection、rejection loop、domain binding 或 downstream assembly。

## 代表性结果

```text
context: cross_field_composition / 4
signature: (genre_set, year_range)

all_of/2 + bounded_range: 0.5510204082
all_of/3 + min_only:      0.0524781341
all_of/3 + max_only:      0.0393586006
none_of/2 + bounded_range:0.3571428571
sum:                      1.0
```

Operator support 中 all_of 有三个 completions、none_of 有一个，但 operator probability 仍按 Phase A 的 `45:25`，没有乘 completion count。

## 自动测试覆盖

- D4 candidate restriction；
- invalid/noneligible signature；
- operator/cardinality/numeric feasible support；
- completion-count independence；
- exact complexity coupling；
- TAG ANY aggregation；
- normalized positive distributions；
- payload-free/reference-only singleton；
- Phase C equivalence；
- `5_plus`；
- D4 output order和 determinism；
- operator/cardinality/year/episode scale invariance；
- numeric pool、categorical weight isolation；
- no RNG/rejection/D5A weight/domain/downstream dependency。

实际测试结果：

```text
D5B 专项测试：Ran 19 tests in 8.202s — OK
完整工程测试：Ran 251 tests in 16.965s — OK
compileall：PASS
git diff --check：PASS（仅有已有工作区文件的 LF/CRLF 提示）
skip / expectedFailure：0
```

## 请理论侧重点确认

1. Survivor-state 分支算法是否准确落实 sequential feasibility-conditioned mechanics。
2. Feasible support 只看 completion presence、不看 completion count，是否可以正式冻结。
3. Same-field complexity 1/2/3 与 Phase C joint distribution 等价证据是否充分。
4. D5B 对任何 D4-eligible signature 都有数学定义，同时不检查其 D5A enablement，分层是否正确。
5. Immutable memoized `mechanics_candidates()` 是否符合 pure deterministic query 边界。

## 未实现

- signature/pattern RNG sampling；
- combined sampler；
- concrete value/domain/group binding；
- SemanticSpec assembly；
- combination plausibility；
- distribution audit；
- production generation。
