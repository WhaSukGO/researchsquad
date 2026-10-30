"""Real provider research/engineering/review study, with one final test evaluation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from .contracts import atomic_json,digest
from .team import Team,ROOT
from .team_evaluators import Evaluator
from .fashion_check import download,FILES

def score(image,data,weights,validation=False):
    names=('train-images-idx3-ubyte.gz','train-labels-idx1-ubyte.gz') if validation else ('t10k-images-idx3-ubyte.gz','t10k-labels-idx1-ubyte.gz')
    for name in names:
        if hashlib.md5((data/name).read_bytes()).hexdigest()!=FILES[name]:raise ValueError('Dataset changed')
    name='rsq-live-eval-'+uuid.uuid4().hex[:16]
    cmd=['docker','run','--rm','--name',name,'--network','none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges',
        '--memory','4g','--cpus','2','--pids-limit','64','--user',f'{os.getuid()}:{os.getgid()}', '--tmpfs','/tmp:rw,nosuid,nodev,size=128m']
    for src,dst in [(ROOT/'goalagent/fashion_model.py','/eval/fashion_model.py'),(ROOT/'goalagent/fashion_study_models.py','/eval/eval.py'),
                    (weights,'/weights'),(data/names[0],'/images'),(data/names[1],'/labels')]:
        cmd+=['--mount',f'type=bind,src={src},dst={dst},readonly']
    try:
        r=subprocess.run(cmd+[image,'python','/eval/eval.py','--weights','/weights','--images','/images','--labels','/labels']+(['--validation'] if validation else []),capture_output=True,text=True,timeout=300)
        if r.returncode:raise RuntimeError(r.stderr[-3000:])
        return json.loads(r.stdout)
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)

BRIEF='''Conduct a real bounded Fashion-MNIST learning study. No scripted choices.
Researcher: compare at least two candidate families (MLP and CNN are supported), choose a baseline, a falsifiable improvement hypothesis, validation-based selection and stopping rules in plan.md. You may read official public docs; distinguish sources actually opened from prior knowledge. Do not claim a web search without a successful receipt. Keep scope small.
Engineering: read prior PLAN/plan.md and this protocol. Write your own train.py. Do not copy the old fixed Fashion training fixture. Copy the supplied fashion_model.py and fashion_study_models.py helpers into your code_files. Import build from fashion_study_models and images/labels from fashion_model. Helpers supply ONLY architecture/loading, not a training loop. Choose spec {family:mlp|cnn,width:16|32|64,hidden:128|256|512|1024,dropout:0..0.5}. You control optimizer, lr, epochs (1..5 per job), batch size, normalization-compatible augmentation, regularization. Use seed 1337, all first 55000 train examples and final 5000 for validation. x is float32 [0,1], N,1,28,28; y is int64. CUDA is required, no CPU fallback. Use torch.set_num_threads(4). Train files are /datasets/ID/images.gz and labels.gz (get ID from training_catalog).
Save weights.safetensors with safetensors.torch.save_file(state_dict, path, metadata={'spec':json.dumps(spec)}). Also save metrics.json with spec, hyperparameters, seed, split counts, per-epoch loss and validation_accuracy, optimizer_steps, finite_gradients, device, and elapsed time. Train ONLY on first 55000. Official test data is never available to you.
REQUIRED adaptive loop: run a baseline job, await_job and read_job_output(metrics.json). THEN record_decision citing actual result and select a change to architecture or learning conditions; write updated code/args, start a second job, await and read its metrics. If execution fails inspect log, fix and retry within budget. Up to 4 successful jobs, <=5 total job launches. Retain negative outcomes. Choose final model by validation, not test. Register only selected weights as model. Publish model-ref.json {model_id:...}, experiments.json (job IDs, settings, observed results, changes and selection), and report.md explaining role rationale, successes, failures and limitations. Do NOT use evaluate_model: final protected test runs once after selection through coordinator evaluate. Do not nominate test-driven revisions.
Reviewers must inspect supplied evidence, not assume success. Researcher reviews hypothesis/results; critic reviews leakage and whether a change actually followed observed feedback; report_reader reads report alone for clarity. Full reviewers may request small text files from output to be included when missing, but cannot themselves run new training. Report-only scope cannot inspect code. Coordinator: advance PLAN on delivery/review, then evaluate final STUDY candidate once; no accuracy threshold is imposed. Accept scientifically valid negative outcomes. No new work items for external papers or unbounded expansion. Original objective is this small adaptive run, not state-of-art accuracy.
Public decision summaries only; no hidden reasoning. Task/review outputs must be based on actual tool evidence.
'''

def run(folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}','researchsquad-training:torch2.9.1-cu128'],capture_output=True,text=True,check=True).stdout.strip()
    data=download(Path.home()/'.cache/researchsquad/fashion-mnist')
    agents=folder/'agents-config';agents.mkdir(exist_ok=True)
    for p in (ROOT/'agents/training').iterdir():
        if p.suffix=='.json':
            c=json.loads(p.read_text());c['limits'].update(max_steps=70,max_seconds=3600,model_call_timeout=240)
            c['tools']=[t for t in c['tools'] if t!='evaluate_model']
            if c['id'] not in ('report_reader',) and 'record_decision' not in c['tools']:c['tools'].append('record_decision')
            atomic_json(agents/p.name,c)
        else:(agents/p.name).write_text(p.read_text()+'\nStudy-specific protocol:\n'+BRIEF)
    bindings={'research':'researcher','engineering':'experiment_engineer','auditor':'critic','report_reader':'report_reader','environment':'environment_engineer'}
    task={'goal':BRIEF,'inputs':{'protocol.txt':BRIEF,'fashion_model.py':(ROOT/'goalagent/fashion_model.py').read_text(),
        'fashion_study_models.py':(ROOT/'goalagent/fashion_study_models.py').read_text()},'network':True,'evaluator':'study',
        'budget':{'max_calls':160,'max_seconds':7200,'max_assignments':18,'max_depth':2},
        'training':{'profiles':{'gpu':{'image':image,'gpu':'all','memory':'8g','cpus':4,'max_seconds':180,'max_output_bytes':200000000,'roles':['experiment_engineer']}}},
        'workflow':{'mode':'research','policy_version':2,'role_bindings':bindings,'work_policy':{'max_attempts':3,'checkpoint_interval':8,'coordinator_checkpoint_interval':1},'stages':[
            {'id':'PLAN','description':'Choose candidate models, baseline and falsifiable adaptation rule; deliver plan.md','owner':'research','required_outputs':['plan.md'],'required_reviewers':['auditor'],
             'gates':[{'id':'plan','kind':'artifact','criterion':'Bounded real model experiment plan delivered','path':'plan.md'}]},
            {'id':'STUDY','description':'Run real GPU experiments; read baseline results before revising; choose on validation; final protected test once',
             'owner':'engineering','required_outputs':['report.md','experiments.json','model-ref.json'],'required_tools':['start_job','read_job_output','record_decision'],
             'required_reviewers':['research','auditor','report_reader'],'report_paths':['report.md'],'review_scopes':{'report_reader':'report_only'},
             'gates':[{'id':'study-measured','kind':'evaluation','criterion':'At least two successful real experiments and selected model independently scored','accepted':True}]}]}}
    def evaluate(snapshot,_task):
        if 'model-ref.json' not in snapshot:return {'accepted':False,'reason':'No selected model reference'}
        mid=json.loads(snapshot['model-ref.json'])['model_id'];m=team.training.state['models'][mid]
        jobs=[j for j in team.training.state['jobs'].values() if j['status']=='SUCCEEDED']
        if len(jobs)<2:return {'accepted':False,'reason':'Need at least two completed GPU experiments'}
        once=folder/'final-test.json'
        if once.exists():
            old=json.loads(once.read_text())
            if old['model_id']!=mid:raise ValueError('Protected test already used for a different selection')
            return old
        weights=team.training.store.verify(m['blob'])
        val=score(image,data,weights,True);test=score(image,data,weights)
        result={'accepted':True,'model_id':mid,'validation':val,'test':test,'successful_jobs':len(jobs),
            'scope':'Valid study delivery, no accuracy threshold; adaptive reasoning judged separately by reviewers'}
        atomic_json(once,result);return result
    team=Team(folder,task,agents_dir=agents,evaluators={'study':Evaluator('live-study-v1-'+digest(image)[:12],evaluate)})
    if not team.training.state['datasets']:
        team.training.register_dataset('Fashion-MNIST official train only',{'images.gz':data/'train-images-idx3-ubyte.gz','labels.gz':data/'train-labels-idx1-ubyte.gz'}, {'source':'official Fashion-MNIST','split':'train','samples':60000})
    try:
        outcome=team.run();atomic_json(folder/'outcome.json',{'outcome':outcome,'goal_met':team.state['goal_met'],'calls':team.state['calls']})
        print(json.dumps({'outcome':outcome,'goal_met':team.state['goal_met'],'calls':team.state['calls']}))
    finally:team.trace.export(folder/'trace.html');team.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();run(a.run_dir)
