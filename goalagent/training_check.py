"""Real CPU containers exercise detach/recovery/cancellation/limits without model calls."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time
from .team import Team,BASE
from .training import TERMINAL
from .contracts import atomic_json


def verify(folder):
    folder=Path(folder).resolve()
    task={'goal':'Verify job lifecycle only, not research performance','inputs':{},'network':False,
        'budget':{'max_calls':10,'max_seconds':120,'max_assignments':5,'max_depth':2},
        'training':{'profiles':{'cpu':{'image':BASE,'gpu':False,'memory':'512m','cpus':1,
            'max_seconds':3,'max_output_bytes':32_000_000,'roles':['experiment_engineer']}}}}
    team=Team(folder,task)
    def actor(t):
        path=t.folder/'agents'/'fixture';space=path/'workspace';space.mkdir(parents=True,exist_ok=True)
        return SimpleNamespace(folder=path,workspace=space,config=t.definitions['experiment_engineer'],state={'steps':1})
    agent=actor(team);(agent.workspace/'go.py').write_text('import time\ntime.sleep(1)\nopen("large.bin","wb").write(b"x"*20000000)\n')
    packet={'profile':'cpu','code_files':['go.py'],'entrypoint':'go.py','args':[],'dataset_ids':[]}
    job=team.training.start(agent,packet,'detach');jid=job['job_id'];team.close()
    restored=Team(folder,task);agent=actor(restored)
    deadline=time.monotonic()+30
    while (status:=restored.training.status(restored.training.state['jobs'][jid]))['status'] not in TERMINAL:
        if time.monotonic()>deadline:raise TimeoutError('Detached recovery timed out')
        time.sleep(.3)
    assert status['status']=='SUCCEEDED',status
    ref=restored.training.register_model(agent,jid,'large.bin','checkpoint');assert ref['blob']['bytes']==20_000_000
    (agent.workspace/'go.py').write_text('import time\ntime.sleep(30)\n')
    slow=restored.training.start(agent,packet,'timeout')
    while (ended:=restored.training.status(restored.training.state['jobs'][slow['job_id']]))['status'] not in TERMINAL:
        if time.monotonic()>deadline:raise TimeoutError('Timeout enforcement failed')
        time.sleep(.3)
    assert ended['status']=='FAILED' and ended['docker']['ExitCode']==124,ended
    cancel=restored.training.start(agent,packet,'cancel')
    result=restored.training.dispatch(agent,{'tool':'cancel_job','argument':cancel['job_id']},30)
    assert result['status']=='CANCELLED',result
    output={'status':'passed','real_docker':True,'actual_model_calls':0,'detached_host_reopen':'SUCCEEDED',
        'large_checkpoint_bytes':ref['blob']['bytes'],'deadline_exit_code':ended['docker']['ExitCode'],
        'cancel_status':result['status'],'scope':'Runtime lifecycle and storage; not GPU training'}
    restored.trace.export(Path(folder)/'trace.html');atomic_json(Path(folder)/'verification.json',output);restored.close()
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args()
    print(json.dumps(verify(a.run_dir),indent=2))
