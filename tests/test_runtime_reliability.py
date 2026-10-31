"""Fault and boundary regressions; scripted choices are not research evidence."""
import copy
import errno
import json
import os
from pathlib import Path

import pytest

from goalagent.contracts import atomic_json,AtomicWriteError
from goalagent.context_state import observed_work
from goalagent.team_evaluators import Evaluator
from test_team import make,instance,action
from test_managed import make as managed,spec


@pytest.mark.parametrize('kind',['temporary','permanent','disk_full','serialization'])
def test_atomic_replace_preserves_last_good_state_and_cleans_temps(tmp_path,monkeypatch,kind):
    target=tmp_path/'state.json';atomic_json(target,{'old':True})
    replace=os.replace;calls=[]
    monkeypatch.setattr('goalagent.contracts.time.sleep',lambda _:None)
    def blocked(src,dst,**kwargs):
        calls.append(1)
        if kind=='temporary' and len(calls)>2:return replace(src,dst,**kwargs)
        raise OSError(errno.ENOSPC if kind=='disk_full' else errno.EACCES,'injected replace failure')
    monkeypatch.setattr('goalagent.contracts.os.replace',blocked)
    if kind=='temporary':
        atomic_json(target,{'new':True});assert json.loads(target.read_text())=={'new':True};assert len(calls)==3
    else:
        with pytest.raises(TypeError if kind=='serialization' else OSError):atomic_json(target,{'new':object() if kind=='serialization' else True})
        assert json.loads(target.read_text())=={'old':True}
        assert len(calls)==({'permanent':6,'disk_full':1,'serialization':0}[kind])
    assert list(tmp_path.glob('*.tmp'))==[] and list(tmp_path.glob('.*.tmp'))==[]


@pytest.mark.parametrize('with_dependencies',[False,True])
def test_pre_model_storage_failure_resumes_same_review_without_repeating_read(tmp_path,with_dependencies):
    def hook(role,a,c):
        if role=='critic' and not c['observed_work']['read_files']:
            if with_dependencies:
                dep=team.managed.board.add(key='storage-prerequisite',owner='operator',objective='Completed prerequisite',
                    acceptance_check='Fixture prerequisite complete',stage='R0',kind='support')
                team.managed.board.set_status(dep,'DONE')
                team.managed.board.depend(a['work_id'],dep['work_id'])
            return action('read_file',{'path':'inputs/parent/result.json'})
    team,calls=managed(tmp_path,workflow_spec=spec(reviewers=('auditor',)),hook=hook)
    save=team.save;last_calls=[team.state['calls']];tripped=[False]
    def storage_fault():
        charging=team.state['calls']>last_calls[0]
        if charging and not tripped[0]:
            for aid,entry in team.state['assignments'].items():
                p=team.folder/'agents'/aid/'worker-state.json'
                if entry['agent']=='critic' and p.exists():
                    w=json.loads(p.read_text())
                    if w['history'] and w['history'][-1]['tool']=='read_file':
                        tripped[0]=True
                        raise AtomicWriteError(errno.EACCES,'Injected exhausted replace retries')
        result=save();last_calls[0]=team.state['calls'];return result
    team.save=storage_fault
    assert team.run()['status']=='waiting_external'
    reviewer=next(j for j in team.managed.board.jobs.values() if j['kind']=='review')
    aid=reviewer['assignment_id'];assert len(reviewer['attempts'])==1
    worker=json.loads((team.folder/'agents'/aid/'worker-state.json').read_text())
    assert worker['steps']==1 and worker['status']=='storage_blocked'
    assert team.state['calls']==len(calls) # Failed reservation was rolled back.
    request=team.state['workflow']['pending_external']['request_id']
    team.accept_external(request_id=request,event_id='storage-restored',summary='Filesystem is writable again',files={'readiness.txt':b'operator check'})
    assert team.run()['status']=='completed'
    assert reviewer['assignment_id']==aid and reviewer['attempts']==[aid]
    worker=json.loads((team.folder/'agents'/aid/'worker-state.json').read_text())
    assert sum(h['tool']=='read_file' for h in worker['history'])==1
    assert team.state['calls']==len(calls)


