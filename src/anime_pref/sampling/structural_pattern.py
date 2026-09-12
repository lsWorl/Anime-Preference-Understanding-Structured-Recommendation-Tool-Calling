"""D4. Structural Pattern Eligibility Contract v0.1.

This module enumerates a finite, deterministic space of value-free structural
patterns. It validates eligibility only: it has no RNG, probability weights,
domain binding, concrete values, or SemanticSpec assembly.
"""

from itertools import product

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.sampling.config import (
    NUMERIC_RANGE_PATTERN_ORDER,
    OPERATOR_CARDINALITY_ORDER,
    SET_OPERATOR_ORDER,
)
from anime_pref.sampling.family_complexity import validate_family_complexity_plan
from anime_pref.sampling.structural_atom import (
    STRUCTURAL_ATOM_KIND_ORDER,
    validate_structural_atom,
    structural_constraint_count,
)


_KIND_INDEX = {kind: index for index, kind in enumerate(STRUCTURAL_ATOM_KIND_ORDER)}
_OPERATOR_INDEX = {operator: index for index, operator in enumerate(SET_OPERATOR_ORDER)}
_RANGE_PATTERN_INDEX = {
    pattern: index for index, pattern in enumerate(NUMERIC_RANGE_PATTERN_ORDER)
}

_DIRECT_HARD_KINDS = frozenset(
    {
        "genre_set",
        "tag_set",
        "year_range",
        "episodes_range",
        "format_any",
        "status_any",
    }
)
_SET_KINDS = frozenset({"genre_set", "tag_set"})
_GROUP_KINDS = frozenset({"tag_group_any", "tag_group_none"})


def _atom_sort_key(atom: StructuralAtom) -> tuple[int, int, int]:
    """Return the frozen deterministic order key for one validated atom."""
    validate_structural_atom(atom)
    kind_index = _KIND_INDEX[atom.kind]

    if atom.kind in _SET_KINDS:
        operator = atom.operator_plan.operator
        cardinality = atom.operator_plan.cardinality
        return (
            kind_index,
            _OPERATOR_INDEX[operator],
            OPERATOR_CARDINALITY_ORDER[operator].index(cardinality),
        )

    if atom.kind in {"year_range", "episodes_range"}:
        return (kind_index, _RANGE_PATTERN_INDEX[atom.range_pattern], 0)

    return (kind_index, 0, 0)


def _matches_complexity_bucket(count: int, bucket: object) -> bool:
    """Match an exact D3 count to B's exact buckets or open 5_plus bucket."""
    if bucket == "5_plus":
        return count >= 5
    if bucket == 0:
        return count == 0
    return count == int(bucket)


def _validate_slot_uniqueness(atoms: tuple[StructuralAtom, ...]) -> None:
    """Enforce the single-slot D4 contract for every frozen atom kind."""
    kinds = tuple(atom.kind for atom in atoms)
    if len(kinds) != len(set(kinds)):
        raise ValueError("each structural atom kind may occupy at most one D4 slot")


def _validate_family_rules(plan: StructuralPatternPlan, count: int) -> None:
    """Apply frozen family priority and family-specific structural rules."""
    family = plan.semantic_family
    atoms = plan.atoms
    kinds = {atom.kind for atom in atoms}
    has_reference = "reference" in kinds
    has_group = bool(kinds & _GROUP_KINDS)

    if family == "single_constraint":
        if len(atoms) != 1 or has_reference or has_group:
            raise ValueError("single_constraint requires exactly one direct hard atom")
        if atoms[0].kind not in _DIRECT_HARD_KINDS or count != 1:
            raise ValueError("single_constraint atom must contribute exactly one clause")
        return

    if family == "same_field_logic":
        if len(atoms) != 1 or atoms[0].kind not in _SET_KINDS:
            raise ValueError("same_field_logic requires one genre_set or tag_set atom")
        return

    if family == "cross_field_composition":
        if has_reference or has_group:
            raise ValueError("cross_field_composition forbids reference and tag groups")
        direct_kinds = kinds & _DIRECT_HARD_KINDS
        if len(atoms) != len(direct_kinds) or len(direct_kinds) < 2:
            raise ValueError("cross_field_composition requires two direct hard fields")
        return

    if family == "normalization":
        if not has_group:
            raise ValueError("normalization requires a tag-group atom")
        return

    if family == "reference_only":
        if atoms != (StructuralAtom("reference"),):
            raise ValueError("reference_only must contain exactly one reference atom")
        return

    if family == "reference_composition":
        if not has_reference or has_group:
            raise ValueError(
                "reference_composition requires reference and forbids tag groups"
            )
        hard_atoms = tuple(atom for atom in atoms if atom.kind != "reference")
        if not hard_atoms or any(atom.kind not in _DIRECT_HARD_KINDS for atom in hard_atoms):
            raise ValueError("reference_composition requires at least one direct hard atom")
        return

    # Family validity is normally rejected earlier by Phase B. Keeping this
    # explicit branch makes the helper robust if called independently later.
    raise ValueError(f"unknown semantic family: {family!r}")


