# 架构与模块说明

## 1. 系统边界

项目当前负责“采集与保存外部事实”和“从明确语义生成结构化训练目标”。它不负责把自然
语言自动解析成语义，也不负责使用 Gold Query 检索或排序动画。

```text
外部事实层             词表治理层                 样本契约层
AniList Media          AniList Taxonomy           SemanticSpec
      |                       |                         |
字段校验 + JSONL       canonical snapshot          DomainRules
                              |                         |
                         人工 tag audit          deterministic builder
                              |                         |
                       executable subset          Gold + provenance
```

这些层通过文件契约和版本标识关联，而不是由一个总入口自动编排。

## 2. 目录职责

| 路径 | 职责 |
|---|---|
| `configs/` | 采集配置、DomainRules、taxonomy 字段契约与 audit 格式示例 |
| `scripts/` | 三个面向操作者的命令行入口 |
| `src/anime_pref/schemas/` | 无隐式转换的 dataclass 数据形状 |
| `src/anime_pref/data/` | HTTP、校验、canonicalization、hash、构建与持久化 |
| `tests/` | 使用合成数据和 mock 验证契约，不依赖真实网络 |
| `data/raw/` | 原始作品页与 taxonomy 来源快照 |
| `data/interim/` | 后续中间产物预留 |
| `data/processed/` | 审核后的可执行词表或未来数据集 |
| `outputs/` | 训练、评估或推理输出预留 |

`training/`、`evaluation/`、`inference/` 目前只有包占位。

## 3. 核心对象

| 对象 | 含义 | 是否直接作为模型目标 |
|---|---|---|
| `AnimeMetadata` | 单部作品 API 数据的校验视图 | 否 |
| `CanonicalTaxonomySnapshot` | 可哈希的全局 genre/tag 内容快照 | 否 |
| `ExecutableTagSubset` | 人工明确批准的可执行 tag 词表 | 否 |
| `SemanticSpec` | 展开前、已经明确的 canonical 偏好语义 | 否 |
| Gold Query (`dict`) | 完整结构化查询 | 是 |
| `DatasetRecordSpec` | Gold、源 spec、文本与生成元数据的外层记录 | 仅其中 Gold 是目标 |

dataclass 的类型标注不会自动执行运行时校验。应通过对应 builder/loader 创建对象，而不是把
手工实例化成功误认为数据已经合法。

## 4. 校验分层

| 层 | 入口 | 检查内容 |
|---|---|---|
| 结构 | `validate_query_structure()` | 精确键集合、JSON 类型、重复/冲突、区间关系 |
| 领域 | `validate_query_domain()` | taxonomy allowlist、soft 词表、版本化数值边界 |
| 规范化 | `canonicalize_query()` | 固定键顺序、集合语义字段排序、复制为新对象 |
| 记录一致性 | `validate_dataset_record()` | 从来源重算 Gold、签名、计数、规则 ID 与 sample ID |

结构合法不等于领域合法；canonicalization 也不是清洗器。首尾空白、重复值或未知词不会被
静默修复。

## 5. 主要公开接口

### 作品采集

- `fetch_anime_page(page, per_page, endpoint=..., timeout_seconds=...)`
- `AnimeMetadata.from_api(media)`
- `write_jsonl(records, path)` / `write_manifest(manifest, path)`

### Taxonomy 与审核子集

- `fetch_anilist_taxonomy(...)`
- `build_canonical_taxonomy_snapshot(source_payload)`
- `load_canonical_taxonomy_snapshot(path)`
- `taxonomy_snapshot_sha256(snapshot)`
- `write_taxonomy_snapshot_bundle(...)`
- `load_tag_audit(path)` / `validate_tag_audit(records, snapshot)`
- `build_executable_tag_subset(...)`
- `load_executable_tag_subset(path)`
- `validate_domain_rule_tag_targets(subset, rules)`
- `write_executable_subset_bundle(...)`

### Gold 与 DatasetRecord

- `load_domain_rules(path)`
- `build_query(spec, rules)` / `dumps_query(query)`
- `validate_query_structure(query)` / `validate_query_domain(query, rules)`
- `build_constraint_signature(query)`
- `build_dataset_record(...)` / `validate_dataset_record(record, rules)`

精确参数、返回值与异常边界见各契约文档及源码 docstring。

## 6. 可复现性与来源追踪

- taxonomy hash 来自 compact canonical JSON 的 UTF-8 字节，不来自 HTTP 原始字节；
- subset 有自己的 hash，同时记录来源 snapshot hash；
- Gold canonical JSON 固定键序，并排序集合语义字段；
- sample ID 由 canonical 源 spec、Gold 和生成元数据共同决定；
- constraint signature 只表示哪些硬约束槽位被使用，不编码具体值；
- constraint count 按 tag group 展开前的用户语义子句计数。

哈希和 sample ID 用于内容身份与一致性，不是加密签名或真实性证明。

## 7. 版本关系

| 标识 | 管理对象 |
|---|---|
| `schema_version` | Gold Query 与 DomainRules 契约 |
| `snapshot_schema_version` | taxonomy canonical 字段与排序契约 |
| `canonical_sha256` | 某次 canonical taxonomy 的内容身份 |
| `subset_version` / `subset_hash` | 人工批准词表的版本与内容身份 |
| `dataset_version` | DatasetRecord 所属数据集版本 |

这些标识不可互换。修改进入 canonical hash 的字段、排序或序列化规则时，即使业务名称不变，
也会改变内容身份，应同步更新测试和文档。
