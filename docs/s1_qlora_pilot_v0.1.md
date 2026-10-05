# S1. QLoRA SFT Pilot v0.1 — 实现与实验审查报告

审查日期：2026-10-04。项目：Anime Preference Understanding & Structured Recommendation Tool Calling。

本报告由工程助手直接整理，不调用 `render_s1_report()` 或报告生成脚本。报告渲染不再是用户需要实现的业务模块。

## 1. 阶段结论

S1 已完成冻结数据读取、completion-only tokenization、4-bit QLoRA 训练、best adapter 保存、独立重新加载，以及冻结 E0 evaluator 下的 Base vs SFT 比较。工程执行链检查通过，可提交理论分支审查。

实验结果是混合改善，不能概括为所有指标提升：

- Test Exact：23/30 → 30/30；test Hard P/R/F1 全部达到 100%。
- Challenge Exact：8/12 → 11/12；仍有 `challenge_009` 失败。
- Challenge Domain 有效率：100% → 91.7%；Hard F1：87.8% → 81.1%。
- 没有 Base exact 正确而 S1 exact 错误的样本，但一个原有失败样本出现了新的领域非法值。
- Validation 由 28/30 → 30/30。由于 best checkpoint 按 validation loss 选择，validation 不作为独立泛化的 headline。

工程可交付不等于理论侧已正式冻结。本轮没有新增训练数据、没有改 Gold、没有依据 test/challenge 调参或进行第二轮训练，也没有进行 AniList enrichment。

## 2. 证据来源和核验范围

主要机器可读证据：

- [完整对比与核验记录](D:/Study/anime-preference-sft/artifacts/s1/comparison.json)：包含两组指标、完整错误转移记录、训练身份、trainer state、三个推理身份、中文 slice、masking 核验和来源文件 SHA-256。
- [训练配置](D:/Study/anime-preference-sft/configs/s1_qlora_pilot.v0.1.json)。
- [训练身份](D:/Study/anime-preference-sft/artifacts/s1/run_identity.json)。
- [Trainer 状态与完整日志](D:/Study/anime-preference-sft/artifacts/s1/trainer/trainer_state.json)。
- E0 与 S1 各自的 validation/test/challenge prediction JSONL 和 S1 inference identity JSON，见本报告最后的文件清单。

本次审查重新读取 72 个相同 evaluation examples，对 Base/S1 合计 144 条保存的 raw output 调用原有 evaluator，逐字段核对保存记录。全部一致。还核对了实际数据与训练 sample ID hash、当前训练配置与保存 identity、实际 tokenizer/prompt hash、最终 adapter 与 best checkpoint 的权重 hash。

本次重新执行离线 tokenizer/CPU collator 验证与完整单元测试，没有重新训练或重新生成模型预测。之前 GPU forward/backward 和独立 adapter 重载的数值属于本会话实际运行证据，下面分别标明来源。

## 3. 相关业务代码和职责

以下路径均相对于 `D:\Study\anime-preference-sft`：

```text
configs/
  e0_baseline.v0.1.json
  e0_system_prompt.v0.2.txt
  s1_qlora_pilot.v0.1.json
data/pilot/
  train.v0.1.jsonl
  validation.v0.1.jsonl
  test.v0.1.jsonl
  challenge.v0.1.jsonl
src/anime_pref/
  schemas/s1_training.py
  training/
    sft_config.py
    sft_environment.py
    sft_data.py
    sft_tokenization.py
    sft_token_audit.py
    sft_collator.py
    sft_model.py
    sft_dataset.py
    sft_trainer.py
    sft_identity.py
  inference/
    hf_baseline.py
    hf_sft.py
  evaluation/
    e0_baseline.py
    s1_comparison.py
scripts/
  check_s1_nf4.py
  check_s1_training_step.py
  train_s1_pilot.py
  run_s1_evaluation.py
tests/
  test_sft_data.py
  test_sft_tokenization.py
  test_sft_token_audit.py
  test_sft_config.py
  test_sft_collator.py
  test_e0_baseline.py
```

