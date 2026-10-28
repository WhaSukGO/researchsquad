"""Real-container checkpoint and evidence-driven branch fixture; model choices are scripted."""
import argparse
import json
from pathlib import Path
from .contracts import atomic_json
from .team import Team
from .team_evaluators import EVALUATORS
from .team_check import action

TASK={'goal':'Return every public number in ascending order, preserving duplicates.',
      'inputs':{'numbers.json':'[4,1,3,1]'},'network':False,'unlimited':True,
      'evaluator':'sorted_numbers','budget':{'max_calls':None,'max_seconds':None,'max_assignments':None,'max_depth':None}}


class Provider:
    def __init__(self,config):self.role=config['id']
    def call(self,prompt,schema,folder,**kwargs):
        context=json.loads(prompt.split('Task data:\n')[1]);step=int(Path(folder).name)
        previous=context['recent_actions'][-1]['observation'] if context['recent_actions'] else {}
        if self.role=='coordinator':
            if step==1:result=action('delegate',{'agent':'experiment_engineer','objective':'Implement an initial sorter and preserve a checkpoint','success_criteria':'A runnable candidate with a checkpoint before submission','inputs':{'inputs/numbers.json':'inputs/numbers.json'}})
            elif step==2:
                assert previous['outcome']['status']=='checkpointed'
                result=action('continue_assignment',{'assignment_id':previous['assignment_id'],'checkpoint_id':previous['checkpoint_id'],'guidance':'Submit the preserved candidate now so the protected evaluator can measure it'})
            elif step==3:result=action('evaluate',previous['assignment_id'])
            elif step==4:
                assert previous['measurement']['accepted'] is False
                result=action('delegate',{'agent':'experiment_engineer','objective':'Preserve duplicate values after the protected comparison rejected the deduplicated output','success_criteria':'Sorted complete input retains duplicates','parent':previous['assignment_id'],'mode':'improve'})
            elif step==5:result=action('evaluate',previous['assignment_id'])
            elif step==6:
                assert previous['measurement']['accepted'] is True
                result=action('propose_decision',{'decision':'ADVANCE','state_revision':context['team']['state_revision'],'candidate':previous['assignment_id'],'rationale':'Protected exact comparison now passes','evidence_ids':[previous['evidence_id']]})
            else:raise AssertionError('Unexpected coordinator step')
        elif context['assignment']['mode']=='explore':
            if step==1:
                result=action('run',"python - <<'PY'\nimport json\nfrom pathlib import Path\np=Path('sorter.py');p.write_text(\"import json\\nvalues=json.load(open('inputs/numbers.json'))\\njson.dump(sorted(set(values)),open('result.json','w'))\\n\")\nexec(p.read_text())\nprint('Initial implementation ran; duplicates were removed')\nPY")
            elif step==2:result=action('checkpoint',{'summary':'Initial runnable sorter preserved','findings':['The implementation removes duplicates; independent measurement is still needed'],'failures':[],'next_test':'Submit for the protected complete-input comparison','files':['sorter.py','result.json']})
            elif step==3:
                assert 'protected evaluator' in context['coordinator_guidance']
                result=action('submit_report',{'status':'DONE','summary':'Initial implementation ready for measurement','files':['sorter.py','result.json']})
            else:raise AssertionError('Unexpected initial engineer step')
        else:
            assert context['assignment']['inputs']['numbers.json']['inherited_from']==context['assignment']['parent']
            if step==1:result=action('run',"python - <<'PY'\nfrom pathlib import Path\np=Path('sorter.py');p.write_text(Path('inputs/parent/sorter.py').read_text().replace('sorted(set(values))','sorted(values)'))\nexec(p.read_text())\nprint('Retained duplicates in the revised candidate')\nPY")
            elif step==2:result=action('submit_report',{'status':'DONE','summary':'Revised implementation retains duplicates','files':['sorter.py','result.json']})
            else:raise AssertionError('Unexpected revised engineer step')
        atomic_json(Path(folder)/'scripted-action.json',result)
        return result,{'provider':'scripted-checkpoint-verification'}


def verify(folder):
    team=Team(folder,TASK,provider_factory=Provider,evaluators=EVALUATORS)
    outcome=team.run()
    measurements=list(team.state['evaluations'].values())
    assert outcome['status']=='completed'
    assert [m['accepted'] for m in measurements]==[False,True]
    assert team.state['workflow']['run_status']=='COMPLETED' and team.state['goal_met']
    assert [entry['periods'] for entry in team.state['assignments'].values()]==[2,1]
    calls=team.state['calls']
    restored=Team(folder,TASK,provider_factory=Provider,evaluators=EVALUATORS)
    restored.run();assert restored.state['calls']==calls
    result={'status':'passed','provider':'scripted decisions; no live model reasoning','real_docker':True,
            'budget':team.task['budget'],'calls_reserved':calls,'assignments':2,'checkpoint_continuations':1,
            'protected_acceptance':[m['accepted'] for m in measurements],'resume_added_calls':0,
            'scope':'Shell-created artifacts, exact input handoff, continuation, inherited inputs, measured branch revision and host-enforced completion. No music accuracy claim.'}
    atomic_json(Path(folder)/'verification.json',result)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',required=True);args=parser.parse_args()
    print(json.dumps(verify(args.run_dir),indent=2))
