# Anime Preference Understanding & Structured Recommendation Tool Calling

当前工程实现：作品元数据采集、Schema Contract v0.1.1、确定性 Gold Query 构建、
结构/领域校验分层，以及 DatasetRecord 构建与来源一致性验证。

全量 taxonomy 快照与审核子集目前已添加数据模型、接口和测试骨架，业务函数仍待实现。
尚未实现语义采样、语言生成、数据集切分、训练或推荐执行。

## 阅读入口

从 [项目实现学习手册](docs/项目实现学习手册.md) 开始，按数据流逐个阅读源码。
手册包含函数参数与返回值、内部校验、异常、调用关系、离线示例和测试说明。

- [Schema Contract v0.1.1](docs/schema_contract_v0.1.1.md)：Gold 契约与 canonicalization。
- [DatasetRecord Builder](docs/dataset_record_builder_v0.1.md)：来源、子句计数和确定性身份。
- [Taxonomy snapshot 与 reviewed subset](docs/taxonomy_snapshot_and_subset_v0.1.md)：待实现契约。
- [历史 review bundle](docs/schema_contract_v0.1.1_review_bundle.md)：保留当时审查内容，不代表最新状态。

## 环境与运行

Python >= 3.10，业务代码仅使用标准库；运行配置为 JSON，无需 YAML/Pydantic。
从项目根目录执行：

```powershell
python -B scripts/fetch_anilist.py --dry-run
python -B -m unittest discover -s tests -v
```

可选创建虚拟环境，之后把 python 换成 .\.venv\Scripts\python.exe。
脚本已设置 src 路径；其他程序导入可选择 pip install -e . 或显式设置 src 路径。

截至 2026-09-09：37 项测试，31 项通过，6 项 taxonomy 测试仍跳过。
跳过不表示实现完成；源码中的 NotImplementedError 和 skip 才能判断剩余工作，
历史 TODO 编号本身可能留作学习记录。

## 作品采集

真实采集会联网并创建文件，使用尚未存在的输出文件路径：

```powershell
python -B scripts/fetch_anilist.py --pages 1 --per-page 10 --output data/raw/anilist-new-run
```

默认 configs/data.json，CLI 覆盖同名配置。输出相对路径基于项目根目录，
自定义 --config 相对路径基于工作目录。data.yaml 不被读取。
成功返回 0；已捕获运行错误返回 1；学习骨架异常返回 2；argparse 独立处理参数错误。
dry-run 不联网、不写缓存。独占创建禁止覆盖，失败不自动回滚已写页面。

## 当前数据约定

- AnimeMetadata 是校验视图；data/raw 保存 API 原始 Media，一页一个 JSONL。
- DomainRules 使用 configs/domain_rules.v0.1.1.json；旧 v0.1 文件保留为历史材料。
- HAREM 允许 any_of/none_of，禁止 all_of；展开为三个实际 tags。
- year 为 1900–2100 有效性边界，episodes 至少 1；不是采样分布。
- soft_preferences 批准词表为空；未知表达不能由 builder 自动映射或搬移。
- DatasetRecord 保存源 spec、Gold 和生成元数据；模型目标仍只是 Gold Query。
- taxonomy audit 示例包含占位数据，不能作为正式批准记录。
- data/interim、data/processed、outputs 和 training/evaluation/inference 仍为后续模块预留。

本分支侧重代码复盘与注释；新增语义政策应先在理论分支确认。

