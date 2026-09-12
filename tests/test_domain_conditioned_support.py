"""Acceptance tests for E2A Domain-Conditioned Structural Support v0.1."""

import ast
from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import load_domain_rules
from anime_pref.data.reference_title_pool import load_reference_title_pool
from anime_pref.data.rules_identity import domain_rules_sha256
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.schemas.domain_bindability import ReferenceTitlePoolSpec
from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.structural_signature import StructuralSignature
from anime_pref.sampling.config import load_sampler_config
import anime_pref.sampling.domain_conditioned_support as support_module
from anime_pref.sampling.domain_conditioned_support import (
    bindable_mechanics_candidates,
    bindable_structural_signatures,
)
from anime_pref.sampling.mechanics_probability import mechanics_candidates
from anime_pref.sampling.structural_signature import (
    enumerate_eligible_structural_signatures,
    load_structural_pattern_selection_policy,
    signature_probabilities,
)


FIXTURES = PROJECT_ROOT / "tests/fixtures"


def family_plan(family, bucket):
    return FamilyComplexityPlan(family, bucket)


def signature(*kinds):
    return StructuralSignature(tuple(kinds))


def rehash_rules(rules, **changes):
    changed = replace(rules, **changes)
    return replace(changed, rules_hash=domain_rules_sha256(changed))


class DomainSupportTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_sampler_config(
            FIXTURES / "semantic_sampler.synthetic.v0.1.json"
        )
        cls.policy = load_structural_pattern_selection_policy(
            FIXTURES / "structural_pattern_policy.synthetic.v0.1.json"
        )
        cls.rules = load_domain_rules(
            FIXTURES / "domain_rules.synthetic.v0.1.json"
        )
        cls.subset = load_executable_tag_subset(
            FIXTURES / "executable_tags.synthetic.v0.1.json"
        )
        cls.title_pool = load_reference_title_pool(
            FIXTURES / "reference_titles.synthetic.v0.1.json"
        )
        cls.empty_title_pool = ReferenceTitlePoolSpec(
            "offline-empty-reference-titles-v0.1", ()
        )

    def mechanics(self, plan, selected, *, rules=None, pool=None):
        return bindable_mechanics_candidates(
            plan,
            selected,
            self.config,
            self.rules if rules is None else rules,
            self.subset,
            self.title_pool if pool is None else pool,
        )

    def signatures(self, plan, *, rules=None, pool=None):
        return bindable_structural_signatures(
            self.policy,
            self.config,
            plan,
            self.rules if rules is None else rules,
            self.subset,
            self.title_pool if pool is None else pool,
        )


