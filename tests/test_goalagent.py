"""Behavior tests use scripted models; live results are reported separately."""
import copy,json
from pathlib import Path
import pytest
from goalagent.contracts import validate_decision,success_gate,atomic_json
from goalagent.runner import AgentRunner
from goalagent.music import recover_text_harmony
from scorebench.metrics import xml_chords,chord_from_label

SPEC=json.loads(Path('goals/music.json').read_text())
def decision(tool,arg='',ids=None):
    return {'tool':tool,'argument':arg,'why':'Test an observed failure','hypothesis':'An intervention changes the measured result','expected_observation':'A lower error count on the fixed inputs','evidence_ids':ids or ['goal']}

class Scripted:
    model='test-double'
    def __init__(self,items):self.items=iter(items);self.calls=0
    def call(self,*a,**k):self.calls+=1;return next(self.items),{'test_double':True}

class Domain:
    def __init__(self):self.executions=0
    def assert_originals(self):pass
    def execute(self,tool,arg,*unused):
        self.executions+=1
        return {'id':'dataset','count':32}


def test_model_cannot_cite_unseen_evidence():
    with pytest.raises(ValueError,match='evidence'):validate_decision(decision('finish',ids=['invented']),['goal'])


def test_model_cannot_request_arbitrary_shell():
    with pytest.raises(ValueError,match='Unregistered'):validate_decision(decision('shell','rm -rf /'),['goal'])


def test_extra_output_fields_cannot_override_acceptance():
    d=decision('finish');d['goal_met']=True
    with pytest.raises(ValueError):validate_decision(d,['goal'])


def test_perfect_pilot_is_not_full_goal_success():
    result={'samples':7,'parseable':7,'melody':{'error_rate':0},'chords':{'error_rate':0},'transposition_failures':0,'chord_timing_audited':True,'musician_accepted':True}
    assert success_gate(result,SPEC) is False


def test_perfect_notes_with_unaudited_timing_is_not_success():
    result={'samples':32,'parseable':32,'melody':{'error_rate':0},'chords':{'error_rate':0},'transposition_failures':0,'chord_timing_audited':False,'musician_accepted':True}
    assert success_gate(result,SPEC) is False


def test_false_completion_is_not_accepted(tmp_path):
    p=Scripted([decision('finish')]);r=AgentRunner(SPEC,tmp_path,p,Domain());r.run()
    assert r.state['status']=='goal_unmet' and r.state['goal_met'] is False


def test_finished_resume_makes_no_model_calls(tmp_path):
    r=AgentRunner(SPEC,tmp_path,Scripted([decision('finish')]),Domain());r.run()
    second=Scripted([]);resumed=AgentRunner(SPEC,tmp_path,second,Domain());resumed.run()
    assert second.calls==0


def test_resume_executes_pending_decision_without_replanning(tmp_path):
    domain=Domain();p=Scripted([]);r=AgentRunner(SPEC,tmp_path,p,domain)
    r.state['steps']=1;r.state['pending']={'step':1,'decision':decision('inspect_dataset')};r.save()
    resumed=AgentRunner(SPEC,tmp_path,p,domain);resumed.run(stop_after=1)
    assert p.calls==0 and domain.executions==1
    assert resumed.state['pending'] is None and len(resumed.state['history'])==1


def test_resume_refuses_changed_goal_or_budget(tmp_path):
    AgentRunner(SPEC,tmp_path,Scripted([]),Domain())
    changed=copy.deepcopy(SPEC);changed['budget']['max_steps']+=1
    with pytest.raises(ValueError,match='changed'):AgentRunner(changed,tmp_path,Scripted([]),Domain())


def test_model_call_cap_is_enforced(tmp_path):
    spec=copy.deepcopy(SPEC);spec['budget']['max_model_calls']=1
    p=Scripted([decision('inspect_dataset')]);r=AgentRunner(spec,tmp_path,p,Domain());r.run()
    assert p.calls==1 and r.state['status']=='budget_exhausted' and not r.state['goal_met']


def test_experiment_needs_observed_baseline_and_source(tmp_path):
    r=AgentRunner(SPEC,tmp_path,Scripted([]),Domain())
    with pytest.raises(ValueError,match='Read dataset'):r.validate_action(decision('run_experiment','{"kind":"vision_kern"}'))


def test_text_adapter_rejects_lyrics_and_keeps_slash_bass():
    xml='<score-partwise><part><measure number="1"><direction><direction-type><words>Glory</words></direction-type></direction><direction><direction-type><words>G/B</words></direction-type></direction></measure></part></score-partwise>'
    out,added=recover_text_harmony(xml)
    assert len(added)==1 and xml_chords(out)==[chord_from_label('G:maj/B')]


