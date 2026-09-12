"""Acceptance tests for B. Family + Complexity Planner v0.1."""

from dataclasses import fields, replace
import math
from pathlib import Path
from random import Random
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import WeightTableSpec
from anime_pref.sampling.config import (
    SEMANTIC_FAMILY_ORDER,
    load_sampler_config,
)
from anime_pref.sampling.family_complexity import (
    FAMILY_COMPLEXITY_COMPATIBILITY,
    _weighted_choice,
    compatible_complexity_buckets,
    complexity_marginal_probabilities,
    conditional_complexity_probabilities,
    family_probabilities,
    joint_family_complexity_probabilities,
    normalize_relative_weights,
    sample_family_complexity_plan,
)

SAMPLER_CONFIG_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "semantic_sampler.synthetic.v0.1.json"
)


class CountingRandom:
    """Small deterministic RNG double that exposes random-draw consumption."""

    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


class NormalizeRelativeWeightsTests(unittest.TestCase):
    def test_normalizes_without_mutation_and_preserves_key_order(self):
        weights = {"third": 3, "first": 1, "second": 2}
        original = dict(weights)

        probabilities = normalize_relative_weights(weights)

        self.assertEqual(list(probabilities), list(weights))
        self.assertEqual(weights, original)
        self.assertIsNot(probabilities, weights)
        self.assertTrue(math.isclose(sum(probabilities.values()), 1.0))
        self.assertEqual(
            probabilities,
            {"third": 3 / 6, "first": 1 / 6, "second": 2 / 6},
        )

    def test_normalization_is_invariant_to_positive_scale(self):
        baseline = normalize_relative_weights({"a": 1, "b": 2, "c": 7})
        scaled = normalize_relative_weights({"a": 100, "b": 200, "c": 700})

        for key in baseline:
            self.assertTrue(math.isclose(baseline[key], scaled[key]))

    def test_rejects_invalid_direct_weight_inputs(self):
        invalid_tables = (
            None,
            [],
            {},
            {"a": 0},
            {"a": -1},
            {"a": True},
            {"a": "1"},
            {"a": float("inf")},
            {"a": float("-inf")},
            {"a": float("nan")},
        )

        for weights in invalid_tables:
            with self.subTest(weights=weights):
                with self.assertRaises(ValueError):
                    normalize_relative_weights(weights)

class CompatibilityLookupTests(unittest.TestCase):
    def test_returns_each_frozen_compatible_tuple_directly(self):
        expected = {
            "single_constraint": ("1",),
            "same_field_logic": ("1", "2", "3"),
            "cross_field_composition": ("2", "3", "4", "5_plus"),
            "normalization": ("1", "2", "3", "4", "5_plus"),
            "reference_only": (0,),
            "reference_composition": ("1", "2", "3", "4", "5_plus"),
        }

        for family, buckets in expected.items():
            with self.subTest(family=family):
                result = compatible_complexity_buckets(family)
                self.assertEqual(result, buckets)
                self.assertIs(result, FAMILY_COMPLEXITY_COMPATIBILITY[family])

        self.assertIsInstance(
            compatible_complexity_buckets("reference_only")[0],
            int,
        )
        self.assertIn(
            "5_plus",
            compatible_complexity_buckets("normalization"),
        )
        self.assertNotIn(
            5,
            compatible_complexity_buckets("normalization"),
        )

    def test_rejects_unknown_and_non_string_families_as_value_errors(self):
        invalid_families = (
            "unknown_family",
            " reference_only",
            None,
            [],
            {},
        )

        for family in invalid_families:
            with self.subTest(family=family):
                with self.assertRaises(ValueError):
                    compatible_complexity_buckets(family)

class FamilyProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def assert_probability_maps_close(self, left, right):
        self.assertEqual(list(left), list(right))
        for key in left:
            self.assertTrue(math.isclose(left[key], right[key]))

    def test_uses_fixture_family_weights_in_canonical_order(self):
        probabilities = family_probabilities(self.config)

        self.assertEqual(list(probabilities), list(SEMANTIC_FAMILY_ORDER))
        self.assert_probability_maps_close(
            probabilities,
            {
                "single_constraint": 0.25,
                "same_field_logic": 0.20,
                "cross_field_composition": 0.20,
                "normalization": 0.15,
                "reference_only": 0.10,
                "reference_composition": 0.10,
            },
        )
        self.assertTrue(math.isclose(sum(probabilities.values()), 1.0))

    def test_family_scale_and_count_table_do_not_change_probabilities(self):
        baseline = family_probabilities(self.config)
        scaled_families = replace(
            self.config,
            family_weights=WeightTableSpec(
                weights={
                    key: value * 10
                    for key, value in self.config.family_weights.weights.items()
                }
            ),
        )
        changed_counts = replace(
            self.config,
            constraint_count_weights=WeightTableSpec(
                weights={
                    "1": 1,
                    "2": 2,
                    "3": 3,
                    "4": 4,
                    "5_plus": 5,
                }
            ),
        )

        self.assert_probability_maps_close(
            family_probabilities(scaled_families),
            baseline,
        )
        self.assert_probability_maps_close(
            family_probabilities(changed_counts),
            baseline,
        )

    def test_rejects_invalid_sampler_config_before_probability_work(self):
        with self.assertRaises(ValueError):
            family_probabilities(replace(self.config, seed=True))

class ConditionalComplexityProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def assert_probability_map(self, actual, expected):
        self.assertEqual(list(actual), list(expected))
        for key in actual:
            self.assertTrue(
                math.isclose(actual[key], expected[key]),
                msg=f"probability differs at {key}: {actual[key]} != {expected[key]}",
            )
        self.assertTrue(math.isclose(sum(actual.values()), 1.0))

    def test_computes_each_family_distribution_inside_compatible_space(self):
        expected = {
            "single_constraint": {"1": 1.0},
            "same_field_logic": {
                "1": 35 / 85,
                "2": 30 / 85,
                "3": 20 / 85,
            },
            "cross_field_composition": {
                "2": 30 / 65,
                "3": 20 / 65,
                "4": 10 / 65,
                "5_plus": 5 / 65,
            },
            "normalization": {
                "1": 0.35,
                "2": 0.30,
                "3": 0.20,
                "4": 0.10,
                "5_plus": 0.05,
            },
            "reference_only": {0: 1.0},
            "reference_composition": {
                "1": 0.35,
                "2": 0.30,
                "3": 0.20,
                "4": 0.10,
                "5_plus": 0.05,
            },
        }

        for family, probabilities in expected.items():
            with self.subTest(family=family):
                self.assert_probability_map(
                    conditional_complexity_probabilities(self.config, family),
                    probabilities,
                )

    def test_count_weight_scale_does_not_change_conditionals(self):
        scaled = replace(
            self.config,
            constraint_count_weights=WeightTableSpec(
                weights={
                    key: value * 100
                    for key, value in self.config.constraint_count_weights.weights.items()
                }
            ),
        )

        for family in FAMILY_COMPLEXITY_COMPATIBILITY:
            with self.subTest(family=family):
                baseline = conditional_complexity_probabilities(self.config, family)
                actual = conditional_complexity_probabilities(scaled, family)
                self.assert_probability_map(actual, baseline)

    def test_rejects_unknown_family_and_invalid_config(self):
        with self.assertRaises(ValueError):
            conditional_complexity_probabilities(self.config, "unknown_family")

        with self.assertRaises(ValueError):
            conditional_complexity_probabilities(
                replace(self.config, seed=True),
                "reference_only",
            )

class JointFamilyComplexityProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def test_contains_only_compatible_pairs_in_canonical_order(self):
        joint = joint_family_complexity_probabilities(self.config)
        expected_keys = [
            (family, bucket)
            for family in SEMANTIC_FAMILY_ORDER
            for bucket in FAMILY_COMPLEXITY_COMPATIBILITY[family]
        ]

        self.assertEqual(list(joint), expected_keys)
        self.assertTrue(math.isclose(sum(joint.values()), 1.0))
        self.assertNotIn(("single_constraint", "2"), joint)
        self.assertNotIn(("cross_field_composition", "1"), joint)
        self.assertIn(("reference_only", 0), joint)
        self.assertNotIn(("reference_only", "0"), joint)

    def test_each_joint_value_is_family_times_conditional_probability(self):
        joint = joint_family_complexity_probabilities(self.config)
        families = family_probabilities(self.config)

        for family in SEMANTIC_FAMILY_ORDER:
            conditional = conditional_complexity_probabilities(
                self.config,
                family,
            )
            for bucket in FAMILY_COMPLEXITY_COMPATIBILITY[family]:
                with self.subTest(family=family, bucket=bucket):
                    self.assertTrue(
                        math.isclose(
                            joint[(family, bucket)],
                            families[family] * conditional[bucket],
                        )
                    )

    def test_joint_family_marginal_equals_family_probability(self):
        joint = joint_family_complexity_probabilities(self.config)
        expected = family_probabilities(self.config)

        for family in SEMANTIC_FAMILY_ORDER:
            actual = sum(
                probability
                for (candidate_family, _), probability in joint.items()
                if candidate_family == family
            )
            with self.subTest(family=family):
                self.assertTrue(math.isclose(actual, expected[family]))

class ComplexityMarginalProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def test_aggregates_joint_distribution_in_canonical_bucket_order(self):
        marginal = complexity_marginal_probabilities(self.config)
        joint = joint_family_complexity_probabilities(self.config)
        expected_order = [0, "1", "2", "3", "4", "5_plus"]

        self.assertEqual(list(marginal), expected_order)
        self.assertTrue(math.isclose(sum(marginal.values()), 1.0))

        for bucket in expected_order:
            expected = sum(
                probability
                for (_, candidate_bucket), probability in joint.items()
                if candidate_bucket == bucket
            )
            with self.subTest(bucket=bucket):
                self.assertTrue(math.isclose(marginal[bucket], expected))

    def test_zero_bucket_is_exactly_reference_only_family_probability(self):
        marginal = complexity_marginal_probabilities(self.config)
        families = family_probabilities(self.config)

        self.assertTrue(
            math.isclose(marginal[0], families["reference_only"])
        )
        self.assertNotIn("0", marginal)
        self.assertIn("5_plus", marginal)
        self.assertNotIn(5, marginal)

class WeightedChoiceTests(unittest.TestCase):
    def test_uses_half_open_intervals_and_exactly_one_draw(self):
        choices = ("a", "b", "c")
        probabilities = {"a": 0.25, "b": 0.25, "c": 0.50}
        cases = (
            (0.0, "a"),
            (0.249999999, "a"),
            (0.25, "b"),
            (0.499999999, "b"),
            (0.50, "c"),
            (0.999999999, "c"),
        )

        for draw, expected in cases:
            with self.subTest(draw=draw):
                rng = CountingRandom([draw])
                self.assertEqual(
                    _weighted_choice(choices, probabilities, rng),
                    expected,
                )
                self.assertEqual(rng.call_count, 1)

    def test_traverses_choices_order_instead_of_mapping_order(self):
        probabilities = {"b": 0.80, "a": 0.20}
        rng = CountingRandom([0.10])

        self.assertEqual(
            _weighted_choice(("a", "b"), probabilities, rng),
            "a",
        )
        self.assertEqual(rng.call_count, 1)

    def test_floating_point_tail_falls_to_final_choice(self):
        probabilities = {
            "a": 0.20,
            "b": 0.30,
            "c": 0.4999999999999998,
        }
        rng = CountingRandom([0.9999999999999999])

        self.assertEqual(
            _weighted_choice(("a", "b", "c"), probabilities, rng),
            "c",
        )
        self.assertEqual(rng.call_count, 1)

    def test_empty_choices_fail_before_consuming_rng(self):
        rng = CountingRandom([0.0])

        with self.assertRaises(ValueError):
            _weighted_choice((), {}, rng)

        self.assertEqual(rng.call_count, 0)

