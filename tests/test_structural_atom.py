"""Acceptance tests for D3. Structural Atom Contract v0.1."""

from dataclasses import fields
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.structural_atom import StructuralAtom
import anime_pref.sampling.numeric_range as numeric_range_module
import anime_pref.sampling.operator_cardinality as operator_module
import anime_pref.sampling.structural_atom as structural_atom_module
from anime_pref.sampling.structural_atom import (
    STRUCTURAL_ATOM_KINDS,
    structural_atom_contribution,
    structural_constraint_count,
    validate_structural_atom,
)


def genre_set(operator="any_of", cardinality=2):
    return StructuralAtom(
        "genre_set",
        operator_plan=OperatorCardinalityPlan(operator, cardinality),
    )


def tag_set(operator="any_of", cardinality=2):
    return StructuralAtom(
        "tag_set",
        operator_plan=OperatorCardinalityPlan(operator, cardinality),
    )


class StructuralAtomValidationTests(unittest.TestCase):
    def test_accepts_every_frozen_atom_kind_with_its_required_payload(self):
        atoms = (
            genre_set(),
            tag_set(),
            StructuralAtom("year_range", range_pattern="min_only"),
            StructuralAtom("episodes_range", range_pattern="bounded_range"),
            StructuralAtom("format_any"),
            StructuralAtom("status_any"),
            StructuralAtom("tag_group_any"),
            StructuralAtom("tag_group_none"),
            StructuralAtom("reference"),
        )
        self.assertEqual({atom.kind for atom in atoms}, STRUCTURAL_ATOM_KINDS)
        for atom in atoms:
            with self.subTest(atom=atom):
                self.assertIsNone(validate_structural_atom(atom))

    def test_rejects_invalid_kind_including_tag_group_all(self):
        for atom in (StructuralAtom("unknown"), StructuralAtom("tag_group_all")):
            with self.subTest(atom=atom):
                with self.assertRaises(ValueError):
                    validate_structural_atom(atom)

    def test_set_atom_requires_generic_valid_operator_plan_only(self):
        invalid = (
            StructuralAtom("genre_set"),
            StructuralAtom(
                "tag_set",
                operator_plan=OperatorCardinalityPlan("any_of", 1),
            ),
            StructuralAtom(
                "genre_set",
                operator_plan=OperatorCardinalityPlan("all_of", 1),
                range_pattern="min_only",
            ),
        )
        for atom in invalid:
            with self.subTest(atom=atom):
                with self.assertRaises(ValueError):
                    validate_structural_atom(atom)

    def test_numeric_atom_requires_valid_pattern_and_forbids_operator(self):
        invalid = (
            StructuralAtom("year_range"),
            StructuralAtom("year_range", range_pattern="exact"),
            StructuralAtom(
                "episodes_range",
                operator_plan=OperatorCardinalityPlan("all_of", 1),
                range_pattern="max_only",
            ),
        )
        for atom in invalid:
            with self.subTest(atom=atom):
                with self.assertRaises(ValueError):
                    validate_structural_atom(atom)

    def test_payload_free_kinds_reject_operator_and_range_payloads(self):
        for kind in (
            "format_any",
            "status_any",
            "tag_group_any",
            "tag_group_none",
            "reference",
        ):
            for atom in (
                StructuralAtom(
                    kind,
                    operator_plan=OperatorCardinalityPlan("all_of", 1),
                ),
                StructuralAtom(kind, range_pattern="min_only"),
            ):
                with self.subTest(atom=atom):
                    with self.assertRaises(ValueError):
                        validate_structural_atom(atom)

    def test_rejects_non_atom_object(self):
        with self.assertRaises(ValueError):
            validate_structural_atom({"kind": "reference"})


