"""Load the frozen Qwen3 checkpoint and attach trainable LoRA adapters."""

from typing import Any

from anime_pref.schemas.s1_training import S1TrainingConfig


def load_s1_model(
    config: S1TrainingConfig,
) -> tuple[Any, Any]:
    """Return (model, tokenizer) prepared for the S1 QLoRA pilot."""

    # 重型依赖放在函数内部，避免普通离线测试初始化 CUDA。
    import torch
    import bitsandbytes as bnb
    from huggingface_hub import snapshot_download
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        set_seed,
    )
    from peft import (
        LoraConfig,
        get_peft_model,
        prepare_model_for_kbit_training,
    )

    if not isinstance(config, S1TrainingConfig):
        raise ValueError("config must be S1TrainingConfig")

    if not torch.cuda.is_available():
        raise RuntimeError("S1 requires CUDA")

    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("S1 requires BF16 support")

    # 必须在模型加载和 LoRA 随机初始化之前固定 seed。
    set_seed(config.seed)

    # 解析具体 revision；本地缓存缺失时直接报错。
    model_source = snapshot_download(
        repo_id=config.model_id,
        revision=config.revision,
        local_files_only=config.local_files_only,
    )
    tokenizer_source = snapshot_download(
        repo_id=config.tokenizer_id,
        revision=config.revision,
        local_files_only=config.local_files_only,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_source,
        local_files_only=config.local_files_only,
    )

    if not isinstance(tokenizer.chat_template, str):
        raise RuntimeError("official chat template is missing")
    if not tokenizer.chat_template:
        raise RuntimeError("official chat template is empty")

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    if tokenizer.pad_token_id is None:
        raise RuntimeError("tokenizer has no usable padding token")

    # 训练采用右填充。后续独立推理入口仍使用 E0 的左填充。
    tokenizer.padding_side = "right"


    # 创建 quantization_config = BitsAndBytesConfig(...)
    #
    # 参数对应关系：
    # load_in_4bit             <- config.load_in_4bit
    # bnb_4bit_quant_type       <- config.bnb_4bit_quant_type
    # bnb_4bit_use_double_quant <- config.bnb_4bit_use_double_quant
    # bnb_4bit_compute_dtype    <- torch.bfloat16
    #
    # 最后一项需要 torch dtype 对象，不能传字符串。
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=config.load_in_4bit,
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
        bnb_4bit_use_double_quant=config.bnb_4bit_use_double_quant,
        bnb_4bit_compute_dtype=torch.bfloat16
        )


    # 使用 AutoModelForCausalLM.from_pretrained(...) 加载 model。
    #
    # 第一个参数：model_source
    # quantization_config=quantization_config
    # dtype=torch.bfloat16
    # device_map={"": 0}
    # local_files_only=config.local_files_only
    #
    # device_map 明确将整个模型放到 GPU 0。
    # 此处不调用 model.to("cuda")。
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        quantization_config=quantization_config,
        dtype=torch.bfloat16,
        device_map={"": 0},
        local_files_only=config.local_files_only
        )

    if not getattr(model, "is_loaded_in_4bit", False):
        raise RuntimeError("model was not loaded in 4-bit mode")

    # 验证配置中的每类目标投影实际使用了量化线性层。
    quantized_targets = set()

    for name, module in model.named_modules():
        leaf_name = name.rsplit(".", 1)[-1]
        if (
            leaf_name in config.lora_target_modules
            and isinstance(module, bnb.nn.Linear4bit)
        ):
            quantized_targets.add(leaf_name)

    missing = set(config.lora_target_modules) - quantized_targets
    if missing:
        raise RuntimeError(
            f"target modules were not quantized: {sorted(missing)}"
        )

    # checkpointing 训练期间禁用 KV cache。
    model.config.use_cache = False


    # 调用 prepare_model_for_kbit_training(...)，
    # 并把返回对象重新保存到 model。
    #
    # 参数：
    # model
    # use_gradient_checkpointing=config.gradient_checkpointing
    # gradient_checkpointing_kwargs={"use_reentrant": False}
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=config.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False}
        )

    # 挂载 LoRA 前，base 参数必须全部冻结。
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise RuntimeError("base parameters were not fully frozen")


    # 构造 lora_config = LoraConfig(...)。
    #
    # 参数：
    # r=config.lora_r
    # lora_alpha=config.lora_alpha
    # lora_dropout=config.lora_dropout
    # target_modules=list(config.lora_target_modules)
    # bias=config.lora_bias
    # task_type=config.lora_task_type
    #
    # 然后调用 get_peft_model(model, lora_config)，
    # 将返回对象重新保存到 model。
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=list(config.lora_target_modules),
        bias=config.lora_bias,
        task_type=config.lora_task_type
        )
    model = get_peft_model(model, lora_config)
    trainable_names = [
        name
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    ]

    if not trainable_names:
        raise RuntimeError("no trainable LoRA parameters found")

    # 当前只允许 LoRA A/B 矩阵参与训练。
    unexpected = [
        name
        for name in trainable_names
        if ".lora_A." not in name and ".lora_B." not in name
    ]
    if unexpected:
        raise RuntimeError(
            f"unexpected trainable parameters: {unexpected[:10]}"
        )

    model.train()
    return model, tokenizer