class FamilyComplexityPlannerTests(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)

    def assert_probability_maps_close(self, left, right):
        self.assertEqual(set(left), set(right))
        for key in left:
            self.assertTrue(
                math.isclose(left[key], right[key], rel_tol=1e-12, abs_tol=1e-12),
                msg=f"probability differs at {key}: {left[key]} != {right[key]}",
            )

    def scaled_config(self, family_scale=1.0, count_scale=1.0):
        return replace(
            self.config,
            family_weights=WeightTableSpec(
                weights={
                    key: value * family_scale
                    for key, value in self.config.family_weights.weights.items()
                }
            ),
            constraint_count_weights=WeightTableSpec(
                weights={
                    key: value * count_scale
                    for key, value in self.config.constraint_count_weights.weights.items()
                }
            ),
        )

    def test_compatibility_matrix_exactly_matches_frozen_contract(self):
        expected = {
            "single_constraint": ("1",),
            "same_field_logic": ("1", "2", "3"),
            "cross_field_composition": ("2", "3", "4", "5_plus"),
            "normalization": ("1", "2", "3", "4", "5_plus"),
            "reference_only": (0,),
            "reference_composition": ("1", "2", "3", "4", "5_plus"),
        }
        self.assertEqual(dict(FAMILY_COMPLEXITY_COMPATIBILITY), expected)
        for family, buckets in expected.items():
            self.assertEqual(compatible_complexity_buckets(family), buckets)

    def test_illegal_pairs_are_absent_from_conditional_space(self):
        all_buckets = {0, "1", "2", "3", "4", "5_plus"}
        for family, compatible in FAMILY_COMPLEXITY_COMPATIBILITY.items():
            probabilities = conditional_complexity_probabilities(self.config, family)
            self.assertEqual(set(probabilities), set(compatible))
            self.assertTrue((all_buckets - set(compatible)).isdisjoint(probabilities))

    def test_family_specific_bucket_boundaries_and_five_plus_identity(self):
        self.assertEqual(
            set(conditional_complexity_probabilities(self.config, "single_constraint")),
            {"1"},
        )
        self.assertEqual(
            conditional_complexity_probabilities(self.config, "reference_only"),
            {0: 1.0},
        )
        self.assertNotIn(
            "1",
            conditional_complexity_probabilities(
                self.config, "cross_field_composition"
            ),
        )
        same_field = conditional_complexity_probabilities(
            self.config, "same_field_logic"
        )
        self.assertNotIn("4", same_field)
        self.assertNotIn("5_plus", same_field)
        for family in ("normalization", "reference_composition"):
            self.assertIn(
                "5_plus", conditional_complexity_probabilities(self.config, family)
            )
        self.assertNotIn(
            5,
            conditional_complexity_probabilities(self.config, "normalization"),
        )

    def test_relative_weight_normalization_and_family_probabilities(self):
        probabilities = normalize_relative_weights({"a": 1, "b": 2, "c": 3})
        self.assert_probability_maps_close(
            probabilities,
            {"a": 1 / 6, "b": 2 / 6, "c": 3 / 6},
        )
        family = family_probabilities(self.config)
        self.assertTrue(math.isclose(sum(family.values()), 1.0))
        self.assertTrue(math.isclose(family["reference_only"], 0.1))

    def test_invalid_direct_weight_inputs_fail_explicitly(self):
        invalid_tables = (
            {},
            {"a": 0.0},
            {"a": -1.0},
            {"a": True},
            {"a": float("inf")},
            {"a": float("nan")},
        )
        for weights in invalid_tables:
            with self.subTest(weights=weights):
                with self.assertRaises(ValueError):
                    normalize_relative_weights(weights)

        with self.assertRaises(ValueError):
            compatible_complexity_buckets("unknown_family")

    def test_each_conditional_and_full_joint_distribution_sum_to_one(self):
        for family in FAMILY_COMPLEXITY_COMPATIBILITY:
            conditional = conditional_complexity_probabilities(self.config, family)
            self.assertTrue(math.isclose(sum(conditional.values()), 1.0))

        joint = joint_family_complexity_probabilities(self.config)
        self.assertTrue(math.isclose(sum(joint.values()), 1.0))
        self.assertEqual(
            set(joint),
            {
                (family, bucket)
                for family, buckets in FAMILY_COMPLEXITY_COMPATIBILITY.items()
                for bucket in buckets
            },
        )

    def test_joint_family_marginal_equals_normalized_family_probability(self):
        joint = joint_family_complexity_probabilities(self.config)
        expected = family_probabilities(self.config)
        actual = {
            family: sum(
                probability
                for (candidate_family, _), probability in joint.items()
                if candidate_family == family
            )
            for family in expected
        }
        self.assert_probability_maps_close(actual, expected)

    def test_complexity_marginal_includes_reference_zero_and_sums_to_one(self):
        marginal = complexity_marginal_probabilities(self.config)
        self.assertEqual(set(marginal), {0, "1", "2", "3", "4", "5_plus"})
        self.assertTrue(math.isclose(sum(marginal.values()), 1.0))
        self.assertTrue(
            math.isclose(
                marginal[0],
                family_probabilities(self.config)["reference_only"],
            )
        )

    def test_family_and_count_tables_have_independent_scale_invariance(self):
        baseline = joint_family_complexity_probabilities(self.config)
        cases = (
            self.scaled_config(family_scale=10.0),
            self.scaled_config(count_scale=0.01),
            self.scaled_config(family_scale=7.0, count_scale=0.03),
        )
        for scaled in cases:
            with self.subTest(config=scaled):
                self.assert_probability_maps_close(
                    joint_family_complexity_probabilities(scaled), baseline
                )

    def test_percentage_and_fraction_count_representations_are_equivalent(self):
        percentage = self.config.constraint_count_weights.weights
        fractional = replace(
            self.config,
            constraint_count_weights=WeightTableSpec(
                weights={key: value / 100 for key, value in percentage.items()}
            ),
        )
        self.assert_probability_maps_close(
            joint_family_complexity_probabilities(self.config),
            joint_family_complexity_probabilities(fractional),
        )

    def test_same_seed_reproduces_the_same_plan_sequence(self):
        left_rng = Random(self.config.seed)
        right_rng = Random(self.config.seed)
        left = [
            sample_family_complexity_plan(self.config, left_rng) for _ in range(100)
        ]
        right = [
            sample_family_complexity_plan(self.config, right_rng) for _ in range(100)
        ]
        self.assertEqual(left, right)
        self.assertTrue(all(isinstance(plan, FamilyComplexityPlan) for plan in left))

    def test_reference_only_consumes_no_complexity_draw(self):
        # With fixture family probabilities, 0.85 selects reference_only.
        rng = CountingRandom([0.85])
        plan = sample_family_complexity_plan(self.config, rng)
        self.assertEqual(plan.semantic_family, "reference_only")
        self.assertEqual(plan.complexity_bucket, 0)
        self.assertEqual(rng.call_count, 1)

    def test_hard_family_consumes_exactly_two_draws_without_rejection(self):
        # 0.50 selects cross_field_composition; 0.0 selects its first compatible
        # bucket directly. An invalid global bucket is never drawn and retried.
        rng = CountingRandom([0.50, 0.0])
        plan = sample_family_complexity_plan(self.config, rng)
        self.assertEqual(plan.semantic_family, "cross_field_composition")
        self.assertEqual(plan.complexity_bucket, "2")
        self.assertEqual(rng.call_count, 2)

    def test_plan_contract_has_no_downstream_payload(self):
        self.assertEqual(
            [field.name for field in fields(FamilyComplexityPlan)],
            ["semantic_family", "complexity_bucket"],
        )
        plan = FamilyComplexityPlan("normalization", "5_plus")
        self.assertFalse(hasattr(plan, "semantic_spec"))
        self.assertFalse(hasattr(plan, "dataset_record"))
        self.assertFalse(hasattr(plan, "user_text"))
        self.assertFalse(hasattr(plan, "constraint_count"))

    def test_requires_explicit_rng_with_callable_random(self):
        invalid_rngs = (
            None,
            object(),
            type("NonCallableRandom", (), {"random": 0.5})(),
        )

        for rng in invalid_rngs:
            with self.subTest(rng=rng):
                with self.assertRaises(ValueError):
                    sample_family_complexity_plan(self.config, rng)

if __name__ == "__main__":
    unittest.main()
