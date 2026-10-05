# Final Project Engineering Review Bundle

## 状态与证据边界

核心工程链已运行。数据和模型指标以本报告及 comparison.json 的实际记录为准；模型会产生错误，应用通过严格 validation 拒绝非法 Query，不静默修复。
没有运行额外的 test-informed 调参训练。Final 从冻结 base 新建 LoRA，未从 S1 adapter 继续训练。
第一次连续多 split 的 batch=2 运行中，Base challenge 出现重复乱码；同一输入新进程复核恢复正常，因此旧批量结果保留为诊断材料，不纳入最终比较。三模型最终都用 batch=1、每 split 独立进程重新生成，未筛选更好的单条答案。异常根因未确定。
每次生成返回 CPU 文本后统一释放未使用 CUDA 缓存，并在 runtime identity 记录该政策；不改变权重、prompt 或解码参数。

## 系统架构

```text
User → Qwen3-4B + saved LoRA → raw JSON → strict parser → schema/domain validator
     → local AniList catalog filter → deterministic ranker → CLI recommendations
```

## 数据与来源

- Real catalog: 1544 anime; SHA-256 `b41388866e35c7af1d01081cc801005c0bcccc3f51ae34df173ef21729f4a2b5`.
- Taxonomy: real AniList snapshot; subset 83 tags, reference pool 200 titles.
- Catalog fetched at UTC: `2026-10-04T14:48:17.223945+00:00`; full-site crawl: false.
### Snapshot / executable identity

```json
{
  "taxonomy_manifest": {
    "source": "AniList GraphQL API",
    "resource": [
      "GenreCollection",
      "MediaTagCollection"
    ],
    "fetched_at_utc": "2026-10-04T14:44:01.832852Z",
    "genre_count": 19,
    "tag_count": 428,
    "canonical_sha256": "5727c5340d91fb650958e99489ab67ee9949f773f3205cf96d9597565d0f8755",
    "snapshot_schema_version": "anilist-taxonomy-snapshot-v0.1"
  },
  "subset_manifest": {
    "subset_version": "anilist-executable-tags-v0.2",
    "subset_hash": "2b6b787f9730a30d7d4e39c1c912e12ee97a89292edcc4ee95c9368eedaa7131",
    "derived_from_snapshot_hash": "5727c5340d91fb650958e99489ab67ee9949f773f3205cf96d9597565d0f8755",
    "approved_tag_count": 83
  },
  "rules_hash": "07052a4c3ea0cb9c7f0538386f2ad5a135fa0f8545acd3ef402f505be4dd3828",
  "dataset_version": "anime-pref-final-v0.2"
}
```

- Tag decisions are explicitly selected by the engineering assistant under user delegation; not represented as independent human audit.
- Dataset: 1500; splits {'train': 1200, 'validation': 150, 'test': 150}; challenge 40; 18 controlled styles.
- Cross-split exact text/pair overlap: 0. Complexity 1–5 plus reference-only; multi-value format/status OR covered.
- Taxonomy/subset/rules/dataset/model revisions have separate identities. Synthetic fixtures remain only in historical tests/pilot.

## 最终 QLoRA 配置

```json
{
  "s1_version": "final-qlora-v0.2",
  "model_id": "Qwen/Qwen3-4B",
  "tokenizer_id": "Qwen/Qwen3-4B",
  "revision": "1cfa9a7208912126459214e8b04321603b3df60c",
  "local_files_only": true,
  "dataset_version": "anime-pref-final-v0.2",
  "train_path": "data/final/train.v0.2.jsonl",
  "validation_path": "data/final/validation.v0.2.jsonl",
  "train_expected_count": 1200,
  "validation_expected_count": 150,
  "prompt_version": "final-json-extraction-v0.2",
  "prompt_path": "configs/final_system_prompt.v0.2.txt",
  "serialization_identity": "qwen3-official-chat-template-nonthinking-v1",
  "enable_thinking": false,
  "max_seq_length": 1792,
  "load_in_4bit": true,
  "bnb_4bit_quant_type": "nf4",
  "bnb_4bit_use_double_quant": true,
  "bnb_4bit_compute_dtype": "bfloat16",
  "lora_target_modules": [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj"
  ],
  "lora_r": 16,
  "lora_alpha": 32,
  "lora_dropout": 0.05,
  "lora_bias": "none",
  "lora_task_type": "CAUSAL_LM",
  "optimizer": "paged_adamw_8bit",
  "learning_rate": 0.0002,
  "lr_scheduler_type": "linear",
  "warmup_ratio": 0.1,
  "weight_decay": 0.0,
  "max_grad_norm": 1.0,
  "num_train_epochs": 1,
  "per_device_train_batch_size": 1,
  "per_device_eval_batch_size": 1,
  "gradient_accumulation_steps": 8,
  "gradient_checkpointing": true,
  "bf16": true,
  "fp16": false,
  "tf32": true,
  "logging_steps": 5,
  "eval_strategy": "epoch",
  "save_strategy": "epoch",
  "save_total_limit": 2,
  "load_best_model_at_end": true,
  "metric_for_best_model": "eval_loss",
  "greater_is_better": false,
  "dataloader_num_workers": 0,
  "report_to": "none",
  "seed": 42,
  "data_seed": 42,
  "trainer_output_dir": "artifacts/final/trainer",
  "adapter_output_dir": "artifacts/final/adapter",
  "run_identity_path": "artifacts/final/run_identity.json"
}
```

