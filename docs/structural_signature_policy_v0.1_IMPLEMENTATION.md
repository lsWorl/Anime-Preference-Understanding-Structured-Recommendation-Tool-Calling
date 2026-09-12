# D5A. Structural Signature Selection Policy Contract v0.1 实现报告

## 1. 阶段目标

D5A 在 D4 mechanics patterns 上增加结构签名和显式 allowlist：

```text
FamilyComplexityPlan
→ D4 eligible StructuralPatternPlan
→ StructuralSignature 去除 payload mechanics
→ standalone signature weight policy
→ P(signature | family, complexity)
```

本阶段只定义 sampling support 与 relative-weight policy。它不使用 RNG，也不选择 signature 或具体 mechanics pattern。

## 2. 文件职责

- `src/anime_pref/schemas/structural_signature.py`
  - `StructuralSignature`
  - `StructuralSignatureWeightSpec`
  - `StructuralPatternSelectionPolicySpec`
- `src/anime_pref/sampling/structural_signature.py`
  - signature validation/extraction/enumeration；
  - strict JSON policy loader；
  - canonical serialization 与 SHA-256；
  - Phase A/D4 binding validation；
  - context-local probability normalization。
- `tests/fixtures/structural_pattern_policy.synthetic.v0.1.json`
  - 覆盖全部 B context 的离线 synthetic allowlist。
- `tests/test_structural_signature_policy.py`
  - D5A 合同测试。

## 3. Runtime 数据结构

### `StructuralSignature`

```python
@dataclass(frozen=True)
class StructuralSignature:
    atom_kinds: tuple[StructuralAtomKind, ...]
```

Signature 只表达哪些结构槽位存在。它不包含 family、bucket、operator、cardinality、range pattern 或具体值。

### `StructuralSignatureWeightSpec`

```python
@dataclass(frozen=True)
class StructuralSignatureWeightSpec:
    semantic_family: SemanticFamily
    complexity_bucket: ComplexityBucket
    atom_kinds: tuple[StructuralAtomKind, ...]
    weight: float
```

一个 entry 是一个 `(family, bucket, signature)` allowlist identity。相同 signature 可以出现在不同 context，因为它的可用 mechanics 和 policy weight 可以随 context 改变。

### `StructuralPatternSelectionPolicySpec`

```python
@dataclass(frozen=True)
class StructuralPatternSelectionPolicySpec:
    policy_version: str
    sampler_version: str
    signature_entries: tuple[StructuralSignatureWeightSpec, ...]
    policy_hash: str
```

源 JSON 不包含 `policy_hash`。Loader 对 canonical document 计算 SHA-256，再把 hash 附到 runtime 对象上，避免自引用。

## 4. Signature 合同函数

### `validate_structural_signature(signature)`

验证：

1. 对象类型正确；
2. `atom_kinds` 是非空 tuple；
3. 每个 kind 属于 D3 vocabulary；
4. kind 不重复；
5. kind 使用 D3 canonical order。

函数不会 strip、排序或去重 malformed 输入。

### `structural_signature(pattern)`

1. 调用 D4 `validate_structural_pattern_plan()`；
2. 按 pattern 中已有 canonical atom 顺序提取 `atom.kind`；
3. 构造并验证 `StructuralSignature`。

因此 malformed/noncanonical D4 pattern 不会在 extraction 时被修复。

### `enumerate_eligible_structural_signatures(family_plan)`

```text
D4 enumerate_eligible_structural_patterns
→ 每个 pattern 调 structural_signature
→ set 消除 mechanics multiplicity
→ 按 D3 kind index 做 canonical sort
→ immutable tuple
```

函数使用 immutable memoization 避免 policy binding 重复展开 D4 的有限 mechanics space。缓存不改变返回值，也不引入随机状态。

例如 `single_constraint/1` 有 14 个 D4 mechanics patterns，但它们折叠为 6 个 signatures：

```text
genre_set
tag_set
year_range
episodes_range
format_any
status_any
```

`genre_set(all_of/1)`、`genre_set(any_of/2)`、`genre_set(any_of/3)` 和 `genre_set(none_of/1)` 都得到同一个 `("genre_set",)` signature。

## 5. Strict policy loader

### JSON contract

```json
{
  "policy_version": "offline-synthetic-structural-signature-policy-v0.1",
  "sampler_version": "offline-synthetic-semantic-sampler-v0.1",
  "signature_entries": [
    {
      "semantic_family": "cross_field_composition",
      "complexity_bucket": "2",
      "atom_kinds": ["genre_set", "year_range"],
      "weight": 4
    }
  ]
}
```

顶层和 entry 都采用 exact-key contract。Loader 将 entry array 和 `atom_kinds` array 转成 tuple，但不排序。以下内容直接失败：

- missing/unknown keys；
- 非 canonical entry order；
- 非 canonical atom kind order；
- duplicate identity；
- 非 finite-positive weight；
- 不合法 family/bucket；
- source JSON 自带 `policy_hash`。

### Entry canonical order

Policy entries 使用：

```text
SEMANTIC_FAMILY_ORDER
→ complexity bucket order: 0, 1, 2, 3, 4, 5_plus
→ atom-kind index tuple lexicographic order
```

该顺序服务 reproducibility 和 hash identity，不表示概率优先级。

## 6. Canonical serialization 和 identity

### `canonical_relative_weight(value)`

D5A.1 将 weight validation 与 hash conversion 合并到同一个真值来源：

