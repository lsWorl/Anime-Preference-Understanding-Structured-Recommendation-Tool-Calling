"""Acceptance tests for D1. Direct Categorical Value Sampler v0.1."""

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
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.schemas.categorical_value import DirectCategoricalValuePlan
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.sampling.categorical_value import (
    effective_value_weights,
    initial_value_probabilities,
    sample_direct_categorical_values,
    validate_direct_categorical_sampling_binding,
    validate_direct_categorical_value_context,
    validate_direct_categorical_value_plan,
)
from anime_pref.sampling.config import load_sampler_config

SAMPLER_CONFIG_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "semantic_sampler.synthetic.v0.1.json"
)
RULES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "domain_rules.synthetic.v0.1.json"
SUBSET_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "executable_tags.synthetic.v0.1.json"
)


class CountingRandom:
    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


class CategoricalValueTestCase(unittest.TestCase):
    def setUp(self):
        self.config = load_sampler_config(SAMPLER_CONFIG_PATH)
        self.rules = load_domain_rules(RULES_PATH)
        self.subset = load_executable_tag_subset(SUBSET_PATH)

    def rules_with(self, *, genres=None, tags=None):
        """Load a newly hashed synthetic DomainRules variant for one test."""
        document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        if genres is not None:
            document["taxonomy"]["genres"] = list(genres)
        if tags is not None:
            document["taxonomy"]["tags"] = list(tags)

        temporary = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
            delete=False,
        )
        try:
            json.dump(document, temporary)
            temporary.close()
            return load_domain_rules(Path(temporary.name))
        finally:
            Path(temporary.name).unlink(missing_ok=True)

    def custom_genre_context(self, weights):
        rules = self.rules_with(genres=tuple(weights))
        policy = replace(
            self.config.genre_sampling,
            maximum_value_share=1.0,
            default_weight=1.0,
            priority_weights=dict(weights),
        )
        return replace(self.config, genre_sampling=policy), rules


class EligibleUniverseAndWeightsTests(CategoricalValueTestCase):
    def test_active_rules_genres_are_the_only_genre_universe(self):
        weights = effective_value_weights(
            "genres", self.config, self.rules, self.subset
        )
        self.assertEqual(tuple(weights), tuple(sorted(self.rules.genres)))
        self.assertEqual(set(weights), set(self.rules.genres))

    def test_active_rules_tags_exclude_inactive_approved_tag(self):
        weights = effective_value_weights("tags", self.config, self.rules, self.subset)
        self.assertEqual(set(weights), set(self.rules.tags))
        self.assertNotIn("Ensemble Cast", weights)
        self.assertIn(
            "Ensemble Cast",
            {tag.tag_name for tag in self.subset.tags},
        )

    def test_unreviewed_tag_cannot_enter_candidate_universe(self):
        invalid_rules = self.rules_with(tags=(*self.rules.tags, "Unreviewed Tag"))
        with self.assertRaises(ValueError):
            effective_value_weights(
                "tags", self.config, invalid_rules, self.subset
            )

    def test_untiered_active_tag_uses_default_without_standard_label(self):
        active = (*self.rules.tags, "Ensemble Cast")
        rules = self.rules_with(tags=active)
        weights = effective_value_weights("tags", self.config, rules, self.subset)
        self.assertEqual(
            weights["Ensemble Cast"],
            self.config.tag_sampling.default_weight,
        )
        self.assertNotIn("Ensemble Cast", self.config.tag_sampling.value_tiers)

    def test_tag_priority_overrides_tier_and_default_without_multiplication(self):
        rules = self.rules_with(tags=(*self.rules.tags, "Ensemble Cast"))
        policy = replace(
            self.config.tag_sampling,
            priority_weights={"Female Harem": 7.0, "Ensemble Cast": 4.0},
        )
        config = replace(self.config, tag_sampling=policy)
        weights = effective_value_weights("tags", config, rules, self.subset)

        self.assertEqual(weights["Female Harem"], 7.0)
        self.assertNotEqual(
            weights["Female Harem"],
            7.0 * policy.tier_weights["core"],
        )
        self.assertEqual(weights["Male Harem"], policy.tier_weights["core"])
        self.assertEqual(weights["Ensemble Cast"], 4.0)

    def test_genre_priority_overrides_default(self):
        weights = effective_value_weights(
            "genres", self.config, self.rules, self.subset
        )
        self.assertEqual(weights["Mystery"], 1.1)
        self.assertEqual(weights["Sci-Fi"], 1.05)
        self.assertEqual(weights["Action"], 1.0)

    def test_every_effective_weight_is_finite_and_positive(self):
        for field in ("genres", "tags"):
            with self.subTest(field=field):
                weights = effective_value_weights(
                    field, self.config, self.rules, self.subset
                )
                self.assertTrue(
                    all(
                        isinstance(weight, (int, float))
                        and not isinstance(weight, bool)
                        and math.isfinite(weight)
                        and weight > 0
                        for weight in weights.values()
                    )
                )


