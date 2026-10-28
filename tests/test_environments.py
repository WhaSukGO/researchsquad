"""Readiness, input handoffs and setup budgets are independent of model quality."""
import copy
import json
from pathlib import Path
import pytest
from goalagent.contracts import atomic_json, digest
from goalagent.inputs import resolve_inputs, deliver_inputs, verify_inputs
from goalagent.environments import EnvironmentManager, validate_recipe, dockerfile
from goalagent.research import ResearchTools
from goalagent.coordinator import CoordinatorRunner
from goalagent.sandbox import DockerSandbox, log_summary
from goalagent.worker import ExperimentWorker
from tests.test_research import SPEC, Scripted, FakeSandbox, assignment, decision, action, worker_actions


class FakeEnvironments:
    status='ready'
    def __init__(self,*args):
        self.state={'attempts':0,'model_calls':0,'active_seconds':0,'events':[]}
    def ensure(self,*args):
        return {'status':self.status,'image':{'id':'fixture'},'cache_hit':True}


def managed(tmp_path, actions=None, env=FakeEnvironments):
    spec=copy.deepcopy(SPEC);spec['environment']={'max_attempts':2,'max_model_calls':1,'max_seconds':100}
    provider=Scripted(actions or worker_actions())
    tools=ResearchTools(tmp_path,spec,'test-double',provider,FakeSandbox,env)
    return tools,provider,spec


def cfg(required=None):return {**assignment(),'required_inputs':required or [],'environment':'music-python'}


def test_actual_baseline_handoff_contains_no_labels(tmp_path):
    tools,_,_=managed(tmp_path)
    contract=resolve_inputs(['baseline:audiveris-enlarged'],tools.selected())
    assert {x['sample'] for x in contract['files']}=={i for i,_ in tools.selected()}
    assert all(x['source'].startswith('runs/first-benchmark/') for x in contract['files'])
    deliver_inputs(contract,tmp_path/'workspace');verify_inputs(contract,tmp_path/'workspace')
    first=tmp_path/'workspace'/contract['files'][0]['path'];first.write_text('changed')
    with pytest.raises(ValueError,match='changed'):verify_inputs(contract,tmp_path/'workspace')


def test_missing_input_prevents_dispatch_and_experiment_reservation(tmp_path,monkeypatch):
    tools,provider,spec=managed(tmp_path)
    runner=CoordinatorRunner(spec,tmp_path,Scripted([]),tools)
    runner.state['known_evidence'] += ['dataset','baseline','evidence-source']
    import goalagent.research as module
    def missing(*args):raise ValueError('Missing required baseline prediction')
    monkeypatch.setattr(module,'resolve_inputs',missing)
    with pytest.raises(ValueError,match='Missing required'):
        runner.validate_action(decision('run_experiment',cfg(['baseline:audiveris-enlarged']),['baseline']))
    assert not provider.prompts and not runner.state['experiments']


def test_baseline_sources_and_environment_are_sealed(tmp_path):
    tools,provider,_=managed(tmp_path)
    config=cfg(['baseline:audiveris-enlarged']);tools.prepare_assignment(decision('run_experiment',config))
    r=tools.run_experiment(config,lambda:None,lambda:100)
    folder=tmp_path/'experiments'/r['id'];seal=tools.verify_seal(folder)
    assert 'environment.json' in seal['files']
    assert 'baselines/' in provider.prompts[0] and 'input_contract' in provider.prompts[0]
    assert not list((folder/'worker/workspace').rglob('reference*'))
    assert all('research/data/' not in x for x in json.loads((folder/'source-snapshot.json').read_text()))
    (folder/'environment.json').write_text('{}')
    with pytest.raises(ValueError,match='integrity'):tools.verify_seal(folder)


