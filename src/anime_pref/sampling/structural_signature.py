"""D5A. Structural Signature Selection Policy Contract v0.1.

The module extracts and enumerates signatures, loads an explicit allowlist,
computes its canonical identity, and exposes conditional probabilities. It does
not consume randomness or choose a signature or mechanics pattern.
"""

from collections.abc import Mapping
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from anime_pref.schemas.family_complexity import FamilyComplexityPlan
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.structural_signature import (
    StructuralPatternSelectionPolicySpec,
    StructuralSignature,
    StructuralSignatureWeightSpec,
)
from anime_pref.sampling.config import (
    HARD_CONSTRAINT_COUNT_BUCKET_ORDER,
    SEMANTIC_FAMILY_ORDER,
    validate_sampler_config,
)
from anime_pref.sampling.family_complexity import (
    FAMILY_COMPLEXITY_COMPATIBILITY,
    normalize_relative_weights,
    validate_family_complexity_plan,
)
from anime_pref.sampling.structural_atom import (
    STRUCTURAL_ATOM_KIND_ORDER,
    STRUCTURAL_ATOM_KINDS,
)
from anime_pref.sampling.structural_pattern import (
    enumerate_eligible_structural_patterns,
    validate_structural_pattern_plan,
)


_POLICY_KEYS = frozenset(
    {"policy_version", "sampler_version", "signature_entries"}
)
_ENTRY_KEYS = frozenset(
    {"semantic_family", "complexity_bucket", "atom_kinds", "weight"}
)
_KIND_INDEX = {kind: index for index, kind in enumerate(STRUCTURAL_ATOM_KIND_ORDER)}
_FAMILY_INDEX = {
    family: index for index, family in enumerate(SEMANTIC_FAMILY_ORDER)
}
_BUCKET_ORDER = (0, *HARD_CONSTRAINT_COUNT_BUCKET_ORDER)
_BUCKET_INDEX = {bucket: index for index, bucket in enumerate(_BUCKET_ORDER)}


def _require_exact_object(
    value: Any,
    name: str,
    expected_keys: frozenset[str],
) -> dict[str, Any]:
    """Require an ordinary JSON object with exactly the contract keys."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    missing = expected_keys - set(value)
    unknown = set(value) - expected_keys
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing keys: {sorted(missing)}")
        if unknown:
            details.append(f"unknown keys: {sorted(unknown)}")
        raise ValueError(f"{name} has invalid keys; " + "; ".join(details))
    return value


def _validate_canonical_string(value: Any, name: str) -> None:
    """Reject empty strings and outer whitespace instead of silently stripping."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(
            f"{name} must be a non-empty string without outer whitespace"
        )


