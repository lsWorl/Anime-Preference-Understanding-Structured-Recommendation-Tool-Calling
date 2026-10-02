"""Inspect the S1 runtime without loading a model or starting training."""

from importlib import metadata
import sys
from typing import Any


REQUIRED_PACKAGES = (
    "torch",
    "transformers",
    "peft",
    "accelerate",
    "bitsandbytes",
)


def inspect_s1_environment() -> dict[str, Any]:
    """Report package versions and GPU capability.

    Package presence alone does not prove that 4-bit CUDA kernels work.
    A separate smoke check will verify that after dependencies are installed.
    """

    package_versions: dict[str, str | None] = {}

    # 遍历 REQUIRED_PACKAGES。
    # 使用 metadata.version(name) 获取版本。
    # 如果抛出 metadata.PackageNotFoundError，
    # 就把该包的版本记录为 None。
    #
    # 不要捕获所有 Exception，以免隐藏其他环境故障。
    for package in REQUIRED_PACKAGES:
        try:
            package_versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            package_versions[package] = None
        

    missing_packages = [
        name
        for name, version in package_versions.items()
        if version is None
    ]

    cuda_available = False
    gpu_name = None
    torch_cuda_version = None
    bf16_supported = False

    # torch 未安装时仍应能生成报告。
    if package_versions["torch"] is not None:
        import torch

        torch_cuda_version = torch.version.cuda
        cuda_available = torch.cuda.is_available()

        # 只有 cuda_available 为 True 时，才调用：
        # torch.cuda.get_device_name(0)
        # torch.cuda.is_bf16_supported()
        #
        # 将结果分别赋给 gpu_name、bf16_supported。
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            bf16_supported = torch.cuda.is_bf16_supported()
    return {
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "package_versions": package_versions,
        "missing_packages": missing_packages,
        "torch_cuda_version": torch_cuda_version,
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "bf16_supported": bf16_supported,
    }