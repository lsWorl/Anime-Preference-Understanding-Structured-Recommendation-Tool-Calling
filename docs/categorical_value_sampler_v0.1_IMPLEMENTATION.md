# D1. Direct Categorical Value Sampler v0.1 实现报告

## 1. 本阶段实现目标

D1 接收调用者已经决定好的字段和 C 阶段输出：

```python
field = "genres"  # 或 "tags"
operator_plan = OperatorCardinalityPlan("any_of", 3)
```

然后从经过验证的 active executable vocabulary 中抽取三个互不重复的 direct values，输出：

```python
DirectCategoricalValuePlan(
    field="genres",
    values=(...),
)
```

D1 不决定 field，不改变 operator/cardinality，也不生成 SemanticSpec。

## 2. 新增文件

```text
src/anime_pref/schemas/categorical_value.py
src/anime_pref/sampling/categorical_value.py
tests/test_categorical_value_sampler.py
docs/categorical_value_sampler_v0.1_IMPLEMENTATION.md
docs/categorical_value_sampler_v0.1_REVIEW.md
```

## 3. 输出数据结构

`DirectCategoricalValuePlan` 是 frozen dataclass：

```python
@dataclass(frozen=True)
class DirectCategoricalValuePlan:
    field: DirectCategoricalField
    values: tuple[str, ...]
```

两个 plan object 保持正交：

```text
OperatorCardinalityPlan
  operator="any_of"
  cardinality=3

DirectCategoricalValuePlan
  field="genres"
  values=("Comedy", "Mecha", "Music")
```

后续模块可以组合它们，但 D1 不把它们提前拼成 SemanticSpec-like payload。

## 4. 主要函数

### `_validate_field(field)`

只接受字符串 `genres` 或 `tags`。`formats`、`status` 和其他字段在 D1 中直接失败。

### `_active_values(field, rules)`

从 `DomainRules.genres` 或 `DomainRules.tags` 读取 active vocabulary，再按 Python Unicode lexical
order 排序为 tuple。DomainRules 中的集合没有顺序语义；这里排序只为了固定 seeded sampling 的
候选遍历顺序。

### `effective_value_weights(field, config, rules, subset)`

处理流程：

1. 验证 field。
2. 调用 `validate_sampler_config_against_domain()`，验证 config、rules、subset identity、active
   vocabulary 和 Phase A policy binding。
3. 取得 canonical active values。
4. 根据字段应用 effective-weight precedence。
5. 复用 `normalize_relative_weights()` 验证所有最终权重有限且大于零。
6. 返回 relative weights，不在此函数中改变或归一化其数值。

Genre precedence：

```text
priority_weights[value]
→ 如果没有，则 default_weight
```

Tag precedence：

```text
priority_weights[value]
→ 否则 value_tiers[value] 对应的 tier_weights[tier]
→ 否则 default_weight
```

显式 priority 与 tier 不相乘。未配置 tier 的 tag 只使用 default fallback，代码不会创建或输出
`standard` 标签。

### `initial_value_probabilities(field, config, rules, subset)`

调用 `effective_value_weights()`，然后归一化：

```text
P(v) = w(v) / sum(w)
```

这是第一次 draw 的 theoretical base distribution。函数不计算 cardinality 大于一时的最终
inclusion probability。

### `validate_direct_categorical_sampling_binding(...)`

取得 initial probabilities 后计算最大概率：

```text
max_probability = max(P(v))
```

再与对应字段配置的 `maximum_value_share` 比较。超过阈值立即失败。

该阈值只表示初始单次 draw 的 no-dominance guard，不表示最终数据集经验频率，也不表示无放回
抽样中的最终 inclusion probability。

### `validate_direct_categorical_value_plan(plan, rules, subset)`

这是 generic value-plan validator，依次检查：

1. 对象必须是 `DirectCategoricalValuePlan`。
2. field 必须是 `genres` 或 `tags`。
3. rules/subset identity 必须一致且有效。
4. values 必须是非空 tuple。
5. 每个 value 必须是无首尾空白的非空字符串。
6. values 不能重复。
7. values 必须已经按 canonical lexical order 排列。
8. 每个 value 必须属于当前 field 的 active DomainRules vocabulary。

因此 inactive-but-approved tag 也不能通过，因为它不属于 `DomainRules.tags`。

### `validate_direct_categorical_value_context(...)`

先分别验证 value plan 和 operator plan，再检查：

```text
len(value_plan.values) == operator_plan.cardinality
```

这保持了 generic validity 与 context compatibility 的分层。

### `sample_direct_categorical_values(...)`

完整签名：

```python
sample_direct_categorical_values(
    field,
    operator_plan,
    config,
    rules,
    subset,
    rng,
)
```

函数内部调用顺序：

```text
_validate_field
→ validate_operator_cardinality_plan
→ validate_direct_categorical_sampling_binding
→ validate caller-owned rng
→ effective_value_weights
→ capacity check
→ sequential weighted sampling without replacement
→ canonical sort selected set
→ validate_direct_categorical_value_context
→ return DirectCategoricalValuePlan
```

capacity 在任何抽样前检查。请求数量超过 active distinct values 时不会降低 cardinality、使用重复
value 或扩展到 inactive subset tag。

## 5. 无放回抽样算法

初始状态：

```python
remaining = dict(effective_weights)
selected = []
```

每一轮：

```text
如果 remaining 只有一个并且仍必须选择：
    直接选择，不消费 RNG
否则：
    对 remaining weights 重新归一化
    按 canonical remaining order 做一次 weighted draw

将 chosen 加入 selected
从 remaining 删除 chosen
```

