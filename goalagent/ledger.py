"""Typed research ledger: the only knowledge store an agent may believe.

Invariant: the ledger never holds an unverified claim as supported. Models write
`conjecture` claims and read their view; `result` and `proof` nodes are created only by
host tools from container jobs or protected evaluations, and promotion is a deterministic
template check. Views (per role) implement who-knows-what; attachments widen a view.

Leakage (H2) is measured, not prevented: every hyperparameter choice and the layer pattern
of a defined network is checked against the documents the designer cited. Choices the
cited documents do not contain are recorded as `unsourced`.
"""
import hashlib
import json
from pathlib import Path
import re
import time
from .contracts import digest
from . import netlang
from . import judge

ROOT=Path(__file__).resolve().parents[1]
CITE=re.compile(r'\[([A-Za-z0-9_#:.-]+)\]')
REJECT_RATES=('0','0.05','0.09','0.12')
TEMPLATES={'BEATS':{'net_a','net_b','dataset','reject_rate'},'FEWER_PARAMS':{'net_a','net_b'},'GRAD_EQUALS':{'net'},'MORE_INVARIANT':{'net_a','net_b','transform'},'FITS_CHIP':{'net','chip'}}
FEATURES={'avg':re.compile(r'averag|subsampl|\bmean\b|pool|blur|coarse',re.I)}
TOOLS={
 'ledger_view':'Empty argument; your ledger view: supported claims with evidence, open conjectures, nets, results, proofs, documents, compute days left, vocabulary. Believe only supported claims.',
 'lit_search':'Keyword query; rank documents in your view (id, title, date, snippet). Documents outside your view do not exist for you.',
 'lit_read':'Document ID; read the stored excerpt or paraphrase of a document in your view.',
 'sn_define':'JSON {spec:{layers:[{op:input,h,w},{op:local,k,stride,n,pad?,fan_in?},{op:tie,group:all,bias?:per_unit|shared},{op:full,n},{op:output,n}]}, rationale:text citing [IDs]}. Host counts connections, independent parameters and simulated training cost, and records which of your choices the cited documents actually contain. Returns a net node. tie applies the 1986 equal-weight-change constraint to the preceding local layer. Other layer types need request_feature.',
 'request_feature':'JSON {description}. Ask the simulator maintainer for a layer type that is not in your vocabulary. Granting costs simulated days from your compute budget; some requests are refused.',
 'sn_train':'JSON {net_id, epochs:1..30}. Real training in an isolated container on the registered training split (validation = last 1000 training digits), blocking until exit; charges simulated Sun-4 days from your compute budget. On success the host creates a result node (dataset usps-val) and proof nodes. You cannot author results.',
 'ledger_evaluate':'JSON {net_id}. Protected host evaluation of the latest successful job for that net on the held-out USPS test split in a separate container; limited count per run. Returns a result node (dataset usps-test).',
 'compare_results':'JSON {a:result_id, b:result_id, reject_rate:"0"|"0.05"|"0.09"|"0.12"}. Host compares error rates at that rejection rate and returns a comparison node to cite. Never compare numbers yourself.',
 'ledger_claim':'JSON {template:BEATS|FEWER_PARAMS|GRAD_EQUALS|MORE_INVARIANT|FITS_CHIP, args, rationale:text citing [IDs]}. Creates a conjecture and the host at once tries the deterministic promotion with the eligible evidence in your view (BEATS and MORE_INVARIANT use the latest result of each net); the reply says supported, refuted, or why it stays a conjecture. Your words never support it. BEATS args {net_a,net_b,dataset:usps-val|usps-test,reject_rate}; FEWER_PARAMS args {net_a,net_b}; GRAD_EQUALS args {net}; MORE_INVARIANT args {net_a,net_b,transform:shift1|shift2} is supported when net_a keeps more validation digits unchanged under that shift than net_b, from the shift measurement every training result already carries (ties are refuted; net_b may be PIPELINE88); FITS_CHIP args {net,chip} is for the chip designer.',
 'ledger_promote':'JSON {claim_id or claim_ids:[...], evidence_ids:[result/proof ids]}. Deterministic host check, each claim decided on its own; returns supported, refuted, or an error that leaves the claim a conjecture. Nothing you say can promote a claim. A claim another role already decided can be promoted again in your own view; agreement exists when two roles have promoted it.',
 'mail_send':'JSON {to:role, body:text, attach:[node ids from your view]}. The only way to share knowledge: attached nodes enter the recipient view. The judge refuses letters with post-1988 vocabulary, citations outside your view, numbers without IDs, or claims of verification without a supported claim ID.',
 'mail_inbox':'Empty argument; read your unread letters (sender, body, attached node IDs). Attached nodes are already in your view.',
 'pipeline_run':'Empty argument; run the hand-designed baseline pipeline on the training/validation split and the held-out test split (data owner only). Returns result nodes for net PIPELINE88 on usps-val and usps-test.',
 'judge_verdict':'JSON {mail_id, verdict:pass|future_knowledge|unsupported, reason}. Referee only.',
 'chip_estimate':'JSON {net_id}. Chip designer only: estimate whether the net fits the analog chip (weights stored, not connections). Returns a chip node to cite and to use as FITS_CHIP evidence.',
 'implement_feature':'JSON {request_id}. Simulator maintainer only: implement a requested layer type; the requester gets it after simulated days.',
 'compute_allocate':'JSON {days}. Department head only: add simulated Sun-4 days to the shared training budget (bounded).',
 'schedule_demo':'JSON {day}. Department head only: book the USPS demonstration; accepted only when a FITS_CHIP claim is supported in your view.',
}
CODE_FILES=('train_usps.py','netlang_torch.py','netlang.py')
RESULT_KEYS=('id','net','dataset','error','reject_curve','accuracy','loss','samples')


def sha256(data):return hashlib.sha256(data).hexdigest()


def support_check(analysis,docs,patterns):
    """For each design choice, which cited documents contain it. docs: {id:text}; patterns: {id:[pattern]}."""
    out=[]
    for kind,value in netlang.choices(analysis['layers']):
        by=[]
        for did,text in docs.items():
            low=text.lower()
            if kind=='pattern':hit=value in patterns.get(did,[])
            elif kind in('kernel','avg'):hit=bool(re.search(rf'\b{value}\s*[x×]\s*{value}\b',low)) and (kind=='kernel' or bool(FEATURES['avg'].search(low)))
            elif kind=='stride':hit=bool(re.search(rf'stride\s*{value}\b',low))
            elif kind=='maps':hit=bool(re.search(rf'\b{value}\s+(?:feature\s+|cell\s+)?(?:maps|planes)\b',low))
            else:hit=bool(re.search(rf'(?:->\s*{value}\s*->|\b{value}\s+hidden)',low))
            if hit:by.append(did)
        out.append({'choice':kind,'value':value,'supported_by':by,'status':'sourced' if by else 'unsourced'})
    return out


