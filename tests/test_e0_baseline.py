"""Acceptance tests for strict, training-free E0 baseline evaluation."""

from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import build_query, load_domain_rules
from anime_pref.evaluation.e0_baseline import (
    ERROR_LABEL_ORDER,
    build_inference_messages,
    build_e0_metrics_bundle,
    compute_e0_metrics,
    compute_metric_slices,
    evaluate_raw_prediction,
    hard_constraint_clauses,
    is_recoverable_json,
    load_e0_config,
    load_e0_inputs,
    predictions_to_jsonl,
    strict_parse_prediction,
    validate_e0_split_authorization,
)
from anime_pref.inference.hf_baseline import generate_all
from anime_pref.schemas.e0_baseline import E0InputRecord
from anime_pref.schemas.preference_query import RangeConstraintSpec, SemanticSpec, SetConstraintSpec
import anime_pref.inference.hf_baseline as hf_module


CONFIG_PATH = PROJECT_ROOT / "configs" / "e0_baseline.v0.1.json"
RULES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "domain_rules.synthetic.v0.1.json"


class E0TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_e0_config(CONFIG_PATH, PROJECT_ROOT)
        cls.rules = load_domain_rules(RULES_PATH)
        cls.empty_gold = build_query(SemanticSpec(), cls.rules)

    def input_for(self, spec: SemanticSpec, *, text: str = "测试输入") -> E0InputRecord:
        return E0InputRecord(
            sample_id="sample_test",
            split="validation",
            user_text=text,
            gold_query=build_query(spec, self.rules),
        )

    def evaluate(self, spec: SemanticSpec, output: object, *, text: str = "测试输入"):
        raw = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return evaluate_raw_prediction(
            self.input_for(spec, text=text),
            raw,
            self.rules,
            self.config,
            self.config.revision,
        )