| 文件 / 主要对象或函数 | 职责与关键边界 |
|---|---|
| `schemas/s1_training.py::S1TrainingConfig` | 用冻结配置对象描述数据、模型、量化、LoRA、优化器和输出路径。 |
| `sft_config.py::load_s1_config` | 验证字段集合、类型、合法范围与冻结合同；拒绝 bool 冒充 int、非有限数和配置漂移。 |
| `sft_environment.py::inspect_s1_environment` | 记录实际 Python、依赖版本、CUDA/GPU 和 BF16 支持情况。 |
| `sft_data.py::load_sft_records` | 只允许 train/validation，保留原顺序与已有重复文本，验证数量、字符串和 Gold 结构。 |
| `sft_data.py::build_sft_messages` | 生成 system/user/assistant；assistant 只有 canonical Gold，不包含 DatasetRecord provenance。 |
| `sft_tokenization.py::tokenize_sft_record` | 两次调用官方 chat template；检查 prompt token prefix，屏蔽 prompt，保留 completion labels。 |
| `sft_token_audit.py::audit_sft_token_lengths` | 统计 train min/median/nearest-rank p95/max 和 validation max，不静默截断。 |
| `sft_collator.py::SFTDataCollator` | 按 batch 最长序列右填充；padding attention=0、labels=-100；超长直接拒绝。 |
| `sft_model.py::load_s1_model` | 载入固定 revision，NF4 + double quant + BF16 compute；先准备 k-bit 模型，再挂载 LoRA；检查可训练参数范围。 |
| `sft_dataset.py::build_sft_features` | 按原顺序逐条构造 features；不去重、不裁剪，错误带 index/sample_id。 |
| `sft_trainer.py::build_s1_training_arguments` | 映射冻结配置，validation 仅收集 loss；非 reentrant gradient checkpointing，不额外保存巨大 logits。 |
| `sft_trainer.py::build_s1_trainer` | 组装模型、features 和 collator；构造函数本身不启动训练。 |
| `sft_identity.py::build_s1_run_identity` | 绑定真实模型、prompt/template、数据有序 ID hash、配置、环境和 token 长度，并核对 E0 identity。 |
| `hf_sft.py::HuggingFaceSFTAdapter` | 重载冻结 BF16 base 与已保存 LoRA；核对训练身份、LoRA 配置、prompt/template hash，推理参数全部冻结。 |
| `e0_baseline.py::evaluate_raw_prediction` | 原有 strict parse → structural/schema → domain → canonical comparison；不修复 raw output。 |
| `e0_baseline.py::build_e0_metrics_bundle` | 复用相同公式统计整体、family/count/signature 和 reference/normalization slices。 |
| `s1_comparison.py::build_s1_comparison_bundle` | 检查 Base/SFT 样本身份与推理条件一致，复用 metrics，保留 fixed/still_failed/regressed 的完整记录。 |

`scripts/report_s1_comparison.py` 是此前报告练习草稿，不在必需业务链中；本报告不依赖它。它没有因为本次整理而被删除或修改。

## 4. 调用流程与一个完整样本

### 4.1 训练链

```text
load_s1_config + load_e0_config/load_system_prompt
  → load_sft_records(train=180, validation=30)
  → load_s1_model（固定 revision，NF4 + LoRA）
  → build_sft_features
      → build_sft_messages
      → tokenize_sft_record
  → build_s1_run_identity / token-length audit
  → build_s1_trainer / SFTDataCollator
  → 保存 run identity
  → Trainer.train（仅 --train 启动）
  → 按 validation loss 回载 best checkpoint
  → save_model(adapter) / 保存 trainer state 和指标
```

样本 ID：`sample_86e1fe8eacb2ecc8a667e4c650577c440ad80534fc1cac14f73ba8cef9bcd51c`。

user text：`想找满足以下条件的动画：题材包含“Slice of Life”。`

1. 数据 loader 返回完整记录，样本身份只用于追踪，不进入模型消息。
2. `build_sft_messages(record, frozen_prompt)` 生成三条消息。assistant Gold 中只有 `genres.all_of=["Slice of Life"]`，其余显式字段保留空列表/null。
3. `tokenize_sft_record(record, prompt, tokenizer)` 用 `enable_thinking=False` 的官方模板生成 602-token prompt prefix 和 682-token 完整序列。
4. `labels[:602]` 全为 `-100`；其后 80 个 completion token 与 input token 相同。completion 包含 JSON 以及官方模板的 `<|im_end|>` 和末尾换行，不包含 DatasetRecord provenance。
5. 单样本 batch 的 `input_ids/attention_mask/labels` 都是 `(1, 682)`。模型内部负责 causal shift，不手动移动 labels。
6. NF4 base 保持冻结，LoRA 接收反向梯度。训练结束保存 validation 选定的 adapter。

