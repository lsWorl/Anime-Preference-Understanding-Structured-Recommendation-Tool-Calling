"""Data contracts for AniList taxonomy snapshots and reviewed tag subsets."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxonomyTagSpec:
    """Global tag identity; media-specific relevance rank is intentionally absent."""

    id: int
    name: str
    description: str | None
    category: str
    is_general_spoiler: bool
    is_adult: bool


@dataclass(frozen=True)
class CanonicalTaxonomySnapshot:
    """Canonical taxonomy content used as the input to the snapshot hash."""

    snapshot_schema_version: str
    genres: tuple[str, ...]
    tags: tuple[TaxonomyTagSpec, ...]


@dataclass(frozen=True)
class TaxonomySnapshotManifest:
    """Snapshot provenance and counts excluded from the canonical content hash."""

    source: str
    resource: tuple[str, ...]
    fetched_at_utc: str
    genre_count: int
    tag_count: int
    canonical_sha256: str
    snapshot_schema_version: str


@dataclass(frozen=True)
class TagAuditRecordSpec:
    """Explicit human decision bound to one canonical snapshot hash."""

    tag_id: int
    tag_name: str
    category: str
    approved: bool
    reason: str
    aliases: tuple[str, ...]
    is_general_spoiler: bool
    is_adult: bool
    source_snapshot_hash: str


@dataclass(frozen=True)
class ExecutableTagSpec:
    """Approved tag exported to the executable vocabulary.

    Aliases are retained for future normalization; the review reason remains
    in the audit record and is not duplicated in the executable subset.
    """

    tag_id: int
    tag_name: str
    category: str
    aliases: tuple[str, ...]
    is_general_spoiler: bool
    is_adult: bool


@dataclass(frozen=True)
class ExecutableTagSubset:
    """Versioned approved subset linked to, but distinct from, the full snapshot."""

    subset_version: str
    derived_from_snapshot_hash: str
    tags: tuple[ExecutableTagSpec, ...]


@dataclass(frozen=True)
class ExecutableTagSubsetManifest:
    """Subset identity, source snapshot identity, version, and approved count."""

    subset_version: str
    subset_hash: str
    derived_from_snapshot_hash: str
    approved_tag_count: int
