"""F1-Pilot deterministic realization, record generation, split, and audit.

The reviewed manifest fixes every structural pattern, template, split, and seed
schedule.  This module uses E3 for concrete semantics and the existing record
builder for every derived field; it contains no structural sampler or API call.
"""

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
from random import Random
from typing import Any

from anime_pref.data.dataset_record_builder import (
    build_dataset_record,
    validate_dataset_record,
)
from anime_pref.data.query_builder import DomainRules, build_query
from anime_pref.data.reference_title_pool import validate_reference_title_pool
from anime_pref.schemas.dataset_record import DatasetRecordSpec
from anime_pref.schemas.domain_bindability import ReferenceTitlePoolSpec
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.schemas.pilot_dataset import (
    PilotPatternCase,
    PilotPatternManifest,
)
from anime_pref.schemas.preference_query import (
    RangeConstraintSpec,
    SemanticSpec,
    SetConstraintSpec,
)
from anime_pref.schemas.sampler_config import SemanticSamplerConfigSpec
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.taxonomy import ExecutableTagSubset
from anime_pref.sampling.config import validate_sampler_config_against_domain
from anime_pref.sampling.domain_bindability import (
    validate_structural_pattern_bindability,
)
from anime_pref.sampling.semantic_spec_binder import (
    sample_semantic_spec_from_pattern,
)
from anime_pref.sampling.structural_pattern import validate_structural_pattern_plan


PILOT_SPLITS = ("train", "validation", "test")
GENERATION_FAMILIES = frozenset(
    {"direct_explicit_v1", "direct_compact_v1", "natural_compact_v1"}
)
TAG_GROUP_REALIZATION = {"HAREM": "后宫类型"}


def _canonical_string(value: Any, name: str) -> str:
    """Require a nonempty string without silently changing outer whitespace."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a canonical nonempty string")
    return value


def _parse_manifest_atom(raw: Any, name: str) -> StructuralAtom:
    """Parse one explicit value-free atom without inferring missing mechanics."""
    if not isinstance(raw, dict) or "kind" not in raw:
        raise ValueError(f"{name} must be an object containing kind")
    kind = _canonical_string(raw["kind"], f"{name}.kind")
    set_kinds = {"genre_set", "tag_set"}
    numeric_kinds = {"year_range", "episodes_range"}

    if kind in set_kinds:
        if set(raw) != {"kind", "operator", "cardinality"}:
            raise ValueError(f"{name} set atom has invalid keys")
        atom = StructuralAtom(
            kind,
            operator_plan=OperatorCardinalityPlan(
                raw["operator"], raw["cardinality"]
            ),
        )
    elif kind in numeric_kinds:
        if set(raw) != {"kind", "range_pattern"}:
            raise ValueError(f"{name} numeric atom has invalid keys")
        atom = StructuralAtom(kind, range_pattern=raw["range_pattern"])
    else:
        if set(raw) != {"kind"}:
            raise ValueError(f"{name} payload-free atom has invalid keys")
        atom = StructuralAtom(kind)
    return atom


def validate_pilot_pattern_manifest(manifest: PilotPatternManifest) -> None:
    """Validate canonical reviewed cases, seed schedules, and split ownership."""
    if not isinstance(manifest, PilotPatternManifest):
        raise ValueError("manifest must be a PilotPatternManifest")
    _canonical_string(manifest.manifest_version, "manifest_version")
    _canonical_string(manifest.dataset_version, "dataset_version")
    if not isinstance(manifest.cases, tuple) or not manifest.cases:
        raise ValueError("manifest.cases must be a nonempty tuple")

    case_ids: list[str] = []
    template_splits: dict[str, str] = {}
    total_records = 0
    for case in manifest.cases:
        if not isinstance(case, PilotPatternCase):
            raise ValueError("manifest cases must be PilotPatternCase instances")
        case_ids.append(_canonical_string(case.case_id, "case_id"))
        validate_structural_pattern_plan(case.structural_pattern)
        if case.generation_family not in GENERATION_FAMILIES:
            raise ValueError("unknown pilot generation_family")
        _canonical_string(case.template_id, "template_id")
        if case.template_id != f"{case.case_id}__{case.generation_family}":
            raise ValueError("template_id must explicitly bind case and template family")
        if case.split not in PILOT_SPLITS:
            raise ValueError("pilot split must be train, validation, or test")
        previous_split = template_splits.setdefault(case.template_id, case.split)
        if previous_split != case.split:
            raise ValueError("one exact template_id cannot cross pilot splits")
        if not isinstance(case.seeds, tuple) or not case.seeds:
            raise ValueError("case seeds must be a nonempty tuple")
        if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in case.seeds):
            raise ValueError("pilot seeds must be integers")
        if len(case.seeds) != len(set(case.seeds)):
            raise ValueError("one pilot case cannot contain duplicate seeds")
        if case.seeds != tuple(sorted(case.seeds)):
            raise ValueError("pilot seed schedules must use ascending order")
        total_records += len(case.seeds)

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("pilot case IDs must be unique")
    if case_ids != sorted(case_ids):
        raise ValueError("pilot cases must use canonical case_id order")
    if not 200 <= total_records <= 300:
        raise ValueError("pilot manifest must generate between 200 and 300 records")


def load_pilot_pattern_manifest(path: Path) -> PilotPatternManifest:
    """Load the strict reviewed JSON manifest into immutable pattern contracts."""
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to read or parse pilot pattern manifest") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "manifest_version",
        "dataset_version",
        "cases",
    }:
        raise ValueError("pilot manifest root has invalid keys")
    if not isinstance(raw["cases"], list):
        raise ValueError("pilot manifest cases must be a JSON list")

    cases: list[PilotPatternCase] = []
    expected_case_keys = {
        "case_id",
        "semantic_family",
        "complexity_bucket",
        "atoms",
        "generation_family",
        "template_id",
        "split",
        "seeds",
    }
    for index, raw_case in enumerate(raw["cases"]):
        if not isinstance(raw_case, dict) or set(raw_case) != expected_case_keys:
            raise ValueError(f"cases[{index}] has invalid keys")
        if not isinstance(raw_case["atoms"], list):
            raise ValueError(f"cases[{index}].atoms must be a list")
        if not isinstance(raw_case["seeds"], list):
            raise ValueError(f"cases[{index}].seeds must be a list")
        pattern = StructuralPatternPlan(
            raw_case["semantic_family"],
            raw_case["complexity_bucket"],
            tuple(
                _parse_manifest_atom(atom, f"cases[{index}].atoms[{atom_index}]")
                for atom_index, atom in enumerate(raw_case["atoms"])
            ),
        )
        cases.append(
            PilotPatternCase(
                case_id=raw_case["case_id"],
                structural_pattern=pattern,
                generation_family=raw_case["generation_family"],
                template_id=raw_case["template_id"],
                split=raw_case["split"],
                seeds=tuple(raw_case["seeds"]),
            )
        )

    manifest = PilotPatternManifest(
        manifest_version=raw["manifest_version"],
        dataset_version=raw["dataset_version"],
        cases=tuple(cases),
    )
    validate_pilot_pattern_manifest(manifest)
    return manifest


def _join_and(items: tuple[str, ...]) -> str:
    """Join an asserted conjunction without changing item identity."""
    return "和".join(items)


def _join_or(items: tuple[str, ...]) -> str:
    """Join alternatives with an explicit final OR connective."""
    if len(items) == 1:
        return items[0]
    return "、".join(items[:-1]) + "或" + items[-1]


def _quoted(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"“{value}”" for value in values)


def _group_phrase(group_name: str) -> str:
    """Use only reviewed realization labels; never verbalize expansion leaves."""
    try:
        return TAG_GROUP_REALIZATION[group_name]
    except KeyError as exc:
        raise ValueError(f"no reviewed realization for tag group {group_name!r}") from exc


def _range_clauses(
    constraint: RangeConstraintSpec,
    field: str,
) -> tuple[str, ...]:
    """Realize inclusive numeric bounds without fuzzy temporal/length language."""
    minimum, maximum = constraint.min, constraint.max
    if minimum is None and maximum is None:
        return ()
    if field == "year":
        if minimum is not None and maximum is not None:
            return (f"年份在{minimum}到{maximum}年之间（含边界）",)
        if minimum is not None:
            return (f"年份不早于{minimum}年",)
        return (f"年份不晚于{maximum}年",)
    if minimum is not None and maximum is not None:
        return (f"集数在{minimum}到{maximum}集之间（含边界）",)
    if minimum is not None:
        return (f"至少{minimum}集",)
    return (f"最多{maximum}集",)


def _semantic_clauses(spec: SemanticSpec) -> tuple[str, ...]:
    """Render every and only concrete clauses present in a SemanticSpec."""
    clauses: list[str] = []

    if spec.genres.all_of:
        values = _quoted(spec.genres.all_of)
        prefix = "题材同时包含" if len(values) > 1 else "题材包含"
        clauses.append(prefix + _join_and(values))
    if spec.genres.any_of:
        clauses.append("题材为" + _join_or(_quoted(spec.genres.any_of)) + "中的任一种")
    if spec.genres.none_of:
        clauses.append("排除" + _join_and(_quoted(spec.genres.none_of)) + "题材")

    if spec.tags.all_of:
        values = _quoted(spec.tags.all_of)
        prefix = "标签同时包含" if len(values) > 1 else "标签包含"
        clauses.append(prefix + _join_and(values))

    tag_any_items = list(_quoted(spec.tags.any_of))
    tag_any_items.extend(_group_phrase(group) for group in spec.tag_groups.any_of)
    if tag_any_items:
        clauses.append("标签条件满足" + _join_or(tuple(tag_any_items)) + "中的任一项")

    if spec.tags.none_of:
        clauses.append("排除带有" + _join_and(_quoted(spec.tags.none_of)) + "标签的作品")
    if spec.tag_groups.none_of:
        clauses.extend(f"排除{_group_phrase(group)}" for group in spec.tag_groups.none_of)
    if spec.tag_groups.all_of:
        raise ValueError("pilot v0.1 does not realize tag_group all_of")

    clauses.extend(_range_clauses(spec.year, "year"))
    clauses.extend(_range_clauses(spec.episodes, "episodes"))
    if spec.formats:
        clauses.append("格式为" + _join_or(_quoted(spec.formats)))
    if spec.status:
        clauses.append("状态为" + _join_or(_quoted(spec.status)))
    if spec.reference_titles:
        titles = tuple(f"《{title}》" for title in spec.reference_titles)
        clauses.append("参考" + _join_or(titles) + "寻找相似作品")
    if spec.soft_preferences or spec.unresolved_preferences:
        raise ValueError("pilot auto realization does not support soft/unresolved text")
    if not clauses:
        raise ValueError("cannot realize an empty SemanticSpec")
    return tuple(clauses)


def realize_user_text(
    semantic_spec: SemanticSpec,
    generation_family: str,
    template_id: str,
) -> str:
    """Deterministically realize all explicit semantics through one reviewed style."""
    if generation_family not in GENERATION_FAMILIES:
        raise ValueError("unknown deterministic generation family")
    _canonical_string(template_id, "template_id")
    if not template_id.endswith(f"__{generation_family}"):
        raise ValueError("template_id is not bound to generation_family")
    clauses = _semantic_clauses(semantic_spec)

    if generation_family == "direct_explicit_v1":
        return "想找满足以下条件的动画：" + "；".join(clauses) + "。"
    if generation_family == "direct_compact_v1":
        return "想看动画，" + "，".join(clauses) + "。"
    return "帮我找一部动画，" + "，".join(clauses) + "。"


def generate_pilot_records(
    manifest: PilotPatternManifest,
    sampler_config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
    reference_title_pool: ReferenceTitlePoolSpec,
) -> tuple[DatasetRecordSpec, ...]:
    """Generate and validate every record in manifest case/seed order."""
    validate_pilot_pattern_manifest(manifest)
    validate_sampler_config_against_domain(sampler_config, rules, subset)
    validate_reference_title_pool(reference_title_pool)

    records: list[DatasetRecordSpec] = []
    for case in manifest.cases:
        # Preflight once at case level so an invalid reviewed manifest fails
        # before its seed schedule starts; E3 repeats the frozen public guard.
        validate_structural_pattern_bindability(
            case.structural_pattern,
            sampler_config,
            rules,
            subset,
            reference_title_pool,
        )
        for seed in case.seeds:
            semantic_spec = sample_semantic_spec_from_pattern(
                case.structural_pattern,
                sampler_config,
                rules,
                subset,
                reference_title_pool,
                Random(seed),
            )
            user_text = realize_user_text(
                semantic_spec,
                case.generation_family,
                case.template_id,
            )
            record = build_dataset_record(
                semantic_spec=semantic_spec,
                rules=rules,
                executable_subset=subset,
                dataset_version=manifest.dataset_version,
                semantic_family=case.structural_pattern.semantic_family,
                generation_family=case.generation_family,
                template_id=case.template_id,
                seed=seed,
                user_text=user_text,
                paraphrase_model=None,
                prompt_version=None,
            )
            validate_dataset_record(record, rules, subset)
            records.append(record)

    sample_ids = [record.sample_id for record in records]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("pilot generation produced duplicate sample_id values")
    return tuple(records)


def split_pilot_records(
    manifest: PilotPatternManifest,
    records: tuple[DatasetRecordSpec, ...],
) -> dict[str, tuple[DatasetRecordSpec, ...]]:
    """Partition by manifest-owned template IDs without sample-level randomness."""
    validate_pilot_pattern_manifest(manifest)
    template_split = {case.template_id: case.split for case in manifest.cases}
    split_lists: dict[str, list[DatasetRecordSpec]] = {
        split: [] for split in PILOT_SPLITS
    }
    for record in records:
        try:
            split = template_split[record.template_id]
        except KeyError as exc:
            raise ValueError("record template_id is absent from pilot manifest") from exc
        split_lists[split].append(record)

    result = {split: tuple(split_lists[split]) for split in PILOT_SPLITS}
    all_ids = {record.sample_id for record in records}
    split_id_sets = [
        {record.sample_id for record in result[split]} for split in PILOT_SPLITS
    ]
    if set().union(*split_id_sets) != all_ids:
        raise ValueError("pilot split union does not equal all records")
    if any(
        split_id_sets[left] & split_id_sets[right]
        for left in range(len(split_id_sets))
        for right in range(left + 1, len(split_id_sets))
    ):
        raise ValueError("pilot split sample intersections must be empty")
    template_sets = [
        {record.template_id for record in result[split]} for split in PILOT_SPLITS
    ]
    if any(
        template_sets[left] & template_sets[right]
        for left in range(len(template_sets))
        for right in range(left + 1, len(template_sets))
    ):
        raise ValueError("exact template_id leakage across pilot splits")
    # F1.1 treats exact realized examples as evaluation leakage.  SemanticSpec
    # overlap remains allowed because different language can express one intent.
    validate_pilot_split_hygiene(audit_pilot_split_hygiene(result))
    return result


def dataset_record_to_mapping(record: DatasetRecordSpec) -> dict[str, Any]:
    """Convert the complete dataclass record to deterministic JSON-compatible data."""
    if not isinstance(record, DatasetRecordSpec):
        raise ValueError("record must be a DatasetRecordSpec")
    # asdict recursively handles the existing nested dataclasses.  A JSON
    # round-trip converts tuples to arrays and validates every value is JSON-safe.
    return json.loads(
        json.dumps(asdict(record), ensure_ascii=False, allow_nan=False)
    )


def records_to_jsonl(records: tuple[DatasetRecordSpec, ...]) -> str:
    """Serialize records as compact UTF-8-ready JSONL with stable key ordering."""
    lines = (
        json.dumps(
            dataset_record_to_mapping(record),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        for record in records
    )
    return "".join(f"{line}\n" for line in lines)


def _record_hygiene_keys(record: DatasetRecordSpec) -> dict[str, str]:
    """Build canonical keys for the three F1.1 leakage dimensions."""
    if not isinstance(record, DatasetRecordSpec):
        raise ValueError("split entries must be DatasetRecordSpec instances")
    semantic_key = json.dumps(
        asdict(record.semantic_spec),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    gold_key = json.dumps(
        record.gold_query,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    # A JSON array is an unambiguous composite key even if user text contains
    # punctuation that could collide under ordinary string concatenation.
    pair_key = json.dumps(
        [record.user_text, gold_key],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "exact_user_text": record.user_text,
        "user_text_plus_gold": pair_key,
        "semantic_spec": semantic_key,
    }


def audit_pilot_split_hygiene(
    splits: dict[str, tuple[DatasetRecordSpec, ...]],
) -> dict[str, dict[str, dict[str, int]]]:
    """Count within-split duplicates and pairwise split intersections.

    Pairwise values count distinct keys shared by two splits.  Within-split
    values count duplicate excess: record count minus unique key count.
    """
    if not isinstance(splits, dict) or set(splits) != set(PILOT_SPLITS):
        raise ValueError("splits must contain exactly train, validation, and test")
    key_sets: dict[str, dict[str, set[str]]] = {}
    within_split: dict[str, dict[str, int]] = {}
    dimensions = ("exact_user_text", "user_text_plus_gold", "semantic_spec")

    for split in PILOT_SPLITS:
        records = splits[split]
        if not isinstance(records, tuple):
            raise ValueError("each pilot split must be a tuple")
        keys = [_record_hygiene_keys(record) for record in records]
        key_sets[split] = {
            dimension: {item[dimension] for item in keys}
            for dimension in dimensions
        }
        within_split[split] = {
            dimension: len(records) - len(key_sets[split][dimension])
            for dimension in dimensions
        }

    pairwise: dict[str, dict[str, int]] = {}
    for left_index, left in enumerate(PILOT_SPLITS):
        for right in PILOT_SPLITS[left_index + 1 :]:
            pairwise[f"{left}<->{right}"] = {
                dimension: len(
                    key_sets[left][dimension] & key_sets[right][dimension]
                )
                for dimension in dimensions
            }
    return {"pairwise": pairwise, "within_split": within_split}


def validate_pilot_split_hygiene(
    hygiene: dict[str, dict[str, dict[str, int]]],
) -> None:
    """Reject exact-example leakage while allowing SemanticSpec overlap."""
    if not isinstance(hygiene, dict) or set(hygiene) != {
        "pairwise",
        "within_split",
    }:
        raise ValueError("invalid pilot split hygiene audit")
    for pair, counts in hygiene["pairwise"].items():
        if counts["exact_user_text"]:
            raise ValueError(f"exact user_text leakage across {pair}")
        if counts["user_text_plus_gold"]:
            raise ValueError(f"exact (user_text, Gold) leakage across {pair}")
    for split in ("validation", "test"):
        counts = hygiene["within_split"][split]
        if counts["exact_user_text"]:
            raise ValueError(f"duplicate exact user_text inside {split}")
        if counts["user_text_plus_gold"]:
            raise ValueError(f"duplicate exact (user_text, Gold) inside {split}")


def audit_pilot_records(records: tuple[DatasetRecordSpec, ...]) -> dict[str, Any]:
    """Return the frozen minimal Counter-based pilot audit data."""
    family_counts = Counter(record.semantic_family for record in records)
    constraint_counts = Counter(str(record.constraint_count) for record in records)
    signature_counts = Counter(record.constraint_signature for record in records)
    template_counts = Counter(record.template_id for record in records)
    genre_frequency: Counter[str] = Counter()
    tag_frequency: Counter[str] = Counter()
    numeric_frequency: Counter[str] = Counter()
    reference_frequency: Counter[str] = Counter()
    normalization_frequency: Counter[str] = Counter()

    for record in records:
        hard = record.gold_query["hard_constraints"]
        for operator in ("all_of", "any_of", "none_of"):
            genre_frequency.update(hard["genres"][operator])
            tag_frequency.update(hard["tags"][operator])
        for field in ("year", "episodes"):
            constraint = getattr(record.semantic_spec, field)
            if constraint.min is not None and constraint.max is not None:
                numeric_frequency[f"{field}:bounded_range"] += 1
            elif constraint.min is not None:
                numeric_frequency[f"{field}:min_only"] += 1
            elif constraint.max is not None:
                numeric_frequency[f"{field}:max_only"] += 1
            if constraint.min is not None:
                numeric_frequency[f"{field}:min={constraint.min}"] += 1
            if constraint.max is not None:
                numeric_frequency[f"{field}:max={constraint.max}"] += 1
        if record.semantic_spec.reference_titles:
            reference_frequency["records_with_reference"] += 1
            reference_frequency.update(record.semantic_spec.reference_titles)
        if record.normalization_rule_ids:
            normalization_frequency["records_with_normalization"] += 1
            normalization_frequency.update(record.normalization_rule_ids)

    semantic_keys = [
        json.dumps(asdict(record.semantic_spec), ensure_ascii=False, sort_keys=True)
        for record in records
    ]
    gold_keys = [
        json.dumps(record.gold_query, ensure_ascii=False, sort_keys=True)
        for record in records
    ]
    user_texts = [record.user_text for record in records]
    pair_keys = list(zip(user_texts, gold_keys))
    sample_ids = [record.sample_id for record in records]
    duplicate_counts = {
        "sample_id": len(sample_ids) - len(set(sample_ids)),
        "exact_user_text": len(user_texts) - len(set(user_texts)),
        "user_text_plus_gold": len(pair_keys) - len(set(pair_keys)),
        "semantic_spec": len(semantic_keys) - len(set(semantic_keys)),
    }

    def ordered(counter: Counter[str]) -> dict[str, int]:
        return {key: counter[key] for key in sorted(counter)}

    return {
        "total_records": len(records),
        "semantic_family_counts": ordered(family_counts),
        "constraint_count_counts": ordered(constraint_counts),
        "constraint_signature_counts": ordered(signature_counts),
        "template_id_counts": ordered(template_counts),
        "genre_frequency": ordered(genre_frequency),
        "tag_frequency": ordered(tag_frequency),
        "numeric_frequency": ordered(numeric_frequency),
        "reference_frequency": ordered(reference_frequency),
        "normalization_frequency": ordered(normalization_frequency),
        "duplicate_counts": duplicate_counts,
    }


def render_pilot_audit_markdown(
    audit: dict[str, Any],
    split_hygiene: dict[str, dict[str, dict[str, int]]],
    split_counts: dict[str, int],
    challenge_count: int,
) -> str:
    """Render the small deterministic audit without a dashboard framework."""
    lines = [
        "# Pilot Dataset Audit v0.1",
        "",
        f"- Total records: {audit['total_records']}",
        f"- Train: {split_counts['train']}",
        f"- Validation: {split_counts['validation']}",
        f"- Test: {split_counts['test']}",
        f"- Human challenge cases: {challenge_count}",
        "- Exact template leakage across splits: 0",
        "",
    ]
    lines.extend(
        (
            "## Split hygiene: cross-split overlap",
            "",
            "| Split pair | Exact user text | User text + Gold | SemanticSpec |",
            "|---|---:|---:|---:|",
        )
    )
    for pair, counts in split_hygiene["pairwise"].items():
        lines.append(
            f"| `{pair}` | {counts['exact_user_text']} | "
            f"{counts['user_text_plus_gold']} | {counts['semantic_spec']} |"
        )
    lines.extend(
        (
            "",
            "## Split hygiene: within-split duplicate excess",
            "",
            "| Split | Exact user text | User text + Gold | SemanticSpec |",
            "|---|---:|---:|---:|",
        )
    )
    for split, counts in split_hygiene["within_split"].items():
        lines.append(
            f"| `{split}` | {counts['exact_user_text']} | "
            f"{counts['user_text_plus_gold']} | {counts['semantic_spec']} |"
        )
    lines.append("")
    sections = (
        ("Semantic family counts", "semantic_family_counts"),
        ("Constraint count counts", "constraint_count_counts"),
        ("Constraint signature counts", "constraint_signature_counts"),
        ("Template ID counts", "template_id_counts"),
        ("Genre frequency", "genre_frequency"),
        ("Tag frequency (Gold leaves)", "tag_frequency"),
        ("Numeric pattern and bound frequency", "numeric_frequency"),
        ("Reference frequency", "reference_frequency"),
        ("Normalization frequency", "normalization_frequency"),
        ("Duplicate counts", "duplicate_counts"),
    )
    for title, key in sections:
        lines.extend((f"## {title}", "", "| Value | Count |", "|---|---:|"))
        values = audit[key]
        if values:
            lines.extend(f"| `{value}` | {count} |" for value, count in values.items())
        else:
            lines.append("| `(none)` | 0 |")
        lines.append("")
    return "\n".join(lines)


def build_human_challenge_cases(rules: DomainRules) -> tuple[dict[str, Any], ...]:
    """Build 12 reviewed, training-excluded challenge queries deterministically."""
    cases = (
        ("challenge_001", "不要后宫。", SemanticSpec(tag_groups=SetConstraintSpec(none_of=("HAREM",)))),
        ("challenge_002", "悬疑或科幻题材都可以。", SemanticSpec(genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")))),
        ("challenge_003", "想看同时包含悬疑和科幻题材的动画。", SemanticSpec(genres=SetConstraintSpec(all_of=("Mystery", "Sci-Fi")))),
        ("challenge_004", "想找类似《Steins;Gate》的作品。", SemanticSpec(reference_titles=("Steins;Gate",))),
        ("challenge_005", "想看年份不早于2020年的动画。", SemanticSpec(year=RangeConstraintSpec(min=2020))),
        ("challenge_006", "想看年份不晚于2010年的动画。", SemanticSpec(year=RangeConstraintSpec(max=2010))),
        ("challenge_007", "想看2010到2020年之间（含边界）的动画。", SemanticSpec(year=RangeConstraintSpec(min=2010, max=2020))),
        ("challenge_008", "想看12到24集之间（含边界）的动画。", SemanticSpec(episodes=RangeConstraintSpec(min=12, max=24))),
        ("challenge_009", "想看2010年及以后、最多24集的悬疑或科幻TV动画，不要后宫。", SemanticSpec(genres=SetConstraintSpec(any_of=("Mystery", "Sci-Fi")), tag_groups=SetConstraintSpec(none_of=("HAREM",)), year=RangeConstraintSpec(min=2010), episodes=RangeConstraintSpec(max=24), formats=("TV",))),
        ("challenge_010", "排除Female Harem标签。", SemanticSpec(tags=SetConstraintSpec(none_of=("Female Harem",)))),
        ("challenge_011", "MOVIE或TV格式都可以。", SemanticSpec(formats=("MOVIE", "TV"))),
        ("challenge_012", "FINISHED或RELEASING状态都可以。", SemanticSpec(status=("FINISHED", "RELEASING"))),
    )
    return tuple(
        {
            "challenge_id": challenge_id,
            "user_text": user_text,
            "gold_query": build_query(spec, rules),
        }
        for challenge_id, user_text, spec in cases
    )


def challenge_cases_to_jsonl(cases: tuple[dict[str, Any], ...]) -> str:
    """Serialize reviewed challenge cases in their fixed authored order."""
    return "".join(
        json.dumps(
            case,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for case in cases
    )


def write_pilot_artifacts(
    output_dir: Path,
    audit_path: Path,
    records: tuple[DatasetRecordSpec, ...],
    splits: dict[str, tuple[DatasetRecordSpec, ...]],
    challenge_cases: tuple[dict[str, Any], ...],
    audit_markdown: str,
) -> None:
    """Write only the six reviewed pilot artifacts using UTF-8 and stable bytes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "pilot_all.v0.1.jsonl": records_to_jsonl(records),
        "train.v0.1.jsonl": records_to_jsonl(splits["train"]),
        "validation.v0.1.jsonl": records_to_jsonl(splits["validation"]),
        "test.v0.1.jsonl": records_to_jsonl(splits["test"]),
        "challenge.v0.1.jsonl": challenge_cases_to_jsonl(challenge_cases),
    }
    for filename, payload in payloads.items():
        (output_dir / filename).write_text(payload, encoding="utf-8", newline="")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        audit_markdown,
        encoding="utf-8",
        newline="",
    )
