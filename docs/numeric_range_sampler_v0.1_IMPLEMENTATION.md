# D2. Direct Numeric Range Value Sampler v0.1 实现报告

## 1. 阶段目标

D2 接收调用者已经决定好的 numeric field 和 range pattern：

```python
field = "year"                  # 或 episodes
range_pattern = "bounded_range" # 或 min_only / max_only
```

再从 Phase A 配置的 numeric pools 中生成 canonical range：

```python
DirectNumericRangePlan(
    field="year",
    range_pattern="bounded_range",
    minimum=2010,
    maximum=2020,
)
```

D2 不选择 field、pattern、semantic family 或 structural pattern。

## 2. 文件与数据结构

```text
src/anime_pref/schemas/numeric_range.py
src/anime_pref/sampling/numeric_range.py
tests/test_numeric_range_sampler.py
docs/numeric_range_sampler_v0.1_IMPLEMENTATION.md
docs/numeric_range_sampler_v0.1_REVIEW.md
```

输出对象是 frozen dataclass：

```python
@dataclass(frozen=True)
class DirectNumericRangePlan:
    field: Literal["year", "episodes"]
    range_pattern: Literal["min_only", "max_only", "bounded_range"]
    minimum: int | None
    maximum: int | None
```

Canonical representation 固定为：

```text
min_only      -> minimum=value, maximum=None
max_only      -> minimum=None,  maximum=value
bounded_range -> minimum=lower, maximum=upper, lower <= upper
```

## 3. Canonical mechanics 常量

`NUMERIC_VALUE_POOL_ORDER` 固定为：

```text
common
catalog_region
long_tail
```

每个 pool 的 values 已由 Phase A 要求升序。跨 pool 合并 value 时，D2 再按数值全局升序排列。
顺序不表示语义优先级，但会影响相同 RNG state 的累计概率区间，因此修改顺序需要 bump
`sampler_version`。

## 4. 主要函数

### `validate_numeric_sampling_binding(field, config, rules)`

依次执行：

1. field 必须是 `year` 或 `episodes`。
2. 调用 `validate_sampler_config()` 验证 Phase A 完整配置。
3. 重新计算 `DomainRules` canonical hash，拒绝被篡改的 rules。
4. 读取 field 对应的 `NumericRule` validity guard。
5. 检查三个配置 pool 中的每个 value 都满足实际 DomainRules bounds。

这里不会从 validity range 生成候选值。validity 只负责拒绝损坏配置。

### `numeric_constraint_contribution(pattern)`

返回 direct numeric hard semantic contribution：

```text
min_only      -> 1
max_only      -> 1
bounded_range -> 2
```

函数不会根据 contribution 选择 family 或 pattern。

### `numeric_value_pools(field, config, rules)`

完成 binding validation 后，按 canonical pool order 返回 config 中的原始 tuple。函数不会移动
value 的 pool identity，也不会根据数值大小重新分类。

### `numeric_pool_probabilities(field, config, rules)`

只归一化当前真正存在的 configurable numeric relative-weight layer：

```text
P(S=s) = w_s / sum(w)
```

它不读取 `pattern_weights`，因为 pattern 已由调用者显式提供。

### `base_numeric_value_probabilities(field, config, rules)`

对每个原始 pool 计算：

```text
P0(v) = P(pool(v)) / original_pool_size
```

pool 内 uniform 是冻结合同。函数最后按 value 数值全局升序输出 mapping。

### `conditioned_upper_probabilities(field, lower, config, rules)`

处理 bounded upper：

1. lower 必须是非 bool integer，且来自配置 pool。
2. 计算所有 values 的原始 `P0(v)`。
3. 删除 `v < lower`。
4. 对 surviving base marginals 全局归一化。

公式：

```text
P(U=v | L) = P0(v) / sum(P0(u), u >= L)
```

这里不会重新选择 upper pool，也不会使用 surviving pool size 重新均匀化。

### `_choose_probability_candidate(probabilities, rng)`

统一执行最小 RNG 消耗：

```text
candidate count == 1 -> 直接返回，0 draw
candidate count > 1  -> 一次 weighted draw
```

它始终使用 mapping 的 canonical insertion order。

### `_sample_base_endpoint(field, config, rules, rng)`

用于 single-bound endpoint 和 bounded lower：

```text
numeric_pool_probabilities
→ 选择 pool
→ 对 selected pool 的原始 values 设置相同单位权重
→ pool 内 uniform 选择 value
```

pool stage 和 value stage 各自应用 singleton 零 draw 规则。

### `validate_direct_numeric_range_plan(plan, rules)`

这是 generic public validator，检查：

- 对象类型；
- field 与 pattern；
- rules canonical identity；
- bool 不得作为 endpoint integer；
- pattern 与 minimum/maximum 的 canonical 对应关系；
- bounded range 满足 `minimum <= maximum`；
- endpoint 满足对应 DomainRules validity bounds。

它不要求 endpoint 一定在 sampler pool 内。比如 year=1950 在 1900..2100 内是 generic-valid，
即使当前 synthetic pool 不采 1950。这体现 validity range 与 sampling universe 的分离。

### `sample_direct_numeric_range(...)`

