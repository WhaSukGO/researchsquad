"""Milestone 5: the research ledger on an ordinary ResearchSquad study (Fashion-MNIST, MLP vs CNN).

The training code is host-owned (research/fashion-live/train.py); agents choose model specs and training settings. Results
enter the ledger only from container output, claims are decided only by the host, and a report may call an empirical result
observed only by citing a supported ledger claim (Team.validate_assignment_report). Same roles, budget and PLAN→STUDY
workflow as goalagent/fashion_live.py so that the two studies can be compared offline (scripts/count_unverified_claims.py).
"""
import argparse
import json
import subprocess
from pathlib import Path
from .contracts import atomic_json,digest
from .team import Team,ROOT
from .team_evaluators import Evaluator
from .fashion_check import download,action
from .fashion_live import score
from . import ledger


class StudyEvaluator:
    """Protected test scorer for study specs: fashion_study_models.score in its own container, the spec read from the weights metadata."""
    def __init__(self,image,data):self.image=image;self.data=data;self.version='fashion-study-test-v1-'+digest([image,(ROOT/'goalagent/fashion_study_models.py').read_text()])[:24]
    def __call__(self,path,job):return {'accepted':True,**score(self.image,self.data,path)}

FAMILIES=('mlp','cnn');WIDTHS=(16,32,64);HIDDEN=(128,256,512,1024)
DATASET='Fashion-MNIST official train only'
HANDLES={'FASHION_TRAIN':{'split':'train','description':'60,000 official Fashion-MNIST training images; the host trains on the first 55,000 and validates on the last 5,000'},
         'FASHION_TEST':{'split':'test','description':'10,000 official test images; protected evaluation only, once per run'}}
ENGINEER_TOOLS=['catalog','read_file','write_file','list_files','search_files','read_evidence','finish','checkpoint','submit_report','check_report','read_artifact','review_gate',
                'record_decision','ledger_view','sn_define','sn_train','ledger_evaluate','compare_results','ledger_claim','ledger_promote','mail_send','mail_inbox']
TRAINING_TOOLS={'training_catalog','start_job','job_status','await_job','cancel_job','resume_job','register_model','evaluate_model','register_dataset','read_job_output','publish_job_outputs'}


def params(spec):
    """Parameter count of fashion_study_models.build(spec), by arithmetic; the container's count is checked against it (PARAM_COUNT proof)."""
    h,w=spec['hidden'],spec['width']
    if spec['family']=='mlp':return 784*h+h+h*10+10
    return (9*w+w)+(9*w*2*w+2*w)+(2*w*49*h+h)+(h*10+10)