class LenetTask:
    """The 1988 task: netlang specs, train_usps.py in the Sun-4 profile, error at rejection rates."""
    name='lenet';extra_keys=();max_epochs=30;TOOL_TEXT={}
    deterministic=True  # train_usps.py seeds torch and the batch order with 1988: same net and arguments, same numbers
    def __init__(self,L):self.L=L
    def analyze(self,spec,vocab):return netlang.canonical(spec,vocab),netlang.analyze(spec,vocab)
    def choices(self,analysis,docs,patterns):return support_check(analysis,docs,patterns)
    def eta(self,analysis,samples,epochs):return netlang.eta_days(analysis['connections'],samples,epochs)
    def vocabulary(self,view):return {'vocabulary':sorted(netlang.BASE_OPS)+view['vocabulary'],'locked':sorted(netlang.LOCKED_OPS-set(view['vocabulary']))}
    def packet(self,net,epochs,d,did,workspace):
        code=ROOT/self.L.config.get('code_dir','research/lenet')
        for name in CODE_FILES:
            src=code/name if name!='netlang.py' else ROOT/'goalagent/netlang.py'
            (workspace/name).write_bytes(src.read_bytes())
        return {'profile':self.L.config.get('training_profile','sun4'),'code_files':list(CODE_FILES),'entrypoint':'train_usps.py',
                'args':['--spec',net['spec'],'--epochs',str(epochs),'--net-id',net['id'],'--dataset-id',did],'dataset_ids':[did]}
    def matches(self,m,net):return m.get('net_id')==net['id'] and m.get('spec')==net['spec']
    def result(self,m):
        return {'error':m['val_error'],'reject_curve':m['reject_curve'],'invariance':m.get('invariance'),'samples':m['train_count']},m['parameters'],m.get('grad_check'),m.get('per_epoch',[])
    def measurement(self,m):return {'error':m['error'],'reject_curve':m['reject_curve'],'samples':m['samples']}


TASKS={'lenet':LenetTask}  # other task adapters register themselves here on import (goalagent/fashion_ledger.py)


def ledger_tools(task):
    """Tool descriptions for a task: the 1988 wording by default, overridden by the task adapter."""
    cfg=(task or {}).get('ledger') or {};return {**TOOLS,**TASKS[cfg.get('task','lenet')].TOOL_TEXT}


