"""D5B. Sequential mechanics-pattern conditional probabilities v0.1.

This module computes P(StructuralPatternPlan | family, complexity, signature).
It follows canonical atom order and conditions each mechanics choice on whether
at least one D4 completion survives. It has no RNG and performs no selection.
"""

from functools import lru_cache
import math
from typing import Literal, TypeAlias

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.operator_cardinality import SetOperator
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.structural_signature import StructuralSignature
from anime_pref.sampling.config import (
    NUMERIC_RANGE_PATTERN_ORDER,
    OPERATOR_CARDINALITY_ORDER,
    SET_OPERATOR_ORDER,
    validate_sampler_config,
)
from anime_pref.sampling.family_complexity import (
    normalize_relative_weights,
    validate_family_complexity_plan,
)
from anime_pref.sampling.structural_pattern import (
    enumerate_eligible_structural_patterns,
    validate_structural_pattern_plan,
)
from anime_pref.sampling.structural_signature import (
    enumerate_eligible_structural_signatures,
    structural_signature,
    validate_structural_signature,
)


SetAtomKind: TypeAlias = Literal["genre_set", "tag_set"]
NumericAtomKind: TypeAlias = Literal["year_range", "episodes_range"]

SET_ATOM_KIND_ORDER: tuple[SetAtomKind, ...] = ("genre_set", "tag_set")
NUMERIC_ATOM_KIND_ORDER: tuple[NumericAtomKind, ...] = (
    "year_range",
    "episodes_range",
)
MECHANICS_BEARING_KINDS = frozenset(
    (*SET_ATOM_KIND_ORDER, *NUMERIC_ATOM_KIND_ORDER)
)


def _validate_set_kind(atom_kind: object) -> None:
    """Require one of the two direct-set structural atom kinds."""
    if atom_kind not in SET_ATOM_KIND_ORDER:
        raise ValueError("atom_kind must be 'genre_set' or 'tag_set'")


def _validate_numeric_kind(atom_kind: object) -> None:
    """Require one of the two direct-numeric structural atom kinds."""
    if atom_kind not in NUMERIC_ATOM_KIND_ORDER:
        raise ValueError("atom_kind must be 'year_range' or 'episodes_range'")


def _validate_survivors(
    survivors: tuple[StructuralPatternPlan, ...],
) -> None:
    """Validate a nonempty immutable survivor state without repairing it."""
    if not isinstance(survivors, tuple) or not survivors:
        raise ValueError("survivors must be a nonempty pattern tuple")
    for pattern in survivors:
        validate_structural_pattern_plan(pattern)


def _atom_for_kind(pattern: StructuralPatternPlan, atom_kind: str):
    """Return the unique atom occupying ``atom_kind`` in a D4 pattern."""
    for atom in pattern.atoms:
        if atom.kind == atom_kind:
            return atom
    raise ValueError(f"survivor does not contain required atom kind {atom_kind!r}")


@lru_cache(maxsize=None)
def mechanics_candidates(
    family_complexity_plan: FamilyComplexityPlan,
    signature: StructuralSignature,
) -> tuple[StructuralPatternPlan, ...]:
    """Return D4 patterns restricted to one eligible structural signature."""
    validate_family_complexity_plan(family_complexity_plan)
    validate_structural_signature(signature)
    eligible_signatures = enumerate_eligible_structural_signatures(
        family_complexity_plan
    )
    if signature not in eligible_signatures:
        raise ValueError("signature is not D4-eligible in this family/complexity context")

    candidates = tuple(
        pattern
        for pattern in enumerate_eligible_structural_patterns(family_complexity_plan)
        if structural_signature(pattern) == signature
    )
    if not candidates:
        # Membership above promises capacity. Reaching this branch indicates
        # drift between D4 enumeration and D5A signature extraction.
        raise ValueError("eligible signature has no D4 mechanics completion")
    return candidates


def feasible_set_operators(
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: SetAtomKind,
) -> tuple[SetOperator, ...]:
    """Return canonical operators with at least one current completion."""
    _validate_survivors(survivors)
    _validate_set_kind(atom_kind)
    present = {
        _atom_for_kind(pattern, atom_kind).operator_plan.operator
        for pattern in survivors
    }
    return tuple(operator for operator in SET_OPERATOR_ORDER if operator in present)


def feasible_set_cardinalities(
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: SetAtomKind,
    operator: SetOperator,
) -> tuple[int, ...]:
    """Return canonical cardinalities with a completion for one operator."""
    _validate_survivors(survivors)
    _validate_set_kind(atom_kind)
    if operator not in SET_OPERATOR_ORDER:
        raise ValueError(f"unknown set operator: {operator!r}")
    present = {
        atom.operator_plan.cardinality
        for pattern in survivors
        for atom in (_atom_for_kind(pattern, atom_kind),)
        if atom.operator_plan.operator == operator
    }
    return tuple(
        cardinality
        for cardinality in OPERATOR_CARDINALITY_ORDER[operator]
        if cardinality in present
    )


def feasible_numeric_patterns(
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: NumericAtomKind,
) -> tuple[str, ...]:
    """Return canonical range patterns with at least one current completion."""
    _validate_survivors(survivors)
    _validate_numeric_kind(atom_kind)
    present = {
        _atom_for_kind(pattern, atom_kind).range_pattern
        for pattern in survivors
    }
    return tuple(
        pattern for pattern in NUMERIC_RANGE_PATTERN_ORDER if pattern in present
    )


def conditional_operator_probabilities(
    config: SemanticSamplerConfigSpec,
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: SetAtomKind,
) -> dict[SetOperator, float]:
    """Normalize Phase-A operator weights over feasible support only."""
    validate_sampler_config(config)
    feasible = feasible_set_operators(survivors, atom_kind)
    if not feasible:
        raise ValueError("set atom has no feasible operator completion")
    weights = {operator: config.operator_weights.weights[operator] for operator in feasible}
    return normalize_relative_weights(weights)


