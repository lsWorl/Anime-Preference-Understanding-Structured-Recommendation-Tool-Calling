"""Immutable contracts for D5A structural-signature selection policy."""

from dataclasses import dataclass

from anime_pref.schemas.family_complexity import ComplexityBucket, SemanticFamily
from anime_pref.schemas.structural_atom import StructuralAtomKind


@dataclass(frozen=True)
class StructuralSignature:
    """Canonical structural slot presence without mechanics or context."""

    atom_kinds: tuple[StructuralAtomKind, ...]


@dataclass(frozen=True)
class StructuralSignatureWeightSpec:
    """One explicit signature allowlist entry in a family/bucket context."""

    semantic_family: SemanticFamily
    complexity_bucket: ComplexityBucket
    atom_kinds: tuple[StructuralAtomKind, ...]
    weight: float


@dataclass(frozen=True)
class StructuralPatternSelectionPolicySpec:
    """Versioned structural-signature allowlist with canonical identity."""

    policy_version: str
    sampler_version: str
    signature_entries: tuple[StructuralSignatureWeightSpec, ...]
    policy_hash: str
