# D5C1. Structural Signature RNG Sampler v0.1 实现报告

## 1. 本阶段职责

D5C1 实际采样：

```text
P(StructuralSignature | FamilyComplexityPlan)
```

输入由 validated D5A policy、Phase A sampler config、已经选择的 `FamilyComplexityPlan` 和 caller-owned RNG 组成。输出直接是 `StructuralSignature`，不会继续选择 mechanics pattern。

## 2. 新增文件

- `src/anime_pref/sampling/structural_signature_sampler.py`：caller-owned RNG protocol、singleton-aware choice 和 operational public sampler。
- `tests/test_structural_signature_sampler.py`：D5C1 合同与 RNG consumption 测试。

## 3. `RandomSource`

```python
class RandomSource(Protocol):
    def random(self) -> float: ...
```

Sampler 只要求 caller 提供 callable `random()`。Runtime 不创建 `Random(seed)`，不使用 module-global random state，也不把 `None` 解释为隐式 RNG。

## 4. `_choose_signature_from_probabilities()`

输入是 D5A 已经归一化且具有 canonical insertion order 的 mapping：

```text
0 candidates  → ValueError
1 candidate   → 直接返回，0 RNG draws
>1 candidates → 调用已有 _weighted_choice，一次 draw
```

函数不按 weight 或 probability 重排 mapping，也没有重新实现 cumulative comparison。

## 5. `sample_structural_signature()`

完整执行顺序：

1. 调用 D5A `validate_structural_pattern_selection_policy(policy, sampler_config)`。
2. 验证当前 `FamilyComplexityPlan`。
3. 验证 caller-owned RNG 提供 callable `random()`。
4. 调用 D5A `signature_probabilities(policy, family_plan)`。
5. 按 mapping insertion order 提取 candidates。
6. Singleton 直接返回；multi-candidate 调用 `_weighted_choice()`。
7. 返回 `StructuralSignature`。

所有 validation、policy/config binding、D4 membership 和 B-context coverage 都发生在第一次 RNG draw 之前。

## 6. 完整参数调用流程

```python
from pathlib import Path
from random import Random

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.structural_signature import (
    load_structural_pattern_selection_policy,
)
from anime_pref.sampling.structural_signature_sampler import (
    sample_structural_signature,
)

config = load_sampler_config(
    Path("tests/fixtures/semantic_sampler.synthetic.v0.1.json")
)
policy = load_structural_pattern_selection_policy(
    Path("tests/fixtures/structural_pattern_policy.synthetic.v0.1.json")
)
family_plan = FamilyComplexityPlan("single_constraint", "1")
rng = Random(3817)

selected = sample_structural_signature(
    policy,
    config,
    family_plan,
    rng,
)
```

调用路径：

```text
sample_structural_signature
→ D5A operational binding
   → policy structure/hash
   → sampler_version match
   → all B contexts covered
   → configured signatures D4-eligible
→ validate FamilyComplexityPlan
→ validate caller RNG interface
→ D5A signature_probabilities
→ canonical choices tuple
→ singleton direct return OR existing _weighted_choice
→ StructuralSignature
```

## 7. 概率区间示例

Synthetic policy 在 `single_constraint/1` 中得到：

```text
canonical candidates:
1. genre_set
2. year_range
3. format_any

probabilities:
genre_set  = 3/6 = 0.5
year_range = 2/6 = 1/3
format_any = 1/6
```

使用已有 `_weighted_choice` 的半开区间：

```text
[0, 0.5)     → StructuralSignature(("genre_set",))
[0.5, 5/6)   → StructuralSignature(("year_range",))
[5/6, 1)     → StructuralSignature(("format_any",))
```

例如 caller RNG 返回 `0.7`：

1. `0.7` 不小于第一段 cumulative `0.5`；
2. `0.7 < 0.833333...`；
3. 返回 `("year_range",)`；
4. RNG state 前进恰好一步。

边界值 `0.5` 进入 year，`5/6` 进入 format，与项目已有 primitive 完全一致。

## 8. Singleton 示例

对于 `FamilyComplexityPlan("reference_only", 0)`，D5A mapping 是：

```python
{StructuralSignature(("reference",)): 1.0}
```

D5C1 直接返回 reference signature，不调用 `_weighted_choice`，RNG draw count 为 0。`same_field_logic/2` 在当前 synthetic allowlist 也只有一个 enabled signature，同样零 draw。

## 9. Failure-before-draw

Counting RNG 测试确认以下错误均在 draw count 仍为 0 时抛出：

- policy hash 被篡改；
- policy/config sampler version 不一致；
- invalid `FamilyComplexityPlan`；
- RNG 没有 callable `random()`；
- policy 配置 D4-invalid signature；
- 任一 B context 没有 enabled signature。

Binding validation 自身不接触 RNG。

## 10. Determinism 与 state advancement

```text
same policy + same config + same family plan + same RNG state
→ same signature + same final RNG state
```

对 multi-candidate context，测试将 sampler 后的 `Random.getstate()` 与手动调用一次 `random()` 后的同 seed RNG 比较，两者完全一致。

## 11. Scale invariance 与 context isolation

`3:2:1` 和 `30:20:10` 两份 policy：

- policy hash 不同；
- D5A normalized mapping 相同；
- 使用相同 draw 时 D5C1 选择相同 signature；
- RNG advancement 相同。

将其他 family/bucket 的 weights 放大 100 倍不会改变当前 `single_constraint/1` 的选择。

## 12. 阶段边界

D5C1 没有：

- 复制 D5A filtering/normalization；
- 自定义 weighted cumulative algorithm；
- retry/rejection loop；
- D5B mechanics probability 或 mechanics selection；
- DomainRules/subset/catalog；
- concrete values、group/HAREM binding；
- SemanticSpec/DatasetRecord/user_text；
- E～G 或 production generation。

