# Full AniList Taxonomy Snapshot + Reviewed Executable Tag Subset

> 状态核对（2026-09-10）：snapshot、audit、subset、hash、bundle 写入与两个 CLI
> 均已实现。13 项 taxonomy 单元测试全部通过；测试使用 mock 和合成数据，本次核验未执行
> 真实网络采集，也不代表正式人工审核已经完成。

本工作块只建立外部 taxonomy 的可追溯快照，以及经过人工审核后允许进入 Gold Query 的 tag 子集。它不生成 SemanticSpec、自然语言样本或数据集划分。

## 文件职责

- `src/anime_pref/data/taxonomy_client.py`：获取 AniList 的 `GenreCollection` 与 `MediaTagCollection` 原始响应，不排序、不裁剪。
- `src/anime_pref/schemas/taxonomy.py`：定义 canonical snapshot、audit record、executable subset 及两个 manifest 的不可变数据结构。
- `src/anime_pref/data/taxonomy_snapshot.py`：校验和规范化 source payload，生成稳定 JSON、SHA-256、manifest，并保存 snapshot bundle。
- `src/anime_pref/data/tag_subset.py`：读取人工审核记录，校验其与 snapshot 的 ID/name/provenance 一致性，只提取明确批准的 tags，并验证 `DomainRules`。
- `scripts/fetch_anilist_taxonomy.py`：真实采集入口。
- `scripts/build_executable_tag_subset.py`：从 canonical snapshot 和人工 audit 构建 executable subset。
- `configs/taxonomy_snapshot.v0.1.json`：记录 snapshot schema 允许进入 canonical hash 的字段。
- `configs/tag_audit.example.v0.1.json`：仅演示 audit 文件形状。文件内 ID、category 和零 hash 都是测试占位值，不能作为真实审核结果或直接用于构建正式 subset。
- `tests/test_taxonomy_snapshot.py`：使用合成数据验证 fetch、canonicalization/hash、manifest、audit、subset 和 domain rules 的契约，不依赖网络。

## 数据流与边界

```text
AniList GraphQL response
        |
        +--> source.json                 原始来源记录
        |
        +--> canonical.json              只含 contract 字段、稳定排序
                 |
                 +--> canonical SHA-256
                 +--> manifest.json      获取时间、数量与 snapshot identity
                 |
                 +--> human audit JSON   每个记录明确 approved=true/false
                              |
                              +--> executable_tags.json
                              +--> manifest.json
```

四类版本各自负责不同内容：

- `schema_version`：模型 Gold JSON 的结构版本。
- `snapshot_schema_version` 与 `canonical_sha256`：snapshot 的字段契约与具体 AniList taxonomy 内容。
- `subset_version` 与 `subset_hash`：项目批准的 executable tag vocabulary。
- `dataset_version`：以后生成的数据集版本。

这些版本不能互相替代。`fetched_at_utc` 属于 manifest，不进入 taxonomy content hash。因此相同 canonical 内容在不同时间抓取时 hash 相同；任何纳入 contract 的字段变化都会改变 hash。

## 已实现接口

| 阶段 | 接口 | 行为摘要 |
|---|---|---|
| 获取 | `fetch_anilist_taxonomy` | POST GraphQL，校验 HTTP/JSON/errors/resource，返回完整 decoded response |
| 规范化 | `build_canonical_taxonomy_snapshot` | 严格筛选字段，拒绝重复身份，genres 与 tags 稳定排序 |
| 序列化 | `canonical_taxonomy_to_mapping` / `dumps_canonical_taxonomy` | 固定形状、Unicode compact JSON |
| 身份 | `taxonomy_snapshot_sha256` | 对 canonical UTF-8 JSON 计算 SHA-256 |
| 读取 | `load_canonical_taxonomy_snapshot` | 拒绝重复 JSON key、错误键序和非 canonical 内容 |
| 快照落盘 | `write_taxonomy_snapshot_bundle` | 预检冲突后写 `source.json`、`canonical.json`、`manifest.json` |
| 审核读取 | `load_tag_audit` | 严格读取显式审核记录，不为缺失项补默认批准 |
| 审核校验 | `validate_tag_audit` | 核对 snapshot hash、tag 身份、flags 和 alias 冲突 |
| 子集构建 | `build_executable_tag_subset` | 只提取 `approved is True` 的记录并 canonical sort |
| 子集读写 | `load_executable_tag_subset` / `write_executable_subset_bundle` | 严格读取；写 subset 与 manifest，禁止覆盖 |
| 规则联动 | `validate_domain_rule_tag_targets` | group targets ⊆ active rules tags ⊆ approved subset tags |

两个脚本已经连接这些接口：

```bash
python -B scripts/fetch_anilist_taxonomy.py --output data/raw/taxonomy-run-001

python -B scripts/build_executable_tag_subset.py \
  --canonical-snapshot data/raw/taxonomy-run-001/canonical.json \
  --audit configs/tag_audit.reviewed.v0.1.json \
  --subset-version reviewed-tags-v0.1 \
  --domain-rules configs/domain_rules.v0.1.1.json \
  --output data/processed/executable-tags-v0.1
```

完整操作步骤见 [快速开始](quickstart.md)。

## 人工审核规则

完整 `MediaTagCollection` 只进入 snapshot，不自动进入 executable vocabulary。一个 tag 只有在 audit 中存在记录且 `approved` 严格为 `true` 时才能进入 subset；遗漏记录等价于尚未审核，并不会得到默认批准。

审核时需要逐项核对 tag ID、name、category、spoiler/adult flags 和 source snapshot hash。`reason` 应写出批准或拒绝的领域理由。`aliases` 只填写经过审核的 normalization aliases，并拒绝 aliases 相互重复、与其他 approved tag 的 alias 冲突或与 canonical tag name 冲突。

当前已冻结的 HAREM group 要求 `Female Harem`、`Male Harem`、`Mixed Gender Harem` 三个真实 snapshot 条目全部进入 approved subset。其他 tags 是否批准仍需人工与理论侧共同审核。

## 测试与运行边界

`tests/test_taxonomy_snapshot.py` 的13项测试均已启用，覆盖查询字段、fetch 成功与 GraphQL
错误、输入顺序无关的 canonical/subset hash、canonical 字段边界、manifest/bundle、严格
audit loader、duplicate identity、approved subset、禁止覆盖以及 DomainRules 联动。真实网络
调用不进入单元测试；fetch 测试通过 mock 提供固定响应。

所有 bundle writer 都会先检查目标文件是否存在，并用独占创建模式防止覆盖。不过多文件
写入不是事务：若写入中途发生磁盘错误，已创建的文件不会自动回滚。两个 taxonomy CLI
目前让异常直接传播并以非零状态退出，不提供重试、断点续传或自动清理。

正式 review bundle 仍应包含实际 snapshot manifest、canonical taxonomy 节选、真实 audit
节选、subset manifest/hash、完整测试输出，以及尚待领域确认的 tag selection 边界。