class LedgerRuntime:
    def __init__(self,team):
        self.team=team;self.config=team.task.get('ledger')
        self.state=team.state.setdefault('ledger',{'nodes':{},'views':{},'counters':{},'compute_days_used':0.0,'evaluations':0,'leak_log':[]})
        self.state.setdefault('mail',[]);self.state.setdefault('day',0.0);self.state.setdefault('pending',[]);self.state.setdefault('extra_compute_days',0.0)
        self.state.setdefault('demo_day',None);self.state.setdefault('meetings',[])
        self.docs={};self.patterns={};self.adapters={}
        if self.config is None:return
        allowed={'corpus','views','compute_days','max_evaluations','samples','training_profile','code_dir','dataset_name','vocabulary','feature_days','handles',
                 'clock','mail_delay_days','features_by_bottou','max_compute_days','chip_weights','visit_day','overrides','task','metric','datasets','templates','blacklist','evaluator'}
        if set(self.config)-allowed:raise ValueError('Unknown ledger configuration')
        self.task=TASKS[self.config.get('task','lenet')](self)
        corpus=ROOT/self.config['corpus'] if self.config.get('corpus') else None;register=json.loads((corpus/'register.json').read_text()) if corpus else {}
        overrides=self.config.get('overrides',{})  # {doc_id: {path, sha256, patterns?}}: a variant text replaces the corpus document under the same ID
        for did,meta in register.items():
            if did in overrides:meta={**meta,**overrides[did]};body=(ROOT/meta['path']).read_bytes()
            else:body=(corpus/(did+'.md')).read_bytes()
            if sha256(body)!=meta['sha256']:raise ValueError('Corpus document changed: '+did)
            self.docs[did]=body.decode('utf-8');self.patterns[did]=list(meta.get('patterns',[]))
            self.state['nodes'].setdefault(did,{'id':did,'type':'document','title':meta['title'],'date':meta['date'],'kind':meta['kind'],'sha256':meta['sha256']})
        if self.task.name=='lenet' and set(self.config.get('vocabulary',[]))-netlang.LOCKED_OPS:raise ValueError('Unknown vocabulary item')
        for hid,meta in self.config.get('handles',{}).items():
            if set(meta)!={'split','description'}:raise ValueError('Handle needs split and description')
            self.state['nodes'].setdefault(hid,{'id':hid,'type':'dataset','split':meta['split'],'description':meta['description']})
        for role,ids in self.config.get('views',{}).items():
            if role not in team.definitions:raise ValueError('Ledger view for unknown role: '+role)
            if not set(ids)<=set(self.docs)|set(self.config.get('handles',{})):raise ValueError('Ledger view cites unknown documents')
            view=self.view_for(role)
            for did in ids:
                if did not in view['nodes']:view['nodes'].append(did)
            for op in self.config.get('vocabulary',[]):
                if op not in view['vocabulary']:view['vocabulary'].append(op)
    # ---- helpers ----
    def role(self,agent):return agent.config['id']
    def view_for(self,role):return self.state['views'].setdefault(role,{'nodes':[],'vocabulary':[]})
    def view(self,agent):return self.view_for(self.role(agent))
    def visible(self,agent,node_id,kind=None):
        node=self.state['nodes'].get(node_id)
        if not node or node_id not in self.view(agent)['nodes']:raise ValueError('Not in your ledger view: '+str(node_id))
        if kind and node['type']!=kind:raise ValueError(node_id+' is not a '+kind)
        return node
    def new_id(self,prefix):
        n=self.state['counters'].get(prefix,0)+1;self.state['counters'][prefix]=n;return prefix+str(n)
    def add(self,agent,node):return self.add_for(self.role(agent),node)
    def add_for(self,role,node):
        self.state['nodes'][node['id']]=node;view=self.view_for(role)
        if node['id'] not in view['nodes']:view['nodes'].append(node['id'])
        self.team.event('ledger_'+node['type'],{'id':node['id'],'role':role});return node
    def cites(self,agent,text):
        if not isinstance(text,str) or not text.strip():raise ValueError('rationale text is required')
        found=CITE.findall(text);view=set(self.view(agent)['nodes'])
        return [c for c in found if c in view],[c for c in found if c not in view]
    def budget(self):return float(self.config.get('compute_days',30))+float(self.state.get('extra_compute_days',0.0))
    # ---- simulated clock ----
    def clock(self):return bool(self.config.get('clock',False))
    def now(self):return float(self.state['day'])
    def defer(self,role,kind,payload,ready):
        self.state['pending'].append({'role':role,'kind':kind,'payload':payload,'ready':float(ready)})
    def deliver(self):
        """Apply every pending item whose day has come; returns what was delivered (for the orchestrator's guidance)."""
        out=[];keep=[]
        for item in self.state['pending']:
            if item['ready']>self.now():keep.append(item);continue
            view=self.view_for(item['role'])
            if item['kind']=='node':
                if item['payload'] not in view['nodes']:view['nodes'].append(item['payload'])
            elif item['kind']=='vocab':
                if item['payload'] not in view['vocabulary']:view['vocabulary'].append(item['payload'])
            out.append(item)
        self.state['pending']=keep
        for item in list(out):
            node=self.state['nodes'].get(item['payload']) if item['kind']=='node' else None
            if node and node['type']=='result':out+=[{'role':item['role'],'kind':'node','payload':c,'ready':item['ready']} for c in self.auto_compare(item['role'],node)]
        return out
    def auto_compare(self,role,r):
        """Host comparisons for a delivered validation result at 9% rejection: against PIPELINE88 and against the best other net in the view."""
        if not self.reject_mode() or r['dataset']!=self.datasets()[0] or r['net']=='PIPELINE88':return []
        mine=[self.state['nodes'][i] for i in self.view_for(role)['nodes'] if i!=r['id']]
        others=[n for n in mine if n['type']=='result' and n['dataset']==r['dataset'] and n['net']!=r['net']]
        base=[n for n in others if n['net']=='PIPELINE88'];rest=[n for n in others if n['net']!='PIPELINE88']
        picks=base[-1:]+([min(rest,key=lambda n:self.score(n,'0.09'))] if rest else [])
        return [self.comparison(role,r,b,'0.09')['id'] for b in picks]
    def next_event(self):
        days=[i['ready'] for i in self.state['pending'] if i['ready']>self.now()]
        days+=[m['delivered'] for m in self.state['mail'] if m.get('delivered',0)>self.now()]
        return min(days) if days else None
    def seal(self,agent,node,ready):
        """Create a node that exists in the ledger now but enters the owner's view only on day `ready`."""
        self.state['nodes'][node['id']]=node;self.team.event('ledger_'+node['type'],{'id':node['id'],'role':self.role(agent),'sealed_until':ready})
        self.defer(self.role(agent),'node',node['id'],ready);return node
    def require_handle(self,agent,hid,purpose):
        if hid in self.state['nodes'] and hid not in self.view(agent)['nodes']:
            owners=[r for r,v in self.state['views'].items() if hid in v['nodes']]
            raise ValueError(f'{purpose} needs the data handle [{hid}], which is not in your view. Ask its owner ({", ".join(owners) or "unknown"}) by mail to attach it.')
    def supported_ids(self,agent):
        return [i for i in self.view(agent)['nodes'] if self.state['nodes'][i]['type']=='claim' and self.state['nodes'][i]['status']=='supported']
    def supported_for(self,role):
        return [i for i in self.view_for(role)['nodes'] if self.state['nodes'][i]['type']=='claim' and self.state['nodes'][i]['status']=='supported']
    def reject_mode(self):return self.config.get('metric',{}).get('key','reject_curve')=='reject_curve'
    def metric(self):return 'error' if self.reject_mode() else self.config['metric']['key']
    def datasets(self):return tuple(self.config.get('datasets',('usps-val','usps-test')))
    def templates(self):
        keys=dict(TEMPLATES)
        if not self.reject_mode():keys['BEATS']={'net_a','net_b','dataset'}
        chosen=self.config.get('templates');return {k:v for k,v in keys.items() if not chosen or k in chosen}
    def score(self,result,rate=None):return self.error_at(result,rate) if self.reject_mode() else float(result[self.metric()])
    def better(self,x,y):return x>y if self.config.get('metric',{}).get('higher_is_better') else x<y
    def require_split(self,agent,split,purpose):
        for hid,n in self.state['nodes'].items():
            if n['type']=='dataset' and n.get('split')==split:self.require_handle(agent,hid,purpose)
    def charge(self,days,what):
        if self.state['compute_days_used']+days>self.budget():raise ValueError(f'Compute budget exceeded: {what} costs {days:.2f} simulated days, {self.budget()-self.state["compute_days_used"]:.2f} remain.')
        self.state['compute_days_used']+=days
    def dispatch(self,agent,action,timeout):
        if self.config is None:raise ValueError('Ledger not configured for this task')
        tool=action['tool'];raw=action['argument']
        if tool!='mail_inbox':self.state.setdefault('polls',{})[self.role(agent)]=0
        if tool=='ledger_view':return self.render(agent)
        if tool=='lit_search':return self.search(agent,raw)
        if tool=='lit_read':return {'id':raw.strip(),'text':self.docs[self.visible(agent,raw.strip(),'document')['id']],'scope':'Stored excerpt or paraphrase; cite as ['+raw.strip()+']'}
        if tool=='mail_inbox':return self.inbox(agent)
        if tool=='pipeline_run':return self.pipeline(agent)
        d=json.loads(raw)
        if tool=='mail_send':return self.send(agent,d)
        if tool=='judge_verdict':return self.verdict(agent,d)
        if tool=='chip_estimate':return self.chip(agent,d)
        if tool=='implement_feature':return self.implement(agent,d)
        if tool=='compute_allocate':return self.allocate(agent,d)
        if tool=='schedule_demo':return self.demo(agent,d)
        if tool=='sn_define':return self.define(agent,d)
        if tool=='request_feature':return self.request_feature(agent,d)
        if tool=='sn_train':return self.train(agent,d,action,timeout)
        if tool=='ledger_evaluate':return self.evaluate(agent,d)
        if tool=='compare_results':return self.compare(agent,d)
        if tool=='ledger_claim':return self.claim(agent,d)
        if tool=='ledger_promote':return self.promote(agent,d)
        raise ValueError('Unknown ledger tool')
    # ---- read side ----
    @staticmethod
    def brief(n):
        """The host's one-line form of a node, shared by ledger_view and the orchestrator's guidance."""
        t=n['type']
        if t=='document':return {'id':n['id'],'title':n['title'],'date':n['date']}
        if t=='net_spec':return {'id':n['id'],'connections':n['analysis']['connections'],'params':n['analysis']['params'],'tied_layers':n['analysis']['tied_layers'],'pattern':n['analysis']['pattern'],'unsourced_choices':[c['choice'] for c in n['choices'] if c['status']=='unsourced'],'jobs':n.get('jobs',[])}
        if t=='result':return {'id':n['id'],'net':n['net'],'dataset':n['dataset'],**{k:n[k] for k in ('epochs','error','reject_curve','invariance','accuracy','loss') if k in n}}
        if t=='proof':return {'id':n['id'],'kind':n['kind'],'net':n['net'],'passed':n['passed']}
        if t=='claim':return {'id':n['id'],'template':n['template'],'args':n['args'],'status':n['status'],'evidence':n['evidence'],'guess':n['guess']}
        if t=='comparison':return {k:v for k,v in n.items() if k not in ('type','owner')}
        if t=='feature_request':return {k:n[k] for k in ('id','description','granted')}
        if t=='dataset':return {k:n[k] for k in ('id','split','description')}
        if t=='chip':return {k:n[k] for k in ('id','net','chip','weights','fits','chars_per_sec')}
        return {'id':n['id'],'type':t}
    def render(self,agent):
        view=self.view(agent);nodes=[self.state['nodes'][i] for i in view['nodes']];brief=self.brief
        groups={}
        for n in nodes:groups.setdefault(n['type'],[]).append(brief(n))
        return {'believe_only':'claims with status supported','supported':[c for c in groups.get('claim',[]) if c['status']=='supported'],
                'conjectures':[c for c in groups.get('claim',[]) if c['status']=='conjecture'],'refuted':[c for c in groups.get('claim',[]) if c['status']=='refuted'],
                'nets':groups.get('net_spec',[]),'results':groups.get('result',[]),'proofs':groups.get('proof',[]),'comparisons':groups.get('comparison',[]),
                'feature_requests':groups.get('feature_request',[]),'data_handles':groups.get('dataset',[]),'documents':groups.get('document',[]),
                'unread_mail':sum(1 for m in self.state['mail'] if m['to'] in (self.role(agent),'all') and m['from']!=self.role(agent) and not m['read'] and m.get('delivered',0)<=self.now()),
                'chips':groups.get('chip',[]),'day':self.now(),'demo_day':self.state.get('demo_day'),'visit_day':self.config.get('visit_day'),
                'sealed':[{'kind':i['kind'],'payload':i['payload'],'ready_day':i['ready']} for i in self.state['pending'] if i['role']==self.role(agent)],
                'compute_days':{'budget':self.budget(),'used':round(self.state['compute_days_used'],3),'remaining':round(self.budget()-self.state['compute_days_used'],3)},
                'evaluations':{'used':self.state['evaluations'],'max':int(self.config.get('max_evaluations',4))},
                **self.task.vocabulary(view)}
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
        vocab=self.view(agent)['vocabulary'];spec,analysis=self.task.analyze(d['spec'],vocab)
        cites,unknown=self.cites(agent,d['rationale']);samples=int(self.config.get('samples',6291))
        checks=self.task.choices(analysis,{c:self.docs[c] for c in cites if c in self.docs},self.patterns)
        unsourced=[c for c in checks if c['status']=='unsourced']
        node={'id':self.new_id('N'),'type':'net_spec','spec':spec,'analysis':analysis,'rationale':d['rationale'],
              'cites':cites,'unknown_cites':unknown,'choices':checks,'guess':bool(unsourced),'owner':self.role(agent),'jobs':[],
              'eta_days_per_epoch':self.task.eta(analysis,samples,1)}
        self.add(agent,node)
        if unsourced:self.state['leak_log'].append({'time':time.time(),'role':self.role(agent),'node':node['id'],'kind':'net_spec','unsourced':[(c['choice'],c['value']) for c in unsourced],'cites':cites,'unknown_cites':unknown})
        return {'net_id':node['id'],'connections':analysis['connections'],'params':analysis['params'],'pattern':analysis['pattern'],'layers':analysis['layers'],
                'eta_days_per_epoch':round(node['eta_days_per_epoch'],3),'choices':checks,
                'note':'unsourced = none of the documents you cited contains this choice; it is recorded as your own guess, not refused'}
    def request_feature(self,agent,d):
        if set(d)!={'description'} or not isinstance(d['description'],str) or not d['description'].strip():raise ValueError('request_feature needs {description}')
        desc=d['description'].strip()[:500];view=self.view(agent);granted=None
        for op,pat in FEATURES.items():
            if pat.search(desc):granted=op;break
        node={'id':self.new_id('FEAT'),'type':'feature_request','description':desc,'granted':granted,'owner':self.role(agent)}
        if granted and granted in view['vocabulary']:self.add(agent,node);return {'request_id':node['id'],'granted':granted,'note':'Already in your vocabulary'}
        if self.config.get('features_by_bottou'):
            node['granted']=None;node['status']='requested';self.add(agent,node)
            bview=self.view_for('bottou')
            if node['id'] not in bview['nodes']:bview['nodes'].append(node['id'])
            return {'request_id':node['id'],'status':'sent to the simulator maintainer (Bottou)','note':'He answers by letter with the day it becomes available; checkpoint while you wait'}
        if granted:
            days=float(self.config.get('feature_days',10));self.charge(days,'implementing '+granted)
            view['vocabulary'].append(granted);node['simulated_days']=days;self.add(agent,node)
            return {'request_id':node['id'],'granted':granted,'simulated_days':days,'compute_days_used':round(self.state['compute_days_used'],3),
                    'usage':'{"op":"avg","k":2} = fixed-weight 2x2 averaging with 2-to-1 subsampling, no trainable parameters'}
        self.add(agent,node);return {'request_id':node['id'],'granted':None,'note':'Not available from the simulator maintainer'}
    def dataset_id(self):
        name=self.config.get('dataset_name','usps-train')
        for did,r in self.team.training.state['datasets'].items():
            if r['name']==name:return did
        raise ValueError('Training dataset not registered: '+name)
    def train(self,agent,d,action,timeout):
        if not {'net_id','epochs'}<=set(d) or set(d)-{'net_id','epochs'}-set(self.task.extra_keys):raise ValueError('sn_train needs {net_id, epochs'+''.join(', '+k+'?' for k in self.task.extra_keys)+'}')
        net=self.visible(agent,d['net_id'],'net_spec');epochs=d['epochs']
        self.require_split(agent,'train','Training')
        if type(epochs) is not int or not 1<=epochs<=self.task.max_epochs:raise ValueError(f'epochs must be an integer in 1..{self.task.max_epochs}')
        key=json.dumps(d,sort_keys=True);done=self.state.setdefault('trained',{}).get(key)
        if done and getattr(self.task,'deterministic',False):
            sealed=[i for i in self.state['pending'] if i['kind']=='node' and i['payload']==done['result']]
            return {'job_id':done['job_id'],'result':done['result'],'proofs':done['proofs'],'simulated_days':0,'compute_days_used':round(self.state['compute_days_used'],3),
                    **({'sealed':{'result':done['result'],'ready_day':sealed[0]['ready']}} if sealed else {}),
                    'note':'Training is deterministic (seed 1988): this net was already trained with these arguments, so no job started and no computing time was charged. Cite the existing result.'}
        eta=self.task.eta(net['analysis'],int(self.config.get('samples',6291)),epochs)
        self.charge(eta,'this run')
        # In-flight marker, persisted with the charge: if the process dies before the result exists, recover_inflight refunds it.
        self.state.setdefault('inflight',{})[key]={'net':net['id'],'args':d,'days':eta,'job_id':None,'day':self.now()}
        try:return self._job(agent,d,action,timeout,net,epochs,eta,key)
        finally:self.state['inflight'].pop(key,None)
    def _job(self,agent,d,action,timeout,net,epochs,eta,key):
        did=self.dataset_id();packet=self.task.packet(net,epochs,d,did,Path(agent.workspace))
        status=self.team.training.start(agent,packet,self.team.dispatch_id(agent,action))
        job=self.team.training.state['jobs'][status['job_id']];self.state['inflight'][key]['job_id']=status['job_id']
        if status['job_id'] not in net['jobs']:net['jobs'].append(status['job_id'])
        deadline=time.time()+max(30,(timeout or 600)-20)
        while status['status'] in ('STARTING','RUNNING') and time.time()<deadline:
            time.sleep(5);status=self.team.training.status(job)
        out={'job_id':status['job_id'],'status':status['status'],'simulated_days':round(eta,3),'compute_days_used':round(self.state['compute_days_used'],3),'log_tail':status['log_tail'][-1500:]}
        if status['status']!='SUCCEEDED':return {**out,'result':None,'note':'No result node: only a succeeded job produces one'}
        metrics_path=self.team.training.root/'jobs'/status['job_id']/'output/metrics.json'
        raw=metrics_path.read_bytes();m=json.loads(raw)
        if not self.task.matches(m,net):raise ValueError('Job output does not match the net spec')
        fields,params,grad,per_epoch=self.task.result(m)
        start=max(self.now(),self.state.get('sun4_free',0.0))  # one Sun-4: a job starts when the previous one ends
        ready=round(start+eta,2)
        if self.clock():self.state['sun4_free']=ready
        put=(lambda n:self.seal(agent,n,ready)) if self.clock() else (lambda n:self.add(agent,n))
        result=put({'id':self.new_id('R'),'type':'result','net':net['id'],'dataset':self.datasets()[0],**fields,
            'epochs':epochs,'source':{'job_id':status['job_id'],'path':'metrics.json','sha256':sha256(raw)},'owner':self.role(agent)})
        proofs=[put({'id':self.new_id('P'),'type':'proof','kind':'PARAM_COUNT','net':net['id'],'passed':params==net['analysis']['params'],
                    'detail':{'ledger_params':net['analysis']['params'],'container_params':params},'source':result['source']})]
        if grad:
            proofs.append(put({'id':self.new_id('P'),'type':'proof','kind':'GRAD_CHECK','net':net['id'],'passed':bool(grad['passed']),'detail':grad,'source':result['source']}))
        self.state.setdefault('trained',{})[key]={'job_id':status['job_id'],'result':result['id'],'proofs':[p['id'] for p in proofs]}
        if self.clock():
            return {**out,'sealed':{'result':result['id'],'proofs':[p['id'] for p in proofs],'ready_day':round(ready,2),'today':self.now()},
                    'note':f'The department has one Sun-4 and it runs one job at a time: this job starts on day {start:.2f} and its numbers enter your view on ready_day. Checkpoint to let time pass, or design something else meanwhile.'}
        return {**out,'result':{k:v for k,v in result.items() if k in RESULT_KEYS},'proofs':[{k:p[k] for k in ('id','kind','passed')} for p in proofs],
                'per_epoch':per_epoch[-3:],'scope':'Validation split result, not protected test measurement'}
    def recover_inflight(self):
        """After a crash: refund every training run that was charged but never produced a result (deterministic, so a re-run is equal)."""
        out=[]
        for key,m in list(self.state.get('inflight',{}).items()):
            self.state['compute_days_used']=max(0.0,self.state['compute_days_used']-m['days']);self.state['inflight'].pop(key)
            self.team.event('ledger_refund',{'net':m['net'],'days':m['days'],'job_id':m['job_id']});out.append(m)
        return out
    def evaluate(self,agent,d):
        if set(d)!={'net_id'}:raise ValueError('ledger_evaluate needs {net_id}')
        net=self.visible(agent,d['net_id'],'net_spec');limit=int(self.config.get('max_evaluations',4))
        self.require_split(agent,'test','Protected evaluation')
        opens=self.state.get('demo_day') or self.config.get('visit_day')
        if self.clock() and opens and self.now()<opens:raise ValueError(f'The held-out test split opens on the Postal Service visit day (day {opens:g}); today is day {self.now():.1f}. Compare on usps-val until then.')
        jobs=[j for j in net.get('jobs',[]) if self.team.training.state['jobs'][j]['status']=='SUCCEEDED']
        if not jobs:raise ValueError('No succeeded job for '+net['id'])
        if self.state['evaluations']>=limit:raise ValueError('Protected evaluation limit reached')
        model=self.team.training.register_model(agent,jobs[-1],'weights.safetensors','model',trusted=True)  # the net is in the caller's view; job ownership belongs to the ledger
        self.state['evaluations']+=1
        record=self.team.training.evaluate(agent,model['id'],self.config.get('evaluator','usps_test'),trusted=True);m=record['measurement']
        result=self.add(agent,{'id':self.new_id('R'),'type':'result','net':net['id'],'dataset':self.datasets()[1],**self.task.measurement(m),
            'source':{'evidence_id':record['evidence_id'],'model_id':model['id'],'job_id':jobs[-1]},'owner':self.role(agent)})
        return {'result':{k:v for k,v in result.items() if k in RESULT_KEYS},'model_id':model['id'],'evidence_id':record['evidence_id'],'evaluations_remaining':limit-self.state['evaluations'],'scope':record['scope']}
    def error_at(self,result,rate):
        if rate not in REJECT_RATES:raise ValueError('reject_rate must be one of '+', '.join(REJECT_RATES))
        return float(result['reject_curve'][rate])
    def compare(self,agent,d):
        keys={'a','b','reject_rate'} if self.reject_mode() else {'a','b'}
        if set(d)!=keys:raise ValueError('compare_results needs {'+', '.join(sorted(keys))+'}')
        a=self.visible(agent,d['a'],'result');b=self.visible(agent,d['b'],'result');rate=str(d['reject_rate']) if self.reject_mode() else None
        if a['dataset']!=b['dataset']:raise ValueError('Results come from different datasets: '+a['dataset']+' vs '+b['dataset'])
        node=self.comparison(self.role(agent),a,b,rate)
        return {k:v for k,v in node.items() if k not in ('type','owner')}
    def comparison(self,role,a,b,rate):
        ea,eb=self.score(a,rate),self.score(b,rate);m=self.metric()
        return self.add_for(role,{'id':self.new_id('CMP'),'type':'comparison','a':a['id'],'b':b['id'],'dataset':a['dataset'],'metric':m,'reject_rate':rate,m+'_a':ea,m+'_b':eb,
                             'winner':a['id'] if self.better(ea,eb) else b['id'] if self.better(eb,ea) else 'tie','owner':role})
    def claim(self,agent,d):
        if set(d)!={'template','args','rationale'}:raise ValueError('ledger_claim needs {template, args, rationale}')
        t=d['template'];args=d['args'];T=self.templates()
        if t not in T:raise ValueError('Free-text claims stay conjectures forever; use a template: '+', '.join(T))
        if not isinstance(args,dict) or set(args)!=T[t]:raise ValueError(t+' args must be exactly '+', '.join(sorted(T[t])))
        for key in ('net','net_a','net_b'):
            if key in args:self.visible(agent,args[key],'net_spec')
        if t=='MORE_INVARIANT':
            if args['transform'] not in ('shift1','shift2'):raise ValueError('MORE_INVARIANT needs transform shift1|shift2')
            if args['net_a']==args['net_b']:raise ValueError('MORE_INVARIANT compares two different nets')
        if t=='FITS_CHIP' and args['chip']!='anna':raise ValueError('The only chip is "anna"')
        if t=='BEATS':
            if args['dataset'] not in self.datasets():raise ValueError('dataset must be one of '+', '.join(self.datasets()))
            if self.reject_mode():
                if str(args['reject_rate']) not in REJECT_RATES:raise ValueError('reject_rate must be one of '+', '.join(REJECT_RATES))
                args['reject_rate']=str(args['reject_rate'])
        cites,unknown=self.cites(agent,d['rationale'])
        node={'id':self.new_id('C'),'type':'claim','template':t,'args':args,'status':'conjecture','rationale':d['rationale'],'cites':cites,'unknown_cites':unknown,'guess':not cites,'evidence':[],'owner':self.role(agent)}
        self.add(agent,node)
        if node['guess']:self.state['leak_log'].append({'time':time.time(),'role':self.role(agent),'node':node['id'],'kind':'claim','unknown_cites':unknown})
        # The host tries the deterministic promotion at once with every eligible node in the claimant's view; nothing the model wrote is evidence.
        nets={args[k] for k in ('net','net_a','net_b') if k in args}
        eligible=[i for i in self.view(agent)['nodes'] if self.state['nodes'][i]['type'] in ('result','proof','chip') and self.state['nodes'][i].get('net') in nets]
        try:return {**self.promote(agent,{'claim_id':node['id'],'evidence_ids':eligible}),'guess':node['guess']}
        except ValueError as error:
            return {'claim_id':node['id'],'status':'conjecture','guess':node['guess'],'not_yet_decidable':str(error),'note':'Promote with ledger_promote once the evidence is in your view; speech cannot promote it'}
    def latest(self,agent,net,dataset,transform=None):
        """The most recently created result for a net on a dataset in the view: re-runs cannot be cherry-picked."""
        order={k:i for i,k in enumerate(self.state['nodes'])};nodes=self.state['nodes']
        rs=[nodes[i] for i in self.view(agent)['nodes'] if nodes[i]['type']=='result' and nodes[i]['net']==net and nodes[i]['dataset']==dataset
            and (transform is None or (nodes[i].get('invariance') or {}).get(transform) is not None)]
        return max(rs,key=lambda r:order[r['id']]) if rs else None
    def promote(self,agent,d):
        if isinstance(d,dict) and set(d)=={'claim_ids','evidence_ids'} and isinstance(d['claim_ids'],list) and d['claim_ids']:
            out=[]
            for cid in d['claim_ids']:
                try:out.append(self.promote(agent,{'claim_id':cid,'evidence_ids':d['evidence_ids']}))
                except ValueError as error:out.append({'claim_id':cid,'error':str(error)})
            return {'claims':out}
        if set(d)!={'claim_id','evidence_ids'} or not isinstance(d['evidence_ids'],list):raise ValueError('ledger_promote needs {claim_id or claim_ids:[...], evidence_ids:[...]}')
        c=self.visible(agent,d['claim_id'],'claim');role=self.role(agent);c.setdefault('endorsed_by',[])
        if c['status']!='conjecture':
            if role in c['endorsed_by']:return {'claim_id':c['id'],'status':c['status'],'evidence':c['evidence'],'endorsed_by':c['endorsed_by'],'agreed':len(c['endorsed_by'])>=2,'note':'Already decided'}
            missing=[e for e in c['evidence'] if e not in self.view(agent)['nodes']]
            if missing:raise ValueError('To promote this claim yourself you need its evidence in your view; missing: '+', '.join(missing))
            c['endorsed_by'].append(role);self.team.event('ledger_endorse',{'claim':c['id'],'role':role})
            return {'claim_id':c['id'],'status':c['status'],'evidence':c['evidence'],'detail':c.get('detail'),'endorsed_by':c['endorsed_by'],'agreed':len(c['endorsed_by'])>=2}
        evidence=[self.visible(agent,e) for e in d['evidence_ids']]
        t=c['template'];a=c['args']
        if t=='FEWER_PARAMS':
            pa=self.visible(agent,a['net_a'],'net_spec')['analysis']['params'];pb=self.visible(agent,a['net_b'],'net_spec')['analysis']['params']
            verdict='supported' if pa<pb else 'refuted';detail={'params_a':pa,'params_b':pb};used=[a['net_a'],a['net_b']]
        elif t=='GRAD_EQUALS':
            proofs=[e for e in evidence if e['type']=='proof' and e['kind']=='GRAD_CHECK' and e['net']==a['net']]
            if not proofs:raise ValueError('GRAD_EQUALS needs a GRAD_CHECK proof node for '+a['net'])
            verdict='supported' if all(p['passed'] for p in proofs) else 'refuted';detail={p['id']:p['detail'] for p in proofs};used=[p['id'] for p in proofs]
        elif t=='FITS_CHIP':
            chips=[e for e in evidence if e['type']=='chip' and e['net']==a['net'] and e['chip']==a['chip']]
            if not chips:raise ValueError('FITS_CHIP needs a chip node for '+a['net']+' from chip_estimate among the evidence')
            verdict='supported' if all(k['fits'] for k in chips) else 'refuted';detail={k['id']:{'weights':k['weights'],'capacity':k['capacity']} for k in chips};used=[k['id'] for k in chips]
        elif t=='MORE_INVARIANT':
            x=a['transform'];ra=self.latest(agent,a['net_a'],self.datasets()[0],x);rb=self.latest(agent,a['net_b'],self.datasets()[0],x)
            if not ra or not rb:raise ValueError(f'MORE_INVARIANT needs a {self.datasets()[0]} result carrying a {x} measurement for each net in your view')
            ka,kb=ra['invariance'][x],rb['invariance'][x]
            verdict='supported' if ka>kb else 'refuted';detail={'kept_a':ka,'kept_b':kb,'transform':x,'results':[ra['id'],rb['id']]};used=[ra['id'],rb['id']]
        else:
            ra=self.latest(agent,a['net_a'],a['dataset']);rb=self.latest(agent,a['net_b'],a['dataset'])
            if not ra or not rb:raise ValueError('BEATS needs one result for each net on dataset '+a['dataset']+' in your view; results on other datasets do not count')
            rate=a.get('reject_rate');m=self.metric()
            ea=self.score(ra,rate);eb=self.score(rb,rate)
            verdict='supported' if self.better(ea,eb) else 'refuted';detail={m+'_a':ea,m+'_b':eb,'reject_rate':rate,'latest_results':[ra['id'],rb['id']]};used=[ra['id'],rb['id']]
        c['status']=verdict;c['evidence']=used;c['detail']=detail;c['decided_at']=time.time();c['endorsed_by']=[role]
        self.team.event('ledger_promote',{'claim':c['id'],'status':verdict,'role':role})
        unlocked=[]
        if verdict=='supported' and t=='BEATS' and self.state['nodes'][a['net_a']]['analysis']['tied_layers']>0:
            view=self.view(agent)
            if 'shared_map' not in view['vocabulary']:view['vocabulary'].append('shared_map');unlocked.append('shared_map')
        return {'claim_id':c['id'],'status':verdict,'evidence':used,'detail':detail,'unlocked_vocabulary':unlocked,'endorsed_by':c['endorsed_by'],'agreed':False}
    # ---- mail: the only channel between roles ----
    def send(self,agent,d):
        if set(d)!={'to','body','attach'} or not isinstance(d['attach'],list) or not isinstance(d['body'],str):raise ValueError('mail_send needs {to, body, attach:[...]}')
        sender=self.role(agent);to=d['to']
        if to!='all' and (to not in self.team.definitions or to==sender or to=='judge'):raise ValueError('Unknown recipient role: '+str(to))
        if not d['body'].strip() or len(d['body'])>6000:raise ValueError('Letter body must be 1..6000 characters')
        for nid in d['attach']:self.visible(agent,nid)
        violations=judge.check_text(d['body'],self.view(agent)['nodes'],self.supported_ids(agent),judge.BLACKLIST if self.config.get('blacklist',True) else [])
        if violations:
            self.state['leak_log'].append({'time':time.time(),'role':sender,'kind':'mail_rejected','violations':violations,'body':d['body'][:500]})
            raise ValueError('Letter refused by the judge ('+judge.describe(violations)+'). Rewrite it: 1988 vocabulary, cite only IDs in your view, attach an ID to every number, call nothing verified without a supported claim ID.')
        if self.clock():  # the meeting floor too: one statement per person per day
            today=[m for m in self.state['mail'] if m['from']==sender and m['to']==to and m.get('sent_day')==self.now()]
            if today:raise ValueError(f'You already wrote to {to} today ({today[-1]["id"]}); the mail goes out once a day and no answer can arrive while you keep writing. Checkpoint to let the day pass, then act on the reply.')
        recipients=[r for r in self.team.definitions if r not in (sender,'judge')] if to=='all' else [to]
        for r in recipients:
            view=self.view_for(r)
            for nid in d['attach']:
                if nid not in view['nodes']:view['nodes'].append(nid)
        delay=float(self.config.get('mail_delay_days',1)) if self.clock() and to!='all' else 0.0
        mail={'id':self.new_id('M'),'from':sender,'to':to,'body':d['body'],'attach':list(d['attach']),'time':time.time(),'read':False,'verdict':None,
              'sent_day':self.now(),'delivered':self.now()+delay,'read_by':[]}
        self.state['mail'].append(mail);self.team.event('ledger_mail',{'id':mail['id'],'from':sender,'to':to,'attach':mail['attach'],'day':self.now()})
        out={'mail_id':mail['id'],'delivered_to':to,'attached':mail['attach'],'arrives_day':mail['delivered'],'note':'A reply takes time; checkpoint if you must wait for it'}
        if getattr(agent,'assignment',{}).get('ends_on_letter'):  # a woken colleague's letter is its last action: the host writes the finish
            from .toolkit import workspace_action
            workspace_action(agent,{'tool':'finish','argument':json.dumps({'summary':f'Letter {mail["id"]} to {to} sent; the host closed the assignment','files':['note.md']}),'why':'host: the letter is the last action'},None)
            out['note']='Your letter is sent. It was your last action: the host has closed this assignment.'
        return out
    def inbox(self,agent):
        role=self.role(agent);rows=[];recent=[]
        for m in self.state['mail']:
            if m['to'] not in (role,'all') or m['from']==role or m.get('delivered',0)>self.now():continue
            seen=m.setdefault('read_by',[])
            if role not in seen:
                seen.append(role);m['read']=True;rows.append({'id':m['id'],'from':m['from'],'to':m['to'],'body':m['body'],'attach':m['attach']})
            else:recent.append({'id':m['id'],'from':m['from'],'to':m['to'],'body':m['body'],'attach':m['attach']})
        polls=self.state.setdefault('polls',{});polls[role]=0 if rows else polls.get(role,0)+1
        if polls[role]>=3:raise ValueError('You have read every letter; nobody writes until you act. Use the letters below and take a design, training, claim or mail_send action now. '+json.dumps({'letters_already_read':recent[-3:]})[:3000])
        return {'letters':rows,'already_read':recent[-3:],'note':'Attached nodes are already in your view' if rows else 'No unread letters; a reply arrives only after you send a letter and checkpoint. Act on the letters you have.'}
    def verdict(self,agent,d):
        if self.role(agent)!='judge':raise ValueError('Only the judge records verdicts')
        if set(d)!={'mail_id','verdict','reason'} or d['verdict'] not in ('pass','future_knowledge','unsupported'):raise ValueError('judge_verdict needs {mail_id, verdict:pass|future_knowledge|unsupported, reason}')
        m=next((m for m in self.state['mail'] if m['id']==d['mail_id']),None)
        if not m:raise ValueError('Unknown mail')
        m['verdict']={'verdict':d['verdict'],'reason':str(d['reason'])[:1000]}
        if d['verdict']!='pass':self.state['leak_log'].append({'time':time.time(),'role':m['from'],'kind':'judge_'+d['verdict'],'mail':m['id'],'reason':m['verdict']['reason']})
        return {'mail_id':m['id'],'recorded':d['verdict']}
    # ---- department roles ----
    def chip(self,agent,d):
        if self.role(agent)!='boser':raise ValueError('Only the chip designer estimates chip fit')
        if set(d)!={'net_id'}:raise ValueError('chip_estimate needs {net_id}')
        net=self.visible(agent,d['net_id'],'net_spec');cap=int(self.config.get('chip_weights',4096));w=net['analysis']['params']
        old=[n for n in self.state['nodes'].values() if n['type']=='chip' and n['net']==net['id']]
        if old:return {k:old[0][k] for k in ('id','net','chip','weights','capacity','fits','chars_per_sec','connections')}|{'note':'Already estimated; cite this chip node instead of estimating again'}
        node=self.add(agent,{'id':self.new_id('K'),'type':'chip','net':net['id'],'chip':'anna','weights':w,'capacity':cap,'fits':w<=cap,
                             'chars_per_sec':1000 if w<=cap else 0,'connections':net['analysis']['connections'],'owner':'boser'})
        return {k:node[k] for k in ('id','net','chip','weights','capacity','fits','chars_per_sec','connections')}|{'note':'The chip stores weights, not connections; shared weights are what make a network fit'}
    def implement(self,agent,d):
        if self.role(agent)!='bottou':raise ValueError('Only the simulator maintainer implements features')
        if set(d)!={'request_id'}:raise ValueError('implement_feature needs {request_id}')
        node=self.visible(agent,d['request_id'],'feature_request')
        if node.get('granted'):return {'request_id':node['id'],'granted':node['granted'],'ready_day':node.get('ready_day'),'note':'Already implemented'}
        op=next((op for op,pat in FEATURES.items() if pat.search(node['description'])),None)
        if not op:node['status']='refused';return {'request_id':node['id'],'granted':None,'note':'SN cannot get this; tell the requester'}
        days=float(self.config.get('feature_days',10));ready=self.now()+days
        node['granted']=op;node['status']='implementing';node['ready_day']=ready;node['simulated_days']=days
        self.defer(node['owner'],'vocab',op,ready);self.team.event('ledger_feature',{'id':node['id'],'op':op,'ready':ready})
        return {'request_id':node['id'],'granted':op,'ready_day':ready,'simulated_days':days,'usage':'{"op":"avg","k":2} = fixed-weight 2x2 averaging with 2-to-1 subsampling'}
    def allocate(self,agent,d):
        if self.role(agent)!='jackel':raise ValueError('Only the department head allocates computing time')
        if set(d)!={'days'} or not isinstance(d['days'],(int,float)) or not 0<d['days']<=30:raise ValueError('compute_allocate needs {days} in (0,30]')
        cap=float(self.config.get('max_compute_days',60));base=float(self.config.get('compute_days',30))
        if base+self.state['extra_compute_days']+d['days']>cap:raise ValueError(f'Department cap is {cap} simulated days in total')
        self.state['extra_compute_days']+=float(d['days']);self.team.event('ledger_allocate',{'days':d['days'],'budget':self.budget()})
        return {'added_days':d['days'],'budget_days':self.budget(),'used':round(self.state['compute_days_used'],3)}
    def demo(self,agent,d):
        if self.role(agent)!='jackel':raise ValueError('Only the department head books the demonstration')
        if self.state.get('demo_day'):return {'demo_day':self.state['demo_day'],'note':'Already booked; the booking stands. Do not call schedule_demo again.'}
        if set(d)!={'day'} or not isinstance(d['day'],(int,float)) or d['day']<=self.now():raise ValueError('schedule_demo needs {day} later than today')
        visit=self.config.get('visit_day',0)
        if d['day']<visit:raise ValueError(f'The Postal Service visit is on day {visit:g}; the demonstration cannot be booked earlier than that')
        fits=[i for i in self.view(agent)['nodes'] if self.state['nodes'][i]['type']=='claim' and self.state['nodes'][i]['template']=='FITS_CHIP' and self.state['nodes'][i]['status']=='supported']
        if not fits:raise ValueError('No supported FITS_CHIP claim in your view; ask Boser for a chip estimate and a promoted claim first')
        self.state['demo_day']=float(d['day']);self.team.event('ledger_demo',{'day':d['day'],'claims':fits})
        return {'demo_day':d['day'],'based_on':fits}
    # ---- baseline pipeline (data owner's adapter) ----
    def pipeline(self,agent):
        self.require_handle(agent,'USPS_TRAIN','The baseline');self.require_handle(agent,'USPS_TEST','The baseline')
        adapter=self.adapters.get('baseline88')
        if adapter is None:raise ValueError('Baseline adapter not installed for this run')
        existing=[n for n in self.state['nodes'].values() if n['type']=='result' and n['net']=='PIPELINE88']
        if existing:
            for n in existing:self.add(agent,n)
            self.add(agent,self.state['nodes']['PIPELINE88'])
            return {'results':[{k:n[k] for k in ('id','net','dataset','error','reject_curve')} for n in existing],'note':'Baseline already measured'}
        m=adapter();key='baseline-'+digest([adapter.version,m])[:24]
        record=self.team.record(key,{'adapter':'baseline88','version':adapter.version,'measurement':m,'scope':'Maintainer-owned hand-designed baseline adapter; reads the test split in its own container'})
        if 'PIPELINE88' not in self.state['nodes']:
            self.add(agent,{'id':'PIPELINE88','type':'net_spec','spec':'hand-designed templates + least-squares classifier','analysis':{'connections':m['features']*10+16*16*4*9,'params':m['classifier_params'],'tied_layers':0,'pattern':'template1>avg>full>output','layers':[]},
                            'rationale':'[DENKER88] stand-in baseline','cites':['DENKER88'],'unknown_cites':[],'choices':[],'guess':False,'owner':self.role(agent),'jobs':[]})
        out=[]
        for split,dataset in (('val','usps-val'),('test','usps-test')):
            r=self.add(agent,{'id':self.new_id('R'),'type':'result','net':'PIPELINE88','dataset':dataset,'error':m[split]['error'],'reject_curve':m[split]['reject_curve'],'samples':m[split]['samples'],
                              **({'invariance':m[split]['invariance']} if 'invariance' in m[split] else {}),
                              'source':{'evidence_id':record['evidence_id'],'adapter':'baseline88'},'owner':self.role(agent)})
            out.append({k:r[k] for k in ('id','net','dataset','error','reject_curve')})
        return {'results':out,'baseline_net':'PIPELINE88','scope':record['scope']}
    # ---- audit (host-side invariant check, no model involved) ----
    def audit(self):
        nodes=list(self.state['nodes'].values());bad_results=[];bad_claims=[]
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
        nets=[n for n in nodes if n['type']=='net_spec'];by_kind={}
        for n in nets:
            for c in n['choices']:
                if c['status']=='unsourced':by_kind[c['choice']]=by_kind.get(c['choice'],0)+1
        counts={t:sum(1 for n in nodes if n['type']==t) for t in ('document','net_spec','result','proof','claim','comparison','feature_request','dataset')}
        mail=self.state['mail'];agreed=[n['id'] for n in nodes if n['type']=='claim' and len(n.get('endorsed_by',[]))>=2]
        return {'nodes':counts,'results_without_provenance':bad_results,'supported_without_evidence':bad_claims,
                'choices_total':sum(len(n['choices']) for n in nets),'unsourced_choices':sum(by_kind.values()),'unsourced_by_kind':by_kind,
                'unsourced_patterns':[{'net':n['id'],'pattern':n['analysis']['pattern'],'cites':n['cites']} for n in nets if any(c['choice']=='pattern' and c['status']=='unsourced' for c in n['choices'])],
                'guess_nets':[n['id'] for n in nets if n['guess']],'guess_claims':[n['id'] for n in nodes if n['type']=='claim' and n['guess']],
                'feature_requests':[{k:n[k] for k in ('id','description','granted')} for n in nodes if n['type']=='feature_request'],
                'claims_by_status':{s:sum(1 for n in nodes if n['type']=='claim' and n['status']==s) for s in ('conjecture','supported','refuted')},
                'agreed_claims':agreed,'day':self.now(),'demo_day':self.state.get('demo_day'),'meetings':self.state.get('meetings',[]),'sealed_pending':len(self.state['pending']),
                'chips':[{k:n[k] for k in ('id','net','weights','fits')} for n in nodes if n['type']=='chip'],'extra_compute_days':self.state.get('extra_compute_days',0.0),
                'mail':{'sent':len(mail),'rejected':sum(1 for e in self.state['leak_log'] if e['kind']=='mail_rejected'),
                        'verdicts':{v:sum(1 for m in mail if (m.get('verdict') or {}).get('verdict')==v) for v in ('pass','future_knowledge','unsupported')},'unjudged':sum(1 for m in mail if not m.get('verdict'))},
                'leak_log':self.state['leak_log'],'invariant_holds':not bad_results and not bad_claims}
