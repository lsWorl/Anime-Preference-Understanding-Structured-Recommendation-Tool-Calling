"""Immutable output contract for direct numeric range sampling v0.1."""

from dataclasses import dataclass
from typing import Literal, TypeAlias


DirectNumericField: TypeAlias = Literal["year", "episodes"]
NumericRangePattern: TypeAlias = Literal[
    "min_only",
    "max_only",
    "bounded_range",
]


@dataclass(frozen=True)
class DirectNumericRangePlan:
    """Canonical inclusive bounds for one caller-selected numeric field."""

    field: DirectNumericField
    range_pattern: NumericRangePattern
    minimum: int | None
    maximum: int | None
