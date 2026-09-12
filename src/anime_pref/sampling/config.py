"""Load and validate the versioned Offline Semantic Sampler configuration."""

from collections.abc import Mapping
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any


from anime_pref.data.query_builder import DomainRules, NumericRule
from anime_pref.data.rules_identity import (
    validate_executable_rules_identity,
)
from anime_pref.schemas.sampler_config import (
    CategoricalValuePolicySpec,
    DistributionAuditToleranceSpec,
    NumericSamplingPolicySpec,
    OperatorCardinalityPolicySpec,
    SemanticSamplerConfigSpec,
    TagValuePolicySpec,
    WeightTableSpec,
)
from anime_pref.schemas.taxonomy import ExecutableTagSubset

SEMANTIC_FAMILY_ORDER = (
    "single_constraint",
    "same_field_logic",
    "cross_field_composition",
    "normalization",
    "reference_only",
    "reference_composition",
)
SEMANTIC_FAMILIES = frozenset(SEMANTIC_FAMILY_ORDER)

HARD_CONSTRAINT_COUNT_BUCKET_ORDER = ("1", "2", "3", "4", "5_plus")
HARD_CONSTRAINT_COUNT_BUCKETS = frozenset(HARD_CONSTRAINT_COUNT_BUCKET_ORDER)
SET_OPERATORS = frozenset({"all_of", "any_of", "none_of"})
NUMERIC_RANGE_PATTERNS = frozenset({"min_only", "max_only", "bounded_range"})
NUMERIC_VALUE_POOLS = frozenset({"common", "catalog_region", "long_tail"})
TAG_SAMPLING_TIERS = frozenset({"core", "standard", "edge"})

SAMPLER_CONFIG_KEYS = frozenset(
    {
        "sampler_version",
        "seed",
        "family_weights",
        "constraint_count_weights",
        "operator_weights",
        "operator_cardinality",
        "genre_sampling",
        "tag_sampling",
        "numeric_sampling",
        "combination_policy_version",
        "audit_tolerances",
    }
)

OPERATOR_CARDINALITIES = MappingProxyType(
    {
        "all_of": frozenset({1, 2, 3}),
        "any_of": frozenset({2, 3}),
        "none_of": frozenset({1, 2}),
    }
)

GENRE_SAMPLING_KEYS = frozenset(
    {
        "minimum_coverage_per_value",
        "maximum_value_share",
        "default_weight",
        "priority_weights",
    }
)

TAG_SAMPLING_KEYS = frozenset(
    {
        "minimum_coverage_per_value",
        "maximum_value_share",
        "default_weight",
        "priority_weights",
        "tier_weights",
        "value_tiers",
    }
)

NUMERIC_SAMPLING_KEYS = frozenset({"year", "episodes"})

NUMERIC_POLICY_KEYS = frozenset(
    {
        "pattern_weights",
        "pool_weights",
        "common_values",
        "catalog_region_values",
        "long_tail_values",
    }
)

AUDIT_TOLERANCE_KEYS = frozenset(
    {
        "family_max_absolute_error",
        "constraint_count_max_absolute_error",
        "operator_max_absolute_error",
        "minimum_value_coverage_ratio",
        "maximum_signature_share",
    }
)


