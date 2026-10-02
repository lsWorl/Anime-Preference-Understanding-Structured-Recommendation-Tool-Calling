"""Read and type-check the pilot configuration."""

import json
from math import isfinite
from pathlib import Path
from typing import Any, get_type_hints

from anime_pref.schemas.s1_training import S1TrainingConfig


def _validate_config_types(raw: dict[str, Any]) -> None:
    """Validate source JSON values without coercing invalid types."""

    expected_types = get_type_hints(S1TrainingConfig)

    for name, expected_type in expected_types.items():
        value = raw[name]

        if expected_type is str:
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be a canonical nonempty string")

        elif expected_type is bool:
            if type(value) is not bool:
                raise ValueError(f"{name} must be bool")

        elif expected_type is int:
            # bool 是 int 的子类，因此这里使用精确类型判断。
            if type(value) is not int:
                raise ValueError(f"{name} must be int")

        elif expected_type is float:
            # JSON 的 0 和 0.0 都是合理数字，但 True 不是。
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")

            try:
                finite = isfinite(value)
            except OverflowError as exc:
                raise ValueError(
                    f"{name} must be a finite representable number"
                ) from exc

            if not finite:
                raise ValueError(f"{name} must be finite")

        elif expected_type == tuple[str, ...]:
            # 输入来自 JSON，此时必须还是 list。
            if not isinstance(value, list) or not value:
                raise ValueError(f"{name} must be a nonempty JSON list")

            for item in value:
                if not isinstance(item, str) or not item or item != item.strip():
                    raise ValueError(f"{name} items must be canonical nonempty strings")

            if len(value) != len(set(value)):
                raise ValueError(f"{name} must not contain duplicates")

        else:
            raise TypeError(f"unsupported configuration field type: {name}")


def _validate_config_ranges(config: S1TrainingConfig) -> None:
    """Check numerical ranges after source types have been validated."""

    positive_integer_fields = (
        "train_expected_count",
        "validation_expected_count",
        "max_seq_length",
        "lora_r",
        "lora_alpha",
        "num_train_epochs",
        "per_device_train_batch_size",
        "per_device_eval_batch_size",
        "gradient_accumulation_steps",
        "logging_steps",
        "save_total_limit",
    )

    # 遍历 positive_integer_fields。
    # 使用 getattr(config, name) 取得字段值。
    # 如果值小于 1，抛出包含字段名的 ValueError。
    for name in positive_integer_fields:
        value = getattr(config, name)
        if value < 1:
            raise ValueError(f"{name} must be at least 1")

    nonnegative_integer_fields = (
        "dataloader_num_workers",
        "seed",
        "data_seed",
    )

    # 这些字段允许 0，但不能为负数。
    for name in nonnegative_integer_fields:
        value = getattr(config, name)
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")
    positive_numeric_fields = (
        "learning_rate",
        "max_grad_norm",
    )
    # 这些字段必须严格大于 0。
    for name in positive_numeric_fields:
        value = getattr(config, name)
        if value <= 0:
            raise ValueError(f"{name} must be greater than 0")

    # dropout 必须属于 [0, 1)。
    if not 0 <= config.lora_dropout < 1:
        raise ValueError("lora_dropout must be in [0, 1)")

    # warmup_ratio 必须属于 [0, 1]。
    if not 0 <= config.warmup_ratio <= 1:
        raise ValueError("warmup_ratio must be in [0, 1]")

    if config.weight_decay < 0:
        raise ValueError("weight_decay must be nonnegative")


def _validate_frozen_contract(config: S1TrainingConfig) -> None:
    """Enforce the reviewed S1 model, dataset, and training contract."""

    frozen_values = {
        "s1_version": "s1-qlora-pilot-v0.1",
        "model_id": "Qwen/Qwen3-4B",
        "tokenizer_id": "Qwen/Qwen3-4B",
        "revision": "1cfa9a7208912126459214e8b04321603b3df60c",
        "dataset_version": "anime-pref-pilot-v0.1",
        "train_path": "data/pilot/train.v0.1.jsonl",
        "validation_path": "data/pilot/validation.v0.1.jsonl",
        "train_expected_count": 180,
        "validation_expected_count": 30,
        "prompt_version": "e0-json-extraction-v0.2",
        "prompt_path": "configs/e0_system_prompt.v0.2.txt",
        "serialization_identity": "qwen3-official-chat-template-nonthinking-v1",
        "enable_thinking": False,
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "bfloat16",
        "bf16": True,
        "fp16": False,
        "lora_bias": "none",
        "lora_task_type": "CAUSAL_LM",
        "eval_strategy": "epoch",
        "save_strategy": "epoch",
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
    }

    # 遍历 frozen_values.items()。
    # 使用 getattr(config, name) 读取实际值。
    # 如果实际值与 expected 不一致，抛出 ValueError。
    # 错误信息应包含字段名、expected 和 actual。
    for key, expected_value in frozen_values.items():
        actual_value = getattr(config, key)
        if actual_value != expected_value:
            raise ValueError(
                f"{key} expect {expected_value} but result is {actual_value}"
            )
    allowed_modules = {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    }
    required_modules = {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    }
    actual_modules = set(config.lora_target_modules)

    # 1. actual_modules 必须是 allowed_modules 的子集。
    #    禁止加入 embedding、lm_head 或其他未批准模块。
    #
    # 2. required_modules 必须是 actual_modules 的子集。
    #    attention 四个投影层必须全部覆盖。
    if not actual_modules.issubset(allowed_modules):
        raise ValueError('actual_modules must be allowed_modules subset')
    if not required_modules.issubset(actual_modules):
        missing = sorted(required_modules - actual_modules)
        raise ValueError(
            f"lora_target_modules missing required modules: {missing}"
        )
    
    if config.optimizer != "paged_adamw_8bit":
        raise ValueError("S1 pilot optimizer must be paged_adamw_8bit")

    if config.lr_scheduler_type != "linear":
        raise ValueError("S1 pilot scheduler must be linear")


def load_s1_config(path: Path) -> S1TrainingConfig:
    """Load the exact configuration fields and validate their types.

    Parameter ranges and frozen experiment bindings are validated separately.
    """

    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")

    # 使用 UTF-8 读取 path，并通过 json.loads 得到 raw。

    # 捕获 OSError、UnicodeError、json.JSONDecodeError；
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.loads(f.read())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法从 {path!r} 加载 JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("S1 configuration must be a JSON object")
    expected_keys = set(S1TrainingConfig.__dataclass_fields__)
    actual_keys = set(raw)

    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise ValueError(
            f"invalid S1 config keys: " f"missing={missing}, unexpected={unexpected}"
        )

    _validate_config_types(raw)
    # 创建 raw 的浅拷贝，命名为 values。
    # 将 values["lora_target_modules"] 转换成 tuple。
    # 不修改 raw，不排序、不去重。
    values = raw.copy()
    values["lora_target_modules"] = tuple(values["lora_target_modules"])

    # 用字典参数展开构造 S1TrainingConfig，并返回。
    config = S1TrainingConfig(**values)
    _validate_config_ranges(config)
    _validate_frozen_contract(config)
    return config
