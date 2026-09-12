"""Value-free semantic atom contracts for future structural planning."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

from anime_pref.schemas.numeric_range import NumericRangePattern
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan


StructuralAtomKind: TypeAlias = Literal[
    "genre_set",
    "tag_set",
    "year_range",
    "episodes_range",
    "format_any",
    "status_any",
    "tag_group_any",
    "tag_group_none",
    "reference",
]


@dataclass(frozen=True)
class StructuralAtom:
    """One value-free structural intent with only kind-specific mechanics.

    Direct set atoms carry an operator/cardinality plan. Numeric atoms carry a
    range pattern. All other kinds need no payload because their kind completely
    defines their v0.1 contribution semantics.
    """

    kind: StructuralAtomKind
    operator_plan: OperatorCardinalityPlan | None = None
    range_pattern: NumericRangePattern | None = None
