"""Regression tests for the implemented Schema Contract v0.1.1 behavior."""

import copy
import json
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.constraint_signature import build_constraint_signature
from anime_pref.data.query_builder import build_query, dumps_query, load_domain_rules
from anime_pref.data.query_validation import canonicalize_query, validate_query
from anime_pref.schemas.dataset_record import DatasetRecordSpec
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)

RULES_V011_PATH = PROJECT_ROOT / "tests" / "fixtures" / "domain_rules.synthetic.v0.1.json"


class SchemaContractV011Tests(unittest.TestCase):
    def test_dataset_record_reserves_provenance_without_split(self):
        field_names = set(DatasetRecordSpec.__dataclass_fields__)
        expected = {
            "sample_id",
            "schema_version",
            "dataset_version",
            "executable_subset_version",
            "executable_subset_hash",
            "rules_version",
            "rules_hash",
            "semantic_spec",
            "gold_query",
            "constraint_signature",
            "constraint_count",
            "semantic_family",
            "generation_family",
            "template_id",
            "normalization_rule_ids",
            "seed",
            "user_text",
            "paraphrase_model",
            "prompt_version",
        }
        self.assertEqual(field_names, expected)
        self.assertNotIn("split", field_names)


    def test_rules_declare_harem_allowed_operators_and_empty_soft_taxonomy(self):
        rules = load_domain_rules(RULES_V011_PATH)
        harem = rules.tag_groups["HAREM"]
        self.assertEqual(harem.allowed_operators, frozenset({"any_of", "none_of"}))
        self.assertEqual(
            harem.tags,
            ("Female Harem", "Male Harem", "Mixed Gender Harem"),
        )
        self.assertEqual(harem.normalization_rule_id, "HAREM_EXPANSION_V0_1_1")
        self.assertEqual(rules.soft_preferences, frozenset())
        self.assertEqual(rules.episodes.minimum, 1)
        self.assertIsNone(rules.episodes.maximum)
        self.assertEqual(rules.year.minimum, 1900)
        self.assertEqual(rules.year.maximum, 2100)

    def test_year_sanity_bounds_are_versioned_validity_rules(self):
        rules = load_domain_rules(RULES_V011_PATH)

        for year in (1900, 2100):
            with self.subTest(valid_year=year):
                build_query(
                    SemanticSpec(year=RangeConstraintSpec(min=year, max=year)),
                    rules,
                )

        for year in (1899, 2101):
            with self.subTest(invalid_year=year):
                with self.assertRaises(ValueError):
                    build_query(
                        SemanticSpec(year=RangeConstraintSpec(min=year)),
                        rules,
                    )

    def test_harem_all_is_rejected_but_any_and_none_are_allowed(self):
        rules = load_domain_rules(RULES_V011_PATH)

        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(tag_groups=SetConstraintSpec(all_of=("HAREM",))),
                rules,
            )

        positive = build_query(
            SemanticSpec(tag_groups=SetConstraintSpec(any_of=("HAREM",))),
            rules,
        )
        negative = build_query(
            SemanticSpec(tag_groups=SetConstraintSpec(none_of=("HAREM",))),
            rules,
        )
        expected_tags = ["Female Harem", "Male Harem", "Mixed Gender Harem"]
        self.assertEqual(positive["hard_constraints"]["tags"]["any_of"], expected_tags)
        self.assertEqual(negative["hard_constraints"]["tags"]["none_of"], expected_tags)

    def test_semantic_spec_rejects_outer_whitespace_unknown_soft_and_zero_episodes(self):
        rules = load_domain_rules(RULES_V011_PATH)
        invalid_specs = (
            SemanticSpec(genres=SetConstraintSpec(any_of=(" Mystery",))),
            SemanticSpec(reference_titles=("Steins;Gate ",)),
            SemanticSpec(soft_preferences=("tight_pacing",)),
        )
        for spec in invalid_specs:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    build_query(spec, rules)

        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(episodes=RangeConstraintSpec(min=0)),
                rules,
            )

        unresolved = build_query(
            SemanticSpec(unresolved_preferences=("节奏不要太拖",)),
            rules,
        )
        self.assertEqual(unresolved["unresolved_preferences"], ["节奏不要太拖"])

    def test_leading_and_trailing_whitespace_refuse(self):
        rules = load_domain_rules(RULES_V011_PATH)
        valid_query = build_query(SemanticSpec(), rules)
        for invalid_text in (" leading", "trailing "):
            with self.subTest(value=invalid_text):
                invalid = copy.deepcopy(valid_query)
                invalid["unresolved_preferences"] = [invalid_text]

                with self.assertRaises(ValueError):
                    validate_query(invalid)

                with self.assertRaises(ValueError):
                    dumps_query(invalid)

                with self.assertRaises(ValueError):
                    build_constraint_signature(invalid)

    def test_validation_ignores_key_and_set_value_order_then_canonicalizes(self):
        rules = load_domain_rules(RULES_V011_PATH)
        canonical = build_query(
            SemanticSpec(genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi"))),
            rules,
        )
        reordered = {
            "unresolved_preferences": [],
            "soft_preferences": [],
            "reference_titles": [],
            "hard_constraints": copy.deepcopy(canonical["hard_constraints"]),
        }
        reordered["hard_constraints"]["genres"]["any_of"] = ["Sci-Fi", "Mystery"]

        self.assertIsNone(validate_query(reordered))
        self.assertEqual(canonicalize_query(reordered), canonical)

    def test_serializer_canonicalizes_order_instead_of_rejecting_it(self):
        rules = load_domain_rules(RULES_V011_PATH)
        canonical = build_query(SemanticSpec(), rules)
        reordered = {
            "soft_preferences": [],
            "unresolved_preferences": [],
            "hard_constraints": canonical["hard_constraints"],
            "reference_titles": [],
        }

        serialized = dumps_query(reordered)
        self.assertEqual(json.loads(serialized), canonical)
        self.assertTrue(serialized.startswith('{"hard_constraints":'))


    def test_signature_reuses_validation_but_ignores_non_hard_fields(self):
        rules = load_domain_rules(RULES_V011_PATH)
        query = build_query(
            SemanticSpec(unresolved_preferences=("氛围独特",)),
            rules,
        )
        self.assertEqual(build_constraint_signature(query), "NO_HARD_CONSTRAINT")

        invalid = copy.deepcopy(query)
        invalid["hard_constraints"]["episodes"]["min"] = 0
        with self.assertRaises(ValueError):
            build_constraint_signature(invalid)


if __name__ == "__main__":
    unittest.main()
