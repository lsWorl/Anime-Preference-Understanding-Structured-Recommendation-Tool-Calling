"""Acceptance tests for F1-Pilot dataset realization and record generation."""

import ast
from collections import Counter
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.pilot_dataset import (
    audit_pilot_records,
    audit_pilot_split_hygiene,
    build_human_challenge_cases,
    challenge_cases_to_jsonl,
    generate_pilot_records,
    load_pilot_pattern_manifest,
    realize_user_text,
    records_to_jsonl,
    render_pilot_audit_markdown,
    split_pilot_records,
    validate_pilot_split_hygiene,
    write_pilot_artifacts,
)
from anime_pref.data.query_builder import build_query, load_domain_rules
from anime_pref.data.reference_title_pool import load_reference_title_pool
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.domain_bindability import (
    validate_structural_pattern_bindability,
)
import anime_pref.data.pilot_dataset as pilot_module


FIXTURES = PROJECT_ROOT / "tests/fixtures"
MANIFEST_PATH = PROJECT_ROOT / "configs/pilot_pattern_manifest.v0.1.json"
OUTPUT_DIR = PROJECT_ROOT / "data/pilot"


class PilotDatasetTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_pilot_pattern_manifest(MANIFEST_PATH)
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
        cls.records = generate_pilot_records(
            cls.manifest, cls.config, cls.rules, cls.subset, cls.title_pool
        )
        cls.splits = split_pilot_records(cls.manifest, cls.records)
        cls.audit = audit_pilot_records(cls.records)
        cls.split_hygiene = audit_pilot_split_hygiene(cls.splits)
        cls.challenges = build_human_challenge_cases(cls.rules)


class ManifestTests(PilotDatasetTestCase):
    def test_manifest_load_is_deterministic_and_has_240_explicit_seeds(self):
        self.assertEqual(
            self.manifest,
            load_pilot_pattern_manifest(MANIFEST_PATH),
        )
        self.assertEqual(sum(len(case.seeds) for case in self.manifest.cases), 240)
        self.assertEqual(len(self.manifest.cases), 24)
        self.assertEqual(self.manifest.dataset_version, "anime-pref-pilot-v0.1")

    def test_manifest_covers_all_families_and_primary_fields(self):
        families = {
            case.structural_pattern.semantic_family for case in self.manifest.cases
        }
        self.assertEqual(
            families,
            {
                "single_constraint",
                "same_field_logic",
                "cross_field_composition",
                "normalization",
                "reference_only",
                "reference_composition",
            },
        )
        kinds = {
            atom.kind
            for case in self.manifest.cases
            for atom in case.structural_pattern.atoms
        }
        self.assertTrue(
            {
                "genre_set",
                "tag_set",
                "year_range",
                "episodes_range",
                "format_any",
                "status_any",
                "reference",
            }
            <= kinds
        )

    def test_every_reviewed_pattern_is_e1_bindable(self):
        for case in self.manifest.cases:
            with self.subTest(case=case.case_id):
                self.assertIsNone(
                    validate_structural_pattern_bindability(
                        case.structural_pattern,
                        self.config,
                        self.rules,
                        self.subset,
                        self.title_pool,
                    )
                )