删除动作使同一个 value 不可能再次被选择，因此不存在 duplicate retry loop。

最后执行：

```python
tuple(sorted(selected))
```

抽取先后顺序只影响 RNG history，不进入 set semantics 的 canonical representation。

## 6. 完整参数流程示例一：Genre any_of / 3

### 6.1 输入

```python
config = load_sampler_config(
    Path("tests/fixtures/semantic_sampler.synthetic.v0.1.json")
)
rules = load_domain_rules(
    Path("tests/fixtures/domain_rules.synthetic.v0.1.json")
)
subset = load_executable_tag_subset(
    Path("tests/fixtures/executable_tags.synthetic.v0.1.json")
)

operator_plan = OperatorCardinalityPlan(
    operator="any_of",
    cardinality=3,
)
rng = Random(2026)

result = sample_direct_categorical_values(
    "genres",
    operator_plan,
    config,
    rules,
    subset,
    rng,
)
```

`any_of/3` 的 hard constraint contribution 仍是 1，但 D1 必须选出三个 distinct values，因为
value cardinality 是 3。

### 6.2 Candidate universe

`rules.genres` 有 19 个 active genres。canonical order 从：

```text
Action, Adventure, Comedy, Drama, ..., Mystery, ..., Sci-Fi, ..., Thriller
```

开始。D1 没有读取 full AniList taxonomy 或其他未激活 genre。

### 6.3 Effective weights

fixture 中：

```text
Mystery priority = 1.10
Sci-Fi priority  = 1.05
其他 genre       = default 1.00
```

总权重：

```text
17 × 1.00 + 1.10 + 1.05 = 19.15
```

初始概率：

```text
普通 genre = 1.00 / 19.15 = 0.0522193211
Mystery    = 1.10 / 19.15 = 0.0574412533
Sci-Fi     = 1.05 / 19.15 = 0.0548302872
```

最大值 `0.0574412533 <= maximum_value_share 0.25`，binding 通过。

### 6.4 Sequential draws

`Random(2026)` 的前三次 draw 是：

```text
0.11911988496396309
0.5025157552312506
0.511822712773071
```

第一轮使用总权重 19.15，draw 落在 `Comedy` 区间：

```text
selected = [Comedy]
remaining 删除 Comedy
```

第二轮对剩余权重重新归一化，总权重变成 18.15。第二个 draw 落在 `Music`：

```text
selected = [Comedy, Music]
remaining 删除 Music
```

第三轮再次归一化，总权重变成 17.15。第三个 draw 落在 `Mecha`：

```text
selection order = [Comedy, Music, Mecha]
```

### 6.5 Canonical output

selection order 不具有语义，所以最终排序：

```python
DirectCategoricalValuePlan(
    field="genres",
    values=("Comedy", "Mecha", "Music"),
)
```

context validator 确认三个值均 active、互不重复，且 tuple 长度等于
`operator_plan.cardinality == 3`。

## 7. 完整参数流程示例二：Tag any_of / 3

### 7.1 输入

仍使用相同 config/rules/subset 和 `Random(2026)`，只将 field 改成 `tags`：

```python
result = sample_direct_categorical_values(
    "tags",
    OperatorCardinalityPlan("any_of", 3),
    config,
    rules,
    subset,
    Random(2026),
)
```

### 7.2 Active 与 approved 的边界

subset 中批准了四个 tags，但当前 `DomainRules.tags` 只激活：

```text
Female Harem
Male Harem
Mixed Gender Harem
```

`Ensemble Cast` 虽然 approved，但 inactive，所以不进入候选空间。

三个 active tags 都显式配置为 `core`，且没有 per-value priority：

```text
priority 不存在
→ 使用 core tier weight = 5
```

初始概率都是 `5 / 15 = 1/3`。最大概率 `1/3 <= maximum_value_share 0.4`。

### 7.3 RNG consumption

cardinality 等于 universe size：

```text
draw 1 = 0.11911988496396309 -> Female Harem
draw 2 = 0.5025157552312506  -> Mixed Gender Harem
remaining only Male Harem    -> deterministic, no third draw
```

输出按 canonical set order 排列：

```python
DirectCategoricalValuePlan(
    field="tags",
    values=(
        "Female Harem",
        "Male Harem",
        "Mixed Gender Harem",
    ),
)
```

这里只有 direct tag values。D1 没有生成 `HAREM` group，没有选择 group operator，也没有执行
normalization expansion。

## 8. Default fallback 示例

测试使用一个仍绑定相同 executable subset 的 rules variant，把 approved 的 `Ensemble Cast` 激活。
该 tag 没有 priority，也没有 tier：

```text
priority lookup -> missing
tier lookup     -> missing
default_weight  -> 1.0
```

它保持“untiered”状态；返回的 effective-weight mapping 只包含数值权重，不生成 tier metadata，
因此不会被暗中标为 `standard`。

## 9. 测试结果

```text
D1 专项测试：24 passed
完整离线测试：136 passed
失败：0
跳过：0
```

覆盖范围包括 vocabulary lineage、权重 precedence、scale invariance、no-dominance、minimum coverage
边界、容量失败、无放回重归一化、canonical output、public/context validators 和 RNG consumption。

## 10. 阶段边界

D1 没有实现 numeric year/episodes、field selection、cross-field structure、format/status、reference、
tag-group normalization、SemanticSpec assembly、DatasetRecord、realizer、distribution audit 或 production
dataset。D2 必须等待理论侧单独冻结。
