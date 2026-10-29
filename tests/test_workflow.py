import json
import pytest
from goalagent.team import Team
from goalagent.team_evaluators import EVALUATORS
from test_team import FakeSandbox, Scripted, action, task, instance


def make(tmp_path, stages=None, provider=None):
    spec=task();spec['unlimited']=True
    if stages:spec['workflow']={'mode':'research','stages':stages}
    def default(c):return Scripted([action('write_file',{'path':'result.json','content':'[1,1,3,4]'}),action('submit_report',{'status':'DONE','summary':'Candidate ready','files':['result.json']})])
    return Team(tmp_path,spec,provider_factory=provider or default,sandbox_factory=FakeSandbox,evaluators=EVALUATORS)


def stage(id,kind='evaluation',**kwargs):
    return {'id':id,'description':id,'gates':[{'id':id+'-gate','kind':kind,'criterion':id,**kwargs}]}


def candidate(team,lead):
    return lead.execute(action('delegate',{'agent':'experiment_engineer','objective':'Sort the supplied values','success_criteria':'Ascending complete values','inputs':{}}),100)['assignment_id']


def decide(team,lead,kind,id=None,**kwargs):
    lead.state['steps']+=1
    return lead.execute(action('propose_decision',{'decision':kind,'state_revision':team.state['workflow']['state_revision'],'candidate':id,'rationale':'Evidence-supported decision',**kwargs}),100)


def test_missing_evidence_cannot_pass_and_unknown_is_not_failure(tmp_path):
    team=make(tmp_path);lead=instance(team);id=candidate(team,lead)
    with pytest.raises(ValueError,match='not all PASS'):decide(team,lead,'ADVANCE',id)
    state=lead.execute(action('project_state'),100)
    assert state['workflow']['gates'][0]['status']=='UNKNOWN'
    assert not team.state['goal_met']
    lead.execute(action('evaluate',id),100)
    result=decide(team,lead,'ADVANCE',id)
    assert result['gates'][0]['status']=='PASS'
    assert team.state['workflow']['run_status']=='COMPLETED'


def test_negative_measurement_does_not_complete_positive_objective(tmp_path):
    def provider(c):return Scripted([action('write_file',{'path':'result.json','content':'[1,3,4]'}),action('finish',{'summary':'Ready','files':['result.json']})])
    team=make(tmp_path,provider=provider);lead=instance(team);id=candidate(team,lead)
    measurement=lead.execute(action('evaluate',id),100)
    assert not measurement['measurement']['accepted']
    with pytest.raises(ValueError,match='not all PASS'):decide(team,lead,'ADVANCE',id)
    result=decide(team,lead,'STOP',id,evidence_ids=[measurement['evidence_id']])
    assert result['gates'][0]['status']=='FAIL' and not team.state['goal_met']


def test_configured_stages_cannot_be_skipped_or_finished_by_report_alone(tmp_path):
    stages=[stage('R0','artifact',path='result.json'),stage('R1'),stage('R2')]
    team=make(tmp_path,stages);lead=instance(team);id=candidate(team,lead)
    with pytest.raises(ValueError,match='skip'):decide(team,lead,'ADVANCE',id,target_stage='R2')
    result=decide(team,lead,'ADVANCE',id)
    assert result['target_stage']=='R1'
    stale=action('propose_decision',{'decision':'REVISE','state_revision':0,'rationale':'Stale','owner':'researcher','resume_when':'New evidence'})
    lead.state['steps']+=1
    with pytest.raises(ValueError,match='Stale'):lead.execute(stale,100)
    lead.execute(action('evaluate',id),100)
    decide(team,lead,'ADVANCE',id)
    assert team.state['workflow']['stage']=='R2'
    decide(team,lead,'ADVANCE',id)
    assert team.state['workflow']['run_status']=='COMPLETED'


def test_new_candidate_cannot_reuse_prior_candidate_measurement(tmp_path):
    team=make(tmp_path);lead=instance(team);first=candidate(team,lead)
    lead.execute(action('evaluate',first),100)
    decide(team,lead,'REVISE',first,owner='experiment_engineer',resume_when='Measure a different candidate')
    lead.state['steps']+=1;second=candidate(team,lead)
    with pytest.raises(ValueError,match='not all PASS'):decide(team,lead,'ADVANCE',second)
    # Historical evidence remains readable and still bound to the old candidate.
    assert team.evidence_record('evaluation-'+first)['assignment_id']==first
    assert second not in team.state['evaluations']


