# Pilot Dataset Audit v0.1

- Total records: 240
- Train: 180
- Validation: 30
- Test: 30
- Human challenge cases: 12
- Exact template leakage across splits: 0

## Split hygiene: cross-split overlap

| Split pair | Exact user text | User text + Gold | SemanticSpec |
|---|---:|---:|---:|
| `train<->validation` | 0 | 0 | 2 |
| `train<->test` | 0 | 0 | 0 |
| `validation<->test` | 0 | 0 | 0 |

## Split hygiene: within-split duplicate excess

| Split | Exact user text | User text + Gold | SemanticSpec |
|---|---:|---:|---:|
| `train` | 66 | 66 | 66 |
| `validation` | 0 | 0 | 0 |
| `test` | 0 | 0 | 0 |

## Semantic family counts

| Value | Count |
|---|---:|
| `cross_field_composition` | 70 |
| `normalization` | 30 |
| `reference_composition` | 40 |
| `reference_only` | 10 |
| `same_field_logic` | 30 |
| `single_constraint` | 60 |

## Constraint count counts

| Value | Count |
|---|---:|
| `0` | 10 |
| `1` | 120 |
| `2` | 60 |
| `3` | 50 |

## Constraint signature counts

| Value | Count |
|---|---:|
| `EPISODE_MAX` | 10 |
| `EPISODE_MIN` | 10 |
| `FORMAT` | 20 |
| `GENRE_ALL` | 20 |
| `GENRE_ALL + EPISODE_MAX` | 10 |
| `GENRE_ALL + TAG_NONE` | 10 |
| `GENRE_ANY` | 10 |
| `GENRE_ANY + FORMAT + STATUS` | 10 |
| `GENRE_ANY + YEAR_MIN` | 10 |
| `GENRE_NONE` | 10 |
| `NO_HARD_CONSTRAINT` | 10 |
| `STATUS` | 10 |
| `TAG_ALL` | 10 |
| `TAG_ANY` | 20 |
| `TAG_NONE` | 10 |
| `TAG_NONE + STATUS` | 10 |
| `YEAR_MAX` | 10 |
| `YEAR_MIN` | 10 |
| `YEAR_MIN + EPISODE_MAX` | 20 |
| `YEAR_MIN + YEAR_MAX + FORMAT` | 10 |

## Template ID counts

| Value | Count |
|---|---:|
| `case_001__direct_explicit_v1` | 10 |
| `case_002__direct_explicit_v1` | 10 |
| `case_003__direct_explicit_v1` | 10 |
| `case_004__direct_explicit_v1` | 10 |
| `case_005__direct_compact_v1` | 10 |
| `case_006__direct_compact_v1` | 10 |
| `case_007__direct_compact_v1` | 10 |
| `case_008__natural_compact_v1` | 10 |
| `case_009__direct_explicit_v1` | 10 |
| `case_010__direct_compact_v1` | 10 |
| `case_011__natural_compact_v1` | 10 |
| `case_012__natural_compact_v1` | 10 |
| `case_013__direct_explicit_v1` | 10 |
| `case_014__direct_compact_v1` | 10 |
| `case_015__natural_compact_v1` | 10 |
| `case_016__direct_explicit_v1` | 10 |
| `case_017__natural_compact_v1` | 10 |
| `case_018__direct_compact_v1` | 10 |
| `case_019__direct_explicit_v1` | 10 |
| `case_020__natural_compact_v1` | 10 |
| `case_021__direct_explicit_v1` | 10 |
| `case_022__natural_compact_v1` | 10 |
| `case_023__direct_compact_v1` | 10 |
| `case_024__natural_compact_v1` | 10 |

## Genre frequency

| Value | Count |
|---|---:|
| `Action` | 8 |
| `Adventure` | 4 |
| `Comedy` | 8 |
| `Drama` | 10 |
| `Ecchi` | 7 |
| `Fantasy` | 11 |
| `Hentai` | 15 |
| `Horror` | 9 |
| `Mahou Shoujo` | 4 |
| `Mecha` | 9 |
| `Music` | 4 |
| `Mystery` | 8 |
| `Psychological` | 10 |
| `Romance` | 7 |
| `Sci-Fi` | 4 |
| `Slice of Life` | 7 |
| `Sports` | 6 |
| `Supernatural` | 5 |
| `Thriller` | 4 |

## Tag frequency (Gold leaves)

| Value | Count |
|---|---:|
| `Female Harem` | 55 |
| `Male Harem` | 52 |
| `Mixed Gender Harem` | 53 |

## Numeric pattern and bound frequency

| Value | Count |
|---|---:|
| `episodes:max=1` | 3 |
| `episodes:max=110` | 4 |
| `episodes:max=12` | 11 |
| `episodes:max=24` | 13 |
| `episodes:max=26` | 2 |
| `episodes:max=50` | 6 |
| `episodes:max=7` | 1 |
| `episodes:max_only` | 40 |
| `episodes:min=1` | 2 |
| `episodes:min=110` | 1 |
| `episodes:min=12` | 2 |
| `episodes:min=24` | 2 |
| `episodes:min=26` | 1 |
| `episodes:min=39` | 1 |
| `episodes:min=7` | 1 |
| `episodes:min_only` | 10 |
| `year:bounded_range` | 10 |
| `year:max=1917` | 1 |
| `year:max=1990` | 1 |
| `year:max=2000` | 2 |
| `year:max=2005` | 2 |
| `year:max=2010` | 3 |
| `year:max=2015` | 1 |
| `year:max=2020` | 7 |
| `year:max=2024` | 1 |
| `year:max=2037` | 2 |
| `year:max_only` | 10 |
| `year:min=1917` | 1 |
| `year:min=1990` | 5 |
| `year:min=2000` | 6 |
| `year:min=2005` | 7 |
| `year:min=2010` | 14 |
| `year:min=2015` | 4 |
| `year:min=2020` | 9 |
| `year:min=2024` | 1 |
| `year:min=2037` | 3 |
| `year:min_only` | 40 |

## Reference frequency

| Value | Count |
|---|---:|
| `Fullmetal Alchemist: Brotherhood` | 26 |
| `Steins;Gate` | 24 |
| `records_with_reference` | 50 |

## Normalization frequency

| Value | Count |
|---|---:|
| `HAREM_EXPANSION_V0_1_1` | 30 |
| `records_with_normalization` | 30 |

## Duplicate counts

| Value | Count |
|---|---:|
| `sample_id` | 0 |
| `exact_user_text` | 66 |
| `user_text_plus_gold` | 66 |
| `semantic_spec` | 68 |