class ProbabilityAndBindingTests(CategoricalValueTestCase):
    def assert_probability_maps_close(self, left, right):
        self.assertEqual(list(left), list(right))
        for value in left:
            self.assertTrue(
                math.isclose(left[value], right[value], rel_tol=1e-12),
                msg=f"probability differs for {value!r}",
            )

    def test_genre_weight_distribution_scale_is_invariant(self):
        baseline = initial_value_probabilities(
            "genres", self.config, self.rules, self.subset
        )
        original = self.config.genre_sampling
        scaled_policy = replace(
            original,
            default_weight=original.default_weight * 11,
            priority_weights={
                key: value * 11 for key, value in original.priority_weights.items()
            },
        )
        scaled = replace(self.config, genre_sampling=scaled_policy)
        self.assert_probability_maps_close(
            baseline,
            initial_value_probabilities("genres", scaled, self.rules, self.subset),
        )

    def test_tag_priority_tier_and_default_scale_is_invariant(self):
        rules = self.rules_with(tags=(*self.rules.tags, "Ensemble Cast"))
        original = replace(
            self.config.tag_sampling,
            priority_weights={"Female Harem": 7.0},
        )
        baseline_config = replace(self.config, tag_sampling=original)
        scaled = replace(
            baseline_config,
            tag_sampling=replace(
                original,
                default_weight=original.default_weight * 13,
                priority_weights={
                    key: value * 13
                    for key, value in original.priority_weights.items()
                },
                tier_weights={
                    key: value * 13 for key, value in original.tier_weights.items()
                },
            ),
        )
        self.assert_probability_maps_close(
            initial_value_probabilities(
                "tags", baseline_config, rules, self.subset
            ),
            initial_value_probabilities("tags", scaled, rules, self.subset),
        )

    def test_maximum_value_share_accepts_current_base_distributions(self):
        for field in ("genres", "tags"):
            with self.subTest(field=field):
                self.assertIsNone(
                    validate_direct_categorical_sampling_binding(
                        field, self.config, self.rules, self.subset
                    )
                )

    def test_maximum_value_share_rejects_dominant_genre_and_tag(self):
        genre_config = replace(
            self.config,
            genre_sampling=replace(
                self.config.genre_sampling,
                maximum_value_share=0.05,
            ),
        )
        tag_config = replace(
            self.config,
            tag_sampling=replace(
                self.config.tag_sampling,
                maximum_value_share=0.30,
            ),
        )
        for field, config in (("genres", genre_config), ("tags", tag_config)):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "maximum_value_share"):
                    validate_direct_categorical_sampling_binding(
                        field, config, self.rules, self.subset
                    )

    def test_minimum_coverage_does_not_change_atomic_probabilities(self):
        changed = replace(
            self.config,
            genre_sampling=replace(
                self.config.genre_sampling,
                minimum_coverage_per_value=999,
            ),
        )
        self.assert_probability_maps_close(
            initial_value_probabilities(
                "genres", self.config, self.rules, self.subset
            ),
            initial_value_probabilities("genres", changed, self.rules, self.subset),
        )


