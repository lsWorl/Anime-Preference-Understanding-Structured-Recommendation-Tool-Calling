# D4. Structural Pattern Eligibility Contract v0.1 实现报告

## 1. 本阶段解决的问题

D4 接收 B 阶段已经确定的 `FamilyComplexityPlan`，枚举该 family 与 complexity bucket 下所有合法的值无关结构模式：

```text
FamilyComplexityPlan
        ↓
冻结的 atom slot 与 payload 变体
        ↓
canonical StructuralPatternPlan candidates
```

D4 只回答“哪些抽象结构符合合同”。它不从候选中选择一个，也不声明候选之间的概率。

## 2. 新增和修改的文件

- `src/anime_pref/schemas/structural_pattern.py`
  - 定义不可变输出对象 `StructuralPatternPlan`。
- `src/anime_pref/sampling/structural_pattern.py`
  - canonical order key；
  - complexity bucket matching；
  - slot uniqueness；
  - family-specific eligibility；
  - public validation；
  - finite deterministic enumeration。
- `src/anime_pref/sampling/config.py`
  - 新增 `NUMERIC_RANGE_PATTERN_ORDER`；
  - `NUMERIC_RANGE_PATTERNS` 从该顺序派生，统一 Phase A/D2/D4 的 canonical mechanics order。
- `tests/test_structural_pattern.py`
  - D4 合同验收测试。

## 3. 输出对象

```python
@dataclass(frozen=True)
class StructuralPatternPlan:
    semantic_family: SemanticFamily
    complexity_bucket: ComplexityBucket
    atoms: tuple[StructuralAtom, ...]
```

`atoms` 已经是 canonical tuple，但仍然不携带：

- genre/tag values；
- year/episode endpoints；
- group name；
- reference title；
- probability/weight；
- `SemanticSpec` 或 `DatasetRecord`。

exact hard constraint count 不冗余保存，而是随时通过 D3 的 `structural_constraint_count(atoms)` 推导。

## 4. Canonical mechanics order

第一排序键复用 D3：

```text
genre_set
tag_set
year_range
episodes_range
format_any
status_any
tag_group_any
tag_group_none
reference
```

set atom 的 payload 顺序为：

```text
operator: all_of → any_of → none_of
cardinality: 使用对应 operator 的 OPERATOR_CARDINALITY_ORDER
```

numeric pattern 顺序为：

```text
min_only → max_only → bounded_range
```

该顺序只服务 deterministic enumeration 和 candidate identity，不表示语义优先级或概率。

## 5. 核心函数

### `_atom_sort_key(atom)`

先调用 D3 validator，再将 atom 映射为：

```text
(kind index, operator/range index, cardinality index)
```

公共 validator 用它检测调用方是否已经提供 canonical tuple。validator 不会静默排序。

### `_matches_complexity_bucket(count, bucket)`

把 D3 得到的 exact count 与 B bucket 匹配：

- `0`、`1`、`2`、`3`、`4` 必须 exact match；
- `5_plus` 接受所有 `count >= 5`。

D4 因此第一次能在一个具体 structural pattern 上得到 exact count，但不会把 `5_plus` 改写为 5。

### `_validate_slot_uniqueness(atoms)`

每种 D3 atom kind 在 D4 中最多出现一次。它同时落实：

- direct schema slot uniqueness；
- reference 最多一个；
- `tag_group_any` 最多一个 slot；
- `tag_group_none` 最多一个 slot。

后续 assembly 不需要合并重复结构槽位。

### `_validate_family_rules(plan, count)`

实现 family-specific contract：

- `single_constraint`：一个 contribution=1 的 direct hard atom；
- `same_field_logic`：一个 genre/tag set atom；
- `cross_field_composition`：至少两个不同 direct hard fields，无 reference/group；
- `normalization`：至少一个 group atom，可以带 direct hard atoms/reference；
- `reference_only`：严格等于 `(reference,)`；
- `reference_composition`：一个 reference 加至少一个 direct hard atom，无 group。

这也落实 family priority：含 group 只能归 normalization；无 group但含 reference 只能归 reference family。

### `validate_structural_pattern_plan(plan)`

公共验证调用流程：

1. 检查 `StructuralPatternPlan` 类型。
2. 重建并验证 `FamilyComplexityPlan`，复用 B 合同。
3. 要求 `atoms` 是 tuple。
4. 对每个 atom 调用 D3 public validator。
5. 检查 canonical order，不执行修复。
6. 检查每种结构 slot 唯一。
7. 用 D3 聚合规则得到 exact count。
8. 匹配 B complexity bucket。
9. 验证 family-specific rules 与 priority。

### `_variants_for_kind(kind)`

生成一个 slot 的有限 mechanics 变体：

- genre/tag set：C 冻结的 operator/cardinality 组合；
- year/episodes：三个冻结 range patterns；
- 其余 slot：一个 payload-free atom。

它不生成任何具体 domain value。

### `_enumerate_canonical_atom_tuples()`

每个 schema slot 都有：

```text
unused (None) + frozen payload variants
```

函数按 canonical kind order 对这些有限选项做 Cartesian enumeration，并移除 `None`。因为每个 kind 只有一个 slot，产出的 tuple 天然满足 kind order 与 multiplicity 上限。

