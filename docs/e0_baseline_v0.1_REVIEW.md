# E0 Base-Model Baseline Evaluation v0.1 Review Bundle

## 状态

工程实现和真实 Qwen3-4B GPU baseline 已完成，等待理论审查。本轮没有执行任何训练。

## 交付文件

- `configs/e0_baseline.v0.1.json`
- `configs/e0_system_prompt.v0.1.txt`
- `configs/e0_system_prompt.v0.2.txt`
- `requirements-e0.txt`
- `src/anime_pref/schemas/e0_baseline.py`
- `src/anime_pref/inference/hf_baseline.py`
- `src/anime_pref/evaluation/e0_baseline.py`
- `scripts/run_e0_baseline.py`
- `scripts/report_e0_baseline.py`
- `tests/test_e0_baseline.py`
- `artifacts/e0/run_identity.json`
- `artifacts/e0/determinism_check.json`
- `artifacts/e0/validation_predictions.prompt_v0.1.jsonl`
- `artifacts/e0/validation_predictions.jsonl`
- `artifacts/e0/test_predictions.jsonl`
- `artifacts/e0/challenge_predictions.jsonl`
- `artifacts/e0/metrics.json`
- `docs/e0_baseline_v0.1.md`
- `docs/e0_baseline_v0.1_IMPLEMENTATION.md`

## Run identity

```text
model_id              Qwen/Qwen3-4B
revision              1cfa9a7208912126459214e8b04321603b3df60c
prompt_version        e0-json-extraction-v0.2
prompt_frozen         true
serialization         qwen3-official-chat-template-nonthinking-v1
enable_thinking       false
do_sample             false
num_beams             1
max_new_tokens        512
dtype                 bfloat16
GPU                   NVIDIA GeForce RTX 5070
```

同 checkpoint/prompt/input 的真实双次生成 SHA-256 一致，结果记录在 `determinism_check.json`。

## Prompt selection discipline

prompt v0.1 只运行 validation：JSON 100%、Schema/Domain 76.7%、Exact 70.0%。根据 validation 暴露的 numeric field leakage 和 false HAREM trigger 修订为 v0.2。

v0.2 validation：JSON/Schema/Domain 100%、Exact 93.3%、Hard F1 90.2%。随后将 `prompt_frozen=true`，才首次运行 test/challenge。没有查看 test 后再修改 prompt 或重跑挑选结果。

## Headline metrics

| Split | N | JSON | Schema | Domain | Exact | Hard P/R/F1 |
|---|---:|---:|---:|---:|---:|---:|
| validation | 30 | 100.0% | 100.0% | 100.0% | 93.3% | 88.5% / 92.0% / 90.2% |
| test | 30 | 100.0% | 100.0% | 100.0% | 76.7% | 83.7% / 72.0% / 77.4% |
| challenge | 12 | 100.0% | 100.0% | 100.0% | 66.7% | 94.7% / 81.8% / 87.8% |

## 关键证据

- 30 validation、30 test、12 challenge 每条各有一个 retained raw prediction；
- primary parser 对整段文本严格 `json.loads`，repair 不进入 primary metrics；
- canonical exact match 忽略 JSON key/set order，但不忽略字段、operator 或 value；
- 九个字段 exact accuracy、hard clause P/R/F1、family/count/signature slices 均在 `metrics.json`；
- HAREM normalization 和 reference behavior 单独输出；
- 报告包含全部 11 个 test/challenge failure cases；
- inference 模块没有 optimizer、backward、adapter 或训练依赖；
- prompt message API 不接收 Gold。

## 主要 failure evidence

1. Test 中 `TAG_NONE + STATUS` 共 10 条，仅 3 条 exact。其余 7 条把明确 exclusion 放入 `tags.any_of`，导致 wrong operator/value、missing 与 hallucinated constraint。
2. Test 中 20 条 reference composition 全部 exact，未从 reference title hallucinate hidden hard constraints。
3. Challenge 中“悬疑/科幻”中文领域表达有 2 条未映射到 canonical genres。
4. Challenge reference-only 有 1 条丢失 `Steins;Gate`，但没有额外 hallucinated hard field。
5. 两条 HAREM challenge 的 tags field 均正确；其中复杂组合样本因额外写入 `year.max=2010` 导致整体 exact 失败。

## 验证结果

最终工程验证结果：

```text
E0 专项测试: 21 passed in 0.020s
完整工程测试: 405 passed in 20.575s
compileall: PASS
git diff --check: PASS
skip/expectedFailure: 0
```

