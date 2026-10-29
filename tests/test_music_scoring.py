"""Protected music scoring stays independent of retired experiment runners."""
import json
from pathlib import Path
import pytest
from goalagent.contracts import success_gate, atomic_json

SPEC = json.loads(Path('goals/music-research-v2.json').read_text())


def test_perfect_pilot_is_not_full_goal_success():
    result={'samples':7,'parseable':7,'melody':{'error_rate':0},'chords':{'error_rate':0},'transposition_failures':0,'chord_timing_audited':True,'musician_accepted':True}
    assert success_gate(result,SPEC) is False


def test_perfect_notes_with_unaudited_timing_is_not_success():
    result={'samples':32,'parseable':32,'melody':{'error_rate':0},'chords':{'error_rate':0},'transposition_failures':0,'chord_timing_audited':False,'musician_accepted':True}
    assert success_gate(result,SPEC) is False


def test_prediction_tamper_is_rejected_before_scoring(tmp_path):
    from goalagent.music import MusicScorer
    from scorebench.run import ROOT
    tools=MusicScorer(tmp_path,SPEC)
    eid='exp-123456abcdef';folder=tmp_path/'experiments'/eid;folder.mkdir(parents=True)
    atomic_json(folder/'receipt.json',{'id':eid})
    sample=folder/'sample-001';sample.mkdir();pred=sample/'prediction.krn';pred.write_text('tampered')
    # Absolute paths are accepted by pathlib composition for this isolated test fixture.
    atomic_json(sample/'trace.json',{'output':str(pred),'output_sha256':'incorrect'})
    with pytest.raises(ValueError,match='Prediction integrity'):tools.evaluate(eid,lambda:100)


def test_transposition_checker_uses_pitch_classes_for_slash_bass(tmp_path,monkeypatch):
    import goalagent.music as music
    monkeypatch.setattr(music,'ROOT',tmp_path)
    path=tmp_path/'prediction.krn'
    path.write_text('**kern\t**mxhm\n*clefG2\t*\n*k[]\t*\n4b\tG:maj/B\n*-\t*-\n')
    target=tmp_path/music.transpose_check(path)
    assert 'A:maj/C#' in target.read_text()
    assert '4cc#' in target.read_text()


def test_transposition_checker_handles_b_flat_root_wrap(tmp_path,monkeypatch):
    import goalagent.music as music
    monkeypatch.setattr(music,'ROOT',tmp_path)
    path=tmp_path/'prediction.krn'
    path.write_text('**kern\t**mxhm\n*clefG2\t*\n*k[]\t*\n4b-\tBb:maj\n*-\t*-\n')
    target=tmp_path/music.transpose_check(path)
    assert 'C:maj' in target.read_text()
