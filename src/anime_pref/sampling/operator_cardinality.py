"""Direct Set-Logic Operator + Cardinality Sampler v0.1.

Only ``same_field_logic`` plans are supported here. The module chooses a generic
direct genre/tag set operator and its pre-expansion cardinality without choosing
the field or values and without handling tag-group normalization.
"""

from collections.abc import Mapping
from random import Random

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.operator_cardinality import (
    OperatorCardinalityPlan,
    SetOperator,
)
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.sampling.config import (
    OPERATOR_CARDINALITIES,
    OPERATOR_CARDINALITY_ORDER,
    SET_OPERATOR_ORDER,
    validate_sampler_config,
)
from anime_pref.sampling.family_complexity import (
    _weighted_choice,
    normalize_relative_weights,
    validate_family_complexity_plan,
)


def validate_operator_cardinality_plan(plan: OperatorCardinalityPlan) -> None:
    """Validate the generic operator/cardinality contract of a direct plan."""
    if not isinstance(plan, OperatorCardinalityPlan):
        raise ValueError("plan must be an OperatorCardinalityPlan instance")

    operator = plan.operator
    if not isinstance(operator, str) or operator not in OPERATOR_CARDINALITIES:
        raise ValueError(f"unknown direct set operator: {operator!r}")

    cardinality = plan.cardinality
    if isinstance(cardinality, bool) or not isinstance(cardinality, int):
        raise ValueError("cardinality must be an integer")

    if cardinality not in OPERATOR_CARDINALITIES[operator]:
        raise ValueError(
            f"cardinality {cardinality!r} is invalid for operator {operator!r}"
        )


def constraint_contribution(operator: SetOperator, cardinality: int) -> int:
    """Return the hard-clause contribution of one direct set-logic atom.

    ``all_of`` and ``none_of`` contribute one clause per item. A nonempty
    ``any_of`` collection is one OR clause regardless of whether it contains two
    or three items.
    """
    candidate = OperatorCardinalityPlan(operator, cardinality)
    validate_operator_cardinality_plan(candidate)

    if operator == "any_of":
        return 1
    return cardinality


def _require_same_field_logic_plan(plan: FamilyComplexityPlan) -> int:
    """Validate a phase-B plan and return its exact C-supported complexity."""
    validate_family_complexity_plan(plan)

    if plan.semantic_family != "same_field_logic":
        raise ValueError(
            "C v0.1 supports only the same_field_logic semantic family"
        )

    # Phase B guarantees this family can contain only the exact string buckets
    # 1, 2, and 3. Conversion is safe after public plan validation.
    return int(plan.complexity_bucket)


def eligible_operator_cardinality_pairs(
    family_plan: FamilyComplexityPlan,
) -> tuple[tuple[SetOperator, int], ...]:
    """Derive every pair whose contribution equals the requested complexity."""
    required_contribution = _require_same_field_logic_plan(family_plan)
    eligible: list[tuple[SetOperator, int]] = []

    # Iterate only canonical tuples. This order affects seeded reproducibility,
    # while carrying no semantic preference of its own.
    for operator in SET_OPERATOR_ORDER:
        for cardinality in OPERATOR_CARDINALITY_ORDER[operator]:
            if constraint_contribution(operator, cardinality) == required_contribution:
                eligible.append((operator, cardinality))

    if not eligible:
        # This indicates drift between the frozen phase-B compatibility matrix
        # and the direct set contribution contract, rather than a retry case.
        raise ValueError(
            "same_field_logic plan has no eligible operator/cardinality pair"
        )

    return tuple(eligible)


def operator_probabilities(
    config: SemanticSamplerConfigSpec,
    family_plan: FamilyComplexityPlan,
) -> dict[SetOperator, float]:
    """Compute P(O|context) over operators with at least one eligible pair."""
    validate_sampler_config(config)
    eligible_pairs = eligible_operator_cardinality_pairs(family_plan)

    eligible_operators = {operator for operator, _ in eligible_pairs}
    ordered_weights = {
        operator: config.operator_weights.weights[operator]
        for operator in SET_OPERATOR_ORDER
        if operator in eligible_operators
    }
    return normalize_relative_weights(ordered_weights)


def conditional_cardinality_probabilities(
    config: SemanticSamplerConfigSpec,
    family_plan: FamilyComplexityPlan,
    operator: SetOperator,
) -> dict[int, float]:
    """Compute P(K|O,context) over the selected operator's eligible counts."""
    validate_sampler_config(config)
    eligible_pairs = eligible_operator_cardinality_pairs(family_plan)

    eligible_cardinalities = {
        cardinality
        for candidate_operator, cardinality in eligible_pairs
        if candidate_operator == operator
    }
    if not eligible_cardinalities:
        raise ValueError(
            f"operator {operator!r} is not eligible for the supplied family plan"
        )

    # Attribute lookup is safe only after eligibility proves operator is one of
    # the three frozen generic operators.
    cardinality_weights: Mapping[int, float] = getattr(
        config.operator_cardinality,
        operator,
    )
    ordered_weights = {
        cardinality: cardinality_weights[cardinality]
        for cardinality in OPERATOR_CARDINALITY_ORDER[operator]
        if cardinality in eligible_cardinalities
    }
    return normalize_relative_weights(ordered_weights)


def joint_operator_cardinality_probabilities(
    config: SemanticSamplerConfigSpec,
    family_plan: FamilyComplexityPlan,
) -> dict[tuple[SetOperator, int], float]:
    """Compute P(O,K|context) with hierarchical conditional normalization."""
    operators = operator_probabilities(config, family_plan)
    eligible_pairs = eligible_operator_cardinality_pairs(family_plan)
    conditionals = {
        operator: conditional_cardinality_probabilities(
            config,
            family_plan,
            operator,
        )
        for operator in operators
    }

    # The eligible tuple supplies canonical pair order. We multiply normalized
    # operator and conditional probabilities; raw pair products are never
    # globally normalized.
    return {
        (operator, cardinality): (
            operators[operator] * conditionals[operator][cardinality]
        )
        for operator, cardinality in eligible_pairs
    }


def sample_operator_cardinality_plan(
    config: SemanticSamplerConfigSpec,
    family_plan: FamilyComplexityPlan,
    rng: Random,
) -> OperatorCardinalityPlan:
    """Sample one direct set-logic atom while consuming only necessary draws."""
    validate_sampler_config(config)
    eligible_pairs = eligible_operator_cardinality_pairs(family_plan)
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    operators = operator_probabilities(config, family_plan)
    operator_choices = tuple(operators)
    if len(operator_choices) == 1:
        operator = operator_choices[0]
    else:
        operator = _weighted_choice(operator_choices, operators, rng)

    cardinalities = conditional_cardinality_probabilities(
        config,
        family_plan,
        operator,
    )
    cardinality_choices = tuple(cardinalities)
    if len(cardinality_choices) == 1:
        cardinality = cardinality_choices[0]
    else:
        cardinality = _weighted_choice(cardinality_choices, cardinalities, rng)

    plan = OperatorCardinalityPlan(operator, cardinality)
    validate_operator_cardinality_plan(plan)

    # The public validator checks the generic contract; this membership check
    # additionally protects the current same-field context.
    if (plan.operator, plan.cardinality) not in eligible_pairs:
        raise ValueError("sampled operator/cardinality pair is context-incompatible")

    return plan