### 真实 token / labels 证据

```json
{
  "train": {
    "count": 1200,
    "min": 1642,
    "median": 1665.0,
    "p95": 1690,
    "max": 1708
  },
  "validation": {
    "count": 150,
    "max": 1729
  }
}
```

```json
{
  "input_shape": [
    1,
    1693
  ],
  "labels_shape": [
    1,
    1693
  ],
  "masked_prompt_tokens": 1599,
  "supervised_tokens": 94,
  "completion_decoded": "{\"hard_constraints\":{\"genres\":{\"all_of\":[],\"any_of\":[\"Ecchi\",\"Mecha\"],\"none_of\":[]},\"tags\":{\"all_of\":[],\"any_of\":[],\"none_of\":[]},\"year\":{\"min\":2015,\"max\":null},\"episodes\":{\"min\":null,\"max\":2},\"formats\":[\"ONA\",\"SPECIAL\"],\"status\":[\"CANCELLED\",\"HIATUS\"]},\"reference_titles\":[],\"soft_preferences\":[],\"unresolved_preferences\":[]}<|im_end|>\n"
}
```

- Saved best adapter: `113d3e479b38309996970c6d36fe1f5c64480e09a6392dd1962dba27bd61f85d`; best checkpoint `D:\Study\anime-preference-sft\artifacts\final\trainer\checkpoint-150`.
- All evaluation model variants are loaded in separate processes after training, with BF16 base and saved adapter; no merge.

### Train/validation loss

| Step | Epoch | Train loss | Eval loss | LR |
|---:|---:|---:|---:|---:|
| 5 | 0.03333333333333333 | 0.1122 |  | 5.333333333333333e-05 |
| 10 | 0.06666666666666667 | 0.0205 |  | 0.00012 |
| 15 | 0.1 | 0.0251 |  | 0.0001866666666666667 |
| 20 | 0.13333333333333333 | 0.0154 |  | 0.00019407407407407408 |
| 25 | 0.16666666666666666 | 0.0051 |  | 0.0001866666666666667 |
| 30 | 0.2 | 0.0078 |  | 0.00017925925925925927 |
| 35 | 0.23333333333333334 | 0.0005 |  | 0.00017185185185185185 |
| 40 | 0.26666666666666666 | 0.0011 |  | 0.00016444444444444444 |
| 45 | 0.3 | 0.0003 |  | 0.00015703703703703705 |
| 50 | 0.3333333333333333 | 0.0003 |  | 0.00014962962962962963 |
| 55 | 0.36666666666666664 | 0.0002 |  | 0.00014222222222222224 |
| 60 | 0.4 | 0.0021 |  | 0.00013481481481481482 |
| 65 | 0.43333333333333335 | 0.0035 |  | 0.0001274074074074074 |
| 70 | 0.4666666666666667 | 0.0008 |  | 0.00012 |
| 75 | 0.5 | 0.0018 |  | 0.0001125925925925926 |
| 80 | 0.5333333333333333 | 0.0003 |  | 0.00010518518518518518 |
| 85 | 0.5666666666666667 | 0.0002 |  | 9.777777777777778e-05 |
| 90 | 0.6 | 0.0019 |  | 9.037037037037038e-05 |
| 95 | 0.6333333333333333 | 0.0018 |  | 8.296296296296296e-05 |
| 100 | 0.6666666666666666 | 0.0002 |  | 7.555555555555556e-05 |
| 105 | 0.7 | 0.0001 |  | 6.814814814814815e-05 |
| 110 | 0.7333333333333333 | 0.0011 |  | 6.074074074074074e-05 |
| 115 | 0.7666666666666667 | 0.0001 |  | 5.333333333333333e-05 |
| 120 | 0.8 | 0.0001 |  | 4.592592592592593e-05 |
| 125 | 0.8333333333333334 | 0.0001 |  | 3.851851851851852e-05 |
| 130 | 0.8666666666666667 | 0.0001 |  | 3.111111111111111e-05 |
| 135 | 0.9 | 0.0002 |  | 2.3703703703703707e-05 |
| 140 | 0.9333333333333333 | 0.0001 |  | 1.62962962962963e-05 |
| 145 | 0.9666666666666667 | 0.0001 |  | 8.88888888888889e-06 |
| 150 | 1.0 | 0.0001 |  | 1.4814814814814817e-06 |
| 150 | 1.0 |  | 8.059773244895041e-05 |  |

