"""Prepared-image cache integrity, readiness and separate setup responsibility."""
import copy
import json
from pathlib import Path
import pytest
from goalagent.environments import EnvironmentManager, dockerfile
from goalagent.sandbox import DockerSandbox, log_summary

SPEC = json.loads(Path('goals/music-research-v2.json').read_text())

class Scripted:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []
    def call(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return next(self.actions), {'test_double': True}


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
