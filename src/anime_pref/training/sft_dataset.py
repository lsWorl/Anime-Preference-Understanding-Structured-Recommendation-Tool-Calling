"""Prepare unpadded SFT features without truncation or deduplication."""

from typing import Any

from anime_pref.training.sft_tokenization import tokenize_sft_record


def build_sft_features(
    records: list[dict[str, Any]],
    system_prompt: str,
    tokenizer: Any,
    max_seq_length: int,
) -> list[dict[str, list[int]]]:
    """Preserve record order and return one tokenized feature per record."""

    if not isinstance(records, list) or not records:
        raise ValueError("records must be a nonempty list")

    if (
        isinstance(max_seq_length, bool)
        or not isinstance(max_seq_length, int)
        or max_seq_length < 1
    ):
        raise ValueError("max_seq_length must be a positive integer")

    features: list[dict[str, list[int]]] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"records[{index}] must be a dict")

        # 调用 tokenize_sft_record(record, system_prompt, tokenizer)。
        # 把结果保存为 encoded。
        #
        # 如果该调用抛出 ValueError：
        # 重新抛出带 index 和 sample_id 的 ValueError，
        # 使用 from exc 保留原因。
        try:
            encoded = tokenize_sft_record(record, system_prompt, tokenizer)
        except ValueError as exc:
            raise ValueError(
                f"records[{index}], "
                f"sample_id={record.get('sample_id')!r}: "
                f"tokenization failed: {exc}"
            ) from exc

        # 超长时立即拒绝，不能裁剪 JSON。
        sequence_length = len(encoded["input_ids"])
        if sequence_length > max_seq_length:
            raise ValueError(
                f"records[{index}], "
                f"sample_id={record.get('sample_id')!r}: "
                f"length={sequence_length} exceeds "
                f"max_seq_length={max_seq_length}"
            )

        # 将 encoded 加入 features。
        # 不排序、不去重、不填充。
        features.append(encoded)

    if len(features) != len(records):
        raise RuntimeError("tokenization changed the record count")

    return features