## Base vs S1 vs Final：同一 v0.2 协议

这些是重新在同一 enlarged-vocabulary prompt 和新数据集上生成的指标，不能直接当作历史 E0/S1 v0.1 的纵向提升。

| Split | Model | N | JSON | Schema | Domain | Exact | Hard P | Hard R | Hard F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| validation | base | 150 | 94.0% | 94.0% | 87.3% | 51.3% | 86.2% | 64.2% | 73.6% |
| validation | s1 | 150 | 100.0% | 100.0% | 94.7% | 82.0% | 96.8% | 88.7% | 92.6% |
| validation | final | 150 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| test | base | 150 | 90.7% | 90.0% | 88.0% | 54.0% | 90.0% | 70.0% | 78.8% |
| test | s1 | 150 | 100.0% | 100.0% | 98.7% | 86.0% | 97.9% | 93.2% | 95.5% |
| test | final | 150 | 100.0% | 100.0% | 99.3% | 99.3% | 100.0% | 99.5% | 99.7% |
| challenge | base | 40 | 85.0% | 85.0% | 82.5% | 42.5% | 86.0% | 63.6% | 73.1% |
| challenge | s1 | 40 | 100.0% | 100.0% | 92.5% | 65.0% | 90.5% | 74.0% | 81.4% |
| challenge | final | 40 | 100.0% | 100.0% | 97.5% | 67.5% | 89.0% | 84.4% | 86.7% |

Exact 与 Hard P/R/F1 沿用冻结 evaluator：集合排序不影响结果，但不折叠 singleton ANY/ALL。部分 WRONG_OPERATOR 因而是表达合同差异，即使执行器过滤结果相同；完整失败 Query 保留供复盘。这条说明不改变任何指标。

### Field accuracy (Final)

| Split | Field | Accuracy |
|---|---|---:|
| test | genres | 99.3% |
| test | tags | 99.3% |
| test | year | 99.3% |
| test | episodes | 99.3% |
| test | formats | 99.3% |
| test | status | 99.3% |
| test | reference_titles | 99.3% |
| test | soft_preferences | 99.3% |
| test | unresolved_preferences | 99.3% |
| challenge | genres | 87.5% |
| challenge | tags | 82.5% |
| challenge | year | 97.5% |
| challenge | episodes | 97.5% |
| challenge | formats | 97.5% |
| challenge | status | 97.5% |
| challenge | reference_titles | 97.5% |
| challenge | soft_preferences | 97.5% |
| challenge | unresolved_preferences | 92.5% |

### 剩余失败与回归

所有模型在 test/challenge 的完整失败 Query、raw output 和 error taxonomy 保存在 `artifacts/final/comparison.json.failures`。
下面保留 Final 的逐条失败；invalid-domain 时冻结 evaluator 采用 fail-closed metrics，不额外给部分分。

### test / sample_6f6da97b248f3241eb1284ae5a90f21343877a8dd876d61db23cb2db94890831

推荐一些满足这些条件的作品：标签为教育或足球中的任一种；状态为正在连载；找类似《JUJUTSU KAISEN》的作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["RELEASING"], "tags": {"all_of": [], "any_of": ["Educational", "Football"], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": ["JUJUTSU KAISEN"], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Education","Football"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["RELEASING"]},"reference_titles":["JUJUTSU KAISEN"],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: DOMAIN_ERROR

### challenge / final_challenge_001

只要悬疑题材，最多二十四集。