class RealizationTests(PilotDatasetTestCase):
    def realize(self, spec):
        return realize_user_text(
            spec,
            "direct_explicit_v1",
            "example__direct_explicit_v1",
        )

    def test_realization_is_deterministic(self):
        spec = SemanticSpec(
            genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")),
            year=RangeConstraintSpec(min=2020),
        )
        self.assertEqual(self.realize(spec), self.realize(spec))

    def test_any_language_explicitly_uses_or_not_and(self):
        text = self.realize(
            SemanticSpec(
                genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")),
                tags=SetConstraintSpec(any_of=("Female Harem",)),
                tag_groups=SetConstraintSpec(any_of=("HAREM",)),
            )
        )
        self.assertIn("“Mystery”或“Sci-Fi”", text)
        self.assertIn("“Female Harem”或后宫类型", text)
        self.assertNotIn("“Mystery”和“Sci-Fi”", text)

    def test_all_and_none_language_are_explicit(self):
        text = self.realize(
            SemanticSpec(
                genres=SetConstraintSpec(all_of=("Mystery", "Sci-Fi")),
                tag_groups=SetConstraintSpec(none_of=("HAREM",)),
            )
        )
        self.assertIn("同时包含“Mystery”和“Sci-Fi”", text)
        self.assertIn("排除后宫类型", text)

    def test_group_text_keeps_concept_and_hides_expansion_leaves(self):
        text = self.realize(
            SemanticSpec(tag_groups=SetConstraintSpec(any_of=("HAREM",)))
        )
        self.assertIn("后宫类型", text)
        for leaf in ("Female Harem", "Male Harem", "Mixed Gender Harem"):
            self.assertNotIn(leaf, text)

    def test_numeric_wording_is_inclusive_and_unambiguous(self):
        text = self.realize(
            SemanticSpec(
                year=RangeConstraintSpec(min=2010, max=2020),
                episodes=RangeConstraintSpec(max=24),
            )
        )
        self.assertIn("2010到2020年之间（含边界）", text)
        self.assertIn("最多24集", text)

    def test_reference_only_text_and_gold_add_no_hidden_constraints(self):
        spec = SemanticSpec(reference_titles=("Steins;Gate",))
        text = self.realize(spec)
        gold = build_query(spec, self.rules)
        self.assertIn("《Steins;Gate》", text)
        hard = gold["hard_constraints"]
        self.assertEqual(hard["genres"], {"all_of": [], "any_of": [], "none_of": []})
        self.assertEqual(hard["tags"], {"all_of": [], "any_of": [], "none_of": []})


class RecordGenerationTests(PilotDatasetTestCase):
    def test_e3_and_record_builder_are_reused_for_every_record(self):
        with patch.object(
            pilot_module,
            "sample_semantic_spec_from_pattern",
            wraps=pilot_module.sample_semantic_spec_from_pattern,
        ) as e3, patch.object(
            pilot_module,
            "build_dataset_record",
            wraps=pilot_module.build_dataset_record,
        ) as builder, patch.object(
            pilot_module,
            "validate_dataset_record",
            wraps=pilot_module.validate_dataset_record,
        ) as validator:
            records = generate_pilot_records(
                self.manifest,
                self.config,
                self.rules,
                self.subset,
                self.title_pool,
            )
        self.assertEqual(len(records), 240)
        self.assertEqual(e3.call_count, 240)
        self.assertEqual(builder.call_count, 240)
        self.assertEqual(validator.call_count, 240)

    def test_every_record_validates_and_has_no_paraphrase_metadata(self):
        from anime_pref.data.dataset_record_builder import validate_dataset_record

        for record in self.records:
            validate_dataset_record(record, self.rules, self.subset)
            self.assertIsNone(record.paraphrase_model)
            self.assertIsNone(record.prompt_version)

    def test_sample_ids_are_unique(self):
        sample_ids = [record.sample_id for record in self.records]
        self.assertEqual(len(sample_ids), len(set(sample_ids)))

    def test_second_generation_is_byte_identical(self):
        second = generate_pilot_records(
            self.manifest,
            self.config,
            self.rules,
            self.subset,
            self.title_pool,
        )
        self.assertEqual(records_to_jsonl(self.records), records_to_jsonl(second))

    def test_checked_in_all_jsonl_matches_current_generation(self):
        self.assertEqual(
            (OUTPUT_DIR / "pilot_all.v0.1.jsonl").read_text(encoding="utf-8"),
            records_to_jsonl(self.records),
        )