def conditional_cardinality_probabilities(
    config: SemanticSamplerConfigSpec,
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: SetAtomKind,
    operator: SetOperator,
) -> dict[int, float]:
    """Normalize one operator's cardinality table over feasible support."""
    validate_sampler_config(config)
    feasible = feasible_set_cardinalities(survivors, atom_kind, operator)
    if not feasible:
        raise ValueError("selected operator has no feasible cardinality completion")
    cardinality_weights = getattr(config.operator_cardinality, operator)
    weights = {
        cardinality: cardinality_weights[cardinality]
        for cardinality in feasible
    }
    return normalize_relative_weights(weights)


def conditional_numeric_pattern_probabilities(
    config: SemanticSamplerConfigSpec,
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: NumericAtomKind,
) -> dict[str, float]:
    """Normalize the field's Phase-A range-pattern weights over survivors."""
    validate_sampler_config(config)
    feasible = feasible_numeric_patterns(survivors, atom_kind)
    if not feasible:
        raise ValueError("numeric atom has no feasible range-pattern completion")
    policy = (
        config.year_sampling
        if atom_kind == "year_range"
        else config.episode_sampling
    )
    weights = {pattern: policy.pattern_weights[pattern] for pattern in feasible}
    return normalize_relative_weights(weights)


def _filter_set_survivors(
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: SetAtomKind,
    operator: SetOperator,
    cardinality: int,
) -> tuple[StructuralPatternPlan, ...]:
    """Keep completions matching one selected set mechanics payload."""
    return tuple(
        pattern
        for pattern in survivors
        for atom in (_atom_for_kind(pattern, atom_kind),)
        if atom.operator_plan.operator == operator
        and atom.operator_plan.cardinality == cardinality
    )


def _filter_numeric_survivors(
    survivors: tuple[StructuralPatternPlan, ...],
    atom_kind: NumericAtomKind,
    range_pattern: str,
) -> tuple[StructuralPatternPlan, ...]:
    """Keep completions matching one selected numeric mechanics payload."""
    return tuple(
        pattern
        for pattern in survivors
        if _atom_for_kind(pattern, atom_kind).range_pattern == range_pattern
    )


def mechanics_pattern_probabilities(
    config: SemanticSamplerConfigSpec,
    family_complexity_plan: FamilyComplexityPlan,
    signature: StructuralSignature,
) -> dict[StructuralPatternPlan, float]:
    """Compute the sequential feasibility-conditioned mechanics distribution."""
    validate_sampler_config(config)
    validate_family_complexity_plan(family_complexity_plan)
    validate_structural_signature(signature)
    candidates = mechanics_candidates(family_complexity_plan, signature)

    # Each state contains all D4 completions sharing mechanics decisions made so
    # far and the probability mass of that decision path. Option probabilities
    # depend on support presence and Phase-A weights, never survivor counts.
    states: tuple[tuple[tuple[StructuralPatternPlan, ...], float], ...] = (
        (candidates, 1.0),
    )
    for atom_kind in signature.atom_kinds:
        if atom_kind not in MECHANICS_BEARING_KINDS:
            # Payload-free atoms have local probability factor 1.
            continue

        next_states: list[
            tuple[tuple[StructuralPatternPlan, ...], float]
        ] = []
        for survivors, path_probability in states:
            if atom_kind in SET_ATOM_KIND_ORDER:
                operator_probabilities = conditional_operator_probabilities(
                    config,
                    survivors,
                    atom_kind,
                )
                for operator, operator_probability in operator_probabilities.items():
                    operator_survivors = tuple(
                        pattern
                        for pattern in survivors
                        if _atom_for_kind(
                            pattern,
                            atom_kind,
                        ).operator_plan.operator
                        == operator
                    )
                    cardinality_probabilities = (
                        conditional_cardinality_probabilities(
                            config,
                            operator_survivors,
                            atom_kind,
                            operator,
                        )
                    )
                    for cardinality, cardinality_probability in (
                        cardinality_probabilities.items()
                    ):
                        remaining = _filter_set_survivors(
                            operator_survivors,
                            atom_kind,
                            operator,
                            cardinality,
                        )
                        next_states.append(
                            (
                                remaining,
                                path_probability
                                * operator_probability
                                * cardinality_probability,
                            )
                        )
            else:
                range_probabilities = conditional_numeric_pattern_probabilities(
                    config,
                    survivors,
                    atom_kind,
                )
                for range_pattern, range_probability in range_probabilities.items():
                    remaining = _filter_numeric_survivors(
                        survivors,
                        atom_kind,
                        range_pattern,
                    )
                    next_states.append(
                        (
                            remaining,
                            path_probability * range_probability,
                        )
                    )
        states = tuple(next_states)

    probabilities: dict[StructuralPatternPlan, float] = {}
    for survivors, path_probability in states:
        if len(survivors) != 1:
            raise ValueError("mechanics traversal did not resolve one D4 pattern")
        pattern = survivors[0]
        if pattern in probabilities:
            raise ValueError("duplicate mechanics path resolved the same D4 pattern")
        probabilities[pattern] = path_probability

    # Preserve D4 canonical mechanics order rather than sorting by probability.
    ordered = {pattern: probabilities[pattern] for pattern in candidates}
    if any(not math.isfinite(value) or value <= 0 for value in ordered.values()):
        raise ValueError("mechanics probabilities must be finite and positive")
    if not math.isclose(sum(ordered.values()), 1.0, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("mechanics probabilities do not sum to one")
    return ordered
