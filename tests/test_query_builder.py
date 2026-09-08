"""Learning tests for semantic specification -> deterministic Gold JSON v0.1."""

import copy
import json
from pathlib import Path
import sys
import tempfile
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

RULES_PATH = PROJECT_ROOT / "configs" / "domain_rules.v0.1.1.json"


class QueryBuilderTests(unittest.TestCase):
    def test_semantic_spec_defaults_are_explicitly_empty(self):
        spec = SemanticSpec()
        self.assertEqual(spec.genres, SetConstraintSpec())
        self.assertEqual(spec.year, RangeConstraintSpec())
        self.assertEqual(spec.reference_titles, ())

    def test_load_domain_rules_validates_approved_taxonomy(self):
        rules = load_domain_rules(RULES_PATH)
        self.assertEqual(rules.schema_version, "0.1.1")
        self.assertIn("Mystery", rules.genres)
        # frozen dataclass 不会自动冻结内部字典；加载器必须显式保护规则映射。
        with self.assertRaises(TypeError):
            rules.tag_groups["NEW_GROUP"] = ("Female Harem",)

    def test_load_domain_rules_rejects_non_object_and_normalized_duplicates(self):
        valid_rules = {
            "schema_version": "0.1.1",
            "taxonomy": {
                "genres": ["Mystery"],
                "tags": ["Female Harem"],
                "formats": ["TV"],
                "statuses": ["FINISHED"],
                "soft_preferences": [],
            },
            "tag_groups": {
                "HAREM": {
                    "tags": ["Female Harem"],
                    "allowed_operators": ["any_of", "none_of"],
                    "normalization_rule_id": "TEST_HAREM_EXPANSION",
                }
            },
            "numeric_rules": {
                "episodes": {"minimum": 1, "maximum": None},
                "year": {"minimum": None, "maximum": None},
            },
        }
        invalid_cases = {
            "non_object": [],
            "allowlist_duplicate_after_stripping": {
                **valid_rules,
                "taxonomy": {
                    **valid_rules["taxonomy"],
                    "formats": ["TV", " TV "],
                },
            },
            "group_duplicate_after_stripping": {
                **valid_rules,
                "tag_groups": {
                    "HAREM": {
                        "tags": ["Female Harem"],
                        "allowed_operators": ["any_of", "none_of"],
                        "normalization_rule_id": "TEST_HAREM_EXPANSION",
                    },
                    " HAREM ": {
                        "tags": ["Female Harem"],
                        "allowed_operators": ["any_of", "none_of"],
                        "normalization_rule_id": "TEST_SPACED_HAREM_EXPANSION",
                    },
                },
            },
            "group_tag_outside_allowlist": {
                **valid_rules,
                "tag_groups": {
                    "HAREM": {
                        "tags": ["Male Harem"],
                        "allowed_operators": ["any_of", "none_of"],
                        "normalization_rule_id": "TEST_HAREM_EXPANSION",
                    }
                },
            },
            "numeric_rules_extra_key": {
                **valid_rules,
                "numeric_rules": {
                    **valid_rules["numeric_rules"],
                    "score": {"minimum": None, "maximum": None},
                },
            },
            "numeric_rules_missing_episodes": {
                **valid_rules,
                "numeric_rules": {
                    "year": {"minimum": None, "maximum": None},
                },
            },
            "numeric_rules_missing_year": {
                **valid_rules,
                "numeric_rules": {
                    "episodes": {"minimum": 1, "maximum": None},
                },
            },
        }

        # 每个配置单独落到临时文件，覆盖 JSON 解析后的真实加载边界。
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for case_name, data in invalid_cases.items():
                with self.subTest(case=case_name):
                    path = root / f"{case_name}.json"
                    path.write_text(
                        json.dumps(data, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        load_domain_rules(path)

    def test_build_query_expands_harem_and_preserves_only_expressed_semantics(self):
        rules = load_domain_rules(RULES_PATH)
        spec = SemanticSpec(
            genres=SetConstraintSpec(any_of=("Sci-Fi", "Mystery")),
            tag_groups=SetConstraintSpec(none_of=("HAREM",)),
            year=RangeConstraintSpec(min=2010),
            reference_titles=("Steins;Gate",),
            unresolved_preferences=("节奏不要太拖沓",),
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
            "soft_preferences": [],
            "unresolved_preferences": ["节奏不要太拖沓"],
        }

        query = build_query(spec, rules)
        self.assertEqual(query, expected)
        self.assertNotIn("tag_groups", query)

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

        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(episodes=RangeConstraintSpec(max=True)),
                rules,
            )

        with self.assertRaises(ValueError):
            build_query({}, rules)

    def test_builder_reject_whitespace_and_rejects_redundant_group_expansion(self):
        rules = load_domain_rules(RULES_PATH)
        exact_text = "  节奏不要太拖沓  "
        #前后有空格直接报异常
        with self.assertRaises(ValueError):
            build_query(
                SemanticSpec(
                    unresolved_preferences=(exact_text,),
            ),
            rules,
        )
        query = build_query(
            SemanticSpec(
                formats=("TV", "MOVIE"),
                status=("RELEASING",),
            ),
            rules,
        )

        self.assertEqual(query["hard_constraints"]["formats"], ["MOVIE", "TV"])
        self.assertEqual(query["hard_constraints"]["status"], ["RELEASING"])

        with self.assertRaisesRegex(ValueError, "duplicates after group expansion"):
            build_query(
                SemanticSpec(
                    tags=SetConstraintSpec(none_of=("Female Harem",)),
                    tag_groups=SetConstraintSpec(none_of=("HAREM",)),
                ),
                rules,
            )

    def test_dumps_query_uses_canonical_unicode_json(self):
        rules = load_domain_rules(RULES_PATH)
        query = build_query(
            SemanticSpec(unresolved_preferences=("节奏紧凑",)),
            rules,
        )
        serialized = dumps_query(query)
        self.assertEqual(json.loads(serialized), query)
        self.assertIn("节奏紧凑", serialized)
        self.assertNotIn(": ", serialized)
        self.assertNotIn(", ", serialized)

    def test_dumps_query_rejects_invalid_structure_and_bounds(self):
        rules = load_domain_rules(RULES_PATH)
        query = build_query(SemanticSpec(), rules)

        extra_key = copy.deepcopy(query)
        extra_key["unexpected"] = []

        wrong_nested_type = copy.deepcopy(query)
        wrong_nested_type["hard_constraints"]["genres"]["any_of"] = ()

        boolean_bound = copy.deepcopy(query)
        boolean_bound["hard_constraints"]["year"]["min"] = True

        non_finite_bound = copy.deepcopy(query)
        non_finite_bound["hard_constraints"]["episodes"]["max"] = float("nan")

        for case_name, invalid_query in (
            ("extra_key", extra_key),
            ("wrong_nested_type", wrong_nested_type),
            ("boolean_bound", boolean_bound),
            ("non_finite_bound", non_finite_bound),
        ):
            with self.subTest(case=case_name):
                with self.assertRaises(ValueError):
                    dumps_query(invalid_query)

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

    def test_constraint_signature_handles_empty_and_rejects_bad_structure(self):
        rules = load_domain_rules(RULES_PATH)
        empty_query = build_query(SemanticSpec(), rules)
        unresolved_only_query = build_query(
            SemanticSpec(unresolved_preferences=("节奏紧凑",)),
            rules,
        )

        self.assertEqual(
            build_constraint_signature(empty_query),
            "NO_HARD_CONSTRAINT",
        )
        # Signature 只描述 hard constraints，不能被 unresolved preference 改变。
        self.assertEqual(
            build_constraint_signature(unresolved_only_query),
            "NO_HARD_CONSTRAINT",
        )

        missing_status = copy.deepcopy(empty_query)
        del missing_status["hard_constraints"]["status"]

        wrong_formats_type = copy.deepcopy(empty_query)
        wrong_formats_type["hard_constraints"]["formats"] = "TV"

        for case_name, invalid_query in (
            ("missing_status", missing_status),
            ("wrong_formats_type", wrong_formats_type),
        ):
            with self.subTest(case=case_name):
                with self.assertRaises(ValueError):
                    build_constraint_signature(invalid_query)


if __name__ == "__main__":
    unittest.main()