def canonical_relative_weight(value: Any, name: str = "weight") -> float:
    """Return the identity-safe binary64 representation of a relative weight.

    JSON integers and floats with the same numeric meaning share one canonical
    float representation. An integer is accepted only when converting it to a
    float and back preserves its exact value; this prevents distinct large JSON
    integers from collapsing onto the same IEEE-754 value and policy hash.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")

    try:
        canonical = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} cannot be represented as a canonical float") from exc
    if not math.isfinite(canonical) or canonical <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")
    if isinstance(value, int) and int(canonical) != value:
        raise ValueError(
            f"{name} integer must be exactly representable as a canonical float"
        )
    return canonical


def _validate_positive_weight(value: Any, name: str) -> None:
    """Validate through the same canonical conversion used by policy hashing."""
    canonical_relative_weight(value, name)


def _signature_sort_key(signature: StructuralSignature) -> tuple[int, ...]:
    """Map a validated signature to its canonical lexicographic kind key."""
    validate_structural_signature(signature)
    return tuple(_KIND_INDEX[kind] for kind in signature.atom_kinds)


def validate_structural_signature(signature: StructuralSignature) -> None:
    """Validate the canonical, nonempty and duplicate-free signature contract."""
    if not isinstance(signature, StructuralSignature):
        raise ValueError("signature must be a StructuralSignature instance")
    if not isinstance(signature.atom_kinds, tuple) or not signature.atom_kinds:
        raise ValueError("signature.atom_kinds must be a nonempty tuple")

    indexes: list[int] = []
    for kind in signature.atom_kinds:
        if not isinstance(kind, str) or kind not in STRUCTURAL_ATOM_KINDS:
            raise ValueError(f"unknown structural atom kind: {kind!r}")
        indexes.append(_KIND_INDEX[kind])

    if len(indexes) != len(set(indexes)):
        raise ValueError("signature atom kinds must not contain duplicates")
    if indexes != sorted(indexes):
        raise ValueError("signature atom kinds must use canonical D3 order")


def structural_signature(pattern: StructuralPatternPlan) -> StructuralSignature:
    """Extract only canonical atom-kind presence from one valid D4 pattern."""
    validate_structural_pattern_plan(pattern)
    signature = StructuralSignature(tuple(atom.kind for atom in pattern.atoms))
    validate_structural_signature(signature)
    return signature


@lru_cache(maxsize=None)
def enumerate_eligible_structural_signatures(
    family_complexity_plan: FamilyComplexityPlan,
) -> tuple[StructuralSignature, ...]:
    """Collapse D4 mechanics variants into unique canonical signatures."""
    validate_family_complexity_plan(family_complexity_plan)
    # Immutable memoization avoids repeating D4's finite mechanics enumeration
    # during policy binding. It does not change output or introduce RNG state.
    patterns = enumerate_eligible_structural_patterns(family_complexity_plan)

    # A set removes mechanics multiplicity. Sorting by atom-kind indexes makes
    # the result independent from how many D4 variants first expose a shape.
    signatures = {structural_signature(pattern) for pattern in patterns}
    return tuple(sorted(signatures, key=_signature_sort_key))


def _entry_sort_key(entry: StructuralSignatureWeightSpec) -> tuple[Any, ...]:
    """Return the frozen context-first policy entry order."""
    signature = StructuralSignature(entry.atom_kinds)
    validate_structural_signature(signature)
    return (
        _FAMILY_INDEX[entry.semantic_family],
        _BUCKET_INDEX[entry.complexity_bucket],
        _signature_sort_key(signature),
    )


def _validate_policy_content(policy: StructuralPatternSelectionPolicySpec) -> None:
    """Validate policy fields without checking its derived SHA-256 identity."""
    if not isinstance(policy, StructuralPatternSelectionPolicySpec):
        raise ValueError(
            "policy must be a StructuralPatternSelectionPolicySpec instance"
        )
    _validate_canonical_string(policy.policy_version, "policy_version")
    _validate_canonical_string(policy.sampler_version, "sampler_version")
    if not isinstance(policy.signature_entries, tuple):
        raise ValueError("signature_entries must be a tuple")

    identities: set[tuple[Any, ...]] = set()
    previous_key: tuple[Any, ...] | None = None
    for index, entry in enumerate(policy.signature_entries):
        if not isinstance(entry, StructuralSignatureWeightSpec):
            raise ValueError(f"signature_entries[{index}] has invalid type")

        family_plan = FamilyComplexityPlan(
            entry.semantic_family,
            entry.complexity_bucket,
        )
        validate_family_complexity_plan(family_plan)
        validate_structural_signature(StructuralSignature(entry.atom_kinds))
        _validate_positive_weight(entry.weight, f"signature_entries[{index}].weight")

        identity = (
            entry.semantic_family,
            entry.complexity_bucket,
            entry.atom_kinds,
        )
        if identity in identities:
            raise ValueError("duplicate family/bucket/signature policy entry")
        identities.add(identity)

        current_key = _entry_sort_key(entry)
        if previous_key is not None and current_key <= previous_key:
            raise ValueError("signature_entries are not in canonical order")
        previous_key = current_key


def canonical_structural_pattern_selection_policy_mapping(
    policy: StructuralPatternSelectionPolicySpec,
) -> dict[str, Any]:
    """Return the hash document, deliberately excluding ``policy_hash``."""
    _validate_policy_content(policy)
    return {
        "policy_version": policy.policy_version,
        "sampler_version": policy.sampler_version,
        "signature_entries": [
            {
                "semantic_family": entry.semantic_family,
                "complexity_bucket": entry.complexity_bucket,
                "atom_kinds": list(entry.atom_kinds),
                # The shared helper makes validation acceptance and hash
                # conversion one contract. Equivalent 1/1.0 values collapse,
                # while lossy large integer conversion is rejected.
                "weight": canonical_relative_weight(
                    entry.weight,
                    "signature entry weight",
                ),
            }
            for entry in policy.signature_entries
        ],
    }


def dumps_structural_pattern_selection_policy(
    policy: StructuralPatternSelectionPolicySpec,
) -> str:
    """Serialize compact canonical Unicode JSON without the derived hash."""
    return json.dumps(
        canonical_structural_pattern_selection_policy_mapping(policy),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def structural_pattern_selection_policy_sha256(
    policy: StructuralPatternSelectionPolicySpec,
) -> str:
    """Compute deterministic SHA-256 over canonical UTF-8 policy bytes."""
    canonical_bytes = dumps_structural_pattern_selection_policy(policy).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def validate_structural_pattern_selection_policy_spec(
    policy: StructuralPatternSelectionPolicySpec,
) -> None:
    """Validate standalone policy structure, order, weights, and identity."""
    _validate_policy_content(policy)
    if (
        not isinstance(policy.policy_hash, str)
        or len(policy.policy_hash) != 64
        or any(character not in "0123456789abcdef" for character in policy.policy_hash)
    ):
        raise ValueError("policy_hash must be a lowercase SHA-256 hex string")
    expected_hash = structural_pattern_selection_policy_sha256(policy)
    if policy.policy_hash != expected_hash:
        raise ValueError("policy_hash does not match canonical policy content")


def load_structural_pattern_selection_policy(
    path: Path,
) -> StructuralPatternSelectionPolicySpec:
    """Strictly load JSON, preserve canonical order, and derive policy hash."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to read or parse structural policy: {path}") from exc

    document = _require_exact_object(raw, "structural policy", _POLICY_KEYS)
    raw_entries = document["signature_entries"]
    if not isinstance(raw_entries, list):
        raise ValueError("signature_entries must be a JSON array")

    entries: list[StructuralSignatureWeightSpec] = []
    for index, raw_entry in enumerate(raw_entries):
        entry = _require_exact_object(
            raw_entry,
            f"signature_entries[{index}]",
            _ENTRY_KEYS,
        )
        atom_kinds = entry["atom_kinds"]
        if not isinstance(atom_kinds, list):
            raise ValueError(f"signature_entries[{index}].atom_kinds must be an array")
        entries.append(
            StructuralSignatureWeightSpec(
                semantic_family=entry["semantic_family"],
                complexity_bucket=entry["complexity_bucket"],
                atom_kinds=tuple(atom_kinds),
                weight=entry["weight"],
            )
        )

    # Input intentionally has no self-referential hash. A temporary instance is
    # validated and serialized before the final immutable identity is attached.
    provisional = StructuralPatternSelectionPolicySpec(
        policy_version=document["policy_version"],
        sampler_version=document["sampler_version"],
        signature_entries=tuple(entries),
        policy_hash="",
    )
    _validate_policy_content(provisional)
    policy_hash = structural_pattern_selection_policy_sha256(provisional)
    policy = StructuralPatternSelectionPolicySpec(
        policy_version=provisional.policy_version,
        sampler_version=provisional.sampler_version,
        signature_entries=provisional.signature_entries,
        policy_hash=policy_hash,
    )
    validate_structural_pattern_selection_policy_spec(policy)
    return policy


