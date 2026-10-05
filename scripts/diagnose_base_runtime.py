"""Fresh-process diagnostic for anomalous repeated Base outputs; no metric repair."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from anime_pref.data.catalog import write_json
from anime_pref.inference.final_parser import FinalPreferenceParser

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=FinalPreferenceParser(ROOT,'base')
    rows=[json.loads(line) for line in (ROOT/'data/final/challenge.v0.2.jsonl').read_text(encoding='utf-8').splitlines()][:2]
    outputs=parser.generate_batch(row['user_text'] for row in rows)
    result={'runtime_identity':parser.runtime_identity,
        'attention':parser.model.config._attn_implementation,
        'allocated_bytes':parser.torch.cuda.memory_allocated(),
        'reserved_bytes':parser.torch.cuda.memory_reserved(),
        'cases':[{'user_text':r['user_text'],'raw_model_output':o} for r,o in zip(rows,outputs)]}
    write_json(ROOT/'artifacts/final/base_runtime_diagnostic.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
