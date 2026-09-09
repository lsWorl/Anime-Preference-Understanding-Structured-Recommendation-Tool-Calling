"""Executable TODO contract for domain validation and DatasetRecord Builder v0.1."""

import copy
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.dataset_record_builder import (
    build_dataset_record,
    collect_normalization_rule_ids,
    count_hard_semantic_clauses,
    validate_dataset_record,
)
from anime_pref.data.domain_validation import validate_query_domain
from anime_pref.data.query_builder import build_query, load_domain_rules
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)

RULES_PATH = PROJECT_ROOT / "configs" / "domain_rules.v0.1.1.json"


class DatasetRecordBuilderTests(unittest.TestCase):
    def test_structural_and_domain_validity_are_separate(self):
        rules = load_domain_rules(RULES_PATH)
        query = build_query(SemanticSpec(), rules)
        self.assertIsNone(validate_query_domain(query, rules))

        invalid_queries = {}
        for name, field, value in (
            ("genre", "genres", "Not In Rules"),
            ("tag", "tags", "Not In Rules"),
        ):
            invalid = copy.deepcopy(query)
            invalid["hard_constraints"][field]["any_of"] = [value]
            invalid_queries[name] = invalid

        for name, field, value in (
            ("format", "formats", "NOT_A_FORMAT"),
            ("status", "status", "NOT_A_STATUS"),
        ):
            invalid = copy.deepcopy(query)
            invalid["hard_constraints"][field] = [value]
            invalid_queries[name] = invalid

        invalid_soft = copy.deepcopy(query)
        invalid_soft["soft_preferences"] = ["tight_pacing"]
        invalid_queries["soft_preference"] = invalid_soft

        invalid_year = copy.deepcopy(query)
        invalid_year["hard_constraints"]["year"]["min"] = 1899
        invalid_queries["year_sanity"] = invalid_year

        from anime_pref.data.query_validation import validate_query_structure

        for case_name, invalid_domain in invalid_queries.items():
            with self.subTest(case=case_name):
                # 这些 query 的 Schema 结构合法，但 domain vocabulary/rule 非法。
                self.assertIsNone(validate_query_structure(invalid_domain))
                with self.assertRaises(ValueError):
                    validate_query_domain(invalid_domain, rules)

    def test_constraint_count_uses_pre_expansion_semantic_clauses(self):
        spec = SemanticSpec(
            genres=SetConstraintSpec(
                all_of=("Action", "Adventure"),
                any_of=("Comedy", "Drama"),
                none_of=("Fantasy",),
            ),
            tag_groups=SetConstraintSpec(none_of=("HAREM",)),
            year=RangeConstraintSpec(min=2000, max=2020),
            episodes=RangeConstraintSpec(max=24),
            formats=("TV", "MOVIE"),
            status=("FINISHED", "RELEASING"),
            reference_titles=("Steins;Gate",),
            unresolved_preferences=("氛围独特",),
        )

        # 2 genre all + 1 genre any-clause + 1 genre exclusion
        # + 1 HAREM concept + 2 year bounds + 1 episode bound
        # + 1 format OR-clause + 1 status OR-clause = 10.
        self.assertEqual(count_hard_semantic_clauses(spec), 10)

    @unittest.skip("TODO-25c: 完成 TODO-21 后启用")
    def test_normalization_rule_ids_are_pre_expansion_provenance(self):
        rules = load_domain_rules(RULES_PATH)
        spec = SemanticSpec(tag_groups=SetConstraintSpec(any_of=("HAREM",)))

        self.assertEqual(
            collect_normalization_rule_ids(spec, rules),
            ("HAREM_EXPANSION_V0_1_1",),
        )

    @unittest.skip("TODO-25d: 完成 TODO-22/23 后启用")
    def test_record_build_is_deterministic_and_keeps_full_provenance(self):
        rules = load_domain_rules(RULES_PATH)
        kwargs = {
            "semantic_spec": SemanticSpec(
                genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")),
                tag_groups=SetConstraintSpec(none_of=("HAREM",)),
                year=RangeConstraintSpec(min=2010),
                episodes=RangeConstraintSpec(max=24),
                formats=("TV",),
            ),
            "rules": rules,
            "dataset_version": "dataset-v0.1",
            "semantic_family": "genre-year-format-harem",
            "generation_family": "curated-template",
            "template_id": "template-001",
            "seed": 7,
            "user_text": "想看2010年后的科幻或悬疑TV动画，不要后宫。",
        }

        first = build_dataset_record(**kwargs)
        second = build_dataset_record(**kwargs)

        self.assertEqual(first, second)
        self.assertRegex(first.sample_id, r"^sample_[0-9a-f]{64}$")
        self.assertEqual(first.schema_version, rules.schema_version)
        self.assertEqual(first.constraint_count, 5)
        self.assertEqual(
            first.normalization_rule_ids,
            ("HAREM_EXPANSION_V0_1_1",),
        )
        self.assertIsNone(validate_dataset_record(first, rules))

    @unittest.skip("TODO-25e: 完成 TODO-24 后启用")
    def test_record_validation_rejects_inconsistent_derived_fields(self):
        rules = load_domain_rules(RULES_PATH)
        record = build_dataset_record(
            semantic_spec=SemanticSpec(
                genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")),
            ),
            rules=rules,
            dataset_version="dataset-v0.1",
            semantic_family="genre-any",
            generation_family="curated-template",
            template_id="template-002",
            seed=11,
            user_text="想看悬疑或者科幻动画。",
        )

        from dataclasses import replace

        invalid_records = (
            replace(record, constraint_count=record.constraint_count + 1),
            replace(record, constraint_signature="TAG_ANY"),
            replace(record, sample_id="sample_" + "0" * 64),
            replace(record, normalization_rule_ids=("UNUSED_RULE",)),
        )
        for invalid in invalid_records:
            with self.subTest(field_values=invalid):
                with self.assertRaises(ValueError):
                    validate_dataset_record(invalid, rules)


if __name__ == "__main__":
    unittest.main()
