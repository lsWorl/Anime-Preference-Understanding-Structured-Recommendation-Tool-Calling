# D3. Structural Atom Contract v0.1 Review Bundle

## 审查范围

本 bundle 仅覆盖 D3 Structural Atom Contract。它定义值无关 atom、kind-specific payload validation、局部 constraint contribution，以及 direct tag ANY 与 tag-group ANY 的聚合计数规则。

## 核心源码

- `src/anime_pref/schemas/structural_atom.py`
- `src/anime_pref/sampling/structural_atom.py`
- `tests/test_structural_atom.py`
- `docs/structural_atom_contract_v0.1_IMPLEMENTATION.md`

## 冻结合同落实情况

- 支持九种冻结 atom kind。
- 明确拒绝未冻结的 `tag_group_all`。
- set atom 复用 C 的 plan validator 与 contribution。
- numeric atom 复用 D2 的 contribution/validation。
- format/status 的局部 contribution 为 1。
- tag-group ANY/NONE 的局部 contribution 为 1。
- reference contribution 为 0。
- 聚合时 direct `tag_set(any_of)` 与 `tag_group_any` 合并成一个 TAG ANY clause，总贡献固定为 1。
- direct tag NONE 保持 item-additive，tag-group NONE 保持 concept-additive。
- atom 不包含具体值，不使用 RNG，不生成 `SemanticSpec`。

## 代表性聚合结果

结构组合：

```text
GENRE all_of cardinality=2
TAG any_of cardinality=3
TAG_GROUP any
TAG_GROUP none
YEAR bounded_range
FORMAT any
STATUS any
REFERENCE
```

计数：

```text
2 + combined_TAG_ANY(1) + 1 + 2 + 1 + 1 + 0 = 8
```

## 自动测试覆盖

专项测试覆盖：

- 全部合法 kind；
- invalid kind / `tag_group_all`；
- set、numeric 和 payload shape validation；
- C/D2 真值来源复用；
- 每类 atom 的局部贡献；
- direct tag ANY、group ANY 以及二者合并；
- 多个 TAG ANY source 仍只贡献 1；
- direct tag NONE 与 group NONE additive semantics；
- reference contribution；
- mixed aggregate；
- empty sequence；
- malformed collection；
- 不携带 value、无 RNG/sample API、无 preference schema dependency。

实际运行结果：

```text
D3 专项测试：Ran 19 tests in 0.001s — OK
完整工程测试：Ran 181 tests in 0.181s — OK
compileall：通过
git diff --check：通过（仅报告已有文件的 LF/CRLF 转换提示，无 whitespace error）
skip / expectedFailure 检索：0 项
```

## 请理论侧重点确认

1. `tag_group_any` / `tag_group_none` 通过 kind 编码 operator，而本阶段不保存 group name，是否符合值无关 atom 的边界。
2. 单 atom helper 返回局部贡献、aggregate helper 独占跨 atom TAG ANY 合并，职责边界是否正确。
3. 通用聚合 helper 接受空序列并返回 0，是否符合后续 planner 需要。
4. group identity、重复 group 和组合可行性继续留给后续 structural planning/combination contract，D3 不提前限制，是否正确。

## 未实现内容

- structural planning / capacity allocation；
- categorical/numeric value binding；
- combination plausibility；
- `SemanticSpec` assembly；
- distribution audit；
- dataset generation。