def test_setup_failure_does_not_consume_scientific_experiment(tmp_path):
    class Blocked(FakeEnvironments):status='environment_blocked'
    tools,workers,spec=managed(tmp_path,env=Blocked)
    lead=Scripted([decision('inspect_dataset'),decision('baseline_summary'),decision('read_evidence','music-benchmark'),
        decision('run_experiment',cfg(),['baseline']),decision('finish')])
    runner=CoordinatorRunner(spec,tmp_path,lead,tools);s=runner.run()
    assert not s['experiments'] and not s['evaluations'] and not workers.prompts
    assert s['history'][3]['observation']['status']=='environment_blocked'
    assert s['model_calls']==5


def test_experiment_requests_setup_without_doing_it(tmp_path):
    tools,_,_=managed(tmp_path,[action('write_file',{'path':'main.py','content':'# progress'}),
                              action('request_environment','Need scipy==1.16.2; import scipy is unavailable')])
    config=cfg();tools.prepare_assignment(decision('run_experiment',config));r=tools.run_experiment(config,lambda:None,lambda:100)
    assert r['worker']['status']=='environment_blocked'
    assert 'scipy' in r['worker']['last_observation']['requirements']
    assert json.loads((tmp_path/'experiments'/r['id']/'source-snapshot.json').read_text())['main.py']=='# progress'


def test_managed_commands_protect_baselines_and_disable_network(tmp_path):
    (tmp_path/'inputs').mkdir();(tmp_path/'baselines').mkdir()
    policy={**SPEC['worker'],'network':False,'managed_environment':True}
    command=DockerSandbox(tmp_path,policy).command('python experiment.py')
    assert command[command.index('--network')+1]=='none'
    assert any('dst=/workspace/baselines,readonly' in x for x in command)
    assert '--read-only' in command and 'PIP_NO_INDEX=1' in command
    worker=ExperimentWorker(tmp_path.parent,{},Scripted([]),policy,FakeSandbox)
    worker.workspace=tmp_path
    with pytest.raises(ValueError,match='read-only'):
        worker.execute(action('write_file',{'path':'baselines/result.krn','content':'fake'}),1)


def test_log_keeps_first_failure_when_tail_is_noise(tmp_path):
    log=tmp_path/'build.log';log.write_text('ERROR: missing native library\n'+'noise\n'*2000)
    r=log_summary(log)
    assert 'missing native' in r['first_diagnostic'] and len(r['tail'].encode())<=4000


def fake_manager(tmp_path,provider=None):
    m=object.__new__(EnvironmentManager)
    m.run_dir=tmp_path;m.folder=tmp_path/'run';m.folder.mkdir(exist_ok=True)
    m.registry=tmp_path/'registry';m.registry.mkdir(exist_ok=True)
    m.state_path=m.folder/'state.json';m.state={'attempts':0,'model_calls':0,'active_seconds':0,'events':[],'requests':{}}
    m.settings={'max_attempts':2,'max_model_calls':1,'max_seconds':30};m.policy=SPEC['worker'];m.provider=provider or Scripted([])
    m.platform='arm64';m.recipe=json.loads(Path('environments/music-python/recipe.json').read_text())
    m.smoke='fixture';m.dependencies='pinned==1.0';m.inspect_image=lambda image:{'id':'sha256:fixture','architecture':'arm64','os':'linux'}
    return m


def ready_builder(m,calls):
    def build(recipe,folder,remaining):
        calls.append(recipe);folder.mkdir(parents=True,exist_ok=True)
        (folder/'resolved-lock.txt').write_text('installed versions')
        import hashlib
        return {'status':'ready','image':m.inspect_image('fixture'),
                'lock_sha256':hashlib.sha256(b'installed versions').hexdigest(),'diagnostic':{'exit_code':0}}
    return build


def test_cached_image_reused_and_dependencies_invalidate(tmp_path):
    m=fake_manager(tmp_path);calls=[];m.build_and_test=ready_builder(m,calls)
    first=m.ensure(lambda:pytest.fail('No engineer for ready recipe'),lambda:30)
    second=m.ensure(lambda:pytest.fail('No engineer for cache'),lambda:30)
    assert not first['cache_hit'] and second['cache_hit'] and len(calls)==1
    m.dependencies+='changed';third=m.ensure(lambda:None,lambda:30)
    assert not third['cache_hit'] and len(calls)==2


