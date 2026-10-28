from __future__ import annotations
import hashlib,json
from pathlib import Path

TOOLS=['inspect_dataset','discover_evidence','read_evidence','baseline_summary',
       'run_experiment','evaluate_experiment','finish']
DECISION_SCHEMA={'type':'object','properties':{
 'tool':{'type':'string','enum':TOOLS},
 'argument':{'type':'string'},
 'why':{'type':'string'},
 'hypothesis':{'type':'string'},
 'expected_observation':{'type':'string'},
 'evidence_ids':{'type':'array','items':{'type':'string'}}},
 'required':['tool','argument','why','hypothesis','expected_observation','evidence_ids'],
 'additionalProperties':False}
VISION_SCHEMA={'type':'object','properties':{'kern':{'type':'string'},
 'uncertainties':{'type':'array','items':{'type':'string'}}},
 'required':['kern','uncertainties'],'additionalProperties':False}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush()
        import os;os.fsync(f.fileno())
    tmp.replace(path)


def validate_decision(data,known_evidence):
    if set(data)!=set(DECISION_SCHEMA['required']):raise ValueError('Decision fields do not match schema')
    if data['tool'] not in TOOLS:raise ValueError('Unregistered tool')
    for k in ['argument','why','hypothesis','expected_observation']:
        if not isinstance(data[k],str):raise ValueError(f'{k} must be text')
    if not isinstance(data['evidence_ids'],list) or any(not isinstance(x,str) or x not in known_evidence for x in data['evidence_ids']):
        raise ValueError('Unobserved or invented evidence citation')
    if not data['why'].strip():raise ValueError('A reviewable reason is required')


def success_gate(evaluation,spec):
    """The controller cannot replace or weaken this predicate."""
    if not evaluation:return False
    acceptance=spec['acceptance']
    return (evaluation.get('samples')==acceptance['required_samples']
            and evaluation.get('parseable')==acceptance['required_samples']
            and evaluation['melody']['error_rate']<=acceptance['max_melody_error_rate']
            and evaluation['chords']['error_rate']<=acceptance['max_chord_error_rate']
            and evaluation.get('transposition_failures')==0
            and (not acceptance['require_audited_chord_timing'] or evaluation.get('chord_timing_audited') is True)
            and (not acceptance['require_musician_review'] or evaluation.get('musician_accepted') is True))
