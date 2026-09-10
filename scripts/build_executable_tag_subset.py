"""Build a versioned executable tag subset from a human-reviewed audit."""

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import load_domain_rules
from anime_pref.data.tag_subset import (
    build_executable_tag_subset,
    load_tag_audit,
    validate_domain_rule_tag_targets,
    write_executable_subset_bundle,
)
from anime_pref.data.taxonomy_snapshot import (
    load_canonical_taxonomy_snapshot,
)


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


def main(argv: list[str] | None = None) -> int:
    # loader 会拒绝非 canonical snapshot 和不完整 audit；构建前不做静默修复。
    args = parse_args(argv)

    snapshot = load_canonical_taxonomy_snapshot(args.canonical_snapshot)
    audit_records = load_tag_audit(args.audit)
    domain_rules = load_domain_rules(args.domain_rules)

    # 只有 audit 中显式 approved=True 的记录进入 subset，遗漏项不会默认批准。
    subset = build_executable_tag_subset(
        audit_records,
        snapshot,
        subset_version=args.subset_version,
    )

    # subset tag 集合必须与 DomainRules.tags 相等，且覆盖所有 tag-group 目标。
    validate_domain_rule_tag_targets(
        subset,
        domain_rules,
    )

    # subset hash 表示批准内容；derived hash 则追踪审核所依据的 taxonomy snapshot。
    manifest = write_executable_subset_bundle(
        subset,
        output_dir=args.output,
    )

    subset_path = args.output / "executable_tags.json"
    manifest_path = args.output / "manifest.json"

    print(f"executable_subset: {subset_path}")
    print(f"manifest: {manifest_path}")
    print(f"subset_version: {manifest.subset_version}")
    print(f"subset_sha256: {manifest.subset_hash}")
    print("derived_from_snapshot_sha256: " f"{manifest.derived_from_snapshot_hash}")
    print(f"approved_tag_count: {manifest.approved_tag_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
