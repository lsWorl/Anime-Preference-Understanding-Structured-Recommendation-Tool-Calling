from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.training.sft_token_audit import (
    audit_sft_token_lengths,
    nearest_rank_percentile,
)


class TokenLengthAuditTests(unittest.TestCase):
    def test_nearest_rank_percentile(self) -> None:
        lengths = [40, 10, 30, 20]
        # p=0.75 的 nearest-rank 结果应为 30。
        self.assertEqual(nearest_rank_percentile(lengths, 0.75), 30)

    def test_percentile_does_not_mutate_input(self) -> None:
        lengths = [40, 10, 30, 20]
        original = lengths.copy()

        nearest_rank_percentile(lengths, 0.95)

        # lengths 仍然等于 original。
        self.assertEqual(original, lengths)

    def test_rejects_invalid_percentile_inputs(self) -> None:
        invalid_probabilities = (
            0,
            -0.1,
            1.1,
            True,
            "0.95",
        )

        for probability in invalid_probabilities:
            with self.subTest(probability=probability):
                with self.assertRaises(ValueError):
                    nearest_rank_percentile(
                        [10, 20],
                        probability,
                    )

        with self.assertRaises(ValueError):
            nearest_rank_percentile([], 0.95)

    @patch("anime_pref.training.sft_token_audit." "tokenize_sft_record")
    def test_builds_expected_summary(
        self,
        mock_tokenize,
    ) -> None:
        train_lengths = list(range(1, 181))
        validation_lengths = list(range(201, 231))

        train_records = [{"length": length} for length in train_lengths]
        validation_records = [{"length": length} for length in validation_lengths]

        def fake_tokenize(record, system_prompt, tokenizer):
            return {
                "input_ids": [1] * record["length"],
                "labels": [1] * record["length"],
                "attention_mask": [1] * record["length"],
            }

        mock_tokenize.side_effect = fake_tokenize

        summary = audit_sft_token_lengths(
            train_records,
            validation_records,
            "system prompt",
            object(),
        )

        # train count  = 180
        # train min    = 1
        # train median = 90.5
        # train p95    = 171
        # train max    = 180
        #
        # validation count = 30
        # validation max   = 230
        # overall max      = 230
        self.assertEqual(summary["train"]["count"], 180)
        self.assertEqual(summary["train"]["min"], 1)
        self.assertEqual(summary["train"]["median"], 90.5)
        self.assertEqual(summary["train"]["p95"], 171)
        self.assertEqual(summary["train"]["max"], 180)

        self.assertEqual(summary["validation"]["count"], 30)
        self.assertEqual(summary["validation"]["max"], 230)
        self.assertEqual(summary["overall_max"], 230)

    def test_rejects_wrong_frozen_split_counts(self) -> None:
        valid_train = [{} for _ in range(180)]
        valid_validation = [{} for _ in range(30)]

        with self.assertRaises(ValueError):
            audit_sft_token_lengths(
                valid_train[:-1],
                valid_validation,
                "system prompt",
                object(),
            )

        with self.assertRaises(ValueError):
            audit_sft_token_lengths(
                valid_train,
                valid_validation[:-1],
                "system prompt",
                object(),
            )


if __name__ == "__main__":
    unittest.main()
