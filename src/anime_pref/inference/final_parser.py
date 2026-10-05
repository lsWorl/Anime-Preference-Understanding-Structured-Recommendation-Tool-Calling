"""One inference loader for Base / frozen S1 / final, with common eval conditions."""
from dataclasses import replace, asdict
from hashlib import sha256
import json
from pathlib import Path

from anime_pref.evaluation.e0_baseline import load_e0_config
from anime_pref.inference.hf_baseline import HuggingFaceBaselineAdapter


def final_inference_config(root):
    # Common v0.2 instruction is required for the enlarged vocabulary. All three
    # models are re-evaluated under it; historical E0/S1 scores remain separate.
    return replace(load_e0_config(root/'configs/e0_baseline.v0.1.json',root),
                   prompt_version='final-json-extraction-v0.2',
                   # Batch one keeps the BF16 evaluation comfortably within
                   # 12 GB. Each split is evaluated in a fresh OS process.
                   prompt_path='configs/final_system_prompt.v0.2.txt',batch_size=1)


class FinalPreferenceParser(HuggingFaceBaselineAdapter):
    def __init__(self, root, model_variant="final"):
        if model_variant not in ("base","s1","final"): raise ValueError("unknown model variant")
        config=final_inference_config(root)
        prompt=(root/config.prompt_path).read_text(encoding='utf-8').rstrip('\r\n')
        super().__init__(config,prompt)
        self.model_variant=model_variant
        self.runtime_identity['model_variant']=model_variant
        self.runtime_identity['release_unused_cuda_cache_between_calls']=True
        if model_variant!='base':
            from peft import PeftModel
            directory=root/('artifacts/s1/adapter' if model_variant=='s1' else 'artifacts/final/adapter')
            identity=json.loads((directory.parent/'run_identity.json').read_text(encoding='utf-8'))
            if identity['resolved_model_revision']!=config.revision or identity['base_model_id']!=config.model_id:
                raise ValueError('adapter base identity mismatch')
            if identity['chat_template_sha256']!=self.chat_template_sha256:
                raise ValueError('adapter template mismatch')
            if model_variant=='final' and identity['system_prompt_sha256']!=self.runtime_identity['system_prompt_sha256']:
                raise ValueError('final training/inference prompt mismatch')
            self.model=PeftModel.from_pretrained(self.model,str(directory),is_trainable=False,local_files_only=True)
            self.model.eval()
            if any(p.requires_grad for p in self.model.parameters()): raise RuntimeError('inference parameters not frozen')
            weight_hash=sha256((directory/'adapter_model.safetensors').read_bytes()).hexdigest()
            if model_variant=='final':
                manifest=json.loads((root/'artifacts/final/adapter_manifest.json').read_text(encoding='utf-8'))
                if manifest['adapter_sha256']!=weight_hash: raise ValueError('adapter weight identity mismatch')
            self.runtime_identity.update(adapter_weights_sha256=weight_hash,
                training_system_prompt_sha256=identity['system_prompt_sha256'])

    def generate_batch(self, user_texts):
        # generate_batch returns CPU strings; its temporary GPU tensors and KV
        # cache no longer need to be retained. Releasing unused allocator blocks
        # limits accumulated reserved memory on a 12-GB Windows GPU. This does
        # not mutate weights, retry generation or alter decoding parameters.
        try:
            return super().generate_batch(user_texts)
        finally:
            if self.config.device=='cuda':
                self.torch.cuda.empty_cache()


def make_service(root, variant="final"):
    from anime_pref.data.catalog import load_catalog
    from anime_pref.data.query_builder import load_domain_rules
    from anime_pref.data.tag_subset import load_executable_tag_subset
    from anime_pref.data.rules_identity import validate_executable_rules_identity
    from anime_pref.recommendation import RecommendationService
    rules=load_domain_rules(root/'configs/domain_rules.v0.2.json')
    subset=load_executable_tag_subset(root/'data/domain/subset_v0.2/executable_tags.json')
    validate_executable_rules_identity(rules,subset)
    return RecommendationService(FinalPreferenceParser(root,variant),rules,
        load_catalog(root/'data/catalog/anilist_catalog_v0.1.jsonl',root/'data/catalog/manifest.json'))
