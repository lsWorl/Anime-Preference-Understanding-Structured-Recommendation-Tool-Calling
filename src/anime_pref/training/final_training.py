"""Reuse S1 QLoRA/Trainer primitives with a separate final experiment identity."""
from dataclasses import asdict
import json
from hashlib import sha256
from pathlib import Path
from statistics import median
from math import ceil

from anime_pref.data.catalog import write_json
from anime_pref.data.query_validation import validate_query_structure
from anime_pref.data.domain_validation import validate_query_domain
from anime_pref.data.query_builder import load_domain_rules
from anime_pref.schemas.s1_training import S1TrainingConfig
from anime_pref.training.sft_config import _validate_config_types, _validate_config_ranges
from anime_pref.training.sft_identity import sample_ids_sha256, sha256_text
from anime_pref.training.sft_dataset import build_sft_features
from anime_pref.training.sft_environment import inspect_s1_environment
from anime_pref.training.sft_model import load_s1_model
from anime_pref.training.sft_trainer import build_s1_trainer

REVISION="1cfa9a7208912126459214e8b04321603b3df60c"


def load_final_config(path):
    """Same config structure as S1; its pilot-only frozen loader remains unchanged."""
    raw=json.loads(Path(path).read_text(encoding="utf-8"))
    if set(raw)!=set(S1TrainingConfig.__dataclass_fields__):
        raise ValueError("final config keys mismatch")
    _validate_config_types(raw)
    raw["lora_target_modules"]=tuple(raw["lora_target_modules"])
    config=S1TrainingConfig(**raw)
    _validate_config_ranges(config)
    expected={"model_id":"Qwen/Qwen3-4B","tokenizer_id":"Qwen/Qwen3-4B","revision":REVISION,
        "dataset_version":"anime-pref-final-v0.2","enable_thinking":False,"load_in_4bit":True,
        "bnb_4bit_quant_type":"nf4","bnb_4bit_compute_dtype":"bfloat16","bf16":True,"fp16":False,
        "load_best_model_at_end":True,"metric_for_best_model":"eval_loss","greater_is_better":False,
        "lora_bias":"none","lora_task_type":"CAUSAL_LM"}
    for k,v in expected.items():
        if getattr(config,k)!=v: raise ValueError(f"final frozen contract mismatch: {k}")
    if not set(config.lora_target_modules)<={"q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"}:
        raise ValueError("invalid LoRA target")
    if not {"q_proj","k_proj","v_proj","o_proj"}<=set(config.lora_target_modules):
        raise ValueError("missing attention LoRA target")
    return config


def load_final_records(root, split, config):
    """Only training/validation are exposed to the Trainer, with real domain checks."""
    if split not in ("train","validation"): raise ValueError("training split must be train/validation")
    path=root / getattr(config,f"{split}_path")
    rows=[json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    if len(rows)!=getattr(config,f"{split}_expected_count"): raise ValueError("dataset count drift")
    rules=load_domain_rules(root / "configs/domain_rules.v0.2.json")
    for row in rows:
        if row["dataset_version"]!=config.dataset_version or row["rules_hash"]!=rules.rules_hash:
            raise ValueError("dataset identity drift")
        validate_query_structure(row["gold_query"]);validate_query_domain(row["gold_query"],rules)
    sample_ids_sha256(rows)
    return rows


def token_summary(train, validation):
    values=sorted(len(f["input_ids"]) for f in train)
    return {"train":{"count":len(values),"min":values[0],"median":median(values),
                     "p95":values[ceil(.95*len(values))-1],"max":values[-1]},
            "validation":{"count":len(validation),"max":max(len(f["input_ids"]) for f in validation)}}


def train_final(root, execute=False):
    """Fresh NF4 base, saved identity, one main run, best adapter; no test selection."""
    config=load_final_config(root / "configs/final_qlora.v0.2.json")
    adapter_path=root/config.adapter_output_dir
    if execute and ((adapter_path/"adapter_model.safetensors").exists() or (root/config.run_identity_path).exists()):
        raise FileExistsError("final experiment already exists; never overwrite/retrain on test results")
    prompt=(root/config.prompt_path).read_text(encoding="utf-8").rstrip("\r\n")
    train=load_final_records(root,"train",config);val=load_final_records(root,"validation",config)
    model,tokenizer=load_s1_model(config)
    train_features=build_sft_features(train,prompt,tokenizer,config.max_seq_length)
    val_features=build_sft_features(val,prompt,tokenizer,config.max_seq_length)
    summary=token_summary(train_features,val_features)
    first=train_features[0]; supervised=next(i for i,v in enumerate(first["labels"]) if v!=-100)
    identity={"s1_version":config.s1_version,"base_model_id":config.model_id,"tokenizer_id":config.tokenizer_id,
        "resolved_model_revision":config.revision,"dataset_version":config.dataset_version,
        "train_sample_ids_sha256":sample_ids_sha256(train),"validation_sample_ids_sha256":sample_ids_sha256(val),
        "system_prompt_sha256":sha256_text(prompt),"chat_template_sha256":sha256_text(tokenizer.chat_template),
        "training_config":asdict(config),"environment":inspect_s1_environment(),"token_length_summary":summary,
        "dataset_file_sha256":{s:sha256((root/getattr(config,f'{s}_path')).read_bytes()).hexdigest() for s in ('train','validation')},
        "masking_evidence":{"input_shape":[1,len(first["input_ids"])],"labels_shape":[1,len(first["labels"])],
                            "masked_prompt_tokens":supervised,"supervised_tokens":len(first["labels"])-supervised,
                            "completion_decoded":tokenizer.decode(first['input_ids'][supervised:])}}
    trainer=build_s1_trainer(config,root,model,tokenizer,train_features,val_features)
    print("Token summary:",summary,flush=True)
    print("Masking:",identity["masking_evidence"],flush=True)
    if not execute: return identity
    write_json(root/config.run_identity_path,identity)
    result=trainer.train()
    trainer.save_model(str(adapter_path));trainer.save_state();trainer.save_metrics("train",result.metrics)
    tokenizer.save_pretrained(adapter_path)
    write_json(root/"artifacts/final/adapter_manifest.json",{
        "best_checkpoint":trainer.state.best_model_checkpoint,"best_validation_loss":trainer.state.best_metric,
        "adapter_sha256":sha256((adapter_path/"adapter_model.safetensors").read_bytes()).hexdigest(),
        "global_step":trainer.state.global_step,"selection_metric":"validation loss"})
    print("Final adapter saved:",adapter_path,flush=True)
    return identity
