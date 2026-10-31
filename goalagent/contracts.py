"""Shared integrity helpers and the protected music completion predicate."""
import errno
import hashlib,json
import tempfile
import time
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class AtomicWriteError(OSError):
    """The completed temporary file could not replace its destination."""


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.'+path.name+'.',suffix='.tmp',delete=False) as f:
            tmp=Path(f.name)
            json.dump(value,f,ensure_ascii=False,indent=2);f.flush()
            import os;os.fsync(f.fileno())
        # Retry replacement only, never the action that produced this state.
        delays=(0.01,0.025,0.05,0.1,0.2)
        for attempt in range(len(delays)+1):
            try:
                tmp.replace(path)
                return
            except OSError as error:
                transient=error.errno in {errno.EACCES,errno.EPERM,errno.EBUSY} or getattr(error,'winerror',None) in {5,32,33}
                if not transient:raise
                if attempt==len(delays):raise AtomicWriteError(error.errno,'Atomic JSON replacement failed after bounded retries: '+str(error),str(path)) from error
                time.sleep(delays[attempt])
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)


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
