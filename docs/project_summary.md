# 项目总结与面试材料

## 问题与方法

用户用自然语言表达 genre/tag 排除、OR/AND、年份、集数与参考作品时，普通推荐提示容易漏约束、混淆 operator 或凭作品知识增加隐藏偏好。本项目把任务限定为自然语言→Structured Preference Query；作品事实与检索由真实 AniList snapshot 提供。

选择 SFT 是因为主要目标是一个稳定、领域明确的输出合同，而不是让模型背动漫数据库。Gold 从 canonical SemanticSpec 和 deterministic builder 生成，再受控表达成文本；LLM 不自由决定标签。QLoRA 把固定 Qwen3-4B 的 base 权重冻结，只训练少量 LoRA 参数，降低单 GPU 显存要求。

结构化输出使 ALL/ANY/NONE、inclusive numeric bounds、format/status OR 与 reference-only 含义可校验、可执行、可量化。JSON/schema/domain validity 分开衡量，领域非法输出在应用中拒绝执行。

## Baseline、首轮 SFT 与失败分析

旧 pilot：Base Test Exact 76.7%，S1 为100%；Challenge Exact 66.7%→91.7%。但 Challenge Domain 100%→91.7%、Hard F1 87.8%→81.1%，不能用总体 Exact 掩盖退化。challenge_009 修正了中文 genre，却错误增加 year.max 并把 TV 复制进 status。

S1 epoch 2/3 的 validation loss 升高，最终保存 epoch 1 best checkpoint。Adapter 保存后在新进程重新加载，评估条件与原 Base 一致。所有 raw outputs 保留，错误结果没有自动修复。

## 第二轮数据与最终系统

接入1,544条真实 AniList records、完整 taxonomy、83个明确选择的非 adult/spoiler tags、200个参考标题。数据扩展到1,500条和40条独立 challenge，增加18种中文/英文受控句式、complexity 1–5、多值 format/status OR 及 numeric/field isolation。没有复制旧 challenge_009 到 train。

Final 重新从同一 frozen base 初始化 LoRA，而不是用 S1 weights继续训练。沿用NF4/BF16、r16/alpha32/dropout0.05、七个 projections；预先选择1epoch和validation-loss checkpoint selection。全部训练身份、数据 hash、真实 token statistics 和 loss日志保存。

最终重新用同一 v0.2 prompt/真实 domain/新 splits 比较 Base、S1、Final，因此与旧 pilot 是不同评估协议。实际最终指标与剩余失败见 [final_metrics.md](final_metrics.md)；没有把未完成/预计指标写成成果。

推荐链已包括：fine-tuned parser → strict validation → 本地 hard filter → reference similarity/quality/popularity ranking → CLI。Reference 不重新注入 hard constraints，非法 Query 与空结果有明确状态。

## 可以据实使用的简历条目

- 构建基于 Qwen3-4B 与4-bit QLoRA的动漫偏好解析系统，将自然语言转换为可校验的结构化检索 Query，并接入真实 AniList 本地目录。
- 设计 semantic-first 数据构造管道，复用 deterministic Gold builder与受控自然语言模板，生成1,500条带版本/hash provenance的样本及40条独立 challenge，检查跨split精确样本泄漏。
- 实现 completion-only masking、单GPU PEFT训练、validation-loss checkpoint选择、adapter保存与独立重载，保留完整训练与推理实验身份。
- 建立 JSON/schema/domain 分层评估及 hard-clause micro P/R/F1，完成 Base/S1/Final 同协议比较和逐条 failure analysis；旧 pilot Test Exact 从76.7%提升到100%，同时记录challenge可执行性退化。
- 实现 ALL/ANY/NONE、含端点数值范围、format/status OR、本地引用解析与可解释 deterministic ranking，并提供十个真实模型→catalog的CLI演示。

数字适用于当前小规模实验；不要扩写成生产泛化、全站实时搜索或独立人工审核结论。最终 adapter 的实际成绩请从最终报告引用，明确数据集与提示词协议。

## 十个面试问题

1. 为什么把偏好解析与作品知识检索拆开？
2. Semantic-first如何防止LLM自由决定Gold？
3. ALL、ANY、NONE与format/status OR有什么区别？
4. HAREM normalization为什么在Gold展开，而在文本保留概念？
5. 如何构造input_ids、attention_mask、labels及padding，哪些token参与loss？
6. QLoRA、NF4、BF16、LoRA rank/alpha各负责什么？哪些参数被训练？
7. 为什么用validation loss选择checkpoint，而不能按test结果反复调参？
8. 为什么Exact提升时Domain validity或Hard F1仍可能下降？
9. 如何保证Base/S1/Final比较公平，保存哪些identity？
10. 如何执行硬约束、处理unknown metadata、查找参考作品并解释排名分数？
