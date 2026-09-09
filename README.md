# Anime Preference Understanding & Structured Recommendation Tool Calling

代码学习线当前状态：Project Scaffold + AniList Data Acquisition v0.1 已完成；
正在实现 Dataset semantic specification + deterministic JSON builder v0.1。
当前不涉及训练与推荐执行。

## 环境与运行

Python >= 3.10。当前代码仅用标准库，配置为 JSON，不需要安装 YAML 或 Pydantic。
在 PowerShell 中执行：

```powershell
cd D:\Study\anime-preference-sft
python -m venv .venv
.\.venv\Scripts\python.exe scripts/fetch_anilist.py --dry-run
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

脚本直接支持 src 布局，不要求提前安装包。如需在其他代码中导入，可选执行
`.\.venv\Scripts\python.exe -m pip install -e .`。

补完 TODO 后运行：

```powershell
.\.venv\Scripts\python.exe scripts/fetch_anilist.py --pages 1 --per-page 10 --output data/raw/anilist
```

`--help`、`--dry-run` 和普通小规模采集均可使用。
配置/运行错误返回 1，成功返回 0。dry-run 不联网、不写缓存。
默认配置是 configs/data.json；命令行参数覆盖对应配置。
输出相对路径基于项目根目录；自定义 --config 相对路径基于当前工作目录。
已有空 configs/data.yaml 保留，但不被读取。

## 学习顺序与验收

1. **TODO-01**，data/anilist_client.py：补 GraphQL 查询，用以前成功的查询作参考。
2. **TODO-02**，同文件：实现单页 POST、超时、HTTP/GraphQL 错误与返回结构检查。
   先在自己的练习脚本调用 `fetch_anime_page(1, 2)`，确认结果包含 media/pageInfo。
3. **TODO-03**，schemas/anime_metadata.py：从一条 Media 构造 dataclass，保留未知值 None。
4. **TODO-04a / 04b**，data/io.py：完成 JSONL 和 manifest 写入。
5. **TODO-05**，scripts/fetch_anilist.py：接上分页、校验、原始缓存、manifest。
6. **TODO-06a / 06b / 06c**，tests/test_scaffold.py：补相应断言并移除 skip。
   建议每完成一个模块就补它的测试。当前跳过的测试不是功能完成的证据。

搜索 `TODO-` 可定位所有练习。函数 docstring 和旁边的注释说明输入、输出和失败行为。
不应通过捕获 NotImplementedError 或返回空列表让尚未实现的功能假装成功。

## 数据约定

- data/raw：保存 API 原始 Media 字典，一页一个 JSONL；不改写原始字段。
- data/interim：后续清洗/标准化中间结果；目前仅占位。
- data/processed：后续训练与评估输入；目前仅占位。
- AnimeMetadata：校验和标准化视图，不替代 raw 记录；dataclass 不会自动校验类型。
- outputs：后续运行产物；training/evaluation/inference 目前只有包占位。
- manifest.json：成功抓取的可追踪摘要，需包含代码中列出的字段。

## Dataset semantic specification + deterministic JSON builder v0.1

## 运行完整测试的指令
```powershell
python -B -m unittest discover -s tests -v
```
本阶段新增：

- `schemas/preference_query.py`：不可变的 canonical semantic spec。
- `data/query_builder.py`：规则加载、确定性 Gold JSON 构建与序列化。
- `data/constraint_signature.py`：hard constraint 结构签名。
- `configs/domain_rules.v0.1.json`：版本化 taxonomy allowlist 与批准的 tag group。
- `tests/test_query_builder.py`：固定语义、期望 JSON、拒绝路径和 signature 骨架。

实现顺序为 TODO-07（规则加载）→ TODO-08（Gold builder）→ TODO-09（序列化）
→ TODO-10（signature）→ TODO-11（逐项启用测试）。当前 tag allowlist 只包含已经批准的
Harem 三个 AniList tags；扩充前必须先完成 taxonomy 审计，不能凭印象添加。

本阶段不生成自然语言、不调用 LLM、不进行数据集切分或训练。若实现过程中发现
Schema 字段类型、numeric rules 或 normalization policy 尚未在理论分支冻结，应先回理论
分支补齐准确规则，再继续代码线。
