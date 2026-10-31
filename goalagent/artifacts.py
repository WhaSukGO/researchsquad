"""Host-owned, content-addressed artifacts and bounded workspace checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .contracts import atomic_json, atomic_bytes, digest
from .sandbox import read_file, workspace_path

MAX_FILE = 16_000_000
MAX_BUNDLE = 64_000_000
MAX_FILES = 256
EXCLUDED = {'inputs', 'baselines', 'tmp', 'vendor', '.venv', 'venv', '.git', '__pycache__', '.cache'}


class ArtifactStore:
    def __init__(self, folder):
        self.folder = Path(folder)

    def register(self, raw, *, owner, path, depends_on=()):
        if len(raw) > MAX_FILE:
            raise ValueError('Artifact exceeds 16 MB')
        workspace_path(Path('/artifact-path-check'), path)
        metadata = {'owner': owner, 'path': path, 'sha256': hashlib.sha256(raw).hexdigest(),
                    'bytes': len(raw), 'depends_on': sorted(set(depends_on))}
        artifact_id = 'artifact-' + digest(metadata)
        metadata['artifact_id'] = artifact_id
        destination = self.folder / artifact_id
        destination.mkdir(parents=True, exist_ok=True)
        content = destination / 'content'
        if content.exists():
            if read_file(destination, 'content', limit=MAX_FILE) != raw:
                raise ValueError('Registered artifact changed')
        else:
            atomic_bytes(content, raw)
        record = destination / 'record.json'
        if record.exists() and json.loads(record.read_text()) != metadata:
            raise ValueError('Artifact metadata changed')
        atomic_json(record, metadata)
        return metadata

    def read(self, metadata):
        artifact_id = metadata['artifact_id']
        if artifact_id != 'artifact-' + digest({k: v for k, v in metadata.items() if k != 'artifact_id'}):
            raise ValueError('Artifact metadata changed')
        folder = workspace_path(self.folder, artifact_id)
        raw = read_file(folder, 'content', limit=MAX_FILE)
        if len(raw) != metadata['bytes'] or hashlib.sha256(raw).hexdigest() != metadata['sha256']:
            raise ValueError('Artifact content changed')
        return raw


def capture_workspace(folder, workspace, *, files=None, include=()):
    """Capture shell-created files too. Report omissions; never silently claim a full backup.

    Explicit submission lists fail closed. Automatic checkpoints skip caches/inputs and
    unsafe or oversized files, keeping an omission manifest for the coordinator.
    """
    store = ArtifactStore(Path(folder) / 'artifacts')
    records, omitted = [], []
    total = 0
    if files is None:
        candidates = list(include)
        for directory, dirs, names in os.walk(workspace, followlinks=False):
            for name in dirs:
                if (Path(directory) / name).is_symlink():
                    omitted.append({'path':str((Path(directory) / name).relative_to(workspace)), 'reason':'Symlink directory omitted'})
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(directory) / d).is_symlink())
            for name in sorted(names):
                relative = str((Path(directory) / name).relative_to(workspace))
                if relative not in candidates: candidates.append(relative)
                if len(candidates) >= 2048:
                    omitted.append({'path': '.', 'reason': 'Scan limit reached; register important files explicitly'})
                    break
            if len(candidates) >= 2048:
                break
    else:
        if not isinstance(files, list) or len(files) > MAX_FILES or any(not isinstance(p, str) for p in files) or len(files) != len(set(files)):
            raise ValueError('Expected up to 256 distinct file paths')
        candidates = files
    for relative in candidates:
        try:
            path = workspace_path(workspace, relative)
            if path.relative_to(workspace).parts[0] in {'inputs', 'baselines'}:
                raise ValueError('Submit authored files, not read-only inputs')
            raw = read_file(workspace, relative, limit=MAX_FILE)
            if len(records) >= MAX_FILES or total + len(raw) > MAX_BUNDLE:
                raise ValueError('Checkpoint exceeds 256 files or 64 MB; register important files explicitly')
            records.append(store.register(raw, owner='workspace', path=relative))
            total += len(raw)
        except (OSError, ValueError) as error:
            if files is not None:
                raise ValueError(f'Cannot preserve {relative}: {error}') from error
            omitted.append({'path': relative, 'reason': str(error)[:200]})
    manifest = {'artifacts': records, 'omitted': omitted, 'bytes': total}
    manifest['snapshot_id'] = 'snapshot-' + digest(manifest)
    atomic_json(Path(folder) / 'snapshots' / (manifest['snapshot_id'] + '.json'), manifest)
    return manifest


def text_snapshot(folder, manifest):
    """Compatibility view for existing protected text evaluators; binary artifacts persist separately."""
    result = {}
    store = ArtifactStore(Path(folder) / 'artifacts')
    for record in manifest['artifacts']:
        raw = store.read(record)
        try:
            result[record['path']] = raw.decode('utf-8')
        except UnicodeDecodeError:
            continue
    return result
