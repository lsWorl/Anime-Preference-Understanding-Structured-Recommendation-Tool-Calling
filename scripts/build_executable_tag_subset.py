"""Build a versioned executable tag subset from a human-reviewed audit."""

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# 此函数已实现参数解析，返回 argparse.Namespace；Path 转换不等于文件存在或内容已校验。
# argv=None 时读取进程命令行；传列表便于离线测试。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-snapshot", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--subset-version", required=True)
    parser.add_argument("--domain-rules", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


# 当前仅解析参数后抛 NotImplementedError；--help 可用，实际业务链尚未接通。
# 下面的 TODO 是待实现契约，本次注释整理没有替学习者补完。
def main(argv: list[str] | None = None) -> int:
    # TODO-39: load the canonical snapshot and audit, build/validate the subset,
    # verify DomainRules targets, persist subset+manifest, and print identity.
    parse_args(argv)
    raise NotImplementedError("TODO-39: wire reviewed executable subset CLI")


if __name__ == "__main__":
    raise SystemExit(main())


