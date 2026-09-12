"""E2A. Deterministic domain-conditioned structural support queries.

The frozen D4/D5 layers continue to define domain-independent structural
eligibility and priors.  This module only filters their enabled support through
the frozen E1 bindability validator; it adds no probability or RNG semantics.
"""

from anime_pref.data.query_builder import DomainRules
from anime_pref.data.reference_title_pool import validate_reference_title_pool
from anime_pref.schemas.domain_bindability import ReferenceTitlePoolSpec
from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.structural_signature import (
    StructuralPatternSelectionPolicySpec,
    StructuralSignature,
)
from anime_pref.schemas.taxonomy import ExecutableTagSubset
from anime_pref.sampling.config import validate_sampler_config_against_domain
from anime_pref.sampling.domain_bindability import (
    validate_structural_pattern_bindability,
)
from anime_pref.sampling.mechanics_probability import mechanics_candidates
from anime_pref.sampling.structural_signature import (
    signature_probabilities,
    validate_structural_pattern_selection_policy,
)


def _validate_domain_resources(
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
) -> None:
    """Separate invalid resources from ordinary zero-capacity support."""
    validate_sampler_config_against_domain(sampler_config, rules, subset)
    validate_reference_title_pool(reference_title_pool)


def _filter_bindable_mechanics_candidates(
    family_complexity_plan: FamilyComplexityPlan,
    structural_signature: StructuralSignature,
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
) -> tuple[StructuralPatternPlan, ...]:
    """Filter one D5B tuple through E1 while preserving its exact order."""
    candidates = mechanics_candidates(
        family_complexity_plan,
        structural_signature,
    )
    bindable: list[StructuralPatternPlan] = []
    for candidate in candidates:
        try:
            # E1 remains the only domain-capacity truth source.  Its ValueError
            # means this otherwise valid D5B candidate has zero assignments in
            # the supplied domain and therefore does not enter support.
            validate_structural_pattern_bindability(
                candidate,
                sampler_config,
                rules,
                subset,
                reference_title_pool,
            )
        except ValueError:
            continue
        bindable.append(candidate)

    # Iteration follows the original canonical D5B tuple.  No capacity score,
    # failure reason, or survivor count is allowed to reorder the result.
    return tuple(bindable)


def bindable_mechanics_candidates(
    family_complexity_plan: FamilyComplexityPlan,
    structural_signature: StructuralSignature,
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
) -> tuple[StructuralPatternPlan, ...]:
    """Return M_bind(F,C,S,D) in the frozen D5B canonical mechanics order."""
    _validate_domain_resources(
        sampler_config,
        rules,
        subset,
        reference_title_pool,
    )
    return _filter_bindable_mechanics_candidates(
        family_complexity_plan,
        structural_signature,
        sampler_config,
        rules,
        subset,
        reference_title_pool,
    )


def bindable_structural_signatures(
    policy: StructuralPatternSelectionPolicySpec,
    sampler_config: SemanticSamplerConfigSpec,
    family_complexity_plan: FamilyComplexityPlan,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
) -> tuple[StructuralSignature, ...]:
    """Return enabled signatures having at least one bindable mechanics plan."""
    # Binding the D5A policy first guarantees that only its explicit, valid
    # allowlist can contribute signatures.  Domain resources are validated
    # before filtering so malformed provenance is never mistaken for capacity 0.
    validate_structural_pattern_selection_policy(policy, sampler_config)
    _validate_domain_resources(
        sampler_config,
        rules,
        subset,
        reference_title_pool,
    )

    # D5A's probability mapping supplies the enabled signature set and its
    # canonical insertion order.  Probability values are deliberately ignored:
    # E2A is a support query and performs no conditioning or renormalization.
    enabled_signatures = tuple(
        signature_probabilities(policy, family_complexity_plan)
    )
    bindable: list[StructuralSignature] = []
    for structural_signature in enabled_signatures:
        mechanics = _filter_bindable_mechanics_candidates(
            family_complexity_plan,
            structural_signature,
            sampler_config,
            rules,
            subset,
            reference_title_pool,
        )
        if mechanics:
            bindable.append(structural_signature)

    # Empty is an explicit zero-capacity result.  No fallback family, lower
    # complexity, disabled signature, inactive tag, or resampling is introduced.
    return tuple(bindable)
