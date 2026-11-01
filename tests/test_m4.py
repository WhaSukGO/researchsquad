"""M4: ablation conditions build valid tasks, idempotent tools, cross-run report."""
import json
import pytest
from goalagent.lenet_m3 import task
from goalagent.lenet_m4 import CONDITIONS, measure, report
from goalagent.lenet_m1 import TIED
from test_m3 import make, worker, call, IMAGE


@pytest.mark.parametrize('cond',sorted(CONDITIONS))
def test_every_condition_builds_a_ledger(tmp_path,cond):
    team=make(tmp_path/cond,**CONDITIONS[cond]);L=team.ledger;lecun=L.view_for('coordinator')
    if cond=='C0':assert lecun['nodes']==[]
    if cond=='C1':assert 'RHW86-TC' in lecun['nodes'] and '98.4%' in L.docs['LECUN89TR']
    if cond=='A1':assert 'RHW86-TC' not in lecun['nodes'] and 'RHW86-TC' in L.view_for('hinton')['nodes']
    if cond=='A2':assert all('DENKER88' not in L.view_for(r)['nodes'] for r in ('coordinator','denker','jackel'))
    if cond=='A3':assert L.budget()==200.0 and call(team,worker(team,'jackel'),'compute_allocate',{'days':30})['budget_days']==230.0
    if cond=='A4':assert 'avg' in lecun['vocabulary']
    if cond=='A5':assert 'FUKUSHIMA82' not in L.view_for('hinton')['nodes']
    if cond=='A6':
        assert '98.4%' not in L.docs['LECUN89TR'] and 'fewest free parameters generalized best' in L.docs['LECUN89TR'] and L.patterns['LECUN89TR']==['output','full>output']
        assert L.state['nodes']['LECUN89TR']['sha256']==CONDITIONS['A6']['overrides']['LECUN89TR']['sha256']


def test_demo_booking_and_chip_estimate_are_idempotent(tmp_path):
    team=make(tmp_path);L=team.ledger;lecun=worker(team,'coordinator');boser=worker(team,'boser');jackel=worker(team,'jackel')
    call(team,lecun,'sn_define',{'spec':TIED,'rationale':'[LECUN89TR]'});call(team,lecun,'mail_send',{'to':'boser','body':'Please estimate [N1].','attach':['N1']})
    k=call(team,boser,'chip_estimate',{'net_id':'N1'});again=call(team,boser,'chip_estimate',{'net_id':'N1'})
    assert again['id']==k['id'] and 'Already estimated' in again['note'] and sum(1 for n in L.state['nodes'].values() if n['type']=='chip')==1
    c=call(team,boser,'ledger_claim',{'template':'FITS_CHIP','args':{'net':'N1','chip':'anna'},'rationale':'['+k['id']+']'})
    call(team,boser,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':[k['id']]});call(team,boser,'mail_send',{'to':'jackel','body':'Fits ['+c['claim_id']+'].','attach':[c['claim_id'],k['id']]})
    assert call(team,jackel,'schedule_demo',{'day':45})['demo_day']==45
    again=call(team,jackel,'schedule_demo',{'day':60});assert again['demo_day']==45 and 'Already booked' in again['note'] and L.state['demo_day']==45


def test_report_aggregates_runs(tmp_path):
    def fake(name,cond,unsourced,path,agreed):
        d=tmp_path/name;d.mkdir()
        s={'condition':cond,'audit':{'invariant_holds':True,'unsourced_choices':unsourced,'choices_total':10,'agreed_claims':['C%d'%i for i in range(agreed)],'claims_by_status':{'refuted':1},
           'feature_requests':[{'granted':'avg'}],'mail':{'sent':20,'rejected':2}},'nets':{'N1':{'pattern':'shared1>avg>output','unsourced':[['pattern','shared1>avg>output']]}},
           'path':{'score':path,'marks':{'read_before_design':True,'constraint_cited':True,'small_before_large':False,'budget_or_feature_driven':True,'agreed_test_beats_at_0.09':path==5}},
           'meetings':[7.0,14.0],'demo_day':45.0,'day':22.0,'calls':300}
        (d/'summary.json').write_text(json.dumps(s))
        (d/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in [{'kind':'ledger_mail','data':{'day':3.0}},{'kind':'ledger_endorse','data':{}},{'kind':'ledger_mail','data':{'day':9.0}}]))
    fake('m4-C1-1','C1',2,4,8);fake('m4-C1-2','C1',4,5,10);fake('m4-C0-1','C0',10,1,0)
    m=measure(tmp_path/'m4-C1-1');assert m['first_agreement_day']==3.0 and m['avg_used'] and m['unsourced_patterns']==['shared1>avg>output']
    text=report(tmp_path);assert '| C0 | 1 | 1/1 | 1.00 |' in text and '| C1 | 2 | 2/2 | 0.30 |' in text and (tmp_path/'report.md').exists()