class ConfigPromptAndInputTests(E0TestCase):
    def test_checkpoint_and_deterministic_generation_are_frozen(self):
        self.assertEqual(self.config.model_id, "Qwen/Qwen3-4B")
        self.assertEqual(self.config.tokenizer_id, "Qwen/Qwen3-4B")
        self.assertFalse(self.config.do_sample)
        self.assertEqual(self.config.num_beams, 1)
        self.assertFalse(self.config.enable_thinking)

    def test_invalid_sampling_config_is_rejected(self):
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        raw["do_sample"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do_sample"):
                load_e0_config(path, PROJECT_ROOT)

    def test_prompt_messages_contain_no_gold_or_assistant_answer(self):
        messages = build_inference_messages("系统规则", "不要后宫")
        self.assertEqual([item["role"] for item in messages], ["system", "user"])
        self.assertEqual(messages[-1]["content"], "不要后宫")
        self.assertNotIn("gold_query", json.dumps(messages, ensure_ascii=False))

    def test_test_and_challenge_require_frozen_prompt(self):
        unfrozen = replace(self.config, prompt_frozen=False)
        self.assertIsNone(validate_e0_split_authorization(unfrozen, "validation"))
        for split in ("test", "challenge"):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "prompt_frozen"):
                validate_e0_split_authorization(unfrozen, split)
        self.assertIsNone(validate_e0_split_authorization(self.config, "test"))

    def test_validation_test_and_challenge_inputs_have_expected_counts(self):
        base = PROJECT_ROOT / "data" / "pilot"
        self.assertEqual(len(load_e0_inputs(base / "validation.v0.1.jsonl", "validation")), 30)
        self.assertEqual(len(load_e0_inputs(base / "test.v0.1.jsonl", "test")), 30)
        self.assertEqual(len(load_e0_inputs(base / "challenge.v0.1.jsonl", "challenge")), 12)

    def test_retained_real_predictions_cover_every_evaluation_input_once(self):
        artifact_dir = PROJECT_ROOT / "artifacts" / "e0"
        input_dir = PROJECT_ROOT / "data" / "pilot"
        for split, expected in (("validation", 30), ("test", 30), ("challenge", 12)):
            with self.subTest(split=split):
                predictions = [
                    json.loads(line)
                    for line in (artifact_dir / f"{split}_predictions.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                inputs = load_e0_inputs(input_dir / f"{split}.v0.1.jsonl", split)
                self.assertEqual(len(predictions), expected)
                self.assertEqual(
                    [row["sample_id"] for row in predictions],
                    [row.sample_id for row in inputs],
                )
                self.assertTrue(all(isinstance(row["raw_model_output"], str) for row in predictions))
                self.assertTrue(all(row["model_id"] == "Qwen/Qwen3-4B" for row in predictions))

    def test_real_determinism_evidence_is_retained(self):
        evidence = json.loads(
            (PROJECT_ROOT / "artifacts" / "e0" / "determinism_check.json")
            .read_text(encoding="utf-8")
        )
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["prompt_version"], "e0-json-extraction-v0.2")


class LayeredEvaluationTests(E0TestCase):
    def test_raw_json_exact_match_passes_all_layers(self):
        result = self.evaluate(SemanticSpec(), self.empty_gold)
        self.assertIsNone(result.parse_error)
        self.assertIsNone(result.schema_error)
        self.assertIsNone(result.domain_error)
        self.assertTrue(result.exact_match)
        self.assertEqual(result.error_labels, ())

    def test_key_and_set_order_do_not_break_canonical_exact_match(self):
        spec = SemanticSpec(genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")))
        prediction = build_query(spec, self.rules)
        prediction["hard_constraints"]["genres"]["any_of"].reverse()
        result = self.evaluate(spec, prediction)
        self.assertTrue(result.exact_match)

    def test_code_fence_is_primary_parse_failure_but_recoverable(self):
        raw = "```json\n" + json.dumps(self.empty_gold) + "\n```"
        result = self.evaluate(SemanticSpec(), raw)
        self.assertEqual(result.error_labels, ("JSON_PARSE_ERROR",))
        self.assertIsNone(result.parsed_prediction)
        self.assertTrue(result.recoverable_json)
        self.assertFalse(result.exact_match)

    def test_schema_and_domain_errors_remain_separate(self):
        malformed = {"hard_constraints": {}}
        schema_result = self.evaluate(SemanticSpec(), malformed)
        self.assertEqual(schema_result.error_labels, ("SCHEMA_ERROR",))
        invalid_domain = json.loads(json.dumps(self.empty_gold))
        invalid_domain["hard_constraints"]["genres"]["all_of"] = ["Not A Genre"]
        domain_result = self.evaluate(SemanticSpec(), invalid_domain)
        self.assertEqual(domain_result.error_labels, ("DOMAIN_ERROR",))

    def test_missing_hallucinated_operator_value_and_numeric_errors_can_coexist(self):
        gold_spec = SemanticSpec(
            genres=SetConstraintSpec(any_of=("Mystery",)),
            year=RangeConstraintSpec(min=2020),
        )
        prediction = build_query(
            SemanticSpec(
                genres=SetConstraintSpec(all_of=("Mystery", "Sci-Fi")),
                year=RangeConstraintSpec(max=2020),
            ),
            self.rules,
        )
        result = self.evaluate(gold_spec, prediction)
        for label in (
            "MISSING_CONSTRAINT",
            "HALLUCINATED_CONSTRAINT",
            "WRONG_OPERATOR",
            "WRONG_VALUE",
            "WRONG_NUMERIC_BOUND",
        ):
            self.assertIn(label, result.error_labels)

    def test_reference_hallucination_is_detected(self):
        spec = SemanticSpec(reference_titles=("Steins;Gate",))
        prediction = build_query(
            SemanticSpec(
                genres=SetConstraintSpec(all_of=("Sci-Fi",)),
                reference_titles=("Steins;Gate",),
            ),
            self.rules,
        )
        result = self.evaluate(spec, prediction)
        self.assertIn("HALLUCINATED_CONSTRAINT", result.error_labels)
        self.assertNotIn("REFERENCE_ERROR", result.error_labels)

    def test_harem_error_receives_normalization_label(self):
        spec = SemanticSpec(tag_groups=SetConstraintSpec(none_of=("HAREM",)))
        result = self.evaluate(spec, self.empty_gold, text="不要后宫")
        self.assertIn("NORMALIZATION_ERROR", result.error_labels)
        self.assertIn("MISSING_CONSTRAINT", result.error_labels)

    def test_raw_output_and_generation_identity_are_retained(self):
        raw = json.dumps(self.empty_gold)
        result = self.evaluate(SemanticSpec(), raw)
        serialized = json.loads(predictions_to_jsonl((result,)))
        self.assertEqual(serialized["raw_model_output"], raw)
        self.assertEqual(serialized["model_id"], "Qwen/Qwen3-4B")
        self.assertEqual(serialized["prompt_version"], self.config.prompt_version)


class ConstraintAndMetricTests(E0TestCase):
    def test_clause_units_match_frozen_any_and_independent_semantics(self):
        query = build_query(
            SemanticSpec(
                genres=SetConstraintSpec(
                    all_of=("Drama",),
                    any_of=("Mystery", "Sci-Fi"),
                    none_of=("Horror",),
                ),
                formats=("MOVIE", "TV"),
            ),
            self.rules,
        )
        clauses = hard_constraint_clauses(query)
        self.assertIn(("genres", "all_of", "Drama"), clauses)
        self.assertIn(("genres", "any_of", ("Mystery", "Sci-Fi")), clauses)
        self.assertIn(("genres", "none_of", "Horror"), clauses)
        self.assertIn(("formats", "any_of", ("MOVIE", "TV")), clauses)
        self.assertEqual(len(clauses), 4)

    def test_metrics_use_strict_primary_results(self):
        exact = self.evaluate(SemanticSpec(), self.empty_gold)
        fenced = self.evaluate(SemanticSpec(), "```json\n" + json.dumps(self.empty_gold) + "\n```")
        rows = [json.loads(predictions_to_jsonl((item,))) for item in (exact, fenced)]
        metrics = compute_e0_metrics(rows)
        self.assertEqual(metrics["json_parse_rate"], 0.5)
        self.assertEqual(metrics["recoverable_json_rate"], 1.0)
        self.assertEqual(metrics["exact_match_rate"], 0.5)

    def test_slice_metrics_and_bundle_are_generated(self):
        item = self.evaluate(SemanticSpec(), self.empty_gold)
        row = json.loads(predictions_to_jsonl((item,)))
        row["semantic_family"] = "reference_only"
        row["constraint_count"] = 0
        row["constraint_signature"] = "NO_HARD_CONSTRAINT"
        self.assertIn("reference_only", compute_metric_slices((row,), "semantic_family"))
        bundle = build_e0_metrics_bundle((row,), (row,), (row,))
        self.assertEqual(bundle["challenge"]["overall"]["total"], 1)
        self.assertEqual(set(bundle), {"validation", "test", "challenge"})

    def test_all_required_error_labels_are_reported_in_metrics(self):
        item = self.evaluate(SemanticSpec(), "not json")
        row = json.loads(predictions_to_jsonl((item,)))
        metrics = compute_e0_metrics((row,))
        self.assertEqual(tuple(metrics["error_counts"]), ERROR_LABEL_ORDER)


class InferenceBoundaryTests(unittest.TestCase):
    def test_generate_all_preserves_order_and_one_output_per_input(self):
        class FakeAdapter:
            def generate_batch(self, values):
                return tuple(f"output:{value}" for value in values)

        self.assertEqual(
            generate_all(FakeAdapter(), ("a", "b", "c"), 2),
            ("output:a", "output:b", "output:c"),
        )

    def test_inference_module_contains_no_training_operations(self):
        source = inspect.getsource(hf_module)
        for forbidden in ("optimizer", ".backward(", "SFTTrainer", "LoraConfig", "PeftModel"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