def test_full_read_reaches_model_context_and_coverage_survives_old_history(tmp_path):
    team=make(tmp_path);a=instance(team,'researcher')
    body='A'*7900+'END-OF-WINDOW';(a.workspace/'paper.txt').write_text(body)
    result=a.execute(action('read_file',{'path':'paper.txt','limit':8000}),1)
    row={'step':1,'tool':'read_file','argument':json.dumps({'path':'paper.txt','limit':8000}),
         'why':'x'*1000,'observation':result,'evidence_id':'read-1'}
    a.state['history']=[row]
    assert len(json.dumps(row))>8000
    assert a.recent_context()[0]['observation']['text']==body
    assert result['returned_bytes']==len(body) and result['next_offset'] is None and result['eof']
    a.state['history'] += [{'step':i,'tool':'list_files','observation':{}} for i in range(2,10)]
    assert len(a.recent_context())==6
    ledger=observed_work(a.state['history']);assert ledger['read_files'][0]['windows'][0]['evidence_id']=='read-1'
    a.state['history'].append({'tool':'write_file','observation':{'written':'paper.txt'}})
    assert observed_work(a.state['history'])['read_files']==[]


def test_checkpoint_checks_are_evidence_bound_and_retained(tmp_path):
    team=make(tmp_path);a=instance(team,'researcher')
    a.assignment['task_id']='test'
    a.validate_checks=lambda checks:team.validate_checks(checks,a.assignment)
    record={'step':1,'tool':'read_file','argument':'{}','observation':{'text':'actual'}}
    eid=team.action_evidence('test',record,a.folder)
    base={'summary':'read verified','next_test':'Inspect unresolved check','files':[],
          'checks':[{'id':'method','description':'Method inspected','status':'passed','evidence_ids':[eid]}]}
    a.execute(action('checkpoint',base),1)
    a.execute(action('checkpoint',{'summary':'continue','next_test':'Inspect code','files':[]}),1)
    assert a.state['review_checklist']['method']['evidence_ids']==[eid]
    wrong=copy.deepcopy(base);wrong['checks'][0]['evidence_ids']=['invented']
    with pytest.raises(ValueError):a.execute(action('checkpoint',wrong),1)


def test_delivered_objection_path_resolves_without_widening_targets(tmp_path):
    team=make(tmp_path);aid='reviewer'
    art=team.register_artifact(b'report',owner='owner',path='report.md')
    assignment={'task_id':aid,'inputs':{'report.md':{**art,'path':'inputs/report.md'}}}
    obj={'target_id':'inputs/report.md: Results','category':'EXPERIENCE','severity':'MINOR','statement':'Ambiguous units',
         'evidence_ids':[],'resolution_test':'State total steps'}
    report={'status':'DONE','summary':'Scoped review','files':[],'objections':[obj]}
    resolved=team.validate_assignment_report(report,assignment)
    assert obj['target_id']==art['artifact_id'] and resolved[0]['supplied'].endswith(': Results')
    report['objections'][0]['target_id']='inputs/secret.txt: Results'
    with pytest.raises(ValueError,match='report_context'):team.validate_assignment_report(report,assignment)
    report['objections']=[];report['files']=['inputs/report.md']
    with pytest.raises(ValueError,match='already-preserved'):team.validate_assignment_report(report,assignment)


