"""Immutable configuration contracts for Offline Semantic Sampler v0.1."""

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class WeightTableSpec:
    """Named positive relative weights; consumers normalize when sampling."""

    weights: Mapping[str, float]


@dataclass(frozen=True)
class OperatorCardinalityPolicySpec:
    """Allowed pre-expansion item counts and relative weights per operator."""

    all_of: Mapping[int, float]
    any_of: Mapping[int, float]
    none_of: Mapping[int, float]


@dataclass(frozen=True)
class CategoricalValuePolicySpec:
    """Coverage-first policy plus optional weak per-value priority overrides."""

    minimum_coverage_per_value: int
    maximum_value_share: float
    default_weight: float
    priority_weights: Mapping[str, float]


@dataclass(frozen=True)
class TagValuePolicySpec:
    """Coverage policy with optional core/standard/edge review tiers."""

    minimum_coverage_per_value: int
    maximum_value_share: float
    default_weight: float
    priority_weights: Mapping[str, float]
    tier_weights: Mapping[str, float]
    value_tiers: Mapping[str, str]


@dataclass(frozen=True)
class NumericSamplingPolicySpec:
    """Pattern weights and configurable semantic-cutoff value pools."""

    pattern_weights: Mapping[str, float]
    pool_weights: Mapping[str, float]
    common_values: tuple[int, ...]
    catalog_region_values: tuple[int, ...]
    long_tail_values: tuple[int, ...]


@dataclass(frozen=True)
class DistributionAuditToleranceSpec:
    """Configurable tolerances used later by distribution audit reports."""

    family_max_absolute_error: float
    constraint_count_max_absolute_error: float
    operator_max_absolute_error: float
    minimum_value_coverage_ratio: float
    maximum_signature_share: float


@dataclass(frozen=True)
class SemanticSamplerConfigSpec:
    """Complete Offline Semantic Sampler configuration contract v0.1."""

    sampler_version: str
    seed: int
    family_weights: WeightTableSpec
    constraint_count_weights: WeightTableSpec
    operator_weights: WeightTableSpec
    operator_cardinality: OperatorCardinalityPolicySpec
    genre_sampling: CategoricalValuePolicySpec
    tag_sampling: TagValuePolicySpec
    year_sampling: NumericSamplingPolicySpec
    episode_sampling: NumericSamplingPolicySpec
    combination_policy_version: str
    audit_tolerances: DistributionAuditToleranceSpec
