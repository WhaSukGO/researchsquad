"""Blinded incident tasks, actual external interruption, real provider recovery."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from .contracts import atomic_json,digest
from .fashion_check import download,FashionEvaluator
from .fashion_live import score
from .team import Team,ROOT
from .team_evaluators import Evaluator

KINDS={'case-01':'interruption','case-02':'shape','case-03':'loss'}

def source_for(kind):
    source=(ROOT/'research/recovery/starter.py').read_text()
    if kind=='interruption':source=source.replace('# CHECKPOINT_BOUNDARY',"if epoch==0 and begin==0 and not a.control:\n            Path('boundary.json').write_text(json.dumps({'epoch':1,'steps':steps}))\n            time.sleep(30)")
    if kind=='shape':source=source.replace('# INPUT_TRANSFORM','train_x=torch.nn.functional.interpolate(train_x,size=(27,27))')
    if kind=='loss':source=source.replace('loss=torch.nn.functional.cross_entropy(logits,train_y[ids])','loss=torch.log(logits).mean()')
    return source

PROTOCOL='''Investigate and recover one real training incident using actual tools and evidence. The incident label does not reveal its cause. Read starter.py, the helpers and training_catalog. Copy starter.py unchanged to train.py, copy the two helpers (run with cp inputs/starter.py train.py and cp inputs/fashion_model.py inputs/fashion_study_models.py . avoids retyping), and FIRST run the supplied source unchanged using profile gpu, code_files [train.py,fashion_model.py,fashion_study_models.py], entrypoint train.py, args [--data,/datasets/DATASET_ID,--epochs,3]. Await its actual terminal status. Do not preemptively repair or bypass the initial reproduction. There is a deliberate incident in that run; the host may exercise an external fault. Do not call the incident a scientific negative result until diagnosed.
After failure: inspect job_status log_tail and any relevant output, record_decision with the evidence IDs, competing causes, diagnosis and selected next test. Diagnose from actual outputs, not the incident label. If a usable checkpoint exists, demonstrate genuine continuation through register_model(kind checkpoint) and resume_job rather than silently restarting. If source needs repair, preserve the original, write a justified patch and start a new job. Keep fixed architecture spec, seed 1337, Adam lr .001, batch512, 3 epochs, first55000 training/final5000 validation and uint8/255 image convention. Do not change data, remove finite checks, sanitize nonfinite losses into dummy values, hardcode metrics, disable training, or use --control in an agent job. No package installation is needed.
Observe the recovered job completing, read its metrics and register final weights.safetensors as model. Publish original relevant failed/recovered output files directly using publish_job_outputs; do not retype their bodies. Deliver report.md, recovery.json {initial_job,recovered_job,model_id,diagnosis,change,tests,remaining_uncertainty}, and the repaired train.py/helpers and supporting outputs. Cite actual receipts for claims. Retain failed jobs. Report honest FAILED/NEEDS_INPUT if bounded attempts cannot recover. Maximum 5 launches per incident; avoid redundant reading once evidence suffices. Keep the standalone report concise (about 1000 words max); no irrelevant hash dumps.
Research reviewer: distinguish restored learning and valid performance from merely a successful exit. Critic: inspect original failure, repair or checkpoint lineage, unchanged data/finite checks and model registration; do not claim independent execution by reading. Report Reader: report-only clarity and scope. Coordinator: evaluate the frozen candidate with the protected recovery evaluator and advance only if required reviews/measurement pass. The host independently scores saved weights on validation; official test data is not used. No new model search or literature expansion is needed. Choices and reviews are real model decisions, not scripted. Public rationale only, no hidden reasoning.
'''

def prepare_control(folder,image,data):
    code=folder/'control/code';out=folder/'control/output';code.mkdir(parents=True,exist_ok=True);out.mkdir(exist_ok=True);out.chmod(0o777)
    (code/'train.py').write_text(source_for('interruption'))
    for name in ('fashion_model.py','fashion_study_models.py'):(code/name).write_bytes((ROOT/'goalagent'/name).read_bytes())
    command=['docker','run','--rm','--network','none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges','--gpus','all',
        '--memory','8g','--cpus','4','--pids-limit','128','--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','-w','/output']
    for src,dst,ro in [(code,'/code',True),(out,'/output',False),(data/'train-images-idx3-ubyte.gz','/data/images.gz',True),(data/'train-labels-idx1-ubyte.gz','/data/labels.gz',True)]:
        command+=['--mount',f'type=bind,src={src},dst={dst}'+(',readonly' if ro else '')]
    result=subprocess.run(command+[image,'python','/code/train.py','--data','/data','--epochs','3','--control'],capture_output=True,text=True,timeout=180)
    (folder/'control/log.txt').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Control training failed: '+result.stderr[-2000:])
    return out/'weights.safetensors'

def run_case(folder,kind):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}','researchsquad-training:torch2.9.1-cu128'],capture_output=True,text=True,check=True).stdout.strip()
    data=download(Path.home()/'.cache/researchsquad/fashion-mnist');seed=source_for(kind)
    control=prepare_control(folder,image,data) if kind=='interruption' and not (folder/'control/output/weights.safetensors').exists() else folder/'control/output/weights.safetensors'
    configs=folder/'agents-config';configs.mkdir(exist_ok=True)
    for p in (ROOT/'agents/training').iterdir():
        if p.suffix=='.json':
            c=json.loads(p.read_text());c['limits'].update(max_steps=100,max_seconds=5400,model_call_timeout=240)
            c['tools']=[t for t in c['tools'] if t!='evaluate_model'];atomic_json(configs/p.name,c)
        else:(configs/p.name).write_text(p.read_text()+'\nIncident task:\n'+PROTOCOL)
    task={'goal':PROTOCOL,'inputs':{'protocol.txt':PROTOCOL,'starter.py':seed,
        'fashion_model.py':(ROOT/'goalagent/fashion_model.py').read_text(),'fashion_study_models.py':(ROOT/'goalagent/fashion_study_models.py').read_text()},
        'network':False,'evaluator':'recovery','budget':{'max_calls':150,'max_seconds':7200,'max_assignments':16,'max_depth':2},
        'training':{'profiles':{'gpu':{'image':image,'gpu':'all','memory':'8g','cpus':4,'max_seconds':120,'max_output_bytes':150000000,'roles':['experiment_engineer']}}},
        'workflow':{'mode':'research','policy_version':2,'role_bindings':{'engineering':'experiment_engineer','research':'researcher','auditor':'critic','report_reader':'report_reader','environment':'environment_engineer'},
            'work_policy':{'max_attempts':2,'checkpoint_interval':8,'coordinator_checkpoint_interval':1},'stages':[{
                'id':'RECOVERY','description':'Reproduce the incident unchanged, diagnose observed failure, repair or genuinely resume and verify learning',
                'owner':'engineering','required_outputs':['report.md','recovery.json'],'required_tools':['start_job','record_decision','publish_job_outputs','register_model'],
                'required_reviewers':['research','auditor','report_reader'],'report_paths':['report.md'],'review_scopes':{'report_reader':'report_only'},
                'gates':[{'id':'recovery-measured','kind':'evaluation','criterion':'Actual seeded failure, repaired learning and checkpoint lineage where applicable','accepted':True}]}]}}
    def evaluate(snapshot,_task):
        packet=json.loads(snapshot.get('recovery.json','{}'))
        if not {'initial_job','recovered_job','model_id'}<=set(packet):return {'accepted':False,'reason':'Missing recovery references'}
        jobs=team.training.state['jobs'];first=jobs[packet['initial_job']];fixed=jobs[packet['recovered_job']]
        first_source=(team.training.root/'jobs'/first['id']/'code/train.py').read_text()
        if first_source!=seed or first['status']!='FAILED' or fixed['status']!='SUCCEEDED':return {'accepted':False,'reason':'Unchanged actual failure and successful recovery required'}
        expected=['--data','/datasets/'+first['request']['dataset_ids'][0],'--epochs','3']
        if first['request']['args']!=expected:return {'accepted':False,'reason':'Initial reproduction did not use the prescribed arguments'}
        initial_status=team.training.status(first)
        log=(team.training.root/'jobs'/first['id']/'job.log').read_text()
        if kind=='shape' and 'mat1 and mat2 shapes cannot be multiplied' not in log:return {'accepted':False,'reason':'Expected actual shape failure not observed'}
        if kind=='loss' and 'non-finite training loss before backward' not in log:return {'accepted':False,'reason':'Expected actual nonfinite failure not observed'}
        if '--control' in first['request']['args'] or '--control' in fixed['request']['args']:return {'accepted':False,'reason':'Control bypass forbidden'}
        model=team.training.state['models'][packet['model_id']]
        if model['job_id']!=fixed['id']:return {'accepted':False,'reason':'Model not from recovered job'}
        weights=team.training.store.verify(model['blob']);measurement=score(image,data,weights,True)
        result={'accepted':measurement['accuracy']>=.75,'kind':kind,'initial_job':first['id'],'recovered_job':fixed['id'],
            'model_id':model['id'],'validation':measurement,'scope':'Independent validation inference, not official test or general recovery proof'}
        if kind=='interruption':
            metrics=json.loads((team.training.root/'jobs'/fixed['id']/'output/metrics.json').read_text())
            comparison=FashionEvaluator(image,data).run(weights,control)
            injected=json.loads((folder/'injection.json').read_text()) if (folder/'injection.json').exists() else {}
            result.update(resume_comparison=comparison,resumed_from_epoch=metrics.get('resumed_from_epoch'),injection=injected)
            result['accepted']=bool(result['accepted'] and comparison['identical'] and metrics.get('resumed_from_epoch')==1 and fixed['parent_job']==first['id'] and injected.get('job_id')==first['id'] and initial_status['docker']['ExitCode']==137 and not initial_status['docker'].get('OOMKilled'))
        atomic_json(folder/'verification.json',result);return result
    team=Team(folder,task,agents_dir=configs,evaluators={'recovery':Evaluator('recovery-v1-'+digest([kind,seed,image])[:16],evaluate)})
    if not team.training.state['datasets']:team.training.register_dataset('Fashion-MNIST official train only',{'images.gz':data/'train-images-idx3-ubyte.gz','labels.gz':data/'train-labels-idx1-ubyte.gz'},{'source':'official Fashion-MNIST','split':'train','samples':60000})
    stop=threading.Event()
    def interrupt():
        while not stop.wait(.1):
            if (folder/'injection.json').exists():return
            for job in list(team.training.state['jobs'].values()):
                output=team.training.root/'jobs'/job['id']/'output'
                if not (output/'boundary.json').exists() or job['request'].get('resume_model'):continue
                source=team.training.root/'jobs'/job['id']/'code/train.py'
                if not source.exists() or source.read_text()!=seed:continue
                span=team.trace.start('fault_injection','external Docker SIGKILL',data={'job_id':job['id'],'checkpoint_bytes':(output/'checkpoint.pt').stat().st_size})
                result=subprocess.run(['docker','kill','--signal','KILL',job['container']],capture_output=True,text=True,timeout=20)
                record={'job_id':job['id'],'action':'external Docker SIGKILL','returncode':result.returncode,'boundary':json.loads((output/'boundary.json').read_text()),'time':time.time()}
                atomic_json(folder/'injection.json',record);team.trace.end(span,record,error=result.stderr if result.returncode else None);return
    observer=threading.Thread(target=interrupt,daemon=True) if kind=='interruption' else None
    if observer:observer.start()
    try:
        outcome=team.run();result={'outcome':outcome,'goal_met':team.state['goal_met'],'calls':team.state['calls'],'kind':kind}
        atomic_json(folder/'outcome.json',result);print(json.dumps(result))
    finally:
        stop.set()
        if observer:observer.join(timeout=25)
        team.trace.export(folder/'trace.html');team.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--case',choices=list(KINDS),required=True);a=p.parse_args();run_case(a.run_dir,KINDS[a.case])
