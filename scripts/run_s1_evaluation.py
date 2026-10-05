"""Evaluate the saved S1 adapter on the frozen validation set."""

import argparse
import json
from dataclasses import asdict
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
)
from anime_pref.inference.hf_baseline import generate_all
from anime_pref.inference.hf_sft import HuggingFaceSFTAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        required=True,
        choices=("validation", "test", "challenge"),
    )
    args = parser.parse_args()
    split = args.split

    expected_counts = {
        "validation": 30,
        "test": 30,
        "challenge": 12,
    }
    config = load_e0_config(
        PROJECT_ROOT / "configs/e0_baseline.v0.1.json",
        PROJECT_ROOT,
    )
    system_prompt = load_system_prompt(config, PROJECT_ROOT)

    records = load_e0_inputs(
        PROJECT_ROOT / f"data/pilot/{split}.v0.1.jsonl",
        split,
    )

    if len(records) != expected_counts[split]:
        raise ValueError(
            f"S1 {split} requires exactly {expected_counts[split]} records"
        )

    if len({record.sample_id for record in records}) != len(records):
        raise ValueError(f"{split} sample IDs must be unique")

    output_dir = PROJECT_ROOT / "artifacts/s1/evaluation"
    predictions_path = output_dir / f"{split}_predictions.jsonl"
    identity_path = output_dir / f"{split}_inference_identity.json"

    # 防止覆盖已经生成的评估证据。
    for path in (predictions_path, identity_path):
        if path.exists():
            raise ValueError(f"evaluation output already exists: {path}")

    rules = load_domain_rules(
        PROJECT_ROOT / "tests/fixtures/domain_rules.synthetic.v0.1.json"
    )

    adapter = HuggingFaceSFTAdapter(
        config,
        system_prompt,
        PROJECT_ROOT / "artifacts/s1/adapter",
        PROJECT_ROOT / "artifacts/s1/run_identity.json",
    )

    outputs = generate_all(
        adapter, (record.user_text for record in records), config.batch_size
    )
    predictions = tuple(
        evaluate_raw_prediction(
            record,
            raw_output,
            rules,
            config,
            adapter.resolved_model_revision,
        )
        for record, raw_output in zip(records, outputs, strict=True)
    )
    inference_identity = {
        "split": split,
        "sample_count": len(records),
        "inference_config": asdict(config),
        "resolved_model_revision": adapter.resolved_model_revision,
        **adapter.runtime_identity,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with predictions_path.open("x", encoding="utf-8") as file:
        file.write(predictions_to_jsonl(predictions))

    with identity_path.open("x", encoding="utf-8") as file:
        json.dump(
            inference_identity,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        file.write("\n")

    print(f"预测总数：{len(predictions)}")
    print(f"exact_match 为 True 的数量：{sum(p.exact_match for p in predictions)}")
    print(f"预测文件：{predictions_path}")
    print(f"推理身份文件：{identity_path}")


if __name__ == "__main__":
    main()
