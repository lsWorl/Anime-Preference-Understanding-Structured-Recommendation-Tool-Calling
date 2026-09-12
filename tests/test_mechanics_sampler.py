"""Acceptance tests for D5C2 Mechanics Pattern RNG Sampler v0.1."""

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from random import Random
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import WeightTableSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.structural_signature import StructuralSignature
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.mechanics_probability import mechanics_candidates
import anime_pref.sampling.mechanics_sampler as sampler_module
from anime_pref.sampling.mechanics_sampler import sample_mechanics_pattern
from anime_pref.sampling.operator_cardinality import (
    sample_operator_cardinality_plan,
)
from anime_pref.sampling.structural_atom import structural_constraint_count


SAMPLER_PATH = PROJECT_ROOT / "tests/fixtures/semantic_sampler.synthetic.v0.1.json"


class CountingRandom:
    """Scripted RNG that makes branch choice and draw count observable."""

    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


def plan(family, bucket):
    return FamilyComplexityPlan(family, bucket)


def signature(*kinds):
    return StructuralSignature(tuple(kinds))


def atom(result, kind):
    return next(candidate for candidate in result.atoms if candidate.kind == kind)


class MechanicsSamplerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_sampler_config(SAMPLER_PATH)
        cls.path_plan = plan("cross_field_composition", "4")
        cls.path_signature = signature("genre_set", "year_range")


class PipelineTruthSourceTests(MechanicsSamplerTestCase):
    def test_public_validation_order_precedes_first_possible_draw(self):
        events = []
        real_config = sampler_module.validate_sampler_config
        real_plan = sampler_module.validate_family_complexity_plan
        real_signature = sampler_module.validate_structural_signature
        real_candidates = sampler_module.mechanics_candidates

        def validate_config(value):
            events.append("config")
            return real_config(value)

        def validate_plan(value):
            events.append("family_plan")
            return real_plan(value)

        def validate_signature(value):
            events.append("signature")
            return real_signature(value)

        def candidates(*args):
            events.append("mechanics_candidates")
            return real_candidates(*args)

        rng = CountingRandom([0.9])
        with patch.object(
            sampler_module, "validate_sampler_config", side_effect=validate_config
        ), patch.object(
            sampler_module,
            "validate_family_complexity_plan",
            side_effect=validate_plan,
        ), patch.object(
            sampler_module,
            "validate_structural_signature",
            side_effect=validate_signature,
        ), patch.object(
            sampler_module, "mechanics_candidates", side_effect=candidates
        ):
            sample_mechanics_pattern(
                self.config,
                self.path_plan,
                self.path_signature,
                rng,
            )
        self.assertEqual(
            events[:4],
            ["config", "family_plan", "signature", "mechanics_candidates"],
        )
        self.assertEqual(rng.call_count, 1)

    def test_candidate_space_comes_from_d5b_mechanics_candidates(self):
        expected = mechanics_candidates(self.path_plan, self.path_signature)
        seen = {}

        def candidates(family_plan, selected_signature):
            seen["arguments"] = (family_plan, selected_signature)
            return expected

        with patch.object(
            sampler_module,
            "mechanics_candidates",
            side_effect=candidates,
        ):
            result = sample_mechanics_pattern(
                self.config,
                self.path_plan,
                self.path_signature,
                CountingRandom([0.9]),
            )
        self.assertEqual(seen["arguments"], (self.path_plan, self.path_signature))
        self.assertIn(result, expected)

    def test_conditional_helpers_are_used_in_canonical_stage_order(self):
        events = []
        real_operator = sampler_module.conditional_operator_probabilities
        real_cardinality = sampler_module.conditional_cardinality_probabilities
        real_numeric = sampler_module.conditional_numeric_pattern_probabilities

        def operator(*args):
            events.append("genre_set.operator")
            return real_operator(*args)

        def cardinality(*args):
            events.append("genre_set.cardinality")
            return real_cardinality(*args)

        def numeric(*args):
            events.append("year_range.pattern")
            return real_numeric(*args)

        with patch.object(
            sampler_module,
            "conditional_operator_probabilities",
            side_effect=operator,
        ), patch.object(
            sampler_module,
            "conditional_cardinality_probabilities",
            side_effect=cardinality,
        ), patch.object(
            sampler_module,
            "conditional_numeric_pattern_probabilities",
            side_effect=numeric,
        ):
            sample_mechanics_pattern(
                self.config,
                self.path_plan,
                self.path_signature,
                CountingRandom([0.1, 0.9, 0.1]),
            )
        self.assertEqual(
            events,
            ["genre_set.operator", "genre_set.cardinality", "year_range.pattern"],
        )

    def test_final_result_is_the_unique_survivor_and_is_validated(self):
        events = []
        real_validate = sampler_module.validate_structural_pattern_plan

        def validate(result):
            events.append(result)
            return real_validate(result)

        with patch.object(
            sampler_module,
            "validate_structural_pattern_plan",
            side_effect=validate,
        ):
            result = sample_mechanics_pattern(
                self.config,
                self.path_plan,
                self.path_signature,
                CountingRandom([0.9]),
            )
        self.assertEqual(events, [result])


