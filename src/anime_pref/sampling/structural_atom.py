"""Structural Atom Contract v0.1.

This module validates value-free atoms and computes pre-expansion hard-clause
counts. It does not select atom combinations, sample values, consume randomness,
or assemble a SemanticSpec.
"""

from collections.abc import Sequence

from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.sampling.numeric_range import numeric_constraint_contribution
from anime_pref.sampling.operator_cardinality import (
    constraint_contribution,
    validate_operator_cardinality_plan,
)


STRUCTURAL_ATOM_KIND_ORDER = (
    "genre_set",
    "tag_set",
    "year_range",
    "episodes_range",
    "format_any",
    "status_any",
    "tag_group_any",
    "tag_group_none",
    "reference",
)
STRUCTURAL_ATOM_KINDS = frozenset(STRUCTURAL_ATOM_KIND_ORDER)
DIRECT_SET_ATOM_KINDS = frozenset({"genre_set", "tag_set"})
NUMERIC_RANGE_ATOM_KINDS = frozenset({"year_range", "episodes_range"})


def validate_structural_atom(atom: StructuralAtom) -> None:
    """Validate one atom's kind-specific, value-free payload contract."""
    if not isinstance(atom, StructuralAtom):
        raise ValueError("atom must be a StructuralAtom instance")
    if not isinstance(atom.kind, str) or atom.kind not in STRUCTURAL_ATOM_KINDS:
        raise ValueError(f"unknown structural atom kind: {atom.kind!r}")

    if atom.kind in DIRECT_SET_ATOM_KINDS:
        if atom.operator_plan is None:
            raise ValueError(f"{atom.kind} requires operator_plan")
        validate_operator_cardinality_plan(atom.operator_plan)
        if atom.range_pattern is not None:
            raise ValueError(f"{atom.kind} must not carry range_pattern")
        return

    if atom.kind in NUMERIC_RANGE_ATOM_KINDS:
        if atom.operator_plan is not None:
            raise ValueError(f"{atom.kind} must not carry operator_plan")
        if atom.range_pattern is None:
            raise ValueError(f"{atom.kind} requires range_pattern")
        # Reuse D2 as the only source for valid patterns and their contribution
        # semantics instead of maintaining another handwritten pattern table.
        numeric_constraint_contribution(atom.range_pattern)
        return

    # format/status OR, tag-group any/none and reference have no variable
    # mechanics in D3. Their kind alone defines contribution. In particular,
    # tag_group_all is absent from the frozen kind set.
    if atom.operator_plan is not None or atom.range_pattern is not None:
        raise ValueError(f"{atom.kind} must not carry operator or range payload")


def structural_atom_contribution(atom: StructuralAtom) -> int:
    """Return one atom's local pre-expansion hard contribution.

    The aggregate helper applies the cross-atom TAG_ANY merge rule. Calling this
    local helper for a direct tag-any atom and a group-any atom returns one for
    each, so callers needing a total must use ``structural_constraint_count``.
    """
    validate_structural_atom(atom)

    if atom.kind in DIRECT_SET_ATOM_KINDS:
        return constraint_contribution(
            atom.operator_plan.operator,
            atom.operator_plan.cardinality,
        )
    if atom.kind in NUMERIC_RANGE_ATOM_KINDS:
        return numeric_constraint_contribution(atom.range_pattern)
    if atom.kind == "reference":
        return 0

    # format_any, status_any, tag_group_any, and tag_group_none each represent
    # one local semantic clause before aggregate TAG_ANY handling.
    return 1


def _participates_in_combined_tag_any(atom: StructuralAtom) -> bool:
    """Return whether this atom contributes to the single final TAG_ANY clause."""
    if atom.kind == "tag_group_any":
        return True
    return (
        atom.kind == "tag_set"
        and atom.operator_plan is not None
        and atom.operator_plan.operator == "any_of"
    )


def structural_constraint_count(atoms: Sequence[StructuralAtom]) -> int:
    """Aggregate pre-expansion hard clauses with combined TAG_ANY semantics."""
    if not isinstance(atoms, Sequence) or isinstance(atoms, (str, bytes)):
        raise ValueError("atoms must be a sequence of StructuralAtom objects")

    total = 0
    combined_tag_any_present = False
    for atom in atoms:
        validate_structural_atom(atom)

        if _participates_in_combined_tag_any(atom):
            # Any number of direct/group ANY sources still materialize as one
            # final tags.any_of OR clause, so record presence instead of adding.
            combined_tag_any_present = True
            continue

        # Direct tag none remains item-additive through Phase C contribution;
        # every group-none atom is a separate pre-expansion concept and adds one.
        total += structural_atom_contribution(atom)

    if combined_tag_any_present:
        total += 1
    return total
