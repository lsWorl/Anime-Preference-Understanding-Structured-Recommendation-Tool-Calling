"""Run one deterministic E0 split with Qwen3-4B and retain raw predictions."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import load_domain_rules
from anime_pref.evaluation.e0_baseline import (
    evaluate_raw_prediction,
    load_e0_config,
    load_e0_inputs,
    load_system_prompt,
    predictions_to_jsonl,
    validate_e0_split_authorization,
)
from anime_pref.inference.hf_baseline import HuggingFaceBaselineAdapter, generate_all


def _input_path(split: str) -> Path:
    if split == "smoke":
        return PROJECT_ROOT / "data" / "pilot" / "train.v0.1.jsonl"
    return PROJECT_ROOT / "data" / "pilot" / f"{split}.v0.1.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        required=True,
        choices=("smoke", "validation", "test", "challenge"),
    )
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs" / "e0_baseline.v0.1.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "e0")
    parser.add_argument("--determinism-check", action="store_true")
    args = parser.parse_args()

    config = load_e0_config(args.config, PROJECT_ROOT)
    validate_e0_split_authorization(config, args.split)
    system_prompt = load_system_prompt(config, PROJECT_ROOT)
    records = load_e0_inputs(_input_path(args.split), args.split)
    if args.split == "smoke":
        records = records[:3]

    adapter = HuggingFaceBaselineAdapter(config, system_prompt)
    rules = load_domain_rules(
        PROJECT_ROOT / "tests" / "fixtures" / "domain_rules.synthetic.v0.1.json"
    )
    if args.determinism_check:
        first = adapter.generate_batch((records[0].user_text,))[0]
        repeated = adapter.generate_batch((records[0].user_text,))[0]
        if repeated != first:
            raise RuntimeError("same checkpoint, prompt, and input produced different output")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "determinism_check.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "sample_id": records[0].sample_id,
                    "model_revision": adapter.resolved_model_revision,
                    "prompt_version": config.prompt_version,
                    "raw_output_sha256": sha256(first.encode("utf-8")).hexdigest(),
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="",
        )
    outputs = generate_all(adapter, (record.user_text for record in records), config.batch_size)

    predictions = tuple(
        evaluate_raw_prediction(
            input_record,
            raw_output,
            rules,
            config,
            adapter.resolved_model_revision,
        )
        for input_record, raw_output in zip(records, outputs, strict=True)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "smoke" if args.split == "smoke" else args.split
    output_path = args.output_dir / f"{suffix}_predictions.jsonl"
    output_path.write_text(predictions_to_jsonl(predictions), encoding="utf-8", newline="")
    run_identity = {
        "e0_version": config.e0_version,
        "model_id": config.model_id,
        "tokenizer_id": config.tokenizer_id,
        "configured_revision": config.revision,
        "resolved_model_revision": adapter.resolved_model_revision,
        "prompt_version": config.prompt_version,
        "prompt_frozen": config.prompt_frozen,
        "serialization_identity": config.serialization_identity,
        "generation_config": predictions[0].generation_config,
        **adapter.runtime_identity,
    }
    (args.output_dir / "run_identity.json").write_text(
        json.dumps(run_identity, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(
        f"Wrote {len(predictions)} {args.split} predictions to {output_path}; "
        f"resolved_revision={adapter.resolved_model_revision}; "
        f"chat_template_sha256={adapter.chat_template_sha256}"
    )


if __name__ == "__main__":
    main()
