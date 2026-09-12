"""Acceptance tests for D5A structural-signature selection policy v0.1."""

import ast
from dataclasses import fields, replace
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.structural_signature import (
    StructuralPatternSelectionPolicySpec,
    StructuralSignature,
    StructuralSignatureWeightSpec,
)
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.family_complexity import FAMILY_COMPLEXITY_COMPATIBILITY
import anime_pref.sampling.structural_signature as signature_module
from anime_pref.sampling.structural_signature import (
    canonical_relative_weight,
    dumps_structural_pattern_selection_policy,
    enumerate_eligible_structural_signatures,
    load_structural_pattern_selection_policy,
    signature_probabilities,
    structural_pattern_selection_policy_sha256,
    structural_signature,
    validate_structural_pattern_selection_policy,
    validate_structural_pattern_selection_policy_spec,
    validate_structural_signature,
)

SAMPLER_PATH = PROJECT_ROOT / "tests/fixtures/semantic_sampler.synthetic.v0.1.json"
POLICY_PATH = (
    PROJECT_ROOT
    / "tests/fixtures/structural_pattern_policy.synthetic.v0.1.json"
)


def genre_atom(operator="all_of", cardinality=1):
    return StructuralAtom(
        "genre_set",
        operator_plan=OperatorCardinalityPlan(operator, cardinality),
    )


def rehash(policy, *, entries=None, **changes):
    """Build a valid identity after an intentional admitted-content change."""
    if entries is not None:
        entries = tuple(sorted(entries, key=signature_module._entry_sort_key))
        changes["signature_entries"] = entries
    provisional = replace(policy, policy_hash="", **changes)
    return replace(
        provisional,
        policy_hash=structural_pattern_selection_policy_sha256(provisional),
    )


class StructuralSignatureTests(unittest.TestCase):
    def test_signature_extracts_only_canonical_atom_kinds(self):
        pattern = StructuralPatternPlan(
            "cross_field_composition",
            "2",
            (
                genre_atom(),
                StructuralAtom("year_range", range_pattern="min_only"),
            ),
        )
        self.assertEqual(
            structural_signature(pattern),
            StructuralSignature(("genre_set", "year_range")),
        )

    def test_signature_ignores_operator_cardinality(self):
        first = StructuralPatternPlan("single_constraint", "1", (genre_atom(),))
        second = StructuralPatternPlan(
            "single_constraint",
            "1",
            (genre_atom("any_of", 3),),
        )
        self.assertEqual(structural_signature(first), structural_signature(second))

    def test_signature_ignores_numeric_range_pattern(self):
        first = StructuralPatternPlan(
            "cross_field_composition",
            "2",
            (genre_atom(), StructuralAtom("year_range", range_pattern="min_only")),
        )
        second = StructuralPatternPlan(
            "cross_field_composition",
            "3",
            (
                genre_atom(),
                StructuralAtom("year_range", range_pattern="bounded_range"),
            ),
        )
        self.assertEqual(structural_signature(first), structural_signature(second))

    def test_signature_validator_rejects_empty_duplicate_unknown_and_bad_order(self):
        invalid = (
            StructuralSignature(()),
            StructuralSignature(("genre_set", "genre_set")),
            StructuralSignature(("unknown",)),
            StructuralSignature(("reference", "genre_set")),
            StructuralSignature(["genre_set"]),
        )
        for signature in invalid:
            with self.subTest(signature=signature):
                with self.assertRaises(ValueError):
                    validate_structural_signature(signature)

    def test_extraction_rejects_malformed_pattern_without_sorting(self):
        malformed = StructuralPatternPlan(
            "cross_field_composition",
            "2",
            (StructuralAtom("format_any"), genre_atom()),
        )
        with self.assertRaises(ValueError):
            structural_signature(malformed)

    def test_eligible_signature_enumeration_is_deterministic_and_deduplicated(self):
        family_plan = FamilyComplexityPlan("single_constraint", "1")
        first = enumerate_eligible_structural_signatures(family_plan)
        second = enumerate_eligible_structural_signatures(family_plan)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(first)))
        self.assertEqual(len(first), 6)
        self.assertEqual(first[0], StructuralSignature(("genre_set",)))

    def test_reference_only_has_exactly_reference_signature(self):
        self.assertEqual(
            enumerate_eligible_structural_signatures(
                FamilyComplexityPlan("reference_only", 0)
            ),
            (StructuralSignature(("reference",)),),
        )


class PolicyLoaderAndIdentityTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_structural_pattern_selection_policy(POLICY_PATH)

    def _write_json(self, document, directory, name="policy.json"):
        path = Path(directory) / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def test_strict_loader_builds_immutable_contract_and_hash(self):
        self.assertIsInstance(self.policy.signature_entries, tuple)
        self.assertEqual(
            self.policy.policy_version,
            "offline-synthetic-structural-signature-policy-v0.1",
        )
        self.assertEqual(len(self.policy.policy_hash), 64)
        self.assertEqual(
            self.policy.policy_hash,
            structural_pattern_selection_policy_sha256(self.policy),
        )
        validate_structural_pattern_selection_policy_spec(self.policy)

    def test_loader_rejects_missing_unknown_and_wrong_shapes(self):
        base = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        variants = []
        missing = dict(base)
        missing.pop("policy_version")
        variants.append(missing)
        unknown = dict(base)
        unknown["policy_hash"] = "not accepted in source JSON"
        variants.append(unknown)
        wrong_entries = dict(base)
        wrong_entries["signature_entries"] = {}
        variants.append(wrong_entries)
        bad_entry = json.loads(json.dumps(base))
        bad_entry["signature_entries"][0]["extra"] = True
        variants.append(bad_entry)

        with TemporaryDirectory() as directory:
            for index, document in enumerate(variants):
                with self.subTest(index=index):
                    path = self._write_json(document, directory, f"{index}.json")
                    with self.assertRaises(ValueError):
                        load_structural_pattern_selection_policy(path)

    def test_loader_rejects_noncanonical_entry_and_atom_order(self):
        base = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        reversed_entries = json.loads(json.dumps(base))
        reversed_entries["signature_entries"] = list(
            reversed(reversed_entries["signature_entries"])
        )
        bad_atoms = json.loads(json.dumps(base))
        target = bad_atoms["signature_entries"][7]
        target["atom_kinds"] = list(reversed(target["atom_kinds"]))

        with TemporaryDirectory() as directory:
            for index, document in enumerate((reversed_entries, bad_atoms)):
                path = self._write_json(document, directory, f"{index}.json")
                with self.assertRaises(ValueError):
                    load_structural_pattern_selection_policy(path)

    def test_finite_positive_weights_required_but_sum_one_is_not(self):
        self.assertEqual(
            [entry.weight for entry in self.policy.signature_entries[:3]],
            [3, 2, 1],
        )
        self.assertNotEqual(sum(entry.weight for entry in self.policy.signature_entries), 1)

        first = self.policy.signature_entries[0]
        for value in (0, -1, True, "1", float("inf"), float("nan")):
            entries = (replace(first, weight=value), *self.policy.signature_entries[1:])
            malformed = replace(self.policy, signature_entries=entries)
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_structural_pattern_selection_policy_spec(malformed)

    def test_duplicate_policy_identity_is_rejected(self):
        first = self.policy.signature_entries[0]
        malformed = replace(
            self.policy,
            signature_entries=(first, first, *self.policy.signature_entries[1:]),
        )
        with self.assertRaises(ValueError):
            validate_structural_pattern_selection_policy_spec(malformed)

    def test_hash_is_deterministic_and_one_equals_one_point_zero(self):
        again = load_structural_pattern_selection_policy(POLICY_PATH)
        self.assertEqual(self.policy.policy_hash, again.policy_hash)
        float_entries = tuple(
            replace(entry, weight=float(entry.weight))
            for entry in self.policy.signature_entries
        )
        float_policy = replace(self.policy, signature_entries=float_entries, policy_hash="")
        self.assertEqual(
            structural_pattern_selection_policy_sha256(self.policy),
            structural_pattern_selection_policy_sha256(float_policy),
        )

    def test_lossy_large_integer_is_rejected_before_hash_identity(self):
        exactly_representable = 9007199254740992
        lossy_collision = 9007199254740993
        self.assertEqual(
            canonical_relative_weight(exactly_representable),
            float(exactly_representable),
        )
        with self.assertRaises(ValueError):
            canonical_relative_weight(lossy_collision)
        with self.assertRaises(ValueError):
            canonical_relative_weight(10**10000)

        first = self.policy.signature_entries[0]
        safe_entries = (
            replace(first, weight=exactly_representable),
            *self.policy.signature_entries[1:],
        )
        safe_policy = rehash(self.policy, entries=safe_entries)
        validate_structural_pattern_selection_policy_spec(safe_policy)

        unsafe_entries = (
            replace(first, weight=lossy_collision),
            *self.policy.signature_entries[1:],
        )
        with self.assertRaises(ValueError):
            rehash(self.policy, entries=unsafe_entries)

    def test_hash_changes_for_each_admitted_content_family(self):
        changed_version = rehash(self.policy, policy_version="changed-v0.1")
        changed_sampler = rehash(self.policy, sampler_version="changed-sampler-v0.1")
        changed_entries = list(self.policy.signature_entries)
        changed_entries[0] = replace(changed_entries[0], weight=30)
        changed_weight = rehash(self.policy, entries=changed_entries)
        hashes = {
            self.policy.policy_hash,
            changed_version.policy_hash,
            changed_sampler.policy_hash,
            changed_weight.policy_hash,
        }
        self.assertEqual(len(hashes), 4)

    def test_tampered_hash_is_rejected(self):
        malformed = replace(self.policy, policy_hash="0" * 64)
        with self.assertRaises(ValueError):
            validate_structural_pattern_selection_policy_spec(malformed)


class PolicyBindingAndProbabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_structural_pattern_selection_policy(POLICY_PATH)
        cls.config = load_sampler_config(SAMPLER_PATH)

    def test_synthetic_policy_binds_and_covers_every_b_context(self):
        validate_structural_pattern_selection_policy(self.policy, self.config)
        configured_contexts = {
            (entry.semantic_family, entry.complexity_bucket)
            for entry in self.policy.signature_entries
        }
        expected_contexts = {
            (family, bucket)
            for family, buckets in FAMILY_COMPLEXITY_COMPATIBILITY.items()
            for bucket in buckets
        }
        self.assertEqual(configured_contexts, expected_contexts)

    def test_configured_signature_must_exist_in_d4_space(self):
        entries = [
            entry
            for entry in self.policy.signature_entries
            if not (
                entry.semantic_family == "cross_field_composition"
                and entry.complexity_bucket == "2"
            )
        ]
        entries.append(
            StructuralSignatureWeightSpec(
                "cross_field_composition",
                "2",
                ("format_any", "reference"),
                1,
            )
        )
        malformed = rehash(self.policy, entries=entries)
        with self.assertRaises(ValueError):
            validate_structural_pattern_selection_policy(malformed, self.config)

    def test_missing_d4_signatures_are_intentionally_disabled(self):
        enabled = {
            entry.atom_kinds
            for entry in self.policy.signature_entries
            if entry.semantic_family == "single_constraint"
            and entry.complexity_bucket == "1"
        }
        mechanically_eligible = {
            signature.atom_kinds
            for signature in enumerate_eligible_structural_signatures(
                FamilyComplexityPlan("single_constraint", "1")
            )
        }
        self.assertLess(enabled, mechanically_eligible)
        validate_structural_pattern_selection_policy(self.policy, self.config)

    def test_every_b_context_requires_one_enabled_signature(self):
        entries = tuple(
            entry
            for entry in self.policy.signature_entries
            if not (
                entry.semantic_family == "reference_only"
                and entry.complexity_bucket == 0
            )
        )
        incomplete = rehash(self.policy, entries=entries)
        with self.assertRaises(ValueError):
            validate_structural_pattern_selection_policy(incomplete, self.config)

    def test_sampler_version_must_match_phase_a(self):
        mismatched = rehash(self.policy, sampler_version="other-sampler-v0.1")
        with self.assertRaises(ValueError):
            validate_structural_pattern_selection_policy(mismatched, self.config)

    def test_probabilities_normalize_only_within_selected_context(self):
        single = signature_probabilities(
            self.policy,
            FamilyComplexityPlan("single_constraint", "1"),
        )
        cross = signature_probabilities(
            self.policy,
            FamilyComplexityPlan("cross_field_composition", "2"),
        )
        self.assertTrue(math.isclose(sum(single.values()), 1.0))
        self.assertTrue(math.isclose(sum(cross.values()), 1.0))
        self.assertEqual(list(single.values()), [0.5, 1 / 3, 1 / 6])
        self.assertEqual(list(cross.values()), [0.2, 0.8])

    def test_within_context_positive_scaling_preserves_probabilities(self):
        family_plan = FamilyComplexityPlan("single_constraint", "1")
        baseline = signature_probabilities(self.policy, family_plan)
        entries = tuple(
            replace(entry, weight=entry.weight * 10)
            if entry.semantic_family == "single_constraint"
            else entry
            for entry in self.policy.signature_entries
        )
        scaled = rehash(self.policy, entries=entries)
        self.assertEqual(baseline, signature_probabilities(scaled, family_plan))
        # Scale invariance belongs to the normalized probability distribution.
        # Raw admitted weights remain policy content and therefore change hash.
        self.assertNotEqual(self.policy.policy_hash, scaled.policy_hash)

    def test_changing_other_context_does_not_change_selected_distribution(self):
        family_plan = FamilyComplexityPlan("single_constraint", "1")
        baseline = signature_probabilities(self.policy, family_plan)
        entries = tuple(
            replace(entry, weight=entry.weight * 100)
            if entry.semantic_family == "cross_field_composition"
            else entry
            for entry in self.policy.signature_entries
        )
        changed = rehash(self.policy, entries=entries)
        self.assertEqual(baseline, signature_probabilities(changed, family_plan))

    def test_reference_only_probability_is_ordinary_singleton_normalization(self):
        probabilities = signature_probabilities(
            self.policy,
            FamilyComplexityPlan("reference_only", 0),
        )
        self.assertEqual(probabilities, {StructuralSignature(("reference",)): 1.0})


