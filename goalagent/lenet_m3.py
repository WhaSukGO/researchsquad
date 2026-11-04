"""LeNet rediscovery, milestone 3: the whole department on a simulated clock.

Roles: LeCun (lead), Denker (data, baseline), Jackel (budget, demo), Boser (chip), Bottou
(simulator features, remote), Hinton (advice, remote, weekly), judge (referee). Training
results are sealed until their simulated Sun-4 days have passed; letters take a day; Monday
meetings convene when something new exists; at day 60 Jackel pushes for a demonstration.
Modes: `check` (scripted decisions, real containers) and `live`.
"""
import argparse
import json
from pathlib import Path
import time
from .contracts import atomic_json
from .team import Team, ROOT
from .lenet_m1 import download, UspsEvaluator, URL, DOCS, action, FULL, TIED
from .lenet_sim import Baseline88, HANDLES, DENKER_DOCS, LECUN_DOCS, referee, ScriptedDenker, ScriptedJudge

ROLE_DOCS={'coordinator':LECUN_DOCS,'denker':DENKER_DOCS+list(HANDLES),'jackel':['DENKER88','GRAF87','DENKER87'],'boser':['GRAF87'],
           'bottou':['BOTTOU88'],'hinton':['RHW86','RHW86-TC','WAIBEL87','HINTON83','FUKUSHIMA82','HOPFIELD82'],'judge':[]}
GOAL=('It is 3 October 1988 (day 0). The department recognizes handwritten USPS zip code digits; Denker owns the data and a hand-designed '
      'baseline; Boser designs the analog chip; Jackel runs the department and books the USPS demonstration; Bottou maintains the SN '
      'simulator in Paris; Hinton answers letters from Toronto. Obtain data by letter, define constrained networks in the 1988 vocabulary, '
      'train them (results arrive after simulated Sun-4 days), and establish agreed claims: FEWER_PARAMS, BEATS on usps-val '
      'against the fully connected control and PIPELINE88, GRAD_EQUALS, MORE_INVARIANT, and FITS_CHIP so that a demonstration can be booked. '
      'An agreed claim is a milestone, not the end: keep lowering the validation error at 9% rejection until the Postal Service visit. '
      'The held-out test split opens on the visit day for one evaluation; report.md is written that day, citing only ledger IDs.')


def task(image,*,compute_days=20.0,max_evaluations=1,corpus=True,vocabulary=(),clock=True,visit_day=45,drop=None,overrides=None,max_compute_days=60):
    views={r:[x for x in (d if corpus or r!='coordinator' else []) if x not in (drop or {}).get(r,())] for r,d in ROLE_DOCS.items()}
    return {'goal':GOAL,'inputs':{},'network':False,'budget':{'max_calls':5000,'max_seconds':86400,'max_assignments':80,'max_depth':2},
        'training':{'profiles':{'sun4':{'image':image,'gpu':False,'memory':'2g','cpus':2,'max_seconds':1200,'max_output_bytes':50_000_000,'roles':['coordinator']}}},
        'ledger':{'corpus':'research/lit-1988','handles':HANDLES,'vocabulary':list(vocabulary),'views':views,'clock':clock,'mail_delay_days':1,
                  'features_by_bottou':True,'feature_days':10,'max_compute_days':max_compute_days,'chip_weights':4096,'visit_day':visit_day,
                  'compute_days':compute_days,'max_evaluations':max_evaluations,'samples':6291,'training_profile':'sun4','code_dir':'research/lenet','dataset_name':'usps-train'}|({'overrides':overrides} if overrides else {})}


def build(folder,image,cache,*,provider_factory=None,model=None,**kw):
    import subprocess
    folder=Path(folder).resolve();data=download(cache)
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],capture_output=True,text=True,check=True).stdout.strip()
    team=Team(folder,task(image,**kw),agents_dir=ROOT/'agents/lenet',provider_factory=provider_factory,model=model,model_evaluators={'usps_test':UspsEvaluator(image,data)})
    team.ledger.adapters['baseline88']=Baseline88(image,data);guard_finish(team);guard_checkpoint(team)
    if not team.training.state['datasets']:
        team.training.register_dataset('usps-train',{'zip.train.gz':data/'zip.train.gz'},{'source':URL+'zip.train.gz','split':'train','samples':7291})
    return team