class FashionTask:
    """Spec = {family, width, hidden, dropout} as fashion_study_models.build accepts; metric = accuracy, higher is better."""
    name='fashion';extra_keys=('lr','batch_size');max_epochs=5
    TOOL_TEXT={
     'sn_define':'JSON {spec:{family:mlp|cnn, width:16|32|64, hidden:128|256|512|1024, dropout:0..0.5}, rationale:text citing [IDs] or [conj:ID]}. Host counts the parameters and returns a model node. The layer structure of each family is fixed by the host loader; you choose these four values.',
     'sn_train':'JSON {net_id, epochs:1..5, lr?:1e-5..0.1 (default 0.001), batch_size?:16..1024 (default 256)}. Real GPU training by the host-owned train.py (Adam, seed 1337) on the first 55,000 official training images, validated on the last 5,000; blocks until the job exits. On success the host creates a result node (dataset fashion-val, accuracy) and a PARAM_COUNT proof. You cannot author results.',
     'ledger_evaluate':'JSON {net_id}. Protected host evaluation of the latest successful job for that model on the 10,000 official test images (dataset fashion-test). One per run: evaluate only the model you selected on validation.',
     'compare_results':'JSON {a:result_id, b:result_id}. Host compares the accuracy of two results on the same dataset and returns a comparison node to cite. Never compare numbers yourself.',
     'ledger_claim':'JSON {template:BEATS|FEWER_PARAMS, args, rationale:text citing [IDs]}. Creates a conjecture; it is never supported by itself. BEATS args {net_a,net_b,dataset:fashion-val|fashion-test} means net_a has the higher accuracy; FEWER_PARAMS args {net_a,net_b}.',
     'ledger_promote':'JSON {claim_id, evidence_ids:[result ids]}. Deterministic host check; returns supported or refuted. Nothing you say can promote a claim. Another role may promote a decided claim again in its own view once the evidence is in that view; agreement exists when two roles have promoted it.',
     'mail_send':'JSON {to:role|all, body:text, attach:[node ids from your view]}. Attached nodes enter the recipient views; this is how reviewers get to see your models, results and claims in ledger_view. Letters are refused when they cite IDs outside your view, state numbers without an ID, or call something verified without a supported claim ID.',
    }
    def __init__(self,L):self.L=L
    def analyze(self,spec,vocab):
        if not isinstance(spec,dict) or set(spec)!={'family','width','hidden','dropout'}:raise ValueError('spec needs exactly {family, width, hidden, dropout}')
        if spec['family'] not in FAMILIES or spec['width'] not in WIDTHS or spec['hidden'] not in HIDDEN or not isinstance(spec['dropout'],(int,float)) or not 0<=spec['dropout']<=0.5:
            raise ValueError('family mlp|cnn, width 16|32|64, hidden 128|256|512|1024, dropout 0..0.5')
        spec={'family':spec['family'],'width':int(spec['width']),'hidden':int(spec['hidden']),'dropout':float(spec['dropout'])};p=params(spec)
        return spec,{'connections':p,'params':p,'tied_layers':0,'pattern':spec['family'],'layers':[]}
    def choices(self,analysis,docs,patterns):return []
    def eta(self,analysis,samples,epochs):return 0.0
    def vocabulary(self,view):return {'spec_format':{'family':list(FAMILIES),'width':list(WIDTHS),'hidden':list(HIDDEN),'dropout':'0..0.5'}}
    def packet(self,net,epochs,d,did,workspace):
        lr=d.get('lr',0.001);bs=d.get('batch_size',256)
        if not isinstance(lr,(int,float)) or not 1e-5<=lr<=0.1 or type(bs) is not int or not 16<=bs<=1024:raise ValueError('lr in [1e-5, 0.1] and batch_size an integer in [16, 1024]')
        for name,src in (('train.py',ROOT/'research/fashion-live/train.py'),('fashion_model.py',ROOT/'goalagent/fashion_model.py'),('fashion_study_models.py',ROOT/'goalagent/fashion_study_models.py')):
            (workspace/name).write_bytes(src.read_bytes())
        s=net['spec'];args=['--dataset-id',did,'--family',s['family'],'--width',str(s['width']),'--hidden',str(s['hidden']),'--dropout',str(s['dropout']),'--epochs',str(epochs),'--lr',str(lr),'--batch-size',str(bs)]
        return {'profile':self.L.config.get('training_profile','gpu'),'code_files':['train.py','fashion_model.py','fashion_study_models.py'],'entrypoint':'train.py','args':args,'dataset_ids':[did]}
    def matches(self,m,net):return m.get('spec')==net['spec']
    def result(self,m):
        per=[round(e['validation_accuracy'],4) for e in m['per_epoch']]
        return ({'accuracy':m['final_validation_accuracy'],'samples':m['split_counts']['validation'],'hyperparameters':{k:m['hyperparameters'][k] for k in ('lr','batch_size','epochs')}},
                m['environment']['parameter_count'],None,per)
    def measurement(self,m):return {'accuracy':m['accuracy'],'loss':m['loss'],'samples':m['samples']}


ledger.TASKS['fashion']=FashionTask

