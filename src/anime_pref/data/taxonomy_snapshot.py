"""Canonicalize, hash, and persist AniList taxonomy snapshots."""

# 调用会抛 NotImplementedError，不能把已定义的接口视为已完成的采集/审核能力。

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from anime_pref.schemas.taxonomy import (
    CanonicalTaxonomySnapshot,
    TaxonomySnapshotManifest,
    TaxonomyTagSpec,
)

SNAPSHOT_SCHEMA_VERSION = "anilist-taxonomy-snapshot-v0.1"
ANILIST_SOURCE = "AniList GraphQL API"
ANILIST_RESOURCES = ("GenreCollection", "MediaTagCollection")


def build_canonical_taxonomy_snapshot(
    source_payload: Mapping[str, Any],
    *,
    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> CanonicalTaxonomySnapshot:
    """Validate a raw response and retain only approved canonical fields."""
    # - 严格读取 source_payload["data"] 下两个 resource；非法结构统一 ValueError；
    # - genre 必须是非空、无首尾 whitespace 的唯一字符串；
    # - tag 精确读取 id/name/description/category/isGeneralSpoiler/isAdult；
    # - id 为正 int（排除 bool）；name/category 非空且无首尾 whitespace；
    # - description 只允许 str 或 None；两个 flag 必须是 bool；
    # - 拒绝 duplicate tag id/name；不要读取或创造 media-specific rank；
    # - genres 按字符串升序，tags 按 (id, name) 升序；
    # - 不修改 source_payload，不静默 strip，不保留未批准字段。
    if not isinstance(source_payload, Mapping):
        raise ValueError("source_payload must be a mapping")

    if (
        not isinstance(snapshot_schema_version, str)
        or not snapshot_schema_version
        or snapshot_schema_version != snapshot_schema_version.strip()
    ):
        raise ValueError(
            "snapshot_schema_version must be a non-empty string "
            "without leading or trailing whitespace"
        )

    data = source_payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("source_payload must contain a valid 'data' object")

    raw_genres = data.get("GenreCollection")
    if not isinstance(raw_genres, list):
        raise ValueError("'data.GenreCollection' must be a list")

    raw_tags = data.get("MediaTagCollection")
    if not isinstance(raw_tags, list):
        raise ValueError("'data.MediaTagCollection' must be a list")

    canonical_genres: list[str] = []
    seen_genres: set[str] = set()

    for index, genre in enumerate(raw_genres):
        if not isinstance(genre, str):
            raise ValueError(f"GenreCollection[{index}] must be a string")
        if not genre or genre != genre.strip():
            raise ValueError(
                f"GenreCollection[{index}] must be non-empty and have no leading or trailing whitespace"
            )
        if genre in seen_genres:
            raise ValueError(f"duplicate genre name: {genre!r}")

        seen_genres.add(genre)
        canonical_genres.append(genre)

    sorted_genres = tuple(sorted(canonical_genres))

    required_tag_fields = (
        "id",
        "name",
        "description",
        "category",
        "isGeneralSpoiler",
        "isAdult",
    )

    canonical_tags: list[TaxonomyTagSpec] = []
    seen_tag_ids: set[int] = set()
    seen_tag_names: set[str] = set()
    for index, raw_tag in enumerate(raw_tags):
        if not isinstance(raw_tag, Mapping):
            raise ValueError(f"MediaTagCollection[{index}] must be an object")

        missing_fields = [
            field for field in required_tag_fields if field not in raw_tag
        ]
        if missing_fields:
            raise ValueError(
                f"MediaTagCollection[{index}] is missing fields: " f"{missing_fields}"
            )

        tag_id = raw_tag["id"]
        name = raw_tag["name"]
        description = raw_tag["description"]
        category = raw_tag["category"]
        is_general_spoiler = raw_tag["isGeneralSpoiler"]
        is_adult = raw_tag["isAdult"]

        if isinstance(tag_id, bool) or not isinstance(tag_id, int) or tag_id <= 0:
            raise ValueError(
                f"MediaTagCollection[{index}].id must be a positive integer"
            )

        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError(
                f"MediaTagCollection[{index}].name must be a non-empty "
                "string without leading or trailing whitespace"
            )

        if description is not None and not isinstance(description, str):
            raise ValueError(
                f"MediaTagCollection[{index}].description " "must be a string or None"
            )

        if (
            not isinstance(category, str)
            or not category
            or category != category.strip()
        ):
            raise ValueError(
                f"MediaTagCollection[{index}].category must be a non-empty "
                "string without leading or trailing whitespace"
            )

        if not isinstance(is_general_spoiler, bool):
            raise ValueError(
                f"MediaTagCollection[{index}].isGeneralSpoiler " "must be a boolean"
            )

        if not isinstance(is_adult, bool):
            raise ValueError(f"MediaTagCollection[{index}].isAdult must be a boolean")

        if tag_id in seen_tag_ids:
            raise ValueError(f"duplicate tag id: {tag_id}")

        if name in seen_tag_names:
            raise ValueError(f"duplicate tag name: {name!r}")

        seen_tag_ids.add(tag_id)
        seen_tag_names.add(name)

        canonical_tags.append(
            TaxonomyTagSpec(
                id=tag_id,
                name=name,
                description=description,
                category=category,
                is_general_spoiler=is_general_spoiler,
                is_adult=is_adult,
            )
        )

    sorted_tags = tuple(
        sorted(
            canonical_tags,
            key=lambda tag: (tag.id, tag.name),
        )
    )

    return CanonicalTaxonomySnapshot(
        snapshot_schema_version=snapshot_schema_version,
        genres=sorted_genres,
        tags=sorted_tags,
    )


def canonical_taxonomy_to_mapping(
    snapshot: CanonicalTaxonomySnapshot,
) -> dict[str, Any]:
    """Convert a validated snapshot to its one full canonical JSON shape."""
    # TODO-28a: 固定 key order，tag 字段使用 schema 定义顺序；保留 None；返回全新对象。
    raise NotImplementedError("TODO-28a: map canonical taxonomy to JSON types")


def dumps_canonical_taxonomy(snapshot: CanonicalTaxonomySnapshot) -> str:
    """Serialize the canonical snapshot deterministically as Unicode JSON."""
    # TODO-28b: 复用 mapping；ensure_ascii=False、紧凑 separators、allow_nan=False。
    raise NotImplementedError("TODO-28b: serialize canonical taxonomy")


def load_canonical_taxonomy_snapshot(path: Path) -> CanonicalTaxonomySnapshot:
    """Load canonical.json and reject any non-canonical structure or ordering."""
    # TODO-28c:
    # - UTF-8 读取 JSON；精确检查 canonical snapshot 与 tag 的 key 集合和类型；
    # - 构造 dataclass 后复用 canonical mapping/serializer validation；
    # - 文件内容必须已经是 canonical order，不静默排序、strip 或修复；
    # - JSON parse 错误与 contract 错误对调用方统一表现为 ValueError。
    raise NotImplementedError("TODO-28c: load canonical taxonomy")


def taxonomy_snapshot_sha256(snapshot: CanonicalTaxonomySnapshot) -> str:
    """Hash canonical UTF-8 JSON, never raw HTTP response bytes."""
    # TODO-28d: 对 dumps_canonical_taxonomy(snapshot).encode("utf-8") 计算 SHA-256 hex。
    raise NotImplementedError("TODO-28d: hash canonical taxonomy")


def build_taxonomy_snapshot_manifest(
    snapshot: CanonicalTaxonomySnapshot,
    *,
    fetched_at_utc: str,
    source: str = ANILIST_SOURCE,
    resource: tuple[str, ...] = ANILIST_RESOURCES,
) -> TaxonomySnapshotManifest:
    """Build manifest metadata that is excluded from the content hash."""
    # TODO-29:
    # - 验证 source/resource/fetched_at_utc；时间必须是带 Z 的 UTC ISO-8601 字符串；
    # - counts 从 snapshot 计算，hash 调 taxonomy_snapshot_sha256；
    # - snapshot_schema_version 从 snapshot 读取；不得由调用方覆盖 counts/hash/version。
    raise NotImplementedError("TODO-29: build taxonomy snapshot manifest")


def write_taxonomy_snapshot_bundle(
    source_payload: Mapping[str, Any],
    *,
    output_dir: Path,
    fetched_at_utc: str,
) -> TaxonomySnapshotManifest:
    """Write source.json, canonical.json, and manifest.json without overwriting."""
    # TODO-30:
    # - 构造 canonical snapshot 与 manifest 后再开始写文件；
    # - 创建 output_dir，但三个目标中任一已存在都先抛 FileExistsError；
    # - source.json 保留输入 payload；canonical.json 使用 canonical serializer；
    # - manifest.json 使用固定字段顺序、UTF-8 和末尾换行；
    # - 返回 manifest。不要把 fetched_at 写入 canonical content/hash。
    raise NotImplementedError("TODO-30: persist taxonomy snapshot bundle")