class MechanicsSupportTests(DomainSupportTestCase):
    def test_d5b_candidate_order_is_preserved_after_e1_filter(self):
        plan = family_plan("cross_field_composition", "4")
        selected = signature("genre_set", "year_range")
        original = mechanics_candidates(plan, selected)
        actual = self.mechanics(plan, selected)
        self.assertTrue(set(actual).issubset(original))
        self.assertEqual(actual, tuple(item for item in original if item in actual))

    def test_e1_validator_is_the_only_bindability_truth_source(self):
        plan = family_plan("cross_field_composition", "4")
        selected = signature("genre_set", "year_range")
        candidates = mechanics_candidates(plan, selected)

        def accept_only(candidate, *_):
            if candidate != candidates[-1]:
                raise ValueError("synthetic zero capacity")

        with patch.object(
            support_module,
            "validate_structural_pattern_bindability",
            side_effect=accept_only,
        ) as e1:
            self.assertEqual(self.mechanics(plan, selected), (candidates[-1],))
        self.assertEqual(e1.call_count, len(candidates))

    def test_only_value_error_is_treated_as_unbindable(self):
        with patch.object(
            support_module,
            "validate_structural_pattern_bindability",
            side_effect=RuntimeError("invariant failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.mechanics(
                    family_plan("single_constraint", "1"),
                    signature("format_any"),
                )

    def test_numeric_e1_failure_filters_relevant_mechanics(self):
        with patch.object(
            support_module,
            "validate_structural_pattern_bindability",
            side_effect=ValueError("numeric capacity unavailable"),
        ):
            self.assertEqual(
                self.mechanics(
                    family_plan("single_constraint", "1"),
                    signature("year_range"),
                ),
                (),
            )

    def test_repeated_queries_return_identical_immutable_tuples(self):
        plan = family_plan("cross_field_composition", "3")
        selected = signature("genre_set", "year_range")
        first = self.mechanics(plan, selected)
        second = self.mechanics(plan, selected)
        self.assertIsInstance(first, tuple)
        self.assertEqual(first, second)


class SignatureSupportTests(DomainSupportTestCase):
    def test_signature_order_comes_from_d5a_enabled_mapping(self):
        plan = family_plan("single_constraint", "1")
        enabled = tuple(signature_probabilities(self.policy, plan))
        bindable = self.signatures(plan)
        self.assertEqual(bindable, tuple(item for item in enabled if item in bindable))

    def test_d5a_disabled_but_bindable_signature_is_not_reenabled(self):
        plan = family_plan("single_constraint", "1")
        disabled = signature("status_any")
        self.assertIn(disabled, enumerate_eligible_structural_signatures(plan))
        self.assertNotIn(disabled, signature_probabilities(self.policy, plan))
        self.assertTrue(self.mechanics(plan, disabled))
        self.assertNotIn(disabled, self.signatures(plan))

    def test_signature_is_kept_exactly_when_mechanics_support_is_nonempty(self):
        plan = family_plan("single_constraint", "1")
        enabled = tuple(signature_probabilities(self.policy, plan))
        expected = tuple(
            selected
            for selected in enabled
            if self.mechanics(plan, selected)
        )
        self.assertEqual(self.signatures(plan), expected)

    def test_zero_mechanics_removes_signature_and_exposes_empty_context(self):
        plan = family_plan("normalization", "5_plus")
        selected = signature("genre_set", "tag_set", "tag_group_none")
        self.assertIn(selected, signature_probabilities(self.policy, plan))
        self.assertEqual(self.mechanics(plan, selected), ())
        self.assertEqual(self.signatures(plan), ())

    def test_candidate_multiplicity_does_not_change_signature_membership_shape(self):
        plan = family_plan("single_constraint", "1")
        supports = {
            selected: len(self.mechanics(plan, selected))
            for selected in signature_probabilities(self.policy, plan)
        }
        self.assertGreater(len(set(supports.values())), 1)
        result = self.signatures(plan)
        self.assertTrue(all(isinstance(item, StructuralSignature) for item in result))
        self.assertEqual(set(result), {item for item, count in supports.items() if count})


class SyntheticHaremIntegrationTests(DomainSupportTestCase):
    def setUp(self):
        self.plan = family_plan("normalization", "5_plus")
        self.selected = signature("genre_set", "tag_set", "tag_group_none")

    def test_direct_tag_harem_gap_is_filtered(self):
        self.assertEqual(self.mechanics(self.plan, self.selected), ())

    def test_activating_ensemble_cast_restores_mechanics_and_signature(self):
        activated = rehash_rules(
            self.rules,
            tags=self.rules.tags | {"Ensemble Cast"},
        )
        mechanics = self.mechanics(self.plan, self.selected, rules=activated)
        self.assertEqual(len(mechanics), 2)
        self.assertEqual(
            self.signatures(self.plan, rules=activated),
            (self.selected,),
        )

    def test_group_only_normalization_remains_bindable(self):
        plan = family_plan("normalization", "1")
        selected = signature("tag_group_none")
        self.assertTrue(self.mechanics(plan, selected))
        self.assertIn(selected, self.signatures(plan))


class ReferenceResourceTests(DomainSupportTestCase):
    def test_empty_pool_removes_reference_only_mechanics_and_signature(self):
        plan = family_plan("reference_only", 0)
        selected = signature("reference")
        self.assertEqual(
            self.mechanics(plan, selected, pool=self.empty_title_pool), ()
        )
        self.assertEqual(self.signatures(plan, pool=self.empty_title_pool), ())

    def test_empty_pool_removes_reference_composition_support(self):
        plan = family_plan("reference_composition", "2")
        selected = signature("genre_set", "reference")
        self.assertEqual(
            self.mechanics(plan, selected, pool=self.empty_title_pool), ()
        )
        self.assertEqual(self.signatures(plan, pool=self.empty_title_pool), ())

    def test_empty_pool_does_not_affect_non_reference_support(self):
        plan = family_plan("cross_field_composition", "3")
        selected = signature("genre_set", "year_range")
        self.assertEqual(
            self.mechanics(plan, selected, pool=self.empty_title_pool),
            self.mechanics(plan, selected, pool=self.title_pool),
        )


class BindingAndBoundaryTests(DomainSupportTestCase):
    def test_signature_public_api_performs_d5a_and_domain_prebinding(self):
        events = []
        real_policy = support_module.validate_structural_pattern_selection_policy
        real_domain = support_module.validate_sampler_config_against_domain
        real_pool = support_module.validate_reference_title_pool

        def policy(*args):
            events.append("policy")
            return real_policy(*args)

        def domain(*args):
            events.append("domain")
            return real_domain(*args)

        def pool(*args):
            events.append("title_pool")
            return real_pool(*args)

        with patch.object(
            support_module,
            "validate_structural_pattern_selection_policy",
            side_effect=policy,
        ), patch.object(
            support_module,
            "validate_sampler_config_against_domain",
            side_effect=domain,
        ), patch.object(
            support_module,
            "validate_reference_title_pool",
            side_effect=pool,
        ):
            self.signatures(family_plan("single_constraint", "1"))
        self.assertEqual(events[:3], ["policy", "domain", "title_pool"])

    def test_invalid_resources_raise_instead_of_becoming_empty_support(self):
        invalid_pool = ReferenceTitlePoolSpec(" bad", ())
        with self.assertRaises(ValueError):
            self.signatures(
                family_plan("single_constraint", "1"),
                pool=invalid_pool,
            )

    def test_module_contains_no_rng_probability_sampling_or_downstream_layer(self):
        source = inspect.getsource(support_module)
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        forbidden_imports = {
            "random",
            "anime_pref.sampling.family_complexity",
            "anime_pref.sampling.categorical_value",
            "anime_pref.sampling.numeric_range",
            "anime_pref.data.anilist_client",
            "anime_pref.schemas.preference_query",
            "anime_pref.schemas.dataset_record",
        }
        # Importing numeric-range sampling is forbidden; E2A reaches numeric
        # bindability exclusively through E1 rather than importing D2 itself.
        self.assertTrue(forbidden_imports.isdisjoint(imports))
        for forbidden_text in (
            "_weighted_choice",
            "normalize_relative_weights",
            "mechanics_pattern_probabilities",
            "sample_",
            "SemanticSpec",
            "DatasetRecord",
            "user_text",
        ):
            self.assertNotIn(forbidden_text, source)
        self.assertFalse(any(isinstance(node, ast.While) for node in ast.walk(tree)))
        self.assertFalse(
            any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("sample_")
                for node in ast.walk(tree)
            )
        )


if __name__ == "__main__":
    unittest.main()