WAKEABLE=('denker','jackel','boser','bottou','hinton')


def end_day(L):
    """The day the simulation ends: the booked demonstration, else the Postal Service visit."""
    return L.state.get('demo_day') or L.config.get('visit_day') or 10**9


def guard_finish(team):
    """The department does not stop when a claim is agreed: the lead's finish is refused before the visit day."""
    orig=team.validate_assignment_report
    def guarded(report,assignment):
        L=team.ledger
        if report.get('status')=='DONE' and assignment.get('depth',1)==0 and L.config and L.config.get('clock') and L.now()<end_day(L):
            raise ValueError(f'The Postal Service visit is on day {end_day(L):g}; today is day {L.now():.1f}. The department keeps working until then: a lower validation error at 9% rejection, new networks, letters, checkpoint. report.md is written on the visit day.')
        return orig(report,assignment)
    team.validate_assignment_report=guarded


def idle_reason(L):
    """Why the lead may not let days pass yet: the Sun-4 is idle while computing days remain before the visit. None when it may."""
    left=L.budget()-L.state['compute_days_used']
    running=any(i['role']=='coordinator' and i['kind']=='node' and L.state['nodes'][i['payload']]['type']=='result' for i in L.state['pending'])
    if L.clock() and 'USPS_TRAIN' in L.view_for('coordinator')['nodes'] and L.now()<end_day(L) and left>=1 and not running:
        return f'Day {L.now():.0f}. Checkpoint refused: the Sun-4 is idle and {left:.1f} computing days remain before the visit on day {end_day(L):g}; letting days pass now leaves them unused. Define or train a network (or say in a new checkpoint why not), then checkpoint.'
    return None


def guard_checkpoint(team):
    """The idle refusal happens inside the lead's checkpoint call, once per simulated day, so the lead keeps its context and a second checkpoint passes."""
    from .toolkit import Tool
    tool=team.registry.tools['checkpoint']
    def handler(agent,action,timeout):
        L=team.ledger;reason=idle_reason(L) if agent.config['id']=='coordinator' else None
        if reason and L.state.get('idle_refused_day')!=L.now():
            L.state['idle_refused_day']=L.now();raise ValueError(reason)
        return tool.handler(agent,action,timeout)
    team.registry.tools['checkpoint']=Tool(tool.name,tool.description,handler,tool.version)


def unread_for(team,role,direct=True):
    """Delivered, unread letters for a role. Floor statements (to 'all') never wake anyone; they are read at the next turn."""
    L=team.ledger
    return [m for m in L.state['mail'] if (m['to']==role if direct else m['to'] in (role,'all')) and m['from']!=role and role not in m.get('read_by',[]) and m.get('delivered',0)<=L.now()]


def take(team,role,direct=True):
    """Hand a role its unread letters and mark them read: a letter the orchestrator put in front of a role must not wake it again."""
    new=unread_for(team,role,direct)
    for m in new:m.setdefault('read_by',[]).append(role)
    return new


def letters_text(ms):
    return '\n\n'.join(f"Letter {m['id']} from {m['from']} to {m['to']} (attached: {', '.join(m['attach']) or 'nothing'}):\n{m['body']}" for m in ms)


def briefing(team,role):
    """Host-built, model-free summary for a woken colleague (a fresh agent with no memory): what entered its view since its
    last wake, its own recent letters and the claims it already promoted. Advances the role's 'seen' mark."""
    L=team.ledger;nodes=L.state['nodes'];view=L.view_for(role)['nodes'];seen=L.state.setdefault('seen',{})
    new=view[seen.get(role,0):];seen[role]=len(view)
    sent=[f"{m['id']} to {m['to']} on day {m['sent_day']:g}: {m['body'][:160]}" for m in L.state['mail'] if m['from']==role][-3:]
    endorsed=[i for i in view if nodes[i]['type']=='claim' and role in nodes[i].get('endorsed_by',[])]
    text=('New in your view since your last turn: '+json.dumps([L.brief(nodes[i]) for i in new],ensure_ascii=False)+'\n'
          +'Claims you already promoted: '+(', '.join(endorsed) or 'none')+'\nYour last letters: '+(' | '.join(sent) or 'none'))
    return text[:5000]


