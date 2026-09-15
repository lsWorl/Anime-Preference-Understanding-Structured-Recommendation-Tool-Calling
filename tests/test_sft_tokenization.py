from copy import deepcopy
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.evaluation.e0_baseline import (
    load_e0_config,
    load_system_prompt,
)
from anime_pref.training.sft_data import load_sft_records
from anime_pref.training.sft_tokenization import (
    IGNORE_INDEX,
    tokenize_sft_record,
)

CONFIG_PATH = PROJECT_ROOT / "configs" / "e0_baseline.v0.1.json"


class FakeQwenTokenizer:
    """Minimal fake of the official chat-template interface."""

    chat_template = "fake-qwen-chat-template"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def apply_chat_template(
        self,
        messages,
        *,
        tokenize,
        add_generation_prompt,
        enable_thinking,
    ):
        self.calls.append(
            {
                "roles": [message["role"] for message in messages],
                "tokenize": tokenize,
                "add_generation_prompt": add_generation_prompt,
                "enable_thinking": enable_thinking,
            }
        )

        roles = [message["role"] for message in messages]

        if roles == ["system", "user"]:
            return [10, 11, 12]

        if roles == ["system", "user", "assistant"]:
            return [10, 11, 12, 20, 21]

        raise AssertionError(f"unexpected message roles: {roles}")


class MisalignedTokenizer(FakeQwenTokenizer):
    """Return a full sequence whose prefix differs from the prompt."""

    def apply_chat_template(
        self,
        messages,
        *,
        tokenize,
        add_generation_prompt,
        enable_thinking,
    ):
        roles = [message["role"] for message in messages]

        if roles == ["system", "user"]:
            return [10, 11, 12]

        return [10, 99, 12, 20, 21]


class EmptyTargetTokenizer(FakeQwenTokenizer):
    """Return no assistant completion tokens."""

    def apply_chat_template(
        self,
        messages,
        *,
        tokenize,
        add_generation_prompt,
        enable_thinking,
    ):
        return [10, 11, 12]


class InvalidTokenIdTokenizer(FakeQwenTokenizer):
    """Return an invalid token ID through the public tokenization path."""

    def apply_chat_template(
        self,
        messages,
        *,
        tokenize,
        add_generation_prompt,
        enable_thinking,
    ):
        roles = [message["role"] for message in messages]

        if roles == ["system", "user"]:
            return [10, 11]

        return [10, 11, -1]


class SFTTokenizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_e0_config(CONFIG_PATH, PROJECT_ROOT)
        cls.system_prompt = load_system_prompt(config, PROJECT_ROOT)
        cls.record = load_sft_records(PROJECT_ROOT, "train")[0]

    def test_builds_completion_only_labels(self) -> None:
        tokenizer = FakeQwenTokenizer()

        encoded = tokenize_sft_record(
            self.record,
            self.system_prompt,
            tokenizer,
        )

        # input_ids       == [10, 11, 12, 20, 21]
        # labels          == [-100, -100, -100, 20, 21]
        # attention_mask  == [1, 1, 1, 1, 1]
        self.assertEqual(encoded["input_ids"], [10, 11, 12, 20, 21])
        self.assertEqual(encoded["labels"], [-100, -100, -100, 20, 21])
        self.assertEqual(encoded["attention_mask"], [1, 1, 1, 1, 1])

    def test_uses_required_qwen_chat_template_flags(self) -> None:
        tokenizer = FakeQwenTokenizer()

        tokenize_sft_record(
            self.record,
            self.system_prompt,
            tokenizer,
        )

        self.assertEqual(len(tokenizer.calls), 2)

        prompt_call = tokenizer.calls[0]
        full_call = tokenizer.calls[1]

        # prompt_call roles:
        #     system, user
        # prompt_call add_generation_prompt:
        #     True
        #
        # full_call roles:
        #     system, user, assistant
        # full_call add_generation_prompt:
        #     False
        #
        # 两次调用：
        #     tokenize 都是 True
        #     enable_thinking 都是 False
        self.assertEqual(prompt_call["roles"], ["system", "user"])
        self.assertEqual(prompt_call["add_generation_prompt"], True)
        self.assertEqual(full_call["roles"], ["system", "user", "assistant"])
        self.assertEqual(full_call["add_generation_prompt"], False)
        self.assertEqual(prompt_call["tokenize"], True)
        self.assertEqual(full_call["tokenize"], True)
        self.assertEqual(prompt_call["enable_thinking"], False)
        self.assertEqual(full_call["enable_thinking"], False)

    def test_all_output_shapes_are_equal(self) -> None:
        encoded = tokenize_sft_record(
            self.record,
            self.system_prompt,
            FakeQwenTokenizer(),
        )

        # input_ids、labels、attention_mask 长度必须相等。
        self.assertEqual(
            len(encoded["input_ids"]),
            len(encoded["labels"]),
        )

        self.assertEqual(
            len(encoded["input_ids"]),
            len(encoded["attention_mask"]),
        )

    def test_does_not_mutate_dataset_record(self) -> None:
        original = deepcopy(self.record)

        tokenize_sft_record(
            self.record,
            self.system_prompt,
            FakeQwenTokenizer(),
        )

        self.assertEqual(self.record, original)

    def test_tokenization_is_deterministic(self) -> None:
        first = tokenize_sft_record(
            self.record,
            self.system_prompt,
            FakeQwenTokenizer(),
        )
        second = tokenize_sft_record(
            self.record,
            self.system_prompt,
            FakeQwenTokenizer(),
        )

        self.assertEqual(first, second)

    def test_rejects_missing_chat_template(self) -> None:
        tokenizer = FakeQwenTokenizer()
        tokenizer.chat_template = ""

        with self.assertRaises(ValueError):
            tokenize_sft_record(
                self.record,
                self.system_prompt,
                tokenizer,
            )

    def test_rejects_missing_template_method(self) -> None:
        class MissingMethodTokenizer:
            chat_template = "template"

        with self.assertRaises(ValueError):
            tokenize_sft_record(
                self.record,
                self.system_prompt,
                MissingMethodTokenizer(),
            )

    def test_rejects_misaligned_prompt_prefix(self) -> None:
        with self.assertRaises(ValueError):
            tokenize_sft_record(
                self.record,
                self.system_prompt,
                MisalignedTokenizer(),
            )

    def test_rejects_empty_assistant_target(self) -> None:
        with self.assertRaises(ValueError):
            tokenize_sft_record(
                self.record,
                self.system_prompt,
                EmptyTargetTokenizer(),
            )

    def test_rejects_invalid_token_ids(self) -> None:
        with self.assertRaises(ValueError):
            tokenize_sft_record(
                self.record,
                self.system_prompt,
                InvalidTokenIdTokenizer(),
            )


if __name__ == "__main__":
    unittest.main()
