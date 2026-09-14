"""Strict E0 parsing, validation, comparison, slicing, and reporting.

Primary evaluation never repairs model output.  A separate recoverability flag
may inspect common wrappers, but repaired content is never stored as the primary
prediction or used by exact/field/constraint metrics.
"""

from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from anime_pref.data.domain_validation import validate_query_domain
from anime_pref.data.query_builder import DomainRules
from anime_pref.data.query_validation import canonicalize_query, validate_query_structure
from anime_pref.schemas.e0_baseline import (
    E0BaselineConfig,
    E0InputRecord,
    E0PredictionRecord,
)


FIELD_NAMES = (
    "genres",
    "tags",
    "year",
    "episodes",
    "formats",
    "status",
    "reference_titles",
    "soft_preferences",
    "unresolved_preferences",
)
ERROR_LABEL_ORDER = (
    "JSON_PARSE_ERROR",
    "SCHEMA_ERROR",
    "DOMAIN_ERROR",
    "MISSING_CONSTRAINT",
    "HALLUCINATED_CONSTRAINT",
    "WRONG_OPERATOR",
    "WRONG_VALUE",
    "WRONG_NUMERIC_BOUND",
    "REFERENCE_ERROR",
    "NORMALIZATION_ERROR",
)
PAIRWISE_SET_FIELDS = ("genres", "tags")


def _canonical_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a canonical nonempty string")
    return value


def load_e0_config(path: Path, project_root: Path) -> E0BaselineConfig:
    """Load the strict E0 identity/config without importing model libraries."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to read E0 baseline config") from exc
    expected = set(E0BaselineConfig.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("E0 baseline config has invalid keys")
    for name in (
        "e0_version",
        "model_id",
        "tokenizer_id",
        "revision",
        "prompt_version",
        "prompt_path",
        "serialization_identity",
        "device",
        "dtype",
    ):
        _canonical_nonempty_string(raw[name], name)
    if raw["device"] not in {"cuda", "cpu"}:
        raise ValueError("device must be cuda or cpu")
    if raw["dtype"] not in {"bfloat16", "float16", "float32"}:
        raise ValueError("unsupported E0 dtype")
    for name in ("enable_thinking", "do_sample", "local_files_only", "prompt_frozen"):
        if not isinstance(raw[name], bool):
            raise ValueError(f"{name} must be bool")
    if raw["do_sample"]:
        raise ValueError("E0 primary generation must use do_sample=false")
    if raw["num_beams"] != 1:
        raise ValueError("E0 primary generation must use num_beams=1")
    for name in ("max_new_tokens", "batch_size"):
        if isinstance(raw[name], bool) or not isinstance(raw[name], int) or raw[name] < 1:
            raise ValueError(f"{name} must be a positive integer")
    prompt_path = project_root / raw["prompt_path"]
    if not prompt_path.is_file():
        raise ValueError("configured E0 prompt file does not exist")
    return E0BaselineConfig(**raw)


def load_system_prompt(config: E0BaselineConfig, project_root: Path) -> str:
    """Read the frozen prompt and remove only ordinary file-ending newlines."""
    text = (project_root / config.prompt_path).read_text(encoding="utf-8")
    # Version-controlled text files conventionally end with LF.  That byte is
    # not part of the chat message; spaces and other outer drift still fail.
    canonical = text.rstrip("\r\n")
    if not canonical or canonical != canonical.strip():
        raise ValueError("system prompt must be nonempty")
    return canonical


def build_inference_messages(system_prompt: str, user_text: str) -> list[dict[str, str]]:
    """Build the only two messages visible to the model; Gold is never accepted."""
    _canonical_nonempty_string(system_prompt, "system_prompt")
    _canonical_nonempty_string(user_text, "user_text")
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]


def validate_e0_split_authorization(config: E0BaselineConfig, split: str) -> None:
    """Keep test/challenge unavailable until the validation prompt is frozen."""
    if split not in {"smoke", "validation", "test", "challenge"}:
        raise ValueError("unknown E0 split")
    if split in {"test", "challenge"} and not config.prompt_frozen:
        raise ValueError("test/challenge require prompt_frozen=true")


def load_e0_inputs(path: Path, split: str) -> tuple[E0InputRecord, ...]:
    """Load pilot or challenge JSONL into one evaluator input contract."""
    if split not in {"smoke", "validation", "test", "challenge"}:
        raise ValueError("unknown E0 split")
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to read E0 input JSONL") from exc
    records: list[E0InputRecord] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("E0 input row must be an object")
        if split == "challenge":
            sample_id = _canonical_nonempty_string(row.get("challenge_id"), "challenge_id")
            family = None
            count = None
            signature = None
            normalization_ids: tuple[str, ...] = ()
        else:
            sample_id = _canonical_nonempty_string(row.get("sample_id"), "sample_id")
            family = row.get("semantic_family")
            count = row.get("constraint_count")
            signature = row.get("constraint_signature")
            normalization_ids = tuple(row.get("normalization_rule_ids", ()))
        user_text = _canonical_nonempty_string(row.get("user_text"), "user_text")
        gold = row.get("gold_query")
        if not isinstance(gold, dict):
            raise ValueError(f"row {index} lacks gold_query")
        validate_query_structure(gold)
        records.append(
            E0InputRecord(
                sample_id=sample_id,
                split=split,
                user_text=user_text,
                gold_query=gold,
                semantic_family=family,
                constraint_count=count,
                constraint_signature=signature,
                normalization_rule_ids=normalization_ids,
            )
        )
    if not records:
        raise ValueError("E0 input cannot be empty")
    return tuple(records)


def strict_parse_prediction(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse the complete raw output once; code fences and extra text fail."""
    if not isinstance(raw_output, str):
        raise ValueError("raw_output must be a string")
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return None, f"{exc.msg} at line {exc.lineno} column {exc.colno}"
    if not isinstance(parsed, dict):
        return None, "top-level JSON value must be an object"
    return parsed, None


def is_recoverable_json(raw_output: str) -> bool:
    """Report common wrapper recoverability without changing primary metrics."""
    parsed, error = strict_parse_prediction(raw_output)
    if error is None:
        return True
    stripped = raw_output.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1)] if fenced else []
    first, last = stripped.find("{"), stripped.rfind("}")
    if first >= 0 and last > first:
        candidates.append(stripped[first : last + 1])
    for candidate in candidates:
        try:
            if isinstance(json.loads(candidate), dict):
                return True
        except json.JSONDecodeError:
            pass
    return False


def _field_value(query: Mapping[str, Any], field: str) -> Any:
    if field in {"genres", "tags", "year", "episodes", "formats", "status"}:
        return query["hard_constraints"][field]
    return query[field]


def hard_constraint_clauses(query: Mapping[str, Any]) -> frozenset[tuple[Any, ...]]:
    """Map canonical hard constraints to pre-expansion semantic clause units."""
    canonical = canonicalize_query(query)
    hard = canonical["hard_constraints"]
    clauses: set[tuple[Any, ...]] = set()
    for field in PAIRWISE_SET_FIELDS:
        constraint = hard[field]
        for operator in ("all_of", "none_of"):
            clauses.update((field, operator, value) for value in constraint[operator])
        if constraint["any_of"]:
            clauses.add((field, "any_of", tuple(constraint["any_of"])))
    for field in ("year", "episodes"):
        for bound in ("min", "max"):
            if hard[field][bound] is not None:
                clauses.add((field, bound, hard[field][bound]))
    for field in ("formats", "status"):
        if hard[field]:
            clauses.add((field, "any_of", tuple(hard[field])))
    return frozenset(clauses)


def _operator_values(query: Mapping[str, Any], field: str) -> dict[str, set[str]]:
    return {
        operator: set(query["hard_constraints"][field][operator])
        for operator in ("all_of", "any_of", "none_of")
    }


def _has_wrong_operator(gold: Mapping[str, Any], prediction: Mapping[str, Any]) -> bool:
    for field in PAIRWISE_SET_FIELDS:
        gold_ops = _operator_values(gold, field)
        pred_ops = _operator_values(prediction, field)
        for pred_operator, pred_values in pred_ops.items():
            for gold_operator, gold_values in gold_ops.items():
                if pred_operator != gold_operator and pred_values & gold_values:
                    return True
    return False


def _has_wrong_categorical_value(
    gold: Mapping[str, Any], prediction: Mapping[str, Any]
) -> bool:
    for field in ("genres", "tags", "formats", "status"):
        gold_value = _field_value(gold, field)
        pred_value = _field_value(prediction, field)
        if gold_value == pred_value:
            continue
        gold_present = bool(gold_value) if isinstance(gold_value, list) else any(gold_value.values())
        pred_present = bool(pred_value) if isinstance(pred_value, list) else any(pred_value.values())
        if gold_present and pred_present:
            return True
    return False


