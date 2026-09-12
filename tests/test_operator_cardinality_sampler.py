"""Acceptance tests for direct set-logic operator/cardinality sampling v0.1."""

from dataclasses import fields, replace
import math
from pathlib import Path
from random import Random
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.sampler_config import (
    OperatorCardinalityPolicySpec,
    WeightTableSpec,
)
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.family_complexity import (
    FAMILY_COMPLEXITY_COMPATIBILITY,
    validate_family_complexity_plan,
)
from anime_pref.sampling.operator_cardinality import (
    conditional_cardinality_probabilities,
    constraint_contribution,
    eligible_operator_cardinality_pairs,
    joint_operator_cardinality_probabilities,
    operator_probabilities,
    sample_operator_cardinality_plan,
    validate_operator_cardinality_plan,
)

SAMPLER_CONFIG_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "semantic_sampler.synthetic.v0.1.json"
)


class CountingRandom:
    """Deterministic RNG double used to assert exact random-draw consumption."""

    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


def same_field_plan(complexity: str) -> FamilyComplexityPlan:
    return FamilyComplexityPlan("same_field_logic", complexity)


class FamilyComplexityPlanValidationTests(unittest.TestCase):
    def test_accepts_every_frozen_family_bucket_pair(self):
        valid = tuple(
            (family, bucket)
            for family, buckets in FAMILY_COMPLEXITY_COMPATIBILITY.items()
            for bucket in buckets
        )
        for family, bucket in valid:
            with self.subTest(family=family, bucket=bucket):
                self.assertIsNone(
                    validate_family_complexity_plan(
                        FamilyComplexityPlan(family, bucket)
                    )
                )

    def test_rejects_invalid_direct_construction_and_incompatible_pairs(self):
        invalid = (
            object(),
            FamilyComplexityPlan("unknown", "1"),
            FamilyComplexityPlan("single_constraint", "2"),
            FamilyComplexityPlan("cross_field_composition", "1"),
            FamilyComplexityPlan("same_field_logic", 0),
            FamilyComplexityPlan("reference_only", "1"),
            FamilyComplexityPlan("reference_only", False),
            FamilyComplexityPlan("normalization", 5),
        )
        for plan in invalid:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    validate_family_complexity_plan(plan)


class GenericOperatorCardinalityContractTests(unittest.TestCase):
    def test_accepts_every_allowed_generic_pair(self):
        valid = {
            ("all_of", 1),
            ("all_of", 2),
            ("all_of", 3),
            ("any_of", 2),
            ("any_of", 3),
            ("none_of", 1),
            ("none_of", 2),
        }
        for operator, cardinality in valid:
            with self.subTest(operator=operator, cardinality=cardinality):
                self.assertIsNone(
                    validate_operator_cardinality_plan(
                        OperatorCardinalityPlan(operator, cardinality)
                    )
                )

    def test_rejects_unknown_operator_illegal_cardinality_bool_and_wrong_type(self):
        invalid = (
            object(),
            OperatorCardinalityPlan("unknown", 1),
            OperatorCardinalityPlan("all_of", 0),
            OperatorCardinalityPlan("all_of", 4),
            OperatorCardinalityPlan("any_of", 1),
            OperatorCardinalityPlan("none_of", 3),
            OperatorCardinalityPlan("all_of", True),
            OperatorCardinalityPlan("all_of", "1"),
        )
        for plan in invalid:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    validate_operator_cardinality_plan(plan)

    def test_direct_constraint_contribution_matches_frozen_semantics(self):
        expected = {
            ("all_of", 1): 1,
            ("all_of", 2): 2,
            ("all_of", 3): 3,
            ("any_of", 2): 1,
            ("any_of", 3): 1,
            ("none_of", 1): 1,
            ("none_of", 2): 2,
        }
        for pair, contribution in expected.items():
            with self.subTest(pair=pair):
                self.assertEqual(constraint_contribution(*pair), contribution)

    def test_contribution_rejects_illegal_generic_pair(self):
        with self.assertRaises(ValueError):
            constraint_contribution("any_of", 1)


