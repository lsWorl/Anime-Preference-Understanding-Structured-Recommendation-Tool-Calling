"""Load and validate the minimal E1 reference-title pool resource."""

import json
from pathlib import Path

from anime_pref.schemas.domain_bindability import ReferenceTitlePoolSpec


def validate_reference_title_pool(pool: ReferenceTitlePoolSpec) -> None:
    """Validate canonical strings, uniqueness, and deterministic title order."""
    if not isinstance(pool, ReferenceTitlePoolSpec):
        raise ValueError("reference_title_pool must be a ReferenceTitlePoolSpec")
    if (
        not isinstance(pool.pool_version, str)
        or not pool.pool_version
        or pool.pool_version != pool.pool_version.strip()
    ):
        raise ValueError(
            "reference title pool version must be a canonical non-empty string"
        )
    if not isinstance(pool.titles, tuple):
        raise ValueError("reference title pool titles must be a tuple")

    for title in pool.titles:
        if (
            not isinstance(title, str)
            or not title
            or title != title.strip()
        ):
            raise ValueError(
                "reference titles must be canonical non-empty strings"
            )
    if len(pool.titles) != len(set(pool.titles)):
        raise ValueError("reference titles must be unique")
    if pool.titles != tuple(sorted(pool.titles)):
        # Validation rejects upstream nondeterminism instead of silently sorting
        # it and hiding a resource-construction error.
        raise ValueError("reference titles must use canonical sorted order")


def load_reference_title_pool(path: Path) -> ReferenceTitlePoolSpec:
    """Load one strict JSON pool and preserve its reviewed canonical ordering."""
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to read or parse reference title pool") from exc
    if not isinstance(raw, dict) or set(raw) != {"pool_version", "titles"}:
        raise ValueError(
            "reference title pool must contain exactly pool_version and titles"
        )
    if not isinstance(raw["titles"], list):
        raise ValueError("reference title pool titles must be a JSON list")

    pool = ReferenceTitlePoolSpec(
        pool_version=raw["pool_version"],
        titles=tuple(raw["titles"]),
    )
    validate_reference_title_pool(pool)
    return pool

