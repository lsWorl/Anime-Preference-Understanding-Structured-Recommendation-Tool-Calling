# Review Bundle: Executable Rules Identity + DatasetRecord Provenance v0.1

## Review scope and status

This bundle covers only:

```text
approved executable subset
        ↓
active DomainRules + canonical rules identity
        ↓
Gold builder + DatasetRecord provenance
```

Offline contract implementation status: **PASS**.

- 48 unit tests passed with no skips.
- Python compilation passed.
- `git diff --check` reported no whitespace errors.
- Tests use network mocks and explicitly synthetic taxonomy/subset/rules identities.
- Production AniList taxonomy, audit, subset, and rules acceptance remain deferred.

Semantic sampling, text realization, paraphrase, split, tokenizer statistics, and training are outside this review.

## Relevant project tree

```text
configs/
└── domain_rules.v0.1.1.json
src/anime_pref/
├── data/
│   ├── query_builder.py
│   ├── rules_identity.py
│   ├── tag_subset.py
│   └── dataset_record_builder.py
└── schemas/
    ├── dataset_record.py
    └── taxonomy.py
tests/
├── fixtures/
│   ├── domain_rules.synthetic.v0.1.json
│   └── executable_tags.synthetic.v0.1.json
├── test_rules_identity_and_record_provenance.py
├── test_dataset_record_builder.py
├── test_query_builder.py
└── test_taxonomy_snapshot.py
docs/
└── rules_identity_and_record_provenance_v0.1.md
```

The production-oriented config is not populated with synthetic identity values. Offline acceptance uses only files under `tests/fixtures/` whose names and versions explicitly identify them as synthetic.

## Executable relationship

The implementation validates:

```text
tag_group members ⊆ DomainRules.tags ⊆ approved executable subset tags
```

The executable subset is the reviewed approved pool. `DomainRules.tags` is the active vocabulary for one rules version. An approved tag may remain inactive. A tag group may only expand to active tags.

`validate_executable_rules_identity(rules, subset)` also requires:

- declared subset version equals the actual subset version;
- declared subset hash equals the recomputed subset hash;
- stored rules hash equals the recomputed canonical rules hash;
- the group/active/approved inclusion hierarchy holds.

## DomainRules identity contract

`DomainRules` contains:

```text
rules_version
rules_hash
schema_version
executable_subset_version
executable_subset_hash
genres / tags / formats / statuses / soft_preferences
tag_groups
episodes / year numeric rules
```

The input rules JSON contains every field above except `rules_hash`. The loader validates the document, builds immutable rules, computes the canonical hash, and stores the derived value.

Representative canonical rules document:

```json
{"rules_version":"synthetic-domain-rules-v0.1","schema_version":"0.1.1","executable_subset_version":"synthetic-approved-tags-v0.1","executable_subset_hash":"067b04f668406703b91233ea8eb5f10235a66387887d9161f4cb8050e5a43296","taxonomy":{"genres":["Action","Adventure","Comedy","Drama","Ecchi","Fantasy","Hentai","Horror","Mahou Shoujo","Mecha","Music","Mystery","Psychological","Romance","Sci-Fi","Slice of Life","Sports","Supernatural","Thriller"],"tags":["Female Harem","Male Harem","Mixed Gender Harem"],"formats":["MOVIE","MUSIC","ONA","OVA","SPECIAL","TV","TV_SHORT"],"statuses":["CANCELLED","FINISHED","HIATUS","NOT_YET_RELEASED","RELEASING"],"soft_preferences":[]},"tag_groups":{"HAREM":{"tags":["Female Harem","Male Harem","Mixed Gender Harem"],"allowed_operators":["any_of","none_of"],"normalization_rule_id":"HAREM_EXPANSION_V0_1_1"}},"numeric_rules":{"episodes":{"minimum":1,"maximum":null},"year":{"minimum":1900,"maximum":2100}}}
```

Synthetic fixture identities:

