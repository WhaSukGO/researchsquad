"""Host policy fixtures use scripted model decisions, never claim research quality."""
import copy
import json
from pathlib import Path

import pytest

from goalagent.team import Team
from goalagent.team_evaluators import EVALUATORS
from goalagent import workflow
from test_team import FakeSandbox, action


BINDINGS = {'research':'researcher','engineering':'experiment_engineer','experience':'experience',
            'strategy':'strategy','auditor':'critic','environment':'environment_engineer','report_reader':'report_reader'}


def spec(*, reviewers=('auditor','experience'), tools=(), candidates=(), partial=False):
    stages=[{'id':'R0','description':'Produce a sorted complete result','owner':'engineering',
        'required_reviewers':list(reviewers),'required_outputs':['result.json'],
        'required_tools':list(tools),'required_candidates':list(candidates),
        'gates':[{'id':'result-accepted','kind':'evaluation','criterion':'Protected exact result','accepted':True}]}]
    if partial:
        stages[0]['gates']=[]
        stages.append({'id':'R1','description':'Later study','owner':'research','required_reviewers':[],
            'required_outputs':['report.md'],'gates':[{'id':'later','kind':'artifact','criterion':'Later report','path':'report.md'}]})
    value={'mode':'research','policy_version':2,'role_bindings':dict(BINDINGS),'stages':stages}
    if partial:value['completion_stage']='R0'
    return value


class Model:
    def __init__(self, role, calls, hook=None):
        self.role=role;self.calls=calls;self.hook=hook

    def call(self,prompt,schema,folder,**kwargs):
        c=json.loads(prompt.split('Task data:\n',1)[1]);a=c['assignment']
        self.calls.append((self.role,copy.deepcopy(a),c))
        override=self.hook(self.role,a,c) if self.hook else None
        if override is not None:return override,{}
        recent=c['recent_actions'];tools=[r.get('tool') for r in recent]
        if self.role=='coordinator':
            candidate=c['team']['workflow']['candidate']
            if 'evaluate' not in tools and not c['team']['definition'].get('completion_stage'):
                return action('evaluate',candidate),{}
            return action('propose_decision',{'decision':'ADVANCE','candidate':candidate,
                'state_revision':c['team']['workflow']['state_revision'],'rationale':'Required work returned'}),{}
        if a.get('review_of'):
            gate=a['acceptance_checks'][0]['check_id']
            if 'review_gate' not in tools:
                return action('review_gate',{'gate_id':gate,'candidate':a['review_of'],
                    'verdict':'PASS','evidence_ids':[a['candidate_receipt_id']],'summary':'Fixture review within stated scope'}),{}
            return action('submit_report',{'status':'DONE','summary':'Review complete','files':[]}),{}
        if 'write_file' not in tools:
            return action('write_file',{'path':'result.json','content':'[1,1,3,4]'}),{}
        if 'run' in a.get('available_tools',[]) and 'run' not in tools:
            return action('run','python -c "print(1)"'),{}
        return action('submit_report',{'status':'DONE','summary':'Result delivered','files':['result.json']}),{}


def make(tmp_path, *, workflow_spec=None, hook=None, **kwargs):
    calls=[]
    task={'goal':'Sort public numbers while retaining duplicate values',
          'inputs':{'numbers.json':'[4,1,3,1]'},'evaluator':'sorted_numbers','network':False,
          'workflow':workflow_spec or spec(),
          'budget':{'max_calls':100,'max_seconds':120,'max_assignments':40,'max_depth':2}}
    sandbox=kwargs.pop('sandbox_factory',FakeSandbox)
    team=Team(tmp_path,task,provider_factory=lambda config:Model(config['id'],calls,hook),
              sandbox_factory=sandbox,evaluators=EVALUATORS,**kwargs)
    return team,calls


def test_required_owner_and_each_reviewer_are_automatically_dispatched(tmp_path):
    team,calls=make(tmp_path,workflow_spec=spec(tools=('run',)))
    assert team.run()['status']=='completed'
    assert calls[0][0]=='experiment_engineer'
    assert {'critic','experience'} <= {c[0] for c in calls}
    assert team.state['goal_met']
    owners=[j for j in team.managed.board.jobs.values() if j['kind']=='owner']
    assert len(owners)==1 and owners[0]['status']=='DONE'
    assert len(owners[0]['attempts'])==1