@pytest.mark.parametrize('field',['platform','smoke','dependencies'])
def test_readiness_key_changes_with_contract(tmp_path,field):
    m=fake_manager(tmp_path);before=m.key(m.recipe);setattr(m,field,'different');assert before!=m.key(m.recipe)


def test_missing_image_or_lock_never_reuses_readiness(tmp_path):
    m=fake_manager(tmp_path);calls=[];m.build_and_test=ready_builder(m,calls);m.ensure(lambda:None,lambda:30)
    key=m.key(m.recipe);(m.registry/key/'resolved-lock.txt').write_text('tampered')
    assert not m.ensure(lambda:None,lambda:30)['cache_hit'] and len(calls)==2
    m.inspect_image=lambda image:None
    r=m.ensure(lambda:None,lambda:30);assert r['status']=='environment_blocked'


def test_environment_engineer_has_bounded_calls_and_separate_prompt(tmp_path):
    base=json.loads(Path('environments/music-python/recipe.json').read_text())
    engineer=Scripted([{'system_packages':base['system_packages'],'python_packages':base['python_packages']+['scipy==1.16.2'],'reason':'Add missing module'}])
    m=fake_manager(tmp_path,engineer);calls=[];m.build_and_test=ready_builder(m,calls);charges=[]
    result=m.ensure(lambda:charges.append(1),lambda:30,'scipy import missing')
    assert result['status']=='ready' and len(charges)==1
    assert 'not the research engineer or evaluator' in engineer.prompts[0]
    assert 'reference.krn' not in engineer.prompts[0]
    result=m.ensure(lambda:pytest.fail('Do not call engineer again'),lambda:30)
    assert result['cache_hit'] and len(calls)==1 and 'scipy==1.16.2' in m.state['active_recipe']['python_packages']
    assert m.ensure(lambda:None,lambda:30,'Another missing package')['status']=='environment_blocked'


def test_no_weakened_smoke_or_build_injection(tmp_path):
    m=fake_manager(tmp_path)
    for field,value in [('base','python:latest'),('system_packages',['pkg; cat /secret']),('python_packages',['https://arbitrary/script'])]:
        recipe=copy.deepcopy(m.recipe);recipe[field]=value if field=='base' else value
        with pytest.raises(ValueError):dockerfile(recipe)

@pytest.mark.skipif(__import__('os').environ.get('GOALAGENT_DOCKER_TESTS') != '1', reason='Real Docker publication regression')
def test_two_registries_never_replace_an_image_already_handed_off(tmp_path):
    from goalagent.environment_check import NoModel
    spec=json.loads(Path('goals/music-research-v2.json').read_text())
    first=EnvironmentManager(tmp_path/'first',spec['environment'],spec['worker'],NoModel(),tmp_path/'registry-a')
    a=first.ensure(lambda:None,lambda:900);assert a['status']=='ready',a
    second=EnvironmentManager(tmp_path/'second',spec['environment'],spec['worker'],NoModel(),tmp_path/'registry-b')
    b=second.ensure(lambda:None,lambda:900);assert b['status']=='ready',b
    assert a['cache_key']==b['cache_key']
    assert a['published_tag']!=b['published_tag']
    assert first.inspect_image(a['image']['id'])==a['image']
    workspace=tmp_path/'old-worker'
    for name in ('inputs','output','tmp'):(workspace/name).mkdir(parents=True,exist_ok=True)
    sandbox=DockerSandbox(workspace,{**spec['worker'],'image':a['image']['id'],'network':False,'managed_environment':True})
    r=sandbox.run('python -c "import music21; print(42)"',tmp_path/'old-image.log',30)
    assert r['exit_code']==0,r
