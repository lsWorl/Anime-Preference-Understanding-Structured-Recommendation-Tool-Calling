"""Direct Numeric Range Value Sampler v0.1.

The caller supplies both numeric field and range pattern. Single endpoints and
bounded lower endpoints use pool-then-uniform-value sampling. A bounded upper is
sampled by globally conditioning every value's original base marginal on
``upper >= lower``.
"""

from collections.abc import Mapping
from random import Random
from typing import TypeVar

from anime_pref.data.query_builder import DomainRules, NumericRule
from anime_pref.data.rules_identity import domain_rules_sha256
from anime_pref.schemas.numeric_range import (
    DirectNumericField,
    DirectNumericRangePlan,
    NumericRangePattern,
)
from anime_pref.schemas.sampler_config import (
    NumericSamplingPolicySpec,
    SemanticSamplerConfigSpec,
)
from anime_pref.sampling.config import (
    NUMERIC_RANGE_PATTERNS,
    NUMERIC_VALUE_POOL_ORDER,
    validate_sampler_config,
)
from anime_pref.sampling.family_complexity import (
    _weighted_choice,
    normalize_relative_weights,
)


DIRECT_NUMERIC_FIELDS = frozenset({"year", "episodes"})
ChoiceT = TypeVar("ChoiceT")


def _validate_numeric_field(field: DirectNumericField) -> None:
    """Require the caller to explicitly choose year or episodes."""
    if not isinstance(field, str) or field not in DIRECT_NUMERIC_FIELDS:
        raise ValueError("numeric field must be either 'year' or 'episodes'")


def _validate_range_pattern(pattern: NumericRangePattern) -> None:
    """Require one of the three caller-selected canonical range patterns."""
    if not isinstance(pattern, str) or pattern not in NUMERIC_RANGE_PATTERNS:
        raise ValueError(
            "range pattern must be min_only, max_only, or bounded_range"
        )


def _validate_rules_hash(rules: DomainRules) -> None:
    """Validate the standalone DomainRules shape and canonical content hash."""
    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")
    if rules.rules_hash != domain_rules_sha256(rules):
        raise ValueError("rules.rules_hash does not match DomainRules content")


def _numeric_policy(
    field: DirectNumericField,
    config: SemanticSamplerConfigSpec,
) -> NumericSamplingPolicySpec:
    """Return the already validated field-specific numeric sampling policy."""
    return config.year_sampling if field == "year" else config.episode_sampling


def _numeric_rule(field: DirectNumericField, rules: DomainRules) -> NumericRule:
    """Return the corresponding validity guard, not a sampling universe."""
    return rules.year if field == "year" else rules.episodes


def _policy_pool_values(
    policy: NumericSamplingPolicySpec,
) -> dict[str, tuple[int, ...]]:
    """Expose configured pools in canonical source order without moving values."""
    return {
        pool: getattr(policy, f"{pool}_values")
        for pool in NUMERIC_VALUE_POOL_ORDER
    }


def validate_numeric_sampling_binding(
    field: DirectNumericField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
) -> None:
    """Validate numeric pools against the selected DomainRules validity range."""
    _validate_numeric_field(field)
    validate_sampler_config(config)
    _validate_rules_hash(rules)

    rule = _numeric_rule(field, rules)
    policy = _numeric_policy(field, config)
    for pool, values in _policy_pool_values(policy).items():
        for value in values:
            if rule.minimum is not None and value < rule.minimum:
                raise ValueError(
                    f"{field} pool {pool!r} contains {value}, below "
                    f"DomainRules minimum {rule.minimum}"
                )
            if rule.maximum is not None and value > rule.maximum:
                raise ValueError(
                    f"{field} pool {pool!r} contains {value}, above "
                    f"DomainRules maximum {rule.maximum}"
                )


def numeric_constraint_contribution(pattern: NumericRangePattern) -> int:
    """Return the hard-clause contribution of a direct numeric range pattern."""
    _validate_range_pattern(pattern)
    return 2 if pattern == "bounded_range" else 1


def numeric_value_pools(
    field: DirectNumericField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
) -> dict[str, tuple[int, ...]]:
    """Return only the configured field pools after actual validity binding."""
    validate_numeric_sampling_binding(field, config, rules)
    return _policy_pool_values(_numeric_policy(field, config))


def numeric_pool_probabilities(
    field: DirectNumericField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
) -> dict[str, float]:
    """Compute P(S) from the three configured pool relative weights."""
    validate_numeric_sampling_binding(field, config, rules)
    policy = _numeric_policy(field, config)
    ordered_weights = {
        pool: policy.pool_weights[pool]
        for pool in NUMERIC_VALUE_POOL_ORDER
    }
    return normalize_relative_weights(ordered_weights)


def base_numeric_value_probabilities(
    field: DirectNumericField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
) -> dict[int, float]:
    """Compute P0(v) = P(pool(v)) / original_pool_size in ascending order."""
    pools = numeric_value_pools(field, config, rules)
    pool_probabilities = numeric_pool_probabilities(field, config, rules)
    value_probabilities: dict[int, float] = {}

    for pool in NUMERIC_VALUE_POOL_ORDER:
        values = pools[pool]
        uniform_probability = pool_probabilities[pool] / len(values)
        for value in values:
            value_probabilities[value] = uniform_probability

    # Pools are individually ascending but their numeric regions can interleave.
    # Global ascending order fixes endpoint sampling mechanics across all pools.
    return {
        value: value_probabilities[value]
        for value in sorted(value_probabilities)
    }


