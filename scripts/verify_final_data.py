"""Verify persisted provenance through the existing DatasetRecord contract."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from anime_pref.data.catalog import write_json
from anime_pref.data.dataset_record_builder import validate_dataset_record
from anime_pref.data.query_builder import load_domain_rules
from anime_pref.data.tag_subset import load_executable_tag_subset
from anime_pref.data.final_dataset import authored_challenges
from anime_pref.schemas.dataset_record import DatasetRecordSpec
from anime_pref.schemas.preference_query import SemanticSpec, SetConstraintSpec, RangeConstraintSpec


def verify_saved_records():
    """Reconstruct types only; never recalculate and replace stored provenance.

    JSON arrays become the tuple types expected by the canonical semantic layer.
    The existing validator then independently rebuilds expected Gold/count/
    signature/rule IDs/sample ID and rejects any disagreement with saved values.
    """
    rules=load_domain_rules(ROOT/'configs/domain_rules.v0.2.json')
    subset=load_executable_tag_subset(ROOT/'data/domain/subset_v0.2/executable_tags.json')
    counts=Counter()
    for split in ('train','validation','test'):
        path=ROOT/f'data/final/{split}.v0.2.jsonl'
        for line in path.read_text(encoding='utf-8').splitlines():
            record=json.loads(line)
            spec=record['semantic_spec']
            typed={}
            for name,value in spec.items():
                if name in ('genres','tags','tag_groups'):
                    typed[name]=SetConstraintSpec(**{k:tuple(v) for k,v in value.items()})
                elif name in ('year','episodes'):
                    typed[name]=RangeConstraintSpec(**value)
                else:
                    typed[name]=tuple(value)
            record['semantic_spec']=SemanticSpec(**typed)
            record['normalization_rule_ids']=tuple(record['normalization_rule_ids'])
            validate_dataset_record(DatasetRecordSpec(**record),rules,subset)
            counts[split]+=1
    # Challenge uses the existing E0 challenge shape, not DatasetRecordSpec.
    # Compare it directly with deterministic Gold rebuilt from the authored
    # SemanticSpecs. Do not pretend that challenge IDs are full sample IDs.
    challenge=[json.loads(line) for line in (ROOT/'data/final/challenge.v0.2.jsonl').read_text(encoding='utf-8').splitlines()]
    if challenge!=authored_challenges(rules):
        raise ValueError('saved challenge differs from authored source semantics')
    return {'status':'PASS','validated_record_count':sum(counts.values()),
        'splits':dict(counts),'authored_challenge_verified_count':len(challenge),
        'rules_hash':rules.rules_hash,'subset_hash':rules.executable_subset_hash,
        'validation':'Existing DatasetRecord validator, applied to saved JSONL; no silent repair.'}


if __name__=='__main__':
    result=verify_saved_records()
    write_json(ROOT/'artifacts/final/provenance_audit.json',result)
    print(json.dumps(result),flush=True)
