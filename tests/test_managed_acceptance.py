import copy
import json
from pathlib import Path

from goalagent.music_team import music_evaluator, task_inputs
from goalagent.team import ROOT
from goalagent.team_evaluators import Evaluator
from test_managed import make, spec


def test_full_music_manifest_handoff_has_32_images_and_no_reference_paths(tmp_path):
    settings=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    settings['budget']['experiment_sample_scope']='all'
    _,domain=music_evaluator(tmp_path,settings)
    assets,inputs=task_inputs(domain)
    assert len(json.loads(inputs['samples.json']))==32
    assert len([p for p in assets if p.startswith('images/')])==32
    references={str(ROOT/s['reference']) for _,s in domain.selected()}
    assert not references.intersection(assets.values())
    assert all('reference' not in name for name in assets)
    assert '32 supplied development excerpts' in inputs['brief.txt']


def test_trusted_music_finalization_cannot_replace_bad_measurements(tmp_path):
    settings=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    evaluator,_=music_evaluator(tmp_path,settings)
    measured={'samples':32,'parseable':32,'melody':{'error_rate':0.1},'chords':{'error_rate':0},
              'transposition_failures':0,'chord_timing_audited':False,'musician_accepted':False,'accepted':False}
    external={'chord-timing-audit':{'verdict':'PASS'},'musician-review':{'verdict':'PASS'}}
    assert evaluator.finalize(copy.deepcopy(measured),external)['accepted'] is False
    measured['melody']['error_rate']=0
    assert evaluator.finalize(copy.deepcopy(measured),external)['accepted'] is True
    assert evaluator.finalize(copy.deepcopy(measured),{'musician-review':{'verdict':'PASS'}})['accepted'] is False
    measured['samples']=7;measured['parseable']=7
    assert evaluator.finalize(copy.deepcopy(measured),external)['accepted'] is False


def test_full_missing_music_batch_retains_all_reference_denominators(tmp_path):
    settings=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    settings['budget']['experiment_sample_scope']='all'
    evaluator,_=music_evaluator(tmp_path,settings)
    result=evaluator({}, {})
    assert result['samples']==32 and result['parseable']==0
    assert len(result['per_sample'])==32
    assert result['melody']['reference_count']>0 and result['chords']['reference_count']>0
    assert result['melody']['errors']==result['melody']['reference_count']
    assert result['chords']['errors']==result['chords']['reference_count']
    assert result['accepted'] is False


def test_external_acceptance_is_candidate_bound_immutable_and_revocable(tmp_path,monkeypatch):
    from test_workflow import make as make_legacy, stage, candidate, decide
    from test_team import instance, action
    team=make_legacy(tmp_path,[stage('FINAL','external')])
    def finalize(measured,external):
        return {**measured,'accepted':measured['numeric_ok'] and
                external.get('FINAL-gate',{}).get('verdict')=='PASS'}
    monkeypatch.setitem(team.evaluators,'sorted_numbers',Evaluator('deferred-fixture-v1',
        lambda *_:{'accepted':False,'numeric_ok':True},finalize))
    lead=instance(team);first=candidate(team,lead)
    base=lead.execute(action('evaluate',first),100)
    waiting=decide(team,lead,'WAIT_EXTERNAL',first,owner='musician',resume_when='Review this frozen candidate')
    team.accept_external(request_id=waiting['decision_id'],event_id='human-pass',
        summary='Original human review',files={'review.txt':b'Actual fixture approval'},
        gate_verdicts={'FINAL-gate':'PASS'})
    accepted=lead.execute(action('evaluate',first),100)
    assert accepted['measurement']['accepted'] and team.state['goal_met']
    assert team.evidence_record(base['evidence_id'])['measurement']['accepted'] is False
    lead.state['steps']+=1;second=candidate(team,lead)
    assert not lead.execute(action('evaluate',second),100)['measurement']['accepted']
    waiting=decide(team,lead,'WAIT_EXTERNAL',first,owner='musician',resume_when='Inspect newly reported defect')
    team.accept_external(request_id=waiting['decision_id'],event_id='human-revoked',
        summary='Human review withdrawn after inspecting a defect',files={'review.txt':b'Approval withdrawn'},
        gate_verdicts={'FINAL-gate':'FAIL'})
    assert first not in team.state['acceptances'] and not team.state['goal_met']
    rejected=lead.execute(action('evaluate',first),100)
    assert not rejected['measurement']['accepted']
    assert team.evidence_record(accepted['evidence_id'])['measurement']['accepted']
    assert rejected['evidence_id']!=accepted['evidence_id']
