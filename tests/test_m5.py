"""M5: the ledger on a non-LeNet task (Fashion-MNIST), the report checker, and the offline unverified-claim counter."""
import json
from types import SimpleNamespace
import pytest
from goalagent.team import Team
from goalagent import fashion_ledger as fl
from scripts.count_unverified_claims import count
from test_team import FakeSandbox, action

IMAGE='sha256:'+'d'*64


class FakeEval:
    version='fake-fashion-test-v1'
    def __call__(self,path,job):return {'accepted':True,'accuracy':0.87,'loss':0.4,'samples':10000}


def make(tmp_path):
    agents=fl.write_agents(tmp_path/'agents',managed=False)
    return Team(tmp_path/'run',fl.task(IMAGE,managed=False),agents_dir=agents,provider_factory=lambda c:None,sandbox_factory=FakeSandbox,model_evaluators={'fashion_test':FakeEval()})


def worker(team):
    folder=team.folder/'agents/lead';(folder/'workspace').mkdir(parents=True,exist_ok=True)
    return SimpleNamespace(folder=folder,workspace=folder/'workspace',config=team.definitions['coordinator'],state={'steps':1},assignment={'depth':0})


def call(team,agent,tool,data=''):return team.ledger.dispatch(agent,action(tool,data),10)


def metrics(spec,acc,params):
    return {'spec':spec,'final_validation_accuracy':acc,'per_epoch':[{'validation_accuracy':acc}],'split_counts':{'train':55000,'validation':5000},
            'hyperparameters':{'lr':0.001,'batch_size':256,'epochs':1},'environment':{'parameter_count':params},'finite_gradients':True}


def fake_training(team,monkeypatch,accuracies):
    blob=team.folder/'images.gz';blob.write_bytes(b'x');team.training.register_dataset(fl.DATASET,{'images.gz':blob,'labels.gz':blob},{'split':'train'})
    def start(agent,packet,key):
        family=packet['args'][packet['args'].index('--family')+1];net=next(n for n in team.ledger.state['nodes'].values() if n['type']=='net_spec' and n['spec']['family']==family)
        jid='job-'+family;out=team.training.root/'jobs'/jid/'output';out.mkdir(parents=True,exist_ok=True)
        (out/'metrics.json').write_text(json.dumps(metrics(net['spec'],accuracies[family],fl.params(net['spec']))));(out/'weights.safetensors').write_bytes(b'w')
        team.training.state['jobs'][jid]={'id':jid,'owner':'agents/lead','status':'SUCCEEDED','request':packet,'parent_job':None}
        return {'job_id':jid,'status':'SUCCEEDED','log_tail':''}
    monkeypatch.setattr(team.training,'start',start);monkeypatch.setattr(team.training,'status',lambda j:{'job_id':j['id'],'status':j['status'],'log_tail':''})


def test_fashion_ledger_has_no_corpus_and_counts_parameters(tmp_path):
    team=make(tmp_path);L=team.ledger;a=worker(team)
    assert L.docs=={} and L.task.name=='fashion' and 'FASHION_TRAIN' in L.view(a)['nodes']
    assert call(team,a,'sn_define',{'spec':fl.MLP,'rationale':'[FASHION_TRAIN]'})['params']==784*128+128+1290==101770
    assert call(team,a,'sn_define',{'spec':fl.CNN,'rationale':'[FASHION_TRAIN]'})['params']==160+4640+200832+1290==206922
    with pytest.raises(ValueError,match='width 16'):call(team,a,'sn_define',{'spec':{**fl.MLP,'width':5},'rationale':'x'})
    view=call(team,a,'ledger_view');assert view['spec_format']['family']==['mlp','cnn'] and view['documents']==[]
    assert team.registry.tools['sn_define'].description.startswith('JSON {spec:{family')


