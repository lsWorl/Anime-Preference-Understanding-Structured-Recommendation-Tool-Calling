"""Canonicalize, hash, and persist AniList taxonomy snapshots."""

# 本模块实现 canonical snapshot、稳定哈希、严格读取和不可覆盖的 bundle 写入。
import hashlib
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
import json

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
    # 固定 key order，tag 字段使用 schema 定义顺序；保留 None；返回全新对象。
    if not isinstance(snapshot, CanonicalTaxonomySnapshot):
        raise ValueError("snapshot must be a CanonicalTaxonomySnapshot")

    if not isinstance(snapshot.genres, tuple):
        raise ValueError("snapshot.genres must be a tuple")

    if not isinstance(snapshot.tags, tuple):
        raise ValueError("snapshot.tags must be a tuple")

    for index, tag in enumerate(snapshot.tags):
        if not isinstance(tag, TaxonomyTagSpec):
            raise ValueError(f"snapshot.tags[{index}] must be a TaxonomyTagSpec")

    validation_source = {
        "data": {
            "GenreCollection": list(snapshot.genres),
            "MediaTagCollection": [
                {
                    "id": tag.id,
                    "name": tag.name,
                    "description": tag.description,
                    "category": tag.category,
                    "isGeneralSpoiler": tag.is_general_spoiler,
                    "isAdult": tag.is_adult,
                }
                for tag in snapshot.tags
            ],
        }
    }

    rebuilt_snapshot = build_canonical_taxonomy_snapshot(
        validation_source,
        snapshot_schema_version=snapshot.snapshot_schema_version,
    )

    if rebuilt_snapshot != snapshot:
        raise ValueError("snapshot content or ordering is not canonical")

    return {
        "snapshot_schema_version": snapshot.snapshot_schema_version,
        "genres": list(snapshot.genres),
        "tags": [
            {
                "id": tag.id,
                "name": tag.name,
                "description": tag.description,
                "category": tag.category,
                "is_general_spoiler": tag.is_general_spoiler,
                "is_adult": tag.is_adult,
            }
            for tag in snapshot.tags
        ],
    }