### 4.2 独立推理与比较链

```text
冻结 E0 配置 / system prompt
  → HuggingFaceSFTAdapter
      → 身份与 saved LoRA config 检查
      → 原 E0 BF16 base/tokenizer 加载
      → PeftModel.from_pretrained(saved adapter, is_trainable=False)
  → load_e0_inputs(split)
  → generate_all（greedy，batch=2，只输入 system + user）
  → evaluate_raw_prediction（原 E0 evaluator）
  → 保存完整 raw prediction 与 split inference identity
  → build_s1_comparison_bundle（相同样本、相同推理条件）
```

训练用右填充；decoder-only 批量推理复用 E0 左填充。这是两个不同环节。最终 evaluation 使用非量化 BF16 base + LoRA，与 E0 保持同一加载精度，不将 NF4 训练加载方式带入本轮最终比较。

## 5. 模型、环境、数据和训练配置

### 5.1 实验身份

| 项目 | 值 |
|---|---|
| Model / tokenizer | `Qwen/Qwen3-4B` |
| Revision | `1cfa9a7208912126459214e8b04321603b3df60c` |
| S1 version | `s1-qlora-pilot-v0.1` |
| Dataset version | `anime-pref-pilot-v0.1` |
| Prompt version | `e0-json-extraction-v0.2` |
| Serialization identity | `qwen3-official-chat-template-nonthinking-v1` |
| Python | 3.14.2 |
| GPU | NVIDIA GeForce RTX 5070 |
| torch / CUDA runtime | 2.11.0+cu130 / 13.0 |
| transformers | 4.57.6 |
| peft | 0.21.2 |
| accelerate | 1.15.0 |
| bitsandbytes | 0.50.2 |
| CUDA / BF16 | 可用 / 支持 |
| Trainer | 标准 Transformers Trainer；本轮不使用 TRL |

### 5.2 数据边界

| Split | N | 用途 |
|---|---:|---|
| train | 180 | 训练；保留冻结 train 中已有重复文本 |
| validation | 30 | validation loss、checkpoint selection 和后续生成评估 |
| test | 30 | 训练完成后冻结评估，不参与训练/调参 |
| challenge | 12 | 训练完成后人工挑战集评估，不参与训练/调参 |

本次额外核对 exact `(user_text, canonical Gold)` intersection：train↔validation、train↔test、validation↔test、train↔challenge 均为 0。Gold 在这个 intersection 检查中按 key 排序和 compact JSON 序列化，仅用于审查，不改 dataset/sample_id 或训练输入。

当前 domain validation 使用 `tests/fixtures/domain_rules.synthetic.v0.1.json`。这些是冻结 pilot 的 synthetic 测试规则，不是 production AniList taxonomy/subset acceptance。不能把本轮结果视为 production vocabulary 验收。

### 5.3 完整训练配置

下面是本次训练配置的内容；本次核对它与 `run_identity.json.training_config` 一致。

```json
{
  "s1_version": "s1-qlora-pilot-v0.1",
  "model_id": "Qwen/Qwen3-4B",
  "tokenizer_id": "Qwen/Qwen3-4B",
  "revision": "1cfa9a7208912126459214e8b04321603b3df60c",
  "local_files_only": true,
  "dataset_version": "anime-pref-pilot-v0.1",
  "train_path": "data/pilot/train.v0.1.jsonl",
  "validation_path": "data/pilot/validation.v0.1.jsonl",
  "train_expected_count": 180,
  "validation_expected_count": 30,
  "prompt_version": "e0-json-extraction-v0.2",
  "prompt_path": "configs/e0_system_prompt.v0.2.txt",
  "serialization_identity": "qwen3-official-chat-template-nonthinking-v1",
  "enable_thinking": false,
  "max_seq_length": 768,
  "load_in_4bit": true,
  "bnb_4bit_quant_type": "nf4",
  "bnb_4bit_use_double_quant": true,
  "bnb_4bit_compute_dtype": "bfloat16",
  "lora_target_modules": [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj"
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
  "num_train_epochs": 3,
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
  "trainer_output_dir": "artifacts/s1/trainer",
  "adapter_output_dir": "artifacts/s1/adapter",
  "run_identity_path": "artifacts/s1/run_identity.json"
}
```