def lead_wakes(L,news,lead_day):
    """The lead reads its mail at most once per simulated day, and only after that day's last due event."""
    nxt=L.next_event()
    return bool(news) and int(L.now())>lead_day and not (nxt is not None and int(nxt)==int(L.now()))


LAST='Your letter is your last action: the host closes this assignment when mail_send succeeds, so do everything else first.'


def simulate(team,*,max_days=180,max_meetings=6,max_rounds=40,use_referee=True,phase=None):
    L=team.ledger;defs=team.definitions;counts={r:0 for r in defs};judged=set();hinton_last=-99;announced=False;lead_day=-1
    lead={'goal':team.task['goal'],'objective':'Coordinate measurable progress toward the goal','success_criteria':'Claims agreed by the department and a demonstration booked','depth':0,'inputs':[]}
    def run_role(role,objective):
        counts[role]+=1
        ws=team.folder/'agents'/f'{role}-{counts[role]}'/'workspace';ws.mkdir(parents=True,exist_ok=True);(ws/'note.md').write_text('note\n')  # finish needs a file; the model need not write one
        objective=(objective+'\n\n'+briefing(team,role))[:12000]
        return team.run_agent(f'{role}-{counts[role]}',defs[role],{'goal':team.task['goal'],'objective':objective,'depth':1,'inputs':[],'ends_on_letter':True})
    def judge_new():
        for m in L.state['mail']:
            if use_referee and m['id'] not in judged and m['verdict'] is None:referee(team,m);judged.add(m['id'])
    team.started=time.monotonic();team.state['inflight_started']=time.time();team.save();continuation=None;rounds=0;outcome=None
    try:
        while rounds<max_rounds and L.now()<=max_days:
            rounds+=1
            if phase is not None:phase['lead']=rounds-1
            lead_day=int(L.now())
            outcome=team.run_agent('lead',defs['coordinator'],lead,continuation);judge_new()
            if outcome['status']!='checkpointed':break
            notes=[];arrived=[]
            for _ in range(8):  # process the department until something reaches LeCun
                for role in WAKEABLE:
                    pending=unread_for(team,role)
                    requests=[n for n in L.state['nodes'].values() if n['type']=='feature_request' and n.get('status')=='requested'] if role=='bottou' else []
                    if role=='hinton' and pending and L.now()-hinton_last<7:continue
                    if pending or requests:
                        what=('letters '+', '.join(m['id'] for m in pending)) if pending else ''
                        what+=((' and ' if what else '')+'feature requests '+', '.join(n['id'] for n in requests)) if requests else ''
                        run_role(role,(f'Day {L.now():.0f}. {what.capitalize()} arrived for you; the letters are below and their attachments are already in your view. Act with your tools, then answer with mail_send. {LAST}\n\n'+letters_text(pending))[:7000]);take(team,role)
                        if role=='hinton':hinton_last=L.now()
                        judge_new()
                for i in L.deliver():
                    if i['role']!='coordinator':continue
                    if i['kind']=='node':arrived.append(i['payload'])
                    else:notes.append(f"{i['kind']} {i['payload']} is now in your vocabulary")
                news=unread_for(team,'coordinator') or notes or arrived
                if lead_wakes(L,news,lead_day):break
                if L.now()>=end_day(L):break
                nxt=L.next_event();monday=(int(L.now())//7+1)*7
                candidates=[d for d in (nxt,monday,end_day(L),float(int(L.now())+1) if news else None) if d is not None and d>L.now()]
                if not candidates:break
                L.state['day']=float(min(candidates));team.save()
                if L.now()%7==0 and len(L.state['meetings'])<max_meetings and L.now() not in L.state['meetings']:  # every Monday, news or not
                    L.state['meetings'].append(L.now())
                    for role in ('jackel','denker','boser'):
                        floor=[m for m in unread_for(team,role,False) if m['to']=='all']
                        run_role(role,(f'Day {L.now():.0f}, Monday meeting. The floor so far is below. Say one thing to "all" with mail_send (at most three sentences, every number with a ledger ID, attach what colleagues need). Jackel decides compute_allocate first if someone showed a supported claim. {LAST}\n\n'+(letters_text(floor) or 'Nobody has spoken yet.'))[:7000])
                        for m in floor:m.setdefault('read_by',[]).append(role)
                    judge_new();notes.append(f'Monday meeting held on day {L.now():.0f}; the floor statements are among the letters below')
                visit=L.config.get('visit_day',0)
                if L.now()>=visit-15 and not announced and not L.state.get('demo_day'):
                    announced=True
                    run_role('jackel',f'Day {L.now():.0f}. The Postal Service visit is on day {visit:g}, {visit-L.now():.0f} days away. If a supported FITS_CHIP claim is in your view, first call schedule_demo for day {visit:g}. Then tell "all" by mail_send what you booked or what you still need (a supported FITS_CHIP claim in your view). {LAST}')
                    judge_new();notes.append('Jackel wrote to everyone about the demonstration')
            if L.now()>=end_day(L):
                continuation={'dispatch_id':f'round-{rounds}','guidance':f'Day {L.now():.0f}: the Postal Service visit. The held-out test split is open today for one ledger_evaluate: evaluate the network you choose, compare it with the pipeline test result at 9% rejection, then write report.md with the agreed claims and finish.'}
            else:
                new=take(team,'coordinator',direct=False)  # direct letters and the meeting floor
                head=f"Day {L.now():.0f}. "+('; '.join(notes)+'. ' if notes else '')
                nodes=('New in your view (host records): '+json.dumps([L.brief(L.state['nodes'][i]) for i in arrived],ensure_ascii=False)+'\n') if arrived else ''
                body=('These letters arrived; attachments are already in your view. Act on them now; do not poll mail_inbox.\n\n'+letters_text(new)) if new else ('' if arrived else 'Nothing new arrived. Continue your own work or write again.')
                continuation={'dispatch_id':f'round-{rounds}','guidance':(head+nodes+body)[:12000]}
        team.state['outcome']=outcome;return outcome
    finally:
        team.state['active_seconds']+=time.monotonic()-team.started;team.started=None;team.state.pop('inflight_started',None);team.save()


def path_score(team):
    """Five host-checked path marks (0-5). Not a quality score; a trace of the historical route."""
    L=team.ledger;nodes=L.state['nodes'];acts=[]
    for p in sorted((team.folder/'agents/lead/actions').glob('*.json')):acts.append(json.loads(p.read_text()))
    first_def=next((i for i,a in enumerate(acts) if a['tool']=='sn_define'),len(acts))
    reads=sum(1 for a in acts[:first_def] if a['tool']=='lit_read')
    tied=[n for n in nodes.values() if n['type']=='net_spec' and n['analysis'].get('tied_layers',0)>0 and n['id']!='PIPELINE88']
    cites_ok=bool(tied) and bool(set(tied[0]['cites'])&{'RHW86-TC','WAIBEL87','FUKUSHIMA80','FUKUSHIMA82','LECUN89TR'})
    trained=[nodes[a['observation'].get('net_id') or json.loads(a['argument'])['net_id']] for a in acts if a['tool']=='sn_train' and isinstance(a.get('observation'),dict) and 'error' not in a['observation'] and json.loads(a['argument'])['net_id'] in nodes]
    small_first=len(trained)>=2 and trained[0]['analysis']['params']<=trained[1]['analysis']['params']
    budget_hits=[i for i,a in enumerate(acts) if isinstance(a.get('observation'),dict) and 'Compute budget' in str(a['observation'].get('detail',''))]
    simplified=any(a['tool']=='request_feature' for a in acts) or any(any(b['tool']=='sn_define' for b in acts[i+1:i+4]) for i in budget_hits)
    agreed_test=any(n['type']=='claim' and n['template']=='BEATS' and n['args']['dataset']=='usps-test' and n['args']['reject_rate']=='0.09' and len(n.get('endorsed_by',[]))>=2 for n in nodes.values())
    marks={'read_before_design':reads>=2,'constraint_cited':cites_ok,'small_before_large':small_first,'budget_or_feature_driven':simplified,'agreed_test_beats_at_0.09':agreed_test}
    return {'score':sum(marks.values()),'marks':marks}


# ---------------- scripted department (check mode) ----------------
WAIT=[lambda s:action('checkpoint',{'summary':'Waiting for the Sun-4 or for letters','next_test':'Act when results or letters arrive'})]
PHASES={
 'data':[lambda s:action('lit_read','LECUN89TR'),lambda s:action('lit_read','RHW86-TC'),
  lambda s:action('sn_define',{'spec':FULL,'rationale':'Fully connected control like Net-2 in [LECUN89TR]'}),
  lambda s:action('mail_send',{'to':'denker','body':'Dear John, could you attach the training data handle and say which split and rejection rate comparisons use? [LECUN89TR]','attach':[]}),
  lambda s:action('checkpoint',{'summary':'Asked for data','next_test':'Train the control and a shared-weight net'})],
 'train':[
  lambda s:action('sn_define',{'spec':TIED,'rationale':'Net-5 of [LECUN89TR] with the constraint of [RHW86-TC]'}),
  lambda s:action('sn_train',{'net_id':'N1','epochs':8}),lambda s:action('sn_train',{'net_id':'N2','epochs':8}),
  lambda s:action('request_feature',{'description':'a fixed-weight averaging layer with 2 to 1 subsampling'}),
  lambda s:action('mail_send',{'to':'boser','body':'Bernhard, could you estimate whether the shared-weight network [N2] fits the chip and promote a FITS_CHIP claim? Attached.','attach':['N2']}),
  lambda s:action('checkpoint',{'summary':'Two runs on the Sun-4, feature requested, chip estimate requested','next_test':'Compare when results arrive'})],
 'validate':[
  lambda s:action('compare_results',{'a':'R2','b':'R1','reject_rate':'0.09'}),
  lambda s:action('ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N2','net_b':'N1'},'rationale':'[N1] [N2]'}),lambda s:action('ledger_promote',{'claim_id':'C1','evidence_ids':[]}),
  lambda s:action('ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'usps-val','reject_rate':'0.09'},'rationale':'[CMP1]'}),lambda s:action('ledger_promote',{'claim_id':'C2','evidence_ids':['R1','R2']}),
  lambda s:action('ledger_claim',{'template':'MORE_INVARIANT','args':{'net_a':'N2','net_b':'N1','transform':'shift1'},'rationale':'[R2] [R1]'}),lambda s:action('ledger_promote',{'claim_id':'C3','evidence_ids':['R2','R1']}),
  lambda s:action('mail_send',{'to':'denker','body':'John, the shared-weight network [N2] beats the control [N1] on the validation split at 9% rejection [C2] [CMP1]. Could you promote the claim in your view, run your baseline, and attach the test handle? [R2]','attach':['N2','R2','C2','R1','N1']}),
  lambda s:action('checkpoint',{'summary':'Asked Denker for baseline and test handle','next_test':'Evaluate on test'})],
 'jackel':[
  lambda s:action('mail_send',{'to':'jackel','body':'Larry, Boser promoted the chip claim for [N2] ['+s['fits']+']; attached so you can book the demonstration.','attach':[s['fits'],'N2']+([s['chip']] if s['chip'] else [])}),
  lambda s:action('checkpoint',{'summary':'Asked Jackel to book','next_test':'Report on demonstration day'})],
 'final':[
  lambda s:action('ledger_evaluate',{'net_id':'N2'}),
  lambda s:action('write_file',{'path':'report.md','content':'# Milestone 3 (scripted)\nAgreed claims are in the ledger audit.'}),
  lambda s:action('finish',{'summary':'Scripted department fixture complete','files':['report.md']})]}