def test_accuracy_results_compare_and_promote_with_higher_is_better(tmp_path,monkeypatch):
    team=make(tmp_path);L=team.ledger;a=worker(team);fake_training(team,monkeypatch,{'mlp':0.85,'cnn':0.90})
    call(team,a,'sn_define',{'spec':fl.MLP,'rationale':'[FASHION_TRAIN]'});call(team,a,'sn_define',{'spec':fl.CNN,'rationale':'[FASHION_TRAIN]'})
    r1=call(team,a,'sn_train',{'net_id':'N1','epochs':1});r2=call(team,a,'sn_train',{'net_id':'N2','epochs':2,'lr':0.01})
    assert r1['result']['accuracy']==0.85 and r1['result']['dataset']=='fashion-val' and r1['proofs'][0]['passed'] and r2['result']['id']=='R2'
    with pytest.raises(ValueError,match='epochs must be an integer in 1..5'):call(team,a,'sn_train',{'net_id':'N1','epochs':8})
    with pytest.raises(ValueError,match='compare_results needs'):call(team,a,'compare_results',{'a':'R1','b':'R2','reject_rate':'0.09'})
    cmp=call(team,a,'compare_results',{'a':'R1','b':'R2'});assert cmp['winner']=='R2' and cmp['metric']=='accuracy' and cmp['accuracy_b']==0.9
    with pytest.raises(ValueError,match='args must be exactly'):call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'fashion-val','reject_rate':'0.09'},'rationale':'[CMP1]'})
    with pytest.raises(ValueError,match='use a template: BEATS, FEWER_PARAMS'):call(team,a,'ledger_claim',{'template':'GRAD_EQUALS','args':{'net':'N2'},'rationale':'[CMP1]'})
    c=call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'fashion-val'},'rationale':'[CMP1]'})
    assert call(team,a,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['R1','R2']})['status']=='supported'
    worse=call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N1','net_b':'N2','dataset':'fashion-val'},'rationale':'[CMP1]'})
    assert call(team,a,'ledger_promote',{'claim_id':worse['claim_id'],'evidence_ids':['R1','R2']})['status']=='refuted'
    fewer=call(team,a,'ledger_claim',{'template':'FEWER_PARAMS','args':{'net_a':'N1','net_b':'N2'},'rationale':'[N1] [N2]'})
    assert call(team,a,'ledger_promote',{'claim_id':fewer['claim_id'],'evidence_ids':[]})['status']=='supported'
    # A later assignment of the same role evaluates a net whose job an earlier assignment started: the ledger view, not job ownership, decides.
    later=SimpleNamespace(**{**vars(a),'folder':team.folder/'agents/task-2'});(later.folder/'workspace').mkdir(parents=True)
    ev=call(team,later,'ledger_evaluate',{'net_id':'N2'});assert ev['result']['dataset']=='fashion-test' and ev['result']['accuracy']==0.87 and ev['model_id'].startswith('model-')
    with pytest.raises(ValueError,match='limit reached'):call(team,a,'ledger_evaluate',{'net_id':'N1'})
    assert L.audit()['invariant_holds'] and L.audit()['choices_total']==0


def test_reports_call_empirical_results_observed_only_through_supported_claims(tmp_path,monkeypatch):
    team=make(tmp_path);a=worker(team);fake_training(team,monkeypatch,{'mlp':0.85,'cnn':0.90})
    call(team,a,'sn_define',{'spec':fl.MLP,'rationale':'[FASHION_TRAIN]'});call(team,a,'sn_define',{'spec':fl.CNN,'rationale':'[FASHION_TRAIN]'})
    call(team,a,'sn_train',{'net_id':'N1','epochs':1});call(team,a,'sn_train',{'net_id':'N2','epochs':1})
    lead={'agent':'coordinator','task_id':'lead','depth':0}
    def report(claims):return {'status':'DONE','summary':'s','files':['report.md'],'claims':claims}
    observed=lambda ids:{'statement':'CNN beats MLP on validation','epistemic_status':'observed','scope':'empirical','evidence_ids':ids,'limitations':'one seed'}
    with pytest.raises(ValueError,match='none is supported yet'):team.validate_assignment_report(report([observed(['R2'])]),lead)
    c=call(team,a,'ledger_claim',{'template':'BEATS','args':{'net_a':'N2','net_b':'N1','dataset':'fashion-val'},'rationale':'[R1] [R2]'});call(team,a,'ledger_promote',{'claim_id':c['claim_id'],'evidence_ids':['R1','R2']})
    with pytest.raises(ValueError,match=r'supported ledger claim ID in your view \(C1\)'):team.validate_assignment_report(report([observed(['R2'])]),lead)
    team.validate_assignment_report(report([observed(['C1','R2'])]),lead)
    team.validate_assignment_report(report([{'statement':'Dropout would help','epistemic_status':'hypothesis','scope':'empirical','evidence_ids':[],'limitations':'untested'}]),lead)
    with pytest.raises(ValueError,match='Unknown claim evidence'):team.validate_assignment_report(report([observed(['C9'])]),lead)


