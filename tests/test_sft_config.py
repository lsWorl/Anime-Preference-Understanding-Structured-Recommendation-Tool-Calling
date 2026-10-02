import json
from pathlib import Path
import sys
import unittest
from unittest.mock import mock_open, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.training.sft_config import load_s1_config

CONFIG_PATH = PROJECT_ROOT / "configs" / "s1_qlora_pilot.v0.1.json"


class S1ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def load_modified(self, **changes):
        """Exercise the public loader without writing temporary files."""
        raw = dict(self.raw, **changes)
        content = json.dumps(raw)

        with patch(
            "builtins.open",
            mock_open(read_data=content),
        ):
            return load_s1_config(CONFIG_PATH)

    def test_loads_real_configuration(self) -> None:
        config = load_s1_config(CONFIG_PATH)
        # model_id == "Qwen/Qwen3-4B"
        # max_seq_length == 768
        # lora_target_modules 是 tuple
        # 模块数量 == 7
        self.assertEqual(config.model_id, "Qwen/Qwen3-4B")
        self.assertEqual(config.max_seq_length, 768)
        self.assertEqual(type(config.lora_target_modules), tuple)
        self.assertEqual(len(config.lora_target_modules), 7)

    def test_rejects_invalid_fields_and_types(self) -> None:
        cases = (
            {"seed": True},
            {"learning_rate": float("inf")},
            {"lora_target_modules": ["q_proj", "q_proj"]},
        )

        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.load_modified(**changes)

        # 复制 self.raw，删除 seed。
        # 用 mock_open 将该字典送入 load_s1_config。
        # 断言抛出 ValueError。
        raw = self.raw.copy()
        del raw["seed"]
        content = json.dumps(raw)
        with patch("builtins.open", mock_open(read_data=content)):
            with self.assertRaises(ValueError):
                load_s1_config(CONFIG_PATH)

    def test_validates_numeric_boundaries(self) -> None:
        cases = (
            ("learning_rate", 0, False),
            ("learning_rate", 0.0002, True),
            ("lora_r", 0, False),
            ("seed", -1, False),
            ("seed", 0, True),
            ("lora_dropout", 0, True),
            ("lora_dropout", 1, False),
            ("warmup_ratio", 1, True),
            ("warmup_ratio", 1.01, False),
            ("weight_decay", -0.01, False),
        )

        # 由你实现：
        # 遍历 field、value、should_accept。
        # should_accept 为 True 时正常加载；
        # 否则使用 assertRaises(ValueError)。
        for field, value, should_accept in cases:
            with self.subTest(field=field, value=value):
                if should_accept:
                    config = self.load_modified(**{field: value})
                    self.assertEqual(getattr(config, field), value)
                else:
                    with self.assertRaises(ValueError):
                        self.load_modified(**{field: value})

    def test_rejects_frozen_identity_changes(self) -> None:
        cases = (
            {"model_id": "other-model"},
            {"revision": "other-revision"},
            {"train_path": "data/pilot/test.v0.1.jsonl"},
            {"validation_path": "data/pilot/challenge.v0.1.jsonl"},
            {"enable_thinking": True},
            {"load_in_4bit": False},
            {"bnb_4bit_quant_type": "fp4"},
            {"metric_for_best_model": "test_exact"},
        )

        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.load_modified(**changes)

    def test_accepts_required_attention_modules(self) -> None:
        modules = ["q_proj", "k_proj", "v_proj", "o_proj"]
        config = self.load_modified(
            lora_target_modules=modules,
        )
        self.assertEqual(
            config.lora_target_modules,
            tuple(modules),
        )

    def test_rejects_missing_or_forbidden_modules(self) -> None:
        cases = (
            ["q_proj"],
            ["q_proj", "k_proj", "v_proj", "o_proj", "lm_head"],
        )

        for modules in cases:
            with self.subTest(modules=modules):
                with self.assertRaises(ValueError):
                    self.load_modified(
                        lora_target_modules=modules,
                    )


if __name__ == "__main__":
    unittest.main()
