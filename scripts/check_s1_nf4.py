"""Verify NF4 CUDA forward/backward without loading the full model."""

import torch
import bitsandbytes as bnb


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")

    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 support is required")

    torch.manual_seed(42)

    # 在 CPU 创建浮点权重，移动到 CUDA 时进行 4-bit 量化。
    layer = bnb.nn.Linear4bit(
        input_features=64,
        output_features=32,
        bias=False,
        compute_dtype=torch.bfloat16,
        compress_statistics=True,
        quant_type="nf4",
    )
    layer = layer.to("cuda")

    if layer.weight.quant_state is None:
        raise RuntimeError("4-bit quantization state is missing")

    if layer.weight.requires_grad:
        raise RuntimeError("quantized base weights must be frozen")


    # 创建随机输入 x，形状为 (2, 4, 64)。
    # device="cuda"
    # dtype=torch.bfloat16
    # requires_grad=True
    # 输入需要梯度，是为了验证梯度能够穿过冻结的量化层。
    x = torch.randn(
        (2,4,64),
        device="cuda",
        dtype=torch.bfloat16,
        requires_grad=True,
    )
    

    # 调用 layer(x)，将结果保存为 y。
    y = layer(x)

    if tuple(y.shape) != (2, 4, 32):
        raise RuntimeError(f"unexpected output shape: {tuple(y.shape)}")

    if not torch.isfinite(y).all().item():
        raise RuntimeError("forward output contains NaN or infinity")


    # 将 y 转成 float32，计算平方后的均值，保存为 loss。
    # 然后调用 loss.backward()。
    #
    # 使用 float32 计算这个小型诊断 loss，
    # 避免 BF16 精度干扰结果判断。
    loss = y.float().pow(2).mean()
    loss.backward()

    if not torch.isfinite(loss).item():
        raise RuntimeError("loss is not finite")

    if x.grad is None:
        raise RuntimeError("input gradient is missing")

    if not torch.isfinite(x.grad).all().item():
        raise RuntimeError("input gradient contains NaN or infinity")

    if x.grad.abs().max().item() == 0:
        raise RuntimeError("input gradient is entirely zero")

    if layer.weight.grad is not None:
        raise RuntimeError("frozen quantized weights received gradients")

    # 等待 CUDA 完成，确保异步运算中的错误也能暴露。
    torch.cuda.synchronize()

    print("GPU:", torch.cuda.get_device_name(0))
    print("input shape:", tuple(x.shape))
    print("output shape:", tuple(y.shape))
    print("output dtype:", y.dtype)
    print("loss:", loss.item())
    print("input gradient: finite and nonzero")
    print("quantized weight gradient: None")
    print("NF4 forward/backward: PASS")


if __name__ == "__main__":
    main()
