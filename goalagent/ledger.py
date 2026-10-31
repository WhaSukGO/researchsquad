"""Typed research ledger: the only knowledge store an agent may believe.

Invariant: the ledger never holds an unverified claim as supported. Models write
`conjecture` claims and read their view; `result` and `proof` nodes are created only by
host tools from container jobs or protected evaluations, and promotion is a deterministic
template check. Views (per role) implement who-knows-what; attachments widen a view.
"""
import hashlib
import json
from pathlib import Path
import re
import time
from .contracts import digest
from . import netlang

ROOT=Path(__file__).resolve().parents[1]
CITE=re.compile(r'\[([A-Za-z0-9_#:.-]+)\]')
REJECT_RATES=('0','0.05','0.09','0.12')
TEMPLATES={'BEATS':{'net_a','net_b','dataset','reject_rate'},'FEWER_PARAMS':{'net_a','net_b'},'GRAD_EQUALS':{'net'}}
TOOLS={
 'ledger_view':'Empty argument; your ledger view: supported claims with evidence, open conjectures, nets, results, proofs, documents, compute days left, unlocked macros. Believe only supported claims.',
 'lit_search':'Keyword query; rank documents in your view (id, title, date, snippet). Documents outside your view do not exist for you.',
 'lit_read':'Document ID; read the stored excerpt or paraphrase of a document in your view.',
 'sn_define':'JSON {spec:{layers:[{op:input,h,w},{op:local,k,stride,n,pad?,fan_in?},{op:tie,group:all,bias?:per_unit|shared},{op:avg,k},{op:full,n},{op:output,n}]}, rationale:text citing [IDs]}. Host counts connections, independent parameters and simulated training cost; returns a net node. tie applies the 1986 equal-weight-change constraint to the preceding local layer.',
 'sn_train':'JSON {net_id, epochs:1..30}. Real training in an isolated container on the registered training split (validation = last 1000 training digits), blocking until exit; charges simulated Sun-4 days from your compute budget. On success the host creates a result node (dataset usps-val) and proof nodes. You cannot author results.',
 'ledger_evaluate':'JSON {net_id}. Protected host evaluation of the latest successful job for that net on the held-out USPS test split in a separate container; limited count per run. Returns a result node (dataset usps-test).',
 'compare_results':'JSON {a:result_id, b:result_id, reject_rate:"0"|"0.05"|"0.09"|"0.12"}. Host compares error rates at that rejection rate and returns a comparison node to cite. Never compare numbers yourself.',
 'ledger_claim':'JSON {template:BEATS|FEWER_PARAMS|GRAD_EQUALS, args, rationale:text citing [IDs]}. Creates a conjecture; it is never supported by itself. BEATS args {net_a,net_b,dataset:usps-val|usps-test,reject_rate}; FEWER_PARAMS args {net_a,net_b}; GRAD_EQUALS args {net}.',
 'ledger_promote':'JSON {claim_id, evidence_ids:[result/proof ids]}. Deterministic host check; returns supported, refuted, or an error that leaves the claim a conjecture. Nothing you say can promote a claim.',
}
CODE_FILES=('train_usps.py','netlang_torch.py','netlang.py')


def sha256(data):return hashlib.sha256(data).hexdigest()


