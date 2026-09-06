"""用标准库 unittest 执行；skip 表示尚未实现，不表示测试通过。"""
import importlib.util
import sys
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from anime_pref.data.anilist_client import fetch_anime_page
from anime_pref.data.io import write_jsonl, write_manifest
from anime_pref.schemas.anime_metadata import AnimeMetadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "fetch_anilist.py"
FETCH_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "fetch_anilist_script", FETCH_SCRIPT_PATH
)
if FETCH_SCRIPT_SPEC is None or FETCH_SCRIPT_SPEC.loader is None:
    raise RuntimeError(f"Cannot load script: {FETCH_SCRIPT_PATH}")
fetch_anilist_script = importlib.util.module_from_spec(FETCH_SCRIPT_SPEC)
FETCH_SCRIPT_SPEC.loader.exec_module(fetch_anilist_script)


class ScaffoldTests(unittest.TestCase):
    def test_invalid_page_rejected_before_network(self):
        with self.assertRaises(ValueError):
            fetch_anime_page(0, 10)

    def test_graphql_errors_with_http_200(self):
        # GraphQL 即使执行失败，服务器也可能返回 HTTP 200；因此不能只检查状态码。
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = json.dumps(
            {"errors": [{"message": "test GraphQL error"}]}
        ).encode("utf-8")

        # 模拟 urlopen 可让测试稳定、快速运行，并避免依赖网络和 AniList 状态。
        with patch(
            "anime_pref.data.anilist_client.request.urlopen",
            return_value=response,
        ):
            with self.assertRaisesRegex(RuntimeError, "GraphQL errors"):
                fetch_anime_page(1, 10)

    def test_nullable_metadata_and_invalid_tag_rank(self):
        media = {
            "id": 1,
            "title": {
                "romaji": "Test Anime",
                "english": None,
                "native": "测试动画",
            },
            "format": "TV",
            "status": "FINISHED",
            "episodes": None,
            "seasonYear": None,
            "genres": ["Drama"],
            "tags": [{"name": "Time Loop", "rank": 80}],
        }

        # API 中的未知数值应保留为 None，不能被转换成具有实际含义的 0。
        metadata = AnimeMetadata.from_api(media)
        self.assertIsNone(metadata.episodes)
        self.assertIsNone(metadata.season_year)
        self.assertEqual(metadata.tags[0].name, "Time Loop")
        self.assertEqual(metadata.tags[0].rank, 80)

        # rank 的合法范围是 0..100；越界记录必须显式失败，不能被静默丢弃。
        invalid_rank_media = {
            **media,
            "tags": [{"name": "Time Loop", "rank": 101}],
        }
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            AnimeMetadata.from_api(invalid_rank_media)

        # 统一报告为 ValueError。
        with self.assertRaisesRegex(ValueError, "media.*dict"):
            AnimeMetadata.from_api([])

    def test_jsonl_round_trip_and_no_overwrite(self):
        records = [
            {"id": 1, "title": "测试动画"},
            {"id": 2, "title": "Anime"},
        ]

        # 临时目录会在测试结束后清理，测试不会污染项目的 data 目录。
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            jsonl_path = root / "nested" / "records.jsonl"

            # 使用迭代器可确认函数统计的是实际写入量，而不是依赖 len(records)。
            count = write_jsonl(iter(records), jsonl_path)
            text = jsonl_path.read_text(encoding="utf-8")
            loaded_records = [json.loads(line) for line in text.splitlines()]

            self.assertEqual(count, 2)
            self.assertEqual(loaded_records, records)
            self.assertIn("测试动画", text)

            # x 模式必须拒绝覆盖已有缓存，防止重复运行破坏原始数据。
            with self.assertRaises(FileExistsError):
                write_jsonl(records, jsonl_path)

            empty_path = root / "empty.jsonl"
            self.assertEqual(write_jsonl([], empty_path), 0)
            self.assertEqual(empty_path.read_text(encoding="utf-8"), "")

            manifest = {"记录数": 2, "files": ["records.jsonl"]}
            manifest_path = root / "manifest" / "manifest.json"
            self.assertIsNone(write_manifest(manifest, manifest_path))
            manifest_text = manifest_path.read_text(encoding="utf-8")

            self.assertEqual(json.loads(manifest_text), manifest)
            self.assertIn("记录数", manifest_text)
            self.assertIn('\n  "files":', manifest_text)

            with self.assertRaises(FileExistsError):
                write_manifest(manifest, manifest_path)

    def test_fetch_script_end_to_end_without_network(self):
        first_media = {
            "id": 1,
            "title": {"romaji": "First", "english": None, "native": "第一部"},
            "format": "TV",
            "status": "FINISHED",
            "episodes": 12,
            "seasonYear": 2020,
            "genres": ["Drama"],
            "tags": [{"name": "Time Loop", "rank": 80}],
        }
        second_media = {
            "id": 2,
            "title": {"romaji": "Second", "english": None, "native": "第二部"},
            "format": "MOVIE",
            "status": "FINISHED",
            "episodes": 1,
            "seasonYear": 2021,
            "genres": ["Sci-Fi"],
            "tags": [],
        }
        responses = {
            1: {
                "media": [first_media],
                "pageInfo": {"currentPage": 1, "hasNextPage": True},
            },
            2: {
                "media": [second_media],
                "pageInfo": {"currentPage": 2, "hasNextPage": False},
            },
        }
        requested_pages = []

        def fake_fetch(page, per_page, *, endpoint, timeout_seconds):
            # 记录调用参数，同时返回可预测响应，使测试不依赖网络或 AniList 状态。
            requested_pages.append((page, per_page, endpoint, timeout_seconds))
            return responses[page]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "raw" / "anilist"
            arguments = [
                "fetch_anilist.py",
                "--pages",
                "5",
                "--per-page",
                "2",
                "--output",
                str(output_dir),
            ]

            with (
                patch.object(
                    fetch_anilist_script,
                    "fetch_anime_page",
                    side_effect=fake_fetch,
                ),
                patch.object(fetch_anilist_script.time, "sleep") as sleep_mock,
                patch.object(sys, "argv", arguments),
                # CLI 的成功提示不应污染测试输出，同时确认成功路径确实报告结果。
                patch("builtins.print") as print_mock,
            ):
                exit_code = fetch_anilist_script.main()

            self.assertEqual(exit_code, 0)
            print_mock.assert_called_once()
            self.assertEqual([call[0] for call in requested_pages], [1, 2])
            self.assertTrue(all(call[1] == 2 for call in requested_pages))
            sleep_mock.assert_called_once_with(1)

            # page JSONL 必须保留 API 原始字典，而不是写入 dataclass 的映射结果。
            first_page = [
                json.loads(line)
                for line in (output_dir / "page_0001.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            second_page = [
                json.loads(line)
                for line in (output_dir / "page_0002.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(first_page, [first_media])
            self.assertEqual(second_page, [second_media])

            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["requested_pages"], 5)
            self.assertEqual(manifest["actual_pages"], 2)
            self.assertEqual(manifest["per_page"], 2)
            self.assertEqual(manifest["total_records"], 2)
            self.assertEqual(manifest["schema_version"], "0.1")
            self.assertEqual(len(manifest["files"]), 2)
            self.assertTrue(manifest["fetch_time"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
