# E0 Base-Model Baseline Evaluation v0.1

- Model: `Qwen/Qwen3-4B`
- Resolved revision: `1cfa9a7208912126459214e8b04321603b3df60c`
- Tokenizer: `Qwen/Qwen3-4B`
- Prompt version: `e0-json-extraction-v0.2`
- Prompt frozen before test/challenge: `True`
- Serialization: `qwen3-official-chat-template-nonthinking-v1`
- Generation config: `{"device": "cuda", "do_sample": false, "dtype": "bfloat16", "enable_thinking": false, "max_new_tokens": 512, "num_beams": 1}`
- GPU: `NVIDIA GeForce RTX 5070`
- PyTorch: `2.11.0+cu130`
- Transformers: `4.57.6`
- System prompt SHA-256: `80372e73bf41bf7529374c15503e83637ad6e96985cd2220d37d35f16d310b1c`
- Chat template SHA-256: `a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8`
- Training operations: none
- Same-input deterministic check: `PASS`

## Validation-only prompt selection

Prompt v0.1 was evaluated only on validation. It exposed episode/year field leakage and false HAREM normalization from explicit genres. Prompt v0.2 added field-isolation and normalization-trigger instructions, then became frozen before the first test/challenge run.

| Prompt | JSON | Schema | Domain | Exact | Hard F1 |
|---|---:|---:|---:|---:|---:|
| `e0-json-extraction-v0.1` | 100.0% | 76.7% | 76.7% | 70.0% | 72.7% |
| `e0-json-extraction-v0.2` | 100.0% | 100.0% | 100.0% | 93.3% | 90.2% |

## Validation metrics

| Metric | Value |
|---|---:|
| Records | 30 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 93.3% |
| Hard precision | 88.5% |
| Hard recall | 92.0% |
| Hard F1 | 90.2% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 93.3% |
| `tags` | 93.3% |
| `year` | 100.0% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 100.0% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 2 |
| `HALLUCINATED_CONSTRAINT` | 2 |
| `WRONG_OPERATOR` | 0 |
| `WRONG_VALUE` | 0 |
| `WRONG_NUMERIC_BOUND` | 0 |
| `REFERENCE_ERROR` | 0 |
| `NORMALIZATION_ERROR` | 0 |

## Test metrics

| Metric | Value |
|---|---:|
| Records | 30 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 76.7% |
| Hard precision | 83.7% |
| Hard recall | 72.0% |
| Hard F1 | 77.4% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 100.0% |
| `tags` | 76.7% |
| `year` | 100.0% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 100.0% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 7 |
| `HALLUCINATED_CONSTRAINT` | 7 |
| `WRONG_OPERATOR` | 7 |
| `WRONG_VALUE` | 7 |
| `WRONG_NUMERIC_BOUND` | 0 |
| `REFERENCE_ERROR` | 0 |
| `NORMALIZATION_ERROR` | 0 |

## Challenge metrics

| Metric | Value |
|---|---:|
| Records | 12 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 66.7% |
| Hard precision | 94.7% |
| Hard recall | 81.8% |
| Hard F1 | 87.8% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 75.0% |
| `tags` | 100.0% |
| `year` | 91.7% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 91.7% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 3 |
| `HALLUCINATED_CONSTRAINT` | 1 |
| `WRONG_OPERATOR` | 0 |
| `WRONG_VALUE` | 0 |
| `WRONG_NUMERIC_BOUND` | 1 |
| `REFERENCE_ERROR` | 1 |
| `NORMALIZATION_ERROR` | 0 |

## Validation reference behavior

| Metric | Value |
|---|---:|
| Records | 10 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 100.0% |
| Hard precision | 100.0% |
| Hard recall | 100.0% |
| Hard F1 | 100.0% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 100.0% |
| `tags` | 100.0% |
| `year` | 100.0% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 100.0% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 0 |
| `HALLUCINATED_CONSTRAINT` | 0 |
| `WRONG_OPERATOR` | 0 |
| `WRONG_VALUE` | 0 |
| `WRONG_NUMERIC_BOUND` | 0 |
| `REFERENCE_ERROR` | 0 |
| `NORMALIZATION_ERROR` | 0 |