def _require_exact_object(
    value: Any,
    name: str,
    expected_keys: set[str] | frozenset[str],
) -> dict[str, Any]:
    """Require a JSON object with exactly the declared keys."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")

    actual_keys = set(value)
    missing_keys = expected_keys - actual_keys
    unknown_keys = actual_keys - expected_keys

    if missing_keys or unknown_keys:
        details: list[str] = []

        if missing_keys:
            details.append(f"missing keys: {sorted(missing_keys)}")

        if unknown_keys:
            details.append(f"unknown keys: {sorted(unknown_keys)}")

        raise ValueError(f"{name} has invalid keys; " + "; ".join(details))

    return value


def _parse_weight_table(
    value: Any,
    name: str,
    expected_keys: set[str] | frozenset[str],
) -> WeightTableSpec:
    """Parse one exact JSON weight table into an immutable specification."""
    raw_weights = _require_exact_object(
        value,
        name,
        expected_keys,
    )

    return WeightTableSpec(
        weights=MappingProxyType(dict(raw_weights)),
    )


def _parse_cardinality_weights(
    value: Any,
    name: str,
    expected_cardinalities: frozenset[int],
) -> Mapping[int, float]:
    """Parse canonical JSON cardinality keys into immutable integer keys."""
    expected_json_keys = frozenset(
        str(cardinality) for cardinality in expected_cardinalities
    )

    raw_weights = _require_exact_object(
        value,
        name,
        expected_json_keys,
    )

    return MappingProxyType(
        {int(cardinality): weight for cardinality, weight in raw_weights.items()}
    )


def _freeze_json_object(
    value: Any,
    name: str,
) -> Mapping[str, Any]:
    """Copy one open-key JSON object into an immutable mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")

    return MappingProxyType(dict(value))


def _parse_value_tuple(
    value: Any,
    name: str,
) -> tuple[Any, ...]:
    """Convert one JSON array to a tuple without changing its order."""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")

    return tuple(value)


def _parse_numeric_policy(
    value: Any,
    name: str,
) -> NumericSamplingPolicySpec:
    """Parse one immutable year or episode sampling policy."""
    raw_policy = _require_exact_object(
        value,
        name,
        NUMERIC_POLICY_KEYS,
    )

    pattern_weights = _require_exact_object(
        raw_policy["pattern_weights"],
        f"{name}.pattern_weights",
        NUMERIC_RANGE_PATTERNS,
    )

    pool_weights = _require_exact_object(
        raw_policy["pool_weights"],
        f"{name}.pool_weights",
        NUMERIC_VALUE_POOLS,
    )

    return NumericSamplingPolicySpec(
        pattern_weights=MappingProxyType(dict(pattern_weights)),
        pool_weights=MappingProxyType(dict(pool_weights)),
        common_values=_parse_value_tuple(
            raw_policy["common_values"],
            f"{name}.common_values",
        ),
        catalog_region_values=_parse_value_tuple(
            raw_policy["catalog_region_values"],
            f"{name}.catalog_region_values",
        ),
        long_tail_values=_parse_value_tuple(
            raw_policy["long_tail_values"],
            f"{name}.long_tail_values",
        ),
    )