BRIEF='''Conduct a real bounded Fashion-MNIST learning study on the research ledger. No scripted choices.
Researcher: compare the two supported families (MLP and CNN), choose a baseline, a falsifiable improvement hypothesis, validation-based selection and stopping rules in plan.md. Distinguish sources actually opened from prior knowledge. Keep scope small.
Engineering: read PLAN/plan.md and this protocol. The training code is owned by the host; you do not write train.py. You choose model specs with sn_define ({family:mlp|cnn, width, hidden, dropout}) and training settings with sn_train (epochs 1..5, lr, batch_size). Training uses seed 1337, the first 55,000 official training images and the last 5,000 for validation; results enter your ledger view as result nodes only from the container output (ledger_view shows them). Official test data is never available to you except through ledger_evaluate, once, on the model you select by validation.
REQUIRED adaptive loop: define and train a baseline, read its result node. THEN record_decision citing the result ID and select a change to architecture or learning conditions; define/train again. Up to 4 successful jobs, <=5 launches. Retain negative outcomes. Compare only with compare_results; state comparisons as ledger claims (ledger_claim BEATS or FEWER_PARAMS) and promote them with ledger_promote using the result IDs as evidence. A claim you could not promote stays a conjecture. THEN, still in the same assignment and before submit_report, select one model by validation and run ledger_evaluate on it exactly once: the STUDY gate requires a fashion-test result node, and a submission without it is sent back.
Reports: every observed empirical claim in submit_report must cite a supported ledger claim ID (C1, C2, ...) among its evidence_ids, next to the action receipt; a result you read but did not promote is a hypothesis, not observed. Before submitting, mail_send to "all" attaching your model, result and claim node IDs so reviewers can read them in ledger_view. Publish experiments.json (model IDs, result IDs, claim IDs with status, settings, selection) and report.md citing a ledger ID for every number.
Reviewers: inspect the ledger (ledger_view) and the supplied evidence, not assumptions. Researcher reviews hypothesis/results; critic reviews leakage and whether a change actually followed an observed result, and may promote the engineer's decided claims in its own view (ledger_promote) when the evidence is in view; report_reader reads report alone for clarity. Reviewers cannot run training. Coordinator: advance PLAN on delivery/review, then evaluate the final STUDY candidate once; no accuracy threshold is imposed. Accept scientifically valid negative outcomes. No new work items for external papers or unbounded expansion. Original objective is this small adaptive run, not state-of-art accuracy.
Public decision summaries only; no hidden reasoning. Task/review outputs must be based on actual tool evidence.
'''
MLP={'family':'mlp','width':16,'hidden':128,'dropout':0.0};CNN={'family':'cnn','width':16,'hidden':128,'dropout':0.0}


def task(image,*,managed=True,brief=BRIEF):
    roles=['experiment_engineer'] if managed else ['coordinator']
    views={'experiment_engineer':list(HANDLES),'researcher':[],'critic':[],'report_reader':[],'coordinator':[]} if managed else {'coordinator':list(HANDLES)}
    t={'goal':brief,'inputs':{'protocol.txt':brief},'network':managed,
       'budget':{'max_calls':160,'max_seconds':7200,'max_assignments':18,'max_depth':2} if managed else {'max_calls':40,'max_seconds':3600,'max_assignments':2,'max_depth':1},
       'training':{'profiles':{'gpu':{'image':image,'gpu':'all','memory':'8g','cpus':4,'max_seconds':600,'max_output_bytes':200_000_000,'roles':roles}}},
       'ledger':{'task':'fashion','handles':HANDLES,'views':views,'datasets':['fashion-val','fashion-test'],'metric':{'key':'accuracy','higher_is_better':True},
                 'templates':['BEATS','FEWER_PARAMS'],'max_evaluations':1,'training_profile':'gpu','evaluator':'fashion_test','blacklist':False,'dataset_name':DATASET,'compute_days':1}}
    if managed:
        t['evaluator']='study'
        t['workflow']={'mode':'research','policy_version':2,'role_bindings':{'research':'researcher','engineering':'experiment_engineer','auditor':'critic','report_reader':'report_reader','environment':'environment_engineer'},
            'work_policy':{'max_attempts':3,'checkpoint_interval':8,'coordinator_checkpoint_interval':1},'stages':[
            {'id':'PLAN','description':'Choose candidate models, baseline and falsifiable adaptation rule; deliver plan.md','owner':'research','required_outputs':['plan.md'],'required_reviewers':['auditor'],
             'gates':[{'id':'plan','kind':'artifact','criterion':'Bounded real model experiment plan delivered','path':'plan.md'}]},
            {'id':'STUDY','description':'Run real GPU experiments through the ledger; read the baseline result before revising; choose on validation; one protected test through ledger_evaluate',
             'owner':'engineering','required_outputs':['report.md','experiments.json'],'required_tools':['ledger_view'],  # jobs, claims and the test result are checked from ledger state by the gate, so a revision need not retrain
             'required_reviewers':['research','auditor','report_reader'],'report_paths':['report.md'],'review_scopes':{'report_reader':'report_only'},
             'gates':[{'id':'study-measured','kind':'evaluation','criterion':'At least two successful real experiments, a supported ledger claim and one protected test result','accepted':True}]}]}
    return t