def test_failed_review_revises_original_work_and_repeats_all_reviews(tmp_path):
    failed=[]
    def hook(role,a,c):
        if role=='critic' and a.get('review_of') and not failed:
            failed.append(a['review_of'])
            return action('review_gate',{'gate_id':a['acceptance_checks'][0]['check_id'],
                'candidate':a['review_of'],'verdict':'FAIL','evidence_ids':[a['candidate_receipt_id']],
                'summary':'The first submission needs a specific correction'})
    team,calls=make(tmp_path,hook=hook)
    assert team.run()['status']=='completed'
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    assert len(owner['attempts'])==2
    assert team.state['assignments'][owner['attempts'][1]]['assignment']['mode']=='revise'
    reviews=[j for j in team.managed.board.jobs.values() if j['kind']=='review' and j['review_of']==owner['attempts'][1]]
    assert len(reviews)==2 and all(j['status']=='DONE' for j in reviews)


def test_partial_scope_does_not_claim_objective_acceptance(tmp_path):
    team,_=make(tmp_path,workflow_spec=spec(partial=True))
    assert team.run()['status']=='completed'
    assert not team.state['goal_met']
    assert team.state['workflow']['stage']=='R0'


def test_unknown_roles_and_missing_review_grants_fail_before_calls(tmp_path):
    invalid=spec();invalid['role_bindings']['engineering']='not_configured'
    with pytest.raises(ValueError,match='missing role'):make(tmp_path,workflow_spec=invalid)


def test_work_reference_keeps_acceptance_and_cycles_are_rejected(tmp_path):
    team,_=make(tmp_path);board=team.managed.board
    first=board.add(key='one',owner='experiment_engineer',objective='Trace the error',
        acceptance_check='An executed trace',stage='R0')
    assert board.add(key='one',owner='experiment_engineer',objective='Same task',
        acceptance_check='Changed proposal',stage='R0')['acceptance_check']=='An executed trace'
    second=board.add(key='two',owner='researcher',objective='Resolve missing provenance',
        acceptance_check='Explicit source mapping',stage='R0',depends_on=[first['work_id']])
    with pytest.raises(ValueError,match='Cyclic'):board.depend(first['work_id'],second['work_id'])


def test_managed_schema_is_explicit_and_reviewers_are_distinct_gates():
    parsed=workflow.load_workflow(spec())
    gates=parsed['stages'][0]['gates']
    assert {g['id'] for g in gates} >= {'R0-review-auditor','R0-review-experience'}
    assert all(len(g['reviewers'])==1 for g in gates if g['kind']=='review')
    with pytest.raises(ValueError):workflow.load_workflow({'mode':'research','stages':[], 'owner':'x'})


def test_report_only_review_never_receives_original_inputs_or_global_state(tmp_path):
    value=spec(reviewers=('report_reader',))
    value['stages'][0].update(report_paths=['result.json'],review_scopes={'report_reader':'report_only'})
    team,calls=make(tmp_path,workflow_spec=value)
    assert team.run()['status']=='completed'
    for role,a,c in calls:
        if role!='report_reader':continue
        assert a['inputs']=={} and 'parent_evaluation' not in a and 'environment' not in a
        assert a['review_files']==['inputs/parent/result.json']
        assert 'Sort public numbers' not in a['goal']
        assert 'work' not in c['team'] and 'workflow' not in c['team']
        workspace=tmp_path/'agents'/a['task_id']/'workspace'
        delivered=[p.relative_to(workspace).as_posix() for p in workspace.rglob('*') if p.is_file()]
        assert delivered==['inputs/parent/result.json']


def test_missing_execution_cannot_pass_and_has_a_bounded_rework_owner(tmp_path):
    def hook(role,a,c):
        if not a.get('review_of') and role=='experiment_engineer' and any(r['tool']=='write_file' for r in c['recent_actions']):
            return action('submit_report',{'status':'DONE','summary':'Code only, not executed','files':['result.json']})
    value=spec(tools=('run',));value['work_policy']={'max_attempts':2}
    team,_=make(tmp_path,workflow_spec=value,hook=hook)
    assert team.run()['status']=='waiting_external'
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    assert owner['status']=='WAITING' and len(owner['attempts'])==2
    assert any('Missing actual' in f for f in owner['feedback'])
    assert team.state['workflow']['pending_external']['owner']=='operator'
    assert not team.state['goal_met']