1. 只接受 `int` 或 `float`，拒绝 bool；
2. 转换为 canonical float；
3. 要求 canonical float finite 且大于 0；
4. 若 source value 是 int，要求 `int(canonical) == value`。

最后一条保证所有获准的整数都能被 binary64 无损表示，避免两个不同的大整数在 canonical document 中折叠为相同 float。

因此：

```text
1 / 1.0 / JSON 1e0 → 相同 canonical numeric identity
9007199254740992 → accepted
9007199254740993 → rejected（float round-trip 有损）
```

### `canonical_structural_pattern_selection_policy_mapping(policy)`

输出只包含：

- `policy_version`
- `sampler_version`
- canonical `signature_entries`

`policy_hash` 本身不进入 document。Weight 通过 `canonical_relative_weight()` 序列化，因此 validator 接受的值一定能安全进入 canonical float identity；JSON 数字 `1` 与 `1.0` 得到相同 identity。

### `dumps_structural_pattern_selection_policy(policy)`

使用：

```text
ensure_ascii=False
compact separators
allow_nan=False
```

生成 compact Unicode JSON。

### `structural_pattern_selection_policy_sha256(policy)`

```text
canonical JSON
→ UTF-8 bytes
→ SHA-256 lowercase hex
```

Synthetic fixture 当前 hash：

```text
41ae5b66b8887867685f03c97e3617d976a6dd9172a7bb48b87f3dc0c195b6be
```

### `validate_structural_pattern_selection_policy_spec(policy)`

验证 standalone structure、entry order、weight、duplicate identity 以及 `policy_hash` 与 canonical content 一致。

## 7. Binding validation

### `validate_structural_pattern_selection_policy(policy, sampler_config)`

完整流程：

1. 验证 standalone policy 和 hash。
2. 验证 Phase A sampler config。
3. 要求两个 `sampler_version` 相等。
4. 枚举全部 B-compatible family/bucket contexts。
5. 为每个 context 获取 D4 eligible signatures。
6. 验证每个 configured signature 属于对应 D4 space。
7. 要求每个 B context 至少有一个 enabled signature。

没有 entry 的 D4 signature 保持 disabled。Binding 不添加 default weight，也不要求全部 D4 signatures 都出现在 policy。

D5A 不消费 `DomainRules`、`ExecutableTagSubset` 或 catalog。

## 8. Probability helper

### `signature_probabilities(policy, family_plan)`

该函数计算：

```text
P(signature=s | family, complexity)
= w(s) / Σ context 内 enabled signatures 的 weight
```

它只读取与输入 `family_plan` 完全匹配的 entries。其他 context 的权重不进入分母。

Missing D4 signatures 不加入 mapping，因此其 sampling weight 是 0。

## 9. 完整参数调用流程

```python
from pathlib import Path

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.structural_signature import (
    load_structural_pattern_selection_policy,
    signature_probabilities,
    validate_structural_pattern_selection_policy,
)

sampler_config = load_sampler_config(
    Path("tests/fixtures/semantic_sampler.synthetic.v0.1.json")
)
policy = load_structural_pattern_selection_policy(
    Path("tests/fixtures/structural_pattern_policy.synthetic.v0.1.json")
)

validate_structural_pattern_selection_policy(policy, sampler_config)

context = FamilyComplexityPlan("single_constraint", "1")
probabilities = signature_probabilities(policy, context)
```

调用路径：

```text
load JSON
→ exact-key parse
→ immutable entries
→ standalone content validation
→ canonical Unicode JSON
→ UTF-8 SHA-256
→ runtime policy with policy_hash
→ identity revalidation

validate binding
→ sampler_version match
→ enumerate all B contexts
→ D4 patterns
→ signature extraction/dedup
→ configured signature membership
→ context coverage

signature_probabilities(single_constraint/1)
→ only this context's entries
→ normalize 3 : 2 : 1
```

输出：

```python
{
    StructuralSignature(("genre_set",)): 0.5,
    StructuralSignature(("year_range",)): 1 / 3,
    StructuralSignature(("format_any",)): 1 / 6,
}
```

同一 context 权重放大为 `30:20:10` 后概率不变。把其他 context 的权重放大 100 倍也不会改变以上结果。

`3:2:1` 与 `30:20:10` 的 policy hash 不同，因为 raw relative weights 是 admitted policy content。这里只冻结 probability scale invariance，不把比例等价扩展成 policy identity 等价。

## 10. Reference-only 流程

`reference_only/0` 在 D4 只有 `("reference",)`。Fixture 仍显式配置 finite-positive weight：

```python
signature_probabilities(policy, FamilyComplexityPlan("reference_only", 0))
```

普通 singleton normalization 得到：

```python
{StructuralSignature(("reference",)): 1.0}
```

代码没有 reference-only magic factor。

## 11. Synthetic fixture 边界

Fixture 有 22 个 entries，覆盖全部 19 个 B contexts。部分 context 配置多个 signatures 以测试相对权重，其余使用最小 allowlist。

这些 weights 只用于离线合同验证，不代表真实用户 query、AniList traffic 或 production structural distribution。

## 12. 阶段边界

```text
structurally eligible
≠ sampling-enabled
≠ domain-bindable
≠ catalog-plausible
```

D5A 没有：

- RNG 或 signature/pattern selection；
- uniform-within-signature；
- mechanics candidate count weight；
- payload-pattern probability；
- group identity 或 HAREM binding；
- concrete categorical/numeric/reference values；
- SemanticSpec/DatasetRecord/user_text；
- combination plausibility、distribution audit 或 production generation。
