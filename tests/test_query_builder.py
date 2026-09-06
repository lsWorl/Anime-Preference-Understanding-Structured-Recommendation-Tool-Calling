"""Learning tests for semantic specification -> deterministic Gold JSON v0.1."""

import json
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.constraint_signature import build_constraint_signature
from anime_pref.data.query_builder import build_query, dumps_query, load_domain_rules
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)

RULES_PATH = PROJECT_ROOT / "configs" / "domain_rules.v0.1.json"


class QueryBuilderTests(unittest.TestCase):
    def test_semantic_spec_defaults_are_explicitly_empty(self):
        spec = SemanticSpec()
        self.assertEqual(spec.genres, SetConstraintSpec())
        self.assertEqual(spec.year, RangeConstraintSpec())
        self.assertEqual(spec.reference_titles, ())

    @unittest.skip("TODO-11a: 完成 TODO-07 后启用")
    def test_load_domain_rules_validates_approved_taxonomy(self):
        rules = load_domain_rules(RULES_PATH)
        self.assertEqual(rules.schema_version, "0.1")
        self.assertIn("Mystery", rules.genres)
        self.assertEqual(
            rules.tag_groups["HAREM"],
            ("Female Harem", "Male Harem", "Mixed Gender Harem"),
        )
        self.assertTrue(set(rules.tag_groups["HAREM"]).issubset(rules.tags))

    @unittest.skip("TODO-11b: 完成 TODO-07..09 后启用")
    def test_build_query_expands_harem_and_preserves_only_expressed_semantics(self):
        rules = load_domain_rules(RULES_PATH)
        spec = SemanticSpec(
            genres=SetConstraintSpec(any_of=("Sci-Fi", "Mystery")),
            tag_groups=SetConstraintSpec(none_of=("HAREM",)),
            year=RangeConstraintSpec(min=2010),
            reference_titles=("Steins;Gate",),
            soft_preferences=("节奏不要太拖沓",),
        )

        expected = {
            "hard_constraints": {
                "genres": {
                    "all_of": [],
                    "any_of": ["Mystery", "Sci-Fi"],
                    "none_of": [],
                },
                "tags": {
                    "all_of": [],
                    "any_of": [],
                    "none_of": [
                        "Female Harem",
                        "Male Harem",
                        "Mixed Gender Harem",
                    ],
                },
                "year": {"min": 2010, "max": None},
                "episodes": {"min": None, "max": None},
                "formats": [],
                "status": [],
            },
            "reference_titles": ["Steins;Gate"],
            "soft_preferences": ["节奏不要太拖沓"],
            "unresolved_preferences": [],
        }

        query = build_query(spec, rules)
        self.assertEqual(query, expected)
        self.assertNotIn("tag_groups", query)
        self.assertEqual(json.loads(dumps_query(query)), expected)

    @unittest.skip("TODO-11c: 完成 TODO-08 后启用")
    def test_builder_rejects_unknown_taxonomy_and_conflicting_constraints(self):
        rules = load_domain_rules(RULES_PATH)

        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(genres=SetConstraintSpec(any_of=("Suspense",))),
                rules,
            )

        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(
                    genres=SetConstraintSpec(
                        all_of=("Mystery",),
                        none_of=("Mystery",),
                    )
                ),
                rules,
            )

        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(year=RangeConstraintSpec(min=2020, max=2010)),
                rules,
            )

    @unittest.skip("TODO-11d: 完成 TODO-10 后启用")
    def test_constraint_signature_uses_fixed_structural_order(self):
        rules = load_domain_rules(RULES_PATH)
        query = build_query(
            SemanticSpec(
                genres=SetConstraintSpec(any_of=("Mystery",)),
                tags=SetConstraintSpec(all_of=("Female Harem",)),
                episodes=RangeConstraintSpec(max=24),
            ),
            rules,
        )
        self.assertEqual(
            build_constraint_signature(query),
            "GENRE_ANY + TAG_ALL + EPISODE_MAX",
        )


if __name__ == "__main__":
    unittest.main()
