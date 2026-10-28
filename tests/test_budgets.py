import copy
import json
import math
import sys

import pytest

from goalagent.configuration import validate_agent
from goalagent.provider import run_process
from goalagent.team import Team
from test_team import FakeSandbox, Scripted, action, task


def test_unlimited_team_crosses_old_call_and_agent_step_limits(tmp_path):
    spec=task();spec['unlimited']=True
    prompts=[]
    def check(prompt):
        data=json.loads(prompt.split('Task data:\n',1)[1])
        assert data['remaining_steps'] is None and data['remaining_seconds'] is None
        assert 'Infinity' not in prompt
        prompts.append(prompt)
        return action('write_file',{'path':'report.txt','content':'progress'})
    def provider(config):
        assert all(v is None for v in config['limits'].values())
        return Scripted([check]*45+[action('finish',{'summary':'done','files':['report.txt']})])
    team=Team(tmp_path,spec,provider_factory=provider,sandbox_factory=FakeSandbox)
    assert math.isinf(team.remaining())
    assert all(v is None for v in team.task['budget'].values())
    assert team.run()['status']=='submitted'
    assert team.state['calls']==46 and len(prompts)==45
    assert team.state['active_seconds']>=0
    restored=Team(tmp_path,spec,provider_factory=lambda c:Scripted([]),sandbox_factory=FakeSandbox)
    restored.run()
    assert restored.state['calls']==46
    assert 'Infinity' not in (tmp_path/'team-contract.json').read_text()


def test_null_limits_supported_individually_and_invalid_values_rejected(tmp_path):
    spec=task();spec['budget']['max_calls']=None
    team=Team(tmp_path,spec,sandbox_factory=FakeSandbox)
    team.state['calls']=1000000;team.charge()
    assert team.state['calls']==1000001
    assert team.task['budget']['max_seconds']==120
    c=copy.deepcopy(team.definitions['planner']);c['limits']['max_steps']=None
    validate_agent(c)
    for value in [0,-1,False,'unlimited']:
        c['limits']['max_steps']=value
        with pytest.raises(ValueError):validate_agent(c)


def test_unlimited_native_model_process_has_no_overflow(tmp_path):
    code,out,err=run_process([sys.executable,'-c','print("completed")'],timeout=math.inf,cwd=tmp_path)
    assert code==0 and out.strip()=='completed'


def test_changing_budget_mode_requires_fresh_run(tmp_path):
    team=Team(tmp_path,task(),sandbox_factory=FakeSandbox);team.close()
    spec=task();spec['unlimited']=True
    with pytest.raises(ValueError,match='contract changed'):Team(tmp_path,spec,sandbox_factory=FakeSandbox)

@pytest.mark.skipif(__import__('os').environ.get('GOALAGENT_DOCKER_TESTS')!='1',reason='Opt-in real Docker test')
def test_real_unlimited_agent_command_finishes_and_records_usage(tmp_path):
    spec=task();spec['unlimited']=True
    def provider(config):return Scripted([
        action('run',"python -c 'print(42)'"),
        action('write_file',{'path':'report.txt','content':'completed'}),
        action('finish',{'summary':'done','files':['report.txt']})])
    team=Team(tmp_path,spec,provider_factory=provider)
    outcome=team.run_agent('engineer',team.definitions['experiment_engineer'],{'objective':'Run a real command without a deadline'})
    assert outcome['status']=='submitted' and team.state['calls']==3
    result=json.loads((tmp_path/'agents/engineer/actions/001.json').read_text())['observation']
    assert result['exit_code']==0 and result['tail'].strip()=='42'
    team.close()