class DrawConsumptionTests(MechanicsSamplerTestCase):
    def test_payload_free_reference_only_consumes_zero_draws(self):
        rng = CountingRandom([])
        result = sample_mechanics_pattern(
            self.config,
            plan("reference_only", 0),
            signature("reference"),
            rng,
        )
        self.assertEqual(result.atoms[0].kind, "reference")
        self.assertEqual(rng.call_count, 0)

    def test_payload_free_direct_and_group_atoms_consume_zero_draws(self):
        cases = (
            (plan("single_constraint", "1"), signature("format_any")),
            (plan("single_constraint", "1"), signature("status_any")),
            (plan("normalization", "1"), signature("tag_group_any")),
            (plan("normalization", "1"), signature("tag_group_none")),
        )
        for family_plan, selected_signature in cases:
            with self.subTest(signature=selected_signature):
                rng = CountingRandom([])
                sample_mechanics_pattern(
                    self.config,
                    family_plan,
                    selected_signature,
                    rng,
                )
                self.assertEqual(rng.call_count, 0)

    def test_singleton_five_plus_completion_consumes_zero_draws(self):
        rng = CountingRandom([])
        result = sample_mechanics_pattern(
            self.config,
            plan("cross_field_composition", "5_plus"),
            signature("genre_set", "year_range"),
            rng,
        )
        self.assertEqual(atom(result, "genre_set").operator_plan.cardinality, 3)
        self.assertEqual(atom(result, "year_range").range_pattern, "bounded_range")
        self.assertEqual(rng.call_count, 0)

    def test_representative_path_a_consumes_one_draw(self):
        # Operator draw selects none_of.  Its cardinality 2 and bounded year
        # pattern are both forced by remaining exact-complexity completions.
        rng = CountingRandom([0.9])
        result = sample_mechanics_pattern(
            self.config, self.path_plan, self.path_signature, rng
        )
        self.assertEqual(atom(result, "genre_set").operator_plan.operator, "none_of")
        self.assertEqual(atom(result, "genre_set").operator_plan.cardinality, 2)
        self.assertEqual(atom(result, "year_range").range_pattern, "bounded_range")
        self.assertEqual(rng.call_count, 1)

    def test_representative_path_b_consumes_two_draws(self):
        # all_of + cardinality 2 leaves bounded_range as a singleton.
        rng = CountingRandom([0.1, 0.1])
        result = sample_mechanics_pattern(
            self.config, self.path_plan, self.path_signature, rng
        )
        self.assertEqual(atom(result, "genre_set").operator_plan.operator, "all_of")
        self.assertEqual(atom(result, "genre_set").operator_plan.cardinality, 2)
        self.assertEqual(atom(result, "year_range").range_pattern, "bounded_range")
        self.assertEqual(rng.call_count, 2)

    def test_representative_path_c_consumes_three_draws(self):
        # all_of + cardinality 3 leaves a min/max numeric choice.
        rng = CountingRandom([0.1, 0.9, 0.9])
        result = sample_mechanics_pattern(
            self.config, self.path_plan, self.path_signature, rng
        )
        self.assertEqual(atom(result, "genre_set").operator_plan.operator, "all_of")
        self.assertEqual(atom(result, "genre_set").operator_plan.cardinality, 3)
        self.assertEqual(atom(result, "year_range").range_pattern, "max_only")
        self.assertEqual(rng.call_count, 3)

    def test_tag_any_completion_uses_only_one_cardinality_draw(self):
        rng = CountingRandom([0.9])
        result = sample_mechanics_pattern(
            self.config,
            plan("normalization", "1"),
            signature("tag_set", "tag_group_any"),
            rng,
        )
        self.assertEqual(atom(result, "tag_set").operator_plan.operator, "any_of")
        self.assertEqual(atom(result, "tag_set").operator_plan.cardinality, 3)
        self.assertEqual(rng.call_count, 1)


class FailureBeforeDrawTests(MechanicsSamplerTestCase):
    def assert_fails_without_draw(self, config, family_plan, selected_signature, rng=None):
        rng = CountingRandom([0.1]) if rng is None else rng
        with self.assertRaises((TypeError, ValueError)):
            sample_mechanics_pattern(
                config,
                family_plan,
                selected_signature,
                rng,
            )
        self.assertEqual(getattr(rng, "call_count", 0), 0)

    def test_bad_config_fails_before_draw(self):
        self.assert_fails_without_draw(
            object(), self.path_plan, self.path_signature
        )

    def test_invalid_family_plan_fails_before_draw(self):
        self.assert_fails_without_draw(
            self.config,
            plan("cross_field_composition", "1"),
            self.path_signature,
        )

    def test_invalid_signature_fails_before_draw(self):
        self.assert_fails_without_draw(
            self.config,
            self.path_plan,
            signature("year_range", "genre_set"),
        )

    def test_context_ineligible_signature_fails_before_draw(self):
        self.assert_fails_without_draw(
            self.config,
            plan("cross_field_composition", "2"),
            signature("genre_set"),
        )

    def test_invalid_rng_fails_before_draw(self):
        class BadRng:
            random = 0.5
            call_count = 0

        self.assert_fails_without_draw(
            self.config,
            self.path_plan,
            self.path_signature,
            BadRng(),
        )


