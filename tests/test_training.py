import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from goalagent.large_store import LargeStore
from goalagent.tracing import Trace, redact
from goalagent.training import TrainingRuntime
from test_managed import make


def worker(team,role='experiment_engineer',name='worker'):
    path=team.folder/'agents'/name;space=path/'workspace';space.mkdir(parents=True,exist_ok=True)
    return SimpleNamespace(folder=path,workspace=space,config=team.definitions[role],state={'steps':1})


def profile():return {'image':'sha256:'+'a'*64,'gpu':False,'memory':'1g','cpus':1,
                      'max_seconds':2,'max_output_bytes':32_000_000,'roles':['experiment_engineer']}


def test_large_store_streams_over_text_limit_detects_tampering_and_rejects_links(tmp_path):
    src=tmp_path/'large.bin'
    with src.open('wb') as f:f.seek(20_000_000);f.write(b'end')
    store=LargeStore(tmp_path/'store',30_000_000);ref=store.register(src,kind='checkpoint')
    assert ref['bytes']>16_000_000 and store.verify(ref).stat().st_size==20_000_003
    store.verify(ref).write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):store.verify(ref)
    link=tmp_path/'link';link.symlink_to(src)
    with pytest.raises(OSError):store.register(link,kind='model')


def test_profiles_require_owner_grant_immutable_image_and_finite_budget(tmp_path):
    team,_=make(tmp_path);team.task['training']={'profiles':{'cpu':profile()}}
    runtime=TrainingRuntime(team);a=worker(team,'critic')
    packet={'profile':'cpu','code_files':['go.py'],'entrypoint':'go.py','args':[],'dataset_ids':[]}
    with pytest.raises(ValueError,match='not granted'):runtime.start(a,packet,'one')
    team.task['training']['profiles']['cpu']['image']='python:latest'
    with pytest.raises(ValueError,match='immutable'):TrainingRuntime(team)


def test_job_receipt_reuse_no_relaunch_and_cross_assignment_denied(tmp_path,monkeypatch):
    team,_=make(tmp_path);team.task['training']={'profiles':{'cpu':profile()}}
    runtime=TrainingRuntime(team);a=worker(team);(a.workspace/'go.py').write_text('print(1)')
    calls=[]
    def docker(*args,**kwargs):
        calls.append(args)
        if args[0]=='inspect':out=json.dumps({'Running':True,'ExitCode':0})
        else:out=''
        return SimpleNamespace(returncode=0,stdout=out,stderr='')
    monkeypatch.setattr(runtime,'docker',docker)
    packet={'profile':'cpu','code_files':['go.py'],'entrypoint':'go.py','args':[],'dataset_ids':[]}
    first=runtime.start(a,packet,'key');second=runtime.start(a,packet,'key')
    assert first['job_id']==second['job_id'] and sum(c[0]=='run' for c in calls)==1
    with pytest.raises(ValueError,match='another assignment'):runtime.owned(worker(team,name='other'),first['job_id'])
    run=next(c for c in calls if c[0]=='run')
    assert '--network' in run and '--privileged' not in run and '--gpus' not in run
    assert not any('/var/run/docker.sock' in str(v) for v in run)


def test_ambiguous_start_never_blindly_repeats(tmp_path,monkeypatch):
    team,_=make(tmp_path);team.task['training']={'profiles':{'cpu':profile()}}
    runtime=TrainingRuntime(team);a=worker(team);(a.workspace/'go.py').write_text('print(1)')
    calls=[]
    def docker(*args,**kw):
        calls.append(args)
        if args[0]=='run':raise TimeoutError('Unknown container outcome')
        return SimpleNamespace(returncode=1,stdout='',stderr='not found')
    monkeypatch.setattr(runtime,'docker',docker)
    d={'profile':'cpu','code_files':['go.py'],'entrypoint':'go.py','args':[],'dataset_ids':[]}
    with pytest.raises(TimeoutError):runtime.start(a,d,'same')
    assert runtime.start(a,d,'same')['status']=='START_UNCERTAIN'
    assert sum(c[0]=='run' for c in calls)==1


def test_dataset_registration_is_explicit_and_models_cannot_publish_running_output(tmp_path,monkeypatch):
    team,_=make(tmp_path);r=team.training;a=worker(team)
    source=tmp_path/'train-labels';source.write_text('public training labels')
    did=r.register_dataset('train',{'labels':source},{'split':'train'})
    assert did in r.state['datasets'] and str(tmp_path) not in json.dumps(r.catalog())
    r.state['jobs']['j']={'id':'j','owner':r.owner(a)}
    monkeypatch.setattr(r,'status',lambda j:{'status':'RUNNING'})
    with pytest.raises(ValueError,match='after job exits'):r.register_model(a,'j','weights','model')


