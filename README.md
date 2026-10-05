# Anime Preference Understanding & Structured Recommendation Tool Calling

将用户明确表达的动画偏好解析为完整 JSON，再在本地 AniList catalog 中过滤、排序并返回推荐。模型负责偏好理解，AniList 负责作品事实；参考作品的属性不会变成用户未表达的硬约束。

```text
Natural-language user input
          ↓
Qwen3-4B + saved QLoRA adapter
          ↓
Raw JSON → strict parse → Schema / Domain validation
          ↓
Offline AniList catalog → hard filtering → deterministic ranking
          ↓
CLI: structured query + top-k anime
```

## 当前数据与模型

- Base: `Qwen/Qwen3-4B`, revision `1cfa9a7208912126459214e8b04321603b3df60c`。
- 真实 AniList catalog：1,544 部；热门作品、电影、近期条目与较早年份作品分组分页获取，34 个原始页面缓存。
- 完整 taxonomy：19 genres / 428 tags；v0.2 active genres 18 个，明确选择 83 个 executable tags（adult/spoiler flag 不允许进入）。
- Tag selection 为用户授权的工程审核，记录实际 ID/name/category/flags/hash；不声称独立人工专家审核。
- Reference title pool：200 个真实 catalog 标题；Gold 保持字符串，resolver IDs 单独保存。
- 最终数据：1,500 条；train 1,200 / validation 150 / test 150；独立 challenge 40 条。
- 83 个简单 reviewed structural patterns、18 种受控句式，覆盖 ALL/ANY/NONE、含端点数值范围、format/status、reference、HAREM 和 complexity 1–5。
- Gold 来自 SemanticSpec 和现有 deterministic builder。E3 负责具体值绑定，模型不生成 Gold。
- train/validation/test/challenge 之间 exact user text 与 exact text+Gold overlap 均为零。

完整数据统计：[data/final/audit.json](data/final/audit.json)。真实 lineage 见 `data/domain/`；历史 synthetic fixtures 只用于离线测试与旧 pilot。

## Schema

Gold 和模型输出使用 Schema v0.1.1 的完整字段，未表达条件保留空列表或 null：

```json
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```

ALL 要求全部值；ANY 是一个 OR clause；NONE 排除所有指定值。formats/status 是 OR 列表。年份与集数上下界包含端点。通用后宫在正向 tags.any_of、负向 tags.none_of 展开成 Female Harem/Male Harem/Mixed Gender Harem。

结构校验与领域校验分层执行。应用不修复非法输出：JSON 错误返回 `parse_failed`，结构或领域错误返回 `validation_failed`。无法满足硬约束时返回 `no_matches`；unresolved preferences 会显示未执行的 warning。

## 环境与快速演示

本次实际环境：Windows / NVIDIA RTX 5070 12 GB / Python 3.14；依赖版本在 `requirements-s1.txt` 和 run identity 中固定。需要 CUDA GPU、支持 BF16，以及约 10–11 GB 可用显存。新环境先建立虚拟环境并安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-s1.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

模型加载使用本地缓存并绑定固定 revision；新机器需先下载同一 snapshot：

```powershell
.\.venv\Scripts\python.exe scripts/download_base_model.py
```

已完成训练的本项目目录直接运行：

```powershell
.\.venv\Scripts\python.exe scripts/recommend.py "悬疑或者科幻都可以，不要后宫。" --top-k 5
.\.venv\Scripts\python.exe scripts/recommend.py --interactive
```

输出包括 raw model JSON、canonical parsed query、candidate_count、作品标题/年份/format/episodes/genres/tags/score，以及 score components。模型每个进程加载一次；交互模式复用它。

十个真实完整演示见 `artifacts/final/demo_results.json` 与 [最终报告](review_bundle/final_project/REVIEW.md)。离线检索不会在每次推荐时访问 AniList。

## 数据构建

```powershell
.\.venv\Scripts\python.exe scripts/fetch_catalog.py
.\.venv\Scripts\python.exe scripts/build_final_data.py
.\.venv\Scripts\python.exe scripts/prepare_final_config.py
```

采集器按分页缓存恢复，并保存真实 taxonomy source/canonical/manifest。Catalog 保存完整项目所需字段，包括 startDate、seasonYear、media-specific tag rank、averageScore 和 popularity。质量/流行度只用于 ranking，不进入 Gold。

`build_final_data.py` 使用固定 seed、reviewed patterns、E3 binder、受控中文/英文词表与句式，再调用原有 DatasetRecord builder。Identity 包含 rules/subset provenance。Numeric cutoff sampling 与 schema sanity bounds 分离；v0.2 value pools 位于 versioned config。

`prepare_final_config.py` 用真实 tokenizer 统计 train/validation 长度，再决定能覆盖全部序列的 max length。本次为 1,792，实际最大 1,729。无 packing、无静默截断。

## QLoRA 训练与保存

```powershell
.\.venv\Scripts\python.exe scripts/train_final.py --train
```

复用 S1 的 NF4、double quant、BF16 compute 与 PEFT/Transformers Trainer；LoRA r=16 / alpha=32 / dropout=0.05，覆盖 q/k/v/o/gate/up/down projections。只训练 LoRA A/B，embedding/lm_head/base 权重冻结。

Completion-only loss：system/user 和 padding labels=-100；assistant canonical JSON 与官方终止 tokens 使用实际 token IDs。使用 Qwen3 官方模板、enable_thinking=false。训练右 padding，生成左 padding。