训练主配置只运行一次。LoRA 同时覆盖 attention 与 MLP 的七个 projection modules，embedding、lm_head 和其他 base 参数不训练。实际模型准备阶段检查到 504 个可训练 LoRA tensor，共 33,030,144 个可训练参数；这是此前工程预检的运行证据。

## 6. Token 长度、masking 和梯度证据

### 6.1 长度统计：本次离线重算与训练 identity 一致

| 统计 | 值 |
|---|---:|
| Train count | 180 |
| Train min | 675 |
| Train median | 691.0 |
| Train p95（nearest rank） | 706 |
| Train max | 718 |
| Validation count / max | 30 / 705 |
| Overall max | 718 |
| Chosen max_seq_length | 768 |

未裁剪 Gold；超出 max_seq_length 的 feature 会报错，而不是静默 truncation。本次没有 packing。

### 6.2 本次重新执行的离线 masking/padding 核验

- 首条 train 样本：完整长度 682；prompt 屏蔽 602；监督 completion 80。
- prompt labels 全部为 `-100`；completion labels 与 input IDs 完全相同。
- 解码 completion 为 canonical Gold JSON + `<|im_end|>` + 换行。
- 用真实样本组成 `(2, 699)` CPU batch；较短样本长度 678，其右侧 padding labels 全为 `-100`，attention mask 全为 0。
- tokenizer 实际 chat template 和 system prompt 的 hash 与训练 identity 一致。

### 6.3 此前实际 GPU 工程预检的终端证据

`python scripts/check_s1_nf4.py`：

```text
GPU: NVIDIA GeForce RTX 5070
input shape: (2, 4, 64)
output shape: (2, 4, 32)
output dtype: torch.bfloat16
loss: 0.35545483231544495
input gradient: finite and nonzero
quantized weight gradient: None
NF4 forward/backward: PASS
```

`python scripts/check_s1_training_step.py`：

```text
input_ids (1, 682) torch.int64 cuda:0
attention_mask (1, 682) torch.int64 cuda:0
labels (1, 682) torch.int64 cuda:0
masked prompt tokens: 602
supervised tokens: 80
loss: 0.2765079438686371
LoRA tensors with gradients: 504
LoRA tensors with nonzero gradients: 252
frozen base gradients: None
peak allocated MiB: 5794.2
real SFT forward/backward: PASS
```

这两段是用户在本会话提供、先前审查通过的 GPU 运行输出，本次整理报告没有重跑它们。训练步检查只 forward/backward，没有 optimizer step。初始化时并非所有 LoRA tensor 的梯度都非零，不因此将 252/504 判定为训练失败。

## 7. 训练运行与 checkpoint selection

执行命令：`python scripts/train_s1_pilot.py --train`。

运行 3 epochs，共 69 optimizer steps；总耗时 409.5314 秒；Trainer 汇总 train loss 为 0.007255849483202758。

### 7.1 Training log

以下是 trainer state 中已记录的 logging windows。loss 的显示值不是每个 epoch 的全量均值；`0.0` 是已记录的显示精度值，不能解释为数学上的零误差。

| Step | Epoch（约） | Train loss | Learning rate | Grad norm |
|---:|---:|---:|---:|---:|
| 5 | 0.22 | 0.0872 | 1.142857e-4 | 0.601772 |
| 10 | 0.44 | 0.0068 | 1.935484e-4 | 0.056137 |
| 15 | 0.67 | 0.0037 | 1.774194e-4 | 0.049945 |
| 20 | 0.89 | 0.0017 | 1.612903e-4 | 0.030003 |
| 25 | 1.09 | 0.0001 | 1.451613e-4 | 0.003299 |
| 30 | 1.31 | 0.0002 | 1.290323e-4 | 0.003252 |
| 35 | 1.53 | 0.0001 | 1.129032e-4 | 0.002156 |
| 40 | 1.76 | 0.0001 | 9.677419e-5 | 0.000973 |
| 45 | 1.98 | 0.0001 | 8.064516e-5 | 0.003239 |
| 50 | 2.18 | 0.0 | 6.451613e-5 | 0.001338 |
| 55 | 2.40 | 0.0 | 4.838710e-5 | 0.000555 |
| 60 | 2.62 | 0.0 | 3.225806e-5 | 0.000708 |
| 65 | 2.84 | 0.0 | 1.612903e-5 | 0.000963 |

### 7.2 Validation loss

