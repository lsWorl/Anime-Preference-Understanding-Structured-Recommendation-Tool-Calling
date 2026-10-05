"""Check one real SFT forward/backward pass without updating parameters."""

from pathlib import Path
import sys

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.evaluation.e0_baseline import (
    load_e0_config,
    load_system_prompt,
)
from anime_pref.training.sft_collator import SFTDataCollator
from anime_pref.training.sft_config import load_s1_config
from anime_pref.training.sft_data import load_sft_records
from anime_pref.training.sft_model import load_s1_model
from anime_pref.training.sft_tokenization import (
    IGNORE_INDEX,
    tokenize_sft_record,
)


def main() -> None:
    config = load_s1_config(
        PROJECT_ROOT / "configs" / "s1_qlora_pilot.v0.1.json"
    )
    e0_config = load_e0_config(
        PROJECT_ROOT / "configs" / "e0_baseline.v0.1.json",
        PROJECT_ROOT,
    )
    system_prompt = load_system_prompt(e0_config, PROJECT_ROOT)

    # 仅使用第一条 train 数据做工程检查。
    record = load_sft_records(PROJECT_ROOT, "train")[0]
    model, tokenizer = load_s1_model(config)

    feature = tokenize_sft_record(
        record,
        system_prompt,
        tokenizer,
    )
    collator = SFTDataCollator(
        pad_token_id=tokenizer.pad_token_id,
        max_seq_length=config.max_seq_length,
    )
    batch = collator([feature])


    # 将 batch 中的每个 tensor 移到 cuda，
    # 保留 input_ids、attention_mask、labels 三个键。
    batch = {
        name : tensor.to('cuda')
        for name,tensor in batch.items()
    }

    print("sample_id:", record["sample_id"])
    for name, tensor in batch.items():
        print(name, tuple(tensor.shape), tensor.dtype, tensor.device)

    supervised_positions = (
        batch["labels"][0] != IGNORE_INDEX
    ).nonzero(as_tuple=True)[0]

    if supervised_positions.numel() == 0:
        raise RuntimeError("no supervised tokens")

    target_start = supervised_positions[0].item()

    if not (
        batch["labels"][0, :target_start] == IGNORE_INDEX
    ).all().item():
        raise RuntimeError("prompt labels are not fully masked")

    print("masked prompt tokens:", target_start)
    print("supervised tokens:", supervised_positions.numel())
    print(
        "target beginning:",
        repr(
            tokenizer.decode(
                batch["input_ids"][0, target_start:target_start + 12]
                .detach()
                .cpu()
                .tolist()
            )
        ),
    )

    model.train()
    model.zero_grad(set_to_none=True)
    torch.cuda.reset_peak_memory_stats()

    # 第二处由你实现：
    #
    # 在下面的 BF16 autocast 上下文内：
    # 1. 调用 model(**batch)，保存为 outputs。
    # 2. 从 outputs.loss 提取 loss。
    #
    # 模型内部负责 causal shift，不手动移动 labels。
    with torch.autocast(
        device_type="cuda",
        dtype=torch.bfloat16,
    ):
        outputs = model(**batch)
        loss = outputs.loss

    if loss.ndim != 0 or not torch.isfinite(loss).item():
        raise RuntimeError("loss must be a finite scalar")

    # 第三处由你实现：
    # 对 loss 调用 backward()。
    loss.backward()

    trainable_with_grad = 0
    nonzero_gradient_tensors = 0

    for name, parameter in model.named_parameters():
        gradient = parameter.grad

        if not parameter.requires_grad:
            if gradient is not None:
                raise RuntimeError(
                    f"frozen base parameter received gradient: {name}"
                )
            continue

        if gradient is None:
            continue

        trainable_with_grad += 1

        if not torch.isfinite(gradient).all().item():
            raise RuntimeError(f"nonfinite LoRA gradient: {name}")

        if gradient.abs().max().item() > 0:
            nonzero_gradient_tensors += 1

    if trainable_with_grad == 0:
        raise RuntimeError("no LoRA parameter received a gradient")

    if nonzero_gradient_tensors == 0:
        raise RuntimeError("all LoRA gradients are zero")

    torch.cuda.synchronize()

    print("loss:", loss.item())
    print("LoRA tensors with gradients:", trainable_with_grad)
    print("LoRA tensors with nonzero gradients:", nonzero_gradient_tensors)
    print("frozen base gradients: None")
    print(
        "peak allocated MiB:",
        round(torch.cuda.max_memory_allocated() / 1024**2, 1),
    )
    print("real SFT forward/backward: PASS")

    # 检查结束后清理梯度；没有更新任何参数。
    model.zero_grad(set_to_none=True)


if __name__ == "__main__":
    main()