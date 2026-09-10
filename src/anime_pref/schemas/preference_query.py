"""Dataset semantic specification and AnimePreferenceQuery v0.1.1 shapes.

These dataclasses describe sampled canonical semantics, not raw user text.
They are not the final Gold JSON and deliberately perform no implicit cleanup
or normalization. Accepted non-empty strings must not have outer whitespace.
"""

from dataclasses import dataclass, field


# 三个 operator 保存 canonical 值；tuple 类型标注不执行运行时校验。
@dataclass(frozen=True)
class SetConstraintSpec:
    """Canonical values grouped by the output operator they belong to."""

    all_of: tuple[str, ...] = field(default_factory=tuple)
    any_of: tuple[str, ...] = field(default_factory=tuple)
    none_of: tuple[str, ...] = field(default_factory=tuple)


# 闭区间边界；None 表示用户未表达，该模型不会自行填入领域上下界。
@dataclass(frozen=True)
class RangeConstraintSpec:
    """Inclusive numeric bounds; None means the user expressed no such bound."""

    min: int | None = None
    max: int | None = None


# 展开前语义源；tag_groups 仅供构建与 provenance，最终 Gold 不输出该字段。
@dataclass(frozen=True)
class SemanticSpec:
    """Canonical semantic source from which Gold JSON is built.

    ``tag_groups`` is an internal dataset-construction field. For example, the
    approved group ``HAREM`` expands deterministically to three AniList tags.
    It must never appear in the final AnimePreferenceQuery JSON.

    ``formats`` and ``status`` are OR lists of acceptable values. Values in
    ``soft_preferences`` must come from an approved canonical vocabulary;
    expressions without an approved mapping belong in ``unresolved_preferences``.
    """

    genres: SetConstraintSpec = field(default_factory=SetConstraintSpec)
    tags: SetConstraintSpec = field(default_factory=SetConstraintSpec)
    tag_groups: SetConstraintSpec = field(default_factory=SetConstraintSpec)
    year: RangeConstraintSpec = field(default_factory=RangeConstraintSpec)
    episodes: RangeConstraintSpec = field(default_factory=RangeConstraintSpec)
    formats: tuple[str, ...] = field(default_factory=tuple)
    status: tuple[str, ...] = field(default_factory=tuple)
    reference_titles: tuple[str, ...] = field(default_factory=tuple)
    soft_preferences: tuple[str, ...] = field(default_factory=tuple)
    unresolved_preferences: tuple[str, ...] = field(default_factory=tuple)
