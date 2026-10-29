"""Shared integrity helpers and the protected music completion predicate."""
import hashlib,json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush()
        import os;os.fsync(f.fileno())
    tmp.replace(path)


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
