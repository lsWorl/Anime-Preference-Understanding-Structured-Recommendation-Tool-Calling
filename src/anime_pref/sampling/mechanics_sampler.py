"""D5C2. Sequential caller-owned RNG sampling of mechanics patterns.

This module executes the D5B conditional process M ~ P(M | F,C,S).  It keeps
the original D4 candidate tuple as a survivor set, narrows that tuple after
each mechanics decision, and returns its unique value-free completion.  It
does not read D5A signature policy weights or bind any concrete domain value.
"""

from collections.abc import Mapping
from typing import Hashable, Protocol, TypeVar

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.structural_signature import StructuralSignature
from anime_pref.sampling.config import validate_sampler_config
from anime_pref.sampling.family_complexity import (
    _weighted_choice,
    validate_family_complexity_plan,
)
from anime_pref.sampling.mechanics_probability import (
    MECHANICS_BEARING_KINDS,
    NUMERIC_ATOM_KIND_ORDER,
    SET_ATOM_KIND_ORDER,
    _atom_for_kind,
    _filter_numeric_survivors,
    _filter_set_survivors,
    conditional_cardinality_probabilities,
    conditional_numeric_pattern_probabilities,
    conditional_operator_probabilities,
    mechanics_candidates,
)
from anime_pref.sampling.structural_pattern import validate_structural_pattern_plan
from anime_pref.sampling.structural_signature import validate_structural_signature


ChoiceT = TypeVar("ChoiceT", bound=Hashable)


class RandomSource(Protocol):
    """Minimal interface supplied by the caller for reproducible sampling."""

    def random(self) -> float:
        """Return the next pseudorandom draw in the RNG's native sequence."""


def _choose_probability_candidate(
    probabilities: Mapping[ChoiceT, float],
    rng: RandomSource,
) -> ChoiceT:
    """Choose in mapping order, consuming no draw for deterministic support."""
    choices = tuple(probabilities)
    if not choices:
        # A D5B conditional helper should never expose empty feasible support.
        # Raising here makes contract drift explicit instead of inventing a
        # fallback or entering a rejection loop.
        raise ValueError("conditional probability mapping must not be empty")
    if len(choices) == 1:
        return choices[0]
    return _weighted_choice(choices, probabilities, rng)


def _filter_operator_survivors(
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: str,
    operator: str,
) -> tuple[StructuralPatternPlan, ...]:
    """Keep the current completions carrying one selected set operator."""
    remaining = tuple(
        pattern
        for pattern in survivors
        if _atom_for_kind(pattern, atom_kind).operator_plan.operator == operator
    )
    if not remaining:
        # conditional_operator_probabilities() includes only options with a D4
        # completion, so emptiness is an internal invariant failure.
        raise ValueError("selected operator has no surviving D4 completion")
    return remaining


def sample_mechanics_pattern(
    sampler_config: SemanticSamplerConfigSpec,
    family_complexity_plan: FamilyComplexityPlan,
    structural_signature: StructuralSignature,
    rng: RandomSource,
) -> StructuralPatternPlan:
    """Sample the frozen sequential distribution P(M | F,C,S).

    Every conditional stage draws once only when it has multiple feasible
    choices.  Singleton stages and payload-free atoms consume no RNG state.
    The function never retries: D5B feasibility guarantees that each selected
    branch retains at least one valid D4 completion.
    """
    # Keep all caller-controlled failures before the first possible draw.  The
    # final call also proves that the selected signature is D4-eligible in this
    # exact family/complexity context and supplies canonical survivor order.
    validate_sampler_config(sampler_config)
    validate_family_complexity_plan(family_complexity_plan)
    validate_structural_signature(structural_signature)
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")
    survivors = mechanics_candidates(
        family_complexity_plan,
        structural_signature,
    )

    # structural_signature validation guarantees D3 canonical atom-kind order.
    # Payload-free atoms have no local mechanics choice and therefore leave both
    # survivors and RNG state untouched.
    for atom_kind in structural_signature.atom_kinds:
        if atom_kind not in MECHANICS_BEARING_KINDS:
            continue

        if atom_kind in SET_ATOM_KIND_ORDER:
            operator_probabilities = conditional_operator_probabilities(
                sampler_config,
                survivors,
                atom_kind,
            )
            operator = _choose_probability_candidate(
                operator_probabilities,
                rng,
            )
            operator_survivors = _filter_operator_survivors(
                survivors,
                atom_kind,
                operator,
            )

            cardinality_probabilities = conditional_cardinality_probabilities(
                sampler_config,
                operator_survivors,
                atom_kind,
                operator,
            )
            cardinality = _choose_probability_candidate(
                cardinality_probabilities,
                rng,
            )
            survivors = _filter_set_survivors(
                operator_survivors,
                atom_kind,
                operator,
                cardinality,
            )
        elif atom_kind in NUMERIC_ATOM_KIND_ORDER:
            range_probabilities = conditional_numeric_pattern_probabilities(
                sampler_config,
                survivors,
                atom_kind,
            )
            range_pattern = _choose_probability_candidate(
                range_probabilities,
                rng,
            )
            survivors = _filter_numeric_survivors(
                survivors,
                atom_kind,
                range_pattern,
            )

        if not survivors:
            # This cannot occur for valid D5B helper output.  It is defensive
            # detection of implementation drift, never a signal to resample.
            raise ValueError("mechanics selection removed every D4 completion")

    if len(survivors) != 1:
        raise ValueError("mechanics traversal did not resolve one D4 pattern")

    result = survivors[0]
    validate_structural_pattern_plan(result)
    return result
