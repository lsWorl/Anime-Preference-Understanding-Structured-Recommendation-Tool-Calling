"""Deterministic identities for the S1 training experiment."""

from hashlib import sha256
import json
from typing import Any

from dataclasses import asdict
from pathlib import Path

from anime_pref.schemas.s1_training import S1TrainingConfig
from anime_pref.training.sft_environment import inspect_s1_environment
from anime_pref.training.sft_token_audit import audit_sft_token_lengths


def sha256_text(text: str) -> str:
    """Hash the exact UTF-8 text without stripping or changing newlines."""

    if not isinstance(text, str):
        raise ValueError("text must be a string")

    # text.encode("utf-8")
    # → sha256(...)
    # → hexdigest()
    #
    # 返回 64 字符的 SHA-256 十六进制字符串。
    # 不调用 strip()。
    return sha256(text.encode("utf-8")).hexdigest()


def sample_ids_sha256(
    records: list[dict[str, Any]],
) -> str:
    """Hash sample IDs in their original dataset order."""

    if not isinstance(records, list) or not records:
        raise ValueError("records must be a nonempty list")

    sample_ids: list[str] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"records[{index}] must be a dict")

        sample_id = record.get("sample_id")
        if (
            not isinstance(sample_id, str)
            or not sample_id
            or sample_id != sample_id.strip()
        ):
            raise ValueError(f"records[{index}].sample_id must be a canonical string")

        sample_ids.append(sample_id)

    # 相同训练文本可以保留，但完整 DatasetRecord ID 应唯一。
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("duplicate sample_id in dataset")

    # 使用 json.dumps 将 sample_ids 序列化成字符串 payload。
    # 参数：
    # ensure_ascii=False
    # separators=(",", ":")
    # allow_nan=False
    #
    # 保持 sample_ids 原顺序，不排序。
    #
    # 最后返回 sha256_text(payload)。
    payload = json.dumps(
        sample_ids, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return sha256_text(payload)


def build_s1_run_identity(
    config: S1TrainingConfig,
    project_root: Path,
    model: Any,
    tokenizer: Any,
    system_prompt: str,
    train_records: list[dict[str, Any]],
    validation_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Describe the actual S1 inputs and verify consistency with E0."""

    if not isinstance(config, S1TrainingConfig):
        raise ValueError("config must be S1TrainingConfig")

    if not isinstance(project_root, Path):
        raise ValueError("project_root must be a pathlib.Path")

    if not isinstance(train_records, list):
        raise ValueError("train_records must be a list")
    if not isinstance(validation_records, list):
        raise ValueError("validation_records must be a list")

    if len(train_records) != config.train_expected_count:
        raise ValueError("unexpected train record count")
    if len(validation_records) != config.validation_expected_count:
        raise ValueError("unexpected validation record count")

    # 样本声明的数据集版本必须与训练配置一致。
    for split, records in (
        ("train", train_records),
        ("validation", validation_records),
    ):
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError(f"{split}[{index}] must be a dict")
            if record.get("dataset_version") != config.dataset_version:
                raise ValueError(f"{split}[{index}] has inconsistent dataset_version")

    chat_template = getattr(tokenizer, "chat_template", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise ValueError("actual tokenizer chat template is missing")

    if (
        not isinstance(system_prompt, str)
        or not system_prompt
        or system_prompt != system_prompt.strip()
    ):
        raise ValueError("system_prompt must be a canonical nonempty string")

    # 调用 sha256_text，得到：
    # prompt_hash   <- system_prompt
    # template_hash <- chat_template
    prompt_hash = sha256_text(system_prompt)
    template_hash = sha256_text(chat_template)

    # 使用保存的 E0 实验身份作为 before/after 一致性基准。
    baseline_path = project_root / "artifacts/e0/run_identity.json"
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("failed to read frozen E0 identity") from exc

    if not isinstance(baseline, dict):
        raise ValueError("E0 identity must be a JSON object")

    expected_baseline = {
        "model_id": config.model_id,
        "tokenizer_id": config.tokenizer_id,
        "resolved_model_revision": config.revision,
        "prompt_version": config.prompt_version,
        "serialization_identity": config.serialization_identity,
        "system_prompt_sha256": prompt_hash,
        "chat_template_sha256": template_hash,
        "prompt_frozen": True,
    }

    for name, expected in expected_baseline.items():
        if baseline.get(name) != expected:
            raise ValueError(f"S1 does not match E0 identity: {name}")

    # load_s1_model 始终通过具体 snapshot 目录加载。
    # 验证实际模型记录的来源目录指向冻结 revision。
    model_source = getattr(model.config, "_name_or_path", "")
    if not isinstance(model_source, str) or Path(model_source).name != config.revision:
        raise ValueError("actual model source does not match frozen revision")

    # 使用 sample_ids_sha256，分别计算：
    # train_ids_hash
    # validation_ids_hash
    train_ids_hash = sample_ids_sha256(train_records)
    validation_ids_hash = sample_ids_sha256(validation_records)

    environment = inspect_s1_environment()

    if environment["missing_packages"]:
        raise ValueError("training dependencies are missing")
    if not environment["cuda_available"]:
        raise ValueError("CUDA is unavailable")
    if not environment["bf16_supported"]:
        raise ValueError("BF16 is unavailable")

    token_summary = audit_sft_token_lengths(
        train_records,
        validation_records,
        system_prompt,
        tokenizer,
    )

    if token_summary["overall_max"] > config.max_seq_length:
        raise ValueError("max_seq_length does not cover the actual sequences")

    # 返回字典，包含下面所有字段：
    #
    # "s1_version"                 : config.s1_version
    # "base_model_id"              : config.model_id
    # "resolved_model_revision"    : config.revision
    # "tokenizer_id"               : config.tokenizer_id
    # "dataset_version"            : config.dataset_version
    # "train_sample_ids_sha256"    : train_ids_hash
    # "validation_sample_ids_sha256": validation_ids_hash
    # "system_prompt_sha256"       : prompt_hash
    # "chat_template_sha256"       : template_hash
    # "training_config"            : asdict(config)
    # "environment"                : environment
    # "token_length_summary"       : token_summary

    return {
        "s1_version": config.s1_version,
        "base_model_id": config.model_id,
        "resolved_model_revision": config.revision,
        "tokenizer_id": config.tokenizer_id,
        "dataset_version": config.dataset_version,
        "train_sample_ids_sha256": train_ids_hash,
        "validation_sample_ids_sha256": validation_ids_hash,
        "system_prompt_sha256": prompt_hash,
        "chat_template_sha256": template_hash,
        "training_config": asdict(config),
        "environment": environment,
        "token_length_summary": token_summary,
    }
