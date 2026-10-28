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
    assert result['melody']['reference_count']>0
    assert result['chord_timing_audited'] is False
    assert all('id' not in row for row in result['per_sample'])
    missing=evaluator({},{})
    assert missing['parseable']==0 and missing['accepted'] is False
