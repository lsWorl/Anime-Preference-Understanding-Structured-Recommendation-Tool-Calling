# D3. Structural Atom Contract v0.1 实现说明

## 1. 本阶段实现目标

D3 定义位于“结构规划”和具体 `SemanticSpec` 之间的值无关结构原子。它只表达某种约束槽位需要什么结构，不选择 genre、tag、年份或集数等实际值，也不使用随机数。

本阶段支持九种原子：

| kind | payload | 局部 hard constraint contribution |
|---|---|---:|
| `genre_set` | `operator_plan` | 复用 C 的 `constraint_contribution()` |
| `tag_set` | `operator_plan` | 复用 C 的 `constraint_contribution()` |
| `year_range` | `range_pattern` | 复用 D2 的 `numeric_constraint_contribution()` |
| `episodes_range` | `range_pattern` | 复用 D2 的 `numeric_constraint_contribution()` |
| `format_any` | 无 | 1 |
| `status_any` | 无 | 1 |
| `tag_group_any` | 无 | 1 |
| `tag_group_none` | 无 | 1 |
| `reference` | 无 | 0 |

`tag_group_all` 不属于冻结合同，因此验证器会拒绝该 kind。

## 2. 文件职责

- `src/anime_pref/schemas/structural_atom.py`
  - 定义合法 kind 的字面量类型 `StructuralAtomKind`。
  - 定义不可变数据对象 `StructuralAtom`。
- `src/anime_pref/sampling/structural_atom.py`
  - 定义 atom kind 分类常量。
  - 验证 kind 与 payload 的组合。
  - 计算单个 atom 的局部贡献。
  - 计算 atom 序列的最终结构约束数，并处理 TAG ANY 合并语义。
- `tests/test_structural_atom.py`
  - 覆盖全部合法/非法结构、贡献规则、跨 atom 合并规则和阶段边界。

## 3. 数据结构

```python
@dataclass(frozen=True)
class StructuralAtom:
    kind: StructuralAtomKind
    operator_plan: OperatorCardinalityPlan | None = None
    range_pattern: NumericRangePattern | None = None
```

对象只保存结构信息：

- set atom 使用 `operator_plan`，其中包含 operator 与 cardinality；
- numeric atom 使用 `range_pattern`，例如 `min_only`、`max_only` 或 `bounded_range`；
- format、status、tag group 和 reference 不携带 payload；
- 对象中没有任何 genre/tag 字符串或数值 bound。

## 4. 核心函数

### `validate_structural_atom(atom)`

公开验证入口。处理顺序如下：

1. 确认输入确实是 `StructuralAtom`。
2. 确认 `kind` 属于冻结的九种 kind。
3. `genre_set` / `tag_set` 必须且只能携带 `operator_plan`，并调用 C 阶段验证器。
4. `year_range` / `episodes_range` 必须且只能携带 `range_pattern`，并通过 D2 的贡献函数验证 pattern。
5. 其余 atom 禁止携带两个 payload 中的任何一个。

验证失败时直接抛出异常，不静默修复 malformed atom。

### `structural_atom_contribution(atom)`

先调用公共验证器，再计算单个 atom 的局部贡献：

- direct set 的规则完全委托给 C；
- numeric range 的规则完全委托给 D2；
- format/status/group atom 返回 1；
- reference 返回 0。

这个函数返回的是局部贡献。`tag_set(any_of)` 与 `tag_group_any` 的跨 atom 合并只能由聚合函数完成。

### `structural_constraint_count(atoms)`

计算整个 atom 序列的 hard semantic clause 数量。

遍历时，所有 `tag_set` 且 operator 为 `any_of` 的 atom，以及所有 `tag_group_any`，只设置同一个 `has_combined_tag_any` 标志。它们不会分别累计。遍历结束后，如果标志为真，统一加 1。

其余 atom 使用各自的局部贡献正常相加。这样保持冻结语义：direct tag ANY 与 approved tag-group ANY 最终属于同一个 TAG ANY OR clause。

## 5. 完整调用流程示例

以下输入只包含结构，不包含具体分类值：

```python
atoms = (
    StructuralAtom(
        kind="genre_set",
        operator_plan=OperatorCardinalityPlan("all_of", 2),
    ),
    StructuralAtom(
        kind="tag_set",
        operator_plan=OperatorCardinalityPlan("any_of", 3),
    ),
    StructuralAtom(kind="tag_group_any"),
    StructuralAtom(kind="tag_group_none"),
    StructuralAtom(kind="year_range", range_pattern="bounded_range"),
    StructuralAtom(kind="format_any"),
    StructuralAtom(kind="status_any"),
    StructuralAtom(kind="reference"),
)

count = structural_constraint_count(atoms)
```

代码路径和累计结果：

1. `structural_constraint_count()` 接收 tuple，并逐个调用 `validate_structural_atom()`。
2. `genre_set(all_of, cardinality=2)` 调用 C 的贡献函数，贡献 2，累计为 2。
3. `tag_set(any_of, cardinality=3)` 参与最终 TAG ANY，先只设置合并标志，累计仍为 2。
4. `tag_group_any` 也参与同一个 TAG ANY，不额外增加，累计仍为 2。
5. `tag_group_none` 是一个独立 normalization concept，贡献 1，累计为 3。
6. `year_range(bounded_range)` 调用 D2 的贡献函数，min/max 两个 bound 贡献 2，累计为 5。
7. `format_any` 是一个 OR clause，贡献 1，累计为 6。
8. `status_any` 是一个 OR clause，贡献 1，累计为 7。
9. `reference` 不计 hard constraint，贡献 0。
10. 遍历结束后，合并后的 TAG ANY clause 统一贡献 1，最终结果为 **8**。

### TAG NONE 示例

```python
atoms = (
    StructuralAtom(
        kind="tag_set",
        operator_plan=OperatorCardinalityPlan("none_of", 2),
    ),
    StructuralAtom(kind="tag_group_none"),
)
```

direct `none_of` 中两个 independent exclusion 贡献 2，group exclusion 表达一个用户概念并贡献 1，最终为 **3**。这里不执行 TAG ANY 的合并规则。

### Reference-only 示例

```python
structural_constraint_count((StructuralAtom(kind="reference"),))
# 0
```

reference 可以参与 semantic family，但不计 hard constraint。

## 6. 与前序阶段的合同关系

D3 不重新定义 operator/cardinality 或 numeric pattern 的计数逻辑：

- C 是 direct set contribution 的唯一真值来源；
- D2 是 numeric range contribution 的唯一真值来源；
- D3 只增加 atom payload 合法性，以及跨 atom 的 TAG ANY 合并语义。

这避免同一计数规则在不同模块中出现多份实现并逐渐漂移。

## 7. 阶段边界

本模块没有：

- RNG 或 weighted sampling；
- structural planner；
- genre/tag/numeric 具体值；
- `SemanticSpec` 或 `DatasetRecord` 构造；
- soft/unresolved preference；
- E～G 阶段逻辑。

