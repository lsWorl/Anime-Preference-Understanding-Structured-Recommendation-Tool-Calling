"""Immutable output contract for Family + Complexity Planner v0.1."""

from dataclasses import dataclass
from typing import Literal, TypeAlias


SemanticFamily: TypeAlias = Literal[
    "single_constraint",
    "same_field_logic",
    "cross_field_composition",
    "normalization",
    "reference_only",
    "reference_composition",
]

ComplexityBucket: TypeAlias = Literal[0, "1", "2", "3", "4", "5_plus"]


@dataclass(frozen=True)
class FamilyComplexityPlan:
    """One family choice and its compatible hard-complexity bucket.

    ``5_plus`` remains a bucket meaning at least five hard clauses. This object
    intentionally carries no exact constraint count and no SemanticSpec fields.
    """

    semantic_family: SemanticFamily
    complexity_bucket: ComplexityBucket