def test_candidate_obligations_create_rework_instead_of_silent_omission(tmp_path):
    def hook(role,a,c):
        if not a.get('review_of') and role=='experiment_engineer' and any(r['tool']=='run' for r in c['recent_actions']):
            eid=c['recent_actions'][-1]['evidence_id']
            return action('submit_report',{'status':'DONE','summary':'Fixture alternatives acknowledged','files':['result.json'],
                'candidate_decisions':[{'candidate':x,'decision':'UNTESTED','reason':'No recognition experiment in this fixture',
                    'evidence_ids':[eid],'followup_action':'Run a separately specified OMR comparison'} for x in ['HOMR','Audiveris']]})
    team,_=make(tmp_path,workflow_spec=spec(candidates=('HOMR','Audiveris')),hook=hook)
    assert team.run()['status']=='completed'
    assert {d['candidate'] for d in team.managed.board.state['candidate_decisions']}=={'HOMR','Audiveris'}


def test_execution_assertion_rejects_another_assignments_action(tmp_path):
    team,calls=make(tmp_path);team.run()
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    aid=owner['assignment_id']
    eid,record=next((eid,r) for eid,r in team.managed._tool_records(aid) if r['receipt']['tool']=='run')
    reviewer=next(j for j in team.managed.board.jobs.values() if j['kind']=='review')
    report={'status':'DONE','summary':'Unsupported first-person execution','files':[],
        'execution_records':[{'action':'executed','target':record['target'],'evidence_ids':[eid]}]}
    with pytest.raises(ValueError,match='this assignment'):
        team.validate_assignment_report(report,team.state['assignments'][reviewer['assignment_id']]['assignment'])


def test_incapable_work_is_routed_to_a_named_external_owner(tmp_path):
    team,_=make(tmp_path);source=team.managed.seed()
    items={'work_items':[{'existing_work_id':'','owner':'engineering','objective':'Run the missing remote instrument',
        'input_artifact_ids':[],'required_tools':['remote_instrument'],'acceptance_check':'Actual instrument data and settings', 'blocking':True}]}
    external=team.managed.board.add_report_work(items,source)[0]
    assert external['owner']=='operator' and external['status']=='WAITING'
    assert external not in team.managed.board.ready('R0')


def test_unchanged_completed_run_adds_no_model_calls(tmp_path):
    team,_=make(tmp_path);team.run();count=team.state['calls'];team.close()
    restored,calls=make(tmp_path)
    assert restored.run()['status']=='completed' and restored.state['calls']==count and not calls


def test_crash_does_not_blindly_repeat_an_external_command(tmp_path):
    executed=[]
    class Crash(FakeSandbox):
        def run(self,*args,**kwargs):
            executed.append('effect')
            raise KeyboardInterrupt()
    team,_=make(tmp_path,sandbox_factory=Crash)
    with pytest.raises(KeyboardInterrupt):team.run()
    team.close()
    team,_=make(tmp_path)
    team.reopen_stopped('Inspect interrupted execution')
    assert team.run()['status']=='waiting_external'
    assert executed==['effect']
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    team.retry_uncertain_action(owner['assignment_id'],'Synthetic effect inspected; repeating is safe in this fixture')
    assert team.run()['status']=='completed'


def test_major_objection_creates_required_resolution_work(tmp_path):
    raised=[]
    def hook(role,a,c):
        if role=='critic' and a.get('review_of') and not raised and any(r['tool']=='review_gate' for r in c['recent_actions']):
            raised.append(True)
            return action('submit_report',{'status':'DONE','summary':'An important disagreement remains','files':[],
                'objections':[{'target_id':a['review_of'],'category':'FACT','severity':'MAJOR',
                    'statement':'Verify that duplicate inputs are preserved','evidence_ids':[a['candidate_receipt_id']],
                    'resolution_test':'Return a concrete duplicate-preservation fixture'}]})
    team,calls=make(tmp_path,hook=hook)
    assert team.run()['status']=='completed'
    issues=[j for j in team.managed.board.jobs.values() if j['key'].startswith('issue:')]
    assert len(issues)==1 and issues[0]['status']=='DONE'
    assert any(role=='researcher' for role,_,_ in calls)


def test_new_submission_cannot_reuse_old_review_and_cannot_skip_scope(tmp_path):
    team,_=make(tmp_path,workflow_spec=spec(partial=True))
    team.run()
    assert team.state['workflow']['stage']=='R0'
    assert {r['candidate'] for r in team.state['workflow']['reviews']}=={team.state['workflow']['candidate']}


def test_stage_templates_preserve_four_perspective_assignment_contracts():
    root=Path(__file__).resolve().parents[1]
    research=workflow.load_workflow(json.loads((root/'workflows/research.json').read_text()))
    product=workflow.load_workflow(json.loads((root/'workflows/product.json').read_text()))
    assert research['stages'][3]['owner']=='engineering'
    assert research['stages'][0]['required_reviewers']==['strategy','engineering','experience']
    assert product['stages'][4]['owner']=='engineering'
    assert 'report_reader' in research['stages'][-1]['required_reviewers']
    assert 'report_reader' in product['stages'][-1]['required_reviewers']


