import copy
import json
from pathlib import Path
import pytest
from goalagent.agent import Agent
from goalagent.configuration import load_agent
from goalagent.team import Team, ROOT
from goalagent.team_evaluators import EVALUATORS
from goalagent.toolkit import Tool,default_registry

class FakeSandbox:
    def __init__(self,workspace,policy):self.workspace=Path(workspace);self.policy=policy
    def preflight(self):return {'image':'fixture','policy':self.policy}
    def cleanup(self):pass
    def run(self,command,log,timeout):return {'exit_code':0,'interrupted':False,'tail':'fixture, not executed'}
class Scripted:
    def __init__(self,actions):self.actions=iter(actions);self.calls=0
    def call(self,prompt,schema,folder,**kwargs):
        self.calls+=1;action=next(self.actions)
        return (action(prompt) if callable(action) else action),{}
def action(tool,data=''):
    return {'tool':tool,'argument':data if isinstance(data,str) else json.dumps(data),'why':'verification'}
def task():
    return {'goal':'Produce ascending numbers from public input','inputs':{'numbers.json':'[4,1,3,1]'},'evaluator':'sorted_numbers','network':False,
            'budget':{'max_calls':30,'max_seconds':120,'max_assignments':6,'max_depth':2}}
def make(tmp_path,**kwargs):return Team(tmp_path,task(),sandbox_factory=FakeSandbox,**kwargs)
def instance(team,role='coordinator'):
    c=copy.deepcopy(team.definitions[role]);a=Agent(team.folder/'agents'/'test',{'depth':0},Scripted([]),team.policy(c),c,team.registry,FakeSandbox);a.state['steps']=1;return a

def test_role_catalog_and_independent_model_selection(tmp_path):
    captured=[]
    def provider(c):
        captured.append((c['id'],c['model'],c['reasoning_effort']))
        return Scripted([action('write_file',{'path':'report.txt','content':'done'}),action('finish',{'summary':'done','files':['report.txt']})])
    team=make(tmp_path,provider_factory=provider)
    assert set(team.definitions)=={'coordinator','planner','researcher','experiment_engineer','environment_engineer','critic'}
    assert team.run()['status']=='submitted'
    assert not team.state['goal_met']
    assert captured==[('coordinator',None,'low')]

def test_tool_grants_enforced_at_dispatch(tmp_path):
    team=make(tmp_path);a=instance(team,'critic')
    assert 'run' not in a.schema['properties']['tool']['enum']
    with pytest.raises(ValueError,match='not granted'):a.execute(action('run','echo bad'),1)

def test_config_and_tool_version_changes_block_resume(tmp_path):
    team=make(tmp_path);a=instance(team);a.save()
    c=copy.deepcopy(a.config);c['system_prompt']+=' changed'
    with pytest.raises(ValueError,match='contract changed'):Agent(a.folder,a.assignment,a.provider,a.policy,c,team.registry,FakeSandbox)

def test_specialists_are_config_only_and_cannot_escalate(tmp_path):
    team=make(tmp_path);a=instance(team)
    request={'id':'data_analyst','template':'planner','system_prompt':'Analyze tabular inputs','tools':['read_file','write_file','finish']}
    assert a.execute(action('create_specialist',request),1)['created']=='data_analyst'
    assert team.definitions['data_analyst']['model']==team.definitions['planner']['model']
    request.update(id='bad',tools=['run'])
    with pytest.raises(ValueError,match='expand'):a.execute(action('create_specialist',request),1)
    team.close()
    restored=make(tmp_path)
    assert 'data_analyst' in restored.definitions

def test_delegate_copies_only_explicit_inputs_and_is_idempotent(tmp_path):
    providers=[]
    def provider(c):
        p=Scripted([action('read_file',{'path':'inputs/public.txt'}),action('write_file',{'path':'report.txt','content':'observed'}),action('finish',{'summary':'done','files':['report.txt']})]);providers.append(p);return p
    team=make(tmp_path,provider_factory=provider);a=instance(team)
    (a.workspace/'public.txt').write_text('public');(a.workspace/'secret.txt').write_text('do not share')
    request=action('delegate',{'agent':'planner','objective':'Plan a comparison','success_criteria':'A testable plan','inputs':{'public.txt':'public.txt'}})
    first=a.execute(request,30);second=a.execute(request,30)
    assert first==second and len(providers)==1
    child=team.folder/'agents'/first['assignment_id']
    assert (child/'workspace/inputs/public.txt').read_text()=='public'
    assert not (child/'workspace/secret.txt').exists()
    assert (a.workspace/first['artifacts'][0]).read_text()=='observed'

def test_budget_and_depth_reject_dispatch(tmp_path):
    team=make(tmp_path);a=instance(team);a.assignment['depth']=2
    with pytest.raises(ValueError,match='depth'):a.execute(action('delegate',{'agent':'planner','objective':'Plan','success_criteria':'criteria','inputs':{}}),1)
    team.state['calls']=30
    with pytest.raises(TimeoutError):team.charge()

def test_evaluator_is_host_registered_and_submission_is_sealed(tmp_path):
    def provider(c):return Scripted([action('write_file',{'path':'result.json','content':'[1,1,3,4]'}),action('finish',{'summary':'exact','files':['result.json']})])
    team=make(tmp_path,provider_factory=provider,evaluators=EVALUATORS);a=instance(team)
    result=a.execute(action('delegate',{'agent':'experiment_engineer','objective':'Sort input','success_criteria':'Ascending values','inputs':{}}),30)
    id=result['assignment_id'];measured=a.execute(action('evaluate',id),30)
    assert measured['measurement']['accepted'] and team.state['goal_met']
    (team.folder/'agents'/id/'source-snapshot.json').write_text('{}')
    with pytest.raises(ValueError,match='changed'):a.execute(action('evaluate',id),30)

