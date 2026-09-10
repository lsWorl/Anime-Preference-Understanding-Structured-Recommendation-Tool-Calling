"""描述一条作品记录。dataclass 本身不会执行运行时类型校验。"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnimeTag:
    """A media-specific AniList tag and its 0-100 relevance rank."""

    name: str
    rank: int


@dataclass(frozen=True)
class AnimeMetadata:
    """Validated view of the AniList fields retained by the media collector.

    This object is not the raw cache format. The collector validates through
    this view and persists the original ``Media`` mapping unchanged.
    """

    id: int
    title_romaji: str | None
    title_english: str | None
    title_native: str | None
    format: str | None
    status: str | None
    episodes: int | None
    season_year: int | None
    genres: list[str]
    tags: list[AnimeTag]

    @classmethod
    # 把一条原始 Media 校验为 Python 视图；成功返回 cls 实例，字段不合法抛 ValueError。
    # API 的 seasonYear 转为 season_year；缺失/未知的可空字段保留 None，不替换为 0。
    # 这里只检查元数据类型与 rank 范围，不套用用户偏好的年份/集数或 taxonomy 白名单。
    # genres 沿用输入列表；frozen 只保护字段赋值，不递归冻结列表。
    def from_api(cls, media: dict[str, Any]) -> "AnimeMetadata":
        """Validate one raw AniList ``Media`` mapping and return a typed view."""
        if not isinstance(media, dict):
            raise ValueError(
                f"'media' must be a dict, got {type(media).__name__}"
            )
        # bool 是 int 的子类，但 API ID 契约不接受 True/False。
        anime_id = media.get('id')
        if anime_id is None:
            raise ValueError("Missing 'id' field")
        if not isinstance(anime_id, int) or isinstance(anime_id, bool):
            raise ValueError(f"'id' must be an integer, got {type(anime_id).__name__}")

        # title 整体可以缺失；存在时三个已知标题字段只接受 str 或 None。
        title_data = media.get('title')
        if title_data is not None and not isinstance(title_data, dict):
            raise ValueError("'title' must be a dict or None")
        title_romaji = title_english = title_native = None
        if isinstance(title_data,dict):
            for key in ('romaji', 'english', 'native'):
                val = title_data.get(key)
                if val is not None and not isinstance(val, str):
                    raise ValueError(f"title.{key} must be a string or None, got {type(val).__name__}")
                title_romaji = title_data.get('romaji')
                title_english = title_data.get('english')
                title_native = title_data.get('native')

        # AniList enum 在 JSON 中表现为字符串；未知值仍由上游原样保留。
        format_val = media.get('format')
        if format_val is not None and not isinstance(format_val, str):
            raise ValueError(f"'format' must be a string or None, got {type(format_val).__name__}")
        status_val = media.get('status')
        if status_val is not None and not isinstance(status_val, str):
            raise ValueError(f"'status' must be a string or None, got {type(status_val).__name__}")

        # episodes 允许 None；这里只验类型，不在元数据层套用偏好规则的最小集数。
        episodes_val = media.get('episodes')
        if episodes_val is not None:
            if not isinstance(episodes_val, int) or isinstance(episodes_val, bool):
                raise ValueError(f"'episodes' must be an integer or None, got {type(episodes_val).__name__}")

        # seasonYear 是 API 字段名，返回对象使用 Python 风格的 season_year。
        season_year_val = media.get('seasonYear')
        if season_year_val is not None:
            if not isinstance(season_year_val, int) or isinstance(season_year_val, bool):
                raise ValueError(f"'seasonYear' must be an integer or None, got {type(season_year_val).__name__}")

        # genres/tags 是查询明确请求的容器，因此缺失与 null 都视为响应结构错误。
        genres_val = media.get('genres')
        if genres_val is None:
            raise ValueError("Missing 'genres' field")
        if not isinstance(genres_val, list):
            raise ValueError(f"'genres' must be a list, got {type(genres_val).__name__}")
        for g in genres_val:
            if not isinstance(g, str):
                raise ValueError(f"Each genre must be a string, got {type(g).__name__}")

        # rank 属于具体作品与 tag 的关联；全局 taxonomy 快照不会保存它。
        tags_val = media.get('tags')
        if tags_val is None:
            raise ValueError("Missing 'tags' field")
        if not isinstance(tags_val, list):
            raise ValueError(f"'tags' must be a list, got {type(tags_val).__name__}")
        tags_list = []
        for idx, tag_item in enumerate(tags_val):
            if not isinstance(tag_item, dict):
                raise ValueError(f"Tag at index {idx} must be a dict")
            name = tag_item.get('name')
            rank = tag_item.get('rank')
            if name is None:
                raise ValueError(f"Tag at index {idx} missing 'name'")
            if rank is None:
                raise ValueError(f"Tag at index {idx} missing 'rank'")
            if not isinstance(name, str):
                raise ValueError(f"Tag at index {idx} 'name' must be a string, got {type(name).__name__}")
            if not isinstance(rank, int) or isinstance(rank, bool):
                raise ValueError(f"Tag at index {idx} 'rank' must be an integer, got {type(rank).__name__}")
            if not (0 <= rank <= 100):
                raise ValueError(f"Tag at index {idx} 'rank' must be between 0 and 100, got {rank}")
            tags_list.append(AnimeTag(name=name, rank=rank))
        return cls(
            id=anime_id,
            title_romaji=title_romaji,
            title_english=title_english,
            title_native=title_native,
            format=format_val,
            status=status_val,
            episodes=episodes_val,
            season_year=season_year_val,
            genres=genres_val,
            tags=tags_list,
        )
