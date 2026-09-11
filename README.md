# Anime Preference Understanding & Structured Recommendation Tool Calling

一个面向动漫偏好理解数据集的 Python 工程：从 AniList 获取作品与 taxonomy，
将人工明确的偏好语义构造成可复现的结构化 Gold Query，并保存完整的数据来源信息。

## 当前能力

已实现：

- 分页采集 AniList 动画元数据，并保存 JSONL 与采集 manifest；
- 获取 AniList 全局 genre/tag taxonomy，生成 canonical 快照、SHA-256 和 manifest；
- 校验人工 tag audit，生成只包含明确批准项的 executable tag subset；
- 加载版本化 DomainRules，将 `SemanticSpec` 确定性构造成 Gold Query；
- 分离结构校验与领域校验，提供 canonical JSON 和约束结构签名；
- 构建、验证带完整 provenance 的 `DatasetRecordSpec`。

尚未实现：自然语言到 `SemanticSpec` 的自动解析、语义采样、文本生成或改写、
数据集切分、模型训练、推理服务和实际推荐执行器。当前项目是数据与契约层，
不是可直接对话推荐动漫的成品应用。

## 快速开始

要求 Python 3.10 或更高版本，业务代码仅依赖标准库。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -B -m unittest discover -s tests -v
python -B scripts/fetch_anilist.py --dry-run
```

Windows PowerShell 激活环境时使用 `.\.venv\Scripts\Activate.ps1`。未安装 editable
包也可以直接运行 `scripts/` 下的脚本；脚本会自行加入 `src` 路径。

更完整的命令、输出文件和人工审核步骤见 [快速开始](docs/quickstart.md)。

## 三条主要数据流

```text
作品采集：AniList Media -> 字段校验 -> page_*.jsonl + manifest.json

词表治理：AniList taxonomy -> source/canonical/manifest
                               -> 人工 audit -> executable subset/manifest

样本构建：SemanticSpec + DomainRules -> Gold Query
                                     -> signature/count/sample_id
                                     -> DatasetRecordSpec
```

三条流程目前不会自动串成完整训练流水线。尤其是，作品采集结果不会被
`build_query()` 自动读取，人工审核也不能由示例 audit 替代。

## 文档导航

- [文档索引](docs/README.md)：按读者目标选择入口；
- [快速开始](docs/quickstart.md)：安装、测试、三个 CLI 工作流与排错；
- [架构与模块](docs/architecture.md)：边界、数据流、目录和公开函数；
- [项目实现学习手册](docs/项目实现学习手册.md)：逐函数学习材料；
- [Schema Contract v0.1.1](docs/schema_contract_v0.1.1.md)：Gold Query 契约；
- [DatasetRecord Builder v0.1](docs/dataset_record_builder_v0.1.md)：样本身份与来源一致性；
- [Taxonomy snapshot 与 reviewed subset](docs/taxonomy_snapshot_and_subset_v0.1.md)：词表快照和审核流程。
- [Rules identity 与 DatasetRecord provenance](docs/rules_identity_and_record_provenance_v0.1.md)：
  active rules hash、subset 绑定和样本 lineage。

`docs/schema_contract_v0.1.1_review_bundle.md` 是历史审查记录，不代表当前完整状态。

## 关键约定

- `configs/data.json` 是作品采集的默认运行配置；`data.yaml` 当前不被读取。
- 当前 Gold schema 为 `0.1.1`。新的 DomainRules identity contract 已离线验证；
  production rules 配置等待真实 executable subset 后再绑定，禁止填入 synthetic hash。
- HAREM 组允许 `any_of`/`none_of`，禁止 `all_of`，并展开成三个实际 tags。
- `year` 的 1900–2100、`episodes >= 1` 是有效性边界，不是采样分布。
- approved soft preference 词表当前为空；未知表达必须明确放入
  `unresolved_preferences`，builder 不会猜测或迁移。
- canonical 输出保留 Unicode、固定键顺序，并对集合语义字段排序。
- 所有 bundle 写入均拒绝覆盖已有目标；多文件写入不是事务，失败时不会自动回滚。
- `configs/tag_audit.example.v0.1.json` 含占位 ID 与零 hash，只演示格式，不能用于正式构建。

## 验证状态

2026-09-11 使用 Python 3 运行全部 48 项单元测试，全部通过，无跳过。测试使用合成数据
和网络 mock；此次验证没有发起真实 AniList 请求，也不代表人工 taxonomy 审核已经完成。