def _all_family_complexity_contexts() -> tuple[FamilyComplexityPlan, ...]:
    """Return every B-compatible context in frozen family/bucket order."""
    return tuple(
        FamilyComplexityPlan(family, bucket)
        for family in SEMANTIC_FAMILY_ORDER
        for bucket in FAMILY_COMPLEXITY_COMPATIBILITY[family]
    )


def validate_structural_pattern_selection_policy(
    policy: StructuralPatternSelectionPolicySpec,
    sampler_config: SemanticSamplerConfigSpec,
) -> None:
    """Bind an allowlist to Phase A and every mechanically eligible D4 space."""
    validate_structural_pattern_selection_policy_spec(policy)
    validate_sampler_config(sampler_config)
    if policy.sampler_version != sampler_config.sampler_version:
        raise ValueError("policy sampler_version does not match sampler config")

    entries_by_context: dict[
        tuple[Any, Any],
        set[StructuralSignature],
    ] = {}
    for entry in policy.signature_entries:
        context = (entry.semantic_family, entry.complexity_bucket)
        entries_by_context.setdefault(context, set()).add(
            StructuralSignature(entry.atom_kinds)
        )

    for family_plan in _all_family_complexity_contexts():
        context = (
            family_plan.semantic_family,
            family_plan.complexity_bucket,
        )
        enabled = entries_by_context.get(context, set())
        if not enabled:
            raise ValueError(f"no sampling-enabled signature for context {context!r}")
        eligible = set(enumerate_eligible_structural_signatures(family_plan))
        invalid = enabled - eligible
        if invalid:
            raise ValueError(
                f"configured signatures are not D4-eligible for {context!r}: "
                f"{sorted(signature.atom_kinds for signature in invalid)!r}"
            )


def signature_probabilities(
    policy: StructuralPatternSelectionPolicySpec,
    family_complexity_plan: FamilyComplexityPlan,
) -> dict[StructuralSignature, float]:
    """Compute P(signature | family, complexity) over explicit entries only."""
    validate_structural_pattern_selection_policy_spec(policy)
    validate_family_complexity_plan(family_complexity_plan)
    context_entries = tuple(
        entry
        for entry in policy.signature_entries
        if entry.semantic_family == family_complexity_plan.semantic_family
        and entry.complexity_bucket == family_complexity_plan.complexity_bucket
    )
    if not context_entries:
        raise ValueError("context has no sampling-enabled structural signature")

    # No default is added for missing D4 signatures. Raw weights are normalized
    # only inside this already-selected family/complexity context.
    weights = {
        StructuralSignature(entry.atom_kinds): entry.weight
        for entry in context_entries
    }
    return normalize_relative_weights(weights)