预先选定 1 epoch、LR=2e-4、batch size=1、gradient accumulation=8、gradient checkpointing；该选择基于 S1 在 epoch 2/3 的过拟合迹象，未使用本轮 test/challenge 调参。Checkpoint 按 validation loss 选择，保存到 `artifacts/final/adapter/`。未 merge。

已有训练 identity/adapter 时，脚本拒绝覆盖。复现实验应先为新实验配置独立输出目录；不要删除当前证据重跑。

## 评估与 before/after

```powershell
.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model base
.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model s1
.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model final
.\.venv\Scripts\python.exe scripts/run_demo_cases.py
.\.venv\Scripts\python.exe scripts/report_final_project.py
```

三个模型的每个 split 都在独立进程加载 frozen BF16 base，再按需加载 saved adapter。全部使用同一 v0.2 prompt、官方 chat template、greedy decoding、batch_size=1、max_new_tokens=512、同一 test/challenge 与真实 DomainRules，复用原 E0 strict evaluator。已完成的 split 可以安全续跑；不覆盖已有输出，最终报告逐条复核数据与推理身份。

指标包括 JSON/schema/domain validity、canonical full-query Exact、hard clause micro P/R/F1、各字段准确率、reference/HAREM slices、所有 raw failures 和错误转移。最终报告会重新评估所有保存的 raw output 并核对 identity。

历史 pilot 指标：Base→S1 Test Exact 76.7%→100%；Challenge Exact 66.7%→91.7%，但 Challenge Domain 100%→91.7%、Hard F1 87.8%→81.1%。这些属于旧 v0.1 数据/prompt；不可直接与最终 v0.2 数字混成一组。

本轮 **Base/S1/Final 同协议指标** 见 [docs/final_metrics.md](docs/final_metrics.md) 和 `artifacts/final/comparison.json`。保留旧 challenge_009 probe，确认 numeric/format/status isolation 的实际结果。

## 检索与排序政策

- Unknown year/episodes 无法证明指定硬范围；不会作为 0 使用。
- 正向 tag 需要 rank≥50；排除 tag 使用 rank≥1。这是单独的 retrieval relevance policy，不改变 Gold 或 global taxonomy identity。
- Ranking = positive genre/tag overlap + reference genre/tag Jaccard similarity + normalized log popularity + normalized averageScore；同分按 AniList ID 排序。
- Reference 只按三个标题的 Unicode/case 标准化精确查找。无匹配/多匹配提示 warning，不猜测属性。Reference 本身可能仍出现在候选里。
- 本地 catalog 不完整，no_matches 不说明 AniList 全站没有作品。当前不自动放松 hard constraints。

## 测试与代码复盘

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

新增核心测试覆盖 catalog hash/加载、全部过滤语义、rank policy、reference lookup、deterministic ranking、mocked parser 完整链、invalid JSON/domain fallback、真实 domain lineage、数据 hygiene 和 training split isolation。真实 adapter smoke 与十个 demos 单独运行并保存证据。

Demo 的 `status=ok` 表示 Query 合法且完成检索，不证明文本抽取完全正确。`artifacts/final/demo_fidelity_audit.json` 另外保存十条人工预期：本次 10/10 运行完成，7/10 strict Query Exact，允许 singleton ANY/ALL 等价时 8/10 语义匹配。Demo 1 漏抽 Mystery、Demo 7 漏抽 Sci-Fi，保留原始模型输出，未用规则补写。

- [代码导航](docs/code_walkthrough.md)
- [项目总结 / 简历 / 面试问题](docs/project_summary.md)
- [Final Engineering Review](review_bundle/final_project/REVIEW.md)
- [S1 详细报告](docs/s1_qlora_pilot_v0.1.md)

## 局限

这是单 GPU、受控文本训练的端到端工程项目；不是全站搜索服务或生产推荐系统。开放自然语言可能解析错误，当前 tag approval 是工程决策而非独立人工审计。Reference 不使用 embedding，ranker 未训练，词表与 catalog 需要按新版本维护。没有 FastAPI/Web frontend、LLM paraphrase pipeline、RAG vector DB、RLHF 或分布式部署；这些不是本次完成标准。

冻结训练 prompt 的 genre 行沿用了旧词表中的 `Hentai`，但 v0.2 active DomainRules 排除了它；域验证仍会拒绝该输出。本轮保留实际训练/比较使用的 prompt 和 identity，没有在评估后静默替换 prompt。未来若更新词表，应建立新的数据/prompt/模型版本。

第一次 batch=2、连续多个 split 的 Base 运行后段出现重复乱码，新进程同输入复核恢复正常，根因未确定。旧结果保留在 `artifacts/final/evaluation_bulk_interrupted/`，最终三模型统一改用每 split 新进程和单条批次重新评估；不是选择性修复或择优替换模型答案。

每次生成返回 CPU 文本后，清理未使用的 CUDA 缓存以降低连续推理显存压力；这个运行政策也写入 evaluation identity。权重、prompt、greedy 参数和 E0 指标定义保持不变。

<!-- FINAL_METRICS_START -->
## 本轮真实结果（同一 v0.2 协议）

| Metric | Base | S1 | Final |
|---|---:|---:|---:|
| test Exact | 54.0% | 86.0% | 99.3% |
| test Hard F1 | 78.8% | 95.5% | 99.7% |
| test Domain | 88.0% | 98.7% | 99.3% |
| challenge Exact | 42.5% | 65.0% | 67.5% |
| challenge Hard F1 | 73.1% | 81.4% | 86.7% |
| challenge Domain | 82.5% | 92.5% | 97.5% |

完整 JSON/schema validity、field accuracy、所有失败与协议差异见 [最终指标](docs/final_metrics.md)。
<!-- FINAL_METRICS_END -->
