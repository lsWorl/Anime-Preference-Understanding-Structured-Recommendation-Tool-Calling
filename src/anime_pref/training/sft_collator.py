"""Right-pad tokenized SFT samples while preserving completion-only labels."""

from typing import Any

from anime_pref.training.sft_tokenization import IGNORE_INDEX


class SFTDataCollator:
    def __init__(
        self,
        pad_token_id: int,
        max_seq_length: int,
    ) -> None:
        if (
            isinstance(pad_token_id, bool)
            or not isinstance(pad_token_id, int)
            or pad_token_id < 0
        ):
            raise ValueError("pad_token_id must be a nonnegative integer")

        if (
            isinstance(max_seq_length, bool)
            or not isinstance(max_seq_length, int)
            or max_seq_length < 1
        ):
            raise ValueError("max_seq_length must be a positive integer")

        self.pad_token_id = pad_token_id
        self.max_seq_length = max_seq_length

    def __call__(
        self,
        features: list[dict[str, list[int]]],
    ) -> dict[str, Any]:
        import torch

        if not isinstance(features, list) or not features:
            raise ValueError("features must be a nonempty list")

        expected_keys = {"input_ids", "attention_mask", "labels"}
        lengths = []

        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                raise ValueError(f"features[{index}] must be a dict")

            if set(feature) != expected_keys:
                raise ValueError(f"features[{index}] has invalid keys")

            for name in expected_keys:
                values = feature[name]
                if not isinstance(values, list) or not values:
                    raise ValueError(
                        f"features[{index}].{name} must be a nonempty list"
                    )
                if any(type(value) is not int for value in values):
                    raise ValueError(f"features[{index}].{name} must contain integers")

            input_ids = feature["input_ids"]
            labels = feature["labels"]
            attention_mask = feature["attention_mask"]

            if not (len(input_ids) == len(labels) == len(attention_mask)):
                raise ValueError(f"features[{index}] has mismatched lengths")

            if len(input_ids) > self.max_seq_length:
                raise ValueError(
                    f"features[{index}] exceeds max_seq_length; "
                    "truncation is forbidden"
                )

            if any(token_id < 0 for token_id in input_ids):
                raise ValueError("input_ids must be nonnegative")

            if any(value != 1 for value in attention_mask):
                raise ValueError("input features must be unpadded")

            if any(
                label != IGNORE_INDEX and label != token_id
                for label, token_id in zip(labels, input_ids)
            ):
                raise ValueError("unmasked labels must match input_ids")

            if all(label == IGNORE_INDEX for label in labels):
                raise ValueError("each sample must have supervised tokens")

            lengths.append(len(input_ids))

        # 只填充到当前 batch 最长样本，不固定填充到 768。
        batch_width = max(lengths)

        padded_input_ids = []
        padded_attention_masks = []
        padded_labels = []

        for feature in features:
            padding_length = batch_width - len(feature["input_ids"])
            padded_input_ids.append(
                feature["input_ids"] + [self.pad_token_id] * padding_length
            )
            padded_attention_masks.append(
                feature["attention_mask"] + [0] * padding_length
            )
            padded_labels.append(
                feature["labels"] + [IGNORE_INDEX] * padding_length
            )

        # 返回 CPU 上的二维整数 tensor。
        # 后续 Trainer 负责移动到 GPU。
        batch = {
            "input_ids": torch.tensor(padded_input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(padded_attention_masks, dtype=torch.long),
            "labels": torch.tensor(padded_labels, dtype=torch.long),
        }

        expected_shape = (len(features), batch_width)

        for name, tensor in batch.items():
            if tuple(tensor.shape) != expected_shape:
                raise RuntimeError(f"{name} has unexpected batch shape")

        # 所有 padding 位置必须不参与 loss。
        padding_positions = batch["attention_mask"] == 0
        if (batch["labels"][padding_positions] != IGNORE_INDEX).any().item():
            raise RuntimeError("padding labels must be IGNORE_INDEX")

        return batch