| Epoch | Step | Eval loss | 是否 best |
|---:|---:|---:|---|
| 1 | 23 | 0.003476276295259595 | 是 |
| 2 | 46 | 0.0526532307267189 | 否 |
| 3 | 69 | 0.05379656329751015 | 否 |

训练 loss 继续下降，而 epoch 2/3 validation loss 明显升高，是本轮出现过拟合迹象的证据。已有 `load_best_model_at_end=true` 按最低 validation loss 回载 epoch 1 / checkpoint-23；最终 adapter 不是 epoch 3 权重。

这一选择在 test/challenge 生成之前完成。没有根据 test/challenge 的结果重新选择 epoch、LR 或 rank。Teacher-forced validation loss 与生成 Exact 是不同指标，分别报告。

## 8. 保存、独立重载与推理身份

### 8.1 核验 hash

| Identity | SHA-256 |
|---|---|
| System prompt | `80372e73bf41bf7529374c15503e83637ad6e96985cd2220d37d35f16d310b1c` |
| Actual chat template | `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8` |
| Ordered train sample IDs | `8eae2e104aafdb351f2c2b685123aa80b69d153a5ce239c96c0cce9719be013c` |
| Ordered validation sample IDs | `fc2143bb47276b489eaf89a69a9c881d93f9dfc35d245b9220e2ac1f040c149a` |
| Saved adapter weights / checkpoint-23 weights | `18ba7e71cb2ba516349a648eddd2d08c6862b07bd0815ac47c9e51f84d9c6081` |

最终 `artifacts/s1/adapter/adapter_model.safetensors` 与 checkpoint-23 的文件 SHA-256 相同。本次三个 inference identity 也都记录这一 adapter hash，并与训练和 E0 identity 的 prompt/template hash 一致。

### 8.2 独立重载的既有实际验证

训练进程结束后，工程助手在另一进程载入冻结 BF16 base + saved adapter，对首条 train 输入连续生成两次：输出一致；JSON/schema/domain 全通过，Exact=True。运行检查还确认 `is_loaded_in_4bit=False`、BF16 base 参数精度、推理参数全部冻结、tokenizer 左填充。这个 smoke 使用 train 输入，仅用于验证 save/reload 和 generation 可用，不作为泛化证据。

三个 evaluation splits 分别在独立运行中重载 saved adapter，没有依赖训练进程内存中的模型，也没有 merge adapter。

冻结推理设置：`enable_thinking=false`、`do_sample=false`、`num_beams=1`、`max_new_tokens=512`、`batch_size=2`，使用同一 system prompt、官方 chat template、strict parser 和 evaluator。

终端出现的 Triton FLOP counting 警告，以及 greedy 下 temperature/top_p/top_k 可能忽略的提示，没有导致执行失败。主推理由显式 `do_sample=false` 控制，不据这些警告改变冻结配置。

## 9. Base vs SFT 整体指标

采用冻结 E0 evaluator。指标为样本有效率、canonical full-query exact 和 hard-clause micro P/R/F1；不是 token accuracy。

| Split | Model | N | JSON | Schema | Domain | Exact | Hard P | Hard R | Hard F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| validation | Base | 30 | 100.0% | 100.0% | 100.0% | 93.3% | 88.5% | 92.0% | 90.2% |
| validation | S1 | 30 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| test | Base | 30 | 100.0% | 100.0% | 100.0% | 76.7% | 83.7% | 72.0% | 77.4% |
| test | S1 | 30 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| challenge | Base | 12 | 100.0% | 100.0% | 100.0% | 66.7% | 94.7% | 81.8% | 87.8% |
| challenge | S1 | 12 | 100.0% | 100.0% | 91.7% | 91.7% | 100.0% | 68.2% | 81.1% |

| Split | Model | TP | FP | FN |
|---|---|---:|---:|---:|
| validation | Base | 46 | 6 | 4 |
| validation | S1 | 50 | 0 | 0 |
| test | Base | 36 | 7 | 14 |
| test | S1 | 50 | 0 | 0 |
| challenge | Base | 18 | 1 | 4 |
| challenge | S1 | 15 | 0 | 7 |

S1 validation/test 的九个 field exact accuracy 均为 100%。S1 challenge 的九个 field exact accuracy 均为 91.7%，因为领域非法的 `challenge_009` 没有 canonical_prediction，所有字段的官方比较都判 False。这不表示该样本九个字段的 raw values 都有错误。