```text
subset_hash = 067b04f668406703b91233ea8eb5f10235a66387887d9161f4cb8050e5a43296
rules_hash  = f2a22ea1b6cf8a71a59faf3520daa477b8b82f4cb077c78edc5e7e84605f6a53
```

These values are forbidden in production rules.

Canonicalization sorts all set-semantic vocabularies, tag-group names, group members, and allowed operators. Serialization uses compact Unicode JSON and UTF-8. `rules_hash` is excluded from its own input document.

## DatasetRecord provenance contract

Outside the model Gold JSON, every record contains:

```text
executable_subset_version
executable_subset_hash
rules_version
rules_hash
```

`build_dataset_record()` requires the actual `ExecutableTagSubset`, validates it against `DomainRules`, copies the four verified identities, and includes all four in the deterministic `sample_id` payload.

`validate_dataset_record()` takes the record, actual rules, and actual subset. It recomputes subset/rules identity, Gold Query, constraint signature/count, normalization rule IDs, and sample ID. It rejects mismatches without repairing the record.

Representative synthetic record identity:

```json
{"sample_id":"sample_aebe64a91769d946f18211f31ae7d0135f8e80323df8c711d9b9c3be6e7c0a07","schema_version":"0.1.1","dataset_version":"synthetic-dataset-v0.1","executable_subset_version":"synthetic-approved-tags-v0.1","executable_subset_hash":"067b04f668406703b91233ea8eb5f10235a66387887d9161f4cb8050e5a43296","rules_version":"synthetic-domain-rules-v0.1","rules_hash":"f2a22ea1b6cf8a71a59faf3520daa477b8b82f4cb077c78edc5e7e84605f6a53","constraint_signature":"TAG_ANY","constraint_count":1,"normalization_rule_ids":["HAREM_EXPANSION_V0_1_1"]}
```

`sample_id` remains complete DatasetRecord identity. It is not a semantic fingerprint or deduplication key. A rules/subset identity change produces a different sample ID even when SemanticSpec, text, template, and seed are unchanged.

## Tag and alias policy

- Only explicit `approved=true` records can enter the subset.
- `approved=true` with `is_adult=true` is rejected.
- `approved=true` with `is_general_spoiler=true` is rejected in v0.1 because no override field exists.
- Category never grants automatic approval.
- Rejected adult/spoiler records may remain in the audit and are excluded.
- Aliases are part of subset canonical content and affect subset hash.
- Polarity belongs to operators, not alias text.
- Ambiguous or broadened/narrowed aliases are not approved.

## Automated acceptance coverage

Tests verify:

- an approved subset superset plus an active DomainRules subset passes;
- an active unapproved tag fails;
- a group target outside active tags fails;
- rules hash is stable across semantic input order, JSON key order, and formatting;
- an admitted rules field change changes rules hash;
- record identities match the actual rules/subset;
- tampering any of the four record identity fields fails validation;
- a rules hash change changes complete-record sample ID;
- adult/general-spoiler approved tags cannot enter the subset;
- earlier HAREM clause counting and complete-record identity semantics remain unchanged.

Test command and result:

```text
python -B -m unittest discover -s tests -v
Ran 48 tests in 0.039s
OK
```

## Deferred production boundary

Production acceptance remains incomplete until AniList access recovers:

- obtain real source/canonical taxonomy and manifest;
- bind audit records to the real snapshot hash;
- verify actual HAREM IDs, names, categories, and flags;
- build the real approved subset and manifest;
- create production DomainRules containing that exact subset version/hash.

No synthetic snapshot, subset, audit decision, or hash may cross this boundary.

## Questions for theory review

1. Confirm strict rejection of all `is_general_spoiler=true` approved records in v0.1 until an explicit reviewed override field is designed.
2. Confirm requiring the actual subset object at DatasetRecord build/validation time is the desired proof that declared subset provenance is real.
3. Confirm production rules may remain deferred and unusable until a real subset identity exists.
4. If this contract passes, identify the next engineering work block. Semantic sampler must remain blocked unless theory explicitly authorizes it.
