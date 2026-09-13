"""E3-Minimal. Bind one E1-bindable structural pattern to a SemanticSpec.

The structural pattern fixes fields and mechanics.  This module binds concrete
values in the frozen E3 order, reusing D1/D2 and E1 support, then smoke-validates
the result through the deterministic Gold query builder.  It does not select a
new structural pattern, retry, realize user text, or build a dataset record.
"""

from collections.abc import Sequence
from typing import Hashable, Protocol, TypeVar

from anime_pref.data.dataset_record_builder import count_hard_semantic_clauses
from anime_pref.data.query_builder import DomainRules, build_query
from anime_pref.data.reference_title_pool import validate_reference_title_pool
from anime_pref.schemas.categorical_value import DirectCategoricalValuePlan
from anime_pref.schemas.domain_bindability import (
    ReferenceTitlePoolSpec,
    TagGroupBindingPlan,
)
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.taxonomy import ExecutableTagSubset
from anime_pref.sampling.categorical_value import (
    effective_value_weights,
    sample_direct_categorical_values,
    validate_direct_categorical_value_context,
)
from anime_pref.sampling.config import validate_sampler_config_against_domain
from anime_pref.sampling.domain_bindability import (
    feasible_tag_group_bindings,
    validate_structural_pattern_bindability,
)
from anime_pref.sampling.family_complexity import (
    _weighted_choice,
    normalize_relative_weights,
)
from anime_pref.sampling.numeric_range import sample_direct_numeric_range
from anime_pref.sampling.operator_cardinality import (
    validate_operator_cardinality_plan,
)
from anime_pref.sampling.structural_atom import structural_constraint_count
from anime_pref.sampling.structural_pattern import validate_structural_pattern_plan


ChoiceT = TypeVar("ChoiceT", bound=Hashable)


class RandomSource(Protocol):
    """Minimal caller-owned RNG interface used by all concrete choices."""

    def random(self) -> float:
        """Return the next pseudorandom draw from caller-owned state."""


def _choose_uniform(
    candidates: Sequence[ChoiceT],
    rng: RandomSource,
) -> ChoiceT:
    """Choose uniformly in supplied canonical order, with zero singleton draw."""
    choices = tuple(candidates)
    if not choices:
        raise ValueError("uniform choice requires nonempty support")
    if len(choices) == 1:
        return choices[0]
    probabilities = normalize_relative_weights(
        {candidate: 1.0 for candidate in choices}
    )
    return _weighted_choice(choices, probabilities, rng)


def _atom_by_kind(structural_pattern: StructuralPatternPlan, kind: str):
    """Read one optional D4 slot after structural validation proves uniqueness."""
    return next(
        (atom for atom in structural_pattern.atoms if atom.kind == kind),
        None,
    )


def _set_constraint(
    operator: str,
    values: tuple[str, ...],
) -> SetConstraintSpec:
    """Place canonical values into exactly one frozen set-operator slot."""
    if operator == "all_of":
        return SetConstraintSpec(all_of=values)
    if operator == "any_of":
        return SetConstraintSpec(any_of=values)
    if operator == "none_of":
        return SetConstraintSpec(none_of=values)
    raise ValueError(f"unsupported direct set operator: {operator!r}")


def _group_constraint(binding: TagGroupBindingPlan) -> SetConstraintSpec:
    """Preserve selected group identities without expanding them into tags."""
    return SetConstraintSpec(
        any_of=(binding.any_of_group,) if binding.any_of_group else (),
        none_of=(binding.none_of_group,) if binding.none_of_group else (),
    )


def _reserved_group_tags(
    binding: TagGroupBindingPlan,
    rules: DomainRules,
) -> frozenset[str]:
    """Return the union of expansions selected before direct-tag sampling."""
    selected_groups = tuple(
        group_name
        for group_name in (binding.any_of_group, binding.none_of_group)
        if group_name is not None
    )
    return frozenset(
        tag
        for group_name in selected_groups
        for tag in rules.tag_groups[group_name].tags
    )


def _sample_restricted_tag_values(
    operator_plan: OperatorCardinalityPlan,
    allowed_values: frozenset[str],
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    rng: RandomSource,
) -> DirectCategoricalValuePlan:
    """Run D1 weighting on residual active tags without full-domain share guard.

    ``effective_value_weights`` is D1's precedence truth source: explicit
    priority, then configured tier, then default.  Conditioning on group
    reservations changes only the support; sequential weighted sampling and
    canonical final sorting remain identical to D1.
    """
    validate_operator_cardinality_plan(operator_plan)
    if not isinstance(allowed_values, frozenset):
        raise ValueError("allowed direct tags must be a frozenset")
    if not allowed_values <= rules.tags:
        raise ValueError("allowed direct tags must be active in DomainRules")

    full_weights = effective_value_weights(
        "tags",
        sampler_config,
        rules,
        subset,
    )
    # D1 emits full weights in canonical active-value order.  Filtering this
    # mapping preserves that order and the frozen effective-weight precedence.
    remaining: dict[str, float] = {
        tag: weight
        for tag, weight in full_weights.items()
        if tag in allowed_values
    }
    requested_count = operator_plan.cardinality
    if len(remaining) < requested_count:
        raise ValueError("residual direct-tag capacity is insufficient")

    selected: list[str] = []
    while len(selected) < requested_count:
        if len(remaining) == 1:
            chosen = next(iter(remaining))
        else:
            probabilities = normalize_relative_weights(remaining)
            chosen = _weighted_choice(tuple(remaining), probabilities, rng)
        selected.append(chosen)
        del remaining[chosen]

    value_plan = DirectCategoricalValuePlan(
        field="tags",
        values=tuple(sorted(selected)),
    )
    validate_direct_categorical_value_context(
        value_plan,
        operator_plan,
        rules,
        subset,
    )
    return value_plan


