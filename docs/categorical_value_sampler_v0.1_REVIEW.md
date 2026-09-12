# Review Bundle: D1. Direct Categorical Value Sampler v0.1

## Scope and status

```text
explicit field (genres/tags)
+ OperatorCardinalityPlan
+ validated config/rules/subset
        ↓
active direct value universe
        ↓
priority/tier/default effective weights
        ↓
base-probability no-dominance validation
        ↓
sequential weighted sampling without replacement
        ↓
canonical DirectCategoricalValuePlan
```

Status: **offline implementation PASS candidate**.

- D1-specific tests: 24 passed.
- Full offline suite: 136 passed, no skips or failures.
- Python compilation and `git diff --check` passed.
- Full implementation walkthrough: `docs/categorical_value_sampler_v0.1_IMPLEMENTATION.md`.

## Relevant files

```text
src/anime_pref/schemas/categorical_value.py
src/anime_pref/sampling/categorical_value.py
tests/test_categorical_value_sampler.py
docs/categorical_value_sampler_v0.1_IMPLEMENTATION.md
docs/categorical_value_sampler_v0.1_REVIEW.md
```

## Implemented contract

- The caller must explicitly choose `genres` or `tags`.
- Genre candidates equal active `DomainRules.genres`.
- Tag candidates equal active `DomainRules.tags` after full rules/subset identity validation.
- Inactive approved and unreviewed/rejected tags cannot enter the universe.
- Genre weight precedence is explicit priority then default.
- Tag weight precedence is explicit priority, then configured tier, then default.
- Priority and tier weights are not multiplied.
- Untiered tags remain untiered and use default weight.
- All effective weights remain finite positive relative weights.
- `maximum_value_share` guards the largest initial single-draw probability.
- `minimum_coverage_per_value` does not create stateful quota behavior in D1.
- Requested cardinality must fit the active distinct-value capacity.
- Selection is sequential weighted sampling without replacement.
- Remaining weights are renormalized after every removal.
- A required final singleton is deterministic and consumes no RNG draw.
- Final values are distinct and canonical sorted, independent of draw order.
- Equal config/context/RNG state produces equal output.

## Public validation layers

`validate_direct_categorical_value_plan()` checks object type, field, nonempty tuple,
canonical strings/order, duplicates, active vocabulary, and actual subset/rules
identity.

`validate_direct_categorical_value_context()` additionally validates the orthogonal
operator plan and requires `len(values) == operator_plan.cardinality`.

`validate_direct_categorical_sampling_binding()` computes initial probabilities and
rejects a config/domain binding whose maximum value exceeds the field's configured
`maximum_value_share`.

## Example evidence

With the synthetic fixtures and `Random(2026)`:

```text
field: genres
operator/cardinality: any_of / 3
draw order: Comedy -> Music -> Mecha
canonical output: Comedy, Mecha, Music
RNG draws: 3
```

For active tags with the same RNG:

```text
field: tags
operator/cardinality: any_of / 3
active universe size: 3
draw order: Female Harem -> Mixed Gender Harem -> Male Harem
last value deterministic
canonical output: Female Harem, Male Harem, Mixed Gender Harem
RNG draws: 2
```

The detailed arithmetic and every function call are recorded in the implementation
report.

## Automated acceptance

Tests cover all theory-requested D1 boundaries, including active/inactive values,
unreviewed/rejected tags, three-level precedence, no multiplicative double boost,
finite positive weights, scale invariance, max-share acceptance and failure,
minimum-coverage non-interference, capacity failure before draws, cardinality
1/2/3, no duplicates, re-normalization, no rejection loop, canonical ordering,
explicit RNG, final-singleton draw avoidance, deterministic output, generic and
context validators, and the absence of downstream fields.

```text
python -m unittest tests.test_categorical_value_sampler -v
Ran 24 tests
OK

python -m unittest discover -s tests -v
Ran 136 tests
OK
```

## Boundaries for theory review

1. Confirm `maximum_value_share` is correctly enforced by a D1-specific binding
   validator and by the sampler, while pure probability helpers remain inspectable.
2. Confirm canonical lexical order is the deterministic mechanics order for active
   genre/tag values and requires a sampler-version bump if changed.
3. Confirm validation layering between generic value-plan validity and
   operator-cardinality context compatibility.
4. D1 remains an atomic sampler and deliberately does not enforce dataset-level
   minimum coverage.

If D1 passes, authorize only the next explicitly frozen module. D2 numeric sampling
has not been inferred or implemented.
