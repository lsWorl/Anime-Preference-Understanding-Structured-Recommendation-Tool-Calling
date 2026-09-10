# 项目文档索引

文档按“使用 → 理解 → 契约/历史”的顺序组织。

## 开始使用

- [快速开始](quickstart.md)：环境、测试、作品采集、taxonomy 快照和审核子集命令。
- [项目根 README](../README.md)：能力范围、关键约定和最短运行路径。

## 理解实现

- [架构与模块](architecture.md)：三条数据流、模块职责、公开接口和边界。
- [项目实现学习手册](项目实现学习手册.md)：适合按源码逐函数学习的长篇说明。

## 数据契约

- [Schema Contract v0.1.1](schema_contract_v0.1.1.md)：`SemanticSpec`、Gold Query、
  canonicalization 和领域校验。
- [DatasetRecord Builder v0.1](dataset_record_builder_v0.1.md)：约束计数、规则来源、
  确定性 sample ID 和记录一致性。
- [Taxonomy snapshot 与 reviewed subset](taxonomy_snapshot_and_subset_v0.1.md)：
  外部词表快照、人工审核、内容哈希和 executable vocabulary。

## 历史材料

- [Schema Contract v0.1.1 Review Bundle](schema_contract_v0.1.1_review_bundle.md)：
  某一审查阶段的快照，仅供追溯；状态和测试数量以根 README 为准。

## 文档维护规则

- 能力状态以可执行代码和未跳过的测试为准。
- CLI、输出文件名或配置键变化时，同步更新根 README 与快速开始。
- schema、canonicalization 或 hash 输入变化时，必须同步更新对应契约文档和测试。
- 历史 review bundle 保留原貌，不用它覆盖当前状态文档。
