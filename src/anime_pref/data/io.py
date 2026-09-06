"""本地 raw 缓存；保存原始 Media 字典，保留来源字段。"""
from pathlib import Path
from typing import Any, Iterable
import json

def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> int:
    """每条记录写为一行 JSON，返回行数；已有文件抛 FileExistsError。"""
    # TODO-04a: 创建父目录，以 UTF-8 和 x 模式写文件（避免覆盖）。
    # 使用 json.dumps(..., ensure_ascii=False)，每条记录后加换行。
    # 正确处理空输入并返回实际写入数量；不要吞掉磁盘异常。
    # 如果不存在则创建父目录
    path.parent.mkdir(parents=True,exist_ok=True)

    count = 0
    # 'x' 模式：文件不存在则创建，存在则抛出 FileExistsError
    with path.open('x', encoding='utf-8') as f:
        for record in records:
            line = json.dumps(record, ensure_ascii=False) + '\n'
            f.write(line)
            count += 1
    return count


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """写入便于阅读的 JSON manifest；已有文件抛 FileExistsError。"""
    # TODO-04b: UTF-8、x 模式、ensure_ascii=False、indent=2。
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        # 可选：末尾加一个换行，使符合 UNIX 文本文件惯例
        f.write('\n')