def _range_constraint(numeric_plan) -> RangeConstraintSpec:
    """Translate D2's canonical endpoint names into SemanticSpec field names."""
    return RangeConstraintSpec(
        min=numeric_plan.minimum,
        max=numeric_plan.maximum,
    )


def sample_semantic_spec_from_pattern(
    structural_pattern: StructuralPatternPlan,
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
    rng: RandomSource,
) -> SemanticSpec:
    """Bind concrete values in frozen E3 order and return a Gold-valid spec."""
    # Every caller-controlled failure must happen before the first draw.  E1
    # proves a concrete assignment exists; E3 never samples and retries.
    validate_structural_pattern_plan(structural_pattern)
    validate_sampler_config_against_domain(sampler_config, rules, subset)
    validate_reference_title_pool(reference_title_pool)
    validate_structural_pattern_bindability(
        structural_pattern,
        sampler_config,
        rules,
        subset,
        reference_title_pool,
    )
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    # 1. Group identity comes first so its complete expansion can be reserved
    # from the direct-tag sampling universe without rejection.
    group_support = feasible_tag_group_bindings(structural_pattern, rules)
    group_binding = _choose_uniform(group_support, rng)
    tag_groups = _group_constraint(group_binding)
    reserved_tags = _reserved_group_tags(group_binding, rules)

    # 2. Direct genre values use the complete frozen D1 public sampler.
    genres = SetConstraintSpec()
    genre_atom = _atom_by_kind(structural_pattern, "genre_set")
    if genre_atom is not None:
        genre_values = sample_direct_categorical_values(
            "genres",
            genre_atom.operator_plan,
            sampler_config,
            rules,
            subset,
            rng,
        )
        genres = _set_constraint(
            genre_atom.operator_plan.operator,
            genre_values.values,
        )

    # 3. Direct tags use ordinary D1 when no group is selected.  With a group,
    # the restricted adapter conditions D1 weights on the residual universe.
    tags = SetConstraintSpec()
    tag_atom = _atom_by_kind(structural_pattern, "tag_set")
    if tag_atom is not None:
        if reserved_tags:
            tag_values = _sample_restricted_tag_values(
                tag_atom.operator_plan,
                rules.tags - reserved_tags,
                sampler_config,
                rules,
                subset,
                rng,
            )
        else:
            tag_values = sample_direct_categorical_values(
                "tags",
                tag_atom.operator_plan,
                sampler_config,
                rules,
                subset,
                rng,
            )
        tags = _set_constraint(
            tag_atom.operator_plan.operator,
            tag_values.values,
        )

    # 4-5. Numeric endpoint mechanics remain entirely owned by frozen D2.
    year = RangeConstraintSpec()
    year_atom = _atom_by_kind(structural_pattern, "year_range")
    if year_atom is not None:
        year = _range_constraint(
            sample_direct_numeric_range(
                "year",
                year_atom.range_pattern,
                sampler_config,
                rules,
                rng,
            )
        )

    episodes = RangeConstraintSpec()
    episode_atom = _atom_by_kind(structural_pattern, "episodes_range")
    if episode_atom is not None:
        episodes = _range_constraint(
            sample_direct_numeric_range(
                "episodes",
                episode_atom.range_pattern,
                sampler_config,
                rules,
                rng,
            )
        )

    # 6-8. Minimal v0.1 binds exactly one uniform format/status/reference.
    formats: tuple[str, ...] = ()
    if _atom_by_kind(structural_pattern, "format_any") is not None:
        formats = (_choose_uniform(tuple(sorted(rules.formats)), rng),)

    status: tuple[str, ...] = ()
    if _atom_by_kind(structural_pattern, "status_any") is not None:
        status = (_choose_uniform(tuple(sorted(rules.statuses)), rng),)

    reference_titles: tuple[str, ...] = ()
    if _atom_by_kind(structural_pattern, "reference") is not None:
        reference_titles = (
            _choose_uniform(reference_title_pool.titles, rng),
        )

    semantic_spec = SemanticSpec(
        genres=genres,
        tags=tags,
        tag_groups=tag_groups,
        year=year,
        episodes=episodes,
        formats=formats,
        status=status,
        reference_titles=reference_titles,
        soft_preferences=(),
        unresolved_preferences=(),
    )

    structural_count = structural_constraint_count(structural_pattern.atoms)
    semantic_count = count_hard_semantic_clauses(semantic_spec)
    if semantic_count != structural_count:
        raise ValueError(
            "concrete SemanticSpec changed the structural hard-clause count"
        )

    # The existing deterministic builder is the final semantic/domain smoke
    # validator.  Expansion happens there; this public API still returns only
    # the pre-expansion SemanticSpec.
    build_query(semantic_spec, rules)
    return semantic_spec