## Test reference behavior

| Metric | Value |
|---|---:|
| Records | 20 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 100.0% |
| Hard precision | 100.0% |
| Hard recall | 100.0% |
| Hard F1 | 100.0% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 100.0% |
| `tags` | 100.0% |
| `year` | 100.0% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 100.0% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 0 |
| `HALLUCINATED_CONSTRAINT` | 0 |
| `WRONG_OPERATOR` | 0 |
| `WRONG_VALUE` | 0 |
| `WRONG_NUMERIC_BOUND` | 0 |
| `REFERENCE_ERROR` | 0 |
| `NORMALIZATION_ERROR` | 0 |

## Challenge normalization behavior

| Metric | Value |
|---|---:|
| Records | 2 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 50.0% |
| Hard precision | 90.0% |
| Hard recall | 90.0% |
| Hard F1 | 90.0% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 50.0% |
| `tags` | 100.0% |
| `year` | 50.0% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 100.0% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 1 |
| `HALLUCINATED_CONSTRAINT` | 1 |
| `WRONG_OPERATOR` | 0 |
| `WRONG_VALUE` | 0 |
| `WRONG_NUMERIC_BOUND` | 1 |
| `REFERENCE_ERROR` | 0 |
| `NORMALIZATION_ERROR` | 0 |

## Challenge reference behavior

| Metric | Value |
|---|---:|
| Records | 1 |
| JSON parse rate | 100.0% |
| Recoverable JSON rate | 100.0% |
| Schema valid rate | 100.0% |
| Domain valid rate | 100.0% |
| Exact match rate | 0.0% |
| Hard precision | 100.0% |
| Hard recall | 100.0% |
| Hard F1 | 100.0% |

### Field exact accuracy

| Field | Accuracy |
|---|---:|
| `genres` | 100.0% |
| `tags` | 100.0% |
| `year` | 100.0% |
| `episodes` | 100.0% |
| `formats` | 100.0% |
| `status` | 100.0% |
| `reference_titles` | 0.0% |
| `soft_preferences` | 100.0% |
| `unresolved_preferences` | 100.0% |

### Error labels

| Label | Count |
|---|---:|
| `JSON_PARSE_ERROR` | 0 |
| `SCHEMA_ERROR` | 0 |
| `DOMAIN_ERROR` | 0 |
| `MISSING_CONSTRAINT` | 0 |
| `HALLUCINATED_CONSTRAINT` | 0 |
| `WRONG_OPERATOR` | 0 |
| `WRONG_VALUE` | 0 |
| `WRONG_NUMERIC_BOUND` | 0 |
| `REFERENCE_ERROR` | 1 |
| `NORMALIZATION_ERROR` | 0 |

## Validation slices

### Semantic family

| Value | N | Exact | JSON | Domain |
|---|---:|---:|---:|---:|
| `cross_field_composition` | 10 | 100.0% | 100.0% | 100.0% |
| `reference_composition` | 10 | 100.0% | 100.0% | 100.0% |
| `same_field_logic` | 10 | 80.0% | 100.0% | 100.0% |

### Constraint count

| Value | N | Exact | JSON | Domain |
|---|---:|---:|---:|---:|
| `1` | 10 | 100.0% | 100.0% | 100.0% |
| `2` | 20 | 90.0% | 100.0% | 100.0% |

### Constraint signature

| Value | N | Exact | JSON | Domain |
|---|---:|---:|---:|---:|
| `GENRE_NONE` | 10 | 80.0% | 100.0% | 100.0% |
| `YEAR_MAX` | 10 | 100.0% | 100.0% | 100.0% |
| `YEAR_MIN + EPISODE_MAX` | 10 | 100.0% | 100.0% | 100.0% |

## Test slices

### Semantic family

