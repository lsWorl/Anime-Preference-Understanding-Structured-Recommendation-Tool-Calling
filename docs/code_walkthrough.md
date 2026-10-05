# 从数据到推荐的代码导航

项目根目录为 `D:\Study\anime-preference-sft`。下面按调用链复盘；历史概率模块已保留，当前 final pipeline 不要求先理解或扩展它们。

| 顺序 | 文件 | 核心函数/对象 | 数据流与职责 |
|---:|---|---|---|
| 1 | `scripts/fetch_catalog.py`、`src/anime_pref/data/catalog.py` | `fetch_catalog_snapshot`、`graphql`、`load_catalog` | AniList 原始页面 → normalize_media → 按 ID 排序的 JSONL 与 SHA-256 manifest。原始分页缓存可恢复；推荐阶段只加载本地文件。 |
| 2 | `src/anime_pref/data/taxonomy_snapshot.py` | `build_canonical_taxonomy_snapshot`、`write_taxonomy_snapshot_bundle` | 完整 taxonomy → 批准字段/排序 → canonical UTF-8 JSON hash。保留原始 source 与时间，global tag identity 不含 media rank。 |
| 3 | `src/anime_pref/data/final_dataset.py`、`data/domain/` | `build_real_domain` | 显式 tag allowlist/alias + 真实 taxonomy → audit → executable subset → DomainRules。200 个参考标题和 resolver ID 独立保存。 |
| 4 | `src/anime_pref/data/rules_identity.py` | `validate_executable_rules_identity` | 确认 group members⊆active tags⊆subset，并重算 subset/rules hash。完整 DatasetRecord identity 可回溯真实外部 snapshot。 |
| 5 | `src/anime_pref/data/final_dataset.py` | `reviewed_patterns`、`generate_final_dataset` | 固定结构模式与 seed → E3 具体值。v0.2 加入 multi-value format/status OR，仍只计一个 clause。 |
| 6 | `src/anime_pref/sampling/semantic_spec_binder.py` | `sample_semantic_spec_from_pattern` | Group→genre→tag→numeric→format/status/reference 的绑定顺序；复用 D1/D2/E1，返回 pre-expansion SemanticSpec。 |
| 7 | `src/anime_pref/data/query_builder.py` | `build_query`、`dumps_query` | SemanticSpec→结构/domain 校验→HAREM expansion→完整 Gold JSON。Serializer 固定字段序，set 值排序。 |
| 8 | `src/anime_pref/data/final_dataset.py`、`dataset_record_builder.py` | `realize_final_text`、`build_dataset_record` | Spec→受控自然语言；同一 Spec→Gold。Record 记录 versions/hash/seed/template/signature；文字不经 NLP 改写 Gold。 |
| 9 | `scripts/build_final_data.py`、`data/final/` | `generate_final_dataset` | 输出1200/150/150与40条 authored challenge。简单 exact-text 去重复和跨 split 检查，统计可见值与复杂度。 |
| 10 | `src/anime_pref/training/final_training.py` | `load_final_config`、`load_final_records` | 只给 Trainer train/validation；保持固定 checkpoint，绑定真实 domain/data version。复用 S1 config 形状，不修改旧 pilot loader 合同。 |
| 11 | `src/anime_pref/training/sft_data.py` | `build_sft_messages` | record→system/user/assistant 三消息。Assistant 只有 canonical Gold，无 sample ID 或 rules provenance。 |
| 12 | `src/anime_pref/training/sft_tokenization.py` | `tokenize_sft_record` | 官方 Qwen template 分别生成 prompt/full token IDs；检查 prefix 完全一致。labels prompt=-100，completion=input IDs。模型负责 causal shift。 |
| 13 | `src/anime_pref/training/sft_dataset.py`、`sft_collator.py` | `build_sft_features`、`SFTDataCollator` | 单样本 list[int] → batch `[batch, longest_length]` Long tensors。右 padding attention=0/label=-100；Gold 超长拒绝，未 packing。 |
| 14 | `scripts/prepare_final_config.py` | `main` | 用真实 tokenizer 统计长度，确定足够覆盖 max 的 sequence length，写入 versioned config；不加载模型。 |
| 15 | `src/anime_pref/training/sft_model.py` | `load_s1_model` | frozen snapshot→NF4 model→prepare k-bit→LoRA；检查 base frozen、只有 LoRA A/B 可训练。输入 dtype long，compute BF16。 |
| 16 | `src/anime_pref/training/sft_trainer.py` | `build_s1_training_arguments`、`build_s1_trainer` | 复用 Trainer、optimizer、gradient accumulation/checkpointing；validation 只存 loss，避免巨大 logits。 |
| 17 | `scripts/train_final.py`、`final_training.py` | `train_final` | 先记录数据/tokenizer/prompt/config identity，再训练。按 validation loss 回载 best checkpoint，保存 adapter/state/manifest。 |
| 18 | `src/anime_pref/inference/hf_baseline.py` | `HuggingFaceBaselineAdapter.generate_batch` | 官方模板→左 padding→greedy generation→剥离 prompt tokens→raw text。Base checkpoint 和生成条件固定。 |
| 19 | `src/anime_pref/inference/final_parser.py` | `FinalPreferenceParser` | 新进程加载 BF16 base，再从磁盘挂载 S1 或 Final saved adapter；校验 revision/template/weights。三模型评估使用相同 v0.2 prompt。 |
| 20 | `src/anime_pref/evaluation/e0_baseline.py` | `evaluate_raw_prediction`、`build_e0_metrics_bundle` | 原始文本→JSON validity→schema→domain→canonical comparison。沿用冻结 micro hard-clause metrics 与错误 taxonomy；失败不修复。 |
| 21 | `scripts/run_final_evaluation.py`、`report_final_project.py` | `main`、`build_comparison` | 各模型保存全量 raw predictions 与 identity；重新评估保存文本，再统计 Base/S1/Final、失败转移和旧 challenge probes。 |
| 22 | `src/anime_pref/retrieval/executor.py` | `execute_query` | 校验后的 Query→本地 facts 过滤。ALL/ANY/NONE、inclusive ranges、format/status OR 全实现；未知 metadata 不能满足 hard bound。 |
| 23 | `src/anime_pref/retrieval/executor.py` | `resolve_reference`、`rank_candidates` | 精确标题查找→reference genre/tag similarity bonus；加 popularity/quality。Reference不产生硬约束。score components可解释，排序固定。 |
| 24 | `src/anime_pref/recommendation.py` | `RecommendationService.recommend_anime` | 自然语言→model raw→validation→filter→ranking→top-k。返回 query、推荐 facts、warnings 或明确失败状态。 |
| 25 | `scripts/recommend.py` | `main` | 单次或交互 CLI，服务对象/模型只加载一次。`run_demo_cases.py` 保存十个真实完整演示。 |

