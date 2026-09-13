"""Generate the reviewed 240-record offline pilot dataset."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.pilot_dataset import (
    audit_pilot_records,
    audit_pilot_split_hygiene,
    build_human_challenge_cases,
    generate_pilot_records,
    load_pilot_pattern_manifest,
    render_pilot_audit_markdown,
    split_pilot_records,
    write_pilot_artifacts,
)
from anime_pref.data.query_builder import load_domain_rules
from anime_pref.data.reference_title_pool import load_reference_title_pool
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.sampling.config import load_sampler_config


def main() -> None:
    """Load frozen offline resources and write the deterministic pilot outputs."""
    fixtures = PROJECT_ROOT / "tests" / "fixtures"
    manifest = load_pilot_pattern_manifest(
        PROJECT_ROOT / "configs" / "pilot_pattern_manifest.v0.1.json"
    )
    config = load_sampler_config(fixtures / "semantic_sampler.synthetic.v0.1.json")
    rules = load_domain_rules(fixtures / "domain_rules.synthetic.v0.1.json")
    subset = load_executable_tag_subset(
        fixtures / "executable_tags.synthetic.v0.1.json"
    )
    title_pool = load_reference_title_pool(
        fixtures / "reference_titles.synthetic.v0.1.json"
    )

    records = generate_pilot_records(manifest, config, rules, subset, title_pool)
    splits = split_pilot_records(manifest, records)
    challenge_cases = build_human_challenge_cases(rules)
    audit = audit_pilot_records(records)
    split_hygiene = audit_pilot_split_hygiene(splits)
    audit_markdown = render_pilot_audit_markdown(
        audit,
        split_hygiene,
        {name: len(values) for name, values in splits.items()},
        len(challenge_cases),
    )
    write_pilot_artifacts(
        PROJECT_ROOT / "data" / "pilot",
        PROJECT_ROOT / "docs" / "pilot_dataset_audit_v0.1.md",
        records,
        splits,
        challenge_cases,
        audit_markdown,
    )
    print(
        f"Generated {len(records)} records: "
        f"train={len(splits['train'])}, "
        f"validation={len(splits['validation'])}, "
        f"test={len(splits['test'])}, "
        f"challenge={len(challenge_cases)}"
    )


if __name__ == "__main__":
    main()
