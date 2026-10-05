"""Audit actual final tokens before fixing length and the single training config."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer
from anime_pref.data.catalog import write_json
from anime_pref.training.sft_tokenization import tokenize_sft_record
from anime_pref.training.final_training import token_summary

def main():
    config=json.loads((ROOT/"configs/s1_qlora_pilot.v0.1.json").read_text(encoding="utf-8"))
    tokenizer=AutoTokenizer.from_pretrained(snapshot_download(config['tokenizer_id'],revision=config['revision'],local_files_only=True),local_files_only=True)
    prompt=(ROOT/"configs/final_system_prompt.v0.2.txt").read_text(encoding="utf-8").rstrip()
    features={s:[tokenize_sft_record(json.loads(l),prompt,tokenizer) for l in (ROOT/f'data/final/{s}.v0.2.jsonl').read_text(encoding='utf-8').splitlines()] for s in ('train','validation')}
    summary=token_summary(features['train'],features['validation'])
    maximum=max(summary['train']['max'],summary['validation']['max'])
    config.update(s1_version="final-qlora-v0.2",dataset_version="anime-pref-final-v0.2",
        train_path="data/final/train.v0.2.jsonl",validation_path="data/final/validation.v0.2.jsonl",
        train_expected_count=1200,validation_expected_count=150,prompt_version="final-json-extraction-v0.2",
        prompt_path="configs/final_system_prompt.v0.2.txt",max_seq_length=((maximum+127)//128)*128,
        num_train_epochs=1,trainer_output_dir="artifacts/final/trainer",adapter_output_dir="artifacts/final/adapter",
        run_identity_path="artifacts/final/run_identity.json")
    # One epoch is an a-priori pilot choice: S1 showed overfit after epoch 1.
    # No final test/challenge output has been generated at this point.
    write_json(ROOT/'configs/final_qlora.v0.2.json',config)
    write_json(ROOT/'artifacts/final/token_audit.json',summary)
    print('Final actual lengths:',summary,'max_seq_length=',config['max_seq_length'],flush=True)

if __name__=='__main__': main()
