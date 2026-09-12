# Review Bundle: C. Direct Set-Logic Operator + Cardinality Sampler v0.1

## Scope and status

This bundle covers only phase C of Offline Semantic Sampler v0.1 plus the public
phase-B plan validator required as its prerequisite:

```text
FamilyComplexityPlan(same_field_logic, 1/2/3)
        ↓
public plan validation
        ↓
contribution-based eligible pair derivation
        ↓
P(O | context)
        ↓
P(K | O, context)
        ↓
OperatorCardinalityPlan(operator, cardinality)
```

Status: **offline implementation PASS candidate**.

- C-specific tests: 23 passed.
- Full offline suite: 112 passed, no skips or failures.
- Python compilation and `git diff --check` passed.
- No genre/tag field or value was selected.
- No normalization/group operator, structural composition, SemanticSpec,
  DatasetRecord, user text, distribution audit, or production dataset was created.

## Relevant files

```text
src/anime_pref/schemas/family_complexity.py
src/anime_pref/schemas/operator_cardinality.py
src/anime_pref/sampling/config.py
src/anime_pref/sampling/family_complexity.py
src/anime_pref/sampling/operator_cardinality.py
tests/test_family_complexity_planner.py
tests/test_operator_cardinality_sampler.py
tests/fixtures/semantic_sampler.synthetic.v0.1.json
docs/family_complexity_planner_v0.1.md
docs/operator_cardinality_sampler_v0.1.md
docs/operator_cardinality_sampler_v0.1_REVIEW.md
```

`sampling/config.py` now exposes canonical operator and per-operator cardinality
orders. Existing Phase A allowed-cardinality sets are derived from those tuples,
so their validation semantics are unchanged.

## Phase-B public validator prerequisite

`validate_family_complexity_plan(plan)` now protects later modules from arbitrary
direct dataclass construction. It verifies:

- the object is `FamilyComplexityPlan`;
- semantic family belongs to the frozen family set;
- complexity bucket has an allowed runtime type and is not bool;
- the family/bucket pair belongs to the frozen compatibility matrix;
- consequently, zero belongs only to `reference_only`, and `reference_only`
  accepts only zero.

The B planner continues to generate valid output and validates its normal
hard-bearing return path.

## C output and validation

`OperatorCardinalityPlan` is a frozen dataclass with exactly:

```text
operator
cardinality
```

It deliberately carries no field, values, tag group, SemanticSpec, DatasetRecord,
or user text.

`validate_operator_cardinality_plan(plan)` enforces the complete generic contract:

```text
all_of  -> 1 / 2 / 3
any_of  -> 2 / 3
none_of -> 1 / 2
```

It rejects unknown operators, bool cardinality, non-integer cardinality, and every
operator/cardinality mismatch.

## Contribution and eligibility

`constraint_contribution(operator, cardinality)` validates the generic pair and
returns the pre-expansion semantic contribution:

```text
all_of(k)  -> k
any_of(k)  -> 1
none_of(k) -> k
```

`eligible_operator_cardinality_pairs(family_plan)` supports only
`same_field_logic`. It walks the canonical generic pair space and retains pairs
whose contribution equals the requested B complexity. This derives exactly:

```text
complexity 1:
  all_of/1, any_of/2, any_of/3, none_of/1

complexity 2:
  all_of/2, none_of/2

complexity 3:
  all_of/3
```

No invalid pair is drawn or retried. Valid plans from every other family are
rejected with an explicit scope error instead of receiving an invented operator.

## Probability implementation

The C sampler uses the same hierarchical conditional principle as frozen B:

```text
P(O=o | context)
  = w_O(o) / sum_{eligible operator}(w_O)

P(K=k | O=o, context)
  = w_K(k|o) / sum_{compatible cardinality}(w_K)

P(O=o, K=k | context)
  = P(O=o | context) * P(K=k | O=o, context)
```

An operator without a compatible cardinality never enters `operator_probabilities`.
Cardinality normalization happens only inside the selected operator's current
eligible set. The implementation never globally normalizes raw operator/cardinality
weight products.

## Synthetic fixture probability output

For `same_field_logic / complexity=1`:

```json
{
  "operator_probabilities": {
    "all_of": 0.45,
    "any_of": 0.3,
    "none_of": 0.25
  },
  "joint_probabilities": {
    "all_of/1": 0.45,
    "any_of/2": 0.24,
    "any_of/3": 0.06,
    "none_of/1": 0.25
  }
}
```

For `same_field_logic / complexity=2`:

```json
{
  "operator_probabilities": {
    "all_of": 0.6428571428571429,
    "none_of": 0.35714285714285715
  },
  "joint_probabilities": {
    "all_of/2": 0.6428571428571429,
    "none_of/2": 0.35714285714285715
  }
}
```

For `same_field_logic / complexity=3`:

```json
{
  "operator_probabilities": {"all_of": 1.0},
  "joint_probabilities": {"all_of/3": 1.0}
}
```

The values come from the offline synthetic fixture and do not claim a production
user distribution.

## RNG and canonical-order contract

The sampler receives caller-owned RNG state. It does not create `Random(seed)` or
use module-global randomness.

```text
complexity 3:
  unique all_of/3
  RNG draws = 0

complexity 2:
  operator draw = 1
  selected operator has deterministic cardinality
  total RNG draws = 1

complexity 1:
  operator draw = 1
  all_of/none_of selected -> total draws = 1
  any_of selected -> conditional cardinality draw = 1 -> total draws = 2
```

Canonical operator order is `all_of, any_of, none_of`; canonical cardinality
order follows each operator's Phase A contract. These orders carry no semantic
priority but affect seeded reproducibility. Changing them requires a sampler
mechanics version bump.

## Automated acceptance

Tests cover:

- all valid and invalid Phase B family/bucket pairs through the new validator;
- all seven generic operator/cardinality pairs and illegal cardinalities;
- every frozen contribution result;
- exact same-field eligible pair sets for complexity 1, 2, and 3;
- explicit rejection of unsupported families, including normalization;
- eligible operator and conditional cardinality probability spaces;
- hierarchical joint formula and normalization sums;
- operator-table and per-operator cardinality-table scale invariance;
- zero/one/two-draw RNG paths;
- equal RNG state producing equal output sequence;
- canonical pair order;
- exact absence of field, values, normalization and downstream record payload.

Final results:

```text
python -m unittest tests.test_operator_cardinality_sampler -v
Ran 23 tests in 0.035s
OK

python -m unittest discover -s tests -v
Ran 112 tests in 0.118s
OK
```

## Boundaries for theory review

1. Confirm contribution-based pair derivation is the intended implementation of
   the frozen same-field matrix, rather than maintaining a second handwritten
   complexity-to-pair lookup table.
2. Confirm a deterministic context still requires the caller to supply an RNG
   object, while consuming zero draws.
3. Confirm the public `OperatorCardinalityPlan` validator should remain generic;
   current-context compatibility is enforced separately by eligible-pair
   membership during planning.
4. Phase C rejects every family other than `same_field_logic`. Structural rules
   for single/cross-field/normalization/reference families remain intentionally
   undefined and unimplemented.

If Phase C passes, authorize only the next bounded module after its theoretical
contract is frozen. Do not infer Phase D from the existing sampler config.
