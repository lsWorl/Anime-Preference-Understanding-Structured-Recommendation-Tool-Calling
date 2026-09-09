"""本地 raw 缓存；保存原始 Media 字典，保留来源字段。"""
from pathlib import Path
from typing import Any, Iterable
import json

# records 可以是一次性迭代器，因此边写边计数，不提前 len() 或消费输入。
# 每行独立 JSON，保留 Unicode；独占创建防止覆盖已有采集结果。
# 中途序列化/写盘失败会向上传播，也可能留下部分文件；with 只负责关闭句柄。
def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> int:
    """每条记录写为一行 JSON，返回行数；已有文件抛 FileExistsError。"""
    path.parent.mkdir(parents=True,exist_ok=True)

    count = 0
    # 'x' 模式：文件不存在则创建，存在则抛出 FileExistsError
    with path.open('x', encoding='utf-8') as f:
        for record in records:
            line = json.dumps(record, ensure_ascii=False) + '\n'
            f.write(line)
            count += 1
    return count


# 仅负责把传入摘要写盘，不检查摘要与 raw 文件是否一致。
# 调用者应在分页均成功后调用；独占创建不是多文件事务，也没有自动回滚。
def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """写入便于阅读的 JSON manifest；已有文件抛 FileExistsError。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        # 可选：末尾加一个换行，使符合 UNIX 文本文件惯例
        f.write('\n')

