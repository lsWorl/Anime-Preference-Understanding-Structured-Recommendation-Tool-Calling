"""Immutable resource and support contracts for E1 domain bindability."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceTitlePoolSpec:
    """Versioned deterministic offline pool for a single reference slot."""

    pool_version: str
    titles: tuple[str, ...]


@dataclass(frozen=True)
class TagGroupBindingPlan:
    """One value-free assignment of group identities to normalization slots."""

    any_of_group: str | None = None
    none_of_group: str | None = None

