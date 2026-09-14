from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import dumps_query
from anime_pref.evaluation.e0_baseline import (
    load_e0_config,
    load_system_prompt,
)
from anime_pref.training.sft_data import (
    build_sft_messages,
    load_sft_records,
)

CONFIG_PATH = PROJECT_ROOT / "configs" / "e0_baseline.v0.1.json"


class SFTDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_e0_config(CONFIG_PATH, PROJECT_ROOT)
        cls.system_prompt = load_system_prompt(config, PROJECT_ROOT)

        cls.train_records = load_sft_records(PROJECT_ROOT, "train")
        cls.validation_records = load_sft_records(
            PROJECT_ROOT,
            "validation",
        )

        cls.record = cls.train_records[0]

    def test_loads_only_frozen_training_splits(self) -> None:
        # 1. train 数量必须为 180
        # 2. validation 数量必须为 30
        self.assertEqual(len(self.train_records), 180)
        self.assertEqual(len(self.validation_records), 30)
        # 3. test 和 challenge 必须抛出 ValueError
        for forbidden_split in ("test", "challenge"):
            with self.subTest(split=forbidden_split):
                with self.assertRaises(ValueError):
                    load_sft_records(PROJECT_ROOT, forbidden_split)

    def test_builds_exact_three_message_sequence(self) -> None:
        messages = build_sft_messages(
            self.record,
            self.system_prompt,
        )

        # 你来实现：
        # 1. messages 长度为 3
        # 2. role 顺序严格为 system、user、assistant
        # 3. 每个消息的 key 集合只能是 role 和 content
        self.assertEqual(len(messages), 3)
        self.assertEqual(
            [message["role"] for message in messages],
            ["system", "user", "assistant"],
        )

        for message in messages:
            self.assertEqual(
                set(message),
                {"role", "content"},
            )
            self.assertIsInstance(message["content"], str)

    def test_message_contents_match_frozen_sources(self) -> None:
        messages = build_sft_messages(
            self.record,
            self.system_prompt,
        )

        # system content == self.system_prompt
        # user content == self.record["user_text"]
        # assistant content == dumps_query(self.record["gold_query"])
        self.assertEqual(messages[0]["content"], self.system_prompt)
        self.assertEqual(messages[1]["content"], self.record["user_text"])
        self.assertEqual(messages[2]["content"], dumps_query(self.record["gold_query"]))

    def test_assistant_contains_only_canonical_gold_query(self) -> None:
        messages = build_sft_messages(
            self.record,
            self.system_prompt,
        )
        assistant_content = messages[2]["content"]

        # 1. json.loads(assistant_content) 等于 gold_query
        # 2. assistant_content 等于 dumps_query 的结果
        # 3. assistant content 中没有 sample_id
        parsed_assistant = json.loads(assistant_content)
        self.assertEqual(
            parsed_assistant,
            self.record["gold_query"],
        )
        self.assertEqual(
            assistant_content,
            dumps_query(self.record["gold_query"]),
        )
        self.assertNotIn(
            self.record["sample_id"],
            assistant_content,
        )

    def test_message_construction_is_deterministic(self) -> None:
        # 对同一输入调用两次 build_sft_messages。
        # 断言两个结果完全相同。
        first = build_sft_messages(
            self.record,
            self.system_prompt,
        )

        second = build_sft_messages(
            self.record,
            self.system_prompt,
        )

        self.assertEqual(first, second)

    def test_rejects_invalid_system_prompt(self) -> None:
        for invalid_prompt in (
            "",
            " prompt",
            "prompt ",
            None,
            123,
        ):
            with self.subTest(invalid_prompt=invalid_prompt):
                with self.assertRaises(ValueError):
                    build_sft_messages(
                        self.record,
                        invalid_prompt,
                    )

    def test_rejects_invalid_user_text(self) -> None:
        for invalid_text in (
            "",
            " 用户文本",
            "用户文本 ",
            None,
            123,
        ):
            with self.subTest(invalid_text=invalid_text):
                invalid_record = deepcopy(self.record)
                invalid_record["user_text"] = invalid_text

                with self.assertRaises(ValueError):
                    build_sft_messages(
                        invalid_record,
                        self.system_prompt,
                    )

    def test_rejects_missing_or_invalid_gold_query(self) -> None:
        # 1. 从复制的记录中删除 gold_query
        # 2. 将 gold_query 改成结构非法的字典
        #
        # 两种情况都必须抛出 ValueError。
        missing_gold = deepcopy(self.record)
        missing_gold.pop("gold_query")
        with self.assertRaises(ValueError):
            build_sft_messages(
                missing_gold,
                self.system_prompt,
            )
        invalid_gold = deepcopy(self.record)
        invalid_gold["gold_query"] = {}

        with self.assertRaises(ValueError):
            build_sft_messages(
                invalid_gold,
                self.system_prompt,
            )

    def test_provenance_never_enters_messages(self) -> None:
        messages = build_sft_messages(
            self.record,
            self.system_prompt,
        )
        serialized_messages = json.dumps(
            messages,
            ensure_ascii=False,
        )

        provenance_values = (
            self.record["sample_id"],
            self.record["template_id"],
            self.record["rules_hash"],
            self.record["executable_subset_hash"],
        )

        # 你来实现：
        # 逐一确认 provenance_values 不存在于 serialized_messages。
        for provenance_value in provenance_values:
            with self.subTest(provenance_value=provenance_value):
                self.assertNotIn(
                    provenance_value,
                    serialized_messages,
                )


if __name__ == "__main__":
    unittest.main()
