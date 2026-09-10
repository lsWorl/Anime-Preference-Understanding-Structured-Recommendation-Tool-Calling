"""Fetch and validate one AniList anime page without persistence or retries."""
from typing import Any
import json
from urllib import request,error

ANIME_PAGE_QUERY = """
query($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      currentPage
      hasNextPage
    }
    media(type: ANIME, sort: ID) {
      id
      title {
        romaji
        english
        native
      }
      format
      status
      episodes
      seasonYear
      genres
      tags {
        name
        rank
      }
    }
  }
}
"""


# 职责边界：此层负责请求协议和分页容器；每条 Media 的字段交给 AnimeMetadata.from_api。
# 返回的是 data.Page，因此脚本可以直接读取 media 与 pageInfo。
# HTTP 200 仍可能携带 GraphQL errors，必须先排除查询失败再接收数据。
# timeout 的完整有限数检查在作品采集 CLI；直接调用本函数时仅检查是否大于零。
def fetch_anime_page(
    page: int,
    per_page: int,
    *,
    endpoint: str = "https://graphql.anilist.co",
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """返回 response['data']['Page']，含 media 和 pageInfo。

    参数错误抛 ValueError；网络/HTTP/JSON/GraphQL/响应结构错误抛
    RuntimeError，并保留原始异常原因。
    """
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 50:
        raise ValueError("per_page must be an integer between 1 and 50")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    # 防御常量被测试或嵌入方意外替换为空；正常发布版本不会触发此分支。
    if not ANIME_PAGE_QUERY.strip():
        raise NotImplementedError("ANIME_PAGE_QUERY must not be empty")
    payload = {
        "query":ANIME_PAGE_QUERY,
        "variables":{
            "page": page,
            "perPage":per_page
        }
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    req = request.Request(
        endpoint,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req,timeout=timeout_seconds) as respponse:
            # 某些测试响应或替代 transport 会直接暴露 status 属性。
            if respponse.status != 200:
                raise RuntimeError(f"HTTP status {respponse.status}")
            try:
                response_data = json.loads(respponse.read().decode("utf-8"))
            except json.JSONDecodeError as e:
                raise RuntimeError("Failed to decode JSON response") from e
            # GraphQL 应用错误与 HTTP 传输状态独立，不能只看 status=200。
            if "errors" in response_data and response_data["errors"]:
                error_msg = response_data["errors"]
                raise RuntimeError(f"GraphQL errors: {error_msg}")
            # 这里只校验分页容器；单条 media 的字段由 AnimeMetadata 负责。
            if "data" not in response_data or not isinstance(response_data["data"], dict):
                raise RuntimeError("Missing or invalid 'data' field in response")
            if "Page" not in response_data["data"] or not isinstance(response_data["data"]["Page"], dict):
                raise RuntimeError("Missing or invalid 'Page' field in response")

            page_data = response_data['data']['Page']

            # media 可以是空列表，但容器本身必须存在且类型正确。
            if "media" not in page_data or not isinstance(page_data["media"], list):
                raise RuntimeError("Missing or invalid 'media' field in Page")

            # hasNextPage 驱动上层分页循环，因此拒绝 truthy 字符串或数字。
            if "pageInfo" not in page_data or not isinstance(page_data["pageInfo"], dict):
                raise RuntimeError("Missing or invalid 'pageInfo' field in Page")
            if "hasNextPage" not in page_data["pageInfo"]:
                raise RuntimeError("Missing 'hasNextPage' in pageInfo")
            if not isinstance(page_data["pageInfo"]["hasNextPage"], bool):
                raise RuntimeError("'hasNextPage' must be a boolean")

            return page_data
            
    # 保留原始异常作为 __cause__，同时向 CLI 提供统一的 RuntimeError 边界。
    except error.HTTPError as e:
        raise RuntimeError(f"HTTP error {e.code}: {e.reason}") from e
    except error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e
    except RuntimeError:
        # 已规范化的协议错误不再包一层，避免丢失具体错误消息。
        raise
    except Exception as e:
        # 兜底覆盖解码之外的响应对象/transport 异常。
        raise RuntimeError(f"Unexpected error: {e}") from e
