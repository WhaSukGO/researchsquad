"""Handoff/recovery failures observed in research runs, exercised without model claims."""
import copy
import json
from pathlib import Path
import pytest

from goalagent.team import Team
from goalagent.agent import Agent
from goalagent.artifacts import ArtifactStore
from goalagent.configuration import validate_agent
from goalagent.team_evaluators import EVALUATORS
from test_team import FakeSandbox, Scripted, action, task, instance


def make(tmp_path, provider, **kwargs):
    spec=task();spec['unlimited']=True
    return Team(tmp_path,spec,provider_factory=provider,sandbox_factory=FakeSandbox,**kwargs)


def assignment(role='experiment_engineer', **extra):
    return action('delegate',{'agent':role,'objective':'Implement and test a candidate','success_criteria':'A reviewable candidate and measured result',**extra})


def test_unlimited_worker_yields_and_resumes_across_old_step_limit_and_process_restart(tmp_path):
    seen=[]
    class Provider:
        def call(self,prompt,schema,folder,**kwargs):
            ctx=json.loads(prompt.split('Task data:\n')[1]);step=int(Path(folder).name)
            seen.append(step)
            assert ctx['remaining_steps'] is None and ctx['remaining_seconds'] is None
            assert ctx['checkpoint_interval']==8
            if step==1:return action('checkpoint',{'summary':'Found baseline','findings':['Ready to implement'],'failures':[],'next_test':'Sort values','files':[]}),{}
            assert ctx['progress']['summary']=='Found baseline'
            assert ctx['coordinator_guidance']=='Continue the next discriminating test'
            if step==26:return action('submit_report',{'status':'DONE','summary':'Candidate implemented','files':['result.json']}),{}
            return action('write_file',{'path':'result.json','content':'[1,1,3,4]'}),{}
    factory=lambda c:Provider()
    team=make(tmp_path,factory,evaluators=EVALUATORS);lead=instance(team)
    first=lead.execute(assignment(),100);id=first['assignment_id']
    assert first['outcome']['status']=='checkpointed' and team.state['calls']==1
    assert not team.state['evaluations']
    team.close()
    team=make(tmp_path,factory,evaluators=EVALUATORS);lead=instance(team)
    result=first
    while result['outcome']['status']=='checkpointed':
        lead.state['steps']+=1
        command=action('continue_assignment',{'assignment_id':id,'checkpoint_id':result['checkpoint_id'],'guidance':'Continue the next discriminating test'})
        result=lead.execute(command,100)
        used=team.state['calls'];assert lead.execute(command,100)==result and team.state['calls']==used
    assert result['outcome']['status']=='submitted' and team.state['calls']==26
    assert seen==list(range(1,27)) and len(team.state['assignments'])==1
    assert all(v is None for v in team.task['budget'].values())
    assert lead.execute(action('evaluate',id),100)['measurement']['accepted']
    assert first['evidence_id']!=result['evidence_id']
    assert team.evidence_record(first['evidence_id'])['outcome']['status']=='checkpointed'


def test_automatic_checkpoint_limits_model_error_loop_without_consuming_total_budget(tmp_path):
    class Broken:
        def call(self,*args,**kwargs):raise RuntimeError('provider unavailable')
    team=make(tmp_path,lambda c:Broken());lead=instance(team)
    result=lead.execute(assignment(),100)
    assert result['outcome']['status']=='checkpointed' and team.state['calls']==8
    assert 'provider unavailable' in result['outcome']['last_observation']['error']
    assert all(v is None for v in team.task['budget'].values())


def test_shell_created_binary_and_output_files_survive_failed_report_and_debug_handoff(tmp_path):
    class Provider:
        def call(self,prompt,schema,folder,**kwargs):
            workspace=Path(folder).parents[1]/'workspace'
            (workspace/'candidate.py').write_text('print(42)')
            (workspace/'output/prediction.bin').write_bytes(b'\xff\x00prediction')
            (workspace/'unsafe').symlink_to('/etc/passwd')
            return action('submit_report',{'status':'FAILED','failure_kind':'implementation','summary':'Parser contract mismatch','files':[]}),{}
    team=make(tmp_path,lambda c:Provider());lead=instance(team)
    first=lead.execute(assignment(),100)
    assert first['outcome']['status']=='failed'
    assert {'candidate.py','output/prediction.bin'}<=set(first['artifact_ids'])
    assert any(item['path']=='unsafe' for item in first['omitted'])
    record=team.state['artifacts'][first['artifact_ids']['output/prediction.bin']]
    assert team.artifact_store.read(record)==b'\xff\x00prediction'
    lead.state['steps']+=1
    second=lead.execute(assignment(parent=first['assignment_id'],mode='debug'),100)
    child=tmp_path/'agents'/second['assignment_id']/'workspace'
    assert (child/'inputs/parent/candidate.py').read_text()=='print(42)'
    assert (child/'inputs/parent/output/prediction.bin').read_bytes()==b'\xff\x00prediction'
    assert not (child/'inputs/parent/unsafe').exists()