def test_improve_requires_evaluation_and_distinct_assignment(tmp_path):
    team=make(tmp_path);a=instance(team)
    with pytest.raises(ValueError,match='Translate'):a.execute(action('delegate',{'agent':'planner','objective':task()['goal'],'success_criteria':'x'}),1)
    team.state['assignments']['prior']={}
    with pytest.raises(ValueError,match='Measure'):a.execute(action('delegate',{'agent':'planner','objective':'Improve','success_criteria':'x','parent':'prior','mode':'improve'}),1)

def test_extension_test_registration_and_permissions(tmp_path):
    team=make(tmp_path);a=instance(team,'experiment_engineer');(a.workspace/'tool.py').write_text('print(42)')
    result=a.execute(action('register_tool',{'name':'answer','description':'Return answer','script':'tool.py','test_argument':{}}),1)
    assert result['registered']=='script.answer'
    with pytest.raises(ValueError,match='not granted'):a.execute(action('script.answer',{}),1)
    assert 'script.answer' not in team.definitions['critic']['tools']
    team.close()
    restored=make(tmp_path);assert 'script.answer' in restored.registry.tools

def test_failed_extension_does_not_register(tmp_path):
    team=make(tmp_path);a=instance(team,'experiment_engineer');(a.workspace/'bad.py').write_text('raise RuntimeError()')
    a.sandbox.run=lambda *args:{'exit_code':1,'interrupted':False}
    assert a.execute(action('register_tool',{'name':'bad','description':'bad','script':'bad.py','test_argument':{}}),1)['status']=='test_failed'
    assert not team.state['extensions']

def test_network_tools_obey_owner_policy(tmp_path):
    team=make(tmp_path);a=instance(team,'researcher')
    with pytest.raises(ValueError,match='Network'):a.execute(action('web_fetch','https://example.com'),1)

def test_team_resume_does_not_repeat_finished_calls(tmp_path):
    def provider(c):return Scripted([action('write_file',{'path':'report.txt','content':'done'}),action('finish',{'summary':'done','files':['report.txt']})])
    team=make(tmp_path,provider_factory=provider);team.run();calls=team.state['calls']
    resumed=make(tmp_path,provider_factory=lambda c:Scripted([]));resumed.run()
    assert resumed.state['calls']==calls

def test_prompt_path_cannot_escape_configuration(tmp_path):
    c=json.loads((ROOT/'agents/default/planner.json').read_text());c['system_prompt']='../secret'
    p=tmp_path/'role.json';p.write_text(json.dumps(c))
    with pytest.raises(ValueError):load_agent(p)

def test_active_team_lock_prevents_concurrent_state_mutation(tmp_path):
    team=make(tmp_path)
    with pytest.raises(BlockingIOError):make(tmp_path)
    assert team.state['calls']==0
    team.close()
    assert make(tmp_path).state['calls']==0

def test_evaluator_version_change_invalidates_resume(tmp_path):
    from goalagent.team_evaluators import Evaluator,sorted_numbers
    team=make(tmp_path,evaluators=EVALUATORS);team.close()
    with pytest.raises(ValueError,match='contract changed'):make(tmp_path,evaluators={'sorted_numbers':Evaluator('v2',sorted_numbers)})

def test_binary_asset_hash_pins_explicit_inputs(tmp_path):
    asset=tmp_path/'image.bin';asset.write_bytes(b'public bytes')
    spec=task();spec['assets']={'example.bin':str(asset)}
    team=Team(tmp_path/'run',spec,sandbox_factory=FakeSandbox)
    assert team.assets['example.bin']==b'public bytes'
    team.close();asset.write_bytes(b'changed')
    with pytest.raises(ValueError,match='contract changed'):Team(tmp_path/'run',spec,sandbox_factory=FakeSandbox)

def test_environment_recipe_rejects_shell_injection_before_build(tmp_path):
    from goalagent.team_environment import prepare
    team=make(tmp_path);a=instance(team,'environment_engineer')
    with pytest.raises(ValueError,match='package'):prepare(team,a,{'system_packages':['foo; echo BAD'],'python_packages':[],'smoke_script':'x'},1)


def test_role_model_override_reaches_provider(tmp_path):
    configs=tmp_path/'configs';configs.mkdir()
    definition=json.loads((ROOT/'agents/default/coordinator.json').read_text())
    definition['model']='chosen-model';definition['system_prompt']='coordinator.md'
    (configs/'coordinator.json').write_text(json.dumps(definition));(configs/'coordinator.md').write_text('Return a report.')
    seen=[]
    def factory(c):
        seen.append(c['model'])
        return Scripted([action('write_file',{'path':'report.txt','content':'done'}),action('finish',{'summary':'done','files':['report.txt']})])
    Team(tmp_path/'run',task(),agents_dir=configs,model='fallback',provider_factory=factory,sandbox_factory=FakeSandbox).run()
    assert seen==['chosen-model']


def test_ready_environment_is_visible_to_lead_and_new_assignment(tmp_path):
    def provider(c):return Scripted([action('write_file',{'path':'report.txt','content':'ready'}),action('finish',{'summary':'ready','files':['report.txt']})])
    team=make(tmp_path,provider_factory=provider);a=instance(team)
    receipt={'image':'sha256:fixture','packages':{'system_packages':['tesseract-ocr'],'python_packages':[]}}
    team.state['environment']=receipt
    assert a.execute(action('catalog'),1)['environment']==receipt
    result=a.execute(action('delegate',{'agent':'planner','objective':'Inspect available capabilities','success_criteria':'A plan','inputs':{}}),30)
    assert team.state['assignments'][result['assignment_id']]['assignment']['environment']==receipt
