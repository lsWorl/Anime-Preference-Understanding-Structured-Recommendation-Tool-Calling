"""Small immutable contracts for E0 baseline configuration and predictions."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class E0BaselineConfig:
    """Frozen inference identity and deterministic generation settings."""

    e0_version: str
    model_id: str
    tokenizer_id: str
    revision: str
    prompt_version: str
    prompt_path: str
    serialization_identity: str
    enable_thinking: bool
    device: str
    dtype: str
    do_sample: bool
    num_beams: int
    max_new_tokens: int
    batch_size: int
    local_files_only: bool
    prompt_frozen: bool


@dataclass(frozen=True)
class E0InputRecord:
    """Evaluation input stripped to fields required for inference and slicing."""

    sample_id: str
    split: str
    user_text: str
    gold_query: Mapping[str, Any]
    semantic_family: str | None = None
    constraint_count: int | None = None
    constraint_signature: str | None = None
    normalization_rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class E0PredictionRecord:
    """One retained raw generation plus layered evaluation results."""

    sample_id: str
    split: str
    user_text: str
    gold_query: Mapping[str, Any]
    raw_model_output: str
    parsed_prediction: Mapping[str, Any] | None
    parse_error: str | None
    schema_error: str | None
    domain_error: str | None
    canonical_prediction: Mapping[str, Any] | None
    exact_match: bool
    field_correctness: Mapping[str, bool]
    hard_constraint_tp: int
    hard_constraint_fp: int
    hard_constraint_fn: int
    error_labels: tuple[str, ...]
    recoverable_json: bool
    semantic_family: str | None
    constraint_count: int | None
    constraint_signature: str | None
    normalization_rule_ids: tuple[str, ...]
    model_id: str
    tokenizer_id: str
    resolved_model_revision: str
    prompt_version: str
    serialization_identity: str
    generation_config: Mapping[str, Any]
