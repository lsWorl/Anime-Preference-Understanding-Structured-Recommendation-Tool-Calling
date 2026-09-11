"""Regression tests for taxonomy snapshots and reviewed executable subsets."""

import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.query_builder import load_domain_rules
from anime_pref.data.tag_subset import (
    build_executable_subset_manifest,
    build_executable_tag_subset,
    dumps_executable_tag_subset,
    executable_tag_subset_sha256,
    load_tag_audit,
    load_executable_tag_subset,
    validate_domain_rule_tag_targets,
    validate_tag_audit,
    write_executable_subset_bundle,
)
from anime_pref.data.taxonomy_client import TAXONOMY_QUERY
from anime_pref.data.taxonomy_client import fetch_anilist_taxonomy
from anime_pref.data.taxonomy_snapshot import (
    build_canonical_taxonomy_snapshot,
    build_taxonomy_snapshot_manifest,
    taxonomy_snapshot_sha256,
    write_taxonomy_snapshot_bundle,
)
from anime_pref.schemas.taxonomy import (
    ExecutableTagSpec,
    TagAuditRecordSpec,
)

RULES_PATH = PROJECT_ROOT / "configs" / "domain_rules.v0.1.1.json"

SOURCE_PAYLOAD = {
    "data": {
        "GenreCollection": ["Sci-Fi", "Mystery"],
        "MediaTagCollection": [
            {
                "id": 203,
                "name": "Male Harem",
                "description": "Male harem taxonomy description.",
                "category": "Theme-Romance",
                "isGeneralSpoiler": False,
                "isAdult": False,
                "ignoredFutureField": "must not enter canonical snapshot",
            },
            {
                "id": 202,
                "name": "Female Harem",
                "description": "Female harem taxonomy description.",
                "category": "Theme-Romance",
                "isGeneralSpoiler": False,
                "isAdult": False,
            },
            {
                "id": 204,
                "name": "Mixed Gender Harem",
                "description": None,
                "category": "Theme-Romance",
                "isGeneralSpoiler": False,
                "isAdult": False,
            },
            {
                "id": 101,
                "name": "Ensemble Cast",
                "description": "Large main cast.",
                "category": "Cast-Main Cast",
                "isGeneralSpoiler": False,
                "isAdult": False,
            },
        ],
    }
}


def make_audit(snapshot_hash: str) -> tuple[TagAuditRecordSpec, ...]:
    return (
        TagAuditRecordSpec(
            tag_id=202,
            tag_name="Female Harem",
            category="Theme-Romance",
            approved=True,
            reason="Approved HAREM normalization target.",
            aliases=(),
            is_general_spoiler=False,
            is_adult=False,
            source_snapshot_hash=snapshot_hash,
        ),
        TagAuditRecordSpec(
            tag_id=203,
            tag_name="Male Harem",
            category="Theme-Romance",
            approved=True,
            reason="Approved HAREM normalization target.",
            aliases=(),
            is_general_spoiler=False,
            is_adult=False,
            source_snapshot_hash=snapshot_hash,
        ),
        TagAuditRecordSpec(
            tag_id=204,
            tag_name="Mixed Gender Harem",
            category="Theme-Romance",
            approved=True,
            reason="Approved HAREM normalization target.",
            aliases=(),
            is_general_spoiler=False,
            is_adult=False,
            source_snapshot_hash=snapshot_hash,
        ),
        TagAuditRecordSpec(
            tag_id=101,
            tag_name="Ensemble Cast",
            category="Cast-Main Cast",
            approved=False,
            reason="Example reviewed rejection; requires separate domain decision.",
            aliases=(),
            is_general_spoiler=False,
            is_adult=False,
            source_snapshot_hash=snapshot_hash,
        ),
    )


