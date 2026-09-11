# Executable Rules Identity + DatasetRecord Provenance Integration v0.1

> 状态核对（2026-09-11）：本工作块已实现。完整离线测试共 48 项，全部通过且无跳过。
> Production taxonomy/rules acceptance 继续 deferred。

本工作块为 executable rules 建立独立、可重算的内容身份，并把 rules/subset lineage 写入 DatasetRecord。它不实现 semantic sampler、自然语言生成、数据切分或训练。

## 文件职责

- `src/anime_pref/data/query_builder.py`：扩展 `DomainRules` 数据结构和配置加载契约。配置声明 rules/subset version 与 subset hash；`rules_hash` 由程序计算。
- `src/anime_pref/data/rules_identity.py`：生成 canonical rules document、稳定序列化、SHA-256，并将 rules 绑定到实际 executable subset。
- `src/anime_pref/data/tag_subset.py`：验证 `tag_group members ⊆ DomainRules.tags ⊆ approved subset tags`。
- `src/anime_pref/schemas/dataset_record.py`：在 Gold JSON 外保存 subset version/hash 与 rules version/hash。
- `src/anime_pref/data/dataset_record_builder.py`：构建及验证 DatasetRecord 时核对实际 rules/subset，并把四个 identity 纳入 sample ID。
- `tests/test_rules_identity_and_record_provenance.py`：使用明确标记的 synthetic 数据执行离线 contract 验收；其中的 identity 禁止进入 production 配置。

## 版本与 lineage

```text
DatasetRecord
  ├── schema_version                 Gold JSON structure
  ├── dataset_version                dataset release
  ├── rules_version / rules_hash     active executable rules
  └── subset_version / subset_hash   approved tag pool
                      |
                      └── subset manifest.derived_from_snapshot_hash
                                      |
                                      └── AniList taxonomy snapshot
```

DatasetRecord 暂不重复保存 taxonomy snapshot hash。`sample_id` 继续表示完整 DatasetRecord identity；它包含四个新增 identity，因此 rules 或 subset identity 改变时 sample ID 也改变。它仍不承担 semantic dedup 或 semantic fingerprint 的职责。

## Canonical rules document

被 hash 的文档完整包含：

- `rules_version`
- `schema_version`
- `executable_subset_version`
- `executable_subset_hash`
- active genres、tags、formats、statuses、soft preferences
- tag group members、allowed operators、normalization rule ID
- episodes/year numeric rules

所有集合语义值和 group names 使用稳定排序，JSON 使用 compact Unicode serialization 和 UTF-8。`rules_hash` 不进入文档本身，从而避免自引用。输入 JSON 的缩进、键顺序和集合列表顺序不改变 hash；以上 contract 字段的真实变化必须改变 hash。

## Tag approval policy v0.1

- `is_adult=true` 不允许进入 executable subset。
- `is_general_spoiler=true` 默认不允许进入 executable subset。
- category 仅作为 review signal 或 pre-filter，不能据此自动批准整个 category。
- 每个 tag 必须存在显式人工审核记录且 `approved=true` 才能进入 subset。
- 优先审核 sampler v0.x 确实需要的最小 tag 集合，不一次批准完整 AniList taxonomy。

Alias 必须是 canonical concept 的稳定语义等价表达或领域称呼，不能扩大或缩小概念。Alias 本身不携带 polarity，例如保存“后宫”，不能保存“不要后宫”；正负语义由 `any_of`、`none_of` 等 operator 表达。含义有歧义的 alias 默认不映射，同一 alias 默认不能指向多个 active concept。Aliases 属于 subset canonical contract，任何变化都会改变 subset hash。

以上 policy 应在 `validate_tag_audit` 或 subset 构建入口形成可执行检查：即使人工错误地将 adult/general-spoiler tag 标为 approved，builder 也必须拒绝，而不能生成 subset。

## 已完成的实现顺序

1. 把 subset/rules 关系由 exact equality 改为包含关系。
2. 扩展 `DomainRules` 和 loader；离线测试只使用 synthetic rules/subset fixture。
3. 实现 canonical rules mapping、serialization 与 hash。
4. 结合实际 subset 验证 version、hash、active vocabulary 与 tag groups。
5. 扩展 `DatasetRecordSpec` 的四个 provenance 字段。
6. 更新 sample ID、record builder 和 validator，并迁移所有调用点。
7. 强制执行 adult/general-spoiler executable policy。
8. 启用全部回归测试。

当前 production taxonomy acceptance 继续 deferred。真实 AniList source/canonical/manifest、真实 HAREM identity、人工 audit 和 production subset 恢复前，production rules 配置不得声称已绑定某个 synthetic subset。
