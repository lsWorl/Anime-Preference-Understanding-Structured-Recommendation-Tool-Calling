"""Immutable contracts for the reviewed F1 pilot generation manifest."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

from anime_pref.schemas.structural_pattern import StructuralPatternPlan


PilotSplit: TypeAlias = Literal["train", "validation", "test"]


@dataclass(frozen=True)
class PilotPatternCase:
    """One reviewed structural case with a fixed template and seed schedule."""

    case_id: str
    structural_pattern: StructuralPatternPlan
    generation_family: str
    template_id: str
    split: PilotSplit
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class PilotPatternManifest:
    """Versioned deterministic source of all pilot generation cases."""

    manifest_version: str
    dataset_version: str
    cases: tuple[PilotPatternCase, ...]

