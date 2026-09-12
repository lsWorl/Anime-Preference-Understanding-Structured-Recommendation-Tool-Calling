"""Acceptance tests for E1 Structural Pattern Domain Bindability v0.1."""

import ast
from dataclasses import replace
import inspect
from pathlib import Path
from types import MappingProxyType
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import TagGroupRule, load_domain_rules
from anime_pref.data.reference_title_pool import (
    load_reference_title_pool,
    validate_reference_title_pool,
)
from anime_pref.data.rules_identity import domain_rules_sha256
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.schemas.domain_bindability import (
    ReferenceTitlePoolSpec,
    TagGroupBindingPlan,
)
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.sampling.config import load_sampler_config
import anime_pref.sampling.domain_bindability as bindability_module
from anime_pref.sampling.domain_bindability import (
    feasible_tag_group_bindings,
    validate_structural_pattern_bindability,
)


FIXTURES = PROJECT_ROOT / "tests/fixtures"
CONFIG_PATH = FIXTURES / "semantic_sampler.synthetic.v0.1.json"
RULES_PATH = FIXTURES / "domain_rules.synthetic.v0.1.json"
SUBSET_PATH = FIXTURES / "executable_tags.synthetic.v0.1.json"
TITLE_POOL_PATH = FIXTURES / "reference_titles.synthetic.v0.1.json"


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


def group(tags, operators, suffix):
    return TagGroupRule(tuple(tags), frozenset(operators), f"RULE_{suffix}")


class BindabilityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_sampler_config(CONFIG_PATH)
        cls.rules = load_domain_rules(RULES_PATH)
        cls.subset = load_executable_tag_subset(SUBSET_PATH)
        cls.title_pool = load_reference_title_pool(TITLE_POOL_PATH)
        cls.empty_title_pool = ReferenceTitlePoolSpec(
            "offline-empty-reference-titles-v0.1", ()
        )

    def validate(self, selected_pattern, *, rules=None, pool=None, config=None):
        return validate_structural_pattern_bindability(
            selected_pattern,
            self.config if config is None else config,
            self.rules if rules is None else rules,
            self.subset,
            self.title_pool if pool is None else pool,
        )