def load_sampler_config(path: Path) -> SemanticSamplerConfigSpec:
    """Load one strict JSON config without filling unspecified policy values."""
    # Strict loader contract:
    # - UTF-8 JSON；I/O/encoding/JSON/contract errors 对调用方统一为 ValueError；
    # - 顶层及每个嵌套对象采用精确 key set，拒绝 unknown/missing keys；
    # - JSON weight-table keys 转为不可变 MappingProxyType；cardinality keys 转 int；
    # - value arrays 转 tuple，但不得排序来掩盖 duplicate/non-canonical input；
    # - 构造 SemanticSamplerConfigSpec 后调用 validate_sampler_config；
    # - 不读取 production API，不推导缺失权重，不创建 sampler 或 SemanticSpec。
    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to read or parse sampler config: {path}") from exc

    config = _require_exact_object(
        raw_config,
        "sampler config",
        SAMPLER_CONFIG_KEYS,
    )

    family_weights = _parse_weight_table(
        config["family_weights"],
        "family_weights",
        SEMANTIC_FAMILIES,
    )

    constraint_count_weights = _parse_weight_table(
        config["constraint_count_weights"],
        "constraint_count_weights",
        HARD_CONSTRAINT_COUNT_BUCKETS,
    )

    operator_weights = _parse_weight_table(
        config["operator_weights"],
        "operator_weights",
        SET_OPERATORS,
    )

    raw_operator_cardinality = _require_exact_object(
        config["operator_cardinality"],
        "operator_cardinality",
        SET_OPERATORS,
    )

    operator_cardinality = OperatorCardinalityPolicySpec(
        all_of=_parse_cardinality_weights(
            raw_operator_cardinality["all_of"],
            "operator_cardinality.all_of",
            OPERATOR_CARDINALITIES["all_of"],
        ),
        any_of=_parse_cardinality_weights(
            raw_operator_cardinality["any_of"],
            "operator_cardinality.any_of",
            OPERATOR_CARDINALITIES["any_of"],
        ),
        none_of=_parse_cardinality_weights(
            raw_operator_cardinality["none_of"],
            "operator_cardinality.none_of",
            OPERATOR_CARDINALITIES["none_of"],
        ),
    )

    raw_genre_sampling = _require_exact_object(
        config["genre_sampling"],
        "genre_sampling",
        GENRE_SAMPLING_KEYS,
    )

    genre_sampling = CategoricalValuePolicySpec(
        minimum_coverage_per_value=raw_genre_sampling["minimum_coverage_per_value"],
        maximum_value_share=raw_genre_sampling["maximum_value_share"],
        default_weight=raw_genre_sampling["default_weight"],
        priority_weights=_freeze_json_object(
            raw_genre_sampling["priority_weights"],
            "genre_sampling.priority_weights",
        ),
    )

    raw_tag_sampling = _require_exact_object(
        config["tag_sampling"],
        "tag_sampling",
        TAG_SAMPLING_KEYS,
    )

    tag_sampling = TagValuePolicySpec(
        minimum_coverage_per_value=raw_tag_sampling["minimum_coverage_per_value"],
        maximum_value_share=raw_tag_sampling["maximum_value_share"],
        default_weight=raw_tag_sampling["default_weight"],
        priority_weights=_freeze_json_object(
            raw_tag_sampling["priority_weights"],
            "tag_sampling.priority_weights",
        ),
        tier_weights=_freeze_json_object(
            raw_tag_sampling["tier_weights"],
            "tag_sampling.tier_weights",
        ),
        value_tiers=_freeze_json_object(
            raw_tag_sampling["value_tiers"],
            "tag_sampling.value_tiers",
        ),
    )

    raw_numeric_sampling = _require_exact_object(
        config["numeric_sampling"],
        "numeric_sampling",
        NUMERIC_SAMPLING_KEYS,
    )

    year_sampling = _parse_numeric_policy(
        raw_numeric_sampling["year"],
        "numeric_sampling.year",
    )

    episode_sampling = _parse_numeric_policy(
        raw_numeric_sampling["episodes"],
        "numeric_sampling.episodes",
    )

    raw_audit_tolerances = _require_exact_object(
        config["audit_tolerances"],
        "audit_tolerances",
        AUDIT_TOLERANCE_KEYS,
    )

    audit_tolerances = DistributionAuditToleranceSpec(
        family_max_absolute_error=raw_audit_tolerances["family_max_absolute_error"],
        constraint_count_max_absolute_error=raw_audit_tolerances[
            "constraint_count_max_absolute_error"
        ],
        operator_max_absolute_error=raw_audit_tolerances["operator_max_absolute_error"],
        minimum_value_coverage_ratio=raw_audit_tolerances[
            "minimum_value_coverage_ratio"
        ],
        maximum_signature_share=raw_audit_tolerances["maximum_signature_share"],
    )

    sampler_config = SemanticSamplerConfigSpec(
        sampler_version=config["sampler_version"],
        seed=config["seed"],
        family_weights=family_weights,
        constraint_count_weights=constraint_count_weights,
        operator_weights=operator_weights,
        operator_cardinality=operator_cardinality,
        genre_sampling=genre_sampling,
        tag_sampling=tag_sampling,
        year_sampling=year_sampling,
        episode_sampling=episode_sampling,
        combination_policy_version=config["combination_policy_version"],
        audit_tolerances=audit_tolerances,
    )

    validate_sampler_config(sampler_config)
    return sampler_config


