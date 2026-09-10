"""Fetch and persist a versioned AniList taxonomy snapshot."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.taxonomy_client import fetch_anilist_taxonomy
from anime_pref.data.taxonomy_snapshot import write_taxonomy_snapshot_bundle


# 此函数已实现参数解析，返回 argparse.Namespace；Path 转换不等于文件存在或内容已校验。
# argv=None 时读取进程命令行；传列表便于离线测试。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="https://graphql.anilist.co")
    parser.add_argument("--timeout", type=float, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # fetch UTC time once, call fetch_anilist_taxonomy, then write the
    # raw/canonical/manifest bundle. Print paths/hash/counts; return 0 on success.
    args = parse_args(argv)

    fetched_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    source_payload = fetch_anilist_taxonomy(
        endpoint=args.endpoint,
        timeout_seconds=args.timeout,
    )

    manifest = write_taxonomy_snapshot_bundle(
        source_payload,
        output_dir=args.output,
        fetched_at_utc=fetched_at_utc,
    )

    source_path = args.output / "source.json"
    canonical_path = args.output / "canonical.json"
    manifest_path = args.output / "manifest.json"

    print(f"source: {source_path}")
    print(f"canonical: {canonical_path}")
    print(f"manifest: {manifest_path}")
    print(f"canonical_sha256: {manifest.canonical_sha256}")
    print(f"genre_count: {manifest.genre_count}")
    print(f"tag_count: {manifest.tag_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
