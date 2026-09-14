"""Aggregate retained E0 predictions into metrics JSON and Markdown."""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.evaluation.e0_baseline import (
    build_e0_metrics_bundle,
    load_prediction_jsonl,
)


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _metric_table(name: str, metrics: dict) -> list[str]:
    return [
        f"## {name}",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Records | {metrics['total']} |",
        f"| JSON parse rate | {_pct(metrics['json_parse_rate'])} |",
        f"| Recoverable JSON rate | {_pct(metrics['recoverable_json_rate'])} |",
        f"| Schema valid rate | {_pct(metrics['schema_valid_rate'])} |",
        f"| Domain valid rate | {_pct(metrics['domain_valid_rate'])} |",
        f"| Exact match rate | {_pct(metrics['exact_match_rate'])} |",
        f"| Hard precision | {_pct(metrics['hard_constraint_precision'])} |",
        f"| Hard recall | {_pct(metrics['hard_constraint_recall'])} |",
        f"| Hard F1 | {_pct(metrics['hard_constraint_f1'])} |",
        "",
        "### Field exact accuracy",
        "",
        "| Field | Accuracy |",
        "|---|---:|",
        *(
            f"| `{field}` | {_pct(value)} |"
            for field, value in metrics["field_accuracy"].items()
        ),
        "",
        "### Error labels",
        "",
        "| Label | Count |",
        "|---|---:|",
        *(
            f"| `{label}` | {count} |"
            for label, count in metrics["error_counts"].items()
        ),
        "",
    ]


def main() -> None:
    artifact_dir = PROJECT_ROOT / "artifacts" / "e0"
    validation = load_prediction_jsonl(artifact_dir / "validation_predictions.jsonl")
    test = load_prediction_jsonl(artifact_dir / "test_predictions.jsonl")
    challenge = load_prediction_jsonl(artifact_dir / "challenge_predictions.jsonl")
    validation_v01_path = artifact_dir / "validation_predictions.prompt_v0.1.jsonl"
    validation_v01 = (
        load_prediction_jsonl(validation_v01_path)
        if validation_v01_path.is_file()
        else ()
    )
    bundle = build_e0_metrics_bundle(validation, test, challenge)
    run_identity = json.loads(
        (artifact_dir / "run_identity.json").read_text(encoding="utf-8")
    )
    determinism = json.loads(
        (artifact_dir / "determinism_check.json").read_text(encoding="utf-8")
    )
    bundle = {"run_identity": run_identity, **bundle}
    (artifact_dir / "metrics.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="",
    )

    identity = validation[0]
    lines = [
        "# E0 Base-Model Baseline Evaluation v0.1",
        "",
        f"- Model: `{identity['model_id']}`",
        f"- Resolved revision: `{identity['resolved_model_revision']}`",
        f"- Tokenizer: `{identity['tokenizer_id']}`",
        f"- Prompt version: `{identity['prompt_version']}`",
        f"- Prompt frozen before test/challenge: `{run_identity['prompt_frozen']}`",
        f"- Serialization: `{identity['serialization_identity']}`",
        f"- Generation config: `{json.dumps(identity['generation_config'], sort_keys=True)}`",
        f"- GPU: `{run_identity['device_name']}`",
        f"- PyTorch: `{run_identity['torch_version']}`",
        f"- Transformers: `{run_identity['transformers_version']}`",
        f"- System prompt SHA-256: `{run_identity['system_prompt_sha256']}`",
        f"- Chat template SHA-256: `{run_identity['chat_template_sha256']}`",
        "- Training operations: none",
        f"- Same-input deterministic check: `{'PASS' if determinism['passed'] else 'FAIL'}`",
        "",
    ]
    if validation_v01:
        previous = build_e0_metrics_bundle(validation_v01, test, challenge)["validation"]["overall"]
        current = bundle["validation"]["overall"]
        lines.extend(
            (
                "## Validation-only prompt selection",
                "",
                "Prompt v0.1 was evaluated only on validation. It exposed episode/year field "
                "leakage and false HAREM normalization from explicit genres. Prompt v0.2 added "
                "field-isolation and normalization-trigger instructions, then became frozen before "
                "the first test/challenge run.",
                "",
                "| Prompt | JSON | Schema | Domain | Exact | Hard F1 |",
                "|---|---:|---:|---:|---:|---:|",
                f"| `e0-json-extraction-v0.1` | {_pct(previous['json_parse_rate'])} | {_pct(previous['schema_valid_rate'])} | {_pct(previous['domain_valid_rate'])} | {_pct(previous['exact_match_rate'])} | {_pct(previous['hard_constraint_f1'])} |",
                f"| `e0-json-extraction-v0.2` | {_pct(current['json_parse_rate'])} | {_pct(current['schema_valid_rate'])} | {_pct(current['domain_valid_rate'])} | {_pct(current['exact_match_rate'])} | {_pct(current['hard_constraint_f1'])} |",
                "",
            )
        )
    lines.extend(_metric_table("Validation metrics", bundle["validation"]["overall"]))
    lines.extend(_metric_table("Test metrics", bundle["test"]["overall"]))
    lines.extend(_metric_table("Challenge metrics", bundle["challenge"]["overall"]))

    for split_name in ("validation", "test", "challenge"):
        for slice_name in ("normalization", "reference"):
            metrics = bundle[split_name][slice_name]
            if metrics is not None:
                lines.extend(
                    _metric_table(
                        f"{split_name.title()} {slice_name} behavior",
                        metrics,
                    )
                )

    for split_name, rows in (("Validation", validation), ("Test", test)):
        lines.extend((f"## {split_name} slices", ""))
        for slice_name, key in (
            ("Semantic family", "by_semantic_family"),
            ("Constraint count", "by_constraint_count"),
            ("Constraint signature", "by_constraint_signature"),
        ):
            lines.extend((f"### {slice_name}", "", "| Value | N | Exact | JSON | Domain |", "|---|---:|---:|---:|---:|"))
            for value, metrics in bundle[split_name.lower()][key].items():
                lines.append(
                    f"| `{value}` | {metrics['total']} | {_pct(metrics['exact_match_rate'])} | "
                    f"{_pct(metrics['json_parse_rate'])} | {_pct(metrics['domain_valid_rate'])} |"
                )
            lines.append("")

    failures = [row for row in (*test, *challenge) if not row["exact_match"]][:20]
    lines.extend(("## Representative failure cases", ""))
    for index, row in enumerate(failures, 1):
        lines.extend(
            (
                f"### Failure {index}: `{row['sample_id']}`",
                "",
                f"- Split: `{row['split']}`",
                f"- Error labels: `{', '.join(row['error_labels']) or '(none)'}`",
                f"- User text: {row['user_text']}",
                "",
                "Gold:",
                "",
                "```json",
                json.dumps(row["gold_query"], ensure_ascii=False, sort_keys=True),
                "```",
                "",
                "Raw prediction:",
                "",
                "````text",
                row["raw_model_output"],
                "````",
                "",
            )
        )
    (PROJECT_ROOT / "docs" / "e0_baseline_v0.1.md").write_text(
        "\n".join(lines), encoding="utf-8", newline=""
    )
    print("Wrote artifacts/e0/metrics.json and docs/e0_baseline_v0.1.md")


if __name__ == "__main__":
    main()