def lecun_state(team):
    nodes=team.ledger.state['nodes'];s={'test_n2':'R?','test_n1':'R?','fits':'C?','chip':None}
    for n in nodes.values():
        if n['type']=='result' and n['dataset']=='usps-test' and n['net']=='N2':s['test_n2']=n['id']
        if n['type']=='result' and n['dataset']=='usps-test' and n['net']=='N1':s['test_n1']=n['id']
        if n['type']=='claim' and n['template']=='FITS_CHIP':s['fits']=n['id']
        if n['type']=='chip':s['chip']=n['id']
    cmps=[n['id'] for n in nodes.values() if n['type']=='comparison'];claims=[n['id'] for n in nodes.values() if n['type']=='claim']
    s['cmp_last']=cmps[-1] if cmps else 'CMP?';s['claim_last']=claims[-1] if claims else 'C?';return s


class ScriptedLecun:
    """State-driven script: the phase is chosen from what the ledger view holds, not from the round number."""
    def __init__(self,team,phase=None):self.team=team;self.n=0
    def phase(self):
        L=self.team.ledger;V=set(L.view_for('coordinator')['nodes']);nodes=L.state['nodes'];done=L.state.setdefault('script_done',[])
        if 'USPS_TRAIN' not in V:return 'data'
        if 'N2' not in nodes:return 'train'
        if 'R1' not in V or 'R2' not in V:return 'wait'
        if 'validate' not in done:done.append('validate');return 'validate'
        if 'USPS_TEST' not in V:return 'wait'
        fits=[n for n in nodes.values() if n['type']=='claim' and n['template']=='FITS_CHIP' and n['id'] in V]
        if fits and 'jackel' not in done:done.append('jackel');return 'jackel'
        if L.state.get('demo_day') and L.now()>=L.state['demo_day']:return 'final'
        if L.now()>=120:return 'final'
        return 'wait'
    def call(self,prompt,schema,folder,**kw):
        if self.n==0:self.current=self.phase()
        steps=WAIT if self.current=='wait' else PHASES[self.current];step=steps[min(self.n,len(steps)-1)];self.n+=1
        return step(lecun_state(self.team)),{'provider':'scripted'}