class CorrectnessAndDeterminismTests(MechanicsSamplerTestCase):
    def test_exact_complexity_is_maintained_on_every_representative_path(self):
        cases = ([0.9], [0.1, 0.1], [0.1, 0.9, 0.9])
        for draws in cases:
            with self.subTest(draws=draws):
                result = sample_mechanics_pattern(
                    self.config,
                    self.path_plan,
                    self.path_signature,
                    CountingRandom(draws),
                )
                self.assertEqual(structural_constraint_count(result.atoms), 4)

    def test_same_rng_state_reproduces_result_and_advancement(self):
        left = Random(5813)
        right = Random(5813)
        left_result = sample_mechanics_pattern(
            self.config, self.path_plan, self.path_signature, left
        )
        right_result = sample_mechanics_pattern(
            self.config, self.path_plan, self.path_signature, right
        )
        self.assertEqual(left_result, right_result)
        self.assertEqual(left.getstate(), right.getstate())

    def test_same_field_matches_phase_c_result_and_rng_advancement(self):
        for bucket in ("1", "2", "3"):
            for seed in (7, 29, 103):
                family_plan = plan("same_field_logic", bucket)
                phase_c_rng = Random(seed)
                d5c2_rng = Random(seed)
                phase_c = sample_operator_cardinality_plan(
                    self.config,
                    family_plan,
                    phase_c_rng,
                )
                d5c2 = sample_mechanics_pattern(
                    self.config,
                    family_plan,
                    signature("genre_set"),
                    d5c2_rng,
                )
                with self.subTest(bucket=bucket, seed=seed):
                    self.assertEqual(atom(d5c2, "genre_set").operator_plan, phase_c)
                    self.assertEqual(d5c2_rng.getstate(), phase_c_rng.getstate())

    def test_operator_table_scaling_preserves_result_and_rng_advancement(self):
        scaled = replace(
            self.config,
            operator_weights=WeightTableSpec(
                {
                    key: value * 10
                    for key, value in self.config.operator_weights.weights.items()
                }
            ),
        )
        for seed in (13, 71, 211):
            baseline_rng = Random(seed)
            scaled_rng = Random(seed)
            baseline = sample_mechanics_pattern(
                self.config, self.path_plan, self.path_signature, baseline_rng
            )
            selected = sample_mechanics_pattern(
                scaled, self.path_plan, self.path_signature, scaled_rng
            )
            self.assertEqual(baseline, selected)
            self.assertEqual(baseline_rng.getstate(), scaled_rng.getstate())

    def test_numeric_table_scaling_preserves_result_and_rng_advancement(self):
        scaled_year = replace(
            self.config.year_sampling,
            pattern_weights={
                key: value * 10
                for key, value in self.config.year_sampling.pattern_weights.items()
            },
        )
        scaled = replace(self.config, year_sampling=scaled_year)
        family_plan = plan("single_constraint", "1")
        selected_signature = signature("year_range")
        for seed in (17, 37, 101):
            baseline_rng = Random(seed)
            scaled_rng = Random(seed)
            baseline = sample_mechanics_pattern(
                self.config, family_plan, selected_signature, baseline_rng
            )
            selected = sample_mechanics_pattern(
                scaled, family_plan, selected_signature, scaled_rng
            )
            self.assertEqual(baseline, selected)
            self.assertEqual(baseline_rng.getstate(), scaled_rng.getstate())


class PhaseBoundaryTests(unittest.TestCase):
    def test_returns_structural_pattern_plan_directly(self):
        config = load_sampler_config(SAMPLER_PATH)
        result = sample_mechanics_pattern(
            config,
            plan("reference_only", 0),
            signature("reference"),
            CountingRandom([]),
        )
        self.assertIsInstance(result, StructuralPatternPlan)
        self.assertEqual(
            [field.name for field in fields(result)],
            ["semantic_family", "complexity_bucket", "atoms"],
        )

    def test_module_has_no_d5a_value_domain_or_downstream_dependency(self):
        source = inspect.getsource(sampler_module)
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        forbidden = {
            "anime_pref.sampling.structural_signature_sampler",
            "anime_pref.sampling.categorical_value",
            "anime_pref.sampling.numeric_range",
            "anime_pref.schemas.taxonomy",
            "anime_pref.data.query_builder",
            "anime_pref.schemas.preference_query",
            "anime_pref.schemas.dataset_record",
        }
        self.assertTrue(forbidden.isdisjoint(imported))
        for forbidden_text in (
            "StructuralPatternSelectionPolicySpec",
            "signature_probabilities",
            "mechanics_pattern_probabilities",
            "while ",
            "Random(",
            "SemanticSpec",
            "DatasetRecord",
        ):
            self.assertNotIn(forbidden_text, source)


if __name__ == "__main__":
    unittest.main()
