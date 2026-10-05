"""Fresh-process comparison on final splits, reusing the frozen E0 evaluator."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from anime_pref.data.catalog import write_json
from anime_pref.data.query_builder import load_domain_rules
from anime_pref.evaluation.e0_baseline import load_e0_inputs,evaluate_raw_prediction,predictions_to_jsonl
from anime_pref.inference.final_parser import FinalPreferenceParser

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=('base','s1','final'))
    parser.add_argument('--split',choices=('validation','test','challenge','legacy_challenge'))
    args=parser.parse_args();out=ROOT/'artifacts/final/evaluation'/args.model
    if args.split is None:
        # One child per split prevents long-lived runtime state from contaminating
        # later sets. A completed set is never overwritten during an interrupted
        # run's resume; report_final_project rechecks all identities and outputs.
        import subprocess
        for split in ('validation','test','challenge','legacy_challenge'):
            prediction=out/f'{split}_predictions.jsonl';identity=out/f'{split}_identity.json'
            if prediction.exists() and identity.exists():
                print('Saved split retained:',args.model,split,flush=True)
                continue
            if prediction.exists() or identity.exists():
                raise RuntimeError('incomplete artifact pair; preserve it before re-running')
            subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),
                            '--model',args.model,'--split',split],cwd=ROOT,check=True)
        return
    if (out/f'{args.split}_predictions.jsonl').exists() or (out/f'{args.split}_identity.json').exists():
        raise FileExistsError('evaluation split already exists; use saved predictions')
    adapter=FinalPreferenceParser(ROOT,args.model)
    rules=load_domain_rules(ROOT/'configs/domain_rules.v0.2.json')
    out.mkdir(parents=True,exist_ok=True)
    for split in (args.split,):
        path=ROOT/f'data/final/{split}.v0.2.jsonl' if split!='legacy_challenge' else ROOT/'data/pilot/challenge.v0.1.jsonl'
        records=load_e0_inputs(path,split if split!='legacy_challenge' else 'challenge')
        # Ordered batches retain every raw output, without retries or repairs.
        outputs=[]
        for start in range(0,len(records),adapter.config.batch_size):
            batch=records[start:start+adapter.config.batch_size]
            outputs.extend(adapter.generate_batch(r.user_text for r in batch))
            if start%20==0: print(args.model,split,start,'/',len(records),flush=True)
        predictions=tuple(evaluate_raw_prediction(r,text,rules,adapter.config,adapter.resolved_model_revision)
                          for r,text in zip(records,outputs,strict=True))
        (out/f'{split}_predictions.jsonl').write_text(predictions_to_jsonl(predictions),encoding='utf-8',newline='')
        write_json(out/f'{split}_identity.json',{'model_variant':args.model,'inference_config':asdict(adapter.config),
            'dataset_sha256':sha256(path.read_bytes()).hexdigest(),'rules_hash':rules.rules_hash,
            'sample_count':len(records),'fresh_process_per_split':True,
            'effective_batch_size':adapter.config.batch_size,**adapter.runtime_identity})
        print(args.model,split,'exact:',sum(p.exact_match for p in predictions),'/',len(predictions),flush=True)

if __name__=='__main__':main()