class SamplingWithoutReplacementTests(CategoricalValueTestCase):
    def test_cardinality_one_selects_exactly_one_active_value(self):
        rng = CountingRandom([0.0])
        plan = sample_direct_categorical_values(
            "genres",
            OperatorCardinalityPlan("all_of", 1),
            self.config,
            self.rules,
            self.subset,
            rng,
        )
        self.assertEqual(plan, DirectCategoricalValuePlan("genres", ("Action",)))
        self.assertEqual(rng.call_count, 1)

    def test_cardinality_two_and_three_are_distinct_and_active(self):
        cases = (
            OperatorCardinalityPlan("all_of", 2),
            OperatorCardinalityPlan("any_of", 3),
        )
        for operator_plan in cases:
            with self.subTest(operator_plan=operator_plan):
                result = sample_direct_categorical_values(
                    "tags",
                    operator_plan,
                    self.config,
                    self.rules,
                    self.subset,
                    Random(101),
                )
                self.assertEqual(len(result.values), operator_plan.cardinality)
                self.assertEqual(len(result.values), len(set(result.values)))
                self.assertTrue(set(result.values) <= self.rules.tags)

    def test_removal_is_followed_by_weight_renormalization(self):
        config, rules = self.custom_genre_context({"A": 1, "B": 2, "C": 7})
        # First draw 0.75 selects C under 1/2/7. After C is removed, A/B are
        # renormalized to 1/3 and 2/3; second draw 0.20 therefore selects A.
        rng = CountingRandom([0.75, 0.20])
        result = sample_direct_categorical_values(
            "genres",
            OperatorCardinalityPlan("all_of", 2),
            config,
            rules,
            self.subset,
            rng,
        )
        self.assertEqual(result.values, ("A", "C"))
        self.assertEqual(rng.call_count, 2)

    def test_selecting_full_universe_uses_no_draw_for_last_value(self):
        config, rules = self.custom_genre_context({"A": 1, "B": 1, "C": 1})
        rng = CountingRandom([0.0, 0.0])
        result = sample_direct_categorical_values(
            "genres",
            OperatorCardinalityPlan("all_of", 3),
            config,
            rules,
            self.subset,
            rng,
        )
        self.assertEqual(result.values, ("A", "B", "C"))
        self.assertEqual(rng.call_count, 2)

    def test_capacity_failure_occurs_before_rng_consumption(self):
        config, rules = self.custom_genre_context({"A": 1, "B": 1})
        rng = CountingRandom([])
        with self.assertRaisesRegex(ValueError, "exceeds"):
            sample_direct_categorical_values(
                "genres",
                OperatorCardinalityPlan("any_of", 3),
                config,
                rules,
                self.subset,
                rng,
            )
        self.assertEqual(rng.call_count, 0)

    def test_final_values_use_canonical_set_order_not_draw_order(self):
        config, rules = self.custom_genre_context({"A": 1, "B": 2, "C": 7})
        result = sample_direct_categorical_values(
            "genres",
            OperatorCardinalityPlan("all_of", 2),
            config,
            rules,
            self.subset,
            CountingRandom([0.75, 0.20]),
        )
        self.assertEqual(result.values, tuple(sorted(result.values)))
        self.assertEqual(result.values, ("A", "C"))

    def test_same_rng_state_reproduces_same_output(self):
        left = sample_direct_categorical_values(
            "genres",
            OperatorCardinalityPlan("all_of", 3),
            self.config,
            self.rules,
            self.subset,
            Random(31415),
        )
        right = sample_direct_categorical_values(
            "genres",
            OperatorCardinalityPlan("all_of", 3),
            self.config,
            self.rules,
            self.subset,
            Random(31415),
        )
        self.assertEqual(left, right)

    def test_invalid_field_plan_or_rng_fails_explicitly(self):
        with self.assertRaises(ValueError):
            sample_direct_categorical_values(
                "formats",
                OperatorCardinalityPlan("all_of", 1),
                self.config,
                self.rules,
                self.subset,
                Random(1),
            )
        with self.assertRaises(ValueError):
            sample_direct_categorical_values(
                "genres",
                OperatorCardinalityPlan("any_of", 1),
                self.config,
                self.rules,
                self.subset,
                Random(1),
            )
        with self.assertRaises(ValueError):
            sample_direct_categorical_values(
                "genres",
                OperatorCardinalityPlan("all_of", 1),
                self.config,
                self.rules,
                self.subset,
                object(),
            )


class ValuePlanValidationTests(CategoricalValueTestCase):
    def test_public_validator_accepts_canonical_active_plan(self):
        plan = DirectCategoricalValuePlan("genres", ("Action", "Mystery"))
        self.assertIsNone(
            validate_direct_categorical_value_plan(plan, self.rules, self.subset)
        )

    def test_public_validator_rejects_shape_order_duplicate_and_inactive_values(self):
        invalid = (
            object(),
            DirectCategoricalValuePlan("formats", ("TV",)),
            DirectCategoricalValuePlan("genres", ()),
            DirectCategoricalValuePlan("genres", ["Action"]),
            DirectCategoricalValuePlan("genres", (" Action",)),
            DirectCategoricalValuePlan("genres", ("Action", "Action")),
            DirectCategoricalValuePlan("genres", ("Mystery", "Action")),
            DirectCategoricalValuePlan("genres", ("Not Active",)),
            DirectCategoricalValuePlan("tags", ("Ensemble Cast",)),
        )
        for plan in invalid:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    validate_direct_categorical_value_plan(
                        plan, self.rules, self.subset
                    )

    def test_context_validator_checks_operator_cardinality(self):
        value_plan = DirectCategoricalValuePlan(
            "genres", ("Action", "Mystery")
        )
        self.assertIsNone(
            validate_direct_categorical_value_context(
                value_plan,
                OperatorCardinalityPlan("all_of", 2),
                self.rules,
                self.subset,
            )
        )
        with self.assertRaisesRegex(ValueError, "cardinality"):
            validate_direct_categorical_value_context(
                value_plan,
                OperatorCardinalityPlan("all_of", 1),
                self.rules,
                self.subset,
            )

    def test_output_contract_contains_no_operator_or_downstream_payload(self):
        self.assertEqual(
            [field.name for field in fields(DirectCategoricalValuePlan)],
            ["field", "values"],
        )
        plan = DirectCategoricalValuePlan("tags", ("Female Harem",))
        for forbidden in (
            "operator",
            "cardinality",
            "tag_group",
            "numeric_range",
            "semantic_spec",
            "dataset_record",
            "user_text",
        ):
            self.assertFalse(hasattr(plan, forbidden))


if __name__ == "__main__":
    unittest.main()
