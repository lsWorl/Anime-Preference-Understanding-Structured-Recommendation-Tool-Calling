# Schema Contract v0.1.1 Review Bundle

> 状态：该 bundle 已由理论分支审查通过。后续新增决策和 DatasetRecord Builder 工作见
> `dataset_record_builder_v0.1.md`。

## 审查范围

本 bundle 只覆盖进入 semantic sampler 前的 Schema Contract v0.1.1 修正。没有实现
sampler、模板生成、LLM paraphrase、split 或训练。

## 相关目录树

```text
anime-preference-sft/
├── configs/
│   └── domain_rules.v0.1.1.json
├── docs/
│   ├── schema_contract_v0.1.1.md
│   └── schema_contract_v0.1.1_review_bundle.md
├── src/anime_pref/
│   ├── data/
│   │   ├── query_builder.py
│   │   ├── query_validation.py
│   │   └── constraint_signature.py
│   └── schemas/
│       ├── preference_query.py
│       └── dataset_record.py
└── tests/
    ├── test_query_builder.py
    └── test_schema_contract_v011.py
```

## 核心代码位置

- SemanticSpec：[preference_query.py](D:/Study/anime-preference-sft/src/anime_pref/schemas/preference_query.py)
- Dataset provenance：[dataset_record.py](D:/Study/anime-preference-sft/src/anime_pref/schemas/dataset_record.py)
- DomainRules、loader、builder、serializer：[query_builder.py](D:/Study/anime-preference-sft/src/anime_pref/data/query_builder.py)
- 共享 validator/canonicalizer：[query_validation.py](D:/Study/anime-preference-sft/src/anime_pref/data/query_validation.py)
- Constraint signature：[constraint_signature.py](D:/Study/anime-preference-sft/src/anime_pref/data/constraint_signature.py)
- v0.1.1 executable contract：[test_schema_contract_v011.py](D:/Study/anime-preference-sft/tests/test_schema_contract_v011.py)

## Contract 摘要

Gold JSON 保持完整显式结构：

```json
{
  "hard_constraints": {
    "genres": {"all_of": [], "any_of": [], "none_of": []},
    "tags": {"all_of": [], "any_of": [], "none_of": []},
    "year": {"min": null, "max": null},
    "episodes": {"min": null, "max": null},
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

- genres/tags 的三个 operator 是集合约束，内部值 canonical sort。
- formats/status 是 acceptable values 的 OR list，v0.1.1 没有 NOT。
- key order 不影响 semantic validity；canonical serializer 固定输出顺序。
- canonical 字符串非空且禁止首尾 whitespace，不进行静默 strip。
- reference titles 保持字符串；AniList ID 只可作为未来 dataset metadata。
- soft preferences 只能来自 approved vocabulary；当前 vocabulary 为空。

## Normalization 与 HAREM

配置中的 HAREM rule：

```json
{
  "tags": ["Female Harem", "Male Harem", "Mixed Gender Harem"],
  "allowed_operators": ["any_of", "none_of"],
  "normalization_rule_id": "HAREM_EXPANSION_V0_1_1"
}
```

因此：

- 正向 HAREM 展开到 `tags.any_of`。
- 负向 HAREM 展开到 `tags.none_of`。
- HAREM 放入 `all_of` 会失败。
- 实现检查配置的 `allowed_operators`，没有按 HAREM 名称硬编码。
- 显式 tag 与 expansion 重复时失败，不自动去重。

## Validation 与 serialization

`validate_query()` 是 Gold Query 的共享 semantic validator。它检查精确 key 集合、JSON
类型、字符串、重复、operator overlap、range 和 episodes 正数，但不检查 taxonomy。

`canonicalize_query()` 先验证，再重建固定 key order；集合字段排序，文本字段保持顺序，
且不修改输入。

`dumps_query()` 只序列化 canonical copy。`build_constraint_signature()` 先调用同一 validator，
再按固定 token 顺序读取 hard constraints。

## Dataset provenance 预留

模型 Gold JSON 之外已预留：

```text
sample_id, schema_version, dataset_version, semantic_spec, gold_query,
constraint_signature, constraint_count, semantic_family, generation_family,
template_id, normalization_rule_ids, seed, user_text,
paraphrase_model, prompt_version
```

`split` 尚未加入；它属于后续划分阶段。record builder 尚未实现。

## 测试证据

执行：

```powershell
python -B -m py_compile src/anime_pref/data/query_builder.py src/anime_pref/data/query_validation.py src/anime_pref/data/constraint_signature.py
python -B -m unittest tests.test_schema_contract_v011 -v
python -B -m unittest discover -s tests -v
```

预期并已观测：

```text
Schema Contract tests: 8 passed
Full test suite: 23 passed
Skipped: 0
```

覆盖内容包括 HAREM operator、soft/unresolved、whitespace、episodes minimum、reordered
keys、canonical sort、serializer 和 signature 复用 validation。

## 需要理论侧确认的剩余设计点

1. `constraint_count` 按 active slot、leaf value、numeric bound 还是其他单位计算。
2. year 的 basic reasonable range 如何定义，且如何与后续 sampling bounds 区分。
3. 第一版 approved soft preference vocabulary 是否继续为空；若不为空，需要批准 label 与映射。
4. AniList taxonomy snapshot 的版本/hash 格式，以及 executable tag subset audit 流程。
5. 上述四点确认后，工程侧才进入 dataset record builder 与 semantic sampler。