def test_missing_provider_executable_fails_before_reserving_model_calls(tmp_path, monkeypatch):
    team,_=make(tmp_path)
    from goalagent.provider import CodexProvider
    monkeypatch.setattr('goalagent.provider.shutil.which',lambda name:None)
    team.provider_factory=lambda config:CodexProvider('fixture')
    assert team.run()['status']=='waiting_external'
    assert team.state['calls']==0
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    assert 'not on PATH' in owner['feedback'][-1]


def test_independent_reviewers_cannot_read_peer_conclusions_or_artifacts(tmp_path):
    from types import SimpleNamespace
    team,calls=make(tmp_path)
    assert team.run()['status']=='completed'
    for role,a,c in calls:
        if a.get('review_of'):
            assert 'workflow' not in c['team'] and 'candidate_decisions' not in c['team']
            assert c['team']['current_work']['owner']==role
    jobs=[j for j in team.managed.board.jobs.values() if j['kind']=='review']
    first,second=jobs
    aid=second['assignment_id']
    reader=SimpleNamespace(folder=team.folder/'agents'/aid,
        assignment=team.state['assignments'][aid]['assignment'])
    assert 'workflow' not in team.project_state(reader,action('project_state'),10)
    verdict=next(r for r in team.state['workflow']['reviews'] if r['reviewer_assignment']==first['assignment_id'])
    with pytest.raises(ValueError,match='peer review conclusions'):
        team.read_evidence(reader,action('read_evidence',{'id':verdict['evidence_id']}),10)
    peer=team.register_artifact(b'Peer conclusion',owner=first['assignment_id'],path='peer.md')
    with pytest.raises(ValueError,match='peer review artifacts'):
        team.read_artifact(reader,action('read_artifact',{'id':peer['artifact_id']}),10)


def test_environment_recovery_wakes_same_work_with_new_frozen_image(tmp_path,monkeypatch):
    monkeypatch.setattr('goalagent.team_environment.prepare',lambda *args:
        {'status':'ready','image':'fixture-ready-image','environment_id':'fixture-environment'})
    requested=[]
    def hook(role,a,c):
        tools=[r['tool'] for r in c['recent_actions']]
        if role=='experiment_engineer' and not a.get('review_of') and not requested:
            requested.append(True)
            return action('request_environment','Observed fixture dependency failure; request a controlled environment')
        if role=='environment_engineer':
            if 'prepare_environment' not in tools:
                return action('prepare_environment',{'system_packages':[],'python_packages':[],
                    'smoke_script':'fixture-smoke.py'})
            return action('submit_report',{'status':'DONE','summary':'Synthetic readiness receipt','files':[]})
    team,_=make(tmp_path,hook=hook)
    assert team.run()['status']=='completed'
    owner=next(j for j in team.managed.board.jobs.values() if j['kind']=='owner')
    assert len(owner['attempts'])==2
    recovered=team.state['assignments'][owner['attempts'][1]]
    assert recovered['assignment']['mode']=='debug'
    assert json.loads((team.folder/'agents'/owner['attempts'][1]/'execution-policy.json').read_text())['image']=='fixture-ready-image'
    original=json.loads((team.folder/'agents'/owner['attempts'][0]/'execution-policy.json').read_text())
    assert original['image']!='fixture-ready-image'
    environment=next(j for j in team.managed.board.jobs.values() if j['kind']=='environment')
    assert environment['status']=='DONE' and environment['work_id'] in owner['depends_on']


def test_review_candidate_receipt_confusion_returns_actionable_correction(tmp_path):
    from types import SimpleNamespace
    value=spec();value['work_policy']={'checkpoint_interval':1}
    team,_=make(tmp_path,workflow_spec=value)
    team.run()
    reviewer=next(j for j in team.managed.board.jobs.values() if j['kind']=='review')
    aid=reviewer['assignment_id'];assignment=team.state['assignments'][aid]['assignment']
    assert assignment['candidate_receipt_id']!=assignment['review_of']
    reader=SimpleNamespace(folder=team.folder/'agents'/aid,assignment=assignment,
        config=team.definitions[reviewer['owner']],state={'steps':1})
    with pytest.raises(ValueError,match=assignment['review_of']):
        team.review_gate(reader,action('review_gate',{'gate_id':reviewer['gate_id'],
            'candidate':assignment['candidate_receipt_id'],'verdict':'PASS',
            'evidence_ids':[assignment['candidate_receipt_id']],'summary':'Misplaced receipt ID'}),10)