def _validate_canonical_string(
    value: Any,
    name: str,
) -> None:
    """Require a non-empty string without outer whitespace."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(
            f"{name} must be a non-empty string "
            "without leading or trailing whitespace"
        )


def _validate_integer(
    value: Any,
    name: str,
) -> None:
    """Require an integer while rejecting bool."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")


def _validate_positive_integer(
    value: Any,
    name: str,
) -> None:
    """Require an integer greater than zero."""
    _validate_integer(value, name)

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _validate_positive_number(
    value: Any,
    name: str,
) -> None:
    """Require one finite positive integer or float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")

    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _validate_ratio(
    value: Any,
    name: str,
) -> None:
    """Require a finite ratio in the interval (0, 1]."""
    _validate_positive_number(value, name)

    if value > 1:
        raise ValueError(f"{name} must be less than or equal to 1")


def _validate_weight_mapping(
    value: Any,
    name: str,
    expected_keys: set[Any] | frozenset[Any] | None = None,
) -> None:
    """Validate one mapping of names or cardinalities to positive weights."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")

    if expected_keys is not None:
        actual_keys = set(value)

        if actual_keys != expected_keys:
            missing_keys = expected_keys - actual_keys
            unknown_keys = actual_keys - expected_keys
            details: list[str] = []

            if missing_keys:
                details.append(f"missing keys: {sorted(missing_keys)}")

            if unknown_keys:
                details.append(f"unknown keys: {sorted(unknown_keys)}")

            raise ValueError(f"{name} has invalid keys; " + "; ".join(details))
    else:
        for key in value:
            _validate_canonical_string(
                key,
                f"{name} key",
            )

    for key, weight in value.items():
        _validate_positive_number(
            weight,
            f"{name}[{key!r}]",
        )


def _validate_common_value_policy(
    policy: CategoricalValuePolicySpec | TagValuePolicySpec,
    name: str,
) -> None:
    """Validate fields shared by genre and tag sampling policies."""
    _validate_positive_integer(
        policy.minimum_coverage_per_value,
        f"{name}.minimum_coverage_per_value",
    )
    _validate_ratio(
        policy.maximum_value_share,
        f"{name}.maximum_value_share",
    )
    _validate_positive_number(
        policy.default_weight,
        f"{name}.default_weight",
    )
    _validate_weight_mapping(
        policy.priority_weights,
        f"{name}.priority_weights",
    )


def _validate_value_tiers(
    value_tiers: Any,
    name: str,
) -> None:
    """Validate canonical tag names mapped to approved sampling tiers."""
    if not isinstance(value_tiers, Mapping):
        raise ValueError(f"{name} must be a mapping")

    for tag_name, tier in value_tiers.items():
        _validate_canonical_string(
            tag_name,
            f"{name} key",
        )

        if not isinstance(tier, str) or tier not in TAG_SAMPLING_TIERS:
            raise ValueError(
                f"{name}[{tag_name!r}] must be one of " f"{sorted(TAG_SAMPLING_TIERS)}"
            )


def _validate_numeric_policy(
    policy: Any,
    name: str,
) -> None:
    """Validate one standalone year or episode sampling policy."""
    if not isinstance(policy, NumericSamplingPolicySpec):
        raise ValueError(f"{name} must be a NumericSamplingPolicySpec")

    _validate_weight_mapping(
        policy.pattern_weights,
        f"{name}.pattern_weights",
        NUMERIC_RANGE_PATTERNS,
    )
    _validate_weight_mapping(
        policy.pool_weights,
        f"{name}.pool_weights",
        NUMERIC_VALUE_POOLS,
    )

    value_pools = (
        ("common_values", policy.common_values),
        ("catalog_region_values", policy.catalog_region_values),
        ("long_tail_values", policy.long_tail_values),
    )

    seen_values: set[int] = set()

    for pool_name, values in value_pools:
        full_name = f"{name}.{pool_name}"

        if not isinstance(values, tuple):
            raise ValueError(f"{full_name} must be a tuple")

        if not values:
            raise ValueError(f"{full_name} must not be empty")

        for index, value in enumerate(values):
            _validate_positive_integer(
                value,
                f"{full_name}[{index}]",
            )

        if len(values) != len(set(values)):
            raise ValueError(f"{full_name} must not contain duplicate values")

        if values != tuple(sorted(values)):
            raise ValueError(f"{full_name} must use ascending canonical order")

        overlap = seen_values.intersection(values)

        if overlap:
            raise ValueError(
                f"{full_name} overlaps another value pool: " f"{sorted(overlap)}"
            )

        seen_values.update(values)


