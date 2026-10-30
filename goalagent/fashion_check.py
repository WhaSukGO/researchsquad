"""Scripted Agent choices + real GPU learning/restart/independent evaluation fixture.

This validates the training machinery, not autonomous scientific judgment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import uuid
from .contracts import atomic_json, digest
from .team import Team,ROOT
from .team_evaluators import Evaluator

FILES={'train-images-idx3-ubyte.gz':'8d4fb7e6c68d591d4c3dfef9ec88bf0d',
       'train-labels-idx1-ubyte.gz':'25c81989df183df01b3e8a0aad5dffbe',
       't10k-images-idx3-ubyte.gz':'bef4ecab320f06d8554ea6380940ec79',
       't10k-labels-idx1-ubyte.gz':'bb300cfdad3c16e7a12a480ee83cd310'}


def download(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for name,expected in FILES.items():
        p=folder/name
        if not p.exists():
            req=urllib.request.Request('https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/'+name)
            with urllib.request.urlopen(req,timeout=120) as response:p.write_bytes(response.read(35_000_000))
        if hashlib.md5(p.read_bytes()).hexdigest()!=expected:raise ValueError('Official dataset check failed: '+name)
    return folder


class FashionEvaluator:
    def __init__(self,image,data):
        self.image=image;self.data=data
        self.version='fashion-cnn-v1-'+digest([image,FILES,(ROOT/'goalagent/fashion_model.py').read_text()])[:24]
    def run(self,weights,compare=None):
        if not compare:
            for filename in ('t10k-images-idx3-ubyte.gz','t10k-labels-idx1-ubyte.gz'):
                if hashlib.md5((self.data/filename).read_bytes()).hexdigest()!=FILES[filename]:raise ValueError('Protected test source changed')
        name='rsq-eval-'+uuid.uuid4().hex[:20]
        command=['docker','run','--name',name,'--rm','--network','none','--read-only','--cap-drop=ALL',
            '--security-opt','no-new-privileges','--memory','4g','--cpus','2','--pids-limit','64',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--user',f'{os.getuid()}:{os.getgid()}']
        def mount(src,dst):command.extend(['--mount',f'type=bind,src={src},dst={dst},readonly'])
        mount(ROOT/'goalagent/fashion_model.py','/eval.py');mount(weights,'/weights')
        if compare:
            mount(compare,'/compare');args=['--weights','/weights','--compare','/compare']
        else:
            mount(self.data/'t10k-images-idx3-ubyte.gz','/test-images')
            mount(self.data/'t10k-labels-idx1-ubyte.gz','/test-labels')
            args=['--weights','/weights','--images','/test-images','--labels','/test-labels']
        try:
            result=subprocess.run([*command,self.image,'python','/eval.py',*args],capture_output=True,text=True,timeout=300)
            if result.returncode:raise RuntimeError(result.stderr[-3000:])
            return json.loads(result.stdout)
        finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
    def __call__(self,path,job):return self.run(path)


def action(tool,arg):return {'tool':tool,'argument':arg if isinstance(arg,str) else json.dumps(arg),'why':'Scripted validation decision; not live scientific reasoning'}


class Decisions:
    def __init__(self,role,team):self.role=role;self.team=team
    def call(self,prompt,schema,folder,**kwargs):
        c=json.loads(prompt.split('Task data:\n',1)[1]);a=c['assignment'];n=int(Path(folder).name)
        runtime=self.team.training;models=list(runtime.state['models'].values());jobs=list(runtime.state['jobs'].values())
        if self.role=='coordinator':
            candidate=c['team']['workflow']['candidate']
            if n==1:return action('evaluate',candidate),{'provider':'scripted fixture'}
            return action('propose_decision',{'decision':'ADVANCE','candidate':candidate,
                'state_revision':c['team']['workflow']['state_revision'],'rationale':'Required reviews and protected model-result reference passed'}),{}
        if a.get('review_of'):
            tools=[x['tool'] for x in c['recent_actions']]
            if 'read_file' not in tools:return action('read_file',{'path':'inputs/parent/report.md'}),{}
            if 'review_gate' not in tools:return action('review_gate',{'gate_id':a['acceptance_checks'][0]['check_id'],
                'candidate':a['review_of'],'verdict':'PASS','evidence_ids':[a['candidate_receipt_id']],
                'summary':'Fixture reviews delivery and scoped claims; numerical verification belongs to the host evaluator'}),{}
            return action('submit_report',{'status':'DONE','summary':'Fixture scoped review complete','files':[]}),{}
        if any(j['status'] in {'FAILED','CANCELLED','LOST','START_FAILED','START_UNCERTAIN'} for j in jobs):
            return action('submit_report',{'status':'FAILED','failure_kind':'environment','summary':'Actual job failed; inspect its Docker log before changing the environment. No trained model or project acceptance is claimed.','files':[]}),{}
        did=next(iter(runtime.state['datasets']));dataset='/datasets/'+did
        packet={'profile':'gpu','code_files':['train.py','fashion_model.py'],'entrypoint':'train.py',
                'args':['--data',dataset,'--epochs','1'],'dataset_ids':[did]}
        actions={1:lambda:action('training_catalog',''),
            2:lambda:action('record_decision',{'summary':'Verify exact epoch-boundary resume before making research-quality claims',
                'candidates':[{'kind':'experiment','target':'uninterrupted vs resumed same-seed training','status':'SELECTED','reason':'Separates runtime resume correctness from model quality'},
                              {'kind':'experiment','target':'architecture search','status':'DEFERRED','reason':'First validate actual learning, persistence and independent scoring'}]}),
            3:lambda:action('write_file',{'path':'train.py','content':(ROOT/'goalagent/fashion_train.py').read_text()}),
            4:lambda:action('write_file',{'path':'fashion_model.py','content':(ROOT/'goalagent/fashion_model.py').read_text()}),
            5:lambda:action('start_job',packet),
            6:lambda:action('await_job',jobs[0]['id']),
            7:lambda:action('register_model',{'job_id':jobs[0]['id'],'path':'checkpoint.pt','kind':'checkpoint'}),
            8:lambda:action('resume_job',{'parent_job':jobs[0]['id'],'model_id':models[0]['id'],'args':['--data',dataset,'--epochs','2']}),
            9:lambda:action('await_job',jobs[1]['id']),
            10:lambda:action('register_model',{'job_id':jobs[1]['id'],'path':'weights.safetensors','kind':'model'}),
            11:lambda:action('evaluate_model',{'model_id':models[1]['id'],'evaluator':'fashion'}),
            12:lambda:action('start_job',{**packet,'args':['--data',dataset,'--epochs','2']}),
            13:lambda:action('await_job',jobs[2]['id']),
            14:lambda:action('register_model',{'job_id':jobs[2]['id'],'path':'weights.safetensors','kind':'model'}),
            15:lambda:action('evaluate_model',{'model_id':models[2]['id'],'evaluator':'fashion'}),
            16:lambda:action('write_file',{'path':'model-ref.json','content':json.dumps({'model_id':models[1]['id']})}),
            17:lambda:action('write_file',{'path':'report.md','content':'# GPU runtime validation\nA scripted engineering fixture trained the fixed CNN on 55,000 official training images, used 5,000 training images for validation, saved and resumed at an epoch boundary, and requested independent CPU evaluation on the 10,000 protected test images. The host evaluates saved safetensors with its own architecture and no agent code. Required reviews in this fixture are scripted too. This is not autonomous architecture research or a multi-seed accuracy claim. Exact resume equivalence is checked separately by the host verifier after the run. See raw job outputs, model references and trace for actual outcomes; delivery alone does not prove accuracy.'}),
            18:lambda:action('submit_report',{'status':'DONE','summary':'Scripted real-GPU learning and independent scoring fixture delivered','files':['model-ref.json','report.md']})}
        return actions[n](),{'provider':'scripted validation fixture','usage':{}}


def verify(folder,image,cache):
    folder=Path(folder).resolve();data=download(cache)
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],capture_output=True,text=True,check=True).stdout.strip()
    evaluator=FashionEvaluator(image,data)
    bindings={'engineering':'experiment_engineer','research':'researcher','auditor':'critic',
        'experience':'experience','strategy':'strategy','environment':'environment_engineer','report_reader':'report_reader'}
    task={'goal':'Validate actual GPU training, frozen checkpoints, resume and independent model scoring',
        'inputs':{},'network':False,'evaluator':'fashion-reference','budget':{'max_calls':80,'max_seconds':2400,'max_assignments':20,'max_depth':2},
        'training':{'profiles':{'gpu':{'image':image,'gpu':'all','memory':'8g','cpus':4,'max_seconds':900,
            'max_output_bytes':500_000_000,'roles':['experiment_engineer']}}},
        'workflow':{'mode':'research','policy_version':2,'role_bindings':bindings,'stages':[{
            'id':'GPU','description':'Verify the fixed GPU training/resume fixture; do not claim autonomous scientific decisions',
            'owner':'engineering','required_outputs':['report.md','model-ref.json'],
            'required_tools':['start_job','resume_job','evaluate_model'],'required_reviewers':['auditor','report_reader'],
            'report_paths':['report.md'],'review_scopes':{'report_reader':'report_only'},
            'gates':[{'id':'protected-model-result','kind':'evaluation','criterion':'Frozen model reference has independently accepted model evaluation','accepted':True}]}]}}
    def reference_score(snapshot,_task):
        mid=json.loads(snapshot.get('model-ref.json','{}')).get('model_id')
        receipts=[team.evidence_record(e) for e in team.state['evidence'] if e.startswith('model-evaluation-')]
        matched=[r for r in receipts if r['model_id']==mid]
        candidate=team.state['workflow']['candidate']
        m=team.training.state['models'].get(mid,{})
        job=team.training.state['jobs'].get(m.get('job_id'),{})
        return {'accepted':bool(matched and matched[-1]['measurement']['accepted'] and job.get('owner')=='agents/'+str(candidate)),
                'scope':'Frozen reference to protected model evaluation, not new measurement','model_id':mid}
    # Fixture limits are explicit; production role definitions remain unchanged.
    agents=folder/'fixture-agents';agents.mkdir(parents=True)
    for p in (ROOT/'agents/training').iterdir():
        if not p.is_file():continue
        dest=agents/p.name
        if p.suffix=='.json':
            config=json.loads(p.read_text());config['limits']['max_steps']=40;config['limits']['max_seconds']=2400
            atomic_json(dest,config)
        else:dest.write_bytes(p.read_bytes())
    team=Team(folder,task,agents_dir=agents,provider_factory=lambda c:Decisions(c['id'],team),
        evaluators={'fashion-reference':Evaluator('fashion-reference-v1',reference_score)},model_evaluators={'fashion':evaluator})
    did=team.training.register_dataset('Fashion-MNIST official training split',
        {'images.gz':data/'train-images-idx3-ubyte.gz','labels.gz':data/'train-labels-idx1-ubyte.gz'},
        {'source':'https://github.com/zalandoresearch/fashion-mnist','split':'train','samples':60000})
    outcome=team.run()
    jobs=list(team.training.state['jobs'].values());models=list(team.training.state['models'].values())
    assert outcome['status']=='completed' and team.state['goal_met'],outcome
    assert len(jobs)==3 and len(models)==3
    comparison=evaluator.run(team.training.store.verify(models[1]['blob']),team.training.store.verify(models[2]['blob']))
    assert comparison['identical'],comparison
    reports=[json.loads((team.training.root/'jobs'/j['id']/'output/training.json').read_text()) for j in jobs]
    assert all(r['parameter_delta_norm']>0 and r['finite_gradients'] for r in reports)
    assert reports[1]['resumed_from_epoch']==1 and reports[2]['resumed_from_epoch']==0
    assert models[0]['blob']['bytes']>16_000_000
    count=team.state['calls'];team.run();assert team.state['calls']==count
    result={'status':'passed','provider':'scripted validation choices, not live model reasoning',
        'gpu':reports[0]['device'],'torch':reports[0]['torch'],'cuda':reports[0]['cuda'],
        'training':reports,'checkpoint_bytes':models[0]['blob']['bytes'],'resume_comparison':comparison,
        'evaluations':[team.evidence_record(e)['measurement'] for e in team.state['evidence'] if e.startswith('model-evaluation-')],
        'dataset_id':did,'test_labels_delivered_to_training':False,'reserved_scripted_calls':count,'resume_added_calls':0,
        'scope':'Real learning/storage/exact epoch-resume/isolated CPU evaluation; one seed, fixed architecture, not autonomous research performance'}
    atomic_json(folder/'verification.json',result);team.trace.export(folder/'trace.html');team.close();return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True)
    p.add_argument('--image',default='researchsquad-training:torch2.9.1-cu128')
    p.add_argument('--cache',default=str(Path.home()/'.cache/researchsquad/fashion-mnist'))
    a=p.parse_args();print(json.dumps(verify(a.run_dir,a.image,a.cache),indent=2))
