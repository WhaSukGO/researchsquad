"""Catalogued baseline predictions; supplied reference labels stay separate."""
import hashlib
from .sandbox import read_file
from scorebench.run import ROOT

BASELINE_ROOT = ROOT / "research/baselines/first-benchmark"


def baseline_inventory(selected, engine='audiveris-enlarged'):
    if engine not in {'audiveris-enlarged', 'audiveris-raw', 'transcoda-greedy'}:
        raise ValueError('Unknown baseline prediction set')
    records = []
    for index, _ in selected:
        folder = BASELINE_ROOT / engine / f'sample-{index:03}'
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
