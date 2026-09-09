"""描述一条作品记录。dataclass 本身不会执行运行时类型校验。"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnimeTag:
    name: str
    rank: int


@dataclass(frozen=True)
class AnimeMetadata:
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
    """从API的media中提取对应字段"""
    @classmethod
    # 把一条原始 Media 校验为 Python 视图；成功返回 cls 实例，字段不合法抛 ValueError。
    # API 的 seasonYear 转为 season_year；缺失/未知的可空字段保留 None，不替换为 0。
    # 这里只检查元数据类型与 rank 范围，不套用用户偏好的年份/集数或 taxonomy 白名单。
    # genres 沿用输入列表；frozen 只保护字段赋值，不递归冻结列表。
    def from_api(cls, media: dict[str, Any]) -> "AnimeMetadata":
        if not isinstance(media, dict):
            raise ValueError(
                f"'media' must be a dict, got {type(media).__name__}"
            )
        #提取ID
        anime_id = media.get('id')
        if anime_id is None:
            raise ValueError("Missing 'id' field")
        if not isinstance(anime_id, int) or isinstance(anime_id, bool):
            raise ValueError(f"'id' must be an integer, got {type(anime_id).__name__}")

        #title存在必须是dict类型，且内部字段可为 None 或 str
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

        #提取 format, status
        format_val = media.get('format')
        if format_val is not None and not isinstance(format_val, str):
            raise ValueError(f"'format' must be a string or None, got {type(format_val).__name__}")
        status_val = media.get('status')
        if status_val is not None and not isinstance(status_val, str):
            raise ValueError(f"'status' must be a string or None, got {type(status_val).__name__}")

        #提取 episodes（允许 None，若存在必须为 int，排除 bool）
        episodes_val = media.get('episodes')
        if episodes_val is not None:
            if not isinstance(episodes_val, int) or isinstance(episodes_val, bool):
                raise ValueError(f"'episodes' must be an integer or None, got {type(episodes_val).__name__}")

        #提取 seasonYear（允许 None，若存在必须为 int，排除 bool）
        season_year_val = media.get('seasonYear')
        if season_year_val is not None:
            if not isinstance(season_year_val, int) or isinstance(season_year_val, bool):
                raise ValueError(f"'seasonYear' must be an integer or None, got {type(season_year_val).__name__}")

        #提取 genres（必须存在且为字符串列表）
        genres_val = media.get('genres')
        if genres_val is None:
            raise ValueError("Missing 'genres' field")
        if not isinstance(genres_val, list):
            raise ValueError(f"'genres' must be a list, got {type(genres_val).__name__}")
        for g in genres_val:
            if not isinstance(g, str):
                raise ValueError(f"Each genre must be a string, got {type(g).__name__}")

        #提取 tags（必须存在且为列表，每个元素为包含 name 和 rank 的字典）
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
