"""Acceptance tests for D5B mechanics conditional probabilities v0.1."""

import ast
from dataclasses import replace
import inspect
import math
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import WeightTableSpec
from anime_pref.schemas.structural_signature import StructuralSignature
from anime_pref.sampling.config import load_sampler_config
import anime_pref.sampling.mechanics_probability as mechanics_module
from anime_pref.sampling.mechanics_probability import (
    conditional_cardinality_probabilities,
    conditional_numeric_pattern_probabilities,
    conditional_operator_probabilities,
    feasible_numeric_patterns,
    feasible_set_cardinalities,
    feasible_set_operators,
    mechanics_candidates,
    mechanics_pattern_probabilities,
)
from anime_pref.sampling.operator_cardinality import (
    joint_operator_cardinality_probabilities,
)
from anime_pref.sampling.structural_pattern import (
    enumerate_eligible_structural_patterns,
)
from anime_pref.sampling.structural_signature import structural_signature

SAMPLER_PATH = PROJECT_ROOT / "tests/fixtures/semantic_sampler.synthetic.v0.1.json"


def signature(*atom_kinds):
    return StructuralSignature(tuple(atom_kinds))


class MechanicsProbabilityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_sampler_config(SAMPLER_PATH)

    def assert_probability_mappings_close(self, left, right):
        self.assertEqual(list(left), list(right))
        for key in left:
            self.assertTrue(math.isclose(left[key], right[key], abs_tol=1e-12))


class CandidateAndSupportTests(MechanicsProbabilityTestCase):
    def test_candidates_equal_d4_patterns_restricted_by_signature(self):
        family_plan = FamilyComplexityPlan("cross_field_composition", "3")
        selected = signature("genre_set", "year_range")
        expected = tuple(
            pattern
            for pattern in enumerate_eligible_structural_patterns(family_plan)
            if structural_signature(pattern) == selected
        )
        self.assertEqual(mechanics_candidates(family_plan, selected), expected)

    def test_invalid_or_context_ineligible_signature_is_rejected(self):
        invalid = (
            signature("reference", "genre_set"),
            signature("genre_set"),
            signature("format_any", "reference"),
        )
        family_plan = FamilyComplexityPlan("cross_field_composition", "2")
        for selected in invalid:
            with self.subTest(selected=selected):
                with self.assertRaises(ValueError):
                    mechanics_candidates(family_plan, selected)

    def test_set_operator_support_uses_completion_presence_not_count(self):
        candidates = mechanics_candidates(
            FamilyComplexityPlan("cross_field_composition", "4"),
            signature("genre_set", "year_range"),
        )
        self.assertEqual(feasible_set_operators(candidates, "genre_set"), ("all_of", "none_of"))
        probabilities = conditional_operator_probabilities(
            self.config,
            candidates,
            "genre_set",
        )
        # all_of has three completions and none_of only one. Their probabilities
        # still use 45:25, with no survivor-count multiplier.
        self.assertEqual(probabilities, {"all_of": 45 / 70, "none_of": 25 / 70})

    def test_cardinality_support_is_conditioned_on_operator_and_survivors(self):
        candidates = mechanics_candidates(
            FamilyComplexityPlan("cross_field_composition", "4"),
            signature("genre_set", "year_range"),
        )
        self.assertEqual(
            feasible_set_cardinalities(candidates, "genre_set", "all_of"),
            (2, 3),
        )
        self.assertEqual(
            feasible_set_cardinalities(candidates, "genre_set", "none_of"),
            (2,),
        )
        self.assertEqual(
            conditional_cardinality_probabilities(
                self.config, candidates, "genre_set", "none_of"
            ),
            {2: 1.0},
        )

    def test_numeric_support_is_feasibility_filtered(self):
        candidates = mechanics_candidates(
            FamilyComplexityPlan("single_constraint", "1"),
            signature("year_range"),
        )
        self.assertEqual(
            feasible_numeric_patterns(candidates, "year_range"),
            ("min_only", "max_only"),
        )
        self.assertEqual(
            conditional_numeric_pattern_probabilities(
                self.config,
                candidates,
                "year_range",
            ),
            {"min_only": 4 / 7, "max_only": 3 / 7},
        )

    def test_exact_complexity_couples_earlier_set_and_later_numeric_mechanics(self):
        candidates = mechanics_candidates(
            FamilyComplexityPlan("cross_field_composition", "4"),
            signature("genre_set", "year_range"),
        )
        all_two = tuple(
            pattern
            for pattern in candidates
            if pattern.atoms[0].operator_plan.operator == "all_of"
            and pattern.atoms[0].operator_plan.cardinality == 2
        )
        all_three = tuple(
            pattern
            for pattern in candidates
            if pattern.atoms[0].operator_plan.operator == "all_of"
            and pattern.atoms[0].operator_plan.cardinality == 3
        )
        self.assertEqual(feasible_numeric_patterns(all_two, "year_range"), ("bounded_range",))
        self.assertEqual(
            feasible_numeric_patterns(all_three, "year_range"),
            ("min_only", "max_only"),
        )

    def test_tag_any_aggregation_restricts_normalization_completion(self):
        family_plan = FamilyComplexityPlan("normalization", "1")
        selected = signature("tag_set", "tag_group_any")
        candidates = mechanics_candidates(family_plan, selected)
        self.assertEqual(feasible_set_operators(candidates, "tag_set"), ("any_of",))
        probabilities = mechanics_pattern_probabilities(
            self.config,
            family_plan,
            selected,
        )
        payloads = [pattern.atoms[0].operator_plan for pattern in probabilities]
        self.assertEqual(
            [(plan.operator, plan.cardinality) for plan in payloads],
            [("any_of", 2), ("any_of", 3)],
        )
        self.assertEqual(list(probabilities.values()), [0.8, 0.2])


