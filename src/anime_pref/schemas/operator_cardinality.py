"""Immutable output contract for direct set-logic sampling v0.1."""

from dataclasses import dataclass
from typing import Literal, TypeAlias


SetOperator: TypeAlias = Literal["all_of", "any_of", "none_of"]


@dataclass(frozen=True)
class OperatorCardinalityPlan:
    """One direct set-logic operator and its pre-expansion item count.

    The plan intentionally has no genre/tag field and no values. Cardinality
    counts semantic items before any normalization expansion.
    """

    operator: SetOperator
    cardinality: int
