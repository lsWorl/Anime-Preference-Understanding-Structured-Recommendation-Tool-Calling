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
    
    