class TaxonomySnapshotTests(unittest.TestCase):
    def test_taxonomy_query_uses_global_identity_fields_not_media_rank(self):
        for field in (
            "GenreCollection",
            "MediaTagCollection",
            "id",
            "name",
            "description",
            "category",
            "isGeneralSpoiler",
            "isAdult",
        ):
            self.assertIn(field, TAXONOMY_QUERY)
        self.assertNotIn("rank", TAXONOMY_QUERY)

    def test_taxonomy_fetch_returns_source_response_and_rejects_graphql_errors(self):
        class FakeResponse:
            def __init__(self, payload: dict) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(self.payload).encode("utf-8")

        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(SOURCE_PAYLOAD),
        ):
            self.assertEqual(fetch_anilist_taxonomy(), SOURCE_PAYLOAD)

        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"errors": [{"message": "bad query"}]}),
        ):
            with self.assertRaises(RuntimeError):
                fetch_anilist_taxonomy()

    def test_canonical_snapshot_and_hash_ignore_input_order(self):
        first = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        reversed_source = copy.deepcopy(SOURCE_PAYLOAD)
        reversed_source["data"]["GenreCollection"].reverse()
        reversed_source["data"]["MediaTagCollection"].reverse()
        second = build_canonical_taxonomy_snapshot(reversed_source)

        self.assertEqual(first, second)
        self.assertEqual(
            taxonomy_snapshot_sha256(first), taxonomy_snapshot_sha256(second)
        )
        self.assertEqual(first.genres, ("Mystery", "Sci-Fi"))
        self.assertEqual([tag.id for tag in first.tags], [101, 202, 203, 204])

        changed_source = copy.deepcopy(SOURCE_PAYLOAD)
        changed_source["data"]["MediaTagCollection"][0]["description"] += " changed"
        changed = build_canonical_taxonomy_snapshot(changed_source)
        self.assertNotEqual(
            taxonomy_snapshot_sha256(first),
            taxonomy_snapshot_sha256(changed),
        )

    def test_snapshot_manifest_and_bundle_are_consistent(self):
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        manifest = build_taxonomy_snapshot_manifest(
            snapshot,
            fetched_at_utc="2026-09-09T12:00:00Z",
        )
        self.assertEqual(manifest.genre_count, 2)
        self.assertEqual(manifest.tag_count, 4)
        self.assertEqual(manifest.canonical_sha256, taxonomy_snapshot_sha256(snapshot))

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "snapshot"
            written = write_taxonomy_snapshot_bundle(
                SOURCE_PAYLOAD,
                output_dir=output,
                fetched_at_utc="2026-09-09T12:00:00Z",
            )
            self.assertEqual(written, manifest)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"source.json", "canonical.json", "manifest.json"},
            )
            with self.assertRaises(FileExistsError):
                write_taxonomy_snapshot_bundle(
                    SOURCE_PAYLOAD,
                    output_dir=output,
                    fetched_at_utc="2026-09-09T12:00:00Z",
                )

    def test_audit_must_match_snapshot_and_reject_duplicate_identity(self):
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        snapshot_hash = taxonomy_snapshot_sha256(snapshot)
        audit = make_audit(snapshot_hash)
        self.assertIsNone(validate_tag_audit(audit, snapshot))

        duplicate_id = audit + (replace(audit[0], tag_name="Another Name"),)
        wrong_name = (replace(audit[0], tag_name="Male Harem"),) + audit[1:]
        wrong_hash = (replace(audit[0], source_snapshot_hash="0" * 64),) + audit[1:]
        for name, invalid in (
            ("duplicate_id", duplicate_id),
            ("id_name_mismatch", wrong_name),
            ("snapshot_hash", wrong_hash),
        ):
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_tag_audit(invalid, snapshot)

        additional_invalid_cases = (
            (
                "wrong_category",
                (replace(audit[0], category="Wrong Category"),) + audit[1:],
            ),
            (
                "wrong_spoiler_flag",
                (
                    replace(
                        audit[0],
                        is_general_spoiler=True,
                    ),
                )
                + audit[1:],
            ),
            (
                "wrong_adult_flag",
                (replace(audit[0], is_adult=True),) + audit[1:],
            ),
            (
                "unknown_tag_id",
                (replace(audit[0], tag_id=999999),) + audit[1:],
            ),
            (
                "unknown_tag_name",
                (replace(audit[0], tag_name="Unknown Tag"),) + audit[1:],
            ),
            (
                "duplicate_alias_in_record",
                (
                    replace(
                        audit[0],
                        aliases=("后宫", "后宫"),
                    ),
                )
                + audit[1:],
            ),
            (
                "alias_conflicts_with_canonical_name",
                (
                    replace(
                        audit[0],
                        aliases=("Male Harem",),
                    ),
                )
                + audit[1:],
            ),
            (
                "alias_shared_by_approved_records",
                (
                    replace(audit[0], aliases=("后宫",)),
                    replace(audit[1], aliases=("后宫",)),
                )
                + audit[2:],
            ),
        )

        for name, invalid in additional_invalid_cases:
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_tag_audit(invalid, snapshot)

        approved_and_rejected_share_alias = (
            replace(audit[0], aliases=("后宫",)),
            audit[1],
            audit[2],
            replace(audit[3], aliases=("后宫",)),
        )
        self.assertIsNone(
            validate_tag_audit(
                approved_and_rejected_share_alias,
                snapshot,
            )
        )

    def test_subset_contains_only_explicitly_approved_tags_and_has_own_hash(self):
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        audit = make_audit(taxonomy_snapshot_sha256(snapshot))
        subset = build_executable_tag_subset(
            audit,
            snapshot,
            subset_version="anilist-executable-tags-v0.1",
        )
        self.assertEqual(
            [tag.tag_name for tag in subset.tags],
            ["Female Harem", "Male Harem", "Mixed Gender Harem"],
        )
        self.assertNotIn("Ensemble Cast", {tag.tag_name for tag in subset.tags})

        manifest = build_executable_subset_manifest(subset)
        self.assertEqual(manifest.subset_hash, executable_tag_subset_sha256(subset))
        self.assertEqual(manifest.approved_tag_count, 3)
        self.assertEqual(
            manifest.derived_from_snapshot_hash,
            taxonomy_snapshot_sha256(snapshot),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            subset_path = Path(temporary_directory) / "executable_tags.json"
            subset_path.write_text(
                dumps_executable_tag_subset(subset),
                encoding="utf-8",
            )

            loaded_subset = load_executable_tag_subset(subset_path)

            self.assertEqual(loaded_subset, subset)

    def test_active_tag_and_group_target_hierarchy(self):
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        audit = make_audit(taxonomy_snapshot_sha256(snapshot))
        subset = build_executable_tag_subset(
            audit,
            snapshot,
            subset_version="anilist-executable-tags-v0.1",
        )
        rules = load_domain_rules(RULES_PATH)
        self.assertIsNone(validate_domain_rule_tag_targets(subset, rules))

        missing_target = replace(subset, tags=subset.tags[:-1])
        with self.assertRaises(ValueError):
            validate_domain_rule_tag_targets(missing_target, rules)

        extra_tag = ExecutableTagSpec(
            tag_id=101,
            tag_name="Ensemble Cast",
            category="Cast-Main Cast",
            aliases=(),
            is_general_spoiler=False,
            is_adult=False,
        )
        subset_with_extra_tag = replace(
            subset,
            tags=(extra_tag,) + subset.tags,
        )

        self.assertIsNone(
            validate_domain_rule_tag_targets(
                subset_with_extra_tag,
                rules,
            )
        )

        existing_group = next(iter(rules.tag_groups.values()))

        valid_non_harem_group = replace(
            existing_group,
            tags=("Female Harem",),
            normalization_rule_id="TEST_GROUP_VALID_V0_1",
        )
        rules_with_valid_non_harem_group = replace(
            rules,
            tag_groups={
                **dict(rules.tag_groups),
                "TEST_GROUP": valid_non_harem_group,
            },
        )

        self.assertIsNone(
            validate_domain_rule_tag_targets(
                subset,
                rules_with_valid_non_harem_group,
            )
        )

        invalid_non_harem_group = replace(
            existing_group,
            tags=("Ensemble Cast",),
            normalization_rule_id="TEST_GROUP_INVALID_V0_1",
        )
        rules_with_invalid_non_harem_group = replace(
            rules,
            tag_groups={
                **dict(rules.tag_groups),
                "TEST_GROUP": invalid_non_harem_group,
            },
        )

        with self.assertRaises(ValueError):
            validate_domain_rule_tag_targets(
                subset_with_extra_tag,
                rules_with_invalid_non_harem_group,
            )

    def test_audit_loader_requires_explicit_approved_field(self):
        """Missing review decisions must never receive an implicit default."""
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        snapshot_hash = taxonomy_snapshot_sha256(snapshot)
        record = make_audit(snapshot_hash)[0]
        valid_payload = [asdict(record)]
        with tempfile.TemporaryDirectory() as temporary_directory:
            valid_path = Path(temporary_directory) / "valid-audit.json"
            invalid_path = Path(temporary_directory) / "missing-approved.json"
            valid_path.write_text(
                json.dumps(valid_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            loaded = load_tag_audit(valid_path)
            self.assertEqual(loaded, (record,))
            invalid_payload = copy.deepcopy(valid_payload)
            invalid_payload[0].pop("approved")
            invalid_path.write_text(
                json.dumps(invalid_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"missing=.*approved"):
                load_tag_audit(invalid_path)

    def test_executable_subset_bundle_writes_manifest_and_refuses_overwrite(self):
        """The subset bundle must persist its own identity without overwriting."""
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        audit = make_audit(taxonomy_snapshot_sha256(snapshot))
        subset = build_executable_tag_subset(
            audit,
            snapshot,
            subset_version="anilist-executable-tags-v0.1",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "subset-bundle"

            manifest = write_executable_subset_bundle(
                subset,
                output_dir=output,
            )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"executable_tags.json", "manifest.json"},
            )

            loaded_subset = load_executable_tag_subset(output / "executable_tags.json")
            self.assertEqual(loaded_subset, subset)

            manifest_payload = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest_payload,
                {
                    "subset_version": manifest.subset_version,
                    "subset_hash": manifest.subset_hash,
                    "derived_from_snapshot_hash": manifest.derived_from_snapshot_hash,
                    "approved_tag_count": manifest.approved_tag_count,
                },
            )

            with self.assertRaises(FileExistsError):
                write_executable_subset_bundle(
                    subset,
                    output_dir=output,
                )

    def test_subset_hash_is_independent_of_audit_and_alias_input_order(self):
        """Equivalent reviewed content must produce one canonical subset hash."""
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        audit = make_audit(taxonomy_snapshot_sha256(snapshot))

        first_audit = (
            replace(
                audit[0],
                aliases=("女后宫", "female-harem"),
            ),
        ) + audit[1:]

        first_subset = build_executable_tag_subset(
            first_audit,
            snapshot,
            subset_version="anilist-executable-tags-v0.1",
        )

        second_records = []

        for record in reversed(first_audit):
            if record.tag_id == first_audit[0].tag_id:
                record = replace(
                    record,
                    aliases=tuple(reversed(record.aliases)),
                )
            second_records.append(record)

        second_audit = tuple(second_records)

        second_subset = build_executable_tag_subset(
            second_audit,
            snapshot,
            subset_version="anilist-executable-tags-v0.1",
        )

        self.assertEqual(first_subset, second_subset)

        self.assertEqual(
            dumps_executable_tag_subset(first_subset),
            dumps_executable_tag_subset(second_subset),
        )

        self.assertEqual(
            executable_tag_subset_sha256(first_subset),
            executable_tag_subset_sha256(second_subset),
        )

    def test_snapshot_hash_tracks_contract_fields_but_ignores_extra_fields(self):
        """Hash changes exactly with fields admitted to the canonical contract."""
        baseline_snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        baseline_hash = taxonomy_snapshot_sha256(baseline_snapshot)

        cases = (
            (
                "genre",
                lambda source: source["data"]["GenreCollection"].__setitem__(
                    0, "Action"
                ),
            ),
            (
                "tag_id",
                lambda source: source["data"]["MediaTagCollection"][0].__setitem__(
                    "id", 999
                ),
            ),
            (
                "tag_name",
                lambda source: source["data"]["MediaTagCollection"][0].__setitem__(
                    "name", "Male Harem Revised"
                ),
            ),
            (
                "description",
                lambda source: source["data"]["MediaTagCollection"][0].__setitem__(
                    "description", "Changed description."
                ),
            ),
            (
                "category",
                lambda source: source["data"]["MediaTagCollection"][0].__setitem__(
                    "category", "Changed-Category"
                ),
            ),
            (
                "is_general_spoiler",
                lambda source: source["data"]["MediaTagCollection"][0].__setitem__(
                    "isGeneralSpoiler", True
                ),
            ),
            (
                "is_adult",
                lambda source: source["data"]["MediaTagCollection"][0].__setitem__(
                    "isAdult", True
                ),
            ),
        )
        for case_name, mutate in cases:
            with self.subTest(case=case_name):
                changed_source = copy.deepcopy(SOURCE_PAYLOAD)
                mutate(changed_source)

                changed_snapshot = build_canonical_taxonomy_snapshot(changed_source)
                changed_hash = taxonomy_snapshot_sha256(changed_snapshot)

                self.assertNotEqual(changed_hash, baseline_hash)
        extra_field_change = copy.deepcopy(SOURCE_PAYLOAD)
        extra_field_change["data"]["MediaTagCollection"][0][
            "ignoredFutureField"
        ] = "changed outside canonical contract"

        extra_snapshot = build_canonical_taxonomy_snapshot(extra_field_change)

        self.assertEqual(
            taxonomy_snapshot_sha256(extra_snapshot),
            baseline_hash,
        )

        self.assertEqual(extra_snapshot, baseline_snapshot)

    def test_audit_rejects_duplicate_tag_name_independently(self):
        """Duplicate audit names need a regression test distinct from ID mismatch."""
        snapshot = build_canonical_taxonomy_snapshot(SOURCE_PAYLOAD)
        snapshot_hash = taxonomy_snapshot_sha256(snapshot)
        audit = make_audit(snapshot_hash)

        first_record = audit[3]

        second_record = replace(
            audit[0],
            tag_name=first_record.tag_name,
        )

        self.assertNotEqual(first_record.tag_id, second_record.tag_id)
        self.assertEqual(first_record.tag_name, second_record.tag_name)

        with self.assertRaisesRegex(
            ValueError,
            r"duplicate audit tag_name",
        ):
            validate_tag_audit(
                (first_record, second_record),
                snapshot,
            )


if __name__ == "__main__":
    unittest.main()
