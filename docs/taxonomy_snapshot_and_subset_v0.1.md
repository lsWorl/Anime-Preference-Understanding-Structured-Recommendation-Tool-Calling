# Full AniList Taxonomy Snapshot + Reviewed Executable Tag Subset

> 状态核对（2026-09-09）：当前业务函数仍为 NotImplementedError 骨架；两个 CLI 仅 parse_args 已实现。测试有1项查询常量检查通过、6项待实现测试跳过。以下数据流和函数职责描述目标契约，不能据此判断真实采集或审核已完成。

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

## TODO 实现顺序

1. `TODO-26`：获取并保留完整 GraphQL source response，然后启用 `TODO-40a` 测试。
2. `TODO-27`：严格构造 canonical snapshot。先只完成这一项并运行测试；此时 hash 测试仍保持 skip。
3. `TODO-28a`～`TODO-28d`：canonical mapping、serialization、loader 与 SHA-256，然后启用 `TODO-40b`。
4. `TODO-29`～`TODO-30`：snapshot manifest 与不可覆盖写入，然后启用 `TODO-40c`。
5. 完成一次真实小规模 taxonomy fetch，再从 canonical snapshot 创建真实 audit 文件。不要复制 example 文件中的占位 ID/hash。
6. `TODO-31`～`TODO-32`：audit loader 与 snapshot identity validation，然后启用 `TODO-40d`。
7. `TODO-33`～`TODO-35`：approved subset、canonical serialization/hash 与 manifest，然后启用 `TODO-40e`。
8. `TODO-36`：要求 subset tag names 与 `DomainRules.tags` 相等，并要求所有 tag group targets 存在，然后启用 `TODO-40f`。HAREM 通过配置内容验证，不写名称特例。
9. `TODO-37`～`TODO-39`：两个 bundle 写入和两个 CLI 的连接代码。

## 人工审核规则

完整 `MediaTagCollection` 只进入 snapshot，不自动进入 executable vocabulary。一个 tag 只有在 audit 中存在记录且 `approved` 严格为 `true` 时才能进入 subset；遗漏记录等价于尚未审核，并不会得到默认批准。

审核时需要逐项核对 tag ID、name、category、spoiler/adult flags 和 source snapshot hash。`reason` 应写出批准或拒绝的领域理由。`aliases` 只填写经过审核的 normalization aliases，并拒绝 aliases 相互重复、与其他 approved tag 的 alias 冲突或与 canonical tag name 冲突。

当前已冻结的 HAREM group 要求 `Female Harem`、`Male Harem`、`Mixed Gender Harem` 三个真实 snapshot 条目全部进入 approved subset。其他 tags 是否批准仍需人工与理论侧共同审核。

## 当前测试策略

测试文件先保留 skip 标记，使未实现 TODO 的骨架不会伪装成已完成。完成一组 TODO 后，删除对应测试的 `@unittest.skip` 并运行完整测试。真实网络调用不放入单元测试；fetch 测试通过 mock 固定 GraphQL 成功与错误响应。

完成全部 TODO 后再生成 `REVIEW.md`。Review bundle 应包含实际 snapshot manifest、canonical taxonomy 节选、真实 audit 节选、subset manifest/hash、核心源码、完整测试输出，以及仍需理论侧确认的 tag selection 边界。