def test_trace_redaction_structure_and_export_escapes_html(tmp_path):
    t=Trace(tmp_path);parent=t.start('agent','role',data={'system_prompt':'API_KEY=secret123'})
    child=t.start('model','call',parent=parent,data={'password':'unsafe','text':'<script>BAD</script>'})
    t.end(child,{'why':'A concise public decision'});t.end(parent)
    records=t.records();assert records[1]['parent']==parent
    assert 'secret123' not in json.dumps(records) and 'unsafe' not in json.dumps(records)
    out=tmp_path/'view.html';t.export(out)
    assert '<script>BAD</script>' not in out.read_text() and '\\u003cscript' in out.read_text()


def test_actual_common_agent_records_prompt_tools_decisions_and_results(tmp_path):
    team,_=make(tmp_path);assert team.run()['status']=='completed'
    records=team.trace.records();model=next(r for r in records if r['kind']=='model')
    assert model['input']['system_prompt'] and model['input']['messages'] and model['input']['available_tools']
    assert model['output']['selected_action']['why']
    assert any(r['kind']=='tool' for r in records)


def test_dataset_tool_rejects_host_path_and_registers_only_workspace_files(tmp_path):
    team,_=make(tmp_path);a=worker(team);(a.workspace/'labels.txt').write_text('public')
    packet={'name':'public','files':{'labels':'labels.txt'},'metadata':{'split':'train'}}
    ref=team.training.dispatch(a,{'tool':'register_dataset','argument':json.dumps(packet)},10)
    assert ref['dataset_id'] in team.training.state['datasets']
    packet['files']['labels']='../private-labels'
    with pytest.raises(ValueError,match='escapes'):team.training.dispatch(a,{'tool':'register_dataset','argument':json.dumps(packet)},10)


def test_trace_links_synchronous_child_to_actual_delegate_call(tmp_path):
    from test_team import task, Scripted, action, FakeSandbox
    from goalagent.team import Team
    def provider(config):
        if config['id']=='coordinator':return Scripted([
            action('delegate',{'agent':'planner','objective':'Write a concrete note','success_criteria':'A delivered note','inputs':{}}),
            action('submit_report',{'status':'DONE','summary':'Fixture finished','files':[]})])
        return Scripted([action('write_file',{'path':'note.md','content':'A note'}),
                         action('submit_report',{'status':'DONE','summary':'Delivered','files':['note.md']})])
    team=Team(tmp_path,task(),provider_factory=provider,sandbox_factory=FakeSandbox)
    team.run();records=team.trace.records();delegate=next(r for r in records if r['kind']=='tool' and r['name']=='delegate')
    child=next(r for r in records if r['kind']=='agent' and r['name']=='planner')
    assert child['parent']==delegate['id']


def test_live_output_read_rejects_parent_link_replaced_after_path_check(tmp_path,monkeypatch):
    import goalagent.sandbox as sandbox
    root=tmp_path/'root';sub=root/'sub';sub.mkdir(parents=True);(sub/'file').write_text('public')
    outside=tmp_path/'outside';outside.mkdir();(outside/'file').write_text('protected')
    original=sandbox.workspace_path
    def replace_after_check(base,relative):
        result=original(base,relative)
        sub.rename(root/'held');sub.symlink_to(outside,target_is_directory=True)
        return result
    monkeypatch.setattr(sandbox,'workspace_path',replace_after_check)
    with pytest.raises(OSError):sandbox.read_file(root,'sub/file')


def test_output_inventory_is_bounded_and_does_not_follow_external_links(tmp_path):
    from goalagent.training import output_inventory
    out=tmp_path/'out';out.mkdir()
    for i in range(200):(out/str(i)).write_text('x')
    (out/'escape').symlink_to(tmp_path,target_is_directory=True)
    assert len(output_inventory(out))==128


def test_job_completion_assertion_cannot_use_running_status(tmp_path):
    from goalagent.claim_checks import validate_claims
    team,_=make(tmp_path)
    report={'execution_records':[{'action':'job_completed','target':'job-test','evidence_ids':['action-job-test']}]}
    record={'assignment_id':'worker','target':'job-test','receipt':{'tool':'job_status','observation':{'status':'RUNNING'}}}
    team.record('action-job-test',record)
    with pytest.raises(ValueError,match='SUCCEEDED'):validate_claims(team,report,{'task_id':'worker'})
