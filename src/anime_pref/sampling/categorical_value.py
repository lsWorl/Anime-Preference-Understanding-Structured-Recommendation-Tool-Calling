"""Direct Categorical Value Sampler v0.1.

The caller explicitly supplies ``genres`` or ``tags`` plus an already planned
operator/cardinality. This module selects distinct active direct values. It does
not select the field, expand tag groups, or assemble a SemanticSpec.
"""

from random import Random

from anime_pref.data.query_builder import DomainRules
from anime_pref.data.rules_identity import validate_executable_rules_identity
from anime_pref.schemas.categorical_value import (
    DirectCategoricalField,
    DirectCategoricalValuePlan,
)
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.taxonomy import ExecutableTagSubset
from anime_pref.sampling.config import validate_sampler_config_against_domain
from anime_pref.sampling.family_complexity import (
    _weighted_choice,
    normalize_relative_weights,
)
from anime_pref.sampling.operator_cardinality import (
    validate_operator_cardinality_plan,
)


DIRECT_CATEGORICAL_FIELDS = frozenset({"genres", "tags"})


def _validate_field(field: DirectCategoricalField) -> None:
    """Require the caller to select one of D1's two direct set fields."""
    if not isinstance(field, str) or field not in DIRECT_CATEGORICAL_FIELDS:
        raise ValueError("field must be either 'genres' or 'tags'")


def _active_values(
    field: DirectCategoricalField,
    rules: DomainRules,
) -> tuple[str, ...]:
    """Return active values in canonical lexical order."""
    _validate_field(field)
    # DomainRules exposes frozensets because vocabulary order has no semantics.
    # Sorting here fixes deterministic sampling mechanics for a given version.
    return tuple(sorted(getattr(rules, field)))


def effective_value_weights(
    field: DirectCategoricalField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> dict[str, float]:
    """Resolve one finite positive effective weight for every active value.

    Genre precedence is explicit priority then default. Tag precedence is
    explicit priority, configured tier, then default. Tier and priority are
    alternatives rather than multiplicative factors.
    """
    _validate_field(field)
    validate_sampler_config_against_domain(config, rules, subset)
    values = _active_values(field, rules)

    if field == "genres":
        policy = config.genre_sampling
        weights = {
            value: policy.priority_weights.get(value, policy.default_weight)
            for value in values
        }
    else:
        policy = config.tag_sampling
        weights: dict[str, float] = {}
        for value in values:
            if value in policy.priority_weights:
                # A per-value decision has highest precedence and is not
                # multiplied by a tier weight.
                weight = policy.priority_weights[value]
            elif value in policy.value_tiers:
                tier = policy.value_tiers[value]
                weight = policy.tier_weights[tier]
            else:
                # Absence from value_tiers means untiered. It does not silently
                # assign the semantic label "standard".
                weight = policy.default_weight
            weights[value] = weight

    # Phase A already validates configured weights. Reusing the normalization
    # primitive here additionally proves every selected effective weight remains
    # finite and positive without changing the returned relative values.
    normalize_relative_weights(weights)
    return weights


def initial_value_probabilities(
    field: DirectCategoricalField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> dict[str, float]:
    """Return the theoretical base distribution for the first categorical draw."""
    return normalize_relative_weights(
        effective_value_weights(field, config, rules, subset)
    )


def validate_direct_categorical_sampling_binding(
    field: DirectCategoricalField,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> None:
    """Validate D1 field binding and its base-probability no-dominance guard."""
    probabilities = initial_value_probabilities(field, config, rules, subset)
    policy = config.genre_sampling if field == "genres" else config.tag_sampling
    maximum_probability = max(probabilities.values())

    # maximum_value_share is a base single-draw theoretical guard. It is not an
    # empirical dataset-frequency or without-replacement inclusion guarantee.
    if maximum_probability > policy.maximum_value_share:
        raise ValueError(
            f"{field} base probability {maximum_probability!r} exceeds "
            f"configured maximum_value_share {policy.maximum_value_share!r}"
        )


def validate_direct_categorical_value_plan(
    plan: DirectCategoricalValuePlan,
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> None:
    """Validate generic value-plan shape, canonical order, and active vocabulary."""
    if not isinstance(plan, DirectCategoricalValuePlan):
        raise ValueError("plan must be a DirectCategoricalValuePlan instance")

    _validate_field(plan.field)
    validate_executable_rules_identity(rules, subset)

    values = plan.values
    if not isinstance(values, tuple) or not values:
        raise ValueError("plan.values must be a non-empty tuple")

    for value in values:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                "plan.values must contain canonical non-empty strings"
            )

    if len(values) != len(set(values)):
        raise ValueError("plan.values must not contain duplicates")
    if values != tuple(sorted(values)):
        raise ValueError("plan.values must use canonical lexical order")

    active_values = getattr(rules, plan.field)
    inactive = set(values) - active_values
    if inactive:
        raise ValueError(
            f"plan.values contains values inactive for {plan.field}: "
            f"{sorted(inactive)}"
        )


def validate_direct_categorical_value_context(
    value_plan: DirectCategoricalValuePlan,
    operator_plan: OperatorCardinalityPlan,
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> None:
    """Validate value-plan cardinality against its orthogonal operator plan."""
    validate_direct_categorical_value_plan(value_plan, rules, subset)
    validate_operator_cardinality_plan(operator_plan)
    if len(value_plan.values) != operator_plan.cardinality:
        raise ValueError(
            "value count must equal OperatorCardinalityPlan.cardinality"
        )


def sample_direct_categorical_values(
    field: DirectCategoricalField,
    operator_plan: OperatorCardinalityPlan,
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    rng: Random,
) -> DirectCategoricalValuePlan:
    """Select distinct direct values by sequential weighted sampling.

    Each random step renormalizes weights over remaining candidates. If the last
    remaining value is required, selection is deterministic and consumes no draw.
    The final tuple is sorted so random selection order has no semantic meaning.
    """
    _validate_field(field)
    validate_operator_cardinality_plan(operator_plan)
    validate_direct_categorical_sampling_binding(field, config, rules, subset)
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    weights = effective_value_weights(field, config, rules, subset)
    requested_count = operator_plan.cardinality
    if requested_count > len(weights):
        # Capacity is checked before any draw. D1 never lowers cardinality,
        # duplicates a value, or expands into inactive vocabulary.
        raise ValueError(
            f"requested cardinality {requested_count} exceeds the "
            f"{len(weights)} active {field} values"
        )

    remaining = dict(weights)
    selected: list[str] = []
    while len(selected) < requested_count:
        if len(remaining) == 1:
            # The final required candidate is certain, so consuming randomness
            # would make RNG history depend on an irrelevant implementation step.
            chosen = next(iter(remaining))
        else:
            probabilities = normalize_relative_weights(remaining)
            chosen = _weighted_choice(tuple(remaining), probabilities, rng)

        selected.append(chosen)
        del remaining[chosen]

    plan = DirectCategoricalValuePlan(field, tuple(sorted(selected)))
    validate_direct_categorical_value_context(
        plan,
        operator_plan,
        rules,
        subset,
    )
    return plan
