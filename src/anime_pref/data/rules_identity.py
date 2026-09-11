"""Canonical identity and executable-subset binding for DomainRules."""

from typing import Any

from anime_pref.data.query_builder import DomainRules
from anime_pref.schemas.taxonomy import ExecutableTagSubset


def canonical_rules_to_mapping(rules: DomainRules) -> dict[str, Any]:
    """Return the complete canonical rules document, excluding rules_hash."""
    # TODO-43a:
    # - 严格验证 DomainRules 的 identity、active vocab、groups 和 numeric rules；
    # - 输出 rules_version/schema_version/executable subset version+hash；
    # - genres/tags/formats/statuses/soft_preferences 全部 canonical sort；
    # - tag_groups 按 group name 排序，members/operators 排序，并保留 rule ID；
    # - numeric_rules 固定 episodes/year 与 minimum/maximum key order；
    # - rules.rules_hash 绝不进入 mapping，避免自引用；不修改 rules。
    raise NotImplementedError("TODO-43a: build canonical DomainRules mapping")


def dumps_canonical_rules(rules: DomainRules) -> str:
    """Serialize the canonical rules document as deterministic Unicode JSON."""
    # TODO-43b: 复用 mapping；ensure_ascii=False、compact separators、allow_nan=False。
    raise NotImplementedError("TODO-43b: serialize canonical DomainRules")


def domain_rules_sha256(rules: DomainRules) -> str:
    """Hash the canonical rules document as UTF-8 bytes."""
    # TODO-43c: SHA-256(dumps_canonical_rules(rules).encode("utf-8")).hexdigest()。
    raise NotImplementedError("TODO-43c: hash canonical DomainRules")


def validate_executable_rules_identity(
    rules: DomainRules,
    subset: ExecutableTagSubset,
) -> None:
    """Validate rules identity and active vocabulary against an actual subset."""
    # TODO-44:
    # - 严格验证 subset，并重算 executable_tag_subset_sha256(subset)；
    # - rules 声明的 subset version/hash 必须与实际 subset 完全一致；
    # - rules.rules_hash 必须等于 domain_rules_sha256(rules)；
    # - 复用 validate_domain_rule_tag_targets 检查：
    #     group members ⊆ active rules.tags ⊆ approved subset tags；
    # - 失败直接 ValueError，不写回或修复任一对象。
    raise NotImplementedError("TODO-44: bind DomainRules identity to approved subset")
