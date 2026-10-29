"""Trusted CLI inputs, intentionally absent from model tool registries."""
import json
from pathlib import Path
from .sandbox import read_file
from .artifacts import MAX_FILE


def apply_controls(team, *, external_event=None, resume_stopped=None, retry_action=None, retry_reason=None):
    if retry_action and (not retry_reason or resume_stopped):
        raise ValueError('Execution retry needs a reason and cannot also resume a stopped run')
    if retry_reason and not retry_action:
        raise ValueError('Retry reason needs an assignment ID')
    if external_event:
        path=Path(external_event).resolve()
        event=json.loads(path.read_text())
        event['files']={name:read_file((path.parent/source).resolve().parent,
            (path.parent/source).resolve().name,limit=MAX_FILE) for name,source in event['files'].items()}
        team.accept_external(**event)
    if retry_action:team.retry_uncertain_action(retry_action,retry_reason)
    if resume_stopped:team.reopen_stopped(resume_stopped)
