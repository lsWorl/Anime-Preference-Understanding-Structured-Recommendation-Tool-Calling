# D5A. Structural Signature Selection Policy Contract v0.1 Review Bundle

## 审查范围

```text
D4 StructuralPatternPlan
→ StructuralSignature
→ explicit context allowlist
→ conditional relative-weight table
```

本阶段不执行 sampling。

## 核心文件

- `src/anime_pref/schemas/structural_signature.py`
- `src/anime_pref/sampling/structural_signature.py`
- `tests/fixtures/structural_pattern_policy.synthetic.v0.1.json`
- `tests/test_structural_signature_policy.py`
- `docs/structural_signature_policy_v0.1_IMPLEMENTATION.md`

## 合同落实情况

- Signature 只含 canonical、nonempty、unique `atom_kinds`。
- Signature 不含 family/bucket 或 payload mechanics。
- Extraction 先调用 D4 public validator。
- Operator/cardinality 和 numeric pattern variants 折叠为相同 signature。
- Eligible signature enumeration deterministic、canonical、deduplicated。
- D5A policy 与 Phase A config 分离。
- Strict JSON loader 拒绝 missing/unknown/noncanonical 输入。
- Policy entries 是 immutable tuple。
- Weight 要求 finite positive，不要求总和为 1。
- `(family,bucket,signature)` duplicate 被拒绝。
- 配置使用 explicit allowlist；missing D4 signature 保持 disabled。
- Binding 要求 sampler version 一致。
- Configured signature 必须存在于对应 D4 space。
- 全部 B contexts 至少一个 enabled signature。
- Probability 只在已选 context 内归一化。
- Policy 具有独立 version/hash，hash 不包含自身。
- Canonical compact Unicode JSON → UTF-8 → SHA-256。
- 当前 synthetic policy hash：`41ae5b66b8887867685f03c97e3617d976a6dd9172a7bb48b87f3dc0c195b6be`。
- Fixture 的 22 entries 覆盖全部 19 个 B contexts。
- 无 RNG、pattern/signature selection、domain/catalog dependency 或 downstream assembly。

## 代表性概率

`single_constraint/1`：

```text
genre_set: 3
year_range: 2
format_any: 1
```

归一化：

```text
genre_set: 0.5
year_range: 0.3333333333333333
format_any: 0.16666666666666666
```

未配置的 `tag_set`、`episodes_range`、`status_any` 仍是 D4 eligible，但 D5A sampling-disabled。

## 自动测试覆盖

- signature extraction；
- operator/cardinality 和 numeric pattern 忽略；
- canonical/nonempty/unique kinds；
- deterministic enumeration 和 mechanics dedup；
- reference-only signature；
- strict loader 与 immutable contract；
- finite positive weights、无 sum-to-one 要求；
- duplicate/noncanonical entries；
- deterministic hash、numeric representation canonicalization；
- admitted content/hash tamper；
- sampler-version binding；
- D4 membership；
- 全 B-context coverage；
- explicit disabled signatures；
- within-context scaling invariance；
- context-independent normalization；
- no RNG/domain/value/downstream dependency。

实际测试结果：

```text
D5A/D5A.1 专项测试：Ran 27 tests in 5.833s — OK
完整工程测试：Ran 232 tests in 11.980s — OK
compileall：PASS
git diff --check：PASS（仅有已有工作区文件的 LF/CRLF 提示）
skip / expectedFailure：0
```

## 请理论侧重点确认

1. Signature enumeration 用 D3 kind indexes canonical sort，在 mechanics dedup 后不保留 D4 first-occurrence order，是否是期望的 canonical representation。
2. Entry canonical order采用 family → bucket → signature kind-index tuple，是否可以冻结为 policy mechanics identity。
3. Source JSON 不携带 hash，runtime policy 携带并验证 derived hash，是否符合 identity contract。
4. JSON weight `1` 与 `1.0` canonicalize 为相同 hash identity，是否符合 relative-weight representation 语义。
5. Synthetic fixture 仅启用部分 D4 signatures但覆盖全部 B contexts，是否准确落实 allowlist 与 capacity 边界。
6. `signature_probabilities()` 只执行 standalone validation；实际使用前由 orchestration 显式完成 config/D4 binding，职责是否正确。

## 未实现

- signature RNG sampling；
- payload mechanics probability/sampling；
- uniform within signature；
- group identity/domain/catalog binding；
- concrete values；
- SemanticSpec assembly；
- combination plausibility；
- distribution audit；
- production dataset generation。