def conditioned_upper_probabilities(
    field: DirectNumericField,
    lower: int,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
) -> dict[int, float]:
    """Condition original base marginals globally on the event ``value >= lower``."""
    if isinstance(lower, bool) or not isinstance(lower, int):
        raise ValueError("lower must be an integer")

    base = base_numeric_value_probabilities(field, config, rules)
    if lower not in base:
        raise ValueError("lower must come from the configured numeric value pools")

    surviving = {
        value: probability
        for value, probability in base.items()
        if value >= lower
    }
    # lower itself survives, so a valid sampler-produced lower guarantees this
    # mapping is nonempty. Normalizing base marginals performs global
    # conditioning without re-uniformizing partially surviving pools.
    return normalize_relative_weights(surviving)


def _choose_probability_candidate(
    probabilities: Mapping[ChoiceT, float],
    rng: Random,
) -> ChoiceT:
    """Choose from an ordered probability mapping with zero draw for a singleton."""
    if not probabilities:
        raise ValueError("candidate probability mapping must not be empty")
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    choices = tuple(probabilities)
    if len(choices) == 1:
        return choices[0]
    return _weighted_choice(choices, probabilities, rng)


def _sample_base_endpoint(
    field: DirectNumericField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    rng: Random,
) -> int:
    """Sample pool by relative weight, then sample uniformly inside that pool."""
    pools = numeric_value_pools(field, config, rules)
    pool_probabilities = numeric_pool_probabilities(field, config, rules)
    selected_pool = _choose_probability_candidate(pool_probabilities, rng)

    # Uniform is an explicit numeric-policy contract. Unit relative weights make
    # that contract visible while reusing the common deterministic chooser.
    values = pools[selected_pool]
    uniform_probabilities = normalize_relative_weights(
        {value: 1.0 for value in values}
    )
    return _choose_probability_candidate(uniform_probabilities, rng)


def validate_direct_numeric_range_plan(
    plan: DirectNumericRangePlan,
    rules: DomainRules,
) -> None:
    """Validate generic canonical range semantics and DomainRules bounds."""
    if not isinstance(plan, DirectNumericRangePlan):
        raise ValueError("plan must be a DirectNumericRangePlan instance")

    _validate_numeric_field(plan.field)
    _validate_range_pattern(plan.range_pattern)
    _validate_rules_hash(rules)

    for name, endpoint in (
        ("minimum", plan.minimum),
        ("maximum", plan.maximum),
    ):
        if endpoint is not None and (
            isinstance(endpoint, bool) or not isinstance(endpoint, int)
        ):
            raise ValueError(f"{name} must be an integer or None")

    if plan.range_pattern == "min_only":
        if plan.minimum is None or plan.maximum is not None:
            raise ValueError("min_only requires minimum and forbids maximum")
    elif plan.range_pattern == "max_only":
        if plan.minimum is not None or plan.maximum is None:
            raise ValueError("max_only requires maximum and forbids minimum")
    else:
        if plan.minimum is None or plan.maximum is None:
            raise ValueError("bounded_range requires both minimum and maximum")
        if plan.minimum > plan.maximum:
            raise ValueError("bounded_range requires minimum <= maximum")

    rule = _numeric_rule(plan.field, rules)
    for name, endpoint in (
        ("minimum", plan.minimum),
        ("maximum", plan.maximum),
    ):
        if endpoint is None:
            continue
        if rule.minimum is not None and endpoint < rule.minimum:
            raise ValueError(f"{name} is below DomainRules validity minimum")
        if rule.maximum is not None and endpoint > rule.maximum:
            raise ValueError(f"{name} is above DomainRules validity maximum")


def sample_direct_numeric_range(
    field: DirectNumericField,
    range_pattern: NumericRangePattern,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    rng: Random,
) -> DirectNumericRangePlan:
    """Sample one canonical direct numeric range from configured pools only."""
    _validate_numeric_field(field)
    _validate_range_pattern(range_pattern)
    validate_numeric_sampling_binding(field, config, rules)
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    first_endpoint = _sample_base_endpoint(field, config, rules, rng)
    if range_pattern == "min_only":
        plan = DirectNumericRangePlan(field, range_pattern, first_endpoint, None)
    elif range_pattern == "max_only":
        plan = DirectNumericRangePlan(field, range_pattern, None, first_endpoint)
    else:
        # Lower uses the ordinary base hierarchy. Upper has no pool-selection
        # stage: it is a direct draw from globally conditioned base marginals.
        upper_probabilities = conditioned_upper_probabilities(
            field,
            first_endpoint,
            config,
            rules,
        )
        upper = _choose_probability_candidate(upper_probabilities, rng)
        plan = DirectNumericRangePlan(
            field,
            range_pattern,
            first_endpoint,
            upper,
        )

    validate_direct_numeric_range_plan(plan, rules)
    return plan
