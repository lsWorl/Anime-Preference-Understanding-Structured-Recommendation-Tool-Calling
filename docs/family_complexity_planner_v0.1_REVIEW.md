# Review Bundle: B. Family + Complexity Planner v0.1

## Scope and status

This bundle covers only phase B of Offline Semantic Sampler v0.1:

```text
validated SemanticSamplerConfigSpec
        ↓
normalized P(F)
        ↓
family-compatible P(C|F)
        ↓
theoretical P(F,C) / P(C)
        ↓
explicit-RNG hierarchical sampling
        ↓
FamilyComplexityPlan
```

Status: **offline implementation PASS candidate**.

- B planner tests: 35 passed.
- Full offline suite: 89 passed, no skips or failures.
- Python compilation and `git diff --check` passed.
- No SemanticSpec, DatasetRecord, user text, operator/value/numeric sampler, audit report, or production dataset was created.

## Relevant files

```text
src/anime_pref/schemas/family_complexity.py
src/anime_pref/sampling/config.py
src/anime_pref/sampling/family_complexity.py
tests/test_family_complexity_planner.py
tests/fixtures/semantic_sampler.synthetic.v0.1.json
docs/family_complexity_planner_v0.1.md
docs/family_complexity_planner_v0.1_REVIEW.md
```

`sampling/config.py` gained only canonical ordered tuples for semantic families and hard-complexity buckets. Existing exact-key sets are derived from those tuples, so Phase A validation semantics are unchanged.

## Output contract

`FamilyComplexityPlan` is a frozen dataclass with exactly two fields:

```text
semantic_family
complexity_bucket
```

Allowed complexity values are `0 / 1 / 2 / 3 / 4 / 5_plus`. `0` is exclusive to `reference_only`. `5_plus` remains a string bucket meaning `>= 5`; the planner does not invent an exact integer constraint count.

## Frozen compatibility matrix

```text
single_constraint       -> 1
same_field_logic        -> 1 / 2 / 3
cross_field_composition -> 2 / 3 / 4 / 5_plus
normalization           -> 1 / 2 / 3 / 4 / 5_plus
reference_only          -> 0
reference_composition   -> 1 / 2 / 3 / 4 / 5_plus
```

The mapping is read-only and its candidate collections are tuples. Invalid pairs never enter a candidate space, so there is no invalid-pair rejection loop.

## Probability implementation

The planner implements the revised hierarchical contract:

```text
P(F=f) = w_F(f) / sum_j(w_F(j))

P(C=c | F=f)
  = w_C(c) / sum_{k in compatible(f)}(w_C(k))

P(F=f, C=c) = P(F=f) * P(C=c | F=f)
```

For `reference_only`, `P(C=0 | F=reference_only) = 1`. No count-zero configuration entry, virtual weight, or magic factor exists. The implementation does not globally normalize raw `family_weight * count_weight` products.

Pure functions expose normalized family probabilities, family-conditional complexity probabilities, joint probabilities, and global complexity marginals. The marginal helper only calculates the theoretical expectation for future Phase G; it does not compare or audit samples.

## Scale invariance

Tests independently multiply:

- the complete family table by a positive constant;
- the complete count table by a positive constant;
- both tables by different positive constants.

All resulting joint distributions equal the baseline within floating-point tolerance. Count representations `35/30/20/10/5` and `0.35/0.30/0.20/0.10/0.05` are equivalent.

## Deterministic RNG contract

The public sampler requires a caller-supplied object with callable `random()` and uses canonical candidate order.

```text
hard-bearing family:
  one family draw + one compatible-complexity draw

reference_only:
  one family draw + deterministic bucket 0
```

No module-global random function is used and no internal `Random(seed)` is created. Tests confirm identical plan sequences for equal seeds, exactly one draw for `reference_only`, and exactly two draws for a hard-bearing family.

## Fixture probability output

Using `offline-synthetic-semantic-sampler-v0.1`:

```json
{
  "family_probabilities": {
    "single_constraint": 0.25,
    "same_field_logic": 0.2,
    "cross_field_composition": 0.2,
    "normalization": 0.15,
    "reference_only": 0.1,
    "reference_composition": 0.1
  },
  "conditional_same_field_logic": {
    "1": 0.4117647058823529,
    "2": 0.35294117647058826,
    "3": 0.23529411764705882
  },
  "conditional_cross_field_composition": {
    "2": 0.46153846153846156,
    "3": 0.3076923076923077,
    "4": 0.15384615384615385,
    "5_plus": 0.07692307692307693
  },
  "conditional_reference_only": {
    "0": 1.0
  },
  "complexity_marginal": {
    "0": 0.1,
    "1": 0.41985294117647054,
    "2": 0.23789592760180997,
    "3": 0.1585972850678733,
    "4": 0.05576923076923077,
    "5_plus": 0.027884615384615386
  }
}
```

The marginal differs from the raw count-table ratios because each family renormalizes only over its compatible buckets. This is the intended revised probability model.

## Deterministic sample output

The first twelve plans from a fresh `Random(1729)` are:

```text
reference_composition / 4
same_field_logic / 2
normalization / 1
same_field_logic / 1
reference_only / 0
single_constraint / 1
single_constraint / 1
cross_field_composition / 3
same_field_logic / 1
normalization / 3
cross_field_composition / 3
same_field_logic / 1
```

This output is a deterministic synthetic mechanics check, not a production distribution claim.

## Automated acceptance

The B tests cover:

- every compatible and incompatible family/bucket pair;
- family-specific low/high bucket boundaries;
- preservation of `5_plus` as a bucket;
- strict finite-positive relative-weight normalization;
- normalized family and conditional probability sums;
- the hierarchical joint formula and recovered family marginals;
- complexity marginal aggregation, including reference-only zero;
- independent family/count scaling invariance;
- deterministic sequences and exact RNG draw consumption;
- absence of downstream payload fields from the plan.

Final results:

```text
python -m unittest tests.test_family_complexity_planner -v
Ran 35 tests in 0.040s
OK

python -m unittest discover -s tests -v
Ran 89 tests in 0.074s
OK
```

## Boundaries for theory review

1. Please confirm that the implementation matches the revised hierarchical conditional contract and fully supersedes raw-product global normalization.
2. Please confirm the canonical candidate order is part of deterministic mechanics without adding semantic meaning to order.
3. Phase B deliberately does not validate direct construction of arbitrary `FamilyComplexityPlan` instances; the planner guarantees valid output. Confirm whether future consumers need a separate public plan validator before Phase F.
4. Production taxonomy/rules/dataset generation remains unavailable. All demonstrated inputs and outputs are synthetic offline fixtures.

If Phase B passes, authorize only the next bounded module after its theoretical contract has been frozen. Do not infer or implement Phase C from the existing Phase A config alone.