Gold:
```json
{"hard_constraints": {"episodes": {"max": 24, "min": null}, "formats": [], "genres": {"all_of": ["Mystery"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":24},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_005

2013年及以前的科幻作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": ["Sci-Fi"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": 2013, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":2013},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT

### challenge / final_challenge_008

至少十五集，可以长一些。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 15}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": ["可以长一些"]}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":15,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: 

### challenge / final_challenge_014

想看异世界题材的已完结作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["FINISHED"], "tags": {"all_of": ["Isekai"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":["Isekai"],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["FINISHED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: DOMAIN_ERROR

### challenge / final_challenge_016

包含时间循环标签的动画。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Time Loop"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Time Loop"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_027

2022年及以后，至少六集，喜剧TV动画且已经完结。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 6}, "formats": ["TV"], "genres": {"all_of": ["Comedy"], "any_of": [], "none_of": []}, "status": ["FINISHED"], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": 2022}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Comedy"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":2022,"max":null},"episodes":{"min":6,"max":null},"formats":["TV"],"status":["FINISHED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_029

战斗不作要求，只要机甲题材。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": ["Mecha"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mecha"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_030

有哲学标签，至少十集。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 10}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Philosophy"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Philosophy"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":10,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_031

找群像TV动画，不要后宫。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": ["TV"], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Ensemble Cast"], "any_of": [], "none_of": ["Female Harem", "Male Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, WRONG_VALUE, NORMALIZATION_ERROR

### challenge / final_challenge_032

我想看死亡游戏标签的作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Death Game"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Death Game"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_038

给我治愈系标签的动画，年份不晚于2019年。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Iyashikei"], "any_of": [], "none_of": []}, "year": {"max": 2019, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Iyashikei"],"none_of":[]},"year":{"min":null,"max":2019},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_039

推荐带露营标签的作品，至少两集。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 2}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Camping"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Camping"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":2,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_040

想找节奏紧凑的作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": ["节奏紧凑"]}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: 


### 历史 challenge_009 probe（新公共 prompt）

- base: exact=False; errors=['MISSING_CONSTRAINT'].
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":null},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
- s1: exact=True; errors=[].
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery","Sci-Fi"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":null},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
- final: exact=True; errors=[].
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery","Sci-Fi"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":null},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```

## 十个真实端到端 demos

下面的 Query 来自已保存 Final adapter 的真实 GPU inference；推荐来自 1544 条本地 AniList snapshot。
Pipeline success: 10/10; intended-query exact: 7/10; semantic match allowing singleton ANY/ALL equivalence: 8/10.
Demo 1 漏抽 Mystery；Demo 7 漏抽 Sci-Fi。结构/domain validation 无法检测这种漏抽，不能将 status=ok 描述为语义全对。Demo 9 使用 singleton ANY 而预期为 ALL，过滤语义相同但 strict Exact 不同。
完整人工预期、逐条 Query 对照和推荐违反预期约束的 ID 保存在 `artifacts/final/demo_fidelity_audit.json`。

### Demo 1

想看2018年及以后的悬疑动画，最多24集。

Status: ok
Intended semantics matched: False; recommendation IDs violating intended hard constraints: [113415, 101348].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": 2018,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": 24
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Attack on Titan Season 3 Part 2 | 2019 | TV | 10 | 0.5552 |
| Attack on Titan Final Season | 2020 | TV | 16 | 0.5503 |
| JUJUTSU KAISEN | 2020 | TV | 24 | 0.5503 |
| Attack on Titan Season 3 | 2018 | TV | 12 | 0.5487 |
| Vinland Saga | 2019 | TV | 24 | 0.5468 |
### Demo 2

悬疑或者科幻都可以，不要后宫。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [
        "Mystery",
        "Sci-Fi"
      ],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": [
        "Female Harem",
        "Male Harem",
        "Mixed Gender Harem"
      ]
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Neon Genesis Evangelion | 1995 | TV | 26 | 0.9327 |
| Made in Abyss | 2017 | TV | 13 | 0.9313 |
| The Disappearance of Haruhi Suzumiya | 2010 | MOVIE | 1 | 0.9156 |
| Made in Abyss: Dawn of the Deep Soul | 2020 | MOVIE | 1 | 0.9147 |
| Made in Abyss: The Golden City of the Scorching Sun | 2022 | TV | 12 | 0.9137 |
### Demo 3

想找类似《Steins;Gate》的作品。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [
    "Steins;Gate"
  ],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Steins;Gate | 2011 | TV | 24 | 2.5546 |
| Steins;Gate 0 | 2018 | TV | 23 | 1.8697 |
| Steins;Gate 0: 23β -Divide by Zero- | 2015 | OVA | 1 | 1.7025 |
| ID: INVADED | 2020 | TV | 13 | 1.4670 |
| Steins;Gate The Movie – Load Region of Déjà Vu | 2013 | MOVIE | 1 | 1.4127 |
### Demo 4

