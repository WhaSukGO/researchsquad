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


def test_invariant_to_needs_measured_invariance(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'})
    curve={'0':0.1,'0.05':0.1,'0.09':0.1,'0.12':0.1}
    L.add(lecun,{'id':'R1','type':'result','net':'N1','dataset':'usps-val','error':0.1,'reject_curve':curve,'invariance':{'shift1':0.9,'shift2':0.6},'source':{'evidence_id':'x'},'owner':'coordinator'})
    with pytest.raises(ValueError,match='transform shift1'):call(team,lecun,'ledger_claim',{'template':'INVARIANT_TO','args':{'net':'N1','transform':'rotate','tolerance':0.2},'rationale':'[R1]'})
    c=call(team,lecun,'ledger_claim',{'template':'INVARIANT_TO','args':{'net':'N1','transform':'shift1','tolerance':0.2},'rationale':'[R1]'})
    assert call(team,lecun,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['R1']})['status']=='supported'
    c2=call(team,lecun,'ledger_claim',{'template':'INVARIANT_TO','args':{'net':'N1','transform':'shift2','tolerance':0.2},'rationale':'[R1]'})
    assert call(team,lecun,'ledger_promote',{'claim_id':c2['claim_id'],'evidence_ids':['R1']})['status']=='refuted'


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
