"""M2 invariants: letters are the only channel, the rule judge refuses bad letters, promotion needs the evidence in your own view."""
import json
from types import SimpleNamespace
import pytest
from goalagent.team import Team, ROOT
from goalagent.lenet_sim import task
from goalagent.lenet_m1 import FULL, TIED
from goalagent import judge
from test_team import FakeSandbox, action

IMAGE='sha256:'+'b'*64


def make(tmp_path,**kw):
    return Team(tmp_path,task(IMAGE,**kw),agents_dir=ROOT/'agents/lenet',provider_factory=lambda c:None,sandbox_factory=FakeSandbox)


def worker(team,role,name):
    folder=team.folder/'agents'/name;(folder/'workspace').mkdir(parents=True,exist_ok=True)
    return SimpleNamespace(folder=folder,workspace=folder/'workspace',config=team.definitions[role],state={'steps':1},assignment={'depth':0 if role=='coordinator' else 1})


def call(team,agent,tool,data=''):return team.ledger.dispatch(agent,action(tool,data),10)


def fake_result(team,agent,rid,net,dataset,error):
    curve={'0':error,'0.05':error*0.8,'0.09':error*0.7,'0.12':error*0.6}
    return team.ledger.add(agent,{'id':rid,'type':'result','net':net,'dataset':dataset,'error':error,'reject_curve':curve,'source':{'evidence_id':'x'},'owner':agent.config['id']})


def test_rule_judge():
    assert judge.check_text('The shared-weight network [N2] reaches 4.3% error [R2].',['N2','R2'])==[]
    v=dict(judge.check_text('Our convolutional network gets 4.3% error.',['N2']))
    assert v['vocabulary']=='convolutional network' and 'uncited_number' in v
    assert ('unknown_citation','LECUN98') in judge.check_text('As [LECUN98] shows.',['N2'])
    assert ('unsupported_verification','It is verified that this works.') in judge.check_text('It is verified that this works.',[])
    assert judge.check_text('It is verified [C1].',['C1'],['C1'])==[]
    assert judge.check_text('I conjecture it generalizes [conj:X].',[])==[]


def test_handles_gate_training_and_evaluation(tmp_path):
    team=make(tmp_path);lecun=worker(team,'coordinator','lead')
    call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    with pytest.raises(ValueError,match=r'\[USPS_TRAIN\].*denker'):call(team,lecun,'sn_train',{'net_id':'N1','epochs':2})
    with pytest.raises(ValueError,match=r'\[USPS_TEST\]'):call(team,lecun,'ledger_evaluate',{'net_id':'N1'})
    assert team.ledger.state['compute_days_used']==0


def test_letters_are_the_only_channel_and_widen_views(tmp_path):
    team=make(tmp_path);lecun=worker(team,'coordinator','lead');denker=worker(team,'denker','denker-1')
    with pytest.raises(ValueError,match='Not in your ledger view'):call(team,lecun,'lit_read','DENKER87')
    with pytest.raises(ValueError,match='Not in your ledger view'):call(team,lecun,'mail_send',{'to':'denker','body':'see [USPS_TRAIN]','attach':['USPS_TRAIN']})
    out=call(team,denker,'mail_send',{'to':'coordinator','body':'Here is the training handle [USPS_TRAIN].','attach':['USPS_TRAIN']})
    assert out['mail_id']=='M1' and 'USPS_TRAIN' in team.ledger.view(lecun)['nodes']
    inbox=call(team,lecun,'mail_inbox');assert inbox['letters'][0]['attach']==['USPS_TRAIN'] and call(team,lecun,'mail_inbox')['letters']==[]
    with pytest.raises(ValueError,match='Unknown recipient'):call(team,lecun,'mail_send',{'to':'judge','body':'hi','attach':[]})
    with pytest.raises(ValueError,match='vocabulary'):call(team,lecun,'mail_send',{'to':'denker','body':'My convnet works.','attach':[]})
    with pytest.raises(ValueError,match='number without a ledger ID'):call(team,lecun,'mail_send',{'to':'denker','body':'I got 4.3% error.','attach':[]})
    audit=team.ledger.audit();assert audit['mail']['rejected']==2 and audit['mail']['sent']==1 and audit['leak_log'][-1]['kind']=='mail_rejected'


