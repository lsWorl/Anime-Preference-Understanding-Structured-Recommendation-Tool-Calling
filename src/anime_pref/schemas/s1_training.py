"""Immutable configuration for the QLoRA pilot."""
from dataclasses import dataclass

@dataclass(frozen=True)
class S1TrainingConfig:
    s1_version: str
    model_id: str
    tokenizer_id: str
    revision: str
    local_files_only: bool

    dataset_version: str
    train_path: str
    validation_path: str
    train_expected_count: int
    validation_expected_count: int

    prompt_version: str
    prompt_path: str
    serialization_identity: str
    enable_thinking: bool
    max_seq_length: int

    load_in_4bit: bool
    bnb_4bit_quant_type: str
    bnb_4bit_use_double_quant: bool
    bnb_4bit_compute_dtype: str

    # JSON 中的 list 在加载时转换成 tuple，
    # 避免 frozen dataclass 内仍存在可变的列表。
    lora_target_modules: tuple[str, ...]
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    lora_bias: str
    lora_task_type: str

    optimizer: str
    learning_rate: float
    lr_scheduler_type: str
    warmup_ratio: float
    weight_decay: float
    max_grad_norm: float
    num_train_epochs: int

    per_device_train_batch_size: int
    per_device_eval_batch_size: int
    gradient_accumulation_steps: int
    gradient_checkpointing: bool

    bf16: bool
    fp16: bool
    tf32: bool
    logging_steps: int
    eval_strategy: str
    save_strategy: str
    save_total_limit: int
    load_best_model_at_end: bool
    metric_for_best_model: str
    greater_is_better: bool
    dataloader_num_workers: int
    report_to: str

    seed: int
    data_seed: int

    trainer_output_dir: str
    adapter_output_dir: str
    run_identity_path: str