class ResourceContractTests(BindabilityTestCase):
    def test_fixture_loads_as_canonical_offline_pool(self):
        self.assertEqual(
            self.title_pool,
            ReferenceTitlePoolSpec(
                "offline-synthetic-reference-titles-v0.1",
                ("Fullmetal Alchemist: Brotherhood", "Steins;Gate"),
            ),
        )

    def test_empty_pool_is_valid_for_non_reference_patterns(self):
        validate_reference_title_pool(self.empty_title_pool)
        self.assertIsNone(
            self.validate(
                pattern("single_constraint", "1", StructuralAtom("format_any")),
                pool=self.empty_title_pool,
            )
        )

    def test_pool_rejects_whitespace_duplicates_and_nondeterministic_order(self):
        invalid = (
            ReferenceTitlePoolSpec(" v1", ()),
            ReferenceTitlePoolSpec("v1", ("Title ",)),
            ReferenceTitlePoolSpec("v1", ("Title", "Title")),
            ReferenceTitlePoolSpec("v1", ("Zeta", "Alpha")),
        )
        for pool in invalid:
            with self.subTest(pool=pool), self.assertRaises(ValueError):
                validate_reference_title_pool(pool)

    def test_loader_rejects_noncanonical_title_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pool.json"
            path.write_text(
                '{"pool_version":"v1","titles":["Zeta","Alpha"]}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_reference_title_pool(path)


class PublicBindingAndCapacityTests(BindabilityTestCase):
    def test_valid_structural_pattern_and_full_domain_binding_pass(self):
        selected = pattern(
            "cross_field_composition",
            "2",
            set_atom("genre_set", "all_of", 1),
            StructuralAtom("format_any"),
        )
        self.assertIsNone(self.validate(selected))

    def test_full_config_rules_subset_binding_is_called_before_capacity(self):
        selected = pattern(
            "single_constraint", "1", StructuralAtom("format_any")
        )
        with patch.object(
            bindability_module,
            "validate_sampler_config_against_domain",
            wraps=bindability_module.validate_sampler_config_against_domain,
        ) as binding:
            self.validate(selected)
        binding.assert_called_once_with(self.config, self.rules, self.subset)

    def test_rules_subset_identity_mismatch_is_rejected(self):
        selected = pattern(
            "single_constraint", "1", StructuralAtom("format_any")
        )
        tampered_subset = replace(
            self.subset,
            subset_version="different-approved-subset-v0.1",
        )
        with self.assertRaises(ValueError):
            validate_structural_pattern_bindability(
                selected,
                self.config,
                self.rules,
                tampered_subset,
                self.title_pool,
            )

    def test_genre_cardinality_capacity(self):
        selected = pattern(
            "same_field_logic", "3", set_atom("genre_set", "all_of", 3)
        )
        two_genres = rehash_rules(
            self.rules,
            genres=frozenset({"Mystery", "Sci-Fi"}),
        )
        with self.assertRaises(ValueError):
            self.validate(selected, rules=two_genres)

    def test_year_binding_reuses_d2_validator(self):
        selected = pattern(
            "single_constraint",
            "1",
            StructuralAtom("year_range", range_pattern="min_only"),
        )
        with patch.object(
            bindability_module,
            "validate_numeric_sampling_binding",
            wraps=bindability_module.validate_numeric_sampling_binding,
        ) as numeric_binding:
            self.validate(selected)
        numeric_binding.assert_called_once_with("year", self.config, self.rules)

    def test_episode_binding_reuses_d2_validator(self):
        selected = pattern(
            "single_constraint",
            "1",
            StructuralAtom("episodes_range", range_pattern="max_only"),
        )
        with patch.object(
            bindability_module,
            "validate_numeric_sampling_binding",
            wraps=bindability_module.validate_numeric_sampling_binding,
        ) as numeric_binding:
            self.validate(selected)
        numeric_binding.assert_called_once_with("episodes", self.config, self.rules)

    def test_invalid_year_and_episode_binding_fail(self):
        cases = (
            (
                StructuralAtom("year_range", range_pattern="min_only"),
                replace(
                    self.config,
                    year_sampling=replace(
                        self.config.year_sampling,
                        long_tail_values=(1899,),
                    ),
                ),
            ),
            (
                StructuralAtom("episodes_range", range_pattern="max_only"),
                replace(
                    self.config,
                    episode_sampling=replace(
                        self.config.episode_sampling,
                        long_tail_values=(0,),
                    ),
                ),
            ),
        )
        for selected_atom, invalid_config in cases:
            with self.subTest(kind=selected_atom.kind), self.assertRaises(ValueError):
                self.validate(
                    pattern("single_constraint", "1", selected_atom),
                    config=invalid_config,
                )

    def test_format_and_status_require_nonempty_active_vocabularies(self):
        cases = (
            ("format_any", replace(self.rules, formats=frozenset())),
            ("status_any", replace(self.rules, statuses=frozenset())),
        )
        for kind, invalid_rules in cases:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.validate(
                    pattern("single_constraint", "1", StructuralAtom(kind)),
                    rules=invalid_rules,
                )

    def test_reference_requires_nonempty_title_pool(self):
        selected = pattern(
            "reference_only", 0, StructuralAtom("reference")
        )
        self.assertIsNone(self.validate(selected))
        with self.assertRaises(ValueError):
            self.validate(selected, pool=self.empty_title_pool)


class TagGroupSupportTests(BindabilityTestCase):
    def test_group_any_and_none_require_operator_support(self):
        any_only_rules = rehash_rules(
            self.rules,
            tag_groups=MappingProxyType(
                {"ANY_ONLY": group(("Female Harem",), ("any_of",), "ANY")}
            ),
        )
        none_only_rules = rehash_rules(
            self.rules,
            tag_groups=MappingProxyType(
                {"NONE_ONLY": group(("Male Harem",), ("none_of",), "NONE")}
            ),
        )
        with self.assertRaises(ValueError):
            self.validate(
                pattern("normalization", "1", StructuralAtom("tag_group_any")),
                rules=none_only_rules,
            )
        with self.assertRaises(ValueError):
            self.validate(
                pattern("normalization", "1", StructuralAtom("tag_group_none")),
                rules=any_only_rules,
            )

    def test_any_and_none_require_distinct_nonoverlapping_groups(self):
        selected = pattern(
            "normalization",
            "2",
            StructuralAtom("tag_group_any"),
            StructuralAtom("tag_group_none"),
        )
        # A and B have different identities but both expand to Female Harem.
        overlapping = rehash_rules(
            self.rules,
            tag_groups=MappingProxyType(
                {
                    "A": group(("Female Harem",), ("any_of",), "A"),
                    "B": group(("Female Harem",), ("none_of",), "B"),
                }
            ),
        )
        self.assertEqual(feasible_tag_group_bindings(selected, overlapping), ())
        with self.assertRaises(ValueError):
            self.validate(selected, rules=overlapping)

    def test_at_least_one_disjoint_assignment_makes_groups_bindable(self):
        selected = pattern(
            "normalization",
            "2",
            StructuralAtom("tag_group_any"),
            StructuralAtom("tag_group_none"),
        )
        disjoint = rehash_rules(
            self.rules,
            tag_groups=MappingProxyType(
                {
                    "A_ANY": group(("Female Harem",), ("any_of",), "A"),
                    "B_NONE": group(("Male Harem",), ("none_of",), "B"),
                    "C_NONE_OVERLAP": group(
                        ("Female Harem",), ("none_of",), "C"
                    ),
                }
            ),
        )
        self.assertEqual(
            feasible_tag_group_bindings(selected, disjoint),
            (TagGroupBindingPlan("A_ANY", "B_NONE"),),
        )
        self.assertIsNone(self.validate(selected, rules=disjoint))

    def test_support_order_is_canonical_by_group_name(self):
        selected = pattern(
            "normalization", "1", StructuralAtom("tag_group_any")
        )
        reordered_source = rehash_rules(
            self.rules,
            tag_groups=MappingProxyType(
                {
                    "Z_GROUP": group(("Male Harem",), ("any_of",), "Z"),
                    "A_GROUP": group(("Female Harem",), ("any_of",), "A"),
                }
            ),
        )
        self.assertEqual(
            feasible_tag_group_bindings(selected, reordered_source),
            (
                TagGroupBindingPlan("A_GROUP", None),
                TagGroupBindingPlan("Z_GROUP", None),
            ),
        )


class DirectTagJointCapacityTests(BindabilityTestCase):
    def test_direct_tag_without_group_uses_active_tag_capacity(self):
        selected = pattern(
            "same_field_logic", "3", set_atom("tag_set", "all_of", 3)
        )
        self.assertEqual(
            feasible_tag_group_bindings(selected, self.rules),
            (TagGroupBindingPlan(),),
        )
        self.assertIsNone(self.validate(selected))

    def test_synthetic_harem_group_reserves_all_active_tags(self):
        selected = pattern(
            "normalization",
            "2",
            set_atom("tag_set", "all_of", 1),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(feasible_tag_group_bindings(selected, self.rules), ())
        with self.assertRaises(ValueError):
            self.validate(selected)

    def test_same_operator_duplicate_prevention_reserves_group_expansion(self):
        selected = pattern(
            "normalization",
            "1",
            set_atom("tag_set", "any_of", 2),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(feasible_tag_group_bindings(selected, self.rules), ())

    def test_cross_operator_overlap_prevention_reserves_group_expansion(self):
        selected = pattern(
            "normalization",
            "2",
            set_atom("tag_set", "none_of", 1),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(feasible_tag_group_bindings(selected, self.rules), ())

    def test_approved_but_inactive_tag_is_not_used_for_capacity(self):
        self.assertIn(
            "Ensemble Cast", {tag.tag_name for tag in self.subset.tags}
        )
        self.assertNotIn("Ensemble Cast", self.rules.tags)
        selected = pattern(
            "normalization",
            "2",
            set_atom("tag_set", "all_of", 1),
            StructuralAtom("tag_group_none"),
        )
        with self.assertRaises(ValueError):
            self.validate(selected)

    def test_activating_one_approved_tag_creates_one_direct_capacity(self):
        activated = rehash_rules(
            self.rules,
            tags=self.rules.tags | {"Ensemble Cast"},
        )
        selected = pattern(
            "normalization",
            "2",
            set_atom("tag_set", "all_of", 1),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(
            feasible_tag_group_bindings(selected, activated),
            (TagGroupBindingPlan("HAREM", None),),
        )
        self.assertIsNone(self.validate(selected, rules=activated))


class PhaseBoundaryTests(unittest.TestCase):
    def test_runtime_has_no_rng_sampling_catalog_or_downstream_dependency(self):
        source = inspect.getsource(bindability_module)
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
        forbidden_imports = {
            "random",
            "anime_pref.sampling.categorical_value",
            "anime_pref.schemas.preference_query",
            "anime_pref.schemas.dataset_record",
            "anime_pref.data.anilist_client",
        }
        self.assertTrue(forbidden_imports.isdisjoint(imported))
        for forbidden_text in (
            "sample_direct_categorical_values",
            "sample_direct_numeric_range",
            "SemanticSpec",
            "DatasetRecord",
            "user_text",
            "retry",
            "while ",
        ):
            self.assertNotIn(forbidden_text, source)


if __name__ == "__main__":
    unittest.main()