def _validate_audit_tolerances(
    tolerances: Any,
) -> None:
    """Validate all standalone distribution audit ratios."""
    if not isinstance(
        tolerances,
        DistributionAuditToleranceSpec,
    ):
        raise ValueError("audit_tolerances must be a " "DistributionAuditToleranceSpec")

    ratio_fields = (
        "family_max_absolute_error",
        "constraint_count_max_absolute_error",
        "operator_max_absolute_error",
        "minimum_value_coverage_ratio",
        "maximum_signature_share",
    )

    for field_name in ratio_fields:
        _validate_ratio(
            getattr(tolerances, field_name),
            f"audit_tolerances.{field_name}",
        )


def validate_sampler_config(config: SemanticSamplerConfigSpec) -> None:
    """Validate the standalone sampler contract, independent of DomainRules."""
    # Standalone invariant contract:
    # - sampler_version/combination_policy_version 非空且无首尾 whitespace；seed 是 int 非 bool；
    # - family/count/operator tables 的 key set 必须分别精确等于本模块常量；
    # - relative weights 必须是有限正数；不要求浮点和恰好为 1；
    # - cardinality 精确允许 all_of={1,2,3}, any_of={2,3}, none_of={1,2}；
    # - coverage 是正 int，share/tolerance ratio 在 (0,1]，default/priority/tier weights 为正；
    # - tag tiers 只能 core/standard/edge；value_tiers 与 priority keys 唯一且 canonical；
    # - numeric patterns/pools key set 精确，所有 pools 非空、内部及跨 pool 不重复；
    # - numeric value 是正 int 非 bool，tuple 使用升序 canonical order；
    # - 不把 year/episode validity 或 production sampling cutoffs 写死在本函数。
    if not isinstance(config, SemanticSamplerConfigSpec):
        raise ValueError("config must be a SemanticSamplerConfigSpec instance")

    _validate_canonical_string(
        config.sampler_version,
        "sampler_version",
    )
    _validate_canonical_string(
        config.combination_policy_version,
        "combination_policy_version",
    )
    _validate_integer(config.seed, "seed")

    weight_tables = (
        (
            "family_weights",
            config.family_weights,
            SEMANTIC_FAMILIES,
        ),
        (
            "constraint_count_weights",
            config.constraint_count_weights,
            HARD_CONSTRAINT_COUNT_BUCKETS,
        ),
        (
            "operator_weights",
            config.operator_weights,
            SET_OPERATORS,
        ),
    )

    for name, table, expected_keys in weight_tables:
        if not isinstance(table, WeightTableSpec):
            raise ValueError(f"{name} must be a WeightTableSpec")

        _validate_weight_mapping(
            table.weights,
            f"{name}.weights",
            expected_keys,
        )

    if not isinstance(
        config.operator_cardinality,
        OperatorCardinalityPolicySpec,
    ):
        raise ValueError(
            "operator_cardinality must be an " "OperatorCardinalityPolicySpec"
        )

    for operator in ("all_of", "any_of", "none_of"):
        cardinality_weights = getattr(
            config.operator_cardinality,
            operator,
        )

        _validate_weight_mapping(
            cardinality_weights,
            f"operator_cardinality.{operator}",
            OPERATOR_CARDINALITIES[operator],
        )

    if not isinstance(
        config.genre_sampling,
        CategoricalValuePolicySpec,
    ):
        raise ValueError("genre_sampling must be a " "CategoricalValuePolicySpec")

    _validate_common_value_policy(
        config.genre_sampling,
        "genre_sampling",
    )

    if not isinstance(
        config.tag_sampling,
        TagValuePolicySpec,
    ):
        raise ValueError("tag_sampling must be a TagValuePolicySpec")

    _validate_common_value_policy(
        config.tag_sampling,
        "tag_sampling",
    )

    _validate_weight_mapping(
        config.tag_sampling.tier_weights,
        "tag_sampling.tier_weights",
        TAG_SAMPLING_TIERS,
    )

    _validate_value_tiers(
        config.tag_sampling.value_tiers,
        "tag_sampling.value_tiers",
    )

    _validate_numeric_policy(
        config.year_sampling,
        "numeric_sampling.year",
    )

    _validate_numeric_policy(
        config.episode_sampling,
        "numeric_sampling.episodes",
    )

    _validate_audit_tolerances(
        config.audit_tolerances,
    )