def write_agents(dest,*,managed=True,brief=BRIEF):
    """Role configs for the study: the training profile's roles with ledger tools instead of raw training tools."""
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    for p in (ROOT/'agents/training').iterdir():
        if p.suffix=='.json':
            c=json.loads(p.read_text());c['limits'].update(max_steps=70,max_seconds=3600,command_timeout=700,model_call_timeout=240)
            if c['id']=='experiment_engineer':c['tools']=list(ENGINEER_TOOLS)
            elif c['id']!='report_reader':c['tools']=[t for t in c['tools'] if t not in TRAINING_TOOLS]+['ledger_view']+(['ledger_promote','mail_inbox'] if c['id'] in ('critic','researcher') else [])
            if c['id']=='coordinator' and not managed:c['tools']=list(ENGINEER_TOOLS)
            atomic_json(dest/p.name,c)
        else:(dest/p.name).write_text(p.read_text()+'\nStudy-specific protocol:\n'+brief)
    return dest


def study_evaluator(holder):
    """Gate evaluator reading ledger state; holder['team'] is set once the Team exists."""
    def evaluate(snapshot,_task):
        team=holder['team'];L=team.ledger;nodes=list(L.state['nodes'].values())
        jobs=[j for j in team.training.state['jobs'].values() if j['status']=='SUCCEEDED']
        tests=[n for n in nodes if n['type']=='result' and n['dataset']=='fashion-test'];supported=[n['id'] for n in nodes if n['type']=='claim' and n['status']=='supported']
        if len(jobs)<2:return {'accepted':False,'reason':'Need at least two completed GPU experiments'}
        if not supported:return {'accepted':False,'reason':'No supported ledger claim'}
        if not tests:return {'accepted':False,'reason':'No protected test result; the engineer runs ledger_evaluate once on the selected model'}
        return {'accepted':True,'successful_jobs':len(jobs),'supported_claims':supported,'test_results':[{k:t[k] for k in ('id','net','accuracy')} for t in tests],
                'scope':'Valid study delivery judged from ledger state; no accuracy threshold. Adaptive reasoning is judged by reviewers.'}
    return Evaluator('ledger-study-v1',evaluate)


