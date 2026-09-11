"""Regression tests for rules identity and DatasetRecord provenance integration."""

import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.dataset_record_builder import (
    build_dataset_record,
    validate_dataset_record,
)
from anime_pref.data.query_builder import load_domain_rules
from anime_pref.data.rules_identity import (
    domain_rules_sha256,
    dumps_canonical_rules,
    validate_executable_rules_identity,
)
from anime_pref.data.tag_subset import executable_tag_subset_sha256
from anime_pref.schemas.preference_query import SemanticSpec, SetConstraintSpec
from anime_pref.schemas.taxonomy import ExecutableTagSpec, ExecutableTagSubset


def make_approved_subset() -> ExecutableTagSubset:
    """Return a synthetic approved pool; never use its identity in production."""
    return ExecutableTagSubset(
        subset_version="synthetic-approved-tags-v0.1",
        derived_from_snapshot_hash="a" * 64,
        tags=(
            ExecutableTagSpec(101, "Ensemble Cast", "Cast-Main Cast", (), False, False),
            ExecutableTagSpec(202, "Female Harem", "Theme-Romance", (), False, False),
            ExecutableTagSpec(203, "Male Harem", "Theme-Romance", (), False, False),
            ExecutableTagSpec(204, "Mixed Gender Harem", "Theme-Romance", (), False, False),
        ),
    )


def make_rules_document(subset: ExecutableTagSubset) -> dict:
    """Build a synthetic config with three active tags from a four-tag approved pool."""
    return {
        "rules_version": "synthetic-domain-rules-v0.1",
        "schema_version": "0.1.1",
        "executable_subset_version": subset.subset_version,
        "executable_subset_hash": executable_tag_subset_sha256(subset),
        "taxonomy": {
            "genres": ["Mystery", "Sci-Fi"],
            "tags": ["Female Harem", "Male Harem", "Mixed Gender Harem"],
            "formats": ["MOVIE", "TV"],
            "statuses": ["FINISHED", "RELEASING"],
            "soft_preferences": [],
        },
        "tag_groups": {
            "HAREM": {
                "tags": ["Female Harem", "Male Harem", "Mixed Gender Harem"],
                "allowed_operators": ["any_of", "none_of"],
                "normalization_rule_id": "HAREM_EXPANSION_V0_1_1",
            }
        },
        "numeric_rules": {
            "episodes": {"minimum": 1, "maximum": None},
            "year": {"minimum": 1900, "maximum": 2100},
        },
    }


def load_rules_document(document: dict):
    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "rules.json"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return load_domain_rules(path)


