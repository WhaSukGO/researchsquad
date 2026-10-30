import json
from scripts.compare_fashion_studies import summarize,handoff_audit

def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))

def test_repeat_measurement_excludes_errors_and_distinguishes_pagination(tmp_path):
    state={'assignments':{'worker':{'agent':'researcher'}},'goal_met':False,
        'workflow':{'run_status':'ACTIVE'},'training':{'jobs':{}},'calls':4}
    put(tmp_path/'team-state.json',state)
    put(tmp_path/'team-contract.json',{'task':{'budget':{},'workflow':{}}})
    history=[]
    for offset in [0,0,4000]:
        history.append({'tool':'read_file','argument':json.dumps({'path':'x','offset':offset}),
            'observation':{'path':'x','offset':offset,'text':'first' if offset==0 else 'second'}})
    history.append({'tool':'read_file','step':4,'argument':'{}','observation':{'error':'missing'}})
    put(tmp_path/'agents/worker/worker-state.json',{'history':history})
    put(tmp_path/'traces/span.json',{'kind':'host_event','status':'COMPLETED','started_at':'2026-10-31T00:00:00+00:00',
        'ended_at':'2026-10-31T00:00:10+00:00'})
    result=summarize(tmp_path)
    assert result['read_calls']==3 and result['same_resource_extra_reads']==2
    assert result['identical_window_extra_reads']==1 and result['wall_seconds']==10

def test_audit_uses_parent_artifact_inventory_and_detects_changed_receiver(tmp_path):
    row={'job_id':'job','source':'metrics.json','destination':'metrics.json','artifact_id':'original','bytes':2}
    state={'events':[{'kind':'training_outputs_published','data':{'files':[row]}}],
        'artifacts':{'copy':{'path':'metrics.json'},'report':{'path':'report.md'}},
        'assignments':{
            'critic':{'agent':'critic','assignment':{'review_of':'worker','review_scope':'full','inputs':{},'parent_artifacts':['copy']}},
            'reader':{'agent':'report_reader','assignment':{'review_of':'worker','review_scope':'report_only','inputs':{},'parent_artifacts':['report']}}}}
    put(tmp_path/'team-state.json',state)
    for name in ['training/jobs/job/output/metrics.json','artifacts/original/content','agents/critic/workspace/inputs/parent/metrics.json']:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'{}')
    result=handoff_audit(tmp_path)[0]
    assert result['registered_identical']
    assert [x['role'] for x in result['reviewer_receivers']]==['critic']
    assert result['reviewer_receivers'][0]['identical']
    (tmp_path/'agents/critic/workspace/inputs/parent/metrics.json').write_bytes(b'changed')
    assert not handoff_audit(tmp_path)[0]['reviewer_receivers'][0]['identical']