def test_managed_study_team_builds_and_its_gate_reads_the_ledger(tmp_path):
    holder={};agents=fl.write_agents(tmp_path/'agents',managed=True)
    team=Team(tmp_path/'run',fl.task(IMAGE,managed=True),agents_dir=agents,provider_factory=lambda c:None,sandbox_factory=FakeSandbox,
              model_evaluators={'fashion_test':FakeEval()},evaluators={'study':fl.study_evaluator(holder)});holder['team']=team
    assert 'ledger_view' not in team.definitions['report_reader']['tools'] and 'sn_train' in team.definitions['experiment_engineer']['tools'] and 'start_job' not in team.definitions['coordinator']['tools']
    assert team.evaluators['study'].evaluate({},team.task)=={'accepted':False,'reason':'Need at least two completed GPU experiments'}


def test_lenet_task_is_unchanged_by_the_adapter(tmp_path):
    from test_m3 import make as make_lenet, worker as lenet_worker
    team=make_lenet(tmp_path);L=team.ledger;lecun=lenet_worker(team,'coordinator')
    assert L.task.name=='lenet' and L.reject_mode() and L.datasets()==('usps-val','usps-test') and set(L.templates())=={'BEATS','FEWER_PARAMS','GRAD_EQUALS','INVARIANT_TO','FITS_CHIP'}
    assert 'locked' in call(team,lecun,'ledger_view') and team.registry.tools['sn_train'].description.startswith('JSON {net_id, epochs:1..30}')


def put(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))


def test_unverified_claim_counter(tmp_path):
    put(tmp_path/'team-state.json',{'assignments':{'task-a':{'agent':'experiment_engineer'},'task-b':{'agent':'researcher'}},'ledger':{'nodes':{'C1':{'type':'claim','status':'supported'},'C2':{'type':'claim','status':'refuted'}}}})
    put(tmp_path/'evidence/action-task-a-000003.json',{'kind':'tool_result','verification':'PENDING'})
    put(tmp_path/'evidence/evaluation-task-a.json',{'verification':'VERIFIED'})
    put(tmp_path/'evidence/model-evaluation-abc.json',{'measurement':{}})
    put(tmp_path/'evidence/review-1.json',{'kind':'review'})
    claim=lambda status,ids:{'statement':'s','epistemic_status':status,'scope':'empirical','evidence_ids':ids,'limitations':'l'}
    put(tmp_path/'reports/task-a.json',{'claims':[claim('observed',['action-task-a-000003']),claim('observed',['action-task-a-000003','C1']),claim('observed',['evaluation-task-a']),claim('inferred',['model-evaluation-abc']),claim('observed',['C2'])]})
    put(tmp_path/'reports/task-b.json',{'claims':[claim('observed',['review-1']),claim('hypothesis',[])]})
    out=count(tmp_path)
    assert {k:out['total'][k] for k in ('claims','verified','unverified','conjecture')}=={'claims':7,'verified':3,'unverified':3,'conjecture':1}
    assert out['total']['empirical']['unverified']==3 and out['by_role']['experiment_engineer']['verified']==3 and out['by_role']['researcher']['unverified']==1
    assert [c['via'] for c in out['claims'][:4]]==[[],['ledger'],['verified_record'],['model_evaluation']]
