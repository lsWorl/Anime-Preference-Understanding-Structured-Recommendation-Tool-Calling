"""Fetch validated AniList media pages into an append-only raw-data bundle."""

import argparse
import json
from pathlib import Path
import sys
import time
from datetime import datetime,timezone
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.data.anilist_client import fetch_anime_page
from anime_pref.data.io import write_jsonl, write_manifest
from anime_pref.schemas.anime_metadata import AnimeMetadata


# argparse 的类型转换入口：把命令行字符串转成正整数。
# per_page <= 50 等跨来源规则仍在 main 中统一校验，JSON 配置也须经过这些规则。
def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


# 编排顺序：读取配置 → CLI 覆盖 → 参数校验 → 分页请求 → 逐条验证 → raw 写盘 → 摘要。
# dry-run 在任何网络/缓存操作之前返回；输出相对路径基于 PROJECT_ROOT。
# 成功返回 0，已捕获运行错误返回 1，查询常量缺失返回 2；argparse 自行处理解析退出。
# 校验视图不替代原始 Media；若后续页面失败，已成功写入的页面不会被撤销。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/data.json")
    parser.add_argument("--pages", type=positive_int)
    parser.add_argument("--per-page", type=positive_int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="只检查配置，不联网、不写文件")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config must be a JSON object")
        for key in ("pages", "per_page", "output"):
            value = getattr(args, key)
            if value is not None:
                config[key] = str(value) if isinstance(value, Path) else value
        for key, upper in (("pages", None), ("per_page", 50)):
            value = config[key]
            if type(value) is not int or value < 1 or (upper and value > upper):
                raise ValueError(f"invalid {key}: {value}")
        timeout = config["timeout_seconds"]
        if type(timeout) not in (int, float) or not 0 < timeout < float("inf"):
            raise ValueError("timeout_seconds must be finite and positive")
        if not isinstance(config["endpoint"], str) or not config["endpoint"].startswith("https://"):
            raise ValueError("endpoint must be an HTTPS URL")
        output = Path(config["output"])
        config["output"] = str(output if output.is_absolute() else PROJECT_ROOT / output)
        if args.dry_run:
            print(json.dumps(config, ensure_ascii=False, indent=2))
            print("Configuration OK. No network requests or files written.")
            return 0
        # 分页数据流：
        # 1. 从 page=1 开始，最多抓取 config['pages'] 页。
        # 2. 调用 fetch_anime_page；逐条用 AnimeMetadata.from_api 校验。
        # 3. 将原始 media 字典写入 page_0001.jsonl 等文件。
        # 4. hasNextPage=False 时停止；请求间使用适当间隔，不做并发。
        # 5. 全部成功后写 manifest.json：UTC 抓取时间、endpoint、请求页数、
        #    实际页数、per_page、实际记录数、文件列表、schema_version='0.1'。
        # 任意步骤失败时不要生成表示成功的 manifest；已有输出不应被覆盖。
        max_pages = config['pages']
        per_page = config['per_page']
        endpoint = config['endpoint']
        timeout = config['timeout_seconds']
        output_dir = Path(config['output'])

        page = 1
        total_pages_fetched = 0
        total_records = 0
        file_list = []

        while True:
            # 即使 API 仍有下一页，也以调用方配置的最大页数为硬停止条件。
            if max_pages is not None and page > max_pages:
                break

            # 先完成整页获取与字段校验，再创建该页文件，避免保存已知无效页面。
            page_data = fetch_anime_page(page,per_page,endpoint=endpoint,timeout_seconds=timeout)
            media_list = page_data.get('media',[])
            page_info = page_data.get('pageInfo', {})
            has_next = page_info.get('hasNextPage', False)
            # 校验对象不替换 media_list；raw 缓存继续保存 API 原始字段。
            for media in media_list:
                AnimeMetadata.from_api(media=media)

            # 文件使用独占创建；重复运行必须选择新目录，不能覆盖来源证据。
            filename = f"page_{page:04d}.jsonl"
            file_path = output_dir / filename
            count = write_jsonl(media_list,file_path)
            total_records += count
            total_pages_fetched += 1
            file_list.append(str(file_path))

            # API 明确到达末页时，无需把 configured pages 全部请求完。
            if not has_next:
                break

            # 串行请求间留出固定间隔；当前没有指数退避或断点续传。
            time.sleep(1)
            page += 1
        # 只有整个循环成功后才写 manifest；已写页面在后续失败时不会自动回滚。
        manifest = {
            "fetch_time": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "requested_pages": max_pages,
            "actual_pages": total_pages_fetched,
            "per_page": per_page,
            "total_records": total_records,
            "files": file_list,
            "schema_version": "0.1"
        }
        manifest_path = output_dir / "manifest.json"
        write_manifest(manifest, manifest_path)

        print(f"Successfully fetched {total_pages_fetched} pages, {total_records} records to {output_dir}")

        return 0

            
    except NotImplementedError as exc:
        print(f"Configuration invariant failed: {exc}.", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
