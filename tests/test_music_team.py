import json
from goalagent.music_team import music_evaluator,task_inputs
from goalagent.team import ROOT
from goalagent.inputs import baseline_inventory


def test_music_team_delivers_images_and_predictions_not_labels(tmp_path):
    spec=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    _,domain=music_evaluator(tmp_path,spec)
    assets,inputs=task_inputs(domain)
    labels={str(ROOT/s['reference']) for _,s in domain.selected()}
    assert len(assets)==21 and not labels.intersection(assets.values())
    assert len(json.loads(inputs['samples.json']))==7


def test_music_adapter_reuses_protected_metrics_and_completion_gate(tmp_path):
    spec=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    evaluator,domain=music_evaluator(tmp_path,spec)
    snapshot={f"sample-{r['sample']:03}.krn":(ROOT/r['source']).read_text()
              for r in baseline_inventory(domain.selected()) if r['path'].endswith('.krn')}
    result=evaluator(snapshot,{})
    assert result['samples']==7 and result['accepted'] is False
    assert result['parseable']==3
    assert result['melody']['errors']==101 and result['melody']['reference_count']==130
    assert result['chords']['errors']==38 and result['chords']['reference_count']==38
    assert result['chord_timing_audited'] is False
    assert all('id' not in row for row in result['per_sample'])
    missing=evaluator({},{})
    assert missing['parseable']==0 and missing['accepted'] is False


def test_archived_baselines_match_provenance_without_run_outputs():
    import hashlib
    from goalagent.inputs import BASELINE_ROOT
    provenance = json.loads((BASELINE_ROOT / 'provenance.json').read_text())
    assert provenance['source_revision'] == 'caad09f98dd985ae8e081aa7689280870ad08a83'
    for record in provenance['files']:
        raw = (BASELINE_ROOT / record['path']).read_bytes()
        assert len(raw) == record['bytes']
        assert hashlib.sha256(raw).hexdigest() == record['sha256']


def test_missing_baseline_does_not_search_reference_labels(tmp_path, monkeypatch):
    import pytest
    import goalagent.inputs as inputs
    monkeypatch.setattr(inputs, 'BASELINE_ROOT', tmp_path)
    with pytest.raises(ValueError, match='Missing required baseline prediction'):
        inputs.baseline_inventory([(1, {'reference': 'research/data/supplied-label.krn'})])