def dumps_canonical_taxonomy(snapshot: CanonicalTaxonomySnapshot) -> str:
    """Serialize the canonical snapshot deterministically as Unicode JSON."""
    # 复用 mapping；ensure_ascii=False、紧凑 separators、allow_nan=False。
    canonical_mapping = canonical_taxonomy_to_mapping(snapshot)

    return json.dumps(
        canonical_mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def load_canonical_taxonomy_snapshot(path: Path) -> CanonicalTaxonomySnapshot:
    """Load canonical.json and reject any non-canonical structure or ordering."""
    # - UTF-8 读取 JSON；精确检查 canonical snapshot 与 tag 的 key 集合和类型；
    # - 构造 dataclass 后复用 canonical mapping/serializer validation；
    # - 文件内容必须已经是 canonical order，不静默排序、strip 或修复；
    # - JSON parse 错误与 contract 错误对调用方统一表现为 ValueError。
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value

        return result

    try:
        json_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"failed to read canonical taxonomy file: {path}") from exc

    try:
        raw_snapshot = json.loads(
            json_text,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid canonical taxonomy JSON: {path}") from exc

    if not isinstance(raw_snapshot, dict):
        raise ValueError("canonical taxonomy root must be a JSON object")

    expected_root_keys = (
        "snapshot_schema_version",
        "genres",
        "tags",
    )

    if tuple(raw_snapshot.keys()) != expected_root_keys:
        raise ValueError(
            "canonical taxonomy keys must be exactly "
            f"{expected_root_keys} in that order"
        )

    if not isinstance(raw_snapshot["snapshot_schema_version"], str):
        raise ValueError("snapshot_schema_version must be a string")

    if not isinstance(raw_snapshot["genres"], list):
        raise ValueError("genres must be a list")

    if not isinstance(raw_snapshot["tags"], list):
        raise ValueError("tags must be a list")

    expected_tag_keys = (
        "id",
        "name",
        "description",
        "category",
        "is_general_spoiler",
        "is_adult",
    )

    tag_specs: list[TaxonomyTagSpec] = []

    for index, raw_tag in enumerate(raw_snapshot["tags"]):
        if not isinstance(raw_tag, dict):
            raise ValueError(f"tags[{index}] must be a JSON object")

        if tuple(raw_tag.keys()) != expected_tag_keys:
            raise ValueError(
                f"tags[{index}] keys must be exactly "
                f"{expected_tag_keys} in that order"
            )

        tag_specs.append(
            TaxonomyTagSpec(
                id=raw_tag["id"],
                name=raw_tag["name"],
                description=raw_tag["description"],
                category=raw_tag["category"],
                is_general_spoiler=raw_tag["is_general_spoiler"],
                is_adult=raw_tag["is_adult"],
            )
        )

    candidate_snapshot = CanonicalTaxonomySnapshot(
        snapshot_schema_version=raw_snapshot["snapshot_schema_version"],
        genres=tuple(raw_snapshot["genres"]),
        tags=tuple(tag_specs),
    )

    try:
        canonical_mapping = canonical_taxonomy_to_mapping(candidate_snapshot)
    except ValueError as exc:
        raise ValueError("canonical taxonomy content is invalid") from exc

    if raw_snapshot != canonical_mapping:
        raise ValueError("canonical taxonomy file does not match the canonical mapping")

    return candidate_snapshot


def taxonomy_snapshot_sha256(snapshot: CanonicalTaxonomySnapshot) -> str:
    """Hash canonical UTF-8 JSON, never raw HTTP response bytes."""
    # 对 dumps_canonical_taxonomy(snapshot).encode("utf-8") 计算 SHA-256 hex。
    canonical_json = dumps_canonical_taxonomy(snapshot)
    canonical_bytes = canonical_json.encode("utf-8")

    return hashlib.sha256(canonical_bytes).hexdigest()


def build_taxonomy_snapshot_manifest(
    snapshot: CanonicalTaxonomySnapshot,
    *,
    fetched_at_utc: str,
    source: str = ANILIST_SOURCE,
    resource: tuple[str, ...] = ANILIST_RESOURCES,
) -> TaxonomySnapshotManifest:
    """Build manifest metadata that is excluded from the content hash."""
    # - 验证 source/resource/fetched_at_utc；时间必须是带 Z 的 UTC ISO-8601 字符串；
    # - counts 从 snapshot 计算，hash 调 taxonomy_snapshot_sha256；
    # - snapshot_schema_version 从 snapshot 读取；不得由调用方覆盖 counts/hash/version。
    if not isinstance(source, str) or not source or source != source.strip():
        raise ValueError(
            "source must be a non-empty string without "
            "leading or trailing whitespace"
        )

    if not isinstance(resource, tuple) or not resource:
        raise ValueError("resource must be a non-empty tuple")

    seen_resources: set[str] = set()

    for index, resource_name in enumerate(resource):
        if (
            not isinstance(resource_name, str)
            or not resource_name
            or resource_name != resource_name.strip()
        ):
            raise ValueError(
                f"resource[{index}] must be a non-empty string "
                "without leading or trailing whitespace"
            )

        if resource_name in seen_resources:
            raise ValueError(f"duplicate resource name: {resource_name!r}")

        seen_resources.add(resource_name)
    if (
        not isinstance(fetched_at_utc, str)
        or not fetched_at_utc
        or fetched_at_utc != fetched_at_utc.strip()
        or not fetched_at_utc.endswith("Z")
        or "T" not in fetched_at_utc
    ):
        raise ValueError(
            "fetched_at_utc must be a UTC ISO-8601 string " "ending in 'Z'"
        )

    try:
        datetime.fromisoformat(fetched_at_utc[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(
            "fetched_at_utc must be a valid UTC ISO-8601 timestamp"
        ) from exc

    canonical_hash = taxonomy_snapshot_sha256(snapshot)

    return TaxonomySnapshotManifest(
        source=source,
        resource=resource,
        fetched_at_utc=fetched_at_utc,
        genre_count=len(snapshot.genres),
        tag_count=len(snapshot.tags),
        canonical_sha256=canonical_hash,
        snapshot_schema_version=snapshot.snapshot_schema_version,
    )


def write_taxonomy_snapshot_bundle(
    source_payload: Mapping[str, Any],
    *,
    output_dir: Path,
    fetched_at_utc: str,
) -> TaxonomySnapshotManifest:
    """Write source.json, canonical.json, and manifest.json without overwriting."""
    # - 构造 canonical snapshot 与 manifest 后再开始写文件；
    # - 创建 output_dir，但三个目标中任一已存在都先抛 FileExistsError；
    # - source.json 保留输入 payload；canonical.json 使用 canonical serializer；
    # - manifest.json 使用固定字段顺序、UTF-8 和末尾换行；
    # - 返回 manifest。不要把 fetched_at 写入 canonical content/hash。
    if not isinstance(output_dir, Path):
        raise ValueError("output_dir must be a pathlib.Path")

    snapshot = build_canonical_taxonomy_snapshot(source_payload)

    manifest = build_taxonomy_snapshot_manifest(
        snapshot,
        fetched_at_utc=fetched_at_utc,
    )

    try:
        source_json = (
            json.dumps(
                dict(source_payload),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "source_payload cannot be serialized as standard JSON"
        ) from exc

    canonical_json = dumps_canonical_taxonomy(snapshot)

    manifest_mapping = {
        "source": manifest.source,
        "resource": list(manifest.resource),
        "fetched_at_utc": manifest.fetched_at_utc,
        "genre_count": manifest.genre_count,
        "tag_count": manifest.tag_count,
        "canonical_sha256": manifest.canonical_sha256,
        "snapshot_schema_version": manifest.snapshot_schema_version,
    }

    manifest_json = (
        json.dumps(
            manifest_mapping,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    source_path = output_dir / "source.json"
    canonical_path = output_dir / "canonical.json"
    manifest_path = output_dir / "manifest.json"

    target_paths = (
        source_path,
        canonical_path,
        manifest_path,
    )

    existing_paths = [path for path in target_paths if path.exists()]

    if existing_paths:
        formatted_paths = ", ".join(str(path) for path in existing_paths)
        raise FileExistsError(
            "taxonomy snapshot bundle target already exists: " f"{formatted_paths}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    files_to_write = (
        (source_path, source_json),
        (canonical_path, canonical_json),
        (manifest_path, manifest_json),
    )

    for path, content in files_to_write:
        with path.open(
            mode="x",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(content)

    return manifest