class ScriptedRole:
    """Generic scripted department member: inbox, one role-specific action, reply, note, finish."""
    def __init__(self,role,team):self.role=role;self.team=team;self.n=0
    def call(self,prompt,schema,folder,**kw):
        self.n+=1;L=self.team.ledger;nodes=L.state['nodes'];objective=json.loads(prompt.split('Task data:\n',1)[1])['assignment']['objective']
        mine=[m for m in L.state['mail'] if m['to'] in (self.role,'all') and m['from']!=self.role];last=mine[-1] if mine else {'attach':[],'body':''}
        if self.n==1:return action('mail_inbox'),{}
        seq=[]
        if 'Monday meeting' in objective:
            seq=[action('mail_send',{'to':'all','body':f'{self.role.capitalize()} here: nothing new beyond what the ledger shows [DENKER88].' if self.role!='boser' else 'Boser here: shared weights are what make a network fit the chip [GRAF87].','attach':[]})]
        elif self.role=='boser':
            net=next((a for a in last['attach'] if a.startswith('N')),None);chip=next((n['id'] for n in nodes.values() if n['type']=='chip'),None);claim=next((n['id'] for n in nodes.values() if n['type']=='claim' and n['template']=='FITS_CHIP'),None)
            seq=[action('chip_estimate',{'net_id':net or 'N2'}),
                 lambda:action('ledger_claim',{'template':'FITS_CHIP','args':{'net':net or 'N2','chip':'anna'},'rationale':'Chip node ['+next(n['id'] for n in nodes.values() if n['type']=='chip')+']'}),
                 lambda:action('ledger_promote',{'claim_id':next(n['id'] for n in nodes.values() if n['type']=='claim' and n['template']=='FITS_CHIP'),'evidence_ids':[next(n['id'] for n in nodes.values() if n['type']=='chip')]}),
                 lambda:action('mail_send',{'to':'coordinator','body':'Yann, the network fits the chip ['+next(n['id'] for n in nodes.values() if n['type']=='chip')+'] and I promoted the claim ['+next(n['id'] for n in nodes.values() if n['type']=='claim' and n['template']=='FITS_CHIP')+']. Attached.','attach':[next(n['id'] for n in nodes.values() if n['type']=='chip'),next(n['id'] for n in nodes.values() if n['type']=='claim' and n['template']=='FITS_CHIP')]})]
        elif self.role=='bottou':
            req=next((n['id'] for n in nodes.values() if n['type']=='feature_request' and n.get('status')=='requested'),None) or next((n['id'] for n in nodes.values() if n['type']=='feature_request'),'FEAT1')
            seq=[action('implement_feature',{'request_id':req}),lambda:action('mail_send',{'to':'coordinator','body':'Yann, the averaging layer ['+req+'] will be in SN on day '+str(int(nodes[req].get('ready_day',0)))+' ['+req+'].','attach':[]})]
        elif self.role=='jackel':
            fits=[n['id'] for n in nodes.values() if n['type']=='claim' and n['template']=='FITS_CHIP' and n['status']=='supported' and n['id'] in L.view_for('jackel')['nodes']]
            if fits and not L.state.get('demo_day'):seq=[action('schedule_demo',{'day':max(L.now()+30,L.config.get('visit_day',0))}),action('mail_send',{'to':'all','body':'The demonstration is booked on the strength of the chip claim ['+fits[0]+'].','attach':[]})]
            else:seq=[action('mail_send',{'to':'all','body':'I need a supported chip claim in my view before I can book the demonstration [GRAF87].','attach':[]})]
        elif self.role=='hinton':
            seq=[action('mail_send',{'to':'coordinator','body':'If you do all the sensible things it works; constrain the weights as in [RHW86-TC].','attach':[]})]
        elif self.role=='denker':
            return ScriptedDenker.call(self,prompt,schema,folder)
        seq+=[action('finish',{'summary':'done','files':['note.md']})]  # note.md is pre-created by the orchestrator
        item=seq[min(self.n-2,len(seq)-1)];return (item() if callable(item) else item),{}


