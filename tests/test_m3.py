"""M3: simulated clock seals results, letters take a day, role tools are role-bound, new templates decide deterministically."""
from types import SimpleNamespace
import pytest
from goalagent.team import Team, ROOT
from goalagent.lenet_m3 import task
from goalagent.lenet_m1 import FULL, TIED
from test_team import FakeSandbox, action

IMAGE='sha256:'+'c'*64


def make(tmp_path,**kw):
    return Team(tmp_path,task(IMAGE,**kw),agents_dir=ROOT/'agents/lenet',provider_factory=lambda c:None,sandbox_factory=FakeSandbox)


def worker(team,role):
    folder=team.folder/'agents'/(role if role!='coordinator' else 'lead');(folder/'workspace').mkdir(parents=True,exist_ok=True)
    return SimpleNamespace(folder=folder,workspace=folder/'workspace',config=team.definitions[role],state={'steps':1},assignment={'depth':0 if role=='coordinator' else 1})


def call(team,agent,tool,data=''):return team.ledger.dispatch(agent,action(tool,data),10)


def test_letters_take_a_day_and_all_is_the_meeting_floor(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');denker=worker(team,'denker');boser=worker(team,'boser')
    out=call(team,denker,'mail_send',{'to':'coordinator','body':'Handle attached [USPS_TRAIN].','attach':['USPS_TRAIN']})
    assert out['arrives_day']==1.0 and call(team,lecun,'mail_inbox')['letters']==[] and 'USPS_TRAIN' in L.view(lecun)['nodes']
    L.state['day']=1.0;assert call(team,lecun,'mail_inbox')['letters'][0]['id']=='M1'
    call(team,boser,'mail_send',{'to':'all','body':'Shared weights fit the chip [GRAF87].','attach':['GRAF87']})
    assert call(team,denker,'mail_inbox')['letters'][0]['to']=='all' and call(team,lecun,'mail_inbox')['letters'][0]['id']=='M2' and 'GRAF87' in L.view(lecun)['nodes']
    assert call(team,boser,'mail_inbox')['letters']==[]  # your own floor statement is not your mail


def test_sealed_nodes_enter_the_view_only_when_their_day_comes(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    node={'id':'R9','type':'result','net':'N1','dataset':'usps-val','error':0.1,'reject_curve':{'0':0.1,'0.05':0.1,'0.09':0.1,'0.12':0.1},'source':{'evidence_id':'x'},'owner':'coordinator'}
    L.seal(lecun,node,3.0)
    assert 'R9' not in L.view(lecun)['nodes'] and call(team,lecun,'ledger_view')['sealed'][0]['ready_day']==3.0 and L.next_event()==3.0
    L.state['day']=2.0;assert L.deliver()==[] and 'R9' not in L.view(lecun)['nodes']
    L.state['day']=3.0;d=L.deliver();assert d[0]['payload']=='R9' and 'R9' in L.view(lecun)['nodes'] and L.next_event() is None


def test_feature_requests_go_through_bottou_with_delay(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');bottou=worker(team,'bottou');denker=worker(team,'denker')
    r=call(team,lecun,'request_feature',{'description':'a fixed-weight averaging and subsampling layer'})
    assert r['status'].startswith('sent') and 'FEAT1' in L.view_for('bottou')['nodes'] and 'avg' not in L.view(lecun)['vocabulary']
    with pytest.raises(ValueError,match='Only the simulator maintainer'):call(team,denker,'implement_feature',{'request_id':'FEAT1'})
    out=call(team,bottou,'implement_feature',{'request_id':'FEAT1'});assert out['granted']=='avg' and out['ready_day']==10.0
    assert 'avg' not in L.view(lecun)['vocabulary'];L.state['day']=10.0;L.deliver();assert 'avg' in L.view(lecun)['vocabulary']
    no=call(team,lecun,'request_feature',{'description':'a rotation layer'});assert call(team,bottou,'implement_feature',{'request_id':no['request_id']})['granted'] is None


def test_chip_and_fits_chip_and_demo_gating(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');boser=worker(team,'boser');jackel=worker(team,'jackel')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'})
    big={'layers':[{'op':'input','h':16,'w':16},{'op':'full','n':64},{'op':'output','n':10}]}
    call(team,lecun,'sn_define',{'spec':big,'rationale':'[LECUN89TR]'})
    with pytest.raises(ValueError,match='Only the chip designer'):call(team,lecun,'chip_estimate',{'net_id':'N1'})
    call(team,lecun,'mail_send',{'to':'boser','body':'Please estimate [N1] and [N2].','attach':['N1','N2']})
    k1=call(team,boser,'chip_estimate',{'net_id':'N1'});k2=call(team,boser,'chip_estimate',{'net_id':'N2'})
    assert k1['fits'] and k1['weights']==1060 and not k2['fits'] and k2['weights']==17098
    c=call(team,boser,'ledger_claim',{'template':'FITS_CHIP','args':{'net':'N1','chip':'anna'},'rationale':'['+k1['id']+']'})
    assert call(team,boser,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':[k1['id']]})['status']=='supported'
    c2=call(team,boser,'ledger_claim',{'template':'FITS_CHIP','args':{'net':'N2','chip':'anna'},'rationale':'['+k2['id']+']'})
    assert call(team,boser,'ledger_promote',{'claim_id':c2['claim_id'],'evidence_ids':[k2['id']]})['status']=='refuted'
    with pytest.raises(ValueError,match='No supported FITS_CHIP'):call(team,jackel,'schedule_demo',{'day':45})
    call(team,boser,'mail_send',{'to':'jackel','body':'Fits ['+c['claim_id']+'].','attach':[c['claim_id'],k1['id']]})
    with pytest.raises(ValueError,match='visit is on day 45'):call(team,jackel,'schedule_demo',{'day':30})
    assert call(team,jackel,'schedule_demo',{'day':45})['demo_day']==45 and L.state['demo_day']==45
    with pytest.raises(ValueError,match='Only the department head'):call(team,boser,'compute_allocate',{'days':5})
    assert call(team,jackel,'compute_allocate',{'days':10})['budget_days']==30.0
    assert call(team,jackel,'compute_allocate',{'days':30})['budget_days']==60.0
    with pytest.raises(ValueError,match='Department cap'):call(team,jackel,'compute_allocate',{'days':1})
    assert L.audit()['chips'][0]['fits'] and L.audit()['demo_day']==45 and call(team,jackel,'ledger_view')['visit_day']==45


CURVE={'0':0.1,'0.05':0.1,'0.09':0.1,'0.12':0.1}


def result(L,agent,rid,net,err=0.1,inv=None,dataset='usps-val'):
    L.add(agent,{'id':rid,'type':'result','net':net,'dataset':dataset,'error':err,'reject_curve':{k:err for k in CURVE},**({'invariance':inv} if inv else {}),'source':{'evidence_id':'x'},'owner':'coordinator'})


def test_more_invariant_compares_the_latest_results_of_two_nets(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    assert 'INVARIANT_TO' not in L.templates()
    with pytest.raises(ValueError,match='transform shift1'):call(team,lecun,'ledger_claim',{'template':'MORE_INVARIANT','args':{'net_a':'N1','net_b':'N2','transform':'rotate'},'rationale':'[N1]'})
    early=call(team,lecun,'ledger_claim',{'template':'MORE_INVARIANT','args':{'net_a':'N1','net_b':'N2','transform':'shift1'},'rationale':'[N1]'})
    assert early['status']=='conjecture' and 'shift1 measurement' in early['not_yet_decidable']
    result(L,lecun,'R1','N1',inv={'shift1':0.95,'shift2':0.6});result(L,lecun,'R2','N2',inv={'shift1':0.9,'shift2':0.6})
    result(L,lecun,'R3','N1',inv={'shift1':0.85,'shift2':0.6})  # a later run of N1 holds up worse: the earlier one cannot be picked
    c=call(team,lecun,'ledger_claim',{'template':'MORE_INVARIANT','args':{'net_a':'N1','net_b':'N2','transform':'shift1'},'rationale':'[R3] [R2]'})
    assert c['status']=='refuted' and c['detail']['kept_a']==0.85 and c['evidence']==['R3','R2']
    tie=call(team,lecun,'ledger_claim',{'template':'MORE_INVARIANT','args':{'net_a':'N1','net_b':'N2','transform':'shift2'},'rationale':'[R3] [R2]'})
    assert tie['status']=='refuted'
    assert call(team,lecun,'ledger_promote',{'claim_id':early['claim_id'],'evidence_ids':['R3','R2']})['status']=='refuted'


def test_beats_uses_the_latest_result_per_net_and_claims_promote_at_once(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    result(L,lecun,'R1','N1',err=0.02);result(L,lecun,'R2','N2',err=0.05);result(L,lecun,'R3','N1',err=0.08)
    c=call(team,lecun,'ledger_claim',{'template':'BEATS','args':{'net_a':'N1','net_b':'N2','dataset':'usps-val','reject_rate':'0.09'},'rationale':'[R1] [R2]'})
    assert c['status']=='refuted' and c['evidence']==['R3','R2']  # decided on R3, not the better earlier R1
    assert L.state['nodes'][c['claim_id']]['endorsed_by']==['coordinator']


def test_promote_takes_a_list_and_decides_each_claim(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');denker=worker(team,'denker')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    a=call(team,lecun,'ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N1','net_b':'N2'},'rationale':'[N1] [N2]'})['claim_id']
    b=call(team,lecun,'ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N2','net_b':'N1'},'rationale':'[N1] [N2]'})['claim_id']
    call(team,lecun,'mail_send',{'to':'denker','body':'Please promote [C1] [C2].','attach':[a,b,'N1','N2']})
    out=call(team,denker,'ledger_promote',{'claim_ids':[a,b,'C9'],'evidence_ids':[]})['claims']
    assert [o.get('status') for o in out]==['supported','refuted',None] and out[0]['agreed'] and 'Not in your ledger view' in out[2]['error']


def test_delivered_validation_results_get_host_comparisons(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    result(L,lecun,'R1','PIPELINE88',err=0.03);result(L,lecun,'R2','N2',err=0.05);result(L,lecun,'R3','N2',err=0.04)
    L.seal(lecun,{'id':'R4','type':'result','net':'N1','dataset':'usps-val','error':0.02,'reject_curve':{k:0.02 for k in CURVE},'source':{'evidence_id':'x'},'owner':'coordinator'},2.0)
    L.state['day']=2.0;out=L.deliver();cmps=[i['payload'] for i in out if i['payload'].startswith('CMP')]
    nodes=L.state['nodes'];assert [(nodes[c]['a'],nodes[c]['b'],nodes[c]['winner']) for c in cmps]==[('R4','R1','R4'),('R4','R3','R4')]
    assert all(c in L.view(lecun)['nodes'] and nodes[c]['reject_rate']=='0.09' for c in cmps)


def test_training_is_sealed_on_the_clock_without_docker(tmp_path,monkeypatch):
    team=make(tmp_path,compute_days=40);L=team.ledger;lecun=worker(team,'coordinator');denker=worker(team,'denker')
    call(team,denker,'mail_send',{'to':'coordinator','body':'[USPS_TRAIN]','attach':['USPS_TRAIN']})
    call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    import json
    blob=tmp_path/'zip.train.gz';blob.write_bytes(b'fake');team.training.register_dataset('usps-train',{'zip.train.gz':blob},{'split':'train'})
    metrics={'net_id':'N1','spec':L.state['nodes']['N1']['spec'],'parameters':3214,'val_error':0.08,'reject_curve':{'0':0.08,'0.05':0.07,'0.09':0.06,'0.12':0.05},'train_count':6291,'per_epoch':[],'grad_check':None,'invariance':{'shift1':0.8,'shift2':0.5}}
    def fake_start(agent,packet,key):
        jid='job-fake';folder=team.training.root/'jobs'/jid/'output';folder.mkdir(parents=True,exist_ok=True)
        (folder/'metrics.json').write_text(json.dumps(metrics));team.training.state['jobs'][jid]={'id':jid,'owner':'agents/lead','status':'SUCCEEDED','request':packet}
        return {'job_id':jid,'status':'SUCCEEDED','log_tail':''}
    monkeypatch.setattr(team.training,'start',fake_start)
    out=call(team,lecun,'sn_train',{'net_id':'N1','epochs':8})
    assert 'sealed' in out and out['sealed']['result']=='R1' and 'R1' not in L.view(lecun)['nodes'] and L.state['nodes']['R1']['invariance']['shift1']==0.8
    assert L.state['compute_days_used']>0 and L.next_event()==round(out['sealed']['ready_day'],2) or L.next_event()>0
    L.state['day']=out['sealed']['ready_day'];L.deliver();assert 'R1' in L.view(lecun)['nodes'] and 'P1' in L.view(lecun)['nodes']
    assert L.audit()['invariant_holds']


def test_one_letter_per_recipient_per_day(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    call(team,lecun,'mail_send',{'to':'denker','body':'First [LECUN89TR].','attach':[]})
    with pytest.raises(ValueError,match='already wrote to denker today'):call(team,lecun,'mail_send',{'to':'denker','body':'Second [LECUN89TR].','attach':[]})
    call(team,lecun,'mail_send',{'to':'boser','body':'Other colleague [LECUN89TR].','attach':[]})
    L.state['day']=1.0;assert call(team,lecun,'mail_send',{'to':'denker','body':'Next day [LECUN89TR].','attach':[]})['mail_id']=='M3'
    from goalagent import judge
    assert judge.check_text('Please attach the supported claim so that I can promote it [C1].',['C1'])==[]


def test_letters_handed_over_by_the_orchestrator_count_as_read(tmp_path):
    from goalagent.lenet_m3 import unread_for, take
    team=make(tmp_path);L=team.ledger;denker=worker(team,'denker')
    call(team,denker,'mail_send',{'to':'coordinator','body':'Handle attached [USPS_TRAIN].','attach':['USPS_TRAIN']})
    L.state['day']=1.0;assert [m['id'] for m in unread_for(team,'coordinator')]==['M1']
    assert [m['id'] for m in take(team,'coordinator')]==['M1'] and unread_for(team,'coordinator')==[] and take(team,'coordinator')==[]


def test_test_split_opens_on_the_visit_day_and_checklist_counts_only_sourced_components(tmp_path):
    from goalagent.lenet_m3 import lenet_checklist
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    L.add(lecun,dict(L.state['nodes'].get('USPS_TEST') or {'id':'USPS_TEST','type':'dataset','split':'test'}))
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});L.state['nodes']['N1']['jobs']=['job-x']
    with pytest.raises(ValueError,match='opens on the Postal Service visit day'):call(team,lecun,'ledger_evaluate',{'net_id':'N1'})
    c=lenet_checklist(L)  # TIED is Net-5: two shared stages, no averaging
    assert c['shared_maps']['net']==c['two_stage_hierarchy']['net']=='N1' and c['subsampling'] is None and c['beats_pipeline_test'] is None and c['reached']==2
    assert c['discovered']==sum(c[k]['provenance']=='sourced' for k in ('shared_maps','two_stage_hierarchy'))


def test_one_sun4_queues_jobs_back_to_back(tmp_path,monkeypatch):
    import json
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    L.add(lecun,dict(L.state['nodes'].get('USPS_TRAIN') or {'id':'USPS_TRAIN','type':'dataset','split':'train'}))
    call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    def start(agent,packet,dispatch):  # stand-in for the container: a succeeded job with metrics on disk
        jid=f"job-{len(team.training.state['jobs'])}";team.training.state['jobs'][jid]={}
        out=team.training.root/'jobs'/jid/'output';out.mkdir(parents=True);(out/'metrics.json').write_text(json.dumps({}))
        return {'job_id':jid,'status':'SUCCEEDED','log_tail':''}
    monkeypatch.setattr(L,'dataset_id',lambda:'dataset-x');monkeypatch.setattr(L.task,'packet',lambda *a:{})
    monkeypatch.setattr(team.training,'start',start);monkeypatch.setattr(L.task,'matches',lambda m,n:True)
    monkeypatch.setattr(L.task,'result',lambda m:({'error':0.05},L.state['nodes']['N1']['analysis']['params'],None,[]))
    a=call(team,lecun,'sn_train',{'net_id':'N1','epochs':5});b=call(team,lecun,'sn_train',{'net_id':'N1','epochs':6})
    assert a['sealed']['ready_day']>0 and b['sealed']['ready_day']==pytest.approx(a['sealed']['ready_day']+a['simulated_days'],abs=0.02)
    assert 'starts on day' in b['note'] and L.state['inflight']=={}  # the in-flight marker is cleared once the result exists
    again=call(team,lecun,'sn_train',{'net_id':'N1','epochs':5})  # deterministic training: the same run is not repeated
    assert again['result']==a['sealed']['result'] and again['simulated_days']==0 and len(team.training.state['jobs'])==2
    assert again['sealed']['ready_day']==a['sealed']['ready_day'] and L.state['compute_days_used']==pytest.approx(a['simulated_days']+b['simulated_days'],abs=0.01)


def test_the_floor_is_once_a_day_and_a_woken_colleague_ends_on_its_letter(tmp_path):
    team=make(tmp_path);L=team.ledger;boser=worker(team,'boser');lecun=worker(team,'coordinator')
    call(team,boser,'mail_send',{'to':'all','body':'Shared weights fit the chip [GRAF87].','attach':[]})
    with pytest.raises(ValueError,match='already wrote to all today'):call(team,boser,'mail_send',{'to':'all','body':'Again [GRAF87].','attach':[]})
    jackel=worker(team,'jackel');jackel.assignment['ends_on_letter']=True;(jackel.workspace/'note.md').write_text('note')
    out=call(team,jackel,'mail_send',{'to':'coordinator','body':'Book it when the chip fits [GRAF87].','attach':[]})
    assert jackel.state['status']=='submitted' and 'last action' in out['note'] and (jackel.folder/'submission.json').exists()
    out=call(team,lecun,'mail_send',{'to':'denker','body':'Data please [LECUN89TR].','attach':[]});assert 'status' not in lecun.state


def test_woken_colleagues_get_a_host_briefing_and_the_lead_reads_the_floor(tmp_path):
    from goalagent.lenet_m3 import briefing, take
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');denker=worker(team,'denker');boser=worker(team,'boser')
    first=briefing(team,'denker');assert 'USPS_TRAIN' in first and 'none' in first
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});c=call(team,lecun,'ledger_claim',{'template':'GRAD_EQUALS','args':{'net':'N1'},'rationale':'[N1]'})
    call(team,lecun,'mail_send',{'to':'denker','body':'See [N1].','attach':['N1',c['claim_id']]})
    call(team,denker,'mail_send',{'to':'coordinator','body':'Got [N1].','attach':[]})
    second=briefing(team,'denker');assert '"N1"' in second and c['claim_id'] in second and 'USPS_TRAIN' not in second and 'M2 to coordinator' in second
    call(team,boser,'mail_send',{'to':'all','body':'Shared weights fit the chip [GRAF87].','attach':[]})
    L.state['day']=1.0;assert [m['id'] for m in take(team,'coordinator',direct=False)]==['M2','M3'] and take(team,'coordinator',direct=False)==[]


def test_the_lead_wakes_at_most_once_a_day_after_the_days_last_event(tmp_path):
    from goalagent.lenet_m3 import lead_wakes
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    L.state['day']=2.3;L.defer('coordinator','node','R9',2.8)
    assert not lead_wakes(L,['news'],1)  # another event comes due later today
    L.state['day']=2.8;L.deliver();assert lead_wakes(L,['news'],1) and not lead_wakes(L,['news'],2) and not lead_wakes(L,[],1)


def test_idle_checkpoint_is_refused_inside_the_tool_once_a_day(tmp_path):
    from goalagent.lenet_m3 import guard_checkpoint
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');guard_checkpoint(team)
    L.view(lecun)['nodes'].append('USPS_TRAIN');tool=team.registry.tools['checkpoint']
    progress=action('checkpoint',{'summary':'waiting','next_test':'later'})
    with pytest.raises(ValueError,match='Checkpoint refused: the Sun-4 is idle'):tool.handler(lecun,progress,10)
    assert tool.handler(lecun,progress,10)['status']=='checkpointed'


def test_prompt_puts_stable_fields_first_and_keeps_the_latest_ledger_view_whole(tmp_path):
    import json
    from goalagent.agent import Agent
    prompts=[]
    class Provider:
        def call(self,prompt,schema,folder,**kw):prompts.append(prompt);return action('finish',{'summary':'x','files':['note.md']}),{}
    team=Team(tmp_path,task(IMAGE),agents_dir=ROOT/'agents/lenet',provider_factory=lambda c:Provider(),sandbox_factory=FakeSandbox)
    ws=tmp_path/'agents/jackel-1/workspace';ws.mkdir(parents=True);(ws/'note.md').write_text('note')
    team.run_agent('jackel-1',team.definitions['jackel'],{'goal':'g','objective':'o','depth':1,'inputs':[]})
    ctx=json.loads(prompts[0].split('Task data:\n',1)[1]);assert list(ctx)[:3]==['tools','assignment','workspace'] and list(ctx)[-1]=='team'
    big={'tool':'ledger_view','observation':{'nets':'x'*9000}}
    out=Agent.recent_context(SimpleNamespace(state={'history':[big,{'tool':'mail_inbox','observation':{}},dict(big)]}))
    assert out[0]['observation']['truncated'] and out[2]['observation']['nets']=='x'*9000


def test_woken_colleagues_run_concurrently_and_keep_the_ledger_consistent(tmp_path):
    import time
    from goalagent.lenet_m3 import prepare, run_batch
    class Slow:  # a model call that takes 0.5 s and answers with one letter
        def __init__(self,role):self.role=role
        def preflight(self):
            if self.role=='boser':raise RuntimeError('boser has no model')
        def call(self,prompt,schema,folder,**kw):
            time.sleep(0.5);return action('mail_send',{'to':'coordinator','body':f'{self.role} read it [DENKER88].','attach':[]}),{}
    team=Team(tmp_path,task(IMAGE),agents_dir=ROOT/'agents/lenet',provider_factory=lambda c:Slow(c['id']),sandbox_factory=FakeSandbox);L=team.ledger
    counts={r:0 for r in team.definitions}
    start=time.monotonic();run_batch(team,[prepare(team,counts,'denker','Write once.')]);single=time.monotonic()-start
    L.state['day']=1.0
    start=time.monotonic();out=run_batch(team,[prepare(team,counts,'denker','Write once.'),prepare(team,counts,'jackel','Write once.')]);both=time.monotonic()-start
    assert both<1.5*single and [o['status'] for o in out]==['submitted','submitted']
    ids=[m['id'] for m in L.state['mail']];assert sorted(ids)==['M1','M2','M3'] and {m['from'] for m in L.state['mail'][1:]}=={'denker','jackel'}
    assert sorted(e['data']['id'] for e in team.state['events'] if e['kind']=='ledger_mail')==ids and L.audit()['invariant_holds']
    L.state['day']=2.0
    with pytest.raises(RuntimeError,match='boser has no model'):run_batch(team,[prepare(team,counts,'boser','Write once.'),prepare(team,counts,'jackel','Write once.')])
    assert L.state['mail'][-1]['from']=='jackel' and len(L.state['mail'])==4  # the failing colleague does not stop the other


def test_simulation_locals_survive_a_restart_and_the_lead_resumes(tmp_path):
    import json
    from goalagent.lenet_m3 import simulate
    class Quiet:  # the lead waits, colleagues have nothing to add
        def __init__(self,config):self.role=config['id']
        def call(self,prompt,schema,folder,**kw):
            if self.role=='coordinator':return action('checkpoint',{'summary':'wait','next_test':'later'}),{}
            return action('finish',{'summary':'nothing to add','files':['note.md']}),{}
    def open_team():return Team(tmp_path,task(IMAGE),agents_dir=ROOT/'agents/lenet',provider_factory=Quiet,sandbox_factory=FakeSandbox)
    team=open_team();simulate(team,max_rounds=1);S=team.state['sim'];team.close()
    assert S['rounds']==1 and S['counts']['jackel']>=1 and S['lead_seen']>0 and S['continuation']['dispatch_id']=='round-1'
    team=open_team();assert team.state['sim']==S  # round trip through team-state.json
    simulate(team,max_rounds=2,resume=True)  # reusing a colleague's folder name would raise 'Worker assignment changed'
    lead=json.loads((tmp_path/'agents/lead/worker-state.json').read_text())
    assert team.state['sim']['rounds']==2 and team.state['sim']['resumes']==1 and lead['continuation_id']=='resume-1'
    assert team.state['sim']['counts']['jackel']>S['counts']['jackel'] and 'resumed after an interruption' in lead['guidance']
    assert any(e['kind']=='simulation_resumed' for e in team.state['events'])


def test_stale_inflight_training_is_refunded_exactly_once(tmp_path):
    team=make(tmp_path);L=team.ledger
    L.state['compute_days_used']=3.0;L.state['inflight']={'k':{'net':'N1','args':{'net_id':'N1','epochs':5},'days':2.0,'job_id':'job-x','day':1.0}}
    assert [m['net'] for m in L.recover_inflight()]==['N1'] and L.state['compute_days_used']==1.0
    assert L.recover_inflight()==[] and L.state['compute_days_used']==1.0 and L.state['inflight']=={}


def test_resume_refuses_a_changed_contract(tmp_path):
    make(tmp_path).close()
    with pytest.raises(ValueError,match='Team contract changed'):make(tmp_path,visit_day=50)
