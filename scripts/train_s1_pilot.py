"""Prepare the frozen S1 experiment before starting training."""

from pathlib import Path
import json
import sys
import argparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from anime_pref.evaluation.e0_baseline import (
    load_e0_config,
    load_system_prompt,
)
from anime_pref.training.sft_config import load_s1_config
from anime_pref.training.sft_data import load_sft_records
from anime_pref.training.sft_dataset import build_sft_features
from anime_pref.training.sft_identity import build_s1_run_identity
from anime_pref.training.sft_model import load_s1_model
from anime_pref.training.sft_trainer import build_s1_trainer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train",
        action="store_true",
        help="Run the frozen S1 training experiment after preflight.",
    )
    args = parser.parse_args()

    config = load_s1_config(PROJECT_ROOT / "configs/s1_qlora_pilot.v0.1.json")

    # 防止后续正式运行覆盖已有实验结果。
    for relative_path in (
        config.trainer_output_dir,
        config.adapter_output_dir,
    ):
        output_path = PROJECT_ROOT / relative_path

        if output_path.exists():
            if not output_path.is_dir():
                raise RuntimeError(f"output path is not a directory: {output_path}")
            if any(output_path.iterdir()):
                raise RuntimeError(
                    f"output directory already contains artifacts: " f"{output_path}"
                )

    identity_path = PROJECT_ROOT / config.run_identity_path
    if identity_path.exists():
        raise RuntimeError(f"run identity already exists: {identity_path}")

    e0_config = load_e0_config(
        PROJECT_ROOT / "configs/e0_baseline.v0.1.json",
        PROJECT_ROOT,
    )
    system_prompt = load_system_prompt(
        e0_config,
        PROJECT_ROOT,
    )

    train_records = load_sft_records(PROJECT_ROOT, "train")
    validation_records = load_sft_records(
        PROJECT_ROOT,
        "validation",
    )
    model, tokenizer = load_s1_model(config)

    # 分别调用 build_sft_features，生成：
    # train_features
    # validation_features
    #
    # 两次都使用：
    # system_prompt、tokenizer、config.max_seq_length。
    train_features = build_sft_features(
        train_records,
        system_prompt=system_prompt,
        tokenizer=tokenizer,
        max_seq_length=config.max_seq_length,
    )
    validation_features = build_sft_features(
        validation_records,
        system_prompt=system_prompt,
        tokenizer=tokenizer,
        max_seq_length=config.max_seq_length,
    )

    # 调用 build_s1_run_identity，保存为 identity。
    #
    # 参数按函数定义传入：
    # config、PROJECT_ROOT、model、tokenizer、
    # system_prompt、train_records、validation_records。

    identity = build_s1_run_identity(
        config,
        PROJECT_ROOT,
        model,
        tokenizer,
        system_prompt,
        train_records,
        validation_records,
    )

    # 调用 build_s1_trainer，保存为 trainer。
    #
    # 传入 config、PROJECT_ROOT、model、tokenizer、
    # train_features、validation_features。

    trainer = build_s1_trainer(
        config, PROJECT_ROOT, model, tokenizer, train_features, validation_features
    )

    if trainer.state.global_step != 0:
        raise RuntimeError("fresh Trainer must start at global_step=0")

    if trainer.optimizer is not None:
        raise RuntimeError("preflight must not create an optimizer")

    print(
        "train / validation:",
        len(train_features),
        len(validation_features),
    )
    print(
        "token lengths:",
        json.dumps(
            identity["token_length_summary"],
            ensure_ascii=False,
        ),
    )
    print("prompt SHA256:", identity["system_prompt_sha256"])
    print("template SHA256:", identity["chat_template_sha256"])
    print("global_step:", trainer.state.global_step)
    print("S1 preflight: PASS")

    # 默认运行到 preflight 为止。
    if not args.train:
        return

    # 必须先保存实验 identity，再执行第一个参数更新。
    identity_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用 identity_path.open("x", encoding="utf-8")。
    # "x" 表示独占创建：文件已经存在时拒绝覆盖。
    #
    # 在 with 块中使用 json.dump 保存 identity：
    # ensure_ascii=False
    # indent=2
    # sort_keys=True
    # allow_nan=False
    #
    # 写入后追加一个换行。

    with identity_path.open("x", encoding="utf-8") as file:
        json.dump(
            identity,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        file.write("\n")

    print("Starting the frozen S1 training run.")


    # 当前是全新的首轮实验。
    train_result = trainer.train()

    # 配置 load_best_model_at_end=True。
    # 训练结束后，内存中的模型应是 validation loss 最优的 checkpoint。
    if trainer.state.best_model_checkpoint is None:
        raise RuntimeError("training did not select a best checkpoint")

    if trainer.state.best_metric is None:
        raise RuntimeError("best validation loss is missing")

    adapter_dir = PROJECT_ROOT / config.adapter_output_dir

    # 调用 trainer.save_model(str(adapter_dir))。
    #
    # 当前 model 是 PEFT model：
    # save_model 保存 adapter，并保存关联 tokenizer 信息。
    # 不 merge adapter，不保存一份完整 base 权重。
    trainer.save_model(str(adapter_dir))

    # 调用 trainer.save_state()：
    # 保存 Trainer state，包括 step、epoch 和 loss/lr log_history。
    trainer.save_state()
    # 调用 trainer.save_metrics("train", train_result.metrics)：
    # 保存本轮训练统计。
    trainer.save_metrics("train", train_result.metrics)

    # 确认保存出了可重新加载的 adapter。
    if not (adapter_dir / "adapter_config.json").is_file():
        raise RuntimeError("adapter_config.json was not saved")

    weight_files = (
        adapter_dir / "adapter_model.safetensors",
        adapter_dir / "adapter_model.bin",
    )
    if not any(path.is_file() for path in weight_files):
        raise RuntimeError("adapter weights were not saved")

    print("global_step:", trainer.state.global_step)
    print("best validation loss:", trainer.state.best_metric)
    print("best checkpoint:", trainer.state.best_model_checkpoint)
    print("adapter directory:", adapter_dir)
    print("S1 training and adapter save: PASS")


if __name__ == "__main__":
    main()
