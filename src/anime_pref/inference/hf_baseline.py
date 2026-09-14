"""Minimal Hugging Face inference adapter used only by E0 baseline."""

from hashlib import sha256
from typing import Iterable

from anime_pref.evaluation.e0_baseline import build_inference_messages
from anime_pref.schemas.e0_baseline import E0BaselineConfig


class HuggingFaceBaselineAdapter:
    """Load one checkpoint and perform deterministic, non-training generation."""

    def __init__(self, config: E0BaselineConfig, system_prompt: str) -> None:
        # Heavy optional dependencies remain local to E0 runtime.  The rest of
        # the project and its tests can import without initializing CUDA.
        import torch
        import transformers
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if config.do_sample or config.num_beams != 1:
            raise ValueError("E0 adapter only supports greedy primary generation")
        if config.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("E0 config requires CUDA but CUDA is unavailable")
        dtype = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }[config.dtype]

        self.config = config
        self.system_prompt = system_prompt
        self.torch = torch
        # Passing the concrete snapshot directory prevents tokenizer internals
        # from making an unrelated model-card lookup during an offline E0 run.
        tokenizer_source = (
            snapshot_download(
                config.tokenizer_id,
                revision=config.revision,
                local_files_only=True,
            )
            if config.local_files_only
            else config.tokenizer_id
        )
        model_source = (
            snapshot_download(
                config.model_id,
                revision=config.revision,
                local_files_only=True,
            )
            if config.local_files_only
            else config.model_id
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_source,
            local_files_only=config.local_files_only,
        )
        #若模型无填充对应的id，则将终止符作为其对应填充id
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        #填充方式为左填充
        self.tokenizer.padding_side = "left"
        self.model = AutoModelForCausalLM.from_pretrained(
            model_source,
            dtype=dtype,
            local_files_only=config.local_files_only,
        )
        self.model.to(config.device)
        self.model.eval()
        self.resolved_model_revision = str(
            getattr(self.model.config, "_commit_hash", None) or config.revision
        )
        chat_template = self.tokenizer.chat_template or ""
        self.chat_template_sha256 = sha256(chat_template.encode("utf-8")).hexdigest()
        self.runtime_identity = {
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "device_name": (
                torch.cuda.get_device_name(0) if config.device == "cuda" else "cpu"
            ),
            "chat_template_sha256": self.chat_template_sha256,
            "system_prompt_sha256": sha256(system_prompt.encode("utf-8")).hexdigest(),
        }

    def _serialize(self, user_text: str) -> str:
        """Apply the official Qwen chat template with thinking disabled."""
        messages = build_inference_messages(self.system_prompt, user_text)
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=self.config.enable_thinking,
        )

    def generate_batch(self, user_texts: Iterable[str]) -> tuple[str, ...]:
        """Generate once per input using greedy decoding and retain raw text."""
        texts = tuple(user_texts)
        if not texts:
            return ()
        prompts = [self._serialize(text) for text in texts]
        encoded = self.tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            add_special_tokens=False,
        ).to(self.config.device)
        input_width = encoded.input_ids.shape[1]
        with self.torch.inference_mode():
            generated = self.model.generate(
                **encoded,
                do_sample=False,
                num_beams=1,
                max_new_tokens=self.config.max_new_tokens,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        completion_ids = generated[:, input_width:]
        return tuple(
            self.tokenizer.batch_decode(
                completion_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        )


def generate_all(
    adapter: HuggingFaceBaselineAdapter,
    user_texts: Iterable[str],
    batch_size: int,
) -> tuple[str, ...]:
    """Run ordered batches without retries, n-best search, or hidden sampling."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    values = tuple(user_texts)
    outputs: list[str] = []
    for start in range(0, len(values), batch_size):
        outputs.extend(adapter.generate_batch(values[start : start + batch_size]))
    if len(outputs) != len(values):
        raise RuntimeError("model adapter did not return one output per input")
    return tuple(outputs)
