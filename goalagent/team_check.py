"""Deterministic non-music integration scenario using real Docker, not research-model claims."""
import argparse
import json
from pathlib import Path
from .contracts import atomic_json
from .team import Team
from .team_evaluators import EVALUATORS

TASK={'goal':'Produce the public input numbers in ascending order, retaining duplicates.',
      'inputs':{'numbers.json':'[4,1,3,1]'},'evaluator':'sorted_numbers','network':False,
      'acceptance':'The protected host comparison must match the complete ascending list.',
      'budget':{'max_calls':30,'max_seconds':180,'max_assignments':4,'max_depth':2}}
SCRIPT='''import json,sys
values=json.load(sys.stdin)
result=sorted(values)
with open('result.json','w') as f: json.dump(result,f)
print(json.dumps(result))
'''

def action(tool,data=''):
    return {'tool':tool,'argument':data if isinstance(data,str) else json.dumps(data),'why':'Deterministic integration verification'}

class ScenarioProvider:
    """Scripted decisions exercise machinery; they do not demonstrate autonomous reasoning."""
    def __init__(self,config):self.role=config['id']
    def call(self,prompt,schema,folder,**kwargs):
        context=json.loads(prompt.split('Task data:\n',1)[1]);history=context['recent_actions']
        step=int(Path(folder).name)
        if self.role=='coordinator':
            if step==1:result=action('create_specialist',{'id':'sorting_specialist','template':'experiment_engineer','system_prompt':'Use registered tools to sort the complete assigned public input. Submit result.json.','tools':['read_file','write_file','run','finish']})
            elif step==2:result=action('delegate',{'agent':'experiment_engineer','objective':'Build a reusable numeric sorting tool and submit its initial test result','success_criteria':'A registered tested tool and result.json','inputs':{}})
            elif step==3:result=action('evaluate',history[-1]['observation']['assignment_id'])
            elif step==4:
                observation=history[-1]['observation']
                assert observation['measurement']['accepted'] is False
                result=action('delegate',{'agent':'sorting_specialist','objective':'Apply the reusable sorter to the complete task input after the failed comparison','success_criteria':'Complete ascending values with duplicates retained','inputs':{'numbers.json':'inputs/numbers.json'},'parent':observation['assignment_id'],'mode':'improve'})
            elif step==5:result=action('evaluate',history[-1]['observation']['assignment_id'])
            elif step==6:
                assert history[-1]['observation']['measurement']['accepted'] is True
                result=action('write_file',{'path':'report.txt','content':'Initial test result failed the full-input comparison. The second assignment reused the registered sorter on the full input and passed protected scoring. Scripted workflow check; not autonomous research.'})
            else:result=action('finish',{'summary':'Integration fixture passed','files':['report.txt']})
        elif self.role=='experiment_engineer':
            result={1:action('write_file',{'path':'sorter.py','content':SCRIPT}),2:action('register_tool',{'name':'sort_numbers','description':'Read a JSON number array from stdin; write result.json and print ascending values.','script':'sorter.py','test_argument':[2,1]}),3:action('finish',{'summary':'Reusable sorter and initial fixture output','files':['sorter.py','result.json']})}[step]
        else:
            if step==1:result=action('read_file',{'path':'inputs/numbers.json'})
            elif step==2:result=action('script.sort_numbers',json.loads(history[-1]['observation']['text']))
            else:result=action('finish',{'summary':'Sorted complete input with registered tool','files':['result.json']})
        assert result['tool'] in schema['properties']['tool']['enum']
        atomic_json(Path(folder)/'scripted-action.json',result)
        return result,{'provider':'scripted-integration-fixture'}

def verify_environment(folder):
    from .agent import Agent
    task={**TASK,'network':True}
    team=Team(folder,task,provider_factory=ScenarioProvider,evaluators=EVALUATORS)
    config=team.definitions['environment_engineer']
    agent=Agent(team.folder/'agents'/'setup',{'objective':'Verify generic environment publication'},ScenarioProvider(config),team.policy(config),config,team.registry)
    agent.state['steps']=1
    agent.execute(action('write_file',{'path':'smoke.py','content':"import pathlib,sys; p=pathlib.Path('/workspace/tmp/probe');p.write_text('ready');assert p.read_text()=='ready';assert sys.version_info.major==3;print('READY: Python and writable temp')"}),30)
    request=action('prepare_environment',{'system_packages':[],'python_packages':[],'smoke_script':'smoke.py'})
    first=agent.execute(request,60);second=agent.execute(request,60)
    assert first['status']=='ready' and second['cache_hit'] and first['image']==second['image']
    result={'status':'passed','image':first['image'],'reuse':second['cache_hit'],'setup_attempts':team.state['setup_attempts'],'scope':'Real generic package-builder/readiness/reuse check, no model calls'}
    atomic_json(Path(folder)/'verification.json',result);team.close();return result

def verify(folder):
    team=Team(folder,TASK,provider_factory=ScenarioProvider,evaluators=EVALUATORS)
    outcome=team.run()
    evaluations=list(team.state['evaluations'].values())
    assert outcome['status']=='submitted' and [x['accepted'] for x in evaluations]==[False,True]
    assert team.state['goal_met'] and len(team.state['assignments'])==2
    calls=team.state['calls']
    resumed=Team(folder,TASK,provider_factory=ScenarioProvider,evaluators=EVALUATORS)
    resumed.run();assert resumed.state['calls']==calls
    result={'status':'passed','provider':'scripted (no model calls)','real_docker':True,'agent_runtime':'Agent for all roles',
            'specialist_created':'sorting_specialist','tool_registered':'script.sort_numbers','measurements':evaluations,
            'reserved_scripted_calls':calls,'resume_added_calls':0,'scope':'Non-music integration and evidence-driven control-flow fixture; not autonomous research or transcription accuracy.'}
    result['environment']=verify_environment(Path(folder)/'environment-check')
    atomic_json(Path(folder)/'verification.json',result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',required=True);args=parser.parse_args()
    print(json.dumps(verify(args.run_dir),indent=2))
