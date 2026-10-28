"""Host-owned input contracts. Predictions are not reference labels."""
import hashlib
from pathlib import Path
import shutil
from .contracts import digest
from .sandbox import read_file
from scorebench.run import ROOT


def baseline_inventory(selected, engine='audiveris-enlarged'):
    if engine not in {'audiveris-enlarged', 'audiveris-raw', 'transcoda-greedy'}:
        raise ValueError('Unknown baseline prediction set')
    records = []
    for index, _ in selected:
        folder = ROOT / 'runs/first-benchmark' / engine / f'sample-{index:03}'
        # Only prediction artifacts; never search the reference directory.
        for filename in ('converted.krn', 'prediction.krn', 'prediction.musicxml'):
            path = folder / filename
            if path.is_file():
                break
        else:
            # Raw exports preserve OCR words that may not survive kern conversion.
            choices = sorted(folder.rglob('*.mxl')) + sorted(folder.rglob('*.musicxml'))
            path = choices[0] if choices else None
        if path is None:
            raise ValueError(f'Missing required baseline prediction: {engine}/sample-{index:03}')
        raw = read_file(folder, str(path.relative_to(folder)), 16_000_000)
        if not raw.strip():
            raise ValueError(f'Empty required baseline prediction: sample-{index:03}')
        records.append({'sample': index, 'source': str(path.relative_to(ROOT)),
                        'path': f'baselines/{engine}/sample-{index:03}{path.suffix}',
                        'sha256': hashlib.sha256(raw).hexdigest()})
        # Include the original model export when available, explicitly provenance-tagged.
        exports = sorted(folder.rglob('*.mxl')) + sorted(folder.rglob('*.musicxml'))
        if exports and exports[0] != path:
            p = exports[0]; raw = read_file(folder, str(p.relative_to(folder)), 16_000_000)
            records.append({'sample': index, 'source': str(p.relative_to(ROOT)),
                            'path': f'baselines/{engine}/sample-{index:03}-raw{p.suffix}',
                            'sha256': hashlib.sha256(raw).hexdigest()})
    return records


def resolve_inputs(required, selected):
    if not isinstance(required, list) or len(required) != len(set(required)):
        raise ValueError('required_inputs must be a unique list of artifact IDs')
    records = []
    for name in required:
        if not isinstance(name, str) or not name.startswith('baseline:'):
            raise ValueError('Only catalogued baseline prediction artifacts can be requested')
        records += baseline_inventory(selected, name.split(':', 1)[1])
    return {'required': required, 'files': records, 'hash': digest(records),
            'label_access': 'none; supplied labels remain in the protected evaluator'}


def deliver_inputs(contract, workspace):
    for item in contract['files']:
        source = ROOT / item['source']
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Required prediction artifact changed before dispatch')
        dest = Path(workspace) / item['path']; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)


def verify_inputs(contract, workspace):
    for item in contract['files']:
        raw = read_file(workspace, item['path'], 16_000_000)
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Read-only baseline prediction changed')