class LedgerRuntime:
    def __init__(self,team):
        self.team=team;self.config=team.task.get('ledger')
        self.state=team.state.setdefault('ledger',{'nodes':{},'views':{},'counters':{},'compute_days_used':0.0,'evaluations':0,'leak_log':[]})
        self.docs={}
        if self.config is None:return
        allowed={'corpus','views','compute_days','max_evaluations','samples','training_profile','code_dir','dataset_name'}
        if set(self.config)-allowed:raise ValueError('Unknown ledger configuration')
        corpus=ROOT/self.config['corpus'];register=json.loads((corpus/'register.json').read_text())
        for did,meta in register.items():
            body=(corpus/(did+'.md')).read_bytes()
            if sha256(body)!=meta['sha256']:raise ValueError('Corpus document changed: '+did)
            self.docs[did]=body.decode('utf-8')
            self.state['nodes'].setdefault(did,{'id':did,'type':'document','title':meta['title'],'date':meta['date'],'kind':meta['kind'],'sha256':meta['sha256']})
        for role,ids in self.config.get('views',{}).items():
            if role not in team.definitions:raise ValueError('Ledger view for unknown role: '+role)
            if not set(ids)<=set(self.docs):raise ValueError('Ledger view cites unknown documents')
            view=self.state['views'].setdefault(role,{'nodes':[],'macros':[]})
            for did in ids:
                if did not in view['nodes']:view['nodes'].append(did)
    # ---- helpers ----
    def role(self,agent):return agent.config['id']
    def view(self,agent):return self.state['views'].setdefault(self.role(agent),{'nodes':[],'macros':[]})
    def visible(self,agent,node_id,kind=None):
        node=self.state['nodes'].get(node_id)
        if not node or node_id not in self.view(agent)['nodes']:raise ValueError('Not in your ledger view: '+str(node_id))
        if kind and node['type']!=kind:raise ValueError(node_id+' is not a '+kind)
        return node
    def new_id(self,prefix):
        n=self.state['counters'].get(prefix,0)+1;self.state['counters'][prefix]=n;return prefix+str(n)
    def add(self,agent,node):
        self.state['nodes'][node['id']]=node;view=self.view(agent)
        if node['id'] not in view['nodes']:view['nodes'].append(node['id'])
        self.team.event('ledger_'+node['type'],{'id':node['id'],'role':self.role(agent)});return node
    def cites(self,agent,text):
        if not isinstance(text,str) or not text.strip():raise ValueError('rationale text is required')
        found=CITE.findall(text);view=set(self.view(agent)['nodes'])
        return [c for c in found if c in view],[c for c in found if c not in view]
    def guess(self,agent,node,kind):
        if node['guess']:
            self.state['leak_log'].append({'time':time.time(),'role':self.role(agent),'node':node['id'],'kind':kind,'unknown_cites':node.get('unknown_cites',[])})
    def dispatch(self,agent,action,timeout):
        if self.config is None:raise ValueError('Ledger not configured for this task')
        tool=action['tool'];raw=action['argument']
        if tool=='ledger_view':return self.render(agent)
        if tool=='lit_search':return self.search(agent,raw)
        if tool=='lit_read':return {'id':raw.strip(),'text':self.docs[self.visible(agent,raw.strip(),'document')['id']],'scope':'Stored excerpt or paraphrase; cite as ['+raw.strip()+']'}
        d=json.loads(raw)
        if tool=='sn_define':return self.define(agent,d)
        if tool=='sn_train':return self.train(agent,d,action,timeout)
        if tool=='ledger_evaluate':return self.evaluate(agent,d)
        if tool=='compare_results':return self.compare(agent,d)
        if tool=='ledger_claim':return self.claim(agent,d)
        if tool=='ledger_promote':return self.promote(agent,d)
        raise ValueError('Unknown ledger tool')
    # ---- read side ----
    def render(self,agent):
        view=self.view(agent);nodes=[self.state['nodes'][i] for i in view['nodes']]
        def brief(n):
            t=n['type']
            if t=='document':return {'id':n['id'],'title':n['title'],'date':n['date']}
            if t=='net_spec':return {'id':n['id'],'connections':n['analysis']['connections'],'params':n['analysis']['params'],'tied_layers':n['analysis']['tied_layers'],'guess':n['guess'],'jobs':n.get('jobs',[])}
            if t=='result':return {'id':n['id'],'net':n['net'],'dataset':n['dataset'],'error':n['error'],'reject_curve':n['reject_curve']}
            if t=='proof':return {'id':n['id'],'kind':n['kind'],'net':n['net'],'passed':n['passed']}
            if t=='claim':return {'id':n['id'],'template':n['template'],'args':n['args'],'status':n['status'],'evidence':n['evidence'],'guess':n['guess']}
            if t=='comparison':return {k:n[k] for k in ('id','a','b','reject_rate','error_a','error_b','winner')}
            return {'id':n['id'],'type':t}
        groups={}
        for n in nodes:groups.setdefault(n['type'],[]).append(brief(n))
        budget=float(self.config.get('compute_days',30))
        return {'believe_only':'claims with status supported','supported':[c for c in groups.get('claim',[]) if c['status']=='supported'],
                'conjectures':[c for c in groups.get('claim',[]) if c['status']=='conjecture'],'refuted':[c for c in groups.get('claim',[]) if c['status']=='refuted'],
                'nets':groups.get('net_spec',[]),'results':groups.get('result',[]),'proofs':groups.get('proof',[]),'comparisons':groups.get('comparison',[]),
                'documents':groups.get('document',[]),'compute_days':{'budget':budget,'used':round(self.state['compute_days_used'],3),'remaining':round(budget-self.state['compute_days_used'],3)},
                'evaluations':{'used':self.state['evaluations'],'max':int(self.config.get('max_evaluations',4))},'macros':view['macros']}
    def search(self,agent,query):
        words=[w.lower() for w in re.findall(r'[A-Za-z0-9]+',query or '') if len(w)>2]
        if not words:raise ValueError('Query needs words')
        rows=[]
        for did in self.view(agent)['nodes']:
            node=self.state['nodes'][did]
            if node['type']!='document':continue
            text=self.docs[did];low=text.lower();score=sum(low.count(w) for w in words)
            if score:
                first=next((m.start() for m in (re.search(re.escape(w),low) for w in words) if m),0)
                rows.append({'id':did,'title':node['title'],'date':node['date'],'score':score,'snippet':text[max(0,first-80):first+160].replace('\n',' ')})
        rows.sort(key=lambda r:-r['score']);return {'results':rows[:5],'scope':'Keyword match inside your view only'}
    # ---- write side (host-verified) ----
    def define(self,agent,d):
        if set(d)!={'spec','rationale'}:raise ValueError('sn_define needs {spec, rationale}')
        macros=self.view(agent)['macros'];analysis=netlang.analyze(d['spec'],macros)
        cites,unknown=self.cites(agent,d['rationale']);samples=int(self.config.get('samples',6291))
        node={'id':self.new_id('N'),'type':'net_spec','spec':netlang.canonical(d['spec'],macros),'analysis':analysis,'rationale':d['rationale'],
              'cites':cites,'unknown_cites':unknown,'guess':not cites,'owner':self.role(agent),'jobs':[],
              'eta_days_per_epoch':netlang.eta_days(analysis['connections'],samples,1)}
        self.add(agent,node);self.guess(agent,node,'net_spec')
        return {'net_id':node['id'],'connections':analysis['connections'],'params':analysis['params'],'layers':analysis['layers'],'eta_days_per_epoch':round(node['eta_days_per_epoch'],3),'guess':node['guess'],
                'note':'guess=true means your rationale cited nothing in your view; the choice is recorded as unsupported'}
    def dataset_id(self):
        name=self.config.get('dataset_name','usps-train')
        for did,r in self.team.training.state['datasets'].items():
            if r['name']==name:return did
        raise ValueError('Training dataset not registered: '+name)
    def train(self,agent,d,action,timeout):
        if set(d)!={'net_id','epochs'}:raise ValueError('sn_train needs {net_id, epochs}')
        net=self.visible(agent,d['net_id'],'net_spec');epochs=d['epochs']
        if type(epochs) is not int or not 1<=epochs<=30:raise ValueError('epochs must be an integer in 1..30')
        eta=netlang.eta_days(net['analysis']['connections'],int(self.config.get('samples',6291)),epochs);budget=float(self.config.get('compute_days',30))
        if self.state['compute_days_used']+eta>budget:raise ValueError(f'Compute budget exceeded: this run costs {eta:.2f} simulated days, {budget-self.state["compute_days_used"]:.2f} remain. Simplify the network or train fewer epochs.')
        code=ROOT/self.config.get('code_dir','research/lenet')
        for name in CODE_FILES:
            src=code/name if name!='netlang.py' else ROOT/'goalagent/netlang.py'
            (Path(agent.workspace)/name).write_bytes(src.read_bytes())
        did=self.dataset_id()
        packet={'profile':self.config.get('training_profile','sun4'),'code_files':list(CODE_FILES),'entrypoint':'train_usps.py',
                'args':['--spec',net['spec'],'--epochs',str(epochs),'--net-id',net['id'],'--dataset-id',did],'dataset_ids':[did]}
        self.state['compute_days_used']+=eta
        status=self.team.training.start(agent,packet,self.team.dispatch_id(agent,action))
        job=self.team.training.state['jobs'][status['job_id']]
        if status['job_id'] not in net['jobs']:net['jobs'].append(status['job_id'])
        deadline=time.time()+max(30,(timeout or 600)-20)
        while status['status'] in ('STARTING','RUNNING') and time.time()<deadline:
            time.sleep(5);status=self.team.training.status(job)
        out={'job_id':status['job_id'],'status':status['status'],'simulated_days':round(eta,3),'compute_days_used':round(self.state['compute_days_used'],3),'log_tail':status['log_tail'][-1500:]}
        if status['status']!='SUCCEEDED':return {**out,'result':None,'note':'No result node: only a succeeded job produces one'}
        metrics_path=self.team.training.root/'jobs'/status['job_id']/'output/metrics.json'
        raw=metrics_path.read_bytes();m=json.loads(raw)
        if m.get('net_id')!=net['id'] or m.get('spec')!=net['spec']:raise ValueError('Job output does not match the net spec')
        result=self.add(agent,{'id':self.new_id('R'),'type':'result','net':net['id'],'dataset':'usps-val','error':m['val_error'],'reject_curve':m['reject_curve'],
            'epochs':epochs,'samples':m['train_count'],'source':{'job_id':status['job_id'],'path':'metrics.json','sha256':sha256(raw)},'owner':self.role(agent)})
        proofs=[self.add(agent,{'id':self.new_id('P'),'type':'proof','kind':'PARAM_COUNT','net':net['id'],'passed':m['parameters']==net['analysis']['params'],
                    'detail':{'ledger_params':net['analysis']['params'],'container_params':m['parameters']},'source':result['source']})]
        if m.get('grad_check'):
            proofs.append(self.add(agent,{'id':self.new_id('P'),'type':'proof','kind':'GRAD_CHECK','net':net['id'],'passed':bool(m['grad_check']['passed']),'detail':m['grad_check'],'source':result['source']}))
        return {**out,'result':{k:result[k] for k in ('id','net','dataset','error','reject_curve')},'proofs':[{k:p[k] for k in ('id','kind','passed')} for p in proofs],
                'per_epoch':m['per_epoch'][-3:],'scope':'Validation split result, not protected test measurement'}
    def evaluate(self,agent,d):
        if set(d)!={'net_id'}:raise ValueError('ledger_evaluate needs {net_id}')
        net=self.visible(agent,d['net_id'],'net_spec');limit=int(self.config.get('max_evaluations',4))
        jobs=[j for j in net.get('jobs',[]) if self.team.training.state['jobs'][j]['status']=='SUCCEEDED']
        if not jobs:raise ValueError('No succeeded job for '+net['id'])
        if self.state['evaluations']>=limit:raise ValueError('Protected evaluation limit reached')
        model=self.team.training.register_model(agent,jobs[-1],'weights.safetensors','model')
        self.state['evaluations']+=1
        record=self.team.training.evaluate(agent,model['id'],'usps_test');m=record['measurement']
        result=self.add(agent,{'id':self.new_id('R'),'type':'result','net':net['id'],'dataset':'usps-test','error':m['error'],'reject_curve':m['reject_curve'],'samples':m['samples'],
            'source':{'evidence_id':record['evidence_id'],'model_id':model['id'],'job_id':jobs[-1]},'owner':self.role(agent)})
        return {'result':{k:result[k] for k in ('id','net','dataset','error','reject_curve')},'evidence_id':record['evidence_id'],'evaluations_remaining':limit-self.state['evaluations'],'scope':record['scope']}
    def error_at(self,result,rate):
        if rate not in REJECT_RATES:raise ValueError('reject_rate must be one of '+', '.join(REJECT_RATES))
        return float(result['reject_curve'][rate])
    def compare(self,agent,d):
        if set(d)!={'a','b','reject_rate'}:raise ValueError('compare_results needs {a, b, reject_rate}')
        a=self.visible(agent,d['a'],'result');b=self.visible(agent,d['b'],'result');rate=str(d['reject_rate'])
        if a['dataset']!=b['dataset']:raise ValueError('Results come from different datasets: '+a['dataset']+' vs '+b['dataset'])
        ea,eb=self.error_at(a,rate),self.error_at(b,rate)
        node=self.add(agent,{'id':self.new_id('CMP'),'type':'comparison','a':a['id'],'b':b['id'],'dataset':a['dataset'],'reject_rate':rate,'error_a':ea,'error_b':eb,'winner':a['id'] if ea<eb else b['id'] if eb<ea else 'tie','owner':self.role(agent)})
        return {k:node[k] for k in ('id','a','b','dataset','reject_rate','error_a','error_b','winner')}
    def claim(self,agent,d):
        if set(d)!={'template','args','rationale'}:raise ValueError('ledger_claim needs {template, args, rationale}')
        t=d['template'];args=d['args']
        if t not in TEMPLATES:raise ValueError('Free-text claims stay conjectures forever; use a template: '+', '.join(TEMPLATES))
        if not isinstance(args,dict) or set(args)!=TEMPLATES[t]:raise ValueError(t+' args must be exactly '+', '.join(sorted(TEMPLATES[t])))
        for key in ('net','net_a','net_b'):
            if key in args:self.visible(agent,args[key],'net_spec')
        if t=='BEATS':
            if args['dataset'] not in ('usps-val','usps-test'):raise ValueError('dataset must be usps-val or usps-test')
            if str(args['reject_rate']) not in REJECT_RATES:raise ValueError('reject_rate must be one of '+', '.join(REJECT_RATES))
            args['reject_rate']=str(args['reject_rate'])
        cites,unknown=self.cites(agent,d['rationale'])
        node={'id':self.new_id('C'),'type':'claim','template':t,'args':args,'status':'conjecture','rationale':d['rationale'],'cites':cites,'unknown_cites':unknown,'guess':not cites,'evidence':[],'owner':self.role(agent)}
        self.add(agent,node);self.guess(agent,node,'claim')
        return {'claim_id':node['id'],'status':'conjecture','guess':node['guess'],'note':'Promote with ledger_promote and result/proof evidence; speech cannot promote it'}
    def promote(self,agent,d):
        if set(d)!={'claim_id','evidence_ids'} or not isinstance(d['evidence_ids'],list):raise ValueError('ledger_promote needs {claim_id, evidence_ids:[...]}')
        c=self.visible(agent,d['claim_id'],'claim')
        if c['status']!='conjecture':return {'claim_id':c['id'],'status':c['status'],'evidence':c['evidence'],'note':'Already decided'}
        evidence=[self.visible(agent,e) for e in d['evidence_ids']]
        t=c['template'];a=c['args']
        if t=='FEWER_PARAMS':
            pa=self.visible(agent,a['net_a'],'net_spec')['analysis']['params'];pb=self.visible(agent,a['net_b'],'net_spec')['analysis']['params']
            verdict='supported' if pa<pb else 'refuted';detail={'params_a':pa,'params_b':pb};used=[a['net_a'],a['net_b']]
        elif t=='GRAD_EQUALS':
            proofs=[e for e in evidence if e['type']=='proof' and e['kind']=='GRAD_CHECK' and e['net']==a['net']]
            if not proofs:raise ValueError('GRAD_EQUALS needs a GRAD_CHECK proof node for '+a['net'])
            verdict='supported' if all(p['passed'] for p in proofs) else 'refuted';detail={p['id']:p['detail'] for p in proofs};used=[p['id'] for p in proofs]
        else:
            ra=[e for e in evidence if e['type']=='result' and e['net']==a['net_a'] and e['dataset']==a['dataset']]
            rb=[e for e in evidence if e['type']=='result' and e['net']==a['net_b'] and e['dataset']==a['dataset']]
            if not ra or not rb:raise ValueError('BEATS needs one result for each net on dataset '+a['dataset']+' among the evidence; results on other datasets do not count')
            ea=min(self.error_at(r,a['reject_rate']) for r in ra);eb=min(self.error_at(r,a['reject_rate']) for r in rb)
            verdict='supported' if ea<eb else 'refuted';detail={'error_a':ea,'error_b':eb,'reject_rate':a['reject_rate']};used=[r['id'] for r in ra+rb]
        c['status']=verdict;c['evidence']=used;c['detail']=detail;c['decided_at']=time.time()
        self.team.event('ledger_promote',{'claim':c['id'],'status':verdict,'role':self.role(agent)})
        unlocked=[]
        if verdict=='supported' and t=='BEATS' and self.state['nodes'][a['net_a']]['analysis']['tied_layers']>0:
            view=self.view(agent)
            if 'shared_map' not in view['macros']:view['macros'].append('shared_map');unlocked.append('shared_map')
        return {'claim_id':c['id'],'status':verdict,'evidence':used,'detail':detail,'unlocked_macros':unlocked}
    # ---- audit (host-side invariant check, no model involved) ----
    def audit(self):
        nodes=self.state['nodes'].values();bad_results=[];bad_claims=[]
        for n in nodes:
            if n['type']=='result':
                src=n.get('source',{})
                if 'job_id' in src and 'sha256' in src:
                    path=self.team.training.root/'jobs'/src['job_id']/'output'/src['path']
                    if not path.exists() or sha256(path.read_bytes())!=src['sha256']:bad_results.append(n['id'])
                elif 'evidence_id' in src:
                    if src['evidence_id'] not in self.team.state['evidence']:bad_results.append(n['id'])
                else:bad_results.append(n['id'])
            if n['type']=='claim' and n['status']=='supported' and n['template']!='FEWER_PARAMS' and not n['evidence']:bad_claims.append(n['id'])
        counts={t:sum(1 for n in nodes if n['type']==t) for t in ('document','net_spec','result','proof','claim','comparison')}
        return {'nodes':counts,'results_without_provenance':bad_results,'supported_without_evidence':bad_claims,
                'guess_nets':[n['id'] for n in nodes if n['type']=='net_spec' and n['guess']],'guess_claims':[n['id'] for n in nodes if n['type']=='claim' and n['guess']],
                'claims_by_status':{s:sum(1 for n in nodes if n['type']=='claim' and n['status']==s) for s in ('conjecture','supported','refuted')},
                'leak_log':self.state['leak_log'],'invariant_holds':not bad_results and not bad_claims}