def validate_structural_pattern_plan(plan: StructuralPatternPlan) -> None:
    """Validate canonical order, slots, family eligibility, and exact capacity."""
    if not isinstance(plan, StructuralPatternPlan):
        raise ValueError("plan must be a StructuralPatternPlan instance")

    family_plan = FamilyComplexityPlan(
        plan.semantic_family,
        plan.complexity_bucket,
    )
    validate_family_complexity_plan(family_plan)

    if not isinstance(plan.atoms, tuple):
        raise ValueError("StructuralPatternPlan.atoms must be a tuple")
    for atom in plan.atoms:
        validate_structural_atom(atom)

    # Validation never sorts or repairs caller input. Canonical representation
    # is part of candidate identity and therefore must already be present.
    if plan.atoms != tuple(sorted(plan.atoms, key=_atom_sort_key)):
        raise ValueError("structural atoms are not in canonical order")

    _validate_slot_uniqueness(plan.atoms)
    count = structural_constraint_count(plan.atoms)
    if not _matches_complexity_bucket(count, plan.complexity_bucket):
        raise ValueError(
            f"actual structural count {count} does not match "
            f"bucket {plan.complexity_bucket!r}"
        )
    _validate_family_rules(plan, count)


def _variants_for_kind(kind: str) -> tuple[StructuralAtom, ...]:
    """Build one kind's finite payload variants in frozen mechanics order."""
    if kind in _SET_KINDS:
        return tuple(
            StructuralAtom(
                kind,
                operator_plan=OperatorCardinalityPlan(operator, cardinality),
            )
            for operator in SET_OPERATOR_ORDER
            for cardinality in OPERATOR_CARDINALITY_ORDER[operator]
        )
    if kind in {"year_range", "episodes_range"}:
        return tuple(
            StructuralAtom(kind, range_pattern=pattern)
            for pattern in NUMERIC_RANGE_PATTERN_ORDER
        )
    return (StructuralAtom(kind),)


def _enumerate_canonical_atom_tuples():
    """Yield every finite one-per-slot atom tuple in canonical kind order."""
    # None represents an unused schema slot. Cartesian enumeration is finite:
    # direct kinds have only their frozen C/D2 payload variants, and all group,
    # format, status, and reference kinds have one payload-free variant.
    slot_options = tuple(
        (None, *_variants_for_kind(kind))
        for kind in STRUCTURAL_ATOM_KIND_ORDER
    )
    for choices in product(*slot_options):
        yield tuple(atom for atom in choices if atom is not None)


def enumerate_eligible_structural_patterns(
    family_complexity_plan: FamilyComplexityPlan,
) -> tuple[StructuralPatternPlan, ...]:
    """Return all deterministic abstract candidates for one valid B plan.

    A zero-capacity query returns ``()``. This pure query does not choose among
    candidates; a later, separately frozen probability contract owns selection.
    """
    validate_family_complexity_plan(family_complexity_plan)

    eligible: list[StructuralPatternPlan] = []
    seen: set[StructuralPatternPlan] = set()
    for atoms in _enumerate_canonical_atom_tuples():
        candidate = StructuralPatternPlan(
            semantic_family=family_complexity_plan.semantic_family,
            complexity_bucket=family_complexity_plan.complexity_bucket,
            atoms=atoms,
        )
        try:
            validate_structural_pattern_plan(candidate)
        except ValueError:
            continue
        if candidate not in seen:
            seen.add(candidate)
            eligible.append(candidate)

    return tuple(eligible)
