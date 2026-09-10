# Full AniList Taxonomy Snapshot + Reviewed Executable Tag Subset — Review Bundle

## Review status

**Contract implementation: ready for theoretical review.**

**Real-data acceptance: deferred.** AniList API was not reachable in the current
environment, so this bundle does not claim that a real taxonomy snapshot or a
production tag audit has been completed. All JSON evidence under `examples/` is
generated from the synthetic fixture in `tests/test_taxonomy_snapshot.py` and is
labelled accordingly.

The deferred operational step is:

```text
real AniList fetch -> real source/canonical/manifest bundle
                   -> human review against that snapshot
                   -> production executable subset/manifest
```

No placeholder ID or synthetic hash in this bundle may be copied into a
production audit.

## Scope

This work block implements and tests:

- `GenreCollection` and the approved global `MediaTagCollection` identity fields;
- raw/source preservation and canonical snapshot construction;
- deterministic Unicode JSON serialization and SHA-256 identity;
- snapshot manifest generation;
- strict human-audit loading and validation;
- explicitly approved-only executable subset construction;
- deterministic subset serialization, hash and manifest;
- validation of executable tags and tag-group normalization targets against
  `DomainRules`;
- the two required DatasetRecord Builder contract corrections.

It does not implement semantic sampling, natural-language realization, LLM
paraphrasing, splitting, tokenizer statistics, QLoRA, training, or inference.

## Files and responsibilities

- [`src/anime_pref/data/taxonomy_client.py`](../../src/anime_pref/data/taxonomy_client.py): fetches the complete decoded AniList
  taxonomy response without sorting or canonical-field projection.
- [`src/anime_pref/schemas/taxonomy.py`](../../src/anime_pref/schemas/taxonomy.py): immutable snapshot, audit, subset and
  manifest data contracts.
- [`src/anime_pref/data/taxonomy_snapshot.py`](../../src/anime_pref/data/taxonomy_snapshot.py): canonicalization, serialization,
  snapshot hashing, strict loading and non-overwriting bundle persistence.
- [`src/anime_pref/data/tag_subset.py`](../../src/anime_pref/data/tag_subset.py): audit loading/validation, approved subset
  derivation, subset hashing, strict loading, rule-target validation and bundle
  persistence.
- [`scripts/fetch_anilist_taxonomy.py`](../../scripts/fetch_anilist_taxonomy.py): real fetch CLI.
- [`scripts/build_executable_tag_subset.py`](../../scripts/build_executable_tag_subset.py): reviewed-subset CLI.
- [`configs/taxonomy_snapshot.v0.1.json`](../../configs/taxonomy_snapshot.v0.1.json): approved snapshot field contract.
- [`configs/tag_audit.example.v0.1.json`](../../configs/tag_audit.example.v0.1.json): format-only audit example with deliberate
  placeholders; not production data.
- [`tests/test_dataset_record_builder.py`](../../tests/test_dataset_record_builder.py): DatasetRecord contract corrections.
- [`tests/test_taxonomy_snapshot.py`](../../tests/test_taxonomy_snapshot.py): offline executable snapshot/subset contract.

## Contract decisions implemented

### Snapshot identity

The canonical snapshot contains only:

- `snapshot_schema_version`;
- sorted genres;
- sorted tags with `id`, `name`, `description`, `category`,
  `is_general_spoiler`, and `is_adult`.

Media-specific rank is absent. SHA-256 is computed from compact deterministic
JSON encoded as UTF-8. Input ordering and unknown source fields do not affect the
hash. Changes to any admitted taxonomy value do affect the hash.

`fetched_at_utc`, source name and resource names are manifest provenance and are
excluded from the canonical content hash.

### Audit and executable subset

Every audit record must explicitly provide:

```text
tag_id, tag_name, category, approved, reason, aliases,
is_general_spoiler, is_adult, source_snapshot_hash
```

An audit record must match the referenced canonical snapshot. Duplicate audit
IDs or names are rejected. Missing records and `approved=false` records never
enter the executable subset.

The executable subset contains `subset_version`,
`derived_from_snapshot_hash`, and the canonically sorted approved tags. Its
`subset_hash` is stored in the adjacent manifest and is calculated over the
canonical executable-subset document, which intentionally does not contain its
own hash.