| Value | N | Exact | JSON | Domain |
|---|---:|---:|---:|---:|
| `cross_field_composition` | 10 | 30.0% | 100.0% | 100.0% |
| `reference_composition` | 20 | 100.0% | 100.0% | 100.0% |

### Constraint count

| Value | N | Exact | JSON | Domain |
|---|---:|---:|---:|---:|
| `1` | 20 | 100.0% | 100.0% | 100.0% |
| `3` | 10 | 30.0% | 100.0% | 100.0% |

### Constraint signature

| Value | N | Exact | JSON | Domain |
|---|---:|---:|---:|---:|
| `EPISODE_MIN` | 10 | 100.0% | 100.0% | 100.0% |
| `FORMAT` | 10 | 100.0% | 100.0% | 100.0% |
| `TAG_NONE + STATUS` | 10 | 30.0% | 100.0% | 100.0% |

## Representative failure cases

### Failure 1: `sample_cf3f5fab39d1807e47810b50372c866e458c8d044b473c87746df51700df7be1`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Mixed Gender Harem”标签的作品，状态为“RELEASING”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["RELEASING"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Female Harem","Mixed Gender Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["RELEASING"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 2: `sample_8f88e5f9cc5cb94324f3d84533af9f7c80841e1eea6b3b8879b1a2fd4aad51aa`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Mixed Gender Harem”标签的作品，状态为“HIATUS”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["HIATUS"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Female Harem","Mixed Gender Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["HIATUS"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 3: `sample_a92e7365a16eb4a522a4730a1584255e8c6b61c027556cc087ddb013d14dadec`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Male Harem”标签的作品，状态为“RELEASING”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["RELEASING"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Male Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Female Harem","Male Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["RELEASING"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 4: `sample_786942bfddc75357a308d06792ed3d819de59407325ce69a0527c853845c054c`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Male Harem”标签的作品，状态为“HIATUS”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["HIATUS"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Male Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Female Harem","Male Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["HIATUS"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 5: `sample_55c1f9ac7b0c5fe7b590c90dfa04548cdef6a09d655abc48de3151c078f50f6f`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Male Harem”标签的作品，状态为“FINISHED”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["FINISHED"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Male Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Male Harem","Female Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["FINISHED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 6: `sample_4842ffae58093120dac9d3a1c9cd5d722612cf0e0da783e15035c62a78392445`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Mixed Gender Harem”标签的作品，状态为“FINISHED”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["FINISHED"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Female Harem","Mixed Gender Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["FINISHED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 7: `sample_aab8097e2cd304af809faf9ae5e3c3a2e0c53d758b8058ff09b02f4a03465efa`

- Split: `test`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE`
- User text: 帮我找一部动画，排除带有“Female Harem”和“Mixed Gender Harem”标签的作品，状态为“NOT_YET_RELEASED”。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["NOT_YET_RELEASED"], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Female Harem","Mixed Gender Harem"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["NOT_YET_RELEASED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 8: `challenge_002`

- Split: `challenge`
- Error labels: `MISSING_CONSTRAINT`
- User text: 悬疑或科幻题材都可以。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": ["Mystery", "Sci-Fi"], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 9: `challenge_003`

- Split: `challenge`
- Error labels: `MISSING_CONSTRAINT`
- User text: 想看同时包含悬疑和科幻题材的动画。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": ["Mystery", "Sci-Fi"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 10: `challenge_004`

- Split: `challenge`
- Error labels: `REFERENCE_ERROR`
- User text: 想找类似《Steins;Gate》的作品。

Gold:

```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": ["Steins;Gate"], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````

### Failure 11: `challenge_009`

- Split: `challenge`
- Error labels: `MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_NUMERIC_BOUND`
- User text: 想看2010年及以后、最多24集的悬疑或科幻TV动画，不要后宫。

Gold:

```json
{"hard_constraints": {"episodes": {"max": 24, "min": null}, "formats": ["TV"], "genres": {"all_of": [], "any_of": ["Mystery", "Sci-Fi"], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": ["Female Harem", "Male Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": 2010}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```

Raw prediction:

````text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":2010},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
````