想看同时有科幻和悬疑题材的TV动画。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [
        "Mystery",
        "Sci-Fi"
      ],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [
      "TV"
    ],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Neon Genesis Evangelion | 1995 | TV | 26 | 0.9327 |
| Made in Abyss | 2017 | TV | 13 | 0.9313 |
| Made in Abyss: The Golden City of the Scorching Sun | 2022 | TV | 12 | 0.9137 |
| Serial Experiments Lain | 1998 | TV | 13 | 0.9092 |
| Tengoku Daimakyo | 2023 | TV | 13 | 0.9084 |
### Demo 5

想看已经完结、有异世界标签的动画。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [
        "Isekai"
      ],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [],
    "status": [
      "FINISHED"
    ]
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Spirited Away | 2001 | MOVIE | 1 | 0.7410 |
| Re:ZERO -Starting Life in Another World- | 2016 | TV | 25 | 0.7316 |
| Mushoku Tensei: Jobless Reincarnation Cour 2 | 2021 | TV | 12 | 0.7296 |
| Mushoku Tensei: Jobless Reincarnation | 2021 | TV | 11 | 0.7281 |
| Re:ZERO -Starting Life in Another World- Season 4 | 2026 | TV | 19 | 0.7273 |
### Demo 6

不要恋爱题材。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": [
        "Romance"
      ]
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Hunter x Hunter (2011) | 2011 | TV | 148 | 0.5621 |
| Fullmetal Alchemist: Brotherhood | 2009 | TV | 64 | 0.5620 |
| Frieren: Beyond Journey’s End | 2023 | TV | 28 | 0.5561 |
| Attack on Titan Season 3 Part 2 | 2019 | TV | 10 | 0.5552 |
| Attack on Titan | 2013 | TV | 25 | 0.5550 |
### Demo 7

2010年及以前的科幻作品。

Status: ok
Intended semantics matched: False; recommendation IDs violating intended hard constraints: [5114, 21, 1535, 199].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": 2010
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Fullmetal Alchemist: Brotherhood | 2009 | TV | 64 | 0.5620 |
| ONE PIECE | 1999 | TV | None | 0.5537 |
| Death Note | 2006 | TV | 37 | 0.5500 |
| Spirited Away | 2001 | MOVIE | 1 | 0.5410 |
| Cowboy Bebop | 1998 | TV | 26 | 0.5404 |
### Demo 8

最多12集的作品。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": 12
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| A Silent Voice | 2016 | MOVIE | 1 | 0.5557 |
| Attack on Titan Season 3 Part 2 | 2019 | TV | 10 | 0.5552 |
| Attack on Titan Season 3 | 2018 | TV | 12 | 0.5487 |
| Attack on Titan Season 2 | 2017 | TV | 12 | 0.5471 |
| Your Name. | 2016 | MOVIE | 1 | 0.5466 |
### Demo 9

