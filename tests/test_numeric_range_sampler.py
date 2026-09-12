"""Acceptance tests for D2. Direct Numeric Range Value Sampler v0.1."""

from dataclasses import fields, replace
import json
import math
from pathlib import Path
from random import Random
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import load_domain_rules
from anime_pref.schemas.numeric_range import DirectNumericRangePlan
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.numeric_range import (
    _choose_probability_candidate,
    base_numeric_value_probabilities,
    conditioned_upper_probabilities,
    numeric_constraint_contribution,
    numeric_pool_probabilities,
    numeric_value_pools,
    sample_direct_numeric_range,
    validate_direct_numeric_range_plan,
    validate_numeric_sampling_binding,
)

SAMPLER_CONFIG_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "semantic_sampler.synthetic.v0.1.json"
)
RULES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "domain_rules.synthetic.v0.1.json"


class CountingRandom:
    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


class NumericRangeTestCase(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)
        self.rules = load_domain_rules(RULES_PATH)

    def assert_probability_maps_close(self, left, right):
        self.assertEqual(list(left), list(right))
        for key in left:
            self.assertTrue(
                math.isclose(left[key], right[key], rel_tol=1e-12, abs_tol=1e-12),
                msg=f"probability differs at {key!r}: {left[key]} != {right[key]}",
            )

    def config_with_numeric_pools(
        self,
        field,
        *,
        common,
        catalog_region,
        long_tail,
        pool_weights=None,
    ):
        attribute = f"{field}_sampling"
        original = getattr(self.config, attribute)
        policy = replace(
            original,
            common_values=tuple(common),
            catalog_region_values=tuple(catalog_region),
            long_tail_values=tuple(long_tail),
            pool_weights=(
                original.pool_weights if pool_weights is None else pool_weights
            ),
        )
        return replace(self.config, **{attribute: policy})

    def rules_with_numeric_bounds(self, field, minimum, maximum):
        document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        document["numeric_rules"][field] = {
            "minimum": minimum,
            "maximum": maximum,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "rules.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_domain_rules(path)


class NumericProbabilityContractTests(NumericRangeTestCase):
    def test_pool_probabilities_follow_relative_weights(self):
        self.assert_probability_maps_close(
            numeric_pool_probabilities("year", self.config, self.rules),
            {"common": 0.6, "catalog_region": 0.3, "long_tail": 0.1},
        )

    def test_values_are_uniform_inside_each_original_pool(self):
        base = base_numeric_value_probabilities("year", self.config, self.rules)
        pools = numeric_value_pools("year", self.config, self.rules)
        for values in pools.values():
            probabilities = [base[value] for value in values]
            self.assertTrue(
                all(math.isclose(value, probabilities[0]) for value in probabilities)
            )

    def test_base_marginal_is_pool_probability_divided_by_original_size(self):
        base = base_numeric_value_probabilities("year", self.config, self.rules)
        self.assertTrue(math.isclose(base[2000], 0.6 / 3))
        self.assertTrue(math.isclose(base[1990], 0.3 / 4))
        self.assertTrue(math.isclose(base[1917], 0.1 / 3))
        self.assertTrue(math.isclose(sum(base.values()), 1.0))

    def test_different_pool_sizes_produce_different_value_marginals(self):
        config = self.config_with_numeric_pools(
            "year",
            common=(2000,),
            catalog_region=(1990, 2010),
            long_tail=(1917, 1983, 2037),
            pool_weights={"common": 1, "catalog_region": 1, "long_tail": 1},
        )
        base = base_numeric_value_probabilities("year", config, self.rules)
        self.assertTrue(math.isclose(base[2000], 1 / 3))
        self.assertTrue(math.isclose(base[1990], 1 / 6))
        self.assertTrue(math.isclose(base[1917], 1 / 9))

    def test_pool_weight_scale_preserves_base_and_conditioned_distributions(self):
        original = self.config.year_sampling
        scaled = replace(
            self.config,
            year_sampling=replace(
                original,
                pool_weights={
                    pool: weight * 37
                    for pool, weight in original.pool_weights.items()
                },
            ),
        )
        self.assert_probability_maps_close(
            base_numeric_value_probabilities("year", self.config, self.rules),
            base_numeric_value_probabilities("year", scaled, self.rules),
        )
        self.assert_probability_maps_close(
            conditioned_upper_probabilities(
                "year", 2020, self.config, self.rules
            ),
            conditioned_upper_probabilities("year", 2020, scaled, self.rules),
        )

    def test_global_candidates_are_ascending_and_only_from_configured_pools(self):
        base = base_numeric_value_probabilities("episodes", self.config, self.rules)
        pools = numeric_value_pools("episodes", self.config, self.rules)
        configured = {value for values in pools.values() for value in values}
        self.assertEqual(tuple(base), tuple(sorted(base)))
        self.assertEqual(set(base), configured)
        self.assertNotIn(2, base)


class ConditionedUpperTests(NumericRangeTestCase):
    def test_upper_universe_is_exactly_values_greater_than_or_equal_to_lower(self):
        upper = conditioned_upper_probabilities(
            "year", 2020, self.config, self.rules
        )
        self.assertEqual(tuple(upper), (2020, 2024, 2037))
        self.assertTrue(all(value >= 2020 for value in upper))
        self.assertIn(2020, upper)

    def test_upper_probabilities_are_global_conditioning_of_base_marginals(self):
        base = base_numeric_value_probabilities("year", self.config, self.rules)
        upper = conditioned_upper_probabilities(
            "year", 2020, self.config, self.rules
        )
        denominator = sum(
            probability for value, probability in base.items() if value >= 2020
        )
        expected = {
            value: base[value] / denominator
            for value in base
            if value >= 2020
        }
        self.assert_probability_maps_close(upper, expected)

    def test_partially_surviving_pool_keeps_original_pool_size_denominator(self):
        upper = conditioned_upper_probabilities(
            "year", 2020, self.config, self.rules
        )
        unnormalized = {
            2020: 0.6 / 3,
            2024: 0.3 / 4,
            2037: 0.1 / 3,
        }
        total = sum(unnormalized.values())
        expected = {value: weight / total for value, weight in unnormalized.items()}
        self.assert_probability_maps_close(upper, expected)
        # Hierarchical pool re-selection would yield 0.6/0.3/0.1 here; D2 must not.
        self.assertFalse(math.isclose(upper[2024], 0.3))

    def test_lower_must_be_a_configured_candidate_and_bool_is_invalid(self):
        for lower in (2011, True):
            with self.subTest(lower=lower):
                with self.assertRaises(ValueError):
                    conditioned_upper_probabilities(
                        "year", lower, self.config, self.rules
                    )


class NumericSamplingTests(NumericRangeTestCase):
    def test_single_bound_samples_pool_then_uniform_value(self):
        # Pool draw 0.65 selects catalog_region (interval 0.6..0.9).
        # Value draw 0.60 selects its third of four ascending values: 2015.
        rng = CountingRandom([0.65, 0.60])
        plan = sample_direct_numeric_range(
            "year", "min_only", self.config, self.rules, rng
        )
        self.assertEqual(
            plan,
            DirectNumericRangePlan("year", "min_only", 2015, None),
        )
        self.assertEqual(rng.call_count, 2)

    def test_max_only_uses_canonical_representation(self):
        plan = sample_direct_numeric_range(
            "episodes",
            "max_only",
            self.config,
            self.rules,
            CountingRandom([0.0, 0.99]),
        )
        self.assertEqual(plan, DirectNumericRangePlan("episodes", "max_only", None, 24))

    def test_singleton_value_stage_consumes_no_draw(self):
        config = self.config_with_numeric_pools(
            "year",
            common=(2000,),
            catalog_region=(2010,),
            long_tail=(2020,),
        )
        rng = CountingRandom([0.0])
        plan = sample_direct_numeric_range(
            "year", "min_only", config, self.rules, rng
        )
        self.assertEqual(plan.minimum, 2000)
        self.assertEqual(rng.call_count, 1)

    def test_generic_singleton_candidate_helper_consumes_zero_draws(self):
        rng = CountingRandom([])
        self.assertEqual(_choose_probability_candidate({"only": 1.0}, rng), "only")
        self.assertEqual(rng.call_count, 0)

    def test_bounded_lower_uses_same_base_hierarchy_as_single_bound(self):
        single_rng = CountingRandom([0.65, 0.60])
        bounded_rng = CountingRandom([0.65, 0.60, 0.0])
        single = sample_direct_numeric_range(
            "year", "min_only", self.config, self.rules, single_rng
        )
        bounded = sample_direct_numeric_range(
            "year", "bounded_range", self.config, self.rules, bounded_rng
        )
        self.assertEqual(single.minimum, bounded.minimum)
        self.assertEqual(bounded.minimum, 2015)

    def test_bounded_range_uses_direct_global_upper_draw(self):
        # Lower: common pool then 2020. Upper survivors are 2020/2024/2037;
        # exactly one additional draw is consumed, with no second pool draw.
        rng = CountingRandom([0.0, 0.99, 0.70])
        plan = sample_direct_numeric_range(
            "year", "bounded_range", self.config, self.rules, rng
        )
        self.assertEqual(plan.minimum, 2020)
        self.assertGreaterEqual(plan.maximum, plan.minimum)
        self.assertEqual(rng.call_count, 3)

    def test_maximum_lower_makes_equal_upper_deterministic(self):
        # long_tail pool + last value => lower 2037, the global maximum.
        # Upper can only be 2037, so no third RNG draw occurs.
        rng = CountingRandom([0.99, 0.99])
        plan = sample_direct_numeric_range(
            "year", "bounded_range", self.config, self.rules, rng
        )
        self.assertEqual(
            plan,
            DirectNumericRangePlan("year", "bounded_range", 2037, 2037),
        )
        self.assertEqual(rng.call_count, 2)

    def test_every_sampled_endpoint_comes_from_configured_pools(self):
        candidates = set(
            base_numeric_value_probabilities("year", self.config, self.rules)
        )
        for seed in range(100):
            plan = sample_direct_numeric_range(
                "year",
                "bounded_range",
                self.config,
                self.rules,
                Random(seed),
            )
            self.assertIn(plan.minimum, candidates)
            self.assertIn(plan.maximum, candidates)
            self.assertLessEqual(plan.minimum, plan.maximum)

    def test_same_context_and_rng_state_reproduce_output(self):
        left = sample_direct_numeric_range(
            "episodes", "bounded_range", self.config, self.rules, Random(8675309)
        )
        right = sample_direct_numeric_range(
            "episodes", "bounded_range", self.config, self.rules, Random(8675309)
        )
        self.assertEqual(left, right)

    def test_pattern_weights_are_not_consumed_by_d2(self):
        changed = replace(
            self.config,
            year_sampling=replace(
                self.config.year_sampling,
                pattern_weights={
                    "min_only": 1000,
                    "max_only": 1,
                    "bounded_range": 1,
                },
            ),
        )
        baseline = sample_direct_numeric_range(
            "year", "bounded_range", self.config, self.rules, Random(44)
        )
        actual = sample_direct_numeric_range(
            "year", "bounded_range", changed, self.rules, Random(44)
        )
        self.assertEqual(actual, baseline)

    def test_invalid_config_domain_binding_fails_before_rng(self):
        invalid = self.config_with_numeric_pools(
            "year",
            common=(1899, 2000),
            catalog_region=(2005,),
            long_tail=(2037,),
        )
        rng = CountingRandom([])
        with self.assertRaises(ValueError):
            sample_direct_numeric_range(
                "year", "min_only", invalid, self.rules, rng
            )
        self.assertEqual(rng.call_count, 0)

    def test_invalid_field_pattern_and_rng_fail_explicitly(self):
        cases = (
            ("format", "min_only", Random(1)),
            ("year", "exact", Random(1)),
            ("year", "min_only", object()),
        )
        for field, pattern, rng in cases:
            with self.subTest(field=field, pattern=pattern):
                with self.assertRaises(ValueError):
                    sample_direct_numeric_range(
                        field, pattern, self.config, self.rules, rng
                    )


class NumericContributionAndValidationTests(NumericRangeTestCase):
    def test_numeric_constraint_contribution_is_one_one_two(self):
        self.assertEqual(numeric_constraint_contribution("min_only"), 1)
        self.assertEqual(numeric_constraint_contribution("max_only"), 1)
        self.assertEqual(numeric_constraint_contribution("bounded_range"), 2)
        with self.assertRaises(ValueError):
            numeric_constraint_contribution("exact")

    def test_generic_validator_accepts_all_patterns_and_equal_bounds(self):
        valid = (
            DirectNumericRangePlan("year", "min_only", 1950, None),
            DirectNumericRangePlan("episodes", "max_only", None, 24),
            DirectNumericRangePlan("year", "bounded_range", 2020, 2020),
        )
        for plan in valid:
            with self.subTest(plan=plan):
                self.assertIsNone(validate_direct_numeric_range_plan(plan, self.rules))

        # 1950 is valid under DomainRules but absent from the configured pools.
        self.assertNotIn(
            1950,
            base_numeric_value_probabilities("year", self.config, self.rules),
        )

    def test_generic_validator_rejects_bad_shape_types_patterns_and_bounds(self):
        invalid = (
            object(),
            DirectNumericRangePlan("format", "min_only", 2020, None),
            DirectNumericRangePlan("year", "exact", 2020, 2020),
            DirectNumericRangePlan("year", "min_only", None, None),
            DirectNumericRangePlan("year", "min_only", 2020, 2021),
            DirectNumericRangePlan("year", "max_only", 2020, None),
            DirectNumericRangePlan("year", "bounded_range", 2020, None),
            DirectNumericRangePlan("year", "bounded_range", 2021, 2020),
            DirectNumericRangePlan("year", "min_only", True, None),
            DirectNumericRangePlan("year", "min_only", 1899, None),
            DirectNumericRangePlan("episodes", "max_only", None, 0),
        )
        for plan in invalid:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    validate_direct_numeric_range_plan(plan, self.rules)

    def test_output_contract_has_no_structural_or_downstream_fields(self):
        self.assertEqual(
            [field.name for field in fields(DirectNumericRangePlan)],
            ["field", "range_pattern", "minimum", "maximum"],
        )
        plan = DirectNumericRangePlan("year", "min_only", 2020, None)
        for forbidden in (
            "semantic_family",
            "complexity",
            "categorical_values",
            "tag_group",
            "reference",
            "semantic_spec",
            "dataset_record",
            "user_text",
        ):
            self.assertFalse(hasattr(plan, forbidden))


if __name__ == "__main__":
    unittest.main()
