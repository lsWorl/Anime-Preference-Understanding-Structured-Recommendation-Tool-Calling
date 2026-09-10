"""Fetch the AniList global genre and media-tag taxonomy."""

# 本模块只获取并验证 source response；排序、字段裁剪和持久化由
# taxonomy_snapshot 模块负责。保留完整响应可避免 canonical 规则丢失来源证据。

from typing import Any
import json
import math
from numbers import Real
from urllib import error, request

TAXONOMY_QUERY = """
query {
  GenreCollection
  MediaTagCollection {
    id
    name
    description
    category
    isGeneralSpoiler
    isAdult
  }
}
"""


def fetch_anilist_taxonomy(
    *,
    endpoint: str = "https://graphql.anilist.co",
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Return the raw GraphQL response for the approved taxonomy resources."""
    # - POST TAXONOMY_QUERY 与空 variables；UTF-8 JSON；
    # - 校验 timeout、HTTP、JSON、GraphQL errors 和 data object；
    # - 要求 GenreCollection/MediaTagCollection 是 list；
    # - 返回完整 decoded response，作为 raw/source snapshot；不得在此排序或删字段；
    # - 不加入重试、并发或缓存覆盖策略。

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, Real)
        or not math.isfinite(float(timeout_seconds))
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be a positive finite number")

    payload = {
        "query": TAXONOMY_QUERY,
        "variables": {},
    }

    request_body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    http_request = request.Request(
        endpoint,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "anime-preference-sft/0.1",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_status = getattr(response, "status", 200)
            if response_status != 200:
                raise RuntimeError(f"HTTP status {response_status}")

            response_bytes = response.read()
    except error.HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code}: {exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("AniList taxonomy request timed out") from exc

    try:
        response_text = response_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("AniList taxonomy response is not valid UTF-8") from exc

    try:
        decoded_response = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AniList taxonomy response is not valid JSON") from exc

    if not isinstance(decoded_response, dict):
        raise RuntimeError("AniList taxonomy response must be a JSON object")

    graphql_errors = decoded_response.get("errors")

    if graphql_errors:
        raise RuntimeError(f"GraphQL errors: {graphql_errors}")

    data = decoded_response.get("data")

    if not isinstance(data, dict):
        raise RuntimeError("AniList taxonomy response is missing a valid 'data' object")

    genre_collection = data.get("GenreCollection")
    if not isinstance(genre_collection, list):
        raise RuntimeError("'data.GenreCollection' must be a list")

    media_tag_collection = data.get("MediaTagCollection")
    if not isinstance(media_tag_collection, list):
        raise RuntimeError("'data.MediaTagCollection' must be a list")

    return decoded_response
