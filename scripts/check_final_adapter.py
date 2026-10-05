"""Real fresh-process saved-adapter smoke, separate from headline evaluation."""
from pathlib import Path
import sys
import json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from anime_pref.inference.final_parser import FinalPreferenceParser
from anime_pref.data.catalog import write_json
from anime_pref.data.query_builder import load_domain_rules
from anime_pref.evaluation.e0_baseline import evaluate_raw_prediction,load_e0_inputs

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    adapter=FinalPreferenceParser(ROOT)
    sample=load_e0_inputs(ROOT/'data/final/validation.v0.2.jsonl','validation')[0]
    first=adapter.generate_batch((sample.user_text,))[0]
    second=adapter.generate_batch((sample.user_text,))[0]
    if first!=second:raise RuntimeError('greedy determinism check failed')
    result=evaluate_raw_prediction(sample,first,load_domain_rules(ROOT/'configs/domain_rules.v0.2.json'),adapter.config,adapter.resolved_model_revision)
    evidence={'saved_adapter_new_process':True,'deterministic_repeat':True,
        'is_loaded_in_4bit':getattr(adapter.model,'is_loaded_in_4bit',False),
        'all_parameters_frozen':all(not p.requires_grad for p in adapter.model.parameters()),
        'sample_id':sample.sample_id,'raw_model_output':first,
        'json_valid':result.parse_error is None,'schema_valid':result.schema_error is None,
        'domain_valid':result.domain_error is None,'exact_match':result.exact_match,
        'identity':adapter.runtime_identity}
    write_json(ROOT/'artifacts/final/adapter_smoke.json',evidence)
    if not evidence['all_parameters_frozen'] or not all(evidence[k] for k in ('json_valid','schema_valid','domain_valid')):
        raise RuntimeError('adapter smoke validation failed; evidence retained')
    print(json.dumps(evidence,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