def _validate_mapping_keys_in_allowlist(
    value: Mapping[str, Any],
    name: str,
    allowed_values: frozenset[str],
) -> None:
    """Require every configured mapping key to be active in one vocabulary."""
    unknown_values = set(value) - allowed_values

    if unknown_values:
        raise ValueError(
            f"{name} contains inactive values: " f"{sorted(unknown_values)}"
        )


def _validate_numeric_policy_against_rule(
    policy: NumericSamplingPolicySpec,
    rule: NumericRule,
    name: str,
) -> None:
    """Require every configured numeric cutoff to satisfy its domain rule."""
    value_pools = (
        ("common_values", policy.common_values),
        ("catalog_region_values", policy.catalog_region_values),
        ("long_tail_values", policy.long_tail_values),
    )

    for pool_name, values in value_pools:
        for value in values:
            if rule.minimum is not None and value < rule.minimum:
                raise ValueError(
                    f"{name}.{pool_name} contains {value}, "
                    f"which is below domain minimum {rule.minimum}"
                )

            if rule.maximum is not None and value > rule.maximum:
                raise ValueError(
                    f"{name}.{pool_name} contains {value}, "
                    f"which is above domain maximum {rule.maximum}"
                )


def validate_sampler_config_against_domain(
    config: SemanticSamplerConfigSpec,
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> None:
    """Bind a standalone sampler policy to actual validated rules and subset."""
    # Domain-binding contract:
    # - 先 validate_sampler_config，再 validate_executable_rules_identity；
    # - genre priority keys 必须属于 active rules.genres；
    # - tag priority/value_tiers keys 必须属于 active rules.tags；
    # - numeric pools 必须落在 rules.year/episodes validity bounds；
    # - normalization family weight > 0 时至少存在一个可用 tag group；
    # - reference family weight > 0 不代表 title pool 已存在，本阶段不伪造 title；
    # - 不要求 approved subset 中 inactive tags 出现在 sampler value policy；
    # - 不修改 config/rules/subset，不调用 builder rejection 作为配置验证策略。
    validate_sampler_config(config)

    validate_executable_rules_identity(
        rules,
        subset,
    )

    _validate_mapping_keys_in_allowlist(
        config.genre_sampling.priority_weights,
        "genre_sampling.priority_weights",
        rules.genres,
    )

    _validate_mapping_keys_in_allowlist(
        config.tag_sampling.priority_weights,
        "tag_sampling.priority_weights",
        rules.tags,
    )

    _validate_mapping_keys_in_allowlist(
        config.tag_sampling.value_tiers,
        "tag_sampling.value_tiers",
        rules.tags,
    )

    _validate_numeric_policy_against_rule(
        config.year_sampling,
        rules.year,
        "numeric_sampling.year",
    )

    _validate_numeric_policy_against_rule(
        config.episode_sampling,
        rules.episodes,
        "numeric_sampling.episodes",
    )

    normalization_weight = config.family_weights.weights["normalization"]

    if normalization_weight > 0 and not rules.tag_groups:
        raise ValueError(
            "normalization family has positive weight, "
            "but DomainRules contains no usable tag group"
        )

    return None