class LocalContributionTests(unittest.TestCase):
    def test_genre_and_tag_sets_delegate_to_phase_c_truth_source(self):
        with patch.object(
            structural_atom_module,
            "constraint_contribution",
            wraps=operator_module.constraint_contribution,
        ) as contribution:
            self.assertEqual(structural_atom_contribution(genre_set("all_of", 3)), 3)
            self.assertEqual(structural_atom_contribution(tag_set("any_of", 3)), 1)
            self.assertEqual(structural_atom_contribution(tag_set("none_of", 2)), 2)
            self.assertEqual(contribution.call_count, 3)

    def test_numeric_ranges_delegate_to_d2_truth_source(self):
        with patch.object(
            structural_atom_module,
            "numeric_constraint_contribution",
            wraps=numeric_range_module.numeric_constraint_contribution,
        ) as contribution:
            self.assertEqual(
                structural_atom_contribution(
                    StructuralAtom("year_range", range_pattern="min_only")
                ),
                1,
            )
            self.assertEqual(
                structural_atom_contribution(
                    StructuralAtom("episodes_range", range_pattern="max_only")
                ),
                1,
            )
            self.assertEqual(
                structural_atom_contribution(
                    StructuralAtom("year_range", range_pattern="bounded_range")
                ),
                2,
            )
            self.assertGreaterEqual(contribution.call_count, 3)

    def test_format_status_group_and_reference_local_contributions(self):
        expected = {
            "format_any": 1,
            "status_any": 1,
            "tag_group_any": 1,
            "tag_group_none": 1,
            "reference": 0,
        }
        for kind, contribution in expected.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    structural_atom_contribution(StructuralAtom(kind)),
                    contribution,
                )


class AggregateContributionTests(unittest.TestCase):
    def test_direct_tag_any_alone_counts_one(self):
        self.assertEqual(structural_constraint_count((tag_set("any_of", 3),)), 1)

    def test_tag_group_any_alone_counts_one(self):
        self.assertEqual(
            structural_constraint_count((StructuralAtom("tag_group_any"),)),
            1,
        )

    def test_direct_and_group_tag_any_merge_into_one_final_clause(self):
        atoms = (
            tag_set("any_of", 3),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(structural_constraint_count(atoms), 1)

    def test_multiple_tag_any_sources_still_count_one(self):
        atoms = (
            tag_set("any_of", 2),
            StructuralAtom("tag_group_any"),
            StructuralAtom("tag_group_any"),
        )
        self.assertEqual(structural_constraint_count(atoms), 1)

    def test_direct_tag_none_and_group_none_remain_additive(self):
        atoms = (
            tag_set("none_of", 2),
            StructuralAtom("tag_group_none"),
        )
        self.assertEqual(structural_constraint_count(atoms), 3)

    def test_reference_does_not_change_mixed_hard_count(self):
        hard_atoms = (
            genre_set("all_of", 2),
            StructuralAtom("year_range", range_pattern="bounded_range"),
            StructuralAtom("format_any"),
        )
        with_reference = (*hard_atoms, StructuralAtom("reference"))
        self.assertEqual(structural_constraint_count(hard_atoms), 5)
        self.assertEqual(structural_constraint_count(with_reference), 5)

    def test_full_mixed_example_uses_pre_expansion_semantics(self):
        atoms = (
            genre_set("all_of", 2),             # +2
            tag_set("any_of", 3),               # combined TAG_ANY +1
            StructuralAtom("tag_group_any"),     # merged into TAG_ANY
            StructuralAtom("tag_group_none"),    # +1 concept, not leaf count
            StructuralAtom("year_range", range_pattern="bounded_range"),  # +2
            StructuralAtom("format_any"),        # +1
            StructuralAtom("status_any"),        # +1
            StructuralAtom("reference"),         # +0
        )
        self.assertEqual(structural_constraint_count(atoms), 8)

    def test_empty_sequence_counts_zero_and_bad_container_or_member_fails(self):
        self.assertEqual(structural_constraint_count(()), 0)
        for atoms in (None, "reference", ({"kind": "reference"},)):
            with self.subTest(atoms=atoms):
                with self.assertRaises(ValueError):
                    structural_constraint_count(atoms)


class StructuralAtomBoundaryTests(unittest.TestCase):
    def test_atom_has_no_concrete_value_or_downstream_fields(self):
        self.assertEqual(
            [field.name for field in fields(StructuralAtom)],
            ["kind", "operator_plan", "range_pattern"],
        )
        atom = genre_set()
        for forbidden in (
            "values",
            "genres",
            "tags",
            "minimum",
            "maximum",
            "group_name",
            "title",
            "semantic_spec",
            "dataset_record",
            "user_text",
        ):
            self.assertFalse(hasattr(atom, forbidden))

    def test_contract_module_has_no_rng_or_sampling_entrypoint(self):
        source = inspect.getsource(structural_atom_module)
        self.assertNotIn("import random", source)
        self.assertNotIn("from random", source)
        self.assertNotIn("def sample_", source)
        self.assertNotIn("anime_pref.schemas.preference_query", source)


if __name__ == "__main__":
    unittest.main()
