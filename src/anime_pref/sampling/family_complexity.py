"""Family + Complexity Planner v0.1.

This module plans only a semantic family and a compatible complexity bucket.
It must not create SemanticSpec, DatasetRecord, operators, values, or user text.
"""

from collections.abc import Mapping, Sequence
import math
from random import Random
from types import MappingProxyType
from typing import TypeVar

from anime_pref.schemas.family_complexity import (
    ComplexityBucket,
    FamilyComplexityPlan,
    SemanticFamily,
)
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.sampling.config import (
    HARD_CONSTRAINT_COUNT_BUCKET_ORDER,
    SEMANTIC_FAMILY_ORDER,
    validate_sampler_config,
)

FAMILY_COMPLEXITY_COMPATIBILITY = MappingProxyType(
    {
        "single_constraint": ("1",),
        "same_field_logic": ("1", "2", "3"),
        "cross_field_composition": ("2", "3", "4", "5_plus"),
        "normalization": ("1", "2", "3", "4", "5_plus"),
        "reference_only": (0,),
        "reference_composition": ("1", "2", "3", "4", "5_plus"),
    }
)

ChoiceT = TypeVar("ChoiceT")


def validate_family_complexity_plan(plan: FamilyComplexityPlan) -> None:
    """Validate a planner result or an externally constructed phase-B plan.

    The type aliases on the dataclass are static hints only. This explicit
    validator protects later sampling stages from invalid direct construction,
    including Python's surprising ``False == 0`` behavior.
    """
    if not isinstance(plan, FamilyComplexityPlan):
        raise ValueError("plan must be a FamilyComplexityPlan instance")

    family = plan.semantic_family
    if not isinstance(family, str) or family not in FAMILY_COMPLEXITY_COMPATIBILITY:
        raise ValueError(f"unknown semantic family: {family!r}")

    bucket = plan.complexity_bucket
    if isinstance(bucket, bool) or not isinstance(bucket, (int, str)):
        raise ValueError(f"invalid complexity bucket: {bucket!r}")

    if bucket not in FAMILY_COMPLEXITY_COMPATIBILITY[family]:
        raise ValueError(
            f"complexity bucket {bucket!r} is incompatible with family {family!r}"
        )


def normalize_relative_weights(
    weights: Mapping[ChoiceT, float],
) -> dict[ChoiceT, float]:
    """Return normalized probabilities without mutating the input mapping."""
    # TODO-B01 implementation contract:
    # 1. Reject an empty mapping.
    # 2. Re-check every value is a finite positive number and reject bool.
    # 3. Divide each weight by the total while preserving input key order.
    # 4. Do not round the probabilities and do not require the input sum to be 1.
    if not isinstance(weights, Mapping):
        raise ValueError("weights must be a mapping")

    if not weights:
        raise ValueError("weights must not be empty")

    total: int | float = 0

    for key, weight in weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"weight for {key!r} must be a number")

        if isinstance(weight, float) and not math.isfinite(weight):
            raise ValueError(f"weight for {key!r} must be finite")

        if weight <= 0:
            raise ValueError(f"weight for {key!r} must be greater than zero")

        total += weight

    if isinstance(total, float) and not math.isfinite(total):
        raise ValueError("weight total must be finite")

    return {key: weight / total for key, weight in weights.items()}


def compatible_complexity_buckets(
    family: SemanticFamily,
) -> tuple[ComplexityBucket, ...]:
    """Return the frozen compatible bucket tuple for one semantic family."""
    # TODO-B02 implementation contract:
    # Reject unknown families explicitly. Return the immutable tuple from the
    # compatibility contract; never derive candidates with retry/rejection.
    if not isinstance(family, str) or family not in FAMILY_COMPLEXITY_COMPATIBILITY:
        raise ValueError(f"unknown semantic family: {family!r}")

    return FAMILY_COMPLEXITY_COMPATIBILITY[family]


def family_probabilities(
    config: SemanticSamplerConfigSpec,
) -> dict[SemanticFamily, float]:
    """Compute P(F) from normalized family relative weights."""
    # TODO-B03 implementation contract:
    # Validate the config, then normalize family weights in
    # SEMANTIC_FAMILY_ORDER. Do not use constraint-count weights here.
    validate_sampler_config(config)

    ordered_weights = {
        family: config.family_weights.weights[family]
        for family in SEMANTIC_FAMILY_ORDER
    }

    return normalize_relative_weights(ordered_weights)