class RulesIdentityContractTests(unittest.TestCase):
    def test_active_tags_may_be_a_strict_subset_of_approved_tags(self):
        subset = make_approved_subset()
        rules = load_rules_document(make_rules_document(subset))
        self.assertIsNone(validate_executable_rules_identity(rules, subset))

        missing_approved_tag = replace(subset, tags=subset.tags[1:])
        rules_with_unapproved_active_tag = copy.deepcopy(
            make_rules_document(missing_approved_tag)
        )
        rules_with_unapproved_active_tag["taxonomy"]["tags"].append("Ensemble Cast")
        rules_with_unapproved_active_tag = load_rules_document(
            rules_with_unapproved_active_tag
        )
        with self.assertRaises(ValueError):
            validate_executable_rules_identity(
                rules_with_unapproved_active_tag,
                missing_approved_tag,
            )

    def test_group_target_must_be_in_active_rules_tags(self):
        subset = make_approved_subset()
        document = make_rules_document(subset)
        document["tag_groups"]["CAST"] = {
            "tags": ["Ensemble Cast"],
            "allowed_operators": ["any_of"],
            "normalization_rule_id": "CAST_EXPANSION_TEST",
        }
        with self.assertRaises(ValueError):
            load_rules_document(document)

    def test_rules_hash_is_canonical_and_sensitive_only_to_contract_content(self):
        subset = make_approved_subset()
        first_document = make_rules_document(subset)
        reordered = copy.deepcopy(first_document)
        reordered["taxonomy"]["genres"].reverse()
        reordered["taxonomy"]["tags"].reverse()
        reordered["taxonomy"]["formats"].reverse()
        reordered["tag_groups"]["HAREM"]["tags"].reverse()
        reordered["tag_groups"]["HAREM"]["allowed_operators"].reverse()

        first = load_rules_document(first_document)
        second = load_rules_document(reordered)
        self.assertEqual(dumps_canonical_rules(first), dumps_canonical_rules(second))
        self.assertEqual(domain_rules_sha256(first), domain_rules_sha256(second))
        self.assertEqual(first.rules_hash, domain_rules_sha256(first))

        changed_document = copy.deepcopy(first_document)
        changed_document["numeric_rules"]["year"]["maximum"] = 2099
        changed = load_rules_document(changed_document)
        self.assertNotEqual(domain_rules_sha256(first), domain_rules_sha256(changed))

        with tempfile.TemporaryDirectory() as temporary_directory:
            compact_path = Path(temporary_directory) / "compact.json"
            pretty_path = Path(temporary_directory) / "pretty.json"
            compact_path.write_text(json.dumps(first_document), encoding="utf-8")
            pretty_path.write_text(
                json.dumps(first_document, indent=4), encoding="utf-8"
            )
            self.assertEqual(
                load_domain_rules(compact_path).rules_hash,
                load_domain_rules(pretty_path).rules_hash,
            )

    def test_record_keeps_and_validates_rules_and_subset_identity(self):
        subset = make_approved_subset()
        rules = load_rules_document(make_rules_document(subset))
        record = build_dataset_record(
            semantic_spec=SemanticSpec(
                tag_groups=SetConstraintSpec(any_of=("HAREM",)),
            ),
            rules=rules,
            executable_subset=subset,
            dataset_version="synthetic-dataset-v0.1",
            semantic_family="tag-group-any",
            generation_family="curated-template",
            template_id="template-identity-001",
            seed=1,
            user_text="想看后宫动画。",
        )
        self.assertEqual(record.executable_subset_version, subset.subset_version)
        self.assertEqual(
            record.executable_subset_hash,
            executable_tag_subset_sha256(subset),
        )
        self.assertEqual(record.rules_version, rules.rules_version)
        self.assertEqual(record.rules_hash, rules.rules_hash)
        self.assertIsNone(validate_dataset_record(record, rules, subset))

        for field_name, bad_value in (
            ("executable_subset_version", "tampered-subset-version"),
            ("executable_subset_hash", "0" * 64),
            ("rules_version", "tampered-rules-version"),
            ("rules_hash", "0" * 64),
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    validate_dataset_record(
                        replace(record, **{field_name: bad_value}),
                        rules,
                        subset,
                    )

    def test_rules_hash_change_changes_complete_record_sample_id(self):
        subset = make_approved_subset()
        first_document = make_rules_document(subset)
        changed_document = copy.deepcopy(first_document)
        changed_document["numeric_rules"]["year"]["maximum"] = 2099
        first_rules = load_rules_document(first_document)
        changed_rules = load_rules_document(changed_document)

        common = {
            "semantic_spec": SemanticSpec(),
            "executable_subset": subset,
            "dataset_version": "synthetic-dataset-v0.1",
            "semantic_family": "empty",
            "generation_family": "curated-template",
            "template_id": "template-identity-002",
            "seed": 2,
            "user_text": "请推荐一部动画。",
        }
        first = build_dataset_record(rules=first_rules, **common)
        changed = build_dataset_record(rules=changed_rules, **common)
        self.assertNotEqual(first_rules.rules_hash, changed_rules.rules_hash)
        self.assertNotEqual(first.sample_id, changed.sample_id)


if __name__ == "__main__":
    unittest.main()
