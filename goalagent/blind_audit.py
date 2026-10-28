"""Audit the actual reviewer inputs and frozen artifacts, not reviewer self-report."""
import argparse
import json
from pathlib import Path
from .blind_review import read,sha,verify_seal,REVIEW_FORMAT,REVIEW_SCHEMA
from .contracts import atomic_json
from .roles import role_prompt


def audit(folder):
    folder=Path(folder).resolve();seal=verify_seal(folder);state=read(folder/'state.json')
    protocol=read(folder/'protocol.json');cases=[];usage={}
    for sample in read(folder/'public-inputs.json'):
        out=folder/'cases'/sample['id'];record=read(out/'review.json');model=out/'model'
        expected=role_prompt('reviewer',{'candidate':(out/'candidate.krn').read_text(),'format':REVIEW_FORMAT})
        events=[]
        if (model/'events.jsonl').exists():
            events=[json.loads(line) for line in (model/'events.jsonl').read_text().splitlines()]
        extra=[e['item']['type'] for e in events if e.get('item',{}).get('type') not in [None,'agent_message','reasoning']]
        metadata=read(model/'metadata.json') if (model/'metadata.json').exists() else {}
        for key,val in metadata.get('usage',{}).items():
            if isinstance(val,(int,float)):usage[key]=usage.get(key,0)+val
        cases.append({'case':sample['id'],'review_status':record['status'],
                      'prompt_exactly_allowlisted':(model/'prompt.txt').exists() and (model/'prompt.txt').read_text()==expected,
                      'schema_matches':(model/'schema.json').exists() and read(model/'schema.json')==REVIEW_SCHEMA,
                      'image_hash_matches':metadata.get('image_sha256')==sample['image_sha256'],
                      'no_model_tools':not extra and not metadata.get('unexpected_tool_events'),
                      'os_read_isolation':metadata.get('os_read_isolation',False)})
    checks={'all_inputs_verified':all(c['prompt_exactly_allowlisted'] and c['schema_matches'] and c['image_hash_matches'] for c in cases),
            'no_model_side_tools':all(c['no_model_tools'] for c in cases),
            'all_cases_sealed':len(seal['samples'])==len(cases),
            'within_call_budget':state['model_calls']<=protocol['budget']['max_model_calls'],
            'sealed_before_results_written':not (folder/'results.json').exists() or (folder/'seal.json').stat().st_mtime<=(folder/'results.json').stat().st_mtime,
            'scorer_result_matches_seal':not (folder/'results.json').exists() or read(folder/'results.json')['seal_sha256']==sha(folder/'seal.json')}
    result={'checks':checks,'pass':all(checks.values()),'cases':cases,'usage':usage,
            'scope':'Audit of application data flow and observed tool events, not proof of OS isolation, unknown training data, musical correctness or unbiased human labels.'}
    atomic_json(folder/'audit.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');print(json.dumps(audit(p.parse_args().folder),indent=2))
