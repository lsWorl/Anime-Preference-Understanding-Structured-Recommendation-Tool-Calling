"""Immutable output contract for D4 structural-pattern eligibility."""

from dataclasses import dataclass

from anime_pref.schemas.family_complexity import ComplexityBucket, SemanticFamily
from anime_pref.schemas.structural_atom import StructuralAtom


@dataclass(frozen=True)
class StructuralPatternPlan:
    """One canonical, value-free structural pattern for a family/bucket pair.

    The plan deliberately carries atoms rather than selected domain values. Its
    exact hard-clause count is derived through D3 and is never stored separately.
    """

    semantic_family: SemanticFamily
    complexity_bucket: ComplexityBucket
    atoms: tuple[StructuralAtom, ...]
