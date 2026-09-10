# 快速开始

## 1. 环境准备

项目要求 Python 3.10+，运行时代码无第三方依赖。从项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows PowerShell 使用：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## 2. 运行测试与配置检查

```bash
python -B -m unittest discover -s tests -v
python -B scripts/fetch_anilist.py --dry-run
```

`--dry-run` 只合并和校验作品采集配置，不联网，也不创建文件。默认配置来自
`configs/data.json`；CLI 的 `--pages`、`--per-page` 和 `--output` 会覆盖同名配置。

## 3. 采集作品元数据

下面的命令会联网，并写入一个尚不存在的目标目录：

```bash
python -B scripts/fetch_anilist.py \
  --pages 1 \
  --per-page 10 \
  --output data/raw/anilist-run-001
```

输出：

```text
data/raw/anilist-run-001/
├── page_0001.jsonl
└── manifest.json
```

每行保存 AniList 返回的原始 `Media` 对象；`AnimeMetadata.from_api()` 只作为校验视图，
不会替换原始数据。默认相对输出路径基于项目根目录。若某个目标文件已经存在，写入会失败；
若后续页面失败，之前写好的页面不会自动删除。

## 4. 获取 taxonomy 快照

```bash
python -B scripts/fetch_anilist_taxonomy.py \
  --output data/raw/taxonomy-2026-09-10
```

可选参数为 `--endpoint` 和 `--timeout`。输出：

```text
data/raw/taxonomy-2026-09-10/
├── source.json       # 完整解码后的 GraphQL 响应
├── canonical.json    # 仅保留契约字段并稳定排序
└── manifest.json     # 获取时间、数量、schema 与 canonical SHA-256
```

`fetched_at_utc` 不进入内容哈希，因此相同 taxonomy 内容在不同时间获取时具有相同
`canonical_sha256`。

## 5. 完成人工 tag audit

复制 `configs/tag_audit.example.v0.1.json` 的结构创建新的审核文件，但不要沿用其中的
占位 ID、category 或全零 hash。每条记录都必须：

- 精确对应 `canonical.json` 中的 ID、name、category、spoiler/adult 标记；
- 使用 snapshot manifest 的 `canonical_sha256` 作为 `source_snapshot_hash`；
- 显式设置 `approved`，并填写非空 `reason`；
- 仅添加经过审核且不与 canonical tag name 或其他批准项冲突的 aliases。

未出现在 audit 中的 tag 等价于未审核，不会自动获批。

## 6. 构建 executable tag subset

```bash
python -B scripts/build_executable_tag_subset.py \
  --canonical-snapshot data/raw/taxonomy-2026-09-10/canonical.json \
  --audit configs/tag_audit.reviewed.v0.1.json \
  --subset-version reviewed-tags-v0.1 \
  --domain-rules configs/domain_rules.v0.1.1.json \
  --output data/processed/executable-tags-v0.1
```

输出 `executable_tags.json` 与 `manifest.json`。命令还会要求 subset 的 tag name 集合与
`DomainRules.tags` 完全相等，并检查所有 tag group 展开目标都存在。当前规则因此要求
`Female Harem`、`Male Harem`、`Mixed Gender Harem` 三项全部获得批准。

## 7. 构建一个 Gold Query

```python
from pathlib import Path

from anime_pref.data.query_builder import build_query, dumps_query, load_domain_rules
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)

rules = load_domain_rules(Path("configs/domain_rules.v0.1.1.json"))
spec = SemanticSpec(
    genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")),
    tag_groups=SetConstraintSpec(none_of=("HAREM",)),
    year=RangeConstraintSpec(min=2010),
    episodes=RangeConstraintSpec(max=24),
    formats=("TV",),
    status=("FINISHED",),
    unresolved_preferences=("节奏紧凑",),
)

query = build_query(spec, rules)
print(dumps_query(query))
```

`build_query()` 只转换已经明确给出的 canonical semantics，不读取自然语言，也不会从参考
作品推断额外标签。当前 soft 词表为空，所以尚未批准的偏好表达应由上游明确放入
`unresolved_preferences`。

## 8. 常见问题

- `ModuleNotFoundError: anime_pref`：先执行 editable 安装，或只从项目根目录运行脚本。
- `FileExistsError`：使用新的输出目录；项目刻意禁止覆盖数据证据。
- taxonomy/audit identity 不匹配：重新核对 snapshot manifest 的 hash 和 canonical tag 字段。
- unknown taxonomy/soft preference：输入必须属于当前 DomainRules allowlist。
- 中文显示异常：文件统一使用 UTF-8；终端需要时可使用 `python -X utf8`。
- 网络失败：CLI 不提供重试或断点续传，确认已有部分输出后换新目录重试。
