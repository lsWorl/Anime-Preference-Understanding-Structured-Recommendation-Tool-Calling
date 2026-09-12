"""D5C1. Caller-owned RNG selection of one enabled structural signature.

The public entrypoint performs the complete D5A operational binding, reuses the
frozen D5A probability mapping, and delegates one multi-candidate draw to the
project's existing weighted-choice primitive. It does not select mechanics.
"""

from typing import Protocol

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_signature import (
    StructuralPatternSelectionPolicySpec,
    StructuralSignature,
)
from anime_pref.sampling.family_complexity import (
    _weighted_choice,
    validate_family_complexity_plan,
)
from anime_pref.sampling.structural_signature import (
    signature_probabilities,
    validate_structural_pattern_selection_policy,
)


class RandomSource(Protocol):
    """Minimal caller-owned RNG interface required by weighted selection."""

    def random(self) -> float:
        """Return the next pseudorandom draw."""


def _choose_signature_from_probabilities(
    probabilities: dict[StructuralSignature, float],
    rng: RandomSource,
) -> StructuralSignature:
    """Choose in canonical mapping order with zero draws for a singleton."""
    choices = tuple(probabilities)
    if not choices:
        # D5A binding guarantees coverage; this protects direct helper misuse
        # and future contract drift without adding a fallback signature.
        raise ValueError("signature probability mapping must not be empty")
    if len(choices) == 1:
        return choices[0]
    return _weighted_choice(choices, probabilities, rng)


def sample_structural_signature(
    policy: StructuralPatternSelectionPolicySpec,
    sampler_config: SemanticSamplerConfigSpec,
    family_complexity_plan: FamilyComplexityPlan,
    rng: RandomSource,
) -> StructuralSignature:
    """Sample P(S|F,C) after full binding, using only caller RNG state."""
    # Binding verifies policy/spec/hash, sampler-version identity, configured D4
    # membership, and coverage of every B context. It is deliberately performed
    # on every public call under the frozen v0.1 operational contract.
    validate_structural_pattern_selection_policy(policy, sampler_config)
    validate_family_complexity_plan(family_complexity_plan)
    if not callable(getattr(rng, "random", None)):
        raise ValueError("rng must provide a callable random() method")

    # D5A remains the sole probability truth source. Mapping insertion order is
    # its frozen canonical signature order and must not be re-sorted here.
    probabilities = signature_probabilities(policy, family_complexity_plan)
    selected = _choose_signature_from_probabilities(probabilities, rng)
    if not isinstance(selected, StructuralSignature):
        raise ValueError("signature selection returned an invalid output")
    return selected