def test_review_requires_authorized_separate_assignment_and_candidate_evidence(tmp_path):
    team=make(tmp_path,[stage('R0','review',reviewers=['critic']),stage('R1')]);lead=instance(team);id=candidate(team,lead)
    from goalagent.agent import Agent
    config=team.definitions['critic']
    critic=Agent(team.folder/'agents'/'reviewer',{'depth':1},Scripted([]),team.policy(config),config,team.registry,FakeSandbox)
    critic.state['steps']=1
    review=action('review_gate',{'gate_id':'R0-gate','candidate':id,'verdict':'PASS','evidence_ids':[id],'summary':'Inspected originals'})
    with pytest.raises(ValueError,match='separate assignment'):critic.execute(review,100)
    critic.assignment.update(review_of=id,review_revision=team.state['assignments'][id]['candidate_revision'])
    result=critic.execute(review,100)
    assert result['scope'].startswith('Independent assignment review only')
    assert decide(team,lead,'ADVANCE',id)['gates'][0]['status']=='PASS'
    # Reviewer prose cannot replace a protected evaluation in R1.
    with pytest.raises(ValueError,match='not all PASS'):decide(team,lead,'ADVANCE',id)


def test_wait_is_durable_no_polling_and_only_trusted_matching_event_resumes(tmp_path):
    team=make(tmp_path,[stage('R0','external'),stage('R1')]);lead=instance(team);id=candidate(team,lead)
    decision=decide(team,lead,'WAIT_EXTERNAL',id,owner='human',resume_when='Provide independent observation')
    calls=team.state['calls']
    assert team.run()['status']=='waiting_external' and team.state['calls']==calls
    assert 'accept_external' not in team.registry.tools
    team=make(tmp_path,[stage('R0','external'),stage('R1')])
    with pytest.raises(ValueError,match='pending request'):
        team.accept_external(request_id='wrong',event_id='observation-1',summary='Observed',files={'observation.txt':b'actual data'})
    result=team.accept_external(request_id=decision['decision_id'],event_id='observation-1',summary='Observed with recorded scope',files={'observation.txt':b'actual data'},gate_verdicts={'R0-gate':'PASS'})
    assert team.state['workflow']['run_status']=='ACTIVE'
    assert team.accept_external(request_id=decision['decision_id'],event_id='observation-1',summary='Observed with recorded scope',files={'observation.txt':b'actual data'},gate_verdicts={'R0-gate':'PASS'})==result
    lead=instance(team);lead.state['steps']=20
    assert decide(team,lead,'ADVANCE',id)['gates'][0]['status']=='PASS'
    assert team.state['workflow']['stage']=='R1'


def test_same_decision_replay_does_not_duplicate_transition(tmp_path):
    team=make(tmp_path);lead=instance(team);id=candidate(team,lead)
    data={'decision':'REVISE','state_revision':0,'candidate':id,'rationale':'Measure next','owner':'experiment_engineer','resume_when':'A measurement'}
    command=action('propose_decision',data)
    first=lead.execute(command,100);second=lead.execute(command,100)
    assert first==second and team.state['workflow']['state_revision']==1
    assert len(team.state['workflow']['decisions'])==1


def test_journal_repairs_partial_append_from_authoritative_state(tmp_path):
    team=make(tmp_path);lead=instance(team);candidate(team,lead)
    events=list(team.state['events']);team.close()
    with (tmp_path/'events.jsonl').open('a') as stream:stream.write('{partial')
    restored=make(tmp_path)
    assert [json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]==events
    assert restored.state['events']==events


def test_changed_workflow_contract_requires_new_run(tmp_path):
    team=make(tmp_path,[stage('R0')]);team.close()
    with pytest.raises(ValueError,match='contract changed'):make(tmp_path,[stage('R0','artifact',path='result.json')])


def test_external_event_cannot_be_reused_with_changed_material(tmp_path):
    team=make(tmp_path,[stage('R0','external')]);lead=instance(team);id=candidate(team,lead)
    decision=decide(team,lead,'WAIT_EXTERNAL',id,owner='human',resume_when='Real observation')
    kwargs={'request_id':decision['decision_id'],'event_id':'real-1','summary':'Observed','files':{'data.txt':b'original'},'gate_verdicts':{'R0-gate':'PASS'}}
    team.accept_external(**kwargs)
    kwargs['files']={'data.txt':b'changed'}
    with pytest.raises(ValueError,match='reused with changed'):team.accept_external(**kwargs)


def test_stop_needs_explicit_operator_resume_and_keeps_unlimited_policy(tmp_path):
    team=make(tmp_path);lead=instance(team);id=candidate(team,lead)
    decide(team,lead,'STOP',id)
    assert team.run()['status']=='stopped'
    team=make(tmp_path)
    team.reopen_stopped('Continue under the same objective after reviewing partial results')
    assert team.state['workflow']['run_status']=='ACTIVE'
    assert all(value is None for value in team.task['budget'].values())
