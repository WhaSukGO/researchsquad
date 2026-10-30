import json
import pytest
from test_training import worker
from test_managed import make
from goalagent.artifacts import capture_workspace,text_snapshot

def setup(tmp_path,monkeypatch):
    team,_=make(tmp_path);agent=worker(team);runtime=team.training
    job={'id':'job-one','owner':runtime.owner(agent),'status':'SUCCEEDED'}
    runtime.state['jobs'][job['id']]=job
    root=runtime.root/'jobs/job-one/output';root.mkdir(parents=True)
    (root/'metrics.json').write_text('{"accuracy":0.8}')
    monkeypatch.setattr(runtime,'status',lambda j:{'status':j['status']})
    return team,agent,runtime,root

def publish(runtime,agent,files):
    return runtime.dispatch(agent,{'tool':'publish_job_outputs','argument':json.dumps({'job_id':'job-one','files':files})},10)

def test_published_bytes_provenance_idempotence_and_submission(tmp_path,monkeypatch):
    team,a,r,root=setup(tmp_path,monkeypatch)
    first=publish(r,a,{'metrics.json':'evidence/metrics.json'})
    assert publish(r,a,{'metrics.json':'evidence/metrics.json'})==first
    row=first['files'][0];record=team.state['artifacts'][row['artifact_id']]
    assert record['owner']=='job:job-one'
    assert team.artifact_store.read(record)==(root/'metrics.json').read_bytes()
    manifest=capture_workspace(a.folder,a.workspace,files=['evidence/metrics.json'])
    assert text_snapshot(a.folder,manifest)['evidence/metrics.json']=='{"accuracy":0.8}'
    assert 'text' not in row and 'evidence/metrics.json' in a.state['job_output_files']

def test_publish_denies_running_foreign_unsafe_and_overwrite(tmp_path,monkeypatch):
    team,a,r,root=setup(tmp_path,monkeypatch)
    r.state['jobs']['job-one']['status']='RUNNING'
    with pytest.raises(ValueError,match='exited'):publish(r,a,{'metrics.json':'metrics.json'})
    r.state['jobs']['job-one']['status']='SUCCEEDED'
    other=worker(team,name='other')
    with pytest.raises(ValueError,match='another assignment'):publish(r,other,{'metrics.json':'metrics.json'})
    for dest in ('../escape','inputs/fake','baselines/fake'):
        with pytest.raises(ValueError):publish(r,a,{'metrics.json':dest})
    (a.workspace/'metrics.json').write_text('do not overwrite')
    with pytest.raises(ValueError,match='different'):publish(r,a,{'metrics.json':'metrics.json'})
    (root/'link').symlink_to(root/'metrics.json')
    with pytest.raises((ValueError,OSError)):publish(r,a,{'link':'linked'})

def test_mapping_validation_prevents_partial_publication(tmp_path,monkeypatch):
    team,a,r,root=setup(tmp_path,monkeypatch)
    with pytest.raises((ValueError,OSError)):
        publish(r,a,{'metrics.json':'first','missing':'second'})
    assert not (a.workspace/'first').exists()
    with pytest.raises(ValueError,match='Duplicate'):publish(r,a,{'metrics.json':'same','missing':'same'})