`report_final_project.audit_demo_fidelity` 以手工 SemanticSpec 经既有 Gold builder 生成 demo 预期，核对已保存的 Query 和推荐是否满足文本中的 hard clauses。它只报告，不修复模型输出；只在单独 demo 审核中把 singleton ANY/ALL 视为等价，冻结 E0 Exact 指标保持原定义。

`scripts/verify_final_data.py:verify_saved_records` 将落盘 train/validation/test 重建为 dataclass 后，复用既有 record validator 检查完整 provenance，没有替换保存的派生值。40 条 challenge 是 E0 challenge shape，其 ID 不是 full DatasetRecord identity；独立与作者显式 SemanticSpec 生成的 Gold 对照。

`run_final_evaluation.main` 每个 split 启动一个新进程，三模型统一 batch_size=1；`FinalPreferenceParser.generate_batch` 复用原 HF 生成函数，并在 CPU 文本返回后释放未使用的 CUDA 缓存。它不修改权重或生成参数，也不重试答案。已完成 split 保留用于断点续跑，最终 report 逐条重算指标并检查这些运行身份。初次连续 batch=2 运行的异常输出单独归档，不混入最终指标。

## 一个例子怎么走

输入：`悬疑或者科幻都可以，不要后宫。`

1. CLI 调用服务；模型看到冻结 instruction 和 user text，没有 catalog facts 或 Gold。
2. 预期 Query：genres.any_of=[Mystery,Sci-Fi]；tags.none_of=[Female Harem,Male Harem,Mixed Gender Harem]；其他字段保留显式 empty/null。
3. Strict parser 不移除 code fences。结构合法后按实际 DomainRules 检查可执行词表。
4. Catalog filter 保留至少一种指定 genre 且不带排除 tag 的作品。排除 tag 用 rank≥1，正向 tag 用 rank≥50。
5. 无 reference 时只有 positive overlap、popularity、averageScore 决定排序；同分按 ID。
6. 输出 top-k。实际模型结果及 top titles 见 demo_results.json；不能把这份“预期”当作真实生成证据。

## 后续学习顺序

先复盘 messages/tokenization/collator 的 token 和 label shapes，再看冻结 base + LoRA 的可训练参数，随后看 evaluator 的分层含义，最后从 CLI 跟进 Query 的过滤与 ranking。真实数据/训练参数/失败案例都以最终 review bundle 的实际记录为准。
