"""Immutable output contract for direct categorical value sampling v0.1."""

from dataclasses import dataclass
from typing import Literal, TypeAlias


DirectCategoricalField: TypeAlias = Literal["genres", "tags"]


@dataclass(frozen=True)
class DirectCategoricalValuePlan:
    """A canonical set of direct active values for one caller-selected field.

    Operator and cardinality remain in the orthogonal
    ``OperatorCardinalityPlan``. Values contain direct taxonomy entries only;
    tag-group normalization targets are outside D1.
    """

    field: DirectCategoricalField
    values: tuple[str, ...]
