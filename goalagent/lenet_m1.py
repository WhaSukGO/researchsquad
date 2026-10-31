"""LeNet rediscovery, milestone 1: ledger + tools + a single LeCun role on real USPS training.

`--mode check` runs scripted decisions (no model calls) through real CPU containers and
audits the ledger invariant. `--mode live` runs the common Agent with the configured
provider. Neither mode claims autonomous scientific quality; see docs/lenet-ledger-ko.md.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid
from .contracts import atomic_json, digest
from .team import Team, ROOT

USPS={'zip.train.gz':'66ebf231ab51f2cf6ac1a892d0f98ccffee1079d7a5db638c1f11f366046ca16',
      'zip.test.gz':'8dacc3c6e136af6c3488de9e5113a7daf140c8c2f1f0b61c54ee02f03f1a962f'}
URL='https://hastie.su.domains/ElemStatLearn/datasets/'
DOCS=['ROSENBLATT62','HUBEL62','MINSKY69','FUKUSHIMA80','FUKUSHIMA82','HOPFIELD82','HINTON83','LECUN85','RHW86','RHW86-TC',
      'DENKER87','WAIBEL87','GRAF87','DENKER88','LECUN88','LECUN89TR','BOTTOU88']
GOAL=('It is October 1988. The department recognizes handwritten USPS zip code digits. Using only what your ledger view '
      'supports, define constrained networks in the 1988 vocabulary, train them on the registered training split, and '
      'establish supported claims (FEWER_PARAMS, BEATS on usps-val and usps-test, GRAD_EQUALS) comparing a constrained '
      'network against a fully connected control. Finish with a report.md that cites only ledger IDs.')


def download(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for name,expected in USPS.items():
        p=folder/name
        if not p.exists():
            with urllib.request.urlopen(urllib.request.Request(URL+name),timeout=120) as r:p.write_bytes(r.read(10_000_000))
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('USPS source check failed: '+name)
    return folder


class UspsEvaluator:
    """Protected host adapter: evaluates frozen weights on the held-out test split in a CPU container."""
    def __init__(self,image,data):
        self.image=image;self.data=data
        code=[(ROOT/'research/lenet/netlang_torch.py').read_text(),(ROOT/'goalagent/netlang.py').read_text()]
        self.version='usps-test-v1-'+digest([image,USPS,code])[:24]
    def __call__(self,weights,job):
        if hashlib.sha256((self.data/'zip.test.gz').read_bytes()).hexdigest()!=USPS['zip.test.gz']:raise ValueError('Protected test source changed')
        args=job['request']['args'];spec=args[args.index('--spec')+1]
        name='rsq-eval-'+uuid.uuid4().hex[:20]
        cmd=['docker','run','--name',name,'--rm','--network','none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges',
             '--memory','2g','--cpus','2','--pids-limit','64','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--user',f'{os.getuid()}:{os.getgid()}']
        def mount(src,dst):cmd.extend(['--mount',f'type=bind,src={src},dst={dst},readonly'])
        mount(ROOT/'research/lenet/netlang_torch.py','/eval/netlang_torch.py');mount(ROOT/'goalagent/netlang.py','/eval/netlang.py')
        mount(weights,'/weights');mount(self.data/'zip.test.gz','/test.gz')
        try:
            r=subprocess.run([*cmd,self.image,'python','/eval/netlang_torch.py','--weights','/weights','--data','/test.gz','--spec',spec],capture_output=True,text=True,timeout=300)
            if r.returncode:raise RuntimeError(r.stderr[-3000:])
            return json.loads(r.stdout.strip().splitlines()[-1])
        finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


def task(image,*,compute_days=30.0,max_evaluations=4,budget=None,corpus=True,vocabulary=()):
    return {'goal':GOAL,'inputs':{},'network':False,
        'budget':budget or {'max_calls':80,'max_seconds':7200,'max_assignments':4,'max_depth':1},
        'training':{'profiles':{'sun4':{'image':image,'gpu':False,'memory':'2g','cpus':2,'max_seconds':1200,'max_output_bytes':50_000_000,'roles':['coordinator']}}},
        'ledger':{'corpus':'research/lit-1988','views':{'coordinator':DOCS if corpus else []},'vocabulary':list(vocabulary),'compute_days':compute_days,'max_evaluations':max_evaluations,
                  'samples':6291,'training_profile':'sun4','code_dir':'research/lenet','dataset_name':'usps-train'}}


def build(folder,image,cache,*,provider_factory=None,model=None,**kw):
    folder=Path(folder).resolve();data=download(cache)
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],capture_output=True,text=True,check=True).stdout.strip()
    team=Team(folder,task(image,**kw),agents_dir=ROOT/'agents/lenet',provider_factory=provider_factory,model=model,model_evaluators={'usps_test':UspsEvaluator(image,data)})
    if not team.training.state['datasets']:
        team.training.register_dataset('usps-train',{'zip.train.gz':data/'zip.train.gz'},{'source':URL+'zip.train.gz','split':'train','samples':7291,'note':'last 1000 rows serve as validation inside the job; the test split is never mounted into training'})
    return team


def action(tool,arg=''):return {'tool':tool,'argument':arg if isinstance(arg,str) else json.dumps(arg),'why':'Scripted validation decision; not live reasoning'}


FULL={'layers':[{'op':'input','h':16,'w':16},{'op':'full','n':12},{'op':'output','n':10}]}
TIED={'layers':[{'op':'input','h':16,'w':16},{'op':'local','k':3,'stride':2,'n':2},{'op':'tie','group':'all'},
                {'op':'local','k':5,'stride':2,'n':4},{'op':'tie','group':'all'},{'op':'output','n':10}]}
STEPS=[lambda:action('ledger_view'),lambda:action('lit_read','RHW86-TC'),
 lambda:action('sn_define',{'spec':FULL,'rationale':'Fully connected control like Net-2 in [LECUN89TR]'}),
 lambda:action('sn_define',{'spec':TIED,'rationale':'Two locally connected layers with the equal-weight-change constraint of [RHW86-TC], like Net-5 in [LECUN89TR]'}),
 lambda:action('sn_train',{'net_id':'N1','epochs':8}),lambda:action('sn_train',{'net_id':'N2','epochs':8}),
 lambda:action('ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N2','net_b':'N1'},'rationale':'Host counts for [N1] and [N2]'}),
 lambda:action('ledger_promote',{'claim_id':'C1','evidence_ids':[]}),
 lambda:action('compare_results',{'a':'R2','b':'R1','reject_rate':'0.09'}),
 lambda:action('ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'usps-val','reject_rate':'0.09'},'rationale':'Comparison [CMP1]'}),
 lambda:action('ledger_promote',{'claim_id':'C2','evidence_ids':['R1','R2']}),
 lambda:action('ledger_claim',{'template':'GRAD_EQUALS','args':{'net':'N2'},'rationale':'Proof [P3] from the container gradient check'}),
 lambda:action('ledger_promote',{'claim_id':'C3','evidence_ids':['P3']}),
 lambda:action('ledger_evaluate',{'net_id':'N2'}),lambda:action('ledger_evaluate',{'net_id':'N1'}),
 lambda:action('ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'usps-test','reject_rate':'0.09'},'rationale':'Protected results [R3] [R4]'}),
 lambda:action('ledger_promote',{'claim_id':'C4','evidence_ids':['R3','R4']}),
 # Negative checks: these must fail and leave no supported claim.
 lambda:action('ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'usps-val','reject_rate':'0'},'rationale':'I am sure it is better'}),
 lambda:action('ledger_promote',{'claim_id':'C5','evidence_ids':['R3','R4']}),
 lambda:action('ledger_claim',{'template':'IS_BETTER','args':{'net':'N2'},'rationale':'free text'}),
 lambda:action('write_file',{'path':'report.md','content':'# Ledger milestone 1 (scripted)\nClaims decided by the host: see ledger. No prose claims.'}),
 lambda:action('finish',{'summary':'Scripted ledger fixture complete','files':['report.md']})]


class Decisions:
    def __init__(self):self.n=0
    def call(self,prompt,schema,folder,**kw):
        self.n+=1;return STEPS[self.n-1](),{'provider':'scripted validation fixture'}


def check(folder,image,cache):
    team=build(folder,image,cache,provider_factory=lambda c:Decisions())
    outcome=team.run();audit=team.ledger.audit();nodes=team.ledger.state['nodes']
    claims={k:v['status'] for k,v in nodes.items() if v['type']=='claim'}
    errors=[]
    for p in sorted((team.folder/'agents/lead/actions').glob('*.json')):
        a=json.loads(p.read_text())
        if isinstance(a.get('observation'),dict) and 'error' in a['observation']:errors.append({'step':a['step'],'tool':a['tool'],'detail':a['observation'].get('detail','')[:200]})
    assert outcome['status']=='submitted' and outcome['report']['status']=='DONE',outcome
    assert audit['invariant_holds'],audit
    assert claims['C1']=='supported' and claims['C3']=='supported',claims
    assert claims['C2'] in ('supported','refuted') and claims['C4'] in ('supported','refuted'),claims
    assert claims['C5']=='conjecture' and 'C6' not in claims,claims
    assert any(e['tool']=='ledger_promote' for e in errors) and any(e['tool']=='ledger_claim' for e in errors),errors
    results={k:{'net':v['net'],'dataset':v['dataset'],'error':v['error'],'reject_curve':v['reject_curve']} for k,v in nodes.items() if v['type']=='result'}
    summary={'status':'passed','outcome':outcome['status'],'claims':claims,'results':results,'audit':audit,'tool_errors':errors,
             'compute_days_used':team.ledger.state['compute_days_used'],'vocabulary':team.ledger.state['views']['coordinator']['vocabulary'],
             'scope':'Scripted decisions through real CPU containers and a protected test adapter; validates the ledger invariant and tooling, not autonomous discovery'}
    atomic_json(team.folder/'verification.json',summary);team.trace.export(team.folder/'trace.html');team.close();return summary


def live(folder,image,cache,model,**kw):
    team=build(folder,image,cache,model=model,**kw)
    outcome=team.run();audit=team.ledger.audit();nodes=team.ledger.state['nodes']
    summary={'outcome':outcome,'audit':audit,'claims':{k:{'template':v['template'],'args':v['args'],'status':v['status'],'guess':v['guess']} for k,v in nodes.items() if v['type']=='claim'},
             'nets':{k:{'params':v['analysis']['params'],'connections':v['analysis']['connections'],'tied':v['analysis']['tied_layers'],'pattern':v['analysis']['pattern'],'cites':v['cites'],
                        'unsourced':[(c['choice'],c['value']) for c in v['choices'] if c['status']=='unsourced'],'rationale':v['rationale']} for k,v in nodes.items() if v['type']=='net_spec'},
             'results':{k:{'net':v['net'],'dataset':v['dataset'],'error':v['error']} for k,v in nodes.items() if v['type']=='result'},
             'calls':team.state['calls'],'compute_days_used':team.ledger.state['compute_days_used'],'config':{'corpus':bool(team.task['ledger']['views']['coordinator']),'vocabulary':team.task['ledger']['vocabulary']},
             'scope':'Live model decisions; results are real container measurements; leakage is measured by guess tags, not prevented'}
    atomic_json(team.folder/'summary.json',summary);team.trace.export(team.folder/'trace.html');team.close();return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['check','live'],default='check');p.add_argument('--run-dir',required=True)
    p.add_argument('--image',default='researchsquad-training:torch2.9.1-cu128');p.add_argument('--cache',default=str(Path.home()/'.cache/researchsquad/usps'))
    p.add_argument('--model',default=None);p.add_argument('--corpus-off',action='store_true',help='C0 control: empty literature view')
    p.add_argument('--vocab',default='',help='comma-separated locked ops to unlock from the start, e.g. avg (A4 variant)')
    a=p.parse_args();vocab=tuple(v for v in a.vocab.split(',') if v)
    out=check(a.run_dir,a.image,a.cache) if a.mode=='check' else live(a.run_dir,a.image,a.cache,a.model,corpus=not a.corpus_off,vocabulary=vocab)
    print(json.dumps(out,indent=2,default=str))
