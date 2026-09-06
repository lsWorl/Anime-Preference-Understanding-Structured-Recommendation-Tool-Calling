"""AniList 单页获取；暂不加入重试、并发、训练等额外复杂度。"""
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
    if not ANIME_PAGE_QUERY.strip():
        raise NotImplementedError("TODO-01: add the GraphQL query")
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
            # 检查 HTTP 状态
            if respponse.status != 200:
                raise RuntimeError(f"HTTP status {respponse.status}")
            try:
                response_data = json.loads(respponse.read().decode("utf-8"))
            except json.JSONDecodeError as e:
                raise RuntimeError("Failed to decode JSON response") from e
            if "errors" in response_data and response_data["errors"]:
                error_msg = response_data["errors"]
                raise RuntimeError(f"GraphQL errors: {error_msg}")
            # 检查 data 和 Page 字段
            if "data" not in response_data or not isinstance(response_data["data"], dict):
                raise RuntimeError("Missing or invalid 'data' field in response")
            if "Page" not in response_data["data"] or not isinstance(response_data["data"]["Page"], dict):
                raise RuntimeError("Missing or invalid 'Page' field in response")

            page_data = response_data['data']['Page']

            # 验证 media 是列表
            if "media" not in page_data or not isinstance(page_data["media"], list):
                raise RuntimeError("Missing or invalid 'media' field in Page")

            # 验证 pageInfo 存在且 hasNextPage 是 bool
            if "pageInfo" not in page_data or not isinstance(page_data["pageInfo"], dict):
                raise RuntimeError("Missing or invalid 'pageInfo' field in Page")
            if "hasNextPage" not in page_data["pageInfo"]:
                raise RuntimeError("Missing 'hasNextPage' in pageInfo")
            if not isinstance(page_data["pageInfo"]["hasNextPage"], bool):
                raise RuntimeError("'hasNextPage' must be a boolean")

            return page_data
            
    #若异常则抛出异常
    except error.HTTPError as e:
        raise RuntimeError(f"HTTP error {e.code}: {e.reason}") from e
    except error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e
    except RuntimeError:
        # 直接向上传递已处理的 RuntimeError
        raise
    except Exception as e:
        # 捕获其他未预期的异常
        raise RuntimeError(f"Unexpected error: {e}") from e

# if __name__ == "__main__":
#     fetch_anime_page(1,1)