def test_stable_artifact_handoff_normalizes_input_prefix_and_detects_tampering(tmp_path):
    def factory(c):return Scripted([action('submit_report',{'status':'NEEDS_INPUT','summary':'Need one more input','files':[]})])
    team=make(tmp_path,factory);lead=instance(team)
    (lead.workspace/'source.txt').write_text('provided label')
    first=lead.execute(assignment(inputs={'inputs/label.txt':'source.txt'}),100)
    child=tmp_path/'agents'/first['assignment_id']/'workspace'
    assert (child/'inputs/label.txt').read_text()=='provided label'
    assert not (child/'inputs/inputs').exists()
    artifact_id=first['input_inventory']['label.txt']['artifact_id']
    lead.state['steps']+=1
    second=lead.execute(assignment(input_artifact_ids={'label.txt':artifact_id}),100)
    assert (tmp_path/'agents'/second['assignment_id']/'workspace/inputs/label.txt').read_text()=='provided label'
    (team.artifact_store.folder/artifact_id/'content').write_bytes(b'changed')
    lead.state['steps']+=1
    with pytest.raises(ValueError,match='changed'):lead.execute(assignment(input_artifact_ids={'label.txt':artifact_id}),100)


def test_missing_inputs_and_destination_collisions_fail_before_model_dispatch(tmp_path):
    team=make(tmp_path,lambda c:Scripted([]));lead=instance(team)
    with pytest.raises(FileNotFoundError):lead.execute(assignment(inputs={'file':'missing'}),100)
    (lead.workspace/'a').write_text('one')
    with pytest.raises(ValueError,match='Duplicate'):lead.execute(assignment(inputs={'a':'a','inputs/a':'a'}),100)
    with pytest.raises(ValueError,match='reserved'):lead.execute(assignment(inputs={'inputs/inputs/a':'a'}),100)
    assert team.state['calls']==0 and not team.state['assignments']


def test_partial_failure_summary_and_claim_validation(tmp_path):
    def factory(c):return Scripted([
        action('submit_report',{'status':'DONE','summary':'Invented success','files':[], 'claims':[{'statement':'Accurate','epistemic_status':'observed','evidence_ids':['invented'],'limitations':'none'}]}),
        action('submit_report',{'status':'NEEDS_INPUT','summary':'Evaluation input missing; implementation is preserved','files':[],'open_questions':['Which input?']})])
    team=make(tmp_path,factory,evaluators=EVALUATORS);lead=instance(team);result=lead.execute(assignment(),100)
    assert result['outcome']['status']=='needs_input'
    assert result['outcome']['report']['summary'].startswith('Evaluation input missing')
    assert not team.state['goal_met']
    report=json.loads((tmp_path/'reports'/f"{result['assignment_id']}.json").read_text())
    assert report['task_id']==result['assignment_id'] and report['role']=='experiment_engineer'
    with pytest.raises(ValueError,match='complete submission'):lead.execute(action('evaluate',result['assignment_id']),100)


def test_crash_after_receipt_replays_handoff_without_reexecuting_worker(tmp_path):
    calls=[]
    def factory(c):
        calls.append(c['id'])
        return Scripted([action('write_file',{'path':'result.json','content':'[1,1,3,4]'}),action('finish',{'summary':'Ready','files':['result.json']})])
    team=make(tmp_path,factory);lead=instance(team);request=assignment()
    original=team.record
    def crash(id,data):
        value=original(id,data)
        if id.startswith('task-'):raise KeyboardInterrupt()
        return value
    team.record=crash
    with pytest.raises(KeyboardInterrupt):lead.execute(request,100)
    team.close()
    team=make(tmp_path,factory);lead=instance(team)
    result=lead.execute(request,100)
    assert result['outcome']['status']=='submitted' and team.state['calls']==2
    assert len(calls)==2 # provider reconstructed, but no completed actions re-executed
    assert lead.execute(request,100)==result and team.state['calls']==2