The current rule integration requires the subset tag-name set to equal
`DomainRules.tags`, not merely contain it. Every configured tag-group target is
also checked. Consequently, the current HAREM normalization rule requires:

- `Female Harem`;
- `Male Harem`;
- `Mixed Gender Harem`.

Their production IDs, category and flags must come from a real snapshot; the
synthetic IDs in this bundle are test-only.

### Version boundaries

The following identities are separate:

| Identity | Meaning |
|---|---|
| `schema_version` | Model Gold JSON structural/domain contract |
| `snapshot_schema_version` | Canonical taxonomy field/serialization contract |
| `canonical_sha256` | One concrete taxonomy content identity |
| `subset_version` / `subset_hash` | Reviewed executable tag vocabulary identity |
| `dataset_version` | Final dataset release identity |

No taxonomy or executable-subset identity is substituted by `schema_version`.

Future DatasetRecord integration is intentionally not implemented in this work
block. Before sampling begins, the record contract should add explicit
executable rules/subset provenance and include it in the complete-record
`sample_id` payload. This must preserve the frozen meaning of `sample_id`: it is
not a semantic fingerprint or deduplication key.

## Required DatasetRecord corrections

Both corrections are implemented and covered by tests:

1. Direct `tags.any_of` and `tag_groups.any_of` form one shared TAG ANY OR
   clause. If both are non-empty, their combined `constraint_count` contribution
   is one. Direct and group `none_of` clauses remain additive.
2. The deterministic-record fixture now says: “想看2010年及以后、最多24集的科幻或悬疑TV动画，不要后宫。”
   It therefore explicitly expresses the inclusive year minimum and episode
   maximum represented by its `SemanticSpec`.

The record validator still checks only computable provenance and Gold
consistency. It does not attempt NLP equivalence between `user_text` and
`SemanticSpec`.

## Evidence index

- `examples/source.synthetic.json`: source-payload example.
- `examples/canonical.synthetic.json`: deterministic canonical taxonomy example.
- `examples/snapshot_manifest.synthetic.json`: snapshot manifest example.
- `examples/tag_audit.synthetic.json`: explicit approve/reject audit example.
- `examples/executable_tags.synthetic.json`: derived executable subset example.
- `examples/subset_manifest.synthetic.json`: subset version/hash/provenance.
- `test-output.txt`: complete offline test command and result.

The synthetic snapshot hash is
`558bba0d4a79f87203b814a711b138151eefecf569582449f59d92628e290a0d`.
The synthetic subset hash is
`95827c120efdd0456fecf7b0a191c30fef72a5c6e4a41a3a2cdf3947c1d623fa`.

## Automated test evidence

Command:

```bash
python3 -B -m unittest discover -s tests -v
```

Observed on 2026-09-10:

```text
Ran 42 tests in 0.027s
OK
```

There are no skipped tests. The taxonomy/subset suite includes explicit coverage
for input-order-independent hashes, admitted/ignored snapshot fields, missing
`approved`, duplicate audit identity, approved-only selection, alias ordering,
bundle manifests, overwrite refusal and all configured group targets.

## Boundaries requiring theoretical confirmation

1. Confirm that `subset_hash` belongs in the adjacent manifest rather than in the
   hashed executable document itself, avoiding self-referential hashing.
2. Confirm whether the executable subset must remain exactly equal to
   `DomainRules.tags`, or whether a reviewed subset may be a superset from which
   individual rule versions select tags.
3. Approve the future DatasetRecord provenance fields. Recommended minimum:
   `executable_subset_version`, `executable_subset_hash`, and a distinct
   executable rules version/hash. These identities should enter complete-record
   `sample_id` derivation without changing its frozen non-dedup meaning.
4. Define the human approval policy for non-HAREM tags, including adult tags,
   spoiler tags, category eligibility and alias governance. No automatic bulk
   approval is allowed.
5. When AniList becomes reachable, verify the real identity and flags of all
   three HAREM targets before they are admitted to a production subset.

## Deferred real-data completion criteria

The operational portion of this work block becomes complete only after:

1. a real `source.json`, `canonical.json`, and snapshot `manifest.json` are
   generated together;
2. a human-reviewed audit references that exact canonical hash;
3. the three HAREM targets are verified and approved against the real snapshot;
4. the executable subset and its manifest are generated from that audit;
5. the real manifests and reviewed excerpts replace or accompany the synthetic
   evidence in this bundle.
