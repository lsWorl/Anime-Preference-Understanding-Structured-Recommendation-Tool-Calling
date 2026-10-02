from copy import deepcopy
from pathlib import Path
import sys
import unittest

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.training.sft_collator import SFTDataCollator


class SFTCollatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.features = [
            {
                "input_ids": [10, 11, 20],
                "attention_mask": [1, 1, 1],
                "labels": [-100, -100, 20],
            },
            {
                "input_ids": [10, 11, 12, 20, 21],
                "attention_mask": [1, 1, 1, 1, 1],
                "labels": [-100, -100, -100, 20, 21],
            },
        ]
        self.collator = SFTDataCollator(
            pad_token_id=0,
            max_seq_length=768,
        )

    def test_right_padding_preserves_labels(self) -> None:
        batch = self.collator(self.features)

        # 用 tensor.tolist() 与下面三个列表比较。
        # input_ids:
        # [[10, 11, 20, 0, 0],
        #  [10, 11, 12, 20, 21]]
        #
        # attention_mask:
        # [[1, 1, 1, 0, 0],
        #  [1, 1, 1, 1, 1]]
        #
        # labels:
        # [[-100, -100, 20, -100, -100],
        #  [-100, -100, -100, 20, 21]]
        self.assertEqual(
            batch["input_ids"].tolist(),
            [
                [10, 11, 20, 0, 0],
                [10, 11, 12, 20, 21],
            ],
        )
        self.assertEqual(
            batch["attention_mask"].tolist(),
            [
                [1, 1, 1, 0, 0],
                [1, 1, 1, 1, 1],
            ],
        )
        self.assertEqual(
            batch["labels"].tolist(),
            [
                [-100, -100, 20, -100, -100],
                [-100, -100, -100, 20, 21],
            ],
        )

    def test_returns_cpu_integer_tensors(self) -> None:
        batch = self.collator(self.features)

        # 遍历 batch.values()，逐一确认：
        # tuple(tensor.shape) == (2, 5)
        # tensor.dtype == torch.long
        # tensor.device.type == "cpu"
        for value in batch.values():
            self.assertEqual(tuple(value.shape),(2,5))
            self.assertEqual(value.dtype,torch.long)
            self.assertEqual(value.device.type,"cpu")


    def test_does_not_mutate_features(self) -> None:
        original = deepcopy(self.features)
        self.collator(self.features)

        #features 与 original 完全相同。
        self.assertEqual(self.features,original)

    def test_single_sample_keeps_batch_dimension(self) -> None:
        batch = self.collator([self.features[0]])

        self.assertEqual(
            tuple(batch["input_ids"].shape),
            (1, 3),
        )

    def test_rejects_overlong_sample(self) -> None:
        collator = SFTDataCollator(
            pad_token_id=0,
            max_seq_length=4,
        )

        with self.assertRaises(ValueError):
            collator(self.features)

    def test_rejects_invalid_features(self) -> None:
        cases = []

        # 三组长度不一致。
        mismatched = deepcopy(self.features[0])
        mismatched["labels"].pop()
        cases.append(mismatched)

        # 输入已经填充，不符合 collator 的输入合同。
        padded = deepcopy(self.features[0])
        padded["attention_mask"][-1] = 0
        cases.append(padded)

        # 完全没有可监督 token。
        unsupervised = deepcopy(self.features[0])
        unsupervised["labels"] = [-100, -100, -100]
        cases.append(unsupervised)

        # 非忽略 label 与 input token 不一致。
        wrong_label = deepcopy(self.features[0])
        wrong_label["labels"][-1] = 99
        cases.append(wrong_label)

        for feature in cases:
            with self.subTest(feature=feature):
                with self.assertRaises(ValueError):
                    self.collator([feature])

        with self.assertRaises(ValueError):
            self.collator([])


if __name__ == "__main__":
    unittest.main()