## 10. 重点 probes 与退化检查

### 10.1 Test `TAG_NONE + STATUS`

| N | Base Exact | S1 Exact | Base Hard P / R / F1 | S1 Hard P / R / F1 |
|---:|---:|---:|---|---|
| 10 | 3/10（30.0%） | 10/10（100.0%） | 69.6% / 53.3% / 60.4% | 100.0% / 100.0% / 100.0% |

这一 held-out signature 的七条 Base 错误全部修正。Base 的错误标签包含 MISSING_CONSTRAINT、HALLUCINATED_CONSTRAINT、WRONG_OPERATOR、WRONG_VALUE；S1 该 slice 全部通过。Test 其余 `EPISODE_MIN` 和 `FORMAT` 各 10 条也保持 100% Exact。

### 10.2 Chinese genre challenge

固定 slice 是 `challenge_002/003/009`，完整 query Exact 为 0/3 → 2/3。

| ID | User text | Base Exact | S1 Exact |
|---|---|---|---|
| challenge_002 | 悬疑或科幻题材都可以。 | False | True |
| challenge_003 | 想看同时包含悬疑和科幻题材的动画。 | False | True |
| challenge_009 | 想看2010年及以后、最多24集的悬疑或科幻TV动画，不要后宫。 | False | False |

002/003 表明本轮在这两个人工样本上能够正确表达 Mystery/Sci-Fi 的 ANY/ALL。009 的 S1 raw genres.any_of 也是正确值，但其整条 query domain invalid，因此不能给它官方 field correctness 的部分分。

没有为了这三个 challenge 往 train 添加答案，也不据此声称任意中文 alias 已可靠泛化。

### 10.3 Reference

| Split | N | Base full-query Exact | S1 full-query Exact |
|---|---:|---:|---:|
| validation | 10 | 100.0% | 100.0% |
| test | 20 | 100.0% | 100.0% |
| challenge | 1 | 0.0% | 100.0% |

已有 reference composition 未出现 exact regression；`challenge_004`（想找类似《Steins;Gate》的作品。）的引用错误得到修正。Reference slice 仍只有现有样本规模，不代表 resolver/AniList ID 匹配已经完成。

### 10.4 HAREM normalization

validation/test 当前没有 generic HAREM normalization slice，值为 null，不报告成 100%。Test 的 explicit Harem tag exclusions 是 direct-tag probe，与 generic concept normalization 区分。

challenge 的 generic normalization slice 只有 2 条：

| 指标 | Base | S1 |
|---|---:|---:|
| N | 2 | 2 |
| JSON / Schema | 100.0% / 100.0% | 100.0% / 100.0% |
| Domain | 100.0% | 50.0% |
| Full-query Exact | 50.0% | 50.0% |
| Official tags field accuracy | 100.0% | 50.0% |
| Hard F1 | 90.0% | 46.2% |

`challenge_009` raw tags.none_of 确实包含三个冻结 HAREM target，展开值正确；正式 slice 的 domain/tags/F1 却因整条 query 非法而下降。报告保留正式退化，同时提供 raw 层诊断，不将 raw 层正确当成正式评估通过。

## 11. 错误转移和所有剩余失败

### 11.1 Exact 层转移

| Split | fixed：False→True | still_failed：False→False | regressed：True→False |
|---|---:|---:|---:|
| validation | 2 | 0 | 0 |
| test | 7 | 0 | 0 |
| challenge | 3 | 1 | 0 |

验证集的两条修正是 genre exclusion（Ecchi + Romance / Ecchi + Mystery）；Base 原来错误生成了 HAREM exclusions。Test 的七条修正全部在 `TAG_NONE + STATUS`。Challenge 修正 002、003、004。

`regressed=0` 只表示没有 exact 从正确变错误，不能据此忽略新的 DOMAIN_ERROR。详细逐条 Base/SFT full records 均保存在 comparison JSON 的 transitions 中。

### 11.2 Error taxonomy

| Split / model | 非零错误标签计数 |
|---|---|
| validation Base | MISSING_CONSTRAINT=2；HALLUCINATED_CONSTRAINT=2 |
| validation S1 | 无 |
| test Base | MISSING_CONSTRAINT=7；HALLUCINATED_CONSTRAINT=7；WRONG_OPERATOR=7；WRONG_VALUE=7 |
| test S1 | 无 |
| challenge Base | MISSING_CONSTRAINT=3；HALLUCINATED_CONSTRAINT=1；WRONG_NUMERIC_BOUND=1；REFERENCE_ERROR=1 |
| challenge S1 | DOMAIN_ERROR=1 |

