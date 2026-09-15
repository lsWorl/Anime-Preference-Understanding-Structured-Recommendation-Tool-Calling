"""Qwen3 SFT tokenization with completion-only loss masking."""

from typing import Any

from anime_pref.training.sft_data import build_sft_messages

IGNORE_INDEX = -100


def _validate_token_ids(token_ids: Any, name: str) -> None:
    """Validate one unpadded token ID sequence returned by the tokenizer."""
    if not isinstance(token_ids, list) or not token_ids:
        raise ValueError(f"{name} must be a nonempty list")

    for index, token_id in enumerate(token_ids):
        if isinstance(token_id, bool) or not isinstance(token_id, int) or token_id < 0:
            raise ValueError(f"{name}[{index}] must be a nonnegative integer")


def tokenize_sft_record(
    record: dict[str, Any],
    system_prompt: str,
    tokenizer: Any,
) -> dict[str, list[int]]:
    """Tokenize one record and mask everything before assistant Gold JSON."""

    apply_chat_template = getattr(
        tokenizer,
        "apply_chat_template",
        None,
    )

    if not callable(apply_chat_template):
        raise ValueError("tokenizer must provide callable apply_chat_template")

    # 必须存在实际模板，不能在训练阶段临时手工拼接 special tokens。
    chat_template = getattr(tokenizer, "chat_template", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise ValueError("tokenizer must provide a nonempty chat_template")

    messages = build_sft_messages(record, system_prompt)
    prompt_messages = messages[:2]

    # 使用 tokenizer.apply_chat_template 得到 prompt_input_ids。
    #
    # 输入只能包含 system 和 user。
    # 参数必须是：
    # tokenize=True
    # add_generation_prompt=True
    # enable_thinking=False

    prompt_input_ids = tokenizer.apply_chat_template(
        prompt_messages,
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    # 使用 tokenizer.apply_chat_template 得到 full_input_ids。
    #
    # 输入包含 system、user、assistant。
    # 参数必须是：
    # tokenize=True
    # add_generation_prompt=False
    # enable_thinking=False
    full_input_ids = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False, enable_thinking=False
    )

    _validate_token_ids(prompt_input_ids, "prompt_input_ids")
    _validate_token_ids(full_input_ids, "full_input_ids")

    # 完整序列必须比 prompt 多出 assistant target
    if len(full_input_ids) <= len(prompt_input_ids):
        raise ValueError("full sequence must contain assistant target tokens")

    # 两次官方模板调用必须在 assistant 内容之前完全对齐。
    # 如果不对齐，就不能按 prefix length 安全构造 labels。
    if full_input_ids[: len(prompt_input_ids)] != prompt_input_ids:
        raise ValueError("prompt token IDs are not an exact prefix of full token IDs")

    # labels 长度必须与 full_input_ids 相同。
    #
    # prompt_input_ids 对应的位置全部写入 IGNORE_INDEX。
    # 剩余 assistant completion 部分复制 full_input_ids 中的真实 token ID。

    labels = [IGNORE_INDEX] * len(full_input_ids)
    labels[len(prompt_input_ids):] = full_input_ids[len(prompt_input_ids):]

    # 当前阶段生成未填充的单样本序列，所以每个位置都可见。
    # attention_mask 与 full_input_ids 等长，每个值均为 1。
    attention_mask = [1] * len(full_input_ids)

    if not (len(full_input_ids) == len(labels) == len(attention_mask)):
        raise ValueError("input_ids, labels, and attention_mask must have equal length")

    prompt_length = len(prompt_input_ids)

    if any(label != IGNORE_INDEX for label in labels[:prompt_length]):
        raise ValueError("prompt labels must all use IGNORE_INDEX")

    # assistant completion 必须保留真实 token ID。
    if labels[prompt_length:] != full_input_ids[prompt_length:]:
        raise ValueError(
            "assistant labels must equal assistant token IDs"
        )

    if not labels[prompt_length:]:
        raise ValueError("assistant target cannot be empty")

    if any(value != 1 for value in attention_mask):
        raise ValueError(
            "unpadded attention_mask must contain only 1"
        )

    return {
        "input_ids": full_input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }
