"""Translate the S1 configuration into Transformers training arguments."""

from pathlib import Path
from typing import Any

from anime_pref.schemas.s1_training import S1TrainingConfig


def build_s1_training_arguments(
    config: S1TrainingConfig,
    project_root: Path,
) -> Any:
    """Build training arguments without constructing or running a Trainer."""

    from transformers import TrainingArguments

    if not isinstance(config, S1TrainingConfig):
        raise ValueError("config must be S1TrainingConfig")

    if not isinstance(project_root, Path):
        raise ValueError("project_root must be a pathlib.Path")

    if not project_root.is_dir():
        raise ValueError("project_root must be an existing directory")

    # 这些字段在项目配置与 TrainingArguments 中同名。
    direct_fields = (
        "learning_rate",
        "lr_scheduler_type",
        "warmup_ratio",
        "weight_decay",
        "max_grad_norm",
        "num_train_epochs",
        "per_device_train_batch_size",
        "per_device_eval_batch_size",
        "gradient_accumulation_steps",
        "gradient_checkpointing",
        "bf16",
        "fp16",
        "tf32",
        "logging_steps",
        "eval_strategy",
        "save_strategy",
        "save_total_limit",
        "load_best_model_at_end",
        "metric_for_best_model",
        "greater_is_better",
        "dataloader_num_workers",
        "report_to",
        "seed",
        "data_seed",
    )

    # 创建 kwargs 字典。
    # 遍历 direct_fields，用 getattr(config, name) 获取配置值。
    # 字典 key 是字段名，value 是配置值。
    kwargs = {name: getattr(config, name) for name in direct_fields}

    # 字段名不同的参数单独映射。
    kwargs["optim"] = config.optimizer
    kwargs["output_dir"] = str(project_root / config.trainer_output_dir)

    # 保持与模型准备阶段相同的 checkpointing 方式。
    kwargs["gradient_checkpointing_kwargs"] = {
        "use_reentrant": False,
    }

    # validation 阶段只收集 loss，避免保留巨大词表的 logits。
    kwargs["prediction_loss_only"] = True

    # 保留我们自行构造的 labels，交给模型计算 completion-only loss。
    kwargs["label_names"] = ["labels"]
    kwargs["remove_unused_columns"] = False

    # 使用 TrainingArguments(**kwargs) 构造并返回对象。
    return TrainingArguments(**kwargs)


def build_s1_trainer(
    config: S1TrainingConfig,
    project_root: Path,
    model: Any,
    tokenizer: Any,
    train_features: list[dict[str, list[int]]],
    validation_features: list[dict[str, list[int]]],
) -> Any:
    """Assemble the S1 Trainer without starting training."""

    from transformers import Trainer

    from anime_pref.training.sft_collator import SFTDataCollator

    if not isinstance(config, S1TrainingConfig):
        raise ValueError("config must be S1TrainingConfig")

    if not isinstance(train_features, list):
        raise ValueError("train_features must be a list")

    if not isinstance(validation_features, list):
        raise ValueError("validation_features must be a list")

    if len(train_features) != config.train_expected_count:
        raise ValueError("unexpected train feature count")

    if len(validation_features) != config.validation_expected_count:
        raise ValueError("unexpected validation feature count")

    if not getattr(model, "is_loaded_in_4bit", False):
        raise ValueError("Trainer requires the prepared 4-bit model")

    if not any(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("model has no trainable parameters")

    pad_token_id = getattr(tokenizer, "pad_token_id", None)

    if getattr(tokenizer, "padding_side", None) != "right":
        raise ValueError("S1 training tokenizer must use right padding")


    # 调用 build_s1_training_arguments(config, project_root)，
    # 将结果保存为 training_args。
    training_args = build_s1_training_arguments(config,project_root)


    # 创建 SFTDataCollator。
    # pad_token_id 使用上面提取的值。
    # max_seq_length 使用 config.max_seq_length。
    # 将对象保存为 collator。

    collator = SFTDataCollator(pad_token_id,config.max_seq_length)


    # 构造并返回 Trainer，参数对应关系：
    #
    # model            = model
    # args             = training_args
    # train_dataset    = train_features
    # eval_dataset     = validation_features
    # data_collator    = collator
    # processing_class = tokenizer
    #
    # 不调用 train()、evaluate() 或 save_model()。
    return Trainer(
        model=model,
        args=training_args,
        train_dataset=train_features,
        eval_dataset=validation_features,
        data_collator=collator,
        processing_class=tokenizer
    )
