# E0 Base-Model Baseline Evaluation v0.1 实现报告

## 1. 目标与最终运行身份

E0 测量未经 SFT、LoRA 或 QLoRA 的 base checkpoint 对 `user_text -> 完整 Schema v0.1.1 JSON` 的原始能力。本实现只执行模型加载、前向生成、严格解析、验证、比较和错误分析。

实际运行身份：

- model/tokenizer：`Qwen/Qwen3-4B`；
- revision：`1cfa9a7208912126459214e8b04321603b3df60c`；
- prompt：`e0-json-extraction-v0.2`；
- serialization：Qwen3 官方 chat template，`enable_thinking=false`；
- decoding：`do_sample=false`、`num_beams=1`、`max_new_tokens=512`；
- dtype/device：BF16 / NVIDIA GeForce RTX 5070；
- PyTorch：`2.11.0+cu130`；
- Transformers：`4.57.6`。

模型权重的三个 shard 均来自冻结 checkpoint，其中两个大 shard 使用官方 LFS SHA-256 完整校验。推理配置使用 `local_files_only=true`，正式运行不会因远程仓库变化漂移。

## 2. 文件职责

### `configs/e0_baseline.v0.1.json`

保存 checkpoint、revision、prompt、chat serialization、device/dtype 和确定性 generation settings。`prompt_frozen` 是 test/challenge 的执行门禁；validation 调试结束前二者不能运行。

### `configs/e0_system_prompt.v0.1.txt` 与 `v0.2.txt`

v0.1 是第一次 validation prompt。它在 30 条 validation 上暴露：

- 7 条把 episode max 同时复制到 `year.max`；
- 2 条把明确 genre exclusion 错当成 HAREM normalization。

v0.2 只根据这些 validation 证据增加 numeric field isolation 和 normalization trigger 边界。v0.2 的 validation Exact Match 从 70.0% 提升到 93.3%，随后冻结；test/challenge 只运行一次 v0.2。

### `src/anime_pref/schemas/e0_baseline.py`

- `E0BaselineConfig`：冻结推理和复现身份；
- `E0InputRecord`：只保留 inference/evaluation 所需输入和切片 provenance；
- `E0PredictionRecord`：保存 raw output、逐层错误、canonical prediction、字段结果、constraint counts、错误标签和运行身份。

### `src/anime_pref/inference/hf_baseline.py`

#### `HuggingFaceBaselineAdapter.__init__`

从冻结本地 snapshot 加载 tokenizer/model，设置 BF16、CUDA 和 eval mode。该函数计算 system prompt 与官方 chat template 的 SHA-256，并记录 torch/transformers/GPU 版本。

#### `_serialize(user_text)`

只构造：

```text
system
user
assistant generation start
```

调用 tokenizer 官方 `apply_chat_template`，显式关闭 Qwen3 thinking。接口不接收 Gold，因此 Gold 无法进入 prompt。

#### `generate_batch(user_texts)`

执行一次 greedy primary generation。输出只截取 assistant completion 部分并保存完整 decoded raw text，不做 JSON 截取或 code-fence repair。

#### `generate_all(adapter, user_texts, batch_size)`

按原始顺序分批推理，并验证输出数与输入数相同。没有 retry、n-best、self-consistency 或 fallback prompt。

### `src/anime_pref/evaluation/e0_baseline.py`

#### 配置与输入

- `load_e0_config`：严格校验 config key、类型和 deterministic settings；
- `load_system_prompt`：加载版本化 prompt，只删除普通文本文件末尾换行；
- `build_inference_messages`：建立 system/user 两条消息；
- `validate_e0_split_authorization`：prompt 未冻结时拒绝 test/challenge；
- `load_e0_inputs`：读取 validation/test/challenge JSONL 并验证 Gold 结构。

#### 严格 parse pipeline

`strict_parse_prediction(raw_output)` 对整段 raw output 调用一次 `json.loads`。额外解释、code fence、前后多余字符都会导致 primary parse failure。

`is_recoverable_json` 只计算独立 recoverability signal。它不会替换 `parsed_prediction`，不会参与 exact、field 或 constraint primary metrics。

`evaluate_raw_prediction` 的调用顺序固定为：

```text
raw output
-> strict JSON parse
-> validate_query_structure
-> validate_query_domain
-> canonicalize_query
-> compare canonical Gold
```

任一层失败都保留对应 error string，不 silent repair。

#### 字段与 constraint metrics

字段 exact accuracy 覆盖：genres、tags、year、episodes、formats、status、reference_titles、soft_preferences、unresolved_preferences。

`hard_constraint_clauses` 使用已冻结 semantic clause 单位：

- `all_of`/`none_of` 每个独立 item 一项；
- 非空 `any_of` 整个 OR set 一项；
- year/episodes 每个非空 bound 一项；
- formats/status 非空 OR list 各一项。

基于 Gold/predicted clause 集合交集累计 micro precision、recall 和 F1。

#### 错误分类

一条记录可以同时拥有多个标签：

```text
JSON_PARSE_ERROR
SCHEMA_ERROR
DOMAIN_ERROR
MISSING_CONSTRAINT
HALLUCINATED_CONSTRAINT
WRONG_OPERATOR
WRONG_VALUE
WRONG_NUMERIC_BOUND
REFERENCE_ERROR
NORMALIZATION_ERROR
```

HAREM normalization 通过 record normalization provenance 或 Gold 中完整三个 HAREM leaf 的 concept expansion 识别。Reference error 独立比较标题；从参考作品额外推断 hard fields 会成为 `HALLUCINATED_CONSTRAINT`。

#### 汇总与切片

- `compute_e0_metrics`：整体严格指标、字段准确率、micro hard metrics、错误计数；
- `compute_metric_slices`：按 semantic family、constraint count、signature 复用同一指标；
- `build_e0_metrics_bundle`：组装 validation/test/challenge，并额外输出 normalization/reference 专项切片。

### 命令行

- `scripts/run_e0_baseline.py`：运行一个 split，保存 raw predictions 与 run identity；
- `scripts/report_e0_baseline.py`：从已保存预测生成 `metrics.json` 和 Markdown failure analysis。

## 3. 一条样本走完整流程

以 test 样本为例：

```text
user_text:
帮我找一部动画，排除带有“Female Harem”和“Mixed Gender Harem”标签的作品，状态为“RELEASING”。
```

调用流程：

```text
load_e0_inputs
-> E0InputRecord
-> build_inference_messages(system_prompt, user_text)
-> Qwen official chat template, enable_thinking=false
-> greedy model.generate
-> raw_model_output
-> strict_parse_prediction
-> structural validation
-> domain validation
-> canonicalization
-> Gold comparison
-> clause/field/error evaluation
-> E0PredictionRecord JSONL
```

Gold 中：

```json
{"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Mixed Gender Harem"]},"status":["RELEASING"]}
```

base model 实际预测把两个 tag 放入 `any_of`。解析、Schema 和 Domain 都合法，但语义错误。因此该样本得到：

```text
MISSING_CONSTRAINT
HALLUCINATED_CONSTRAINT
WRONG_OPERATOR
WRONG_VALUE
```

这说明 validity rate 不能代替 semantic exact match，正是分层 evaluator 需要保留的区别。

## 4. 最终结果

| Split | N | JSON | Schema | Domain | Exact | Hard P | Hard R | Hard F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Validation | 30 | 100.0% | 100.0% | 100.0% | 93.3% | 88.5% | 92.0% | 90.2% |
| Test | 30 | 100.0% | 100.0% | 100.0% | 76.7% | 83.7% | 72.0% | 77.4% |
| Challenge | 12 | 100.0% | 100.0% | 100.0% | 66.7% | 94.7% | 81.8% | 87.8% |

Test 的 7 个失败全部来自 `TAG_NONE + STATUS`，模型把 exclusion 错写成 `tags.any_of`。20 个 reference-composition test 样本全部 exact。Challenge 的主要失败是中文 genre 映射、reference title 丢失，以及复杂组合中多写 `year.max`。

## 5. 运行方式

```powershell
python scripts/run_e0_baseline.py --split smoke --determinism-check
python scripts/run_e0_baseline.py --split validation
# validation 调试完成并冻结 prompt_frozen 后：
python scripts/run_e0_baseline.py --split test
python scripts/run_e0_baseline.py --split challenge
python scripts/report_e0_baseline.py
```

正式 baseline 已按该顺序完成。train 的 180 条未进入 headline metrics，只有 3 条用于 smoke。

## 6. 停止边界

本阶段没有 optimizer、backward、adapter、LoRA/QLoRA、SFTTrainer、训练数据 serialization、tokenizer distribution audit、AniList enrichment 或 LLM paraphrase。