def conditional_complexity_probabilities(
    config: SemanticSamplerConfigSpec,
    family: SemanticFamily,
) -> dict[ComplexityBucket, float]:
    """Compute P(C|F) using only buckets compatible with ``family``."""
    # TODO-B04 implementation contract:
    # - reference_only returns {0: 1.0} without reading/normalizing a zero weight;
    # - hard-bearing families restrict the global count table to their compatible
    #   buckets and normalize again within that restricted table;
    # - incompatible buckets must not appear in the returned mapping;
    # - 5_plus must remain the string bucket "5_plus".
    validate_sampler_config(config)

    compatible_buckets = compatible_complexity_buckets(family)

    if family == "reference_only":
        return {0: 1.0}

    compatible_set = set(compatible_buckets)

    ordered_weights = {
        bucket: config.constraint_count_weights.weights[bucket]
        for bucket in HARD_CONSTRAINT_COUNT_BUCKET_ORDER
        if bucket in compatible_set
    }

    return normalize_relative_weights(ordered_weights)


def joint_family_complexity_probabilities(
    config: SemanticSamplerConfigSpec,
) -> dict[tuple[SemanticFamily, ComplexityBucket], float]:
    """Compute P(F,C) = P(F) * P(C|F) for every compatible pair."""
    # TODO-B05 implementation contract:
    # Iterate SEMANTIC_FAMILY_ORDER and each family's compatible tuple. Multiply
    # normalized family probability by that family's conditional probability.
    # Do not globally normalize raw family_weight * count_weight products.
    family_distribution = family_probabilities(config)

    joint_distribution: dict[
        tuple[SemanticFamily, ComplexityBucket],
        float,
    ] = {}

    for family in SEMANTIC_FAMILY_ORDER:
        conditional_distribution = conditional_complexity_probabilities(
            config,
            family,
        )

        for bucket in compatible_complexity_buckets(family):
            joint_distribution[(family, bucket)] = (
                family_distribution[family] * conditional_distribution[bucket]
            )

    return joint_distribution


def complexity_marginal_probabilities(
    config: SemanticSamplerConfigSpec,
) -> dict[ComplexityBucket, float]:
    """Compute P(C) by summing the joint distribution over families."""
    # TODO-B06 implementation contract:
    # Aggregate the joint probabilities into canonical bucket order
    # (0, 1, 2, 3, 4, 5_plus). This is a pure theoretical helper for future G;
    # do not implement sampled-distribution audit/reporting here.
    joint_distribution = joint_family_complexity_probabilities(config)

    bucket_order: tuple[ComplexityBucket, ...] = (
        0,
        *HARD_CONSTRAINT_COUNT_BUCKET_ORDER,
    )

    marginal_distribution = {bucket: 0.0 for bucket in bucket_order}

    for (_, bucket), probability in joint_distribution.items():
        marginal_distribution[bucket] += probability

    return marginal_distribution


def _weighted_choice(
    choices: Sequence[ChoiceT],
    probabilities: Mapping[ChoiceT, float],
    rng: Random,
) -> ChoiceT:
    """Select one ordered choice using exactly one ``rng.random()`` draw."""
    # TODO-B07 implementation contract:
    # Traverse choices in the supplied order, using one cumulative-probability
    # draw. Handle the tiny floating-point tail by returning the final choice.
    # Never instantiate Random here and never use module-level random functions.
    if not choices:
        raise ValueError("choices must not be empty")

    draw = rng.random()
    cumulative_probability = 0.0
    final_choice = choices[-1]

    for choice in choices:
        cumulative_probability += probabilities[choice]

        if draw < cumulative_probability:
            return choice

    return final_choice


def sample_family_complexity_plan(
    config: SemanticSamplerConfigSpec,
    rng: Random,
) -> FamilyComplexityPlan:
    """Sample one hierarchical family/complexity plan with explicit RNG state."""
    # TODO-B08 implementation contract:
    # 1. Validate config and require an explicit RNG object with random().
    # 2. Sample family once in SEMANTIC_FAMILY_ORDER from P(F).
    # 3. reference_only returns bucket 0 immediately: consume no second draw.
    # 4. Otherwise sample once from the compatible conditional distribution,
    #    using HARD_CONSTRAINT_COUNT_BUCKET_ORDER filtered by compatibility.
    # 5. Return FamilyComplexityPlan only. Do not create downstream objects.
    validate_sampler_config(config)

    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    family_distribution = family_probabilities(config)

    family = _weighted_choice(
        SEMANTIC_FAMILY_ORDER,
        family_distribution,
        rng,
    )

    if family == "reference_only":
        return FamilyComplexityPlan(
            semantic_family=family,
            complexity_bucket=0,
        )

    compatible_set = set(compatible_complexity_buckets(family))

    complexity_choices = tuple(
        bucket
        for bucket in HARD_CONSTRAINT_COUNT_BUCKET_ORDER
        if bucket in compatible_set
    )

    conditional_distribution = conditional_complexity_probabilities(
        config,
        family,
    )

    complexity_bucket = _weighted_choice(
        complexity_choices,
        conditional_distribution,
        rng,
    )

    plan = FamilyComplexityPlan(
        semantic_family=family,
        complexity_bucket=complexity_bucket,
    )
    validate_family_complexity_plan(plan)
    return plan
