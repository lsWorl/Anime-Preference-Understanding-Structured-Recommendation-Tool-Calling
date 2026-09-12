# D5A.1 Numeric Weight Identity Fix Review Bundle

## 修复范围

本 patch 只修复 relative-weight canonical float identity。D5A 其他 architecture、allowlist、binding 和 probability 合同保持不变，未开始 D5B。

## 修改文件

- `src/anime_pref/sampling/structural_signature.py`
- `tests/test_structural_signature_policy.py`
- `docs/structural_signature_policy_v0.1_IMPLEMENTATION.md`

## 核心修复

新增公共真值来源：

```python
canonical_relative_weight(value) -> float
```

规则：

- `int`/`float` only，bool 非法；
- `canonical = float(value)`；
- canonical 必须 finite 且正数；
- source 是 int 时必须满足 `int(canonical) == value`；
- validator 与 canonical serializer 都调用该函数。

## Identity 与 probability 区分

```text
1 和 1.0
→ canonical weight 都是 1.0
→ policy hash 相同
```

```text
9007199254740992
→ binary64 round-trip 无损
→ accepted

9007199254740993
→ binary64 round-trip 有损
→ rejected before hashing
```

```text
3:2:1 和 30:20:10
→ normalized probabilities 相同
→ admitted policy contents 不同
→ policy hashes 不同
```

## 自动测试证据

- `1` 与 `1.0` canonical hash identity 相同；
- `2**53` 可接受；
- `2**53 + 1` 在 canonical conversion/hash 前被拒绝；
- `3:2:1` 与 `30:20:10` 的 context-local probabilities 相同；
- 两套 scale-equivalent raw policies 的 hash 不同；
- 原 D5A standalone/binding/allowlist/hash tests 保持通过。

实际命令结果：

```text
D5A/D5A.1 专项测试：Ran 27 tests in 5.833s — OK
完整工程测试：Ran 232 tests in 11.980s — OK
1 vs 1.0 identity：PASS
2**53 accepted / 2**53+1 rejected：PASS
3:2:1 vs 30:20:10 probability invariance：PASS
3:2:1 vs 30:20:10 policy hash distinction：PASS
compileall：PASS
git diff --check：PASS（仅有已有工作区文件的 LF/CRLF 提示）
skip / expectedFailure：0
```

## 未修改边界

- signature canonical sort；
- entry canonical order；
- source JSON 不带 hash；
- explicit allowlist 与 B-context coverage；
- sampler-version/D4-membership binding；
- context-local normalization；
- no RNG、selection、DomainRules/subset/catalog；
- no SemanticSpec/DatasetRecord；
- no D5B。