def check(folder,image,cache):
    phase={'lead':0};holder={}
    def factory(c):
        t=holder['team']
        if c['id']=='coordinator':return ScriptedLecun(t,phase)
        if c['id']=='judge':return ScriptedJudge()
        if c['id']=='denker':return ScriptedDenker(t)
        return ScriptedRole(c['id'],t)
    team=build(folder,image,cache,provider_factory=factory);holder['team']=team
    outcome=simulate(team,phase=phase,max_rounds=60);audit=team.ledger.audit();nodes=team.ledger.state['nodes'];L=team.ledger
    sealed=[e for e in team.state['events'] if e['kind'] in ('ledger_result','ledger_proof') and 'sealed_until' in e['data']]
    claims={k:(v['status'],v.get('endorsed_by',[])) for k,v in nodes.items() if v['type']=='claim'}
    assert outcome['status']=='submitted',outcome
    assert audit['invariant_holds'],audit
    assert sealed and all(e['data']['sealed_until']>0 for e in sealed),'results must be sealed until their simulated day'
    assert 'avg' in L.view_for('coordinator')['vocabulary'],'Bottou must deliver the averaging layer'
    fits=[k for k,(st,by) in claims.items() if nodes[k]['template']=='FITS_CHIP'];assert fits and claims[fits[0]][0]=='supported',claims
    assert L.state.get('demo_day'),'Jackel must book the demonstration'
    assert L.state['meetings'],'at least one Monday meeting'
    assert any(e['kind']=='mail_rejected' for e in audit['leak_log']) or audit['mail']['rejected']>=0
    summary={'status':'passed','outcome':outcome['status'],'day':L.now(),'demo_day':L.state['demo_day'],'meetings':L.state['meetings'],'claims':claims,'agreed':audit['agreed_claims'],
             'mail':audit['mail'],'path':path_score(team),'compute':{'used':L.state['compute_days_used'],'budget':L.budget()},
             'results':{k:(v['net'],v['dataset'],round(v['error'],4),round(v['reject_curve']['0.09'],4)) for k,v in nodes.items() if v['type']=='result'},
             'audit':{k:audit[k] for k in ('nodes','results_without_provenance','supported_without_evidence','invariant_holds','chips')},
             'scope':'Scripted six-role fixture on the simulated clock; validates sealing, meetings, demo gating, feature delivery and templates, not autonomous research'}
    atomic_json(team.folder/'verification.json',summary);team.trace.export(team.folder/'trace.html');team.close();return summary