class SameFieldEligibilityTests(unittest.TestCase):
    def test_complexity_one_has_complete_canonical_pair_set(self):
        self.assertEqual(
            eligible_operator_cardinality_pairs(same_field_plan("1")),
            (
                ("all_of", 1),
                ("any_of", 2),
                ("any_of", 3),
                ("none_of", 1),
            ),
        )

    def test_complexity_two_has_complete_canonical_pair_set(self):
        self.assertEqual(
            eligible_operator_cardinality_pairs(same_field_plan("2")),
            (("all_of", 2), ("none_of", 2)),
        )

    def test_complexity_three_has_only_all_of_three(self):
        self.assertEqual(
            eligible_operator_cardinality_pairs(same_field_plan("3")),
            (("all_of", 3),),
        )

    def test_other_families_are_explicitly_out_of_scope(self):
        other_plans = (
            FamilyComplexityPlan("single_constraint", "1"),
            FamilyComplexityPlan("cross_field_composition", "2"),
            FamilyComplexityPlan("normalization", "1"),
            FamilyComplexityPlan("reference_only", 0),
            FamilyComplexityPlan("reference_composition", "1"),
        )
        for plan in other_plans:
            with self.subTest(plan=plan):
                with self.assertRaisesRegex(ValueError, "same_field_logic"):
                    eligible_operator_cardinality_pairs(plan)


class OperatorCardinalityProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def assert_probability_maps_close(self, actual, expected):
        self.assertEqual(list(actual), list(expected))
        for key in actual:
            self.assertTrue(
                math.isclose(actual[key], expected[key], rel_tol=1e-12),
                msg=f"probability differs at {key}: {actual[key]} != {expected[key]}",
            )
        self.assertTrue(math.isclose(sum(actual.values()), 1.0))

    def test_operator_probabilities_use_only_eligible_operators(self):
        expected = {
            "1": {"all_of": 0.45, "any_of": 0.30, "none_of": 0.25},
            "2": {"all_of": 45 / 70, "none_of": 25 / 70},
            "3": {"all_of": 1.0},
        }
        for complexity, probabilities in expected.items():
            with self.subTest(complexity=complexity):
                self.assert_probability_maps_close(
                    operator_probabilities(
                        self.config,
                        same_field_plan(complexity),
                    ),
                    probabilities,
                )

    def test_conditional_cardinality_probabilities_use_only_eligible_counts(self):
        cases = (
            ("1", "all_of", {1: 1.0}),
            ("1", "any_of", {2: 0.8, 3: 0.2}),
            ("1", "none_of", {1: 1.0}),
            ("2", "all_of", {2: 1.0}),
            ("2", "none_of", {2: 1.0}),
            ("3", "all_of", {3: 1.0}),
        )
        for complexity, operator, probabilities in cases:
            with self.subTest(complexity=complexity, operator=operator):
                self.assert_probability_maps_close(
                    conditional_cardinality_probabilities(
                        self.config,
                        same_field_plan(complexity),
                        operator,
                    ),
                    probabilities,
                )

    def test_ineligible_operator_has_no_conditional_candidate_space(self):
        cases = (("2", "any_of"), ("3", "any_of"), ("3", "none_of"))
        for complexity, operator in cases:
            with self.subTest(complexity=complexity, operator=operator):
                with self.assertRaises(ValueError):
                    conditional_cardinality_probabilities(
                        self.config,
                        same_field_plan(complexity),
                        operator,
                    )

    def test_joint_probabilities_follow_hierarchical_formula_and_sum_to_one(self):
        for complexity in ("1", "2", "3"):
            with self.subTest(complexity=complexity):
                family_plan = same_field_plan(complexity)
                operators = operator_probabilities(self.config, family_plan)
                joint = joint_operator_cardinality_probabilities(
                    self.config,
                    family_plan,
                )
                self.assertEqual(
                    list(joint),
                    list(eligible_operator_cardinality_pairs(family_plan)),
                )
                self.assertTrue(math.isclose(sum(joint.values()), 1.0))
                for (operator, cardinality), probability in joint.items():
                    conditional = conditional_cardinality_probabilities(
                        self.config,
                        family_plan,
                        operator,
                    )
                    self.assertTrue(
                        math.isclose(
                            probability,
                            operators[operator] * conditional[cardinality],
                        )
                    )

    def test_operator_table_scale_does_not_change_joint_distribution(self):
        scaled = replace(
            self.config,
            operator_weights=WeightTableSpec(
                {
                    key: value * 17
                    for key, value in self.config.operator_weights.weights.items()
                }
            ),
        )
        for complexity in ("1", "2", "3"):
            plan = same_field_plan(complexity)
            self.assert_probability_maps_close(
                joint_operator_cardinality_probabilities(scaled, plan),
                joint_operator_cardinality_probabilities(self.config, plan),
            )

    def test_relevant_cardinality_table_scale_does_not_change_distribution(self):
        original = self.config.operator_cardinality
        scaled = replace(
            self.config,
            operator_cardinality=OperatorCardinalityPolicySpec(
                all_of=original.all_of,
                any_of={key: value * 23 for key, value in original.any_of.items()},
                none_of=original.none_of,
            ),
        )
        plan = same_field_plan("1")
        self.assert_probability_maps_close(
            joint_operator_cardinality_probabilities(scaled, plan),
            joint_operator_cardinality_probabilities(self.config, plan),
        )


class OperatorCardinalityRngTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def test_complexity_three_is_deterministic_and_consumes_no_draw(self):
        rng = CountingRandom([])
        result = sample_operator_cardinality_plan(
            self.config,
            same_field_plan("3"),
            rng,
        )
        self.assertEqual(result, OperatorCardinalityPlan("all_of", 3))
        self.assertEqual(rng.call_count, 0)

    def test_complexity_two_consumes_only_operator_draw(self):
        cases = ((0.0, OperatorCardinalityPlan("all_of", 2)), (0.99, OperatorCardinalityPlan("none_of", 2)))
        for draw, expected in cases:
            with self.subTest(draw=draw):
                rng = CountingRandom([draw])
                self.assertEqual(
                    sample_operator_cardinality_plan(
                        self.config,
                        same_field_plan("2"),
                        rng,
                    ),
                    expected,
                )
                self.assertEqual(rng.call_count, 1)

    def test_complexity_one_any_of_consumes_conditional_second_draw(self):
        # 0.50 falls in any_of's operator interval; 0.90 selects cardinality 3.
        rng = CountingRandom([0.50, 0.90])
        result = sample_operator_cardinality_plan(
            self.config,
            same_field_plan("1"),
            rng,
        )
        self.assertEqual(result, OperatorCardinalityPlan("any_of", 3))
        self.assertEqual(rng.call_count, 2)

    def test_complexity_one_deterministic_cardinality_consumes_one_draw(self):
        cases = ((0.10, OperatorCardinalityPlan("all_of", 1)), (0.90, OperatorCardinalityPlan("none_of", 1)))
        for draw, expected in cases:
            with self.subTest(draw=draw):
                rng = CountingRandom([draw])
                self.assertEqual(
                    sample_operator_cardinality_plan(
                        self.config,
                        same_field_plan("1"),
                        rng,
                    ),
                    expected,
                )
                self.assertEqual(rng.call_count, 1)

    def test_equal_rng_state_reproduces_same_sequence(self):
        plans = tuple(same_field_plan(value) for value in ("1", "2", "3") * 40)
        left_rng = Random(2718)
        right_rng = Random(2718)
        left = [
            sample_operator_cardinality_plan(self.config, plan, left_rng)
            for plan in plans
        ]
        right = [
            sample_operator_cardinality_plan(self.config, plan, right_rng)
            for plan in plans
        ]
        self.assertEqual(left, right)

    def test_requires_explicit_rng_even_for_deterministic_context(self):
        for rng in (None, object(), type("BadRng", (), {"random": 0.5})()):
            with self.subTest(rng=rng):
                with self.assertRaises(ValueError):
                    sample_operator_cardinality_plan(
                        self.config,
                        same_field_plan("3"),
                        rng,
                    )


class PhaseBoundaryTests(unittest.TestCase):
    def test_output_contains_no_field_values_or_downstream_objects(self):
        self.assertEqual(
            [field.name for field in fields(OperatorCardinalityPlan)],
            ["operator", "cardinality"],
        )
        plan = OperatorCardinalityPlan("any_of", 2)
        for forbidden in (
            "field",
            "values",
            "tag_group",
            "semantic_spec",
            "dataset_record",
            "user_text",
        ):
            self.assertFalse(hasattr(plan, forbidden))


if __name__ == "__main__":
    unittest.main()