def test_text_adapter_preserves_notes_exactly():
    import xml.etree.ElementTree as ET
    xml='<score-partwise><part><measure><note><pitch><step>E</step><octave>4</octave></pitch><duration>2</duration></note><direction><direction-type><words>Dm7</words></direction-type></direction></measure></part></score-partwise>'
    out,_=recover_text_harmony(xml)
    assert ET.tostring(ET.fromstring(xml).find('.//note'))==ET.tostring(ET.fromstring(out).find('.//note'))


def test_unsupported_domain_is_explicit(tmp_path):
    spec=copy.deepcopy(SPEC);spec['domain']='travel'
    with pytest.raises(ValueError,match='domain adapter'):AgentRunner(spec,tmp_path,Scripted([]))


def test_failed_tool_is_an_observation_not_success(tmp_path):
    class Broken(Domain):
        def execute(self,*a):raise RuntimeError('Injected recognizer failure')
    p=Scripted([decision('inspect_dataset'),decision('finish')]);r=AgentRunner(SPEC,tmp_path,p,Broken());r.run()
    assert r.state['history'][0]['observation']['error']=='RuntimeError'
    assert r.state['status']=='goal_unmet' and not r.state['goal_met']


def test_time_budget_stops_before_model_call(tmp_path):
    spec=copy.deepcopy(SPEC);spec['budget']['max_active_seconds']=0
    p=Scripted([]);r=AgentRunner(spec,tmp_path,p,Domain());r.run()
    assert p.calls==0 and r.state['status']=='budget_exhausted'


def test_prediction_tamper_is_rejected_before_scoring(tmp_path):
    from goalagent.music import MusicTools
    from scorebench.run import ROOT
    tools=MusicTools(tmp_path,SPEC)
    eid='exp-123456abcdef';folder=tmp_path/'experiments'/eid;folder.mkdir(parents=True)
    atomic_json(folder/'receipt.json',{'id':eid})
    sample=folder/'sample-001';sample.mkdir();pred=sample/'prediction.krn';pred.write_text('tampered')
    # Absolute paths are accepted by pathlib composition for this isolated test fixture.
    atomic_json(sample/'trace.json',{'output':str(pred),'output_sha256':'incorrect'})
    with pytest.raises(ValueError,match='Prediction integrity'):tools.evaluate(eid,lambda:100)


def test_completed_experiment_receipt_prevents_reexecution(tmp_path):
    from goalagent.music import MusicTools
    tools=MusicTools(tmp_path,SPEC);cfg={'kind':'vision_kern'};eid=tools.experiment_id(cfg)
    receipt={'id':eid,'samples':7,'statuses':{'ok':7}}
    atomic_json(tmp_path/'experiments'/eid/'receipt.json',receipt)
    def forbidden():raise AssertionError('A cached experiment must not spend a model call')
    assert tools.run_experiment(cfg,forbidden,lambda:100)==receipt


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


def test_recheck_fork_preserves_original_and_redirects_only_artifacts(tmp_path,monkeypatch):
    import goalagent.fork as forking
    monkeypatch.setattr(forking,'ROOT',tmp_path)
    source=tmp_path/'old';source.mkdir()
    state={'status':'goal_unmet','known_evidence':['goal'],'goal_met':False,'best_experiment':'exp-123456abcdef','evaluations':{'old':1},'pending':None,'steps':9,'model_calls':16,'history':[{'observation':{'id':'old'}}]}
    atomic_json(source/'state.json',state)
    out=source/'experiments'/'exp-123456abcdef'/'sample-001';out.mkdir(parents=True)
    (out/'prediction.krn').write_text('original prediction')
    atomic_json(out/'trace.json',{'output':'old/experiments/exp-123456abcdef/sample-001/prediction.krn','output_sha256':'unchanged'})
    atomic_json(out.parent/'evaluation.json',{'old_result':True})
    (out/'prompt.txt').write_text('old/path must remain in original model context')
    dest=forking.fork_for_recheck(source,tmp_path/'new',{'id':'correction'})
    assert json.loads((source/'state.json').read_text())==state
    new=json.loads((dest/'state.json').read_text())
    assert new['steps']==9 and new['model_calls']==16 and new['evaluations']=={}
    new_out=dest/'experiments'/'exp-123456abcdef'/'sample-001'
    assert json.loads((new_out/'trace.json').read_text())['output'].startswith('new/')
    assert (new_out/'prompt.txt').read_text()==(out/'prompt.txt').read_text()
    assert (new_out.parent/'prior-evaluation.json').exists()