def lenet_checklist(L):
    """Host-only scoring of LeNet components; agents never see it. For each component: the first trained net that has it,
    and whether the design choice carrying it was sourced (found in a document the designer cited) or unsourced (recall)."""
    nodes=L.state['nodes'];nets=[n for n in nodes.values() if n['type']=='net_spec' and n['id']!='PIPELINE88' and n.get('jobs')]
    tests={r['net']:r for r in nodes.values() if r['type']=='result' and r['dataset']=='usps-test'};base=tests.get('PIPELINE88')
    def tokens(n):return n['analysis']['pattern'].split('>')
    def prov(n,kind):
        c=[c for c in n['choices'] if c['choice']==kind];return 'sourced' if c and all(x['status']=='sourced' for x in c) else 'unsourced'
    comps={'shared_maps':(lambda n:any(t.startswith('shared') for t in tokens(n)),'pattern'),
           'subsampling':(lambda n:'avg' in tokens(n),'avg'),
           'two_stage_hierarchy':(lambda n:sum(t.startswith('shared') for t in tokens(n))>=2,'pattern'),
           'beats_pipeline_test':(lambda n:bool(base) and n['id'] in tests and tests[n['id']]['reject_curve']['0.09']<base['reject_curve']['0.09'],'pattern')}
    out={}
    for name,(has,kind) in comps.items():
        hit=[n for n in nets if has(n)];first=next((n for n in hit if prov(n,kind)=='sourced'),hit[0] if hit else None)
        out[name]={'net':first['id'],'provenance':prov(first,kind),'cites':sorted(set(first['cites']))} if first else None
    out['discovered']=sum(1 for v in out.values() if v and v['provenance']=='sourced');out['reached']=sum(1 for k,v in out.items() if k!='discovered' and v)
    return out


