from pathlib import Path
from typing import Any
import json

from anime_pref.data.query_validation import validate_query_structure
from anime_pref.data.query_builder import dumps_query


def load_sft_records(project_root: Path, split: str) -> list[dict[str, Any]]:
    if split not in {"train", "validation"}:
        raise ValueError("split must be train or validation!")

    path = project_root / "data" / "pilot" / f"{split}.v0.1.jsonl"
    records: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    if not text:
        raise ValueError("JSONL file must contain at least one record")

    for line_number, line in enumerate(text.splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f" {line_number} is not a valid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f" {line_number} must be a valid JSON object")

        sample_id = record.get("sample_id")
        if not isinstance(sample_id, str):
            raise ValueError(
                f"sample_id must be a string, line_number is {line_number}"
            )
        if len(sample_id) <= 0 or sample_id != sample_id.strip():
            raise ValueError(
                f"sample_id must be not empty and not has whitespace, line_number is {line_number}"
            )

        gold_query = record.get("gold_query")

        if not isinstance(gold_query, dict):
            raise ValueError(f"gold_query must be a dict,line_number is {line_number}")
        try:
            validate_query_structure(gold_query)
        except ValueError as err:
            raise ValueError(
                f"gold_query has invalid structure at line {line_number}"
            ) from err

        user_text = record.get("user_text")

        if not isinstance(user_text, str) or not user_text:
            raise ValueError(f" {line_number} need effective user_text")

        if user_text != user_text.strip():
            raise ValueError(f" {line_number}  user_text has head or tail whitespace")

        records.append(record)

    expected_count = {
        "train": 180,
        "validation": 30,
    }[split]

    if len(records) != expected_count:
        raise ValueError(
            f"records length must same with expected_count,actual={len(records)},expected={expected_count}"
        )

    return records


def build_sft_messages(
    record: dict[str, Any],
    system_prompt: str,
) -> list[dict[str, str]]:
    """Build one system-user-assistant SFT conversation.

    The assistant target contains only the canonical Gold Query JSON.
    DatasetRecord provenance must not enter any message.
    """

    # record 必须是普通字典。
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")

    # system prompt 必须是非空、无首尾空白的字符串。
    if not isinstance(system_prompt, str) or not system_prompt:
        raise ValueError("system_prompt must be a nonempty string")
    if system_prompt != system_prompt.strip():
        raise ValueError("system_prompt must not contain outer whitespace")

    # user_text 必须存在，而且不能静默 strip。
    user_text = record.get("user_text")
    if not isinstance(user_text, str) or not user_text:
        raise ValueError("record.user_text must be a nonempty string")
    if user_text != user_text.strip():
        raise ValueError("record.user_text must not contain outer whitespace")

    # assistant 只能使用 gold_query。
    gold_query = record.get("gold_query")
    if not isinstance(gold_query, dict):
        raise ValueError("record.gold_query must be a dict")

    # 复用统一结构验证，避免无效 Gold 进入训练目标。
    validate_query_structure(gold_query)

    # 复用已有 canonical serializer。
    assistant_content = dumps_query(gold_query)

    # 构造并返回三条消息
    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_text,
        },
        {
            "role": "assistant",
            "content": assistant_content,
        },
    ]
