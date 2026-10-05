"""Compare retained E0 and S1 predictions using the frozen evaluator."""

from anime_pref.evaluation.e0_baseline import build_e0_metrics_bundle


EXPECTED_COUNTS = {
    "validation": 30,
    "test": 30,
    "challenge": 12,
}


def build_s1_comparison_bundle(
    base: dict[str, tuple[dict, ...]],
    sft: dict[str, tuple[dict, ...]],
) -> dict:
    """Return metrics and sample-level transitions without writing files."""

    if not isinstance(base, dict) or not isinstance(sft, dict):
        raise ValueError("base and sft must be dictionaries")

    if set(base) != set(EXPECTED_COUNTS):
        raise ValueError("base must contain all three evaluation splits")
    if set(sft) != set(EXPECTED_COUNTS):
        raise ValueError("sft must contain all three evaluation splits")

    matched_fields = (
        "sample_id",
        "split",
        "user_text",
        "gold_query",
        "model_id",
        "tokenizer_id",
        "resolved_model_revision",
        "prompt_version",
        "serialization_identity",
        "generation_config",
    )

    for split, expected in EXPECTED_COUNTS.items():
        for name, rows in (("base", base[split]), ("sft", sft[split])):
            if not isinstance(rows, tuple):
                raise ValueError(f"{name}/{split} must be a tuple")
            if len(rows) != expected:
                raise ValueError(f"{name}/{split}: invalid record count")

            ids = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("prediction row must be an object")
                if not set(matched_fields).issubset(row):
                    raise ValueError("prediction identity fields are missing")

                sample_id = row["sample_id"]
                if not isinstance(sample_id, str) or not sample_id:
                    raise ValueError("invalid sample_id")
                if row["split"] != split:
                    raise ValueError("prediction split mismatch")
                if type(row.get("exact_match")) is not bool:
                    raise ValueError("exact_match must be bool")
                ids.append(sample_id)

            if len(set(ids)) != len(ids):
                raise ValueError(f"{name}/{split}: duplicate sample IDs")

        for before, after in zip(base[split], sft[split], strict=True):
            for field in matched_fields:
                if before[field] != after[field]:
                    raise ValueError(
                        f"{split}: comparison mismatch in {field}"
                    )


    # 1. 分别调用 build_e0_metrics_bundle，获取 base/sft 指标。
    #    不重新实现 precision、recall、F1。
    #
    # 2. 每个 split 按 exact_match 分类：
    #    fixed：       Base False，SFT True
    #    still_failed：Base False，SFT False
    #    regressed：   Base True， SFT False
    #
    # 3. 每个分类项保存：
    #    {"base": before, "sft": after}
    #    保留完整记录，方便后续报告展示原始输出和错误变化。
    #
    # 4. 返回：
    #    {
    #        "base": base_metrics,
    #        "sft": sft_metrics,
    #        "transitions": {
    #            split: {
    #                "fixed": [...],
    #                "still_failed": [...],
    #                "regressed": [...],
    #            }
    #        },
    #    }
    base_metrics = build_e0_metrics_bundle(
        base["validation"],
        base["test"],
        base["challenge"],
    )
    sft_metrics = build_e0_metrics_bundle(
        sft["validation"],
        sft["test"],
        sft["challenge"],
    )

    transitions = {}

    for split in EXPECTED_COUNTS:
        split_transitions = {
            "fixed": [],
            "still_failed": [],
            "regressed": [],
        }
        for before, after in zip(base[split], sft[split], strict=True):
            base_match = before["exact_match"]
            sft_match = after["exact_match"]
            if not base_match and sft_match:
                category = "fixed"
            elif not base_match and not sft_match:
                category = "still_failed"
            elif base_match and not sft_match:
                category = "regressed"
            else:
                continue  # Base 和 SFT 都正确，不属于要求的三类变化。

            split_transitions[category].append({
                "base": before,
                "sft": after,
            })

        transitions[split] = split_transitions
        
    return {
        "base": base_metrics,
        "sft": sft_metrics,
        "transitions": transitions,
    }