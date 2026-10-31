"""Shared integrity helpers and the protected music completion predicate."""
import errno
import hashlib,json
import os
import time
import uuid
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class AtomicWriteError(OSError):
    """The completed temporary file could not replace its destination."""


def _atomic_file(path,write,*,mode):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Resolve the parent once. Two absolute lookups can hit different mount
    # instances during a bind/DrvFS mount transition, even on the same device.
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temporary='.'+path.name+'.'+uuid.uuid4().hex+'.tmp'
    created=False
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode,dir_fd=directory)
        created=True
        with os.fdopen(fd,'wb') as stream:
            write(stream);stream.flush();os.fsync(stream.fileno())
        # Retry replacement only, never the action that produced this state.
        delays=(0.01,0.025,0.05,0.1,0.2)
        for attempt in range(len(delays)+1):
            try:
                os.replace(temporary,path.name,src_dir_fd=directory,dst_dir_fd=directory)
                return
            except OSError as error:
                transient=error.errno in {errno.EACCES,errno.EPERM,errno.EBUSY} or getattr(error,'winerror',None) in {5,32,33}
                if not transient:raise
                if attempt==len(delays):raise AtomicWriteError(error.errno,'Atomic file replacement failed after bounded retries: '+str(error),str(path)) from error
                time.sleep(delays[attempt])
    finally:
        try:
            if created:
                try:os.unlink(temporary,dir_fd=directory)
                except FileNotFoundError:pass
        finally:os.close(directory)


def atomic_bytes(path,value):
    """Publish a complete artifact on one pinned parent; never copy on EXDEV."""
    _atomic_file(path,lambda stream:stream.write(value),mode=0o644)


def atomic_json(path,value):
    # Serialize before creating the temporary file; private state remains 0600.
    raw=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
    _atomic_file(path,lambda stream:stream.write(raw),mode=0o600)


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
