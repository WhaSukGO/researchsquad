"""Ledger invariant tests: no model, no Docker. Results and proofs cannot be authored; promotion is deterministic."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from goalagent.team import Team, ROOT
from goalagent.ledger import TOOLS, LedgerRuntime
from goalagent.lenet_m1 import task, FULL, TIED
from test_team import FakeSandbox, action

IMAGE='sha256:'+'a'*64


def make(tmp_path,**kw):
    t=task(IMAGE,**kw)
    return Team(tmp_path,t,agents_dir=ROOT/'agents/lenet',provider_factory=lambda c:None,sandbox_factory=FakeSandbox)


def worker(team):
    folder=team.folder/'agents/lead';(folder/'workspace').mkdir(parents=True,exist_ok=True)
    return SimpleNamespace(folder=folder,workspace=folder/'workspace',config=team.definitions['coordinator'],state={'steps':1},assignment={'depth':0})


def call(team,agent,tool,data=''):return team.ledger.dispatch(agent,action(tool,data),10)


def fake_result(team,agent,rid,net,dataset,error):
    curve={'0':error,'0.05':error*0.8,'0.09':error*0.7,'0.12':error*0.6}
    node={'id':rid,'type':'result','net':net,'dataset':dataset,'error':error,'reject_curve':curve,'source':{'evidence_id':'missing'},'owner':'coordinator'}
    team.ledger.add(agent,node);return node


def test_no_tool_lets_a_model_author_a_result_or_proof():
    assert not any(name for name in TOOLS if 'result' in name and name!='compare_results')
    names=set(TOOLS);assert {'ledger_claim','ledger_promote','sn_define','sn_train','ledger_evaluate','compare_results'}<=names


def test_claims_are_born_conjectures_and_free_text_is_rejected(tmp_path):
    team=make(tmp_path);a=worker(team)
    n1=call(team,a,'sn_define',{'spec':FULL,'rationale':'control [LECUN89TR]'});n2=call(team,a,'sn_define',{'spec':TIED,'rationale':'[RHW86-TC] constraint'})
    assert (n1['net_id'],n2['net_id'])==('N1','N2') and n2['params']==1060 and not n2['guess']
    c=call(team,a,'ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N2','net_b':'N1'},'rationale':'[N1] [N2]'})
    assert c['status']=='conjecture'
    with pytest.raises(ValueError,match='Free-text'):call(team,a,'ledger_claim',{'template':'IS_BETTER','args':{'net':'N2'},'rationale':'x'})
    with pytest.raises(ValueError,match='exactly'):call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N2'},'rationale':'x'})
    assert call(team,a,'ledger_promote',{'claim_id':'C1','evidence_ids':[]})['status']=='supported'
    view=call(team,a,'ledger_view');assert view['supported'][0]['id']=='C1' and view['conjectures']==[]


def test_beats_needs_results_on_the_same_dataset_and_decides_deterministically(tmp_path):
    team=make(tmp_path);a=worker(team)
    call(team,a,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'});call(team,a,'sn_define',{'spec':TIED,'rationale':'[RHW86-TC]'})
    fake_result(team,a,'R1','N1','usps-val',0.10);fake_result(team,a,'R2','N2','usps-test',0.05)
    c=call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'usps-val','reject_rate':'0.09'},'rationale':'[R1] [R2]'})
    with pytest.raises(ValueError,match='other datasets do not count'):call(team,a,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['R1','R2']})
    assert team.ledger.state['nodes'][c['claim_id']]['status']=='conjecture'
    with pytest.raises(ValueError,match='different datasets'):call(team,a,'compare_results',{'a':'R1','b':'R2','reject_rate':'0.09'})
    fake_result(team,a,'R3','N2','usps-val',0.04)
    cmp=call(team,a,'compare_results',{'a':'R3','b':'R1','reject_rate':'0.09'});assert cmp['winner']=='R3' and cmp['id']=='CMP1'
    out=call(team,a,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['R1','R3']})
    assert out['status']=='supported' and out['evidence']==['R3','R1'] and out['unlocked_macros']==['shared_map']
    worse=call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N1','net_b':'N2','dataset':'usps-val','reject_rate':'0'},'rationale':'[CMP1]'})
    assert call(team,a,'ledger_promote',{'claim_id':worse['claim_id'],'evidence_ids':['R1','R3']})['status']=='refuted'
    assert call(team,a,'ledger_promote',{'claim_id':worse['claim_id'],'evidence_ids':[]})['note']=='Already decided'


def test_macro_unlocks_only_after_supported_tied_claim(tmp_path):
    team=make(tmp_path);a=worker(team)
    macro={'layers':[{'op':'input','h':16,'w':16},{'op':'shared_map','k':3,'stride':2,'n':2},{'op':'output','n':10}]}
    with pytest.raises(ValueError,match='not in your vocabulary'):call(team,a,'sn_define',{'spec':macro,'rationale':'[RHW86-TC]'})
    team.ledger.view(a)['macros'].append('shared_map')
    assert call(team,a,'sn_define',{'spec':macro,'rationale':'[RHW86-TC]'})['params']==146+1290


def test_guess_tagging_records_unsupported_choices(tmp_path):
    team=make(tmp_path);a=worker(team)
    g=call(team,a,'sn_define',{'spec':TIED,'rationale':'Just seems right'});assert g['guess']
    k=call(team,a,'sn_define',{'spec':TIED,'rationale':'From [RHW86-TC] and [FUKUSHIMA80]'});assert not k['guess']
    u=call(team,a,'sn_define',{'spec':TIED,'rationale':'From [LECUN98]'});assert u['guess']
    audit=team.ledger.audit();assert audit['guess_nets']==['N1','N3'] and len(audit['leak_log'])==2 and audit['leak_log'][1]['unknown_cites']==['LECUN98']
    with pytest.raises(ValueError):call(team,a,'sn_define',{'spec':TIED,'rationale':''})


def test_view_limits_reading_and_claims(tmp_path):
    team=make(tmp_path);a=worker(team)
    assert 'same amount' in call(team,a,'lit_read','RHW86-TC')['text'].lower()
    assert call(team,a,'lit_search','weight changes same amount')['results'][0]['id']=='RHW86-TC'
    team.ledger.view(a)['nodes'].remove('FUKUSHIMA80')
    with pytest.raises(ValueError,match='Not in your ledger view'):call(team,a,'lit_read','FUKUSHIMA80')
    with pytest.raises(ValueError,match='Not in your ledger view'):call(team,a,'ledger_claim',{'template':'GRAD_EQUALS','args':{'net':'N9'},'rationale':'x'})


def test_grad_equals_needs_a_proof_node(tmp_path):
    team=make(tmp_path);a=worker(team)
    call(team,a,'sn_define',{'spec':TIED,'rationale':'[RHW86-TC]'})
    c=call(team,a,'ledger_claim',{'template':'GRAD_EQUALS','args':{'net':'N1'},'rationale':'[N1]'})
    with pytest.raises(ValueError,match='GRAD_CHECK proof'):call(team,a,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['N1']})
    team.ledger.add(a,{'id':'P1','type':'proof','kind':'GRAD_CHECK','net':'N1','passed':False,'detail':{'relative_error':1.0},'source':{}})
    assert call(team,a,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['P1']})['status']=='refuted'


def test_audit_flags_results_without_provenance_and_budget_blocks_training(tmp_path):
    team=make(tmp_path,compute_days=0.001);a=worker(team)
    call(team,a,'sn_define',{'spec':FULL,'rationale':'[LECUN89TR]'})
    with pytest.raises(ValueError,match='Compute budget exceeded'):call(team,a,'sn_train',{'net_id':'N1','epochs':8})
    assert team.ledger.state['compute_days_used']==0 and not team.training.state['jobs']
    assert team.ledger.audit()['invariant_holds']
    fake_result(team,a,'R1','N1','usps-val',0.1)
    audit=team.ledger.audit();assert audit['results_without_provenance']==['R1'] and not audit['invariant_holds']


def test_corpus_hash_is_enforced(tmp_path):
    register=json.loads((ROOT/'research/lit-1988/register.json').read_text())
    assert set(register)>={'RHW86-TC','DENKER88','LECUN89TR'} and all(len(m['sha256'])==64 for m in register.values())
    team=make(tmp_path);assert len(team.ledger.docs)==len(register)