class Scripted:
    """Docker-level check without a model: one role with the engineer's tools walks the ledger path and probes the report checker."""
    def __init__(self,team):self.team=team;self.n=0
    def call(self,prompt,schema,folder,**kw):
        self.n+=1;nodes=self.team.ledger.state['nodes']
        val={n['net']:n for n in nodes.values() if n['type']=='result' and n['dataset']=='fashion-val'}
        best=max(val.values(),key=lambda r:r['accuracy'])['net'] if val else 'N1'
        steps=[lambda:action('ledger_view'),
          lambda:action('sn_define',{'spec':MLP,'rationale':'Baseline on the training handle [FASHION_TRAIN]'}),
          lambda:action('sn_define',{'spec':CNN,'rationale':'Candidate [FASHION_TRAIN]; whether it is better is [conj:CNN_BETTER]'}),
          lambda:action('sn_train',{'net_id':'N1','epochs':1}),lambda:action('sn_train',{'net_id':'N2','epochs':1,'lr':0.002}),
          lambda:action('compare_results',{'a':'R2','b':'R1'}),
          lambda:action('ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'fashion-val'},'rationale':'[CMP1]'}),
          lambda:action('ledger_promote',{'claim_id':'C1','evidence_ids':['R1','R2']}),
          lambda:action('ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N1','net_b':'N2'},'rationale':'Host counts [N1] [N2]'}),
          lambda:action('ledger_promote',{'claim_id':'C2','evidence_ids':[]}),
          lambda:action('ledger_evaluate',{'net_id':best}),
          # Negative probes: a LeNet-style argument set and an observed claim without a supported ID must both be refused.
          lambda:action('ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'fashion-val','reject_rate':'0.09'},'rationale':'[CMP1]'}),
          lambda:action('write_file',{'path':'report.md','content':'# Scripted ledger study\nEvery number lives in the ledger: [R1] [R2] [CMP1] [C1] [C2].'}),
          lambda:action('submit_report',{'status':'DONE','summary':'probe','files':['report.md'],'claims':[{'statement':'The second model is more accurate on validation','epistemic_status':'observed','scope':'empirical','evidence_ids':['R2'],'limitations':'one epoch'}]}),
          lambda:action('submit_report',{'status':'DONE','summary':'Scripted ledger study delivered','files':['report.md'],'claims':[
              {'statement':'The second model is more accurate on validation [C1]','epistemic_status':'observed','scope':'empirical','evidence_ids':['C1'],'limitations':'one seed, one epoch'},
              {'statement':'More epochs would raise accuracy','epistemic_status':'hypothesis','scope':'empirical','evidence_ids':[],'limitations':'untested'}]})]
        return steps[self.n-1](),{'provider':'scripted validation fixture'}


def build(folder,image,cache,*,managed=True,provider_factory=None,model=None):
    folder=Path(folder).resolve();data=download(Path(cache))
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],capture_output=True,text=True,check=True).stdout.strip()
    agents=write_agents(folder/'agents-config',managed=managed)
    holder={}
    team=Team(folder,task(image,managed=managed),agents_dir=agents,provider_factory=provider_factory,model=model,model_evaluators={'fashion_test':StudyEvaluator(image,data)},
              evaluators={'study':study_evaluator(holder)} if managed else None)
    holder['team']=team
    if not team.training.state['datasets']:
        team.training.register_dataset(DATASET,{'images.gz':data/'train-images-idx3-ubyte.gz','labels.gz':data/'train-labels-idx1-ubyte.gz'},{'source':'official Fashion-MNIST','split':'train','samples':60000})
    return team


def run(folder,image,cache,*,check=False,model=None):
    team=build(folder,image,cache,managed=not check,provider_factory=(lambda c:Scripted(team)) if check else None,model=model)
    try:
        outcome=team.run();audit=team.ledger.audit();nodes=team.ledger.state['nodes']
        summary={'outcome':outcome,'goal_met':team.state['goal_met'],'calls':team.state['calls'],'invariant_holds':audit['invariant_holds'],
                 'claims':{k:v['status'] for k,v in nodes.items() if v['type']=='claim'},'results':{k:(v['net'],v['dataset'],v.get('accuracy')) for k,v in nodes.items() if v['type']=='result'},
                 'nets':{k:(v['pattern'] if 'pattern' in v else v['analysis']['pattern'],v['analysis']['params']) for k,v in nodes.items() if v['type']=='net_spec'},
                 'jobs':{j['id']:j['status'] for j in team.training.state['jobs'].values()}}
        atomic_json(Path(folder)/'summary.json',summary);print(json.dumps(summary,indent=1,default=str));return summary
    finally:team.trace.export(Path(folder)/'trace.html');team.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--check',action='store_true');p.add_argument('--model',default=None)
    p.add_argument('--image',default='researchsquad-training:torch2.9.1-cu128');p.add_argument('--cache',default=str(Path.home()/'.cache/researchsquad/fashion-mnist'))
    a=p.parse_args();run(a.run_dir,a.image,a.cache,check=a.check,model=a.model)