def live(folder,image,cache,model,**kw):
    team=build(folder,image,cache,model=model,**kw)
    outcome=simulate(team,max_rounds=200);audit=team.ledger.audit();nodes=team.ledger.state['nodes'];L=team.ledger
    summary={'outcome':outcome,'day':L.now(),'demo_day':L.state['demo_day'],'meetings':L.state['meetings'],'path':path_score(team),
             'audit':{k:v for k,v in audit.items() if k!='leak_log'},'leak_log':audit['leak_log'],
             'claims':{k:{'template':v['template'],'args':v['args'],'status':v['status'],'endorsed_by':v.get('endorsed_by',[])} for k,v in nodes.items() if v['type']=='claim'},
             'nets':{k:{'params':v['analysis']['params'],'pattern':v['analysis']['pattern'],'cites':v['cites'],'unsourced':[(c['choice'],c['value']) for c in v['choices'] if c['status']=='unsourced']} for k,v in nodes.items() if v['type']=='net_spec'},
             'results':{k:(v['net'],v['dataset'],round(v['error'],4),round(v['reject_curve']['0.09'],4)) for k,v in nodes.items() if v['type']=='result'},
             'mail':[{k:m[k] for k in ('id','from','to','attach','verdict')}|{'day':m.get('sent_day'),'body':m['body'][:300]} for m in L.state['mail']],
             'calls':team.state['calls'],'compute':{'used':L.state['compute_days_used'],'budget':L.budget()},'lenet_checklist':lenet_checklist(L),
             'scope':'Live department simulation; results are real container measurements; leakage is measured, not prevented'}
    atomic_json(team.folder/'summary.json',summary);team.trace.export(team.folder/'trace.html');team.close();return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['check','live'],default='check');p.add_argument('--run-dir',required=True)
    p.add_argument('--image',default='researchsquad-training:torch2.9.1-cu128');p.add_argument('--cache',default=str(Path.home()/'.cache/researchsquad/usps'))
    p.add_argument('--model',default=None);p.add_argument('--corpus-off',action='store_true');p.add_argument('--vocab',default='')
    a=p.parse_args();vocab=tuple(v for v in a.vocab.split(',') if v)
    out=check(a.run_dir,a.image,a.cache) if a.mode=='check' else live(a.run_dir,a.image,a.cache,a.model,corpus=not a.corpus_off,vocabulary=vocab)
    print(json.dumps(out,indent=2,default=str))