def test_consensus_needs_evidence_in_own_view(tmp_path):
    team=make(tmp_path);lecun=worker(team,'coordinator','lead');denker=worker(team,'denker','denker-1')
    call(team,lecun,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'});call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'})
    fake_result(team,lecun,'R1','N1','usps-val',0.08);fake_result(team,lecun,'R2','N2','usps-val',0.04)
    c=call(team,lecun,'ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'usps-val','reject_rate':'0.09'},'rationale':'[R1] [R2]'})
    out=call(team,lecun,'ledger_promote',{'claim_id':'C1','evidence_ids':['R1','R2']});assert out['status']=='supported' and out['endorsed_by']==['coordinator'] and not out['agreed']
    call(team,lecun,'mail_send',{'to':'denker','body':'Please confirm [C1].','attach':['C1','N1','N2']})
    with pytest.raises(ValueError,match='missing: R2, R1|missing: R1, R2'):call(team,denker,'ledger_promote',{'claim_id':'C1','evidence_ids':[]})
    call(team,lecun,'mail_send',{'to':'denker','body':'Evidence attached [R1] [R2].','attach':['R1','R2']})
    out=call(team,denker,'ledger_promote',{'claim_id':'C1','evidence_ids':[]});assert out['agreed'] and set(out['endorsed_by'])=={'coordinator','denker'}
    assert call(team,denker,'ledger_promote',{'claim_id':'C1','evidence_ids':[]})['note']=='Already decided'
    assert team.ledger.audit()['agreed_claims']==['C1']


def test_judge_verdict_is_referee_only_and_logged(tmp_path):
    team=make(tmp_path);lecun=worker(team,'coordinator','lead');denker=worker(team,'denker','denker-1');ref=worker(team,'judge','judge')
    call(team,denker,'mail_send',{'to':'coordinator','body':'Hello [USPS_TRAIN].','attach':['USPS_TRAIN']})
    with pytest.raises(ValueError,match='Only the judge'):call(team,lecun,'judge_verdict',{'mail_id':'M1','verdict':'pass','reason':'x'})
    assert call(team,ref,'judge_verdict',{'mail_id':'M1','verdict':'future_knowledge','reason':'mentions later work'})['recorded']=='future_knowledge'
    audit=team.ledger.audit();assert audit['mail']['verdicts']['future_knowledge']==1 and audit['leak_log'][-1]['kind']=='judge_future_knowledge'


def test_baseline_pipeline_creates_provenanced_results(tmp_path):
    team=make(tmp_path);denker=worker(team,'denker','denker-1');lecun=worker(team,'coordinator','lead')
    with pytest.raises(ValueError,match='adapter not installed'):call(team,denker,'pipeline_run')
    class Adapter:
        version='test-v0'
        def __call__(self):
            c=lambda e:{'0':e,'0.05':e*0.9,'0.09':e*0.8,'0.12':e*0.7}
            return {'features':80,'classifier_params':810,'val':{'error':0.06,'reject_curve':c(0.06),'samples':1000},'test':{'error':0.09,'reject_curve':c(0.09),'samples':2007}}
    team.ledger.adapters['baseline88']=Adapter()
    with pytest.raises(ValueError,match=r'\[USPS_TRAIN\]'):call(team,lecun,'pipeline_run')
    out=call(team,denker,'pipeline_run');assert [r['dataset'] for r in out['results']]==['usps-val','usps-test'] and out['baseline_net']=='PIPELINE88'
    again=call(team,denker,'pipeline_run');assert again['note']=='Baseline already measured'
    audit=team.ledger.audit();assert audit['invariant_holds'] and audit['nodes']['result']==2
    assert team.ledger.state['nodes']['PIPELINE88']['analysis']['params']==810
