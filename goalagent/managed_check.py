"""Real Docker + scripted decisions: work, negative measurement, improve and review.

This is an integration fixture, not autonomous research or recognition evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .team import Team
from .team_evaluators import EVALUATORS
from .contracts import atomic_json


def action(tool, data):
    return {'tool':tool,'argument':data if isinstance(data,str) else json.dumps(data),
            'why':'Deterministic managed-runtime verification'}


class Decisions:
    def __init__(self, role):self.role=role
    def call(self,prompt,schema,folder,**kwargs):
        c=json.loads(prompt.split('Task data:\n',1)[1]);a=c['assignment'];history=c['recent_actions']
        used=[r['tool'] for r in history]
        if self.role=='coordinator':
            current=c['team']['workflow']['candidate']
            measured=next((r for r in reversed(history) if r['tool']=='evaluate' and r.get('argument')==current),None)
            if not measured:return action('evaluate',current),{'fixture':'scripted'}
            if not measured['observation']['measurement']['accepted']:
                return action('propose_decision',{'decision':'REVISE','candidate':current,
                    'state_revision':c['team']['workflow']['state_revision'],'owner':'engineering',
                    'resume_when':'Protected output retains duplicate values','rationale':'The measured first result dropped a duplicate'}),{}
            return action('propose_decision',{'decision':'ADVANCE','candidate':current,
                'state_revision':c['team']['workflow']['state_revision'],'rationale':'All required reviews and protected measurement pass'}),{}
        if a.get('review_of'):
            if 'read_file' not in used:
                name='report.md' if self.role=='report_reader' else 'result.json'
                return action('read_file',{'path':'inputs/parent/'+name}),{}
            if 'review_gate' not in used:
                return action('review_gate',{'gate_id':a['acceptance_checks'][0]['check_id'],
                    'candidate':a['review_of'],'verdict':'PASS','evidence_ids':[a['candidate_receipt_id']],
                    'summary':'Scripted bounded review; scientific quality is not inferred'}),{}
            return action('submit_report',{'status':'DONE','summary':'Fixture review delivered','files':[]}),{}
        written=c['authored_files']
        if 'sorter.py' not in written:
            transform='sorted(values)' if a['mode']=='improve' else 'sorted(set(values))'
            source='import json\nfrom pathlib import Path\nvalues=json.loads(Path("inputs/numbers.json").read_text())\nPath("result.json").write_text(json.dumps('+transform+'))\nprint("wrote result.json")\n'
            return action('write_file',{'path':'sorter.py','content':source}),{}
        if 'report.md' not in written:
            return action('write_file',{'path':'report.md','content':'# Sorting fixture\nThis program sorts public values. Protected measurement checks duplicate preservation. No research-quality claim.'}),{}
        if 'run' not in used:return action('run','python sorter.py'),{}
        return action('submit_report',{'status':'DONE','summary':'Executed output ready for protected comparison',
                                      'files':['sorter.py','report.md','result.json']}),{}


def verify(folder):
    folder=Path(folder)
    bindings={'engineering':'experiment_engineer','research':'researcher','auditor':'critic',
              'experience':'experience','strategy':'strategy','environment':'environment_engineer','report_reader':'report_reader'}
    task={'goal':'Sort the public values and preserve every duplicate','inputs':{'numbers.json':'[4,1,3,1]'},
          'evaluator':'sorted_numbers','network':False,
          'budget':{'max_calls':100,'max_seconds':600,'max_assignments':30,'max_depth':2},
          'workflow':{'mode':'research','policy_version':2,'role_bindings':bindings,'stages':[
              {'id':'R0','description':'Implement sorting and deliver the actual result','owner':'engineering',
               'required_outputs':['result.json','report.md'],'required_tools':['run'],
               'required_reviewers':['auditor','experience','report_reader'],
               'review_scopes':{'report_reader':'report_only'},'report_paths':['report.md'],
               'gates':[{'id':'exact-result','kind':'evaluation','criterion':'Duplicates retained','accepted':True}]}]}}
    team=Team(folder,task,provider_factory=lambda c:Decisions(c['id']),evaluators=EVALUATORS)
    outcome=team.run()
    owners=[j for j in team.managed.board.jobs.values() if j['kind']=='owner']
    assert outcome['status']=='completed' and team.state['goal_met']
    assert len(owners)==1 and len(owners[0]['attempts'])==2
    measurements=[team.state['evaluations'][aid]['accepted'] for aid in owners[0]['attempts']]
    assert measurements==[False,True]
    count=team.state['calls'];team.close()
    restored=Team(folder,task,provider_factory=lambda c:Decisions(c['id']),evaluators=EVALUATORS)
    restored.run();assert restored.state['calls']==count
    result={'status':'passed','model':'scripted decisions; no live reasoning','real_docker':True,
        'work_id':owners[0]['work_id'],'owner_attempts':2,'protected_acceptance':measurements,
        'required_reviewers':['critic','experience','report_reader'], 'reserved_calls':count,
        'resume_added_calls':0,'scope':'Execution, work identity, protected failure/improvement, report-only handoff and all-role reviews; not research quality'}
    atomic_json(folder/'verification.json',result);restored.close();return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',required=True)
    print(json.dumps(verify(parser.parse_args().run_dir),indent=2))