def _expects_harem_normalization(input_record: E0InputRecord) -> bool:
    if input_record.normalization_rule_ids:
        return True
    harem = {"Female Harem", "Male Harem", "Mixed Gender Harem"}
    tags = input_record.gold_query["hard_constraints"]["tags"]
    return any(set(tags[operator]) == harem for operator in ("any_of", "none_of"))


def evaluate_raw_prediction(
    input_record: E0InputRecord,
    raw_output: str,
    rules: DomainRules,
    config: E0BaselineConfig,
    resolved_model_revision: str,
) -> E0PredictionRecord:
    """Evaluate one primary generation through parse/schema/domain/canonical layers."""
    parsed, parse_error = strict_parse_prediction(raw_output)
    schema_error: str | None = None
    domain_error: str | None = None
    canonical_prediction: dict[str, Any] | None = None
    if parsed is not None:
        try:
            validate_query_structure(parsed)
        except ValueError as exc:
            schema_error = str(exc)
        if schema_error is None:
            try:
                validate_query_domain(parsed, rules)
            except ValueError as exc:
                domain_error = str(exc)
        if schema_error is None and domain_error is None:
            canonical_prediction = canonicalize_query(parsed)

    gold = canonicalize_query(input_record.gold_query)
    exact_match = canonical_prediction == gold if canonical_prediction is not None else False
    field_correctness = {
        field: (
            canonical_prediction is not None
            and _field_value(canonical_prediction, field) == _field_value(gold, field)
        )
        for field in FIELD_NAMES
    }

    gold_clauses = hard_constraint_clauses(gold)
    predicted_clauses = (
        hard_constraint_clauses(canonical_prediction)
        if canonical_prediction is not None
        else frozenset()
    )
    tp = len(gold_clauses & predicted_clauses)
    fp = len(predicted_clauses - gold_clauses)
    fn = len(gold_clauses - predicted_clauses)

    labels: set[str] = set()
    if parse_error is not None:
        labels.add("JSON_PARSE_ERROR")
    elif schema_error is not None:
        labels.add("SCHEMA_ERROR")
    elif domain_error is not None:
        labels.add("DOMAIN_ERROR")
    else:
        if fn:
            labels.add("MISSING_CONSTRAINT")
        if fp:
            labels.add("HALLUCINATED_CONSTRAINT")
        if _has_wrong_operator(gold, canonical_prediction):
            labels.add("WRONG_OPERATOR")
        if _has_wrong_categorical_value(gold, canonical_prediction):
            labels.add("WRONG_VALUE")
        if not field_correctness["year"] or not field_correctness["episodes"]:
            labels.add("WRONG_NUMERIC_BOUND")
        if not field_correctness["reference_titles"]:
            labels.add("REFERENCE_ERROR")
        if _expects_harem_normalization(input_record) and not field_correctness["tags"]:
            labels.add("NORMALIZATION_ERROR")

    generation_config = {
        "do_sample": config.do_sample,
        "num_beams": config.num_beams,
        "max_new_tokens": config.max_new_tokens,
        "enable_thinking": config.enable_thinking,
        "dtype": config.dtype,
        "device": config.device,
    }
    return E0PredictionRecord(
        sample_id=input_record.sample_id,
        split=input_record.split,
        user_text=input_record.user_text,
        gold_query=gold,
        raw_model_output=raw_output,
        parsed_prediction=parsed,
        parse_error=parse_error,
        schema_error=schema_error,
        domain_error=domain_error,
        canonical_prediction=canonical_prediction,
        exact_match=exact_match,
        field_correctness=field_correctness,
        hard_constraint_tp=tp,
        hard_constraint_fp=fp,
        hard_constraint_fn=fn,
        error_labels=tuple(label for label in ERROR_LABEL_ORDER if label in labels),
        recoverable_json=is_recoverable_json(raw_output),
        semantic_family=input_record.semantic_family,
        constraint_count=input_record.constraint_count,
        constraint_signature=input_record.constraint_signature,
        normalization_rule_ids=input_record.normalization_rule_ids,
        model_id=config.model_id,
        tokenizer_id=config.tokenizer_id,
        resolved_model_revision=resolved_model_revision,
        prompt_version=config.prompt_version,
        serialization_identity=config.serialization_identity,
        generation_config=generation_config,
    )


def prediction_to_mapping(record: E0PredictionRecord) -> dict[str, Any]:
    """Convert a retained prediction to stable JSON-compatible data."""
    return json.loads(json.dumps(asdict(record), ensure_ascii=False, allow_nan=False))


