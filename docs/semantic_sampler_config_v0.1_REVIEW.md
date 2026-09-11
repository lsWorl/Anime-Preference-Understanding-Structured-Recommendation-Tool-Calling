# Review Bundle: Semantic Sampler Config / Contract v0.1

## Scope and status

This bundle covers only phase A of Offline Semantic Sampler v0.1:

```text
versioned sampler JSON
        ↓
strict immutable config model
        ↓
standalone invariants
        ↓
binding to actual synthetic DomainRules + ExecutableTagSubset
```

Status: **offline implementation PASS candidate**.

- Full suite: 54 tests passed, no skips or failures.
- Sampler-config tests: 6 passed.
- Python compilation and `git diff --check` passed.
- No SemanticSpec sequence, DatasetRecord sequence, user text, or production dataset was generated.

## Relevant files

```text
src/anime_pref/schemas/sampler_config.py
src/anime_pref/sampling/__init__.py
src/anime_pref/sampling/config.py
tests/fixtures/semantic_sampler.synthetic.v0.1.json
tests/test_sampler_config.py
docs/semantic_sampler_config_v0.1.md
```

The implementation reuses the explicitly synthetic rules and subset fixtures under `tests/fixtures/`.

## Config structure

`SemanticSamplerConfigSpec` contains:

```text
sampler_version
seed
family_weights
constraint_count_weights
operator_weights
operator_cardinality
genre_sampling
tag_sampling
year_sampling
episode_sampling
combination_policy_version
audit_tolerances
```

Nested immutable contracts are `WeightTableSpec`, `OperatorCardinalityPolicySpec`, `CategoricalValuePolicySpec`, `TagValuePolicySpec`, `NumericSamplingPolicySpec`, and `DistributionAuditToleranceSpec`.

Loaded mappings are copied into `MappingProxyType`; JSON arrays become tuples. Numeric pools must already use ascending canonical order. The loader does not sort or repair invalid input.

## Standalone invariants

Family keys are exactly:

```text
single_constraint
same_field_logic
cross_field_composition
normalization
reference_only
reference_composition
```

Hard-complexity buckets are `1 / 2 / 3 / 4 / 5_plus`. Generic operators are `all_of / any_of / none_of`.

Cardinality is limited to:

```text
all_of: 1, 2, 3
any_of: 2, 3
none_of: 1, 2
```

Weights are finite positive relative weights. Consumers normalize them later; they do not need to sum to `1.0`.

Coverage counts are positive integers. Share and audit ratios are in `(0, 1]`. Tag tiers are restricted to `core`, `standard`, and `edge`.

Numeric policy separates `min_only / max_only / bounded_range` from `common / catalog_region / long_tail` value pools. Pools are nonempty, strictly ascending, internally unique, mutually disjoint, and contain positive non-bool integers. Standalone validation does not hardcode domain bounds.

## Rules/subset binding

`validate_sampler_config_against_domain(config, rules, subset)` first validates the standalone config and previously frozen executable-rules identity. It then requires:

- genre priority keys belong to active `rules.genres`;
- tag priority and value-tier keys belong to active `rules.tags`;
- all numeric values satisfy versioned DomainRules validity bounds;
- positive normalization-family weight has at least one available tag group;
- inactive approved tags need not appear in sampler value policy.

Reference-family weights do not imply that a title pool exists. No title is invented in phase A.

## Synthetic fixture boundary

The fixture contains frozen complexity and generic operator ratios. Exact family weights, cardinality weights, genre priorities, tag tiers, numeric pools, audit tolerances, and combination-policy identifier are synthetic mechanics data unless separately frozen later.

These values are not claimed to reflect users or catalog statistics. The file name and sampler version explicitly contain `synthetic`. Production execution remains blocked by real taxonomy → reviewed subset → production DomainRules and later catalog/title inputs.

## Automated acceptance

The six phase-A tests cover:

- complete loading and immutable mappings;
- exact nested key sets;
- invalid or nonfinite weights;
- illegal operator cardinality;
- duplicate, overlapping, unsorted, boolean, or invalid numeric values;
- invalid identifiers, seed, coverage, tiers, and tolerances;
- inactive genre/tag policy keys;
- numeric values outside DomainRules validity;
- missing normalization groups;
- actual rules/subset identity validation.

Final result:

```text
python -B -m unittest discover -s tests -v
Ran 54 tests in 0.045s
OK
```

## Boundaries for theory review

1. Family/count compatibility remains phase B.
2. `combination_policy_version` is only a reference; concrete plausibility rules remain phase E.
3. Production numerical distributions remain unfrozen.
4. Tag tier assignment is currently optional: configured keys must be active, while an active tag without a tier can later use `default_weight`. Please confirm this fallback before phase D.
5. “Weak genre priority” has no frozen maximum ratio. Phase A validates positive finite weights without inventing a threshold.
6. Reference families remain configurable without creating a title pool.

If phase A passes, authorize only the next bounded module, expected to be **B. Family + Complexity Planner**.