def test_checkpoint_cadence_is_configurable_and_not_a_budget(tmp_path):
    team=make(tmp_path,lambda c:Scripted([]));config=copy.deepcopy(team.definitions['planner'])
    config['checkpoint_interval']=3;validate_agent(config)
    assert all(v is None for v in config['limits'].values())
    config['checkpoint_interval']=None
    with pytest.raises(ValueError,match='checkpoint_interval'):validate_agent(config)


def test_explicit_checkpoint_preserves_named_scratch_artifact(tmp_path):
    def factory(c):return Scripted([action('write_file',{'path':'tmp/important.txt','content':'preserve me'}),action('checkpoint',{'summary':'Prepared data','next_test':'Measure it','files':['tmp/important.txt']})])
    team=make(tmp_path,factory);lead=instance(team);result=lead.execute(assignment(),100)
    assert 'tmp/important.txt' in result['artifact_ids']
    assert (lead.workspace/result['artifacts'][0]).read_text()=='preserve me'


def test_required_outputs_cannot_be_bypassed_by_either_finish_tool(tmp_path):
    def factory(c):return Scripted([
        action('write_file',{'path':'report.txt','content':'Only a report'}),
        action('finish',{'summary':'Done','files':['report.txt']}),
        action('submit_report',{'status':'DONE','summary':'Done','files':['report.txt']}),
        action('submit_report',{'status':'NEEDS_INPUT','summary':'Required result is missing','files':['report.txt']})])
    team=make(tmp_path,factory);lead=instance(team)
    result=lead.execute(assignment(required_outputs=[{'path':'result.json','kind':'prediction','description':'The complete sorted list'}]),100)
    assert result['outcome']['status']=='needs_input'
    packet=json.loads((tmp_path/'tasks'/f"{result['assignment_id']}.json").read_text())
    assert packet['remaining_budget']['model_calls'] is None
    assert packet['required_outputs'][0]['path']=='result.json'
    assert 'submit_report' in packet['available_tools']


def test_binary_change_invalidates_candidate_revision_even_when_text_unchanged(tmp_path):
    class Provider:
        def call(self,prompt,schema,folder,**kwargs):
            step=int(Path(folder).name);workspace=Path(folder).parents[1]/'workspace'
            (workspace/'model.bin').write_bytes(b'\xff'+bytes([step]))
            return action('checkpoint',{'summary':'Binary model changed','next_test':'Measure new model','files':['model.bin']}),{}
    team=make(tmp_path,lambda c:Provider());lead=instance(team)
    first=lead.execute(assignment(),100);lead.state['steps']+=1
    second=lead.execute(action('continue_assignment',{'assignment_id':first['assignment_id'],'checkpoint_id':first['checkpoint_id'],'guidance':'Make the next model revision'}),100)
    assert first['submission_hash']==second['submission_hash']
    assert first['candidate_revision']!=second['candidate_revision']
    lead.state['steps']+=1
    with pytest.raises(ValueError,match='Stale checkpoint'):
        lead.execute(action('continue_assignment',{'assignment_id':first['assignment_id'],'checkpoint_id':first['checkpoint_id'],'guidance':'Invalid old checkpoint'}),100)


def test_large_observations_remain_on_disk_but_context_is_bounded(tmp_path):
    team=make(tmp_path,lambda c:Scripted([]));lead=instance(team)
    lead.state['history']=[{'step':1,'tool':'delegate','observation':{'assignment_id':'task-123','checkpoint_id':'check-123','artifacts':['x'*1000]*500},'evidence_id':'receipt-123'}]
    compact=lead.recent_context()
    assert len(json.dumps(compact))<8000
    assert compact[0]['observation']['read_full_evidence_id']=='receipt-123'
    assert compact[0]['observation']['assignment_id']=='task-123'
    assert len(lead.state['history'][0]['observation']['artifacts'])==500


def test_committed_shell_receipt_is_not_executed_again_after_restart(tmp_path):
    team=make(tmp_path,lambda c:Scripted([]));worker=instance(team,'experiment_engineer')
    command=action('run','external command already completed')
    worker.state['pending']=command
    worker.state['steps']=1
    worker.state['history']=[]
    receipt={'action':command,'step':1,'tool':'run','why':command['why'],'observation':{'exit_code':0,'tail':'already executed'}}
    path=worker.folder/'actions/001.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(receipt))
    worker.save()
    worker.provider=Scripted([action('submit_report',{'status':'DONE','summary':'Used original receipt','files':[]})])
    calls=[]
    worker.sandbox.run=lambda *args: calls.append(args)
    result=worker.run(lambda:None,lambda:float('inf'),checkpoint_interval=8)
    assert result['status']=='submitted' and calls==[]
    assert worker.state['history'][0]['observation']['tail']=='already executed'