想找带时间循环标签的作品。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [
        "Time Loop"
      ],
      "none_of": []
    },
    "year": {
      "min": null,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": null
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Steins;Gate | 2011 | TV | 24 | 0.7546 |
| Re:ZERO -Starting Life in Another World- | 2016 | TV | 25 | 0.7316 |
| Rascal Does Not Dream of Bunny Girl Senpai | 2018 | TV | 13 | 0.7301 |
| JoJo's Bizarre Adventure: Golden Wind | 2018 | TV | 39 | 0.7278 |
| Re:ZERO -Starting Life in Another World- Season 4 | 2026 | TV | 19 | 0.7273 |
### Demo 10

2015年及以后、最多24集、悬疑或者科幻、不要后宫。

Status: ok
Intended semantics matched: True; recommendation IDs violating intended hard constraints: [].
```json
{
  "hard_constraints": {
    "genres": {
      "all_of": [],
      "any_of": [
        "Mystery",
        "Sci-Fi"
      ],
      "none_of": []
    },
    "tags": {
      "all_of": [],
      "any_of": [],
      "none_of": [
        "Female Harem",
        "Male Harem",
        "Mixed Gender Harem"
      ]
    },
    "year": {
      "min": 2015,
      "max": null
    },
    "episodes": {
      "min": null,
      "max": 24
    },
    "formats": [],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

| Title | Year | Format | Episodes | Score |
|---|---:|---|---:|---:|
| Made in Abyss | 2017 | TV | 13 | 0.9313 |
| Made in Abyss: Dawn of the Deep Soul | 2020 | MOVIE | 1 | 0.9147 |
| Made in Abyss: The Golden City of the Scorching Sun | 2022 | TV | 12 | 0.9137 |
| Tengoku Daimakyo | 2023 | TV | 13 | 0.9084 |
| PLUTO | 2023 | ONA | 8 | 0.9022 |

## 测试与可复现命令

完整最新测试输出见 `artifacts/final/tests.txt`；语法编译与 diff whitespace 检查见 `artifacts/final/checks.txt`。
落盘 provenance 审核见 `artifacts/final/provenance_audit.json`：train/validation/test 的完整 DatasetRecord 与既有 validator 重新核对；challenge 保持原 E0 challenge shape，以作者显式 SemanticSpec 重建 Gold 比较。

```text
.......................................................................................................................................................................................................................................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 455 tests in 48.073s

OK
compileall: PASS
git diff --check: PASS
```

```powershell
.\.venv\Scripts\python.exe scripts/fetch_catalog.py
.\.venv\Scripts\python.exe scripts/build_final_data.py
.\.venv\Scripts\python.exe scripts/verify_final_data.py
.\.venv\Scripts\python.exe scripts/prepare_final_config.py
.\.venv\Scripts\python.exe scripts/train_final.py --train
.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model base
.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model s1
.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model final
.\.venv\Scripts\python.exe scripts/run_demo_cases.py
.\.venv\Scripts\python.exe scripts/recommend.py "悬疑或者科幻都可以，不要后宫。"
.\.venv\Scripts\python.exe scripts/recommend.py --interactive
```

训练与 evaluation 拒绝覆盖已有结果。以上训练命令用于新实验目录；当前已完成环境直接运行 recommend 即可。

## 调用链 / 文档

- `README.md`: installation, training, evaluation, CLI, limitations.
- `docs/project_summary.md`: project explanation, resume bullets, interview questions.
- `docs/code_walkthrough.md`: source navigation in data→training→inference order.

## 已知局限与 optional items

- Bounded catalog is neither exhaustive nor continuously updated; 0 matches is returned without relaxing constraints.
- Tag subset has delegated engineering review, not independent expert/user audit; flags exclude adult/spoiler concepts.
- Controlled text is easier than unconstrained user language; challenge failures are retained, not hidden.
- Reference lookup is exact after Unicode/case normalization; ambiguous/unmatched references only warn.
- Reference source itself may remain among recommendations; reference is ranking-only.
- Tag rank thresholds / simple scoring are explicit engineering policies, not learned recommendation quality.
- No LLM paraphrase, trainable ranker, web frontend, FastAPI, vector DB, adapter merge or distributed training.
- No claim of production robustness or causal improvement independent of the new data/prompt protocol.
- Frozen training prompt still lists Hentai from the legacy genre line; active v0.2 DomainRules rejects it. This discrepancy is retained transparently, not silently edited after evaluation.

## 最终文件树

```text
anime-preference-sft/
  .gitignore
  README.md
  pyproject.toml
  requirements-e0.txt
  requirements-s1.txt
  artifacts/
    e0/
      challenge_predictions.jsonl
      determinism_check.json
      metrics.json
      run_identity.json
      smoke_predictions.jsonl
      test_predictions.jsonl
      validation_predictions.jsonl
      validation_predictions.prompt_v0.1.jsonl
    final/
      acceptance_console.log
      acceptance_resumed_console.log
      adapter_manifest.json
      adapter_smoke.json
      base_runtime_diagnostic.json
      checks.txt
      comparison.json
      demo_fidelity_audit.json
      demo_results.json
      provenance_audit.json
      run_identity.json
      tests.txt
      token_audit.json
      training_console.log
      adapter/
        README.md
        adapter_config.json
        adapter_model.safetensors
        added_tokens.json
        chat_template.jinja
        merges.txt
        special_tokens_map.json
        tokenizer.json
        tokenizer_config.json
        training_args.bin
        vocab.json
      evaluation/
        base/
          challenge_identity.json
          challenge_predictions.jsonl
          legacy_challenge_identity.json
          legacy_challenge_predictions.jsonl
          test_identity.json
          test_predictions.jsonl
          validation_identity.json
          validation_predictions.jsonl
        final/
          challenge_identity.json
          challenge_predictions.jsonl
          legacy_challenge_identity.json
          legacy_challenge_predictions.jsonl
          test_identity.json
          test_predictions.jsonl
          validation_identity.json
          validation_predictions.jsonl
        s1/
          challenge_identity.json
          challenge_predictions.jsonl
          legacy_challenge_identity.json
          legacy_challenge_predictions.jsonl
          test_identity.json
          test_predictions.jsonl
          validation_identity.json
          validation_predictions.jsonl
      evaluation_bulk_interrupted/
        base/
          challenge_identity.json
          challenge_predictions.jsonl
          test_identity.json
          test_predictions.jsonl
          validation_identity.json
          validation_predictions.jsonl
        final/
          challenge_identity.json
          challenge_predictions.jsonl
          legacy_challenge_identity.json
          legacy_challenge_predictions.jsonl
          test_identity.json
          test_predictions.jsonl
          validation_identity.json
          validation_predictions.jsonl
      trainer/
        all_results.json
        train_results.json
        trainer_state.json
        checkpoint-150/
          README.md
          adapter_config.json
          adapter_model.safetensors
          added_tokens.json
          chat_template.jinja
          merges.txt
          optimizer.pt
          rng_state.pth
          scheduler.pt
          special_tokens_map.json
          tokenizer.json
          tokenizer_config.json
          trainer_state.json
          training_args.bin
          vocab.json
    s1/
      comparison.json
      run_identity.json
      adapter/
        README.md
        adapter_config.json
        adapter_model.safetensors
        added_tokens.json
        chat_template.jinja
        merges.txt
        special_tokens_map.json
        tokenizer.json
        tokenizer_config.json
        training_args.bin
        vocab.json
      evaluation/
        challenge_inference_identity.json
        challenge_predictions.jsonl
        test_inference_identity.json
        test_predictions.jsonl
        validation_inference_identity.json
        validation_predictions.jsonl
      trainer/
        all_results.json
        train_results.json
        trainer_state.json
        checkpoint-23/
          README.md
          adapter_config.json
          adapter_model.safetensors
          added_tokens.json
          chat_template.jinja
          merges.txt
          optimizer.pt
          rng_state.pth
          scheduler.pt
          special_tokens_map.json
          tokenizer.json
          tokenizer_config.json
          trainer_state.json
          training_args.bin
          vocab.json
        checkpoint-69/
          README.md
          adapter_config.json
          adapter_model.safetensors
          added_tokens.json
          chat_template.jinja
          merges.txt
          optimizer.pt
          rng_state.pth
          scheduler.pt
          special_tokens_map.json
          tokenizer.json
          tokenizer_config.json
          trainer_state.json
          training_args.bin
          vocab.json
  configs/
    data.json
    data.yaml
    domain_rules.v0.1.1.json
    domain_rules.v0.1.json
    domain_rules.v0.2.json
    e0_baseline.v0.1.json
    e0_system_prompt.v0.1.txt
    e0_system_prompt.v0.2.txt
    final_qlora.v0.2.json
    final_system_prompt.v0.2.txt
    pilot_pattern_manifest.v0.1.json
    s1_qlora_pilot.v0.1.json
    semantic_sampler.v0.2.json
    tag_audit.example.v0.1.json
    taxonomy_snapshot.v0.1.json
  data/
    catalog/
      anilist_catalog_v0.1.jsonl
      manifest.json
      source/
        movies_001.json
        movies_002.json
        movies_003.json
        movies_004.json
        movies_005.json
        movies_006.json
        older_001.json
        older_002.json
        popular_001.json
        popular_002.json
        popular_003.json
        popular_004.json
        popular_005.json
        popular_006.json
        popular_007.json
        popular_008.json
        popular_009.json
        popular_010.json
        popular_011.json
        popular_012.json
        popular_013.json
        popular_014.json
        popular_015.json
        popular_016.json
        popular_017.json
        popular_018.json
        popular_019.json
        popular_020.json
        recent_001.json
        recent_002.json
        recent_003.json
        recent_004.json
        recent_005.json
        recent_006.json
    domain/
      reference_ids.v0.2.json
      reference_titles.v0.2.json
      tag_audit.v0.2.json
      tag_selection.v0.2.json
      subset_v0.2/
        executable_tags.json
        manifest.json
      taxonomy_v0.2/
        canonical.json
        manifest.json
        source.json
    final/
      audit.json
      challenge.v0.2.jsonl
      reviewed_patterns.json
      test.v0.2.jsonl
      train.v0.2.jsonl
      validation.v0.2.jsonl
    interim/
      .gitkeep
    pilot/
      challenge.v0.1.jsonl
      pilot_all.v0.1.jsonl
      test.v0.1.jsonl
      train.v0.1.jsonl
      validation.v0.1.jsonl
    processed/
      .gitkeep
    raw/
      .gitkeep
      anilist/
        manifest.json
        page_0001.jsonl
      anilist-smoke/
        manifest.json
        page_0001.jsonl
  docs/
    code_walkthrough.md
    e0_baseline_v0.1.md
    e0_baseline_v0.1_IMPLEMENTATION.md
    e0_baseline_v0.1_REVIEW.md
    pilot_dataset_audit_v0.1.md
    pilot_dataset_v0.1.1_SPLIT_HYGIENE_IMPLEMENTATION.md
    pilot_dataset_v0.1.1_SPLIT_HYGIENE_REVIEW.md
    project_summary.md
    s1_qlora_pilot_v0.1.md
    模块实现详解.md
    项目实现学习手册.md
  outputs/
    .gitkeep
    todo39_offline_fixture_v1/
      audit.json
      snapshot/
        canonical.json
        manifest.json
        source.json
      subset/
        executable_tags.json
        manifest.json
  scripts/
    build_executable_tag_subset.py
    build_final_data.py
    check_final_adapter.py
    check_s1_nf4.py
    check_s1_training_step.py
    diagnose_base_runtime.py
    download_base_model.py
    fetch_anilist.py
    fetch_anilist_taxonomy.py
    fetch_catalog.py
    finish_final_project.py
    generate_pilot_dataset.py
    prepare_final_config.py
    recommend.py
    report_e0_baseline.py
    report_final_project.py
    run_demo_cases.py
    run_e0_baseline.py
    run_final_evaluation.py
    run_s1_evaluation.py
    train_final.py
    train_s1_pilot.py
    verify_final_data.py
  src/
    anime_pref/
      __init__.py
      recommendation.py
      data/
        __init__.py
        anilist_client.py
        catalog.py
        constraint_signature.py
        dataset_record_builder.py
        domain_validation.py
        final_dataset.py
        io.py
        pilot_dataset.py
        query_builder.py
        query_validation.py
        reference_title_pool.py
        rules_identity.py
        tag_subset.py
        taxonomy_client.py
        taxonomy_snapshot.py
      evaluation/
        __init__.py
        e0_baseline.py
        s1_comparison.py
      inference/
        __init__.py
        final_parser.py
        hf_baseline.py
        hf_sft.py
      retrieval/
        __init__.py
        executor.py
      sampling/
        __init__.py
        categorical_value.py
        config.py
        domain_bindability.py
        domain_conditioned_support.py
        family_complexity.py
        mechanics_probability.py
        mechanics_sampler.py
        numeric_range.py
        operator_cardinality.py
        semantic_spec_binder.py
        structural_atom.py
        structural_pattern.py
        structural_signature.py
        structural_signature_sampler.py
      schemas/
        __init__.py
        anime_metadata.py
        categorical_value.py
        dataset_record.py
        domain_bindability.py
        e0_baseline.py
        family_complexity.py
        numeric_range.py
        operator_cardinality.py
        pilot_dataset.py
        preference_query.py
        s1_training.py
        sampler_config.py
        structural_atom.py
        structural_pattern.py
        structural_signature.py
        taxonomy.py
      training/
        __init__.py
        final_training.py
        sft_collator.py
        sft_config.py
        sft_data.py
        sft_dataset.py
        sft_environment.py
        sft_identity.py
        sft_model.py
        sft_token_audit.py
        sft_tokenization.py
        sft_trainer.py
  tests/
    test_categorical_value_sampler.py
    test_dataset_record_builder.py
    test_domain_bindability.py
    test_domain_conditioned_support.py
    test_e0_baseline.py
    test_family_complexity_planner.py
    test_final_project.py
    test_mechanics_probability.py
    test_mechanics_sampler.py
    test_numeric_range_sampler.py
    test_operator_cardinality_sampler.py
    test_pilot_dataset.py
    test_query_builder.py
    test_rules_identity_and_record_provenance.py
    test_sampler_config.py
    test_scaffold.py
    test_schema_contract_v011.py
    test_semantic_spec_binder.py
    test_sft_collator.py
    test_sft_config.py
    test_sft_data.py
    test_sft_token_audit.py
    test_sft_tokenization.py
    test_structural_atom.py
    test_structural_pattern.py
    test_structural_signature_policy.py
    test_structural_signature_sampler.py
    test_taxonomy_snapshot.py
    fixtures/
      domain_rules.synthetic.v0.1.json
      executable_tags.synthetic.v0.1.json
      reference_titles.synthetic.v0.1.json
      semantic_sampler.synthetic.v0.1.json
      structural_pattern_policy.synthetic.v0.1.json
```