完整签名：

```python
sample_direct_numeric_range(
    field,
    range_pattern,
    config,
    rules,
    rng,
)
```

调用链：

```text
validate field/pattern
→ validate numeric config/rules binding
→ validate caller-owned RNG
→ sample first endpoint through pool → uniform value
→ min_only/max_only: 构造 single-bound plan
→ bounded_range: globally condition upper values and direct weighted draw
→ validate DirectNumericRangePlan
→ return
```

代码中不存在 `min > max` 后 retry，也没有 bounded upper 的第二次 pool selection。

## 5. 完整参数流程示例一：Year bounded range

### 5.1 输入代码

```python
config = load_sampler_config(
    Path("tests/fixtures/semantic_sampler.synthetic.v0.1.json")
)
rules = load_domain_rules(
    Path("tests/fixtures/domain_rules.synthetic.v0.1.json")
)

result = sample_direct_numeric_range(
    field="year",
    range_pattern="bounded_range",
    config=config,
    rules=rules,
    rng=Random(2026),
)
```

### 5.2 Pool probabilities

fixture pool weights 是 `6 / 3 / 1`，所以：

```text
P(common)         = 0.6
P(catalog_region) = 0.3
P(long_tail)      = 0.1
```

### 5.3 Base marginals

Year pools：

```text
common:         2000, 2010, 2020          size=3
catalog_region: 1990, 2005, 2015, 2024    size=4
long_tail:      1917, 1983, 2037          size=3
```

因此：

```text
common value marginal         = 0.6 / 3 = 0.20
catalog_region value marginal = 0.3 / 4 = 0.075
long_tail value marginal      = 0.1 / 3 = 0.033333...
```

`Random(2026)` 的前三个 draw：

```text
0.11911988496396309
0.5025157552312506
0.511822712773071
```

### 5.4 Lower sampling

第一个 draw `0.1191` 落在 common pool 的 `[0, 0.6)` 区间。

common 内三个 values uniform。第二个 draw `0.5025` 落在第二个三分之一区间，因此：

```text
lower = 2010
```

### 5.5 Upper global conditioning

删除小于 2010 的 values。survivors 及未归一化 base marginals：

```text
2010 -> 0.20
2015 -> 0.075
2020 -> 0.20
2024 -> 0.075
2037 -> 0.033333...
```

surviving total 为 `0.583333...`。条件概率：

```text
2010 -> 0.3428571429
2015 -> 0.1285714286
2020 -> 0.3428571429
2024 -> 0.1285714286
2037 -> 0.0571428571
```

第三个 draw `0.5118` 直接作用于这个全局升序 universe，落在 2020 的累计区间。因此：

```text
upper = 2020
```

upper 阶段没有 pool draw。最终输出：

```python
DirectNumericRangePlan(
    field="year",
    range_pattern="bounded_range",
    minimum=2010,
    maximum=2020,
)
```

总 RNG 消耗为三次：lower pool、lower value、global upper 各一次。

## 6. 完整参数流程示例二：Episodes max-only

输入：

```python
result = sample_direct_numeric_range(
    "episodes",
    "max_only",
    config,
    rules,
    Random(2026),
)
```

Episode common pool 为 `(12, 24)`。第一个 draw 仍选 common，第二个 draw `0.5025` 落在 24 的
区间，输出：

```python
DirectNumericRangePlan(
    field="episodes",
    range_pattern="max_only",
    minimum=None,
    maximum=24,
)
```

`pattern_weights` 没有参与任何选择。

## 7. Equal endpoint 与零 upper draw 示例

若 lower pool/value draws 选中 year 全局最大候选 `2037`：

```text
eligible upper = {2037}
```

upper 是 singleton，直接确定为 2037，不消费第三次 draw：

```python
DirectNumericRangePlan(
    field="year",
    range_pattern="bounded_range",
    minimum=2037,
    maximum=2037,
)
```

这既验证 `minimum == maximum` 合法，也验证 bounded range 不强制固定三次 RNG。

## 8. Partially surviving pool 为什么不重新均匀化

以 lower=2020 为例，survivors 是：

```text
2020: common pool 原始概率 0.6/3 = 0.20
2024: catalog pool 原始概率 0.3/4 = 0.075
2037: long-tail pool 原始概率 0.1/3 = 0.033333...
```

catalog pool 原本有四个值，现在只有 2024 survives。D2 仍保留 `0.3/4`，不会把它改成
`0.3/1`。三项再一起做 global conditioning。这避免了过滤后突然放大某个 pool 的 surviving value。

## 9. 测试与边界

D2 专项测试覆盖 pool uniform、base marginal、不同 pool size、scale invariance、single-bound
hierarchy、singleton RNG、bounded lower、global upper conditioning、partial survival、equal endpoint、
最大三 draw、candidate source、generic validator、pattern-weight non-consumption 及阶段边界。

```text
D2 专项测试：26 passed
完整离线测试：162 passed
失败：0
跳过：0
```

当前仍是 synthetic/offline mechanics。没有实现 structural planner、categorical composition、HAREM、
SemanticSpec、DatasetRecord、user text、E～G 或 production numeric policy。