### `enumerate_eligible_structural_patterns(family_complexity_plan)`

1. 先验证 B plan。
2. 遍历有限 canonical atom tuple。
3. 构造 `StructuralPatternPlan`。
4. 使用同一个 public validator 筛选。
5. 通过 hashable frozen plan 去重。
6. 按 deterministic enumeration order 返回 tuple。

若没有候选，返回 `()`。函数不消费 RNG；后续 orchestrator 再决定 zero capacity 如何处理。

## 6. 完整参数调用示例

输入：

```python
family_plan = FamilyComplexityPlan(
    semantic_family="normalization",
    complexity_bucket="2",
)

candidates = enumerate_eligible_structural_patterns(family_plan)
```

调用路径：

```text
enumerate_eligible_structural_patterns
→ validate_family_complexity_plan
→ _enumerate_canonical_atom_tuples
→ StructuralPatternPlan(...)
→ validate_structural_pattern_plan
   → D3 validate_structural_atom（逐 atom）
   → canonical order / slot uniqueness
   → D3 structural_constraint_count
   → complexity bucket match
   → normalization family rule
→ deduplicate
→ tuple[candidates]
```

其中一个合法候选可以是：

```python
StructuralPatternPlan(
    semantic_family="normalization",
    complexity_bucket="2",
    atoms=(
        StructuralAtom(
            kind="genre_set",
            operator_plan=OperatorCardinalityPlan("all_of", 1),
        ),
        StructuralAtom(kind="tag_group_none"),
        StructuralAtom(kind="reference"),
    ),
)
```

逐步验证：

1. `normalization/2` 是 B 阶段合法 pair。
2. atom 顺序为 genre → group-none → reference，符合 D3 kind order。
3. 三种 kind 各占一个 slot。
4. genre `all_of/1` 通过 C 合同，贡献 1。
5. group-none 是一个 normalization concept，贡献 1。
6. reference 贡献 0。
7. D3 exact count 为 `1 + 1 + 0 = 2`，匹配 bucket `2`。
8. pattern 含 group atom，因此满足 normalization family；reference 不改变 hard count。

此候选仍没有决定 genre 是什么、group 是什么、reference title 是什么。

## 7. TAG ANY 聚合示例

```python
StructuralPatternPlan(
    semantic_family="normalization",
    complexity_bucket="1",
    atoms=(
        StructuralAtom(
            "tag_set",
            operator_plan=OperatorCardinalityPlan("any_of", 3),
        ),
        StructuralAtom("tag_group_any"),
    ),
)
```

D3 将 direct tag ANY 与 group ANY 合并为同一个最终 TAG ANY OR clause，因此 exact count 为 1。D4 复用该结果，不把两个 atom 错算成 complexity 2。

## 8. `5_plus` 示例

```python
StructuralPatternPlan(
    semantic_family="cross_field_composition",
    complexity_bucket="5_plus",
    atoms=(
        StructuralAtom(
            "genre_set",
            operator_plan=OperatorCardinalityPlan("all_of", 3),
        ),
        StructuralAtom(
            "tag_set",
            operator_plan=OperatorCardinalityPlan("all_of", 3),
        ),
    ),
)
```

两个不同 direct fields 满足 cross-field；D3 exact count 是 6，所以它属于 `5_plus`。专项测试也确认枚举空间含 count 6、7 以及更高的候选。

## 9. 实际候选空间

当前冻结 mechanics 得到：

| family / bucket | candidates | observed exact counts |
|---|---:|---|
| single_constraint / 1 | 14 | 1 |
| same_field_logic / 1 | 8 | 1 |
| same_field_logic / 2 | 4 | 2 |
| same_field_logic / 3 | 2 | 3 |
| cross_field_composition / 2 | 77 | 2 |
| cross_field_composition / 3 | 276 | 3 |
| cross_field_composition / 4 | 595 | 4 |
| cross_field_composition / 5_plus | 3125 | 5–12 |
| normalization / 1 | 8 | 1 |
| normalization / 2 | 98 | 2 |
| normalization / 3 | 520 | 3 |
| normalization / 4 | 1610 | 4 |
| normalization / 5_plus | 22340 | 5–14 |
| reference_only / 0 | 1 | 0 |
| reference_composition / 1 | 14 | 1 |
| reference_composition / 2 | 83 | 2 |
| reference_composition / 3 | 278 | 3 |
| reference_composition / 4 | 595 | 4 |
| reference_composition / 5_plus | 3125 | 5–12 |

这些数量只是 candidate-space cardinality。它们不构成概率，后续不得据此默认 uniform sampling。

## 10. 重要边界

```text
structurally eligible
≠ domain-bindable
≠ catalog-plausible
```

例如 `tag_group_any + tag_group_none` 在 D4 可以合法，因为它表示两个抽象 slots。当前规则是否存在两个不冲突的实际 groups，留给后续 domain/combination feasibility。

D4 没有调用 D1/D2 value sampler，没有绑定 HAREM、format/status、numeric endpoint 或 reference title，也没有实现 pattern weights、uniform/random selection、SemanticSpec assembly、distribution audit 或 production generation。