class SplitAndAuditTests(PilotDatasetTestCase):
    def test_split_counts_union_and_intersections(self):
        self.assertEqual(
            {name: len(values) for name, values in self.splits.items()},
            {"train": 180, "validation": 30, "test": 30},
        )
        all_ids = {record.sample_id for record in self.records}
        split_sets = [
            {record.sample_id for record in self.splits[name]}
            for name in ("train", "validation", "test")
        ]
        self.assertEqual(set().union(*split_sets), all_ids)
        self.assertFalse(split_sets[0] & split_sets[1])
        self.assertFalse(split_sets[0] & split_sets[2])
        self.assertFalse(split_sets[1] & split_sets[2])

    def test_exact_template_id_does_not_cross_splits(self):
        owners = {}
        for split_name, records in self.splits.items():
            for record in records:
                owners.setdefault(record.template_id, set()).add(split_name)
        self.assertTrue(all(len(splits) == 1 for splits in owners.values()))

    def test_exact_examples_do_not_overlap_across_splits(self):
        for pair, counts in self.split_hygiene["pairwise"].items():
            with self.subTest(pair=pair):
                self.assertEqual(counts["exact_user_text"], 0)
                self.assertEqual(counts["user_text_plus_gold"], 0)

    def test_validation_and_test_have_no_internal_exact_pair_duplicates(self):
        for split in ("validation", "test"):
            with self.subTest(split=split):
                counts = self.split_hygiene["within_split"][split]
                self.assertEqual(counts["exact_user_text"], 0)
                self.assertEqual(counts["user_text_plus_gold"], 0)
        # Training duplicates remain visible and are not silently removed.
        self.assertGreater(
            self.split_hygiene["within_split"]["train"]["user_text_plus_gold"],
            0,
        )

    def test_semantic_spec_overlap_is_reported_but_not_rejected(self):
        hygiene = {
            section: {
                owner: dict(counts)
                for owner, counts in values.items()
            }
            for section, values in self.split_hygiene.items()
        }
        hygiene["pairwise"]["train<->validation"]["semantic_spec"] = 99
        self.assertIsNone(validate_pilot_split_hygiene(hygiene))

    def test_split_hygiene_rejects_cross_split_exact_example(self):
        contaminated = dict(self.splits)
        contaminated["validation"] = (
            self.splits["train"][0],
            *self.splits["validation"],
        )
        hygiene = audit_pilot_split_hygiene(contaminated)
        with self.assertRaisesRegex(ValueError, "user_text leakage"):
            validate_pilot_split_hygiene(hygiene)

    def test_audit_totals_match_records_and_reports_duplicates(self):
        self.assertEqual(self.audit["total_records"], len(self.records))
        self.assertEqual(
            sum(self.audit["semantic_family_counts"].values()), len(self.records)
        )
        self.assertEqual(
            sum(self.audit["constraint_count_counts"].values()), len(self.records)
        )
        self.assertEqual(self.audit["duplicate_counts"]["sample_id"], 0)
        self.assertIn("exact_user_text", self.audit["duplicate_counts"])
        self.assertIn("user_text_plus_gold", self.audit["duplicate_counts"])
        self.assertIn("semantic_spec", self.audit["duplicate_counts"])

    def test_rendered_audit_and_artifacts_are_deterministic(self):
        split_counts = {name: len(values) for name, values in self.splits.items()}
        markdown = render_pilot_audit_markdown(
            self.audit,
            self.split_hygiene,
            split_counts,
            len(self.challenges),
        )
        self.assertIn("Split hygiene: cross-split overlap", markdown)
        self.assertIn("Split hygiene: within-split duplicate excess", markdown)
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            for directory in (Path(first_dir), Path(second_dir)):
                write_pilot_artifacts(
                    directory,
                    directory / "pilot_dataset_audit_v0.1.md",
                    self.records,
                    self.splits,
                    self.challenges,
                    markdown,
                )
            first = {path.name: path.read_bytes() for path in Path(first_dir).iterdir()}
            second = {path.name: path.read_bytes() for path in Path(second_dir).iterdir()}
            self.assertEqual(first, second)


class ChallengeAndBoundaryTests(PilotDatasetTestCase):
    def test_human_challenge_set_has_12_cases_and_is_not_training_records(self):
        self.assertEqual(len(self.challenges), 12)
        self.assertTrue(all(set(case) == {"challenge_id", "user_text", "gold_query"} for case in self.challenges))
        training_texts = {record.user_text for record in self.records}
        self.assertTrue(all(case["user_text"] not in training_texts for case in self.challenges))
        self.assertEqual(
            len(challenge_cases_to_jsonl(self.challenges).splitlines()), 12
        )

    def test_jsonl_is_complete_and_parseable(self):
        lines = records_to_jsonl(self.records).splitlines()
        self.assertEqual(len(lines), 240)
        parsed = [json.loads(line) for line in lines]
        self.assertEqual(len({record["sample_id"] for record in parsed}), 240)

    def test_module_has_no_llm_api_master_sampler_or_training_dependency(self):
        source = inspect.getsource(pilot_module)
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
        forbidden = {
            "openai",
            "requests",
            "anime_pref.data.anilist_client",
            "anime_pref.sampling.structural_signature_sampler",
            "anime_pref.sampling.mechanics_sampler",
            "anime_pref.sampling.domain_conditioned_support",
            "anime_pref.training",
        }
        self.assertTrue(forbidden.isdisjoint(imports))
        for text in (
            "sample_structural_signature",
            "sample_mechanics_pattern",
            "E2B",
            "E2C",
            "paraphrase_model=\"",
        ):
            self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