def predictions_to_jsonl(records: Iterable[E0PredictionRecord]) -> str:
    """Serialize complete retained predictions as canonical UTF-8 JSONL."""
    return "".join(
        json.dumps(
            prediction_to_mapping(record),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for record in records
    )


def load_prediction_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    """Load machine-readable results for report aggregation."""
    try:
        rows = tuple(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to load prediction JSONL") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("prediction rows must be objects")
    return rows


def compute_e0_metrics(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute strict rates, field accuracy, micro clause metrics and errors."""
    rows = tuple(records)
    total = len(rows)
    if total == 0:
        raise ValueError("cannot compute E0 metrics for an empty collection")

    def rate(count: int) -> float:
        return count / total

    parse_valid = sum(row["parse_error"] is None for row in rows)
    schema_valid = sum(
        row["parse_error"] is None and row["schema_error"] is None for row in rows
    )
    domain_valid = sum(
        row["parse_error"] is None
        and row["schema_error"] is None
        and row["domain_error"] is None
        for row in rows
    )
    exact = sum(bool(row["exact_match"]) for row in rows)
    recoverable = sum(bool(row["recoverable_json"]) for row in rows)
    field_accuracy = {
        field: rate(sum(bool(row["field_correctness"][field]) for row in rows))
        for field in FIELD_NAMES
    }
    tp = sum(int(row["hard_constraint_tp"]) for row in rows)
    fp = sum(int(row["hard_constraint_fp"]) for row in rows)
    fn = sum(int(row["hard_constraint_fn"]) for row in rows)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    errors = Counter(label for row in rows for label in row["error_labels"])
    return {
        "total": total,
        "json_parse_rate": rate(parse_valid),
        "recoverable_json_rate": rate(recoverable),
        "schema_valid_rate": rate(schema_valid),
        "domain_valid_rate": rate(domain_valid),
        "exact_match_rate": rate(exact),
        "field_accuracy": field_accuracy,
        "hard_constraint_precision": precision,
        "hard_constraint_recall": recall,
        "hard_constraint_f1": f1,
        "hard_constraint_totals": {"tp": tp, "fp": fp, "fn": fn},
        "error_counts": {label: errors.get(label, 0) for label in ERROR_LABEL_ORDER},
    }


def compute_metric_slices(
    records: Iterable[Mapping[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    """Compute the same metrics for each non-null dataset provenance slice."""
    if field not in {"semantic_family", "constraint_count", "constraint_signature"}:
        raise ValueError("unsupported E0 slice field")
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        value = row.get(field)
        if value is not None:
            grouped[str(value)].append(row)
    return {key: compute_e0_metrics(grouped[key]) for key in sorted(grouped)}


def build_e0_metrics_bundle(
    validation: Iterable[Mapping[str, Any]],
    test: Iterable[Mapping[str, Any]],
    challenge: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one machine-readable before-training metrics document."""
    validation_rows, test_rows, challenge_rows = (
        tuple(validation),
        tuple(test),
        tuple(challenge),
    )

    def special_slices(rows: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
        """Keep normalization and reference behavior visible as first-class slices."""
        harem = {"Female Harem", "Male Harem", "Mixed Gender Harem"}
        normalization_rows = tuple(
            row
            for row in rows
            if row.get("normalization_rule_ids")
            or any(
                set(row["gold_query"]["hard_constraints"]["tags"][operator]) == harem
                for operator in ("any_of", "none_of")
            )
        )
        reference_rows = tuple(
            row for row in rows if row["gold_query"]["reference_titles"]
        )
        return {
            "normalization": (
                compute_e0_metrics(normalization_rows) if normalization_rows else None
            ),
            "reference": compute_e0_metrics(reference_rows) if reference_rows else None,
        }

    return {
        "validation": {
            "overall": compute_e0_metrics(validation_rows),
            "by_semantic_family": compute_metric_slices(validation_rows, "semantic_family"),
            "by_constraint_count": compute_metric_slices(validation_rows, "constraint_count"),
            "by_constraint_signature": compute_metric_slices(validation_rows, "constraint_signature"),
            **special_slices(validation_rows),
        },
        "test": {
            "overall": compute_e0_metrics(test_rows),
            "by_semantic_family": compute_metric_slices(test_rows, "semantic_family"),
            "by_constraint_count": compute_metric_slices(test_rows, "constraint_count"),
            "by_constraint_signature": compute_metric_slices(test_rows, "constraint_signature"),
            **special_slices(test_rows),
        },
        "challenge": {
            "overall": compute_e0_metrics(challenge_rows),
            **special_slices(challenge_rows),
        },
    }
