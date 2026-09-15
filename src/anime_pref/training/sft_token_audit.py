"""Minimal token-length audit for the frozen SFT pilot dataset."""

from math import ceil
from statistics import median
from typing import Any

from anime_pref.training.sft_tokenization import tokenize_sft_record


def _validate_lengths(
    lengths: list[int],
    name: str,
) -> None:
    """Validate a nonempty collection of positive sequence lengths."""
    if not isinstance(lengths, list) or not lengths:
        raise ValueError(f"{name} must be a nonempty list")

    for index, length in enumerate(lengths):
        if isinstance(length, bool) or not isinstance(length, int) or length < 1:
            raise ValueError(f"{name}[{index}] must be a positive integer")

def nearest_rank_percentile(
    lengths: list[int],
    probability: float,
) -> int:
    """Return a deterministic nearest-rank percentile."""

    _validate_lengths(lengths, "lengths")

    if (
        isinstance(probability, bool)
        or not isinstance(probability, (int, float))
        or not 0 < probability <= 1
    ):
        raise ValueError("probability must be a number in the interval (0, 1]")

    # 1. 将 lengths 从小到大排序，但不能修改调用方的原列表。
    # 2. nearest-rank 使用：
    #       ceil(probability * 样本数量)
    # 3. 数学 rank 从 1 开始，Python list index 从 0 开始。
    # 4. 返回对应位置的整数长度。

    new_lengths = sorted(lengths)

    nearest_rank = ceil(probability * len(lengths))

    index = nearest_rank - 1

    return new_lengths[index]

def audit_sft_token_lengths(
    train_records: list[dict[str, Any]],
    validation_records: list[dict[str, Any]],
    system_prompt: str,
    tokenizer: Any,
) -> dict[str, Any]:
    """Tokenize frozen train/validation records and summarize lengths."""
    if not isinstance(train_records, list):
        raise ValueError("train_records must be a list")

    if not isinstance(validation_records, list):
        raise ValueError("validation_records must be a list")

    # 当前是冻结的 SFT Pilot v0.1，数量漂移必须立即报错。
    if len(train_records) != 180:
        raise ValueError(
            f"train_records must contain 180 records, "
            f"actual={len(train_records)}"
        )

    if len(validation_records) != 30:
        raise ValueError(
            f"validation_records must contain 30 records, "
            f"actual={len(validation_records)}"
        )

    # 分别遍历 train_records 和 validation_records。
    #
    # 对每条记录调用：
    # tokenize_sft_record(record, system_prompt, tokenizer)
    #
    # 取：
    # len(encoded["input_ids"])
    #
    # 最终得到：
    # train_lengths: list[int]
    # validation_lengths: list[int]
    train_lengths: list[int] = []
    validation_lengths: list[int] = []
    for record in train_records:
        encoded = tokenize_sft_record(record, system_prompt, tokenizer)
        train_lengths.append(len(encoded['input_ids']))

    for record in validation_records:
        encoded = tokenize_sft_record(record, system_prompt, tokenizer)
        validation_lengths.append(len(encoded['input_ids']))

    _validate_lengths(train_lengths, "train_lengths")
    _validate_lengths(
        validation_lengths,
        "validation_lengths",
    )

    # 防止遍历过程中丢失或额外产生记录。
    if len(train_lengths) != len(train_records):
        raise ValueError(
            "train token length count does not match record count"
        )

    if len(validation_lengths) != len(validation_records):
        raise ValueError(
            "validation token length count does not match record count"
        )

    # 返回值结构必须是：
    #
    # {
    #     "train": {
    #         "count": 180,
    #         "min": ...,
    #         "median": ...,
    #         "p95": ...,
    #         "max": ...,
    #     },
    #     "validation": {
    #         "count": 30,
    #         "max": ...,
    #     },
    #     "overall_max": ...,
    # }
    #
    # median 使用 statistics.median。
    # p95 使用上面的 nearest_rank_percentile(..., 0.95)。
    # overall_max 是 train max 和 validation max 中较大的一个。
    max_tratrain_lengths = max(train_lengths)
    max_validation_lengths = max(validation_lengths)
    return {
        "train":{
            "count": 180,
            "min":min(train_lengths),
            "median": median(train_lengths),
            "p95":nearest_rank_percentile(train_lengths,0.95),
            "max":max_tratrain_lengths
        },
        "validation":{
            "count": 30,
            "max":max_validation_lengths
        },
        "overall_max": max(max_tratrain_lengths,max_validation_lengths)
    }