class DistributionTests(MechanicsProbabilityTestCase):
    def test_every_representative_distribution_is_positive_and_normalized(self):
        contexts = (
            ("single_constraint", "1", ("year_range",)),
            ("same_field_logic", "2", ("tag_set",)),
            ("cross_field_composition", "3", ("genre_set", "year_range")),
            ("normalization", "2", ("genre_set", "tag_group_none")),
            ("reference_only", 0, ("reference",)),
            ("reference_composition", "2", ("genre_set", "reference")),
        )
        for family, bucket, kinds in contexts:
            with self.subTest(family=family, bucket=bucket, kinds=kinds):
                probabilities = mechanics_pattern_probabilities(
                    self.config,
                    FamilyComplexityPlan(family, bucket),
                    StructuralSignature(kinds),
                )
                self.assertTrue(all(value > 0 for value in probabilities.values()))
                self.assertTrue(math.isclose(sum(probabilities.values()), 1.0))

    def test_payload_free_and_reference_only_singletons_have_probability_one(self):
        examples = (
            (FamilyComplexityPlan("single_constraint", "1"), signature("format_any")),
            (FamilyComplexityPlan("normalization", "1"), signature("tag_group_none")),
            (FamilyComplexityPlan("reference_only", 0), signature("reference")),
        )
        for family_plan, selected in examples:
            with self.subTest(family_plan=family_plan, selected=selected):
                probabilities = mechanics_pattern_probabilities(
                    self.config,
                    family_plan,
                    selected,
                )
                self.assertEqual(len(probabilities), 1)
                self.assertEqual(next(iter(probabilities.values())), 1.0)

    def test_phase_c_same_field_joint_distribution_equivalence(self):
        for bucket in ("1", "2", "3"):
            family_plan = FamilyComplexityPlan("same_field_logic", bucket)
            phase_c = joint_operator_cardinality_probabilities(
                self.config,
                family_plan,
            )
            phase_d5b = mechanics_pattern_probabilities(
                self.config,
                family_plan,
                signature("genre_set"),
            )
            collapsed = {
                (
                    pattern.atoms[0].operator_plan.operator,
                    pattern.atoms[0].operator_plan.cardinality,
                ): probability
                for pattern, probability in phase_d5b.items()
            }
            with self.subTest(bucket=bucket):
                self.assert_probability_mappings_close(collapsed, phase_c)

    def test_same_field_complexity_three_is_deterministic(self):
        probabilities = mechanics_pattern_probabilities(
            self.config,
            FamilyComplexityPlan("same_field_logic", "3"),
            signature("tag_set"),
        )
        self.assertEqual(len(probabilities), 1)
        pattern = next(iter(probabilities))
        self.assertEqual(
            pattern.atoms[0].operator_plan,
            __import__(
                "anime_pref.schemas.operator_cardinality",
                fromlist=["OperatorCardinalityPlan"],
            ).OperatorCardinalityPlan("all_of", 3),
        )
        self.assertEqual(probabilities[pattern], 1.0)

    def test_five_plus_context_uses_actual_eligible_completions(self):
        probabilities = mechanics_pattern_probabilities(
            self.config,
            FamilyComplexityPlan("cross_field_composition", "5_plus"),
            signature("genre_set", "year_range"),
        )
        self.assertEqual(len(probabilities), 1)
        only = next(iter(probabilities))
        self.assertEqual(only.atoms[0].operator_plan.cardinality, 3)
        self.assertEqual(only.atoms[1].range_pattern, "bounded_range")
        self.assertEqual(probabilities[only], 1.0)

    def test_output_order_is_d4_order_and_repeated_results_are_deterministic(self):
        family_plan = FamilyComplexityPlan("cross_field_composition", "3")
        selected = signature("genre_set", "year_range")
        expected_order = mechanics_candidates(family_plan, selected)
        first = mechanics_pattern_probabilities(self.config, family_plan, selected)
        second = mechanics_pattern_probabilities(self.config, family_plan, selected)
        self.assertEqual(tuple(first), expected_order)
        self.assertEqual(first, second)


class ScaleAndLayerIsolationTests(MechanicsProbabilityTestCase):
    def distribution(self, config):
        return mechanics_pattern_probabilities(
            config,
            FamilyComplexityPlan("cross_field_composition", "3"),
            signature("genre_set", "year_range"),
        )

    def test_operator_table_scaling_is_invariant(self):
        scaled = replace(
            self.config,
            operator_weights=WeightTableSpec(
                {key: value * 10 for key, value in self.config.operator_weights.weights.items()}
            ),
        )
        self.assert_probability_mappings_close(self.distribution(self.config), self.distribution(scaled))

    def test_each_operator_cardinality_table_scales_independently(self):
        baseline = self.distribution(self.config)
        for operator in ("all_of", "any_of", "none_of"):
            current = getattr(self.config.operator_cardinality, operator)
            scaled_table = {key: value * 7 for key, value in current.items()}
            scaled_policy = replace(
                self.config.operator_cardinality,
                **{operator: scaled_table},
            )
            scaled = replace(self.config, operator_cardinality=scaled_policy)
            with self.subTest(operator=operator):
                self.assert_probability_mappings_close(baseline, self.distribution(scaled))

    def test_year_and_episode_pattern_tables_scale_independently(self):
        cases = (
            (
                "year_sampling",
                FamilyComplexityPlan("cross_field_composition", "3"),
                signature("genre_set", "year_range"),
            ),
            (
                "episode_sampling",
                FamilyComplexityPlan("cross_field_composition", "3"),
                signature("genre_set", "episodes_range"),
            ),
        )
        for attribute, family_plan, selected in cases:
            baseline = mechanics_pattern_probabilities(
                self.config, family_plan, selected
            )
            policy = getattr(self.config, attribute)
            scaled_policy = replace(
                policy,
                pattern_weights={
                    key: value * 11 for key, value in policy.pattern_weights.items()
                },
            )
            scaled = replace(self.config, **{attribute: scaled_policy})
            with self.subTest(attribute=attribute):
                self.assert_probability_mappings_close(
                    baseline,
                    mechanics_pattern_probabilities(scaled, family_plan, selected),
                )

    def test_numeric_pool_and_categorical_value_weights_are_not_consumed(self):
        baseline = self.distribution(self.config)
        changed_year = replace(
            self.config.year_sampling,
            pool_weights={"common": 1, "catalog_region": 50, "long_tail": 100},
        )
        changed_genre = replace(
            self.config.genre_sampling,
            default_weight=100,
            priority_weights={"Action": 50},
        )
        changed = replace(
            self.config,
            year_sampling=changed_year,
            genre_sampling=changed_genre,
        )
        self.assert_probability_mappings_close(baseline, self.distribution(changed))


class PhaseBoundaryTests(unittest.TestCase):
    def test_module_has_no_rng_rejection_or_downstream_dependency(self):
        source = inspect.getsource(mechanics_module)
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
            "random",
            "anime_pref.data.query_builder",
            "anime_pref.schemas.taxonomy",
            "anime_pref.sampling.categorical_value",
            "anime_pref.sampling.numeric_range",
            "anime_pref.schemas.preference_query",
            "anime_pref.schemas.dataset_record",
        }
        self.assertTrue(forbidden.isdisjoint(imported))
        self.assertFalse(any(name.startswith("sample_") for name in dir(mechanics_module)))
        self.assertNotIn("while ", source)

    def test_d5a_policy_weights_and_concrete_values_are_absent(self):
        source = inspect.getsource(mechanics_module)
        self.assertNotIn("StructuralSignatureWeightSpec", source)
        self.assertNotIn("signature_probabilities", source)
        self.assertNotIn("common_values", source)
        self.assertNotIn("catalog_region_values", source)
        self.assertNotIn("long_tail_values", source)
        self.assertNotIn("genre_sampling", source)
        self.assertNotIn("tag_sampling", source)


if __name__ == "__main__":
    unittest.main()
