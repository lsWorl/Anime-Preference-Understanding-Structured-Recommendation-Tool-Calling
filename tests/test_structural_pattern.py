"""Acceptance tests for D4. Structural Pattern Eligibility Contract v0.1."""

import ast
from dataclasses import fields
import inspect
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.sampling.family_complexity import FAMILY_COMPLEXITY_COMPATIBILITY
import anime_pref.sampling.structural_pattern as structural_pattern_module
from anime_pref.sampling.structural_atom import (
    STRUCTURAL_ATOM_KIND_ORDER,
    structural_constraint_count,
)
from anime_pref.sampling.structural_pattern import (
    enumerate_eligible_structural_patterns,
    validate_structural_pattern_plan,
)


def set_atom(kind="genre_set", operator="all_of", cardinality=1):
    return StructuralAtom(
        kind,
        operator_plan=OperatorCardinalityPlan(operator, cardinality),
    )


def pattern(family, bucket, *atoms):
    return StructuralPatternPlan(family, bucket, tuple(atoms))


class StructuralPatternValidationTests(unittest.TestCase):
    def test_exact_buckets_zero_through_four_match_actual_count(self):
        examples = (
            pattern("reference_only", 0, StructuralAtom("reference")),
            pattern("single_constraint", "1", StructuralAtom("format_any")),
            pattern(
                "cross_field_composition",
                "2",
                set_atom(),
                StructuralAtom("year_range", range_pattern="min_only"),
            ),
            pattern("same_field_logic", "3", set_atom(cardinality=3)),
            pattern(
                "cross_field_composition",
                "4",
                set_atom(cardinality=2),
                StructuralAtom("year_range", range_pattern="bounded_range"),
            ),
        )
        for candidate in examples:
            with self.subTest(candidate=candidate):
                self.assertIsNone(validate_structural_pattern_plan(candidate))

    def test_five_plus_accepts_exact_counts_above_five(self):
        exact_six = pattern(
            "cross_field_composition",
            "5_plus",
            set_atom("genre_set", "all_of", 3),
            set_atom("tag_set", "all_of", 3),
        )
        exact_seven = pattern(
            "cross_field_composition",
            "5_plus",
            set_atom("genre_set", "all_of", 3),
            set_atom("tag_set", "all_of", 2),
            StructuralAtom("year_range", range_pattern="bounded_range"),
        )
        self.assertEqual(structural_constraint_count(exact_six.atoms), 6)
        self.assertEqual(structural_constraint_count(exact_seven.atoms), 7)
        validate_structural_pattern_plan(exact_six)
        validate_structural_pattern_plan(exact_seven)

    def test_bucket_mismatch_is_rejected_including_five_plus_below_five(self):
        invalid = (
            pattern("same_field_logic", "2", set_atom()),
            pattern(
                "cross_field_composition",
                "5_plus",
                set_atom(),
                StructuralAtom("format_any"),
            ),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_atoms_must_be_tuple_and_each_atom_must_be_valid(self):
        malformed = (
            StructuralPatternPlan("single_constraint", "1", [StructuralAtom("format_any")]),
            pattern("single_constraint", "1", {"kind": "format_any"}),
        )
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_noncanonical_atom_order_is_rejected_without_repair(self):
        candidate = pattern(
            "cross_field_composition",
            "2",
            StructuralAtom("status_any"),
            set_atom("genre_set"),
        )
        original = candidate.atoms
        with self.assertRaises(ValueError):
            validate_structural_pattern_plan(candidate)
        self.assertIs(candidate.atoms, original)

    def test_every_schema_and_group_slot_is_unique(self):
        duplicate_examples = (
            (set_atom(), set_atom()),
            (
                StructuralAtom("year_range", range_pattern="min_only"),
                StructuralAtom("year_range", range_pattern="max_only"),
            ),
            (StructuralAtom("format_any"), StructuralAtom("format_any")),
            (StructuralAtom("reference"), StructuralAtom("reference")),
            (StructuralAtom("tag_group_any"), StructuralAtom("tag_group_any")),
            (StructuralAtom("tag_group_none"), StructuralAtom("tag_group_none")),
        )
        for atoms in duplicate_examples:
            candidate = pattern("normalization", "1", *atoms)
            with self.subTest(atoms=atoms):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_empty_atoms_count_zero_but_match_no_current_family(self):
        self.assertEqual(structural_constraint_count(()), 0)
        for family, buckets in FAMILY_COMPLEXITY_COMPATIBILITY.items():
            for bucket in buckets:
                with self.subTest(family=family, bucket=bucket):
                    with self.assertRaises(ValueError):
                        validate_structural_pattern_plan(pattern(family, bucket))


class FamilyEligibilityTests(unittest.TestCase):
    def test_single_constraint_requires_one_count_one_direct_atom(self):
        validate_structural_pattern_plan(
            pattern("single_constraint", "1", set_atom("tag_set", "any_of", 2))
        )
        invalid = (
            pattern("single_constraint", "1", set_atom(cardinality=2)),
            pattern("single_constraint", "1", StructuralAtom("reference")),
            pattern("single_constraint", "1", StructuralAtom("tag_group_none")),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_same_field_logic_allows_only_one_genre_or_tag_set(self):
        validate_structural_pattern_plan(
            pattern("same_field_logic", "2", set_atom("tag_set", "none_of", 2))
        )
        invalid = (
            pattern("same_field_logic", "1", StructuralAtom("format_any")),
            pattern("same_field_logic", "1", set_atom(), StructuralAtom("status_any")),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_cross_field_requires_two_fields_and_forbids_reference_or_groups(self):
        valid = pattern(
            "cross_field_composition",
            "2",
            set_atom(),
            StructuralAtom("status_any"),
        )
        validate_structural_pattern_plan(valid)
        invalid = (
            pattern("cross_field_composition", "2", set_atom(cardinality=2)),
            pattern("cross_field_composition", "2", set_atom(), StructuralAtom("reference")),
            pattern(
                "cross_field_composition",
                "2",
                set_atom(),
                StructuralAtom("tag_group_none"),
            ),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_normalization_requires_group_and_may_carry_reference(self):
        candidate = pattern(
            "normalization",
            "2",
            set_atom(),
            StructuralAtom("tag_group_none"),
            StructuralAtom("reference"),
        )
        self.assertEqual(structural_constraint_count(candidate.atoms), 2)
        validate_structural_pattern_plan(candidate)
        with self.assertRaises(ValueError):
            validate_structural_pattern_plan(
                pattern("normalization", "1", StructuralAtom("format_any"))
            )

    def test_normalization_can_have_abstract_any_and_none_group_slots(self):
        candidate = pattern(
            "normalization",
            "2",
            StructuralAtom("tag_group_any"),
            StructuralAtom("tag_group_none"),
        )
        validate_structural_pattern_plan(candidate)

    def test_direct_and_group_tag_any_merge_when_matching_bucket(self):
        candidate = pattern(
            "normalization",
            "1",
            set_atom("tag_set", "any_of", 3),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(structural_constraint_count(candidate.atoms), 1)
        validate_structural_pattern_plan(candidate)

    def test_reference_only_is_exactly_one_reference_not_empty(self):
        validate_structural_pattern_plan(
            pattern("reference_only", 0, StructuralAtom("reference"))
        )
        for candidate in (
            pattern("reference_only", 0),
            pattern("reference_only", 0, StructuralAtom("reference"), StructuralAtom("format_any")),
        ):
            with self.assertRaises(ValueError):
                validate_structural_pattern_plan(candidate)

    def test_reference_composition_requires_reference_and_hard_but_no_group(self):
        valid = pattern(
            "reference_composition",
            "1",
            StructuralAtom("format_any"),
            StructuralAtom("reference"),
        )
        validate_structural_pattern_plan(valid)
        invalid = (
            pattern("reference_composition", "1", StructuralAtom("format_any")),
            pattern("reference_composition", "1", StructuralAtom("reference")),
            pattern(
                "reference_composition",
                "1",
                StructuralAtom("tag_group_any"),
                StructuralAtom("reference"),
            ),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)

    def test_family_priority_rejects_group_or_reference_in_lower_priority_family(self):
        invalid = (
            pattern("single_constraint", "1", StructuralAtom("tag_group_any")),
            pattern("same_field_logic", "1", set_atom(), StructuralAtom("reference")),
            pattern(
                "cross_field_composition",
                "2",
                set_atom(),
                StructuralAtom("tag_group_none"),
            ),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_plan(candidate)


class EligibilityEnumerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spaces = {
            (family, bucket): enumerate_eligible_structural_patterns(
                FamilyComplexityPlan(family, bucket)
            )
            for family, buckets in FAMILY_COMPLEXITY_COMPATIBILITY.items()
            for bucket in buckets
        }

    def test_every_frozen_family_complexity_pair_has_candidates(self):
        for pair, candidates in self.spaces.items():
            with self.subTest(pair=pair):
                self.assertTrue(candidates)

    def test_enumeration_is_deterministic_and_contains_no_duplicates(self):
        plan = FamilyComplexityPlan("normalization", "5_plus")
        first = self.spaces[(plan.semantic_family, plan.complexity_bucket)]
        second = enumerate_eligible_structural_patterns(plan)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(first)))

    def test_every_enumerated_plan_is_canonical_and_publicly_valid(self):
        kind_index = {kind: i for i, kind in enumerate(STRUCTURAL_ATOM_KIND_ORDER)}
        for pair, candidates in self.spaces.items():
            for candidate in candidates:
                validate_structural_pattern_plan(candidate)
                indexes = [kind_index[atom.kind] for atom in candidate.atoms]
                self.assertEqual(indexes, sorted(indexes))
                self.assertEqual(len(indexes), len(set(indexes)))

    def test_five_plus_spaces_include_counts_greater_than_five(self):
        for family in (
            "cross_field_composition",
            "normalization",
            "reference_composition",
        ):
            counts = {
                structural_constraint_count(candidate.atoms)
                for candidate in self.spaces[(family, "5_plus")]
            }
            with self.subTest(family=family):
                self.assertTrue(all(count >= 5 for count in counts))
                self.assertTrue(any(count > 5 for count in counts))

    def test_reference_and_normalization_enumeration_obey_priority(self):
        for (family, _), candidates in self.spaces.items():
            for candidate in candidates:
                kinds = {atom.kind for atom in candidate.atoms}
                has_group = bool(kinds & {"tag_group_any", "tag_group_none"})
                has_reference = "reference" in kinds
                if has_group:
                    self.assertEqual(family, "normalization")
                elif has_reference:
                    self.assertIn(family, {"reference_only", "reference_composition"})

    def test_enumerator_rejects_invalid_phase_b_plan(self):
        with self.assertRaises(ValueError):
            enumerate_eligible_structural_patterns(
                FamilyComplexityPlan("cross_field_composition", "1")
            )


class PhaseBoundaryTests(unittest.TestCase):
    def test_output_contract_has_only_value_free_d4_fields(self):
        self.assertEqual(
            [field.name for field in fields(StructuralPatternPlan)],
            ["semantic_family", "complexity_bucket", "atoms"],
        )
        for forbidden in (
            "values",
            "minimum",
            "maximum",
            "group_name",
            "reference_title",
            "semantic_spec",
            "dataset_record",
            "user_text",
            "probability",
            "weight",
        ):
            self.assertFalse(hasattr(StructuralPatternPlan, forbidden))

    def test_module_has_no_rng_value_sampler_or_downstream_imports(self):
        source = inspect.getsource(structural_pattern_module)
        tree = ast.parse(source)
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        self.assertNotIn("random", imported_modules)
        self.assertNotIn("anime_pref.sampling.categorical_value", imported_modules)
        self.assertNotIn("anime_pref.sampling.numeric_range", imported_modules)
        self.assertNotIn("anime_pref.schemas.preference_query", imported_modules)
        self.assertNotIn("anime_pref.schemas.dataset_record", imported_modules)
        self.assertFalse(any(name.startswith("sample_") for name in dir(structural_pattern_module)))


if __name__ == "__main__":
    unittest.main()
