# Review Bundle: D2. Direct Numeric Range Value Sampler v0.1

## Scope and status

```text
explicit year/episodes
+ explicit min_only/max_only/bounded_range
+ validated config/DomainRules
        ↓
pool relative probabilities
        ↓
uniform value within original pool
        ↓
single bound or bounded lower
        ↓
bounded upper global conditioning
        ↓
DirectNumericRangePlan
```

Status: **offline implementation PASS candidate**.

- D2-specific tests: 26 passed.
- Full offline suite: 162 passed, no skips or failures.
- Python compilation and `git diff --check` passed.
- Detailed implementation and parameter walkthrough:
  `docs/numeric_range_sampler_v0.1_IMPLEMENTATION.md`.
- No structural planner, SemanticSpec, DatasetRecord, text, E～G, or production
  numeric generation was implemented.

## Relevant files

```text
src/anime_pref/schemas/numeric_range.py
src/anime_pref/sampling/config.py
src/anime_pref/sampling/numeric_range.py
tests/test_numeric_range_sampler.py
docs/numeric_range_sampler_v0.1_IMPLEMENTATION.md
docs/numeric_range_sampler_v0.1_REVIEW.md
```

## Implemented probability contract

Pool selection:

```text
P(S=s) = w_s / sum(w)
```

Uniform value inside the selected original pool:

```text
P(V=v | S=s) = 1 / original_pool_size(s)
P0(v) = P(S=s) / original_pool_size(s)
```

Bounded upper after sampled lower `L`:

```text
eligible = {v | v >= L}
P(U=v | L) = P0(v) / sum(P0(u), u >= L)
```

The implementation preserves the original pool-size denominator when only part
of a pool survives. It does not perform hierarchical pool re-selection for upper.

## Canonical output and validation

`DirectNumericRangePlan` contains exactly field, range pattern, minimum and maximum.
The public validator rejects bool endpoints, malformed pattern/bound combinations,
reversed bounds, invalid fields/patterns, modified DomainRules identity, and values
outside the field's DomainRules validity bounds. Equal endpoints are valid.

Generic validity deliberately does not require endpoints to belong to sampler pools.
The sampler itself only produces pool values, preserving the frozen distinction:

```text
DomainRules validity range != sampler candidate pools
```

## RNG mechanics

- Lower/single endpoint: pool stage and uniform-value stage each consume one draw
  only when their candidate count exceeds one.
- Bounded upper: direct global conditioned draw; no upper pool stage.
- Singleton candidates consume zero draws.
- Bounded range consumes at most three meaningful draws.
- Caller supplies and owns RNG state.

Canonical pool order is common, catalog_region, long_tail. Global numeric candidate
and upper orders are ascending. These orders carry no semantic priority but affect
seeded reproducibility.

## Representative outputs

Synthetic fixtures with `Random(2026)`:

```text
year / bounded_range
draws: 0.1191198849, 0.5025157552, 0.5118227128
lower: 2010
global-conditioned upper: 2020
output: minimum=2010, maximum=2020

episodes / max_only
draws: 0.1191198849, 0.5025157552
output: minimum=None, maximum=24
```

The full probability arithmetic appears in the implementation report.

## Automated acceptance

The D2 suite covers:

- pool uniform and exact base marginals;
- unequal pool-size effects;
- pool-weight scale invariance for base and conditioned distributions;
- configured-pool-only candidates and global ascending order;
- single-bound pool/value hierarchy;
- singleton zero-draw mechanics;
- bounded lower using the base hierarchy;
- upper `>= lower`, equal endpoint, and global conditioning;
- original denominator for a partially surviving pool;
- no upper pool-selection stage and maximum three draws;
- deterministic output from equal RNG state;
- contribution `1/1/2`;
- validity/pool separation;
- binding failure before RNG;
- explicit field/pattern and pattern-weight non-consumption;
- absence of downstream payload.

```text
python -m unittest tests.test_numeric_range_sampler -v
Ran 26 tests in 0.073s
OK

python -m unittest discover -s tests -v
Ran 162 tests in 0.172s
OK
```

## Boundaries for theory review

1. Confirm the implementation of pool-uniform base marginals and globally
   conditioned upper probabilities.
2. Confirm `conditioned_upper_probabilities()` requiring lower to be a configured
   candidate is appropriate for a D2 helper whose lower must be sampler-produced.
3. Confirm standalone DomainRules hash validation is sufficient for numeric-only
   D2, which does not consume executable tag subset data.
4. Confirm canonical pool and numeric orders are frozen sampler mechanics.

If D2 passes, authorize only the next explicitly frozen module. Structural planning
and E～G remain unimplemented.
