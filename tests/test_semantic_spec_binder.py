"""Acceptance tests for E3-Minimal Concrete SemanticSpec Binder v0.1."""

import ast
from dataclasses import replace
import inspect
from pathlib import Path
from random import Random
from types import MappingProxyType
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.dataset_record_builder import count_hard_semantic_clauses
from anime_pref.data.query_builder import TagGroupRule, build_query, load_domain_rules
from anime_pref.data.reference_title_pool import load_reference_title_pool
from anime_pref.data.rules_identity import domain_rules_sha256
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.schemas.domain_bindability import ReferenceTitlePoolSpec
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.preference_query import SemanticSpec
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.sampling.config import load_sampler_config
import anime_pref.sampling.semantic_spec_binder as binder_module
from anime_pref.sampling.semantic_spec_binder import (
    sample_semantic_spec_from_pattern,
)
from anime_pref.sampling.structural_atom import structural_constraint_count


FIXTURES = PROJECT_ROOT / "tests/fixtures"


class CountingRandom:
    """Scripted RNG that exposes exact E3/D1/D2 draw consumption."""

    def __init__(self, values):
        self._values = iter(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return next(self._values)


def pattern(family, bucket, *atoms):
    return StructuralPatternPlan(family, bucket, tuple(atoms))


def set_atom(kind, operator, cardinality):
    return StructuralAtom(
        kind,
        operator_plan=OperatorCardinalityPlan(operator, cardinality),
    )


def rehash_rules(rules, **changes):
    changed = replace(rules, **changes)
    return replace(changed, rules_hash=domain_rules_sha256(changed))


class SemanticBinderTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_sampler_config(
            FIXTURES / "semantic_sampler.synthetic.v0.1.json"
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

    def bind(self, selected_pattern, rng=None, *, rules=None, pool=None):
        return sample_semantic_spec_from_pattern(
            selected_pattern,
            self.config,
            self.rules if rules is None else rules,
            self.subset,
            self.title_pool if pool is None else pool,
            Random(1729) if rng is None else rng,
        )

    def assert_gold_valid_and_count_preserved(self, selected_pattern, spec, rules=None):
        active_rules = self.rules if rules is None else rules
        gold = build_query(spec, active_rules)
        self.assertIsInstance(gold, dict)
        self.assertEqual(
            count_hard_semantic_clauses(spec),
            structural_constraint_count(selected_pattern.atoms),
        )


class AtomicBindingTests(SemanticBinderTestCase):
    def test_genre_only(self):
        selected = pattern(
            "single_constraint", "1", set_atom("genre_set", "all_of", 1)
        )
        spec = self.bind(selected)
        self.assertEqual(len(spec.genres.all_of), 1)
        self.assertTrue(set(spec.genres.all_of) <= self.rules.genres)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_tag_only(self):
        selected = pattern(
            "same_field_logic", "2", set_atom("tag_set", "all_of", 2)
        )
        spec = self.bind(selected)
        self.assertEqual(len(spec.tags.all_of), 2)
        self.assertTrue(set(spec.tags.all_of) <= self.rules.tags)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_year_only(self):
        selected = pattern(
            "single_constraint",
            "1",
            StructuralAtom("year_range", range_pattern="min_only"),
        )
        spec = self.bind(selected)
        self.assertIsNotNone(spec.year.min)
        self.assertIsNone(spec.year.max)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_episodes_only(self):
        selected = pattern(
            "single_constraint",
            "1",
            StructuralAtom("episodes_range", range_pattern="max_only"),
        )
        spec = self.bind(selected)
        self.assertIsNone(spec.episodes.min)
        self.assertIsNotNone(spec.episodes.max)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_format_only_binds_exactly_one_uniform_value(self):
        selected = pattern(
            "single_constraint", "1", StructuralAtom("format_any")
        )
        rng = CountingRandom([0.99])
        spec = self.bind(selected, rng)
        self.assertEqual(spec.formats, (tuple(sorted(self.rules.formats))[-1],))
        self.assertEqual(rng.call_count, 1)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_status_only_binds_exactly_one_uniform_value(self):
        selected = pattern(
            "single_constraint", "1", StructuralAtom("status_any")
        )
        rng = CountingRandom([0.0])
        spec = self.bind(selected, rng)
        self.assertEqual(spec.status, (tuple(sorted(self.rules.statuses))[0],))
        self.assertEqual(rng.call_count, 1)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_reference_only_binds_exactly_one_title(self):
        selected = pattern(
            "reference_only", 0, StructuralAtom("reference")
        )
        rng = CountingRandom([0.99])
        spec = self.bind(selected, rng)
        self.assertEqual(spec.reference_titles, ("Steins;Gate",))
        self.assertEqual(rng.call_count, 1)
        self.assert_gold_valid_and_count_preserved(selected, spec)


class CompositionTests(SemanticBinderTestCase):
    def test_cross_field_concrete_spec_and_gold(self):
        selected = pattern(
            "cross_field_composition",
            "3",
            set_atom("genre_set", "any_of", 2),
            StructuralAtom("year_range", range_pattern="bounded_range"),
        )
        spec = self.bind(selected, Random(41))
        self.assertEqual(len(spec.genres.any_of), 2)
        self.assertIsNotNone(spec.year.min)
        self.assertIsNotNone(spec.year.max)
        self.assertLessEqual(spec.year.min, spec.year.max)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_reference_composition(self):
        selected = pattern(
            "reference_composition",
            "2",
            set_atom("genre_set", "all_of", 2),
            StructuralAtom("reference"),
        )
        spec = self.bind(selected, Random(99))
        self.assertEqual(len(spec.genres.all_of), 2)
        self.assertEqual(len(spec.reference_titles), 1)
        self.assert_gold_valid_and_count_preserved(selected, spec)

    def test_group_only_keeps_identity_until_gold_builder_expands(self):
        selected = pattern(
            "normalization", "1", StructuralAtom("tag_group_any")
        )
        spec = self.bind(selected, CountingRandom([]))
        self.assertEqual(spec.tag_groups.any_of, ("HAREM",))
        self.assertEqual(spec.tags.any_of, ())
        gold = build_query(spec, self.rules)
        self.assertEqual(
            gold["hard_constraints"]["tags"]["any_of"],
            ["Female Harem", "Male Harem", "Mixed Gender Harem"],
        )
        self.assert_gold_valid_and_count_preserved(selected, spec)


class RestrictedTagBindingTests(SemanticBinderTestCase):
    def setUp(self):
        self.activated_rules = rehash_rules(
            self.rules,
            tags=self.rules.tags | {"Ensemble Cast"},
        )
        self.selected = pattern(
            "normalization",
            "2",
            set_atom("tag_set", "all_of", 1),
            StructuralAtom("tag_group_any"),
        )

    def test_direct_tag_and_group_bind_without_duplicate_or_overlap(self):
        spec = self.bind(
            self.selected,
            CountingRandom([]),
            rules=self.activated_rules,
        )
        self.assertEqual(spec.tags.all_of, ("Ensemble Cast",))
        self.assertEqual(spec.tag_groups.any_of, ("HAREM",))
        expansion = set(self.activated_rules.tag_groups["HAREM"].tags)
        self.assertTrue(set(spec.tags.all_of).isdisjoint(expansion))
        self.assert_gold_valid_and_count_preserved(
            self.selected, spec, self.activated_rules
        )

    def test_residual_singleton_skips_full_domain_max_share_rejection(self):
        # HAREM reserves three active tags, leaving only Ensemble Cast.  Its
        # conditional probability is necessarily 1.0 and consumes no draw.
        rng = CountingRandom([])
        spec = self.bind(self.selected, rng, rules=self.activated_rules)
        self.assertEqual(spec.tags.all_of, ("Ensemble Cast",))
        self.assertEqual(rng.call_count, 0)

    def test_approved_but_inactive_tag_cannot_be_used(self):
        self.assertIn(
            "Ensemble Cast", {tag.tag_name for tag in self.subset.tags}
        )
        self.assertNotIn("Ensemble Cast", self.rules.tags)
        rng = CountingRandom([0.0])
        with self.assertRaises(ValueError):
            self.bind(self.selected, rng, rules=self.rules)
        self.assertEqual(rng.call_count, 0)

    def test_group_identity_is_bound_before_restricted_direct_tag(self):
        events = []
        real_group = binder_module.feasible_tag_group_bindings
        real_tags = binder_module._sample_restricted_tag_values

        def groups(*args):
            events.append("group")
            return real_group(*args)

        def tags(*args):
            events.append("direct_tag")
            return real_tags(*args)

        with patch.object(
            binder_module, "feasible_tag_group_bindings", side_effect=groups
        ), patch.object(
            binder_module, "_sample_restricted_tag_values", side_effect=tags
        ):
            self.bind(
                self.selected,
                CountingRandom([]),
                rules=self.activated_rules,
            )
        self.assertEqual(events, ["group", "direct_tag"])


class RngAndValidationTests(SemanticBinderTestCase):
    def test_invalid_structure_config_subset_and_pool_fail_before_draw(self):
        valid_pattern = pattern(
            "single_constraint", "1", StructuralAtom("format_any")
        )
        invalid_cases = (
            (
                object(),
                self.config,
                self.subset,
                self.title_pool,
            ),
            (
                valid_pattern,
                object(),
                self.subset,
                self.title_pool,
            ),
            (
                valid_pattern,
                self.config,
                replace(self.subset, subset_version="tampered-subset-v0.1"),
                self.title_pool,
            ),
            (
                valid_pattern,
                self.config,
                self.subset,
                ReferenceTitlePoolSpec(" bad-version", ()),
            ),
        )
        for selected, config, subset, pool in invalid_cases:
            rng = CountingRandom([0.1])
            with self.subTest(selected=selected, pool=pool), self.assertRaises(
                (TypeError, ValueError)
            ):
                sample_semantic_spec_from_pattern(
                    selected,
                    config,
                    self.rules,
                    subset,
                    pool,
                    rng,
                )
            self.assertEqual(rng.call_count, 0)

    def test_multiple_group_bindings_use_one_uniform_draw(self):
        groups = MappingProxyType(
            {
                "A_GROUP": TagGroupRule(
                    ("Female Harem",), frozenset({"any_of"}), "RULE_A"
                ),
                "B_GROUP": TagGroupRule(
                    ("Male Harem",), frozenset({"any_of"}), "RULE_B"
                ),
            }
        )
        rules = rehash_rules(self.rules, tag_groups=groups)
        selected = pattern(
            "normalization", "1", StructuralAtom("tag_group_any")
        )
        rng = CountingRandom([0.99])
        spec = self.bind(selected, rng, rules=rules)
        self.assertEqual(spec.tag_groups.any_of, ("B_GROUP",))
        self.assertEqual(rng.call_count, 1)

    def test_singleton_format_support_consumes_zero_draws(self):
        rules = rehash_rules(self.rules, formats=frozenset({"TV"}))
        selected = pattern(
            "single_constraint", "1", StructuralAtom("format_any")
        )
        rng = CountingRandom([])
        self.assertEqual(self.bind(selected, rng, rules=rules).formats, ("TV",))
        self.assertEqual(rng.call_count, 0)

    def test_same_state_reproduces_spec_and_rng_advancement(self):
        selected = pattern(
            "cross_field_composition",
            "4",
            set_atom("genre_set", "all_of", 2),
            StructuralAtom("year_range", range_pattern="bounded_range"),
        )
        left_rng = Random(8080)
        right_rng = Random(8080)
        left = self.bind(selected, left_rng)
        right = self.bind(selected, right_rng)
        self.assertEqual(left, right)
        self.assertEqual(left_rng.getstate(), right_rng.getstate())

    def test_unbindable_pattern_and_invalid_rng_fail_before_draw(self):
        unbindable = pattern(
            "normalization",
            "2",
            set_atom("tag_set", "all_of", 1),
            StructuralAtom("tag_group_any"),
        )
        rng = CountingRandom([0.1])
        with self.assertRaises(ValueError):
            self.bind(unbindable, rng)
        self.assertEqual(rng.call_count, 0)

        deterministic = pattern(
            "normalization", "1", StructuralAtom("tag_group_any")
        )
        with self.assertRaises(ValueError):
            self.bind(deterministic, object())

    def test_build_query_is_final_smoke_validator(self):
        selected = pattern(
            "single_constraint", "1", StructuralAtom("format_any")
        )
        real_builder = binder_module.build_query
        with patch.object(
            binder_module, "build_query", wraps=real_builder
        ) as builder:
            spec = self.bind(selected)
        builder.assert_called_once_with(spec, self.rules)

    def test_soft_and_unresolved_preferences_remain_empty(self):
        selected = pattern(
            "reference_only", 0, StructuralAtom("reference")
        )
        spec = self.bind(selected)
        self.assertEqual(spec.soft_preferences, ())
        self.assertEqual(spec.unresolved_preferences, ())


class PhaseBoundaryTests(unittest.TestCase):
    def test_returns_existing_semantic_spec_without_wrapper(self):
        config = load_sampler_config(FIXTURES / "semantic_sampler.synthetic.v0.1.json")
        rules = load_domain_rules(FIXTURES / "domain_rules.synthetic.v0.1.json")
        subset = load_executable_tag_subset(
            FIXTURES / "executable_tags.synthetic.v0.1.json"
        )
        pool = load_reference_title_pool(
            FIXTURES / "reference_titles.synthetic.v0.1.json"
        )
        result = sample_semantic_spec_from_pattern(
            pattern("reference_only", 0, StructuralAtom("reference")),
            config,
            rules,
            subset,
            pool,
            Random(1),
        )
        self.assertIsInstance(result, SemanticSpec)

    def test_module_has_no_structural_resampling_catalog_or_dataset_layer(self):
        source = inspect.getsource(binder_module)
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
            "anime_pref.data.anilist_client",
            "anime_pref.schemas.dataset_record",
            "anime_pref.sampling.structural_signature_sampler",
            "anime_pref.sampling.mechanics_sampler",
            "anime_pref.sampling.domain_conditioned_support",
        }
        self.assertTrue(forbidden_imports.isdisjoint(imports))
        for forbidden_text in (
            "DatasetRecord",
            "user_text",
            "sample_structural_signature",
            "sample_mechanics_pattern",
        ):
            self.assertNotIn(forbidden_text, source)
        self.assertFalse(any(isinstance(node, ast.Try) for node in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main()
