# D5C2. Mechanics Pattern RNG Sampler v0.1 Review Bundle

## 审查范围

```text
SemanticSamplerConfigSpec
+ FamilyComplexityPlan
+ selected StructuralSignature
+ caller-owned RNG
        ↓
StructuralPatternPlan
```

实现 `M ~ P(M | F,C,S)`，不进入 concrete value binding 或 SemanticSpec assembly。

## 核心文件

- `src/anime_pref/sampling/mechanics_sampler.py`
- `tests/test_mechanics_sampler.py`
- `docs/mechanics_sampler_v0.1_IMPLEMENTATION.md`

## 合同落实

- Public validation 顺序为 config → family plan → signature → RNG interface → D5B candidates。
- 初始 survivors 完全来自 D5B `mechanics_candidates()`。
- 按 signature 内冻结的 D3 canonical atom-kind order 遍历。
- Set mechanics 顺序为 operator → cardinality。
- Numeric mechanics 使用 D5B conditional numeric-pattern helper。
- Conditional probability 唯一来源是 D5B 三个 frozen helpers。
- Payload-free atoms 跳过，survivors 不变且消耗 0 draws。
- Singleton stage 消耗 0 draws；multi-option stage 恰好消耗 1 draw。
- Multi-option selection 复用 `_weighted_choice()` 和 mapping insertion order。
- Survivors 只缩小，不重新枚举，不 retry。
- Traversal 结束必须得到唯一 survivor。
- 返回前执行 `validate_structural_pattern_plan()`。
- 直接返回 `StructuralPatternPlan`。
- D5C2 不读取 D5A policy/signature weights，不调用 D1/D2。

## 代表性路径

Context：

```text
cross_field_composition / 4
signature = (genre_set, year_range)
```

| 路径 | 选择结果 | Operator draws | Cardinality draws | Numeric draws | 总数 |
|---|---|---:|---:|---:|---:|
| A | none_of/2 + bounded | 1 | 0 | 0 | 1 |
| B | all_of/2 + bounded | 1 | 1 | 0 | 2 |
| C | all_of/3 + max | 1 | 1 | 1 | 3 |

详细的输入参数、conditional mappings、survivor state 和结果对象见实现报告。

## 自动测试覆盖

- candidate space 来自 D5B；
- conditional helpers 调用与 canonical traversal order；
- public validation order；
- invalid config/family/signature/context/RNG failure-before-draw；
- payload-free、operator/cardinality/numeric singleton zero draw；
- multi-option stage one draw；
- 代表性 1/2/3 draw paths；
- reference-only 与 singleton 5_plus zero draw；
- exact complexity；
- TAG ANY aggregation completion；
- same seed/state determinism 与 state advancement；
- Phase C exact result/state equivalence；
- operator 与 numeric table scale invariance；
- direct `StructuralPatternPlan` output；
- no D5A/value/domain/downstream dependencies。

## 验收结果

```text
D5C2 专项测试
Ran 23 tests in 6.862s
OK

完整工程测试
Ran 293 tests in 18.616s
OK

compileall: PASS
git diff --check: PASS
skip / expectedFailure 搜索结果: 0
```

`git diff --check` 仅显示两个既有工作区文件的 LF/CRLF 转换提示，退出码为 0，未发现 whitespace error：

- `src/anime_pref/sampling/config.py`
- `tests/test_categorical_value_sampler.py`

## 请理论侧确认

1. Sequential survivor implementation 是否与 D5B mechanics process 完全一致。
2. 每个 conditional stage 的 singleton-zero-draw / multi-one-draw 是否正式冻结。
3. 相同 context 下与 Phase C 的 exact result 和 RNG advancement equivalence 是否满足要求。
4. 直接返回唯一 `StructuralPatternPlan` 的边界是否正确。

## 未实现

- combined B→D5C1→D5C2 master sampler；
- categorical/numeric/format/status value binding；
- tag group 或 reference-title binding；
- combination plausibility；
- SemanticSpec assembly；
- distribution audit；
- production dataset generation。