class PhaseBoundaryTests(unittest.TestCase):
    def test_runtime_contracts_contain_no_values_or_downstream_payload(self):
        self.assertEqual(
            [field.name for field in fields(StructuralSignature)],
            ["atom_kinds"],
        )
        self.assertEqual(
            [field.name for field in fields(StructuralSignatureWeightSpec)],
            ["semantic_family", "complexity_bucket", "atom_kinds", "weight"],
        )
        self.assertEqual(
            [field.name for field in fields(StructuralPatternSelectionPolicySpec)],
            ["policy_version", "sampler_version", "signature_entries", "policy_hash"],
        )

    def test_module_has_no_rng_selection_domain_or_downstream_dependencies(self):
        source = Path(signature_module.__file__).read_text(encoding="utf-8")
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
            "anime_pref.data.query_builder",
            "anime_pref.schemas.taxonomy",
            "anime_pref.sampling.categorical_value",
            "anime_pref.sampling.numeric_range",
            "anime_pref.schemas.preference_query",
            "anime_pref.schemas.dataset_record",
        }
        self.assertTrue(forbidden_imports.isdisjoint(imported))
        self.assertFalse(any(name.startswith("sample_") for name in dir(signature_module)))
        self.assertNotIn("random.choice", source)


if __name__ == "__main__":
    unittest.main()