这些标签沿用原 evaluator 的层级与互斥规则。DOMAIN_ERROR 发生后不继续添加下游 semantic labels。因此 S1 中 WRONG_NUMERIC_BOUND=0 不表示 raw year bounds 全部正确。

### 11.3 唯一剩余失败：challenge_009

User text：**想看2010年及以后、最多24集的悬疑或科幻TV动画，不要后宫。**

Gold：

```json
{
  "hard_constraints": {
    "genres": {"all_of": [], "any_of": ["Mystery", "Sci-Fi"], "none_of": []},
    "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Male Harem", "Mixed Gender Harem"]},
    "year": {"min": 2010, "max": null},
    "episodes": {"min": null, "max": 24},
    "formats": ["TV"],
    "status": []
  },
  "reference_titles": [],
  "soft_preferences": [],
  "unresolved_preferences": []
}
```

Base 保存的原始输出（未修复）：

```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":2010},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```

S1 保存的原始输出（未修复）：

```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery","Sci-Fi"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":2010},"episodes":{"min":null,"max":24},"formats":["TV"],"status":["TV"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```

| 字段 | Gold | Base | S1 |
|---|---|---|---|
| genres.any_of | Mystery / Sci-Fi | [] | 正确 |
| year.min | 2010 | 正确 | 正确 |
| year.max | null | 2010，错误 | 2010，错误保留 |
| episodes.max | 24 | 正确 | 正确 |
| formats | [TV] | 正确 | 正确 |
| status | [] | 正确 | [TV]，新增错误 |
| tags.none_of | 三个 HAREM targets | 正确 | 正确 |

S1 解析和 schema 通过，domain 失败。保存的 domain_error：

```text
hard_constraints.status contains values outside domain rules: ['TV']
```

Base 标签：`MISSING_CONSTRAINT`、`HALLUCINATED_CONSTRAINT`、`WRONG_NUMERIC_BOUND`。S1 标签：`DOMAIN_ERROR`。

S1 raw 层修正了 genre ANY，但继承了把 inclusive lower bound 误变为 exact year 的错误，又新增了把 format TV 复制到 status 的错误。

冻结 evaluator 对 domain-invalid query 不生成 canonical_prediction，predicted hard-clause set 为空。该条 Gold 具有 7 个评估 hard clauses：genre ANY=1、三个独立 tag exclusions=3、year.min=1、episodes.max=1、format OR=1。于是该条 S1 TP=0、FP=0、FN=7。

其他 11 条 challenge 的有效预测贡献 TP=15、FP=0、FN=0；合计 recall=15/22=68.2%，F1=30/37=81.1%。这说明 Exact 提升与 Hard F1 下降可以同时成立，也解释了 domain gate 下 Precision=100% 不能单独代表所有 raw output 没有幻觉。

评估 hard-clause 计数复用现有 evaluator；它与 pre-expansion DatasetRecord.constraint_count 的语义计数不是同一个用途。没有为了本次结果改公式、修复模型输出或修改 Gold。

## 12. 验证与命令结果

### 12.1 本次完整工程测试

```text
python -m unittest discover -s tests
----------------------------------------------------------------------
Ran 441 tests in 20.416s

OK
```

退出码 0。测试数量是现有工程 suite，不声称 441 项全都专门测试 S1。`s1_comparison` 的真实数据/非法输入专项核验为会话中的临时检查，未新增持久化 test 文件。

### 12.2 其他审查结果

- Base/S1 144 条 raw outputs 重新评估，保存记录完全一致。
- 72 个 evaluation examples 的 ID、文本、Gold、revision、prompt、serialization 和 generation config 对齐。
- 当前训练配置、train/validation ordered ID hashes 与训练 identity 一致。
- 210 条 train/validation 的实际 token 长度重算与 identity 一致。
- 实际 completion-only labels 和不同长度样本的 padding 核验通过。
- saved adapter、best checkpoint 与三份推理身份的权重 hash 一致。
- `build_s1_comparison_bundle` 的真实转移计数、指标复用、输入不修改、JSON serialization 核验通过；临时检查还覆盖 12 种非法输入及 isolation 下的 regression 分类分支。
- evaluation runner 的 validation/test/challenge 模拟流程、原始输出保留、顺序、错误数量/重复 ID、非法 split、输出禁止覆盖核验通过。

