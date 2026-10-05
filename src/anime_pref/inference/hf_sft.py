"""Reload the saved S1 adapter while reusing frozen E0 inference."""

from hashlib import sha256
import json
from pathlib import Path

from anime_pref.inference.hf_baseline import HuggingFaceBaselineAdapter
from anime_pref.schemas.e0_baseline import E0BaselineConfig


class HuggingFaceSFTAdapter(HuggingFaceBaselineAdapter):
    def __init__(
        self,
        config: E0BaselineConfig,
        system_prompt: str,
        adapter_dir: Path,
        run_identity_path: Path,
    ) -> None:
        from peft import PeftModel

        if not isinstance(adapter_dir, Path):
            raise ValueError("adapter_dir must be a pathlib.Path")
        if not isinstance(run_identity_path, Path):
            raise ValueError("run_identity_path must be a pathlib.Path")

        adapter_config_path = adapter_dir / "adapter_config.json"
        weights_path = adapter_dir / "adapter_model.safetensors"

        if not adapter_config_path.is_file():
            raise ValueError("saved adapter config is missing")
        if not weights_path.is_file():
            raise ValueError("saved adapter weights are missing")

        try:
            identity = json.loads(
                run_identity_path.read_text(encoding="utf-8")
            )
            adapter_config = json.loads(
                adapter_config_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("failed to read S1 artifacts") from exc

        if not isinstance(identity, dict):
            raise ValueError("S1 identity must be an object")
        if not isinstance(adapter_config, dict):
            raise ValueError("adapter config must be an object")

        training_config = identity.get("training_config")
        if not isinstance(training_config, dict):
            raise ValueError("S1 training config is missing")

        expected_identity = {
            "base_model_id": config.model_id,
            "tokenizer_id": config.tokenizer_id,
            "resolved_model_revision": config.revision,
        }


        # 遍历 expected_identity。
        # 对比 identity 中的实际值，不一致则抛出 ValueError。
        #
        # 再对比 training_config 中的：
        # prompt_version         与 config.prompt_version
        # serialization_identity 与 config.serialization_identity

        for key,v in expected_identity.items():
            if identity[key] != v:
                raise ValueError(f'{key} is incompatible, current value is {identity[key]}, expected {v}')
        if training_config['prompt_version'] != config.prompt_version:
            raise ValueError(f'version must same')
        if training_config['serialization_identity'] != config.serialization_identity:
            raise ValueError(f'serialization_identity must same')

        if not config.prompt_frozen:
            raise ValueError("SFT evaluation requires the frozen prompt")
        if config.enable_thinking:
            raise ValueError("SFT evaluation requires thinking disabled")
        if config.dtype != "bfloat16":
            raise ValueError("SFT evaluation must retain E0 BF16 loading")

        if adapter_config.get("peft_type") != "LORA":
            raise ValueError("saved adapter must use LoRA")

        expected_adapter_fields = {
            "r": training_config["lora_r"],
            "lora_alpha": training_config["lora_alpha"],
            "lora_dropout": training_config["lora_dropout"],
            "bias": training_config["lora_bias"],
            "task_type": training_config["lora_task_type"],
        }
        for name, expected in expected_adapter_fields.items():
            if adapter_config.get(name) != expected:
                raise ValueError(f"saved adapter mismatch: {name}")

        # 模块集合顺序没有语义。
        if set(adapter_config.get("target_modules", [])) != set(
            training_config["lora_target_modules"]
        ):
            raise ValueError("saved adapter target modules mismatch")

        # 重新加载 base 和 tokenizer，完整复用 E0 的加载与推理配置。
        super().__init__(config, system_prompt)

        # 实际加载的 prompt/template 必须与训练时一致。
        for name in (
            "system_prompt_sha256",
            "chat_template_sha256",
        ):
            if self.runtime_identity[name] != identity.get(name):
                raise ValueError(f"loaded inference identity mismatch: {name}")


        # 调用 PeftModel.from_pretrained，参数：
        # 第一个参数：self.model
        # 第二个参数：str(adapter_dir)
        # is_trainable=False
        # local_files_only=True
        #
        # 将返回对象重新保存到 self.model。
        # 这里不调用 load_s1_model，不创建新 LoRA，不 merge。
        self.model = PeftModel.from_pretrained(self.model,str(adapter_dir),is_trainable=False,local_files_only=True)

        self.model.eval()

        if any(
            parameter.requires_grad
            for parameter in self.model.parameters()
        ):
            raise RuntimeError("inference model must be fully frozen")

        # 保留实际使用的 adapter 身份，供后续评估报告追溯。
        self.runtime_identity.update({
            "s1_version": identity["s1_version"],
            "adapter_path": str(adapter_dir.resolve()),
            "adapter_weights_sha256": sha256(
                weights_path.read_bytes()
            ).hexdigest(),
        })