def test_image_handoff_without_reader_capability_fails_before_model_call(tmp_path):
    from test_team import Scripted
    team=make(tmp_path,provider_factory=lambda _:Scripted([]));lead=instance(team)
    team.definitions['report_reader']['tools'].remove('view_image')
    (lead.workspace/'figure.png').write_bytes(b'\x89PNG\r\n')
    request={'agent':'report_reader','objective':'Inspect delivered diagram','success_criteria':'Describe diagram',
             'inputs':{'figure.png':'figure.png'}}
    with pytest.raises(ValueError,match='Input capability mismatch'):lead.execute(action('delegate',request),1)
    assert team.state['calls']==0 and not team.state['assignments']
    with pytest.raises(ValueError,match='view_image'):lead.execute(action('read_file',{'path':'figure.png'}),1)


def test_mechanical_preflight_precedes_review_and_does_not_accept_project(tmp_path):
    seen=[];holder={}
    def preflight(snapshot,task):
        t=holder['team'];seen.append(not t.state['goal_met'])
        return {'accepted':True,'scope':'Receipt structure only'}
    from goalagent.team_evaluators import sorted_numbers
    team,calls=managed(tmp_path,workflow_spec=spec(reviewers=('auditor',)),
        evaluators={'sorted_numbers':Evaluator('fixture-with-preflight',sorted_numbers,preflight=preflight)})
    holder['team']=team
    assert team.run()['status']=='completed' and seen==[True]
    reviewer=next(a for role,a,c in calls if role=='critic')
    assert reviewer['mechanical_checks']['measurement']['scope']=='Receipt structure only'
    events=team.state['events']
    pre=next(e['sequence'] for e in events if e['kind']=='submission_preflight')
    dispatch=next(e['sequence'] for e in events if e['kind']=='assignment' and e['data']['agent']=='critic')
    assert pre<dispatch


def test_own_review_event_supports_document_claim_but_not_peer_or_empirical_claim(tmp_path):
    from goalagent.claim_checks import validate_claims
    team=make(tmp_path)
    row={'reviewer_assignment':'reader','candidate':'candidate','verdict':'PASS'}
    team.record('review-own',row)
    team.state['workflow']['reviews'].append({**row,'evidence_id':'review-own'})
    report={'claims':[{'scope':'document','statement':'My review recorded PASS','epistemic_status':'observed',
                     'evidence_ids':['review-own'],'limitations':'Not experimental validation'}]}
    assignment={'task_id':'reader','review_of':'candidate','inputs':{}}
    validate_claims(team,report,assignment)
    with pytest.raises(ValueError):validate_claims(team,report,{**assignment,'task_id':'other-reader'})
    report['claims'][0]['scope']='empirical'
    with pytest.raises(ValueError):validate_claims(team,report,assignment)


def test_failed_mechanical_preflight_reworks_before_any_semantic_review(tmp_path):
    checks=[]
    def preflight(snapshot,task):
        checks.append(1)
        return {'accepted':len(checks)>1,'reason':'Injected missing source receipt on first delivery'}
    from goalagent.team_evaluators import sorted_numbers
    team,calls=managed(tmp_path,workflow_spec=spec(reviewers=('auditor',)),
        evaluators={'sorted_numbers':Evaluator('reject-first-fixture',sorted_numbers,preflight=preflight)})
    assert team.run()['status']=='completed'
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    assert len(owner['attempts'])==2
    assert all(a.get('review_of')!=owner['attempts'][0] for role,a,c in calls if role=='critic')
    assert len(checks)==2


def test_active_context_clears_previous_stage_candidate_and_gates(tmp_path):
    from test_managed import spec
    settings=spec(partial=True)
    team,calls=managed(tmp_path,workflow_spec=settings)
    state=team.state['workflow'];state.update(stage='R1',candidate='old-owner',candidate_revision='old-revision',
                                            gates=[{'gate_id':'result-accepted','candidate':'old-owner','status':'PASS'}])
    team.managed.after_decision('ADVANCE',{'stage':'R0','target_stage':'R1'})
    context=team.managed.context({'depth':0})
    assert state['candidate'] is None and state['candidate_revision'] is None
    assert all(g['candidate'] is None for g in context['workflow']['gates'])
    assert all(g['gate_id']!='result-accepted' for g in context['workflow']['gates'])
