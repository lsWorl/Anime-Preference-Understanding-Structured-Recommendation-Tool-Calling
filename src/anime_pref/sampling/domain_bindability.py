"""E1. Deterministic domain-bindability preflight for structural patterns.

The module proves that at least one schema/domain-level concrete assignment
exists.  It consumes no randomness, samples no value, and does not ask whether
the AniList catalog contains a media result satisfying that assignment.
"""

from anime_pref.data.query_builder import DomainRules
from anime_pref.data.reference_title_pool import validate_reference_title_pool
from anime_pref.data.rules_identity import domain_rules_sha256
from anime_pref.schemas.domain_bindability import (
    ReferenceTitlePoolSpec,
    TagGroupBindingPlan,
)
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.taxonomy import ExecutableTagSubset
from anime_pref.sampling.config import validate_sampler_config_against_domain
from anime_pref.sampling.numeric_range import validate_numeric_sampling_binding
from anime_pref.sampling.structural_pattern import validate_structural_pattern_plan


def _validate_rules_standalone(rules: DomainRules) -> None:
    """Require an immutable DomainRules instance with its actual content hash."""
    if not isinstance(rules, DomainRules):
        raise ValueError("rules must be a DomainRules instance")
    if rules.rules_hash != domain_rules_sha256(rules):
        raise ValueError("rules.rules_hash does not match DomainRules content")


def _atom_by_kind(structural_pattern: StructuralPatternPlan, kind: str):
    """Return one optional D4 slot; slot uniqueness is validated beforehand."""
    return next(
        (atom for atom in structural_pattern.atoms if atom.kind == kind),
        None,
    )


def _group_names_supporting(rules: DomainRules, operator: str) -> tuple[str, ...]:
    """Return operator-compatible group identities in canonical name order."""
    return tuple(
        group_name
        for group_name in sorted(rules.tag_groups)
        if operator in rules.tag_groups[group_name].allowed_operators
    )


def feasible_tag_group_bindings(
    structural_pattern: StructuralPatternPlan,
    rules: DomainRules,
) -> tuple[TagGroupBindingPlan, ...]:
    """Enumerate canonical group assignments with enough direct-tag capacity.

    All selected group expansions are reserved from the direct-tag universe.
    This prevents both same-operator duplicates and cross-operator overlap in a
    future Gold query without choosing any actual direct tag here.
    """
    validate_structural_pattern_plan(structural_pattern)
    _validate_rules_standalone(rules)

    has_group_any = _atom_by_kind(structural_pattern, "tag_group_any") is not None
    has_group_none = _atom_by_kind(structural_pattern, "tag_group_none") is not None
    direct_tag_atom = _atom_by_kind(structural_pattern, "tag_set")
    direct_cardinality = (
        direct_tag_atom.operator_plan.cardinality
        if direct_tag_atom is not None
        else 0
    )

    any_candidates: tuple[str | None, ...] = (
        _group_names_supporting(rules, "any_of") if has_group_any else (None,)
    )
    none_candidates: tuple[str | None, ...] = (
        _group_names_supporting(rules, "none_of") if has_group_none else (None,)
    )

    feasible: list[TagGroupBindingPlan] = []
    for any_group in any_candidates:
        for none_group in none_candidates:
            selected_names = tuple(
                name for name in (any_group, none_group) if name is not None
            )

            # Opposing slots must denote distinct concepts whose expansions do
            # not overlap, otherwise final tags.any_of and tags.none_of conflict.
            if (
                any_group is not None
                and none_group is not None
                and any_group == none_group
            ):
                continue
            if any_group is not None and none_group is not None:
                any_tags = set(rules.tag_groups[any_group].tags)
                none_tags = set(rules.tag_groups[none_group].tags)
                if any_tags & none_tags:
                    continue

            reserved_tags = {
                tag
                for group_name in selected_names
                for tag in rules.tag_groups[group_name].tags
            }
            available_direct_tags = rules.tags - reserved_tags
            if len(available_direct_tags) < direct_cardinality:
                continue

            feasible.append(
                TagGroupBindingPlan(
                    any_of_group=any_group,
                    none_of_group=none_group,
                )
            )

    # Nested iteration over sorted group names fixes deterministic identity and
    # is intentionally unrelated to probability or future RNG selection.
    return tuple(feasible)


def validate_structural_pattern_bindability(
    structural_pattern: StructuralPatternPlan,
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
) -> None:
    """Raise unless at least one legal domain assignment exists for a pattern."""
    # Full provenance binding precedes capacity checks.  No object is repaired,
    # and this function never falls back to inactive subset tags.
    validate_structural_pattern_plan(structural_pattern)
    validate_sampler_config_against_domain(sampler_config, rules, subset)
    validate_reference_title_pool(reference_title_pool)

    genre_atom = _atom_by_kind(structural_pattern, "genre_set")
    if (
        genre_atom is not None
        and len(rules.genres) < genre_atom.operator_plan.cardinality
    ):
        raise ValueError("active genre vocabulary cannot satisfy cardinality")

    # D2 remains the single truth source for configured numeric pools versus
    # DomainRules sanity bounds.  E1 checks only fields present in the pattern.
    if _atom_by_kind(structural_pattern, "year_range") is not None:
        validate_numeric_sampling_binding("year", sampler_config, rules)
    if _atom_by_kind(structural_pattern, "episodes_range") is not None:
        validate_numeric_sampling_binding("episodes", sampler_config, rules)

    if _atom_by_kind(structural_pattern, "format_any") is not None:
        if not rules.formats:
            raise ValueError("format_any requires a nonempty active format vocabulary")
    if _atom_by_kind(structural_pattern, "status_any") is not None:
        if not rules.statuses:
            raise ValueError("status_any requires a nonempty active status vocabulary")

    if _atom_by_kind(structural_pattern, "reference") is not None:
        if not reference_title_pool.titles:
            raise ValueError("reference atom requires at least one reference title")

    # This one support enumeration jointly covers operator-compatible groups,
    # opposing-group separation, and direct-tag capacity after reservations.
    if not feasible_tag_group_bindings(structural_pattern, rules):
        raise ValueError("pattern has no feasible tag/group domain binding")

    return None

