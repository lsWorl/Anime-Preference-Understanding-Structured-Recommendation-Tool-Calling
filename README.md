# Anime Preference Understanding & Structured Recommendation Tool Calling

本项目为动漫偏好理解任务构建可审计、可复现的结构化训练数据。它从 AniList 获取作品和
taxonomy，经人工审核形成可执行词表，再从受控结构模式生成 SemanticSpec、自然语言和
Gold Query，最终输出带完整 provenance 的 pilot dataset。

当前不是在线动漫推荐器：尚未实现自然语言解析模型、训练、推理服务和目录检索执行器。

## 从这里开始

- [项目实现学习手册](docs/项目实现学习手册.md)：安装、架构、流程图、函数和实例。
- [模块实现详解](docs/模块实现详解.md)：逐模块讲解数据结构、算法、依赖、错误边界和测试。
- [Pilot Dataset Audit](docs/pilot_dataset_audit_v0.1.md)：当前生成产物的统计报告。

## 最短运行路径

要求 Python 3.10 或更高版本，运行时代码只使用标准库。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -B -m unittest discover -s tests -v
python -B scripts/fetch_anilist.py --dry-run
```

当前测试基线（2026-09-12）：380 项全部通过，无跳过。测试大量使用合成 fixture 与
网络 mock；这不代表已经完成真实 taxonomy 人工审核。

## 当前交付物

- `data/pilot/pilot_all.v0.1.jsonl`：240 条确定性 pilot records；
- train 180 条、validation 30 条、test 30 条；
- `data/pilot/challenge.v0.1.jsonl`：12 条训练外人工 challenge cases；
- `docs/pilot_dataset_audit_v0.1.md`：分布、覆盖与重复统计。

Pilot 使用 `tests/fixtures/` 中明确标记为 synthetic 的离线资源，只用于验证工程管道，
不能冒充 production taxonomy、正式审核结果或最终训练集。