### 12.3 已完成的实际生成

```text
python scripts/run_s1_evaluation.py --split validation
预测总数：30
exact_match 为 True 的数量：30

python scripts/run_s1_evaluation.py --split test
预测总数：30
exact_match 为 True 的数量：30

python scripts/run_s1_evaluation.py --split challenge
预测总数：12
exact_match 为 True 的数量：11
```

validation 最初运行时脚本尚未引入 `--split` 参数；其保存结果已在参数化版本完成后核对，本次没有覆盖或重新生成 validation。

## 13. 局限与理论侧需要判断的问题

1. 这是 180-train / 30-test / 12-challenge 的 pilot，有限模板、vocabulary 和结构覆盖不能支持 production 泛化结论。多值 format/status OR、复杂度 4/5+ 与更广泛语言变体的充分覆盖尚未完成。
2. Generic HAREM normalization 的 headline evidence 只有 challenge 2 条；不能以 raw expansion 正确掩盖该 slice 的 official validity/F1 下降。
3. Challenge Domain 下降是新增的可执行性退化，尽管没有 exact True→False。理论侧应同时考虑完整 query 通过率与 fail-closed hard-clause metrics。
4. 中文样本中 ANY/ALL 的两个基础例子改善，组合例子仍有 year/status isolation 错误。不能仅根据 2/3 就批准全面中文 alias 能力。
5. Epoch 2/3 的 validation loss 升高已由 best-checkpoint selection 控制；本轮仅一套训练主配置，不进行 test-informed 二次调参。
6. Production AniList snapshot/audit/subset acceptance 继续不在本次结果中；当前 synthetic identities 仍不得用于 production。

建议理论审查聚焦：是否接受 S1 工程闭环与混合指标作为首轮证据；如何在保留冻结评估口径的前提下看待 challenge domain/F1 退化；下一阶段是否单独授权 field isolation、numeric bounds、语言覆盖或其他数据迭代。本报告不提前落实任何第二轮 augmentation、paraphrase 或训练。

## 14. 交付清单

- 本报告：[s1_qlora_pilot_v0.1.md](D:/Study/anime-preference-sft/docs/s1_qlora_pilot_v0.1.md)。
- 完整机器可读证据：[comparison.json](D:/Study/anime-preference-sft/artifacts/s1/comparison.json)。
- [training config](D:/Study/anime-preference-sft/configs/s1_qlora_pilot.v0.1.json)、[run identity](D:/Study/anime-preference-sft/artifacts/s1/run_identity.json)、[trainer state](D:/Study/anime-preference-sft/artifacts/s1/trainer/trainer_state.json)。
- S1：[validation predictions](D:/Study/anime-preference-sft/artifacts/s1/evaluation/validation_predictions.jsonl)、[test predictions](D:/Study/anime-preference-sft/artifacts/s1/evaluation/test_predictions.jsonl)、[challenge predictions](D:/Study/anime-preference-sft/artifacts/s1/evaluation/challenge_predictions.jsonl)。
- S1：[validation identity](D:/Study/anime-preference-sft/artifacts/s1/evaluation/validation_inference_identity.json)、[test identity](D:/Study/anime-preference-sft/artifacts/s1/evaluation/test_inference_identity.json)、[challenge identity](D:/Study/anime-preference-sft/artifacts/s1/evaluation/challenge_inference_identity.json)。
- E0：[validation predictions](D:/Study/anime-preference-sft/artifacts/e0/validation_predictions.jsonl)、[test predictions](D:/Study/anime-preference-sft/artifacts/e0/test_predictions.jsonl)、[challenge predictions](D:/Study/anime-preference-sft/artifacts/e0/challenge_predictions.jsonl)。
- [saved adapter config](D:/Study/anime-preference-sft/artifacts/s1/adapter/adapter_config.json)、[adapter weights](D:/Study/anime-preference-sft/artifacts/s1/adapter/adapter_model.safetensors)。权重无需作为理论语义审查的聊天附件；hash 和重载证据已提供。

理论分支首先读取 Markdown 和 comparison JSON 即可审查主要结论；需要逐文件追溯时再使用以上源文件。工程侧在提交后停止，不自行开启下一阶段。
