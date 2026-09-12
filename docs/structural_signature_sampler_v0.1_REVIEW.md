# D5C1. Structural Signature RNG Sampler v0.1 Review Bundle

## 审查范围

```text
validated D5A policy
+ SemanticSamplerConfigSpec
+ already-selected FamilyComplexityPlan
+ caller-owned RNG
→ StructuralSignature
```

## 核心文件

- `src/anime_pref/sampling/structural_signature_sampler.py`
- `tests/test_structural_signature_sampler.py`
- `docs/structural_signature_sampler_v0.1_IMPLEMENTATION.md`

## 合同落实情况

- Public sampler 每次先执行完整 D5A operational binding。
- D5A `signature_probabilities()` 是唯一概率真值来源。
- Candidate 顺序直接使用 D5A mapping insertion order。
- Multi-candidate 复用已有 `_weighted_choice()`。
- Singleton 直接返回，不调用 weighted choice。
- Singleton/reference-only 消耗 0 draws。
- Multi-candidate 消耗恰好 1 draw。
- RNG 完全由 caller 提供，runtime 不创建或隐藏 RNG。
- Validation/binding failure 全部发生在首次 draw 前。
- 相同输入和 RNG state 得到相同 signature 与 state advancement。
- Scale-equivalent weights 选择相同，但 policy hash 保持不同。
- 其他 context 的 weight 变化不影响当前选择。
- 输出直接是 `StructuralSignature`，无 wrapper/debug payload。
- 无 retry、D5B mechanics call、domain/value/downstream logic。

## 代表性区间

```text
single_constraint / 1

genre_set:  0.5
year_range: 1/3
format_any: 1/6

[0, 0.5)   → genre_set
[0.5, 5/6) → year_range
[5/6, 1)   → format_any
```

## 自动测试覆盖

- binding-before-probability 调用顺序；
- D5A mapping 与 canonical candidate order 复用；
- singleton/multi-candidate draw count；
- reference-only zero draw；
- half-open probability intervals；
- same seed/state determinism；
- exact one-step RNG advancement；
- binding zero draw；
- bad hash/version/family/RNG/D4 signature/context coverage failure-before-draw；
- scale selection invariance 与 hash distinction；
- other-context isolation；
- direct `StructuralSignature` output；
- no D5B/domain/downstream dependency。

## 验收结果

```text
D5C1 专项测试
Ran 19 tests in 5.661s
OK

完整工程测试
Ran 270 tests in 16.746s
OK

compileall: PASS
git diff --check: PASS
skip / expectedFailure 搜索结果: 0
```

`git diff --check` 只显示两个既有工作区文件的 LF/CRLF 转换提示，退出码为 0，未发现 whitespace error：

- `src/anime_pref/sampling/config.py`
- `tests/test_categorical_value_sampler.py`

## 请理论侧重点确认

1. Public entrypoint 顺序为完整 D5A binding → family plan → RNG interface → D5A probabilities → selection，是否正式冻结。
2. Singleton 在 public binding 和 probability lookup 完成后直接返回并消耗 0 draws，是否正确。
3. Candidate order 完全继承 D5A mapping，multi-candidate 完全复用 `_weighted_choice`，是否满足 reproducibility contract。
4. Output 直接返回 `StructuralSignature`，不增加 selection metadata，是否正确。

## 未实现

- D5C2 mechanics RNG sampler；
- combined signature/mechanics sampler；
- value/domain/group binding；
- SemanticSpec assembly；
- combination plausibility；
- distribution audit；
- production generation。
