"""Actual GPU fault-mechanism check, not evidence of agent recovery ability."""
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from goalagent.team import Team,ROOT
from goalagent.recovery_live import source_for
from goalagent.fashion_check import download
from goalagent.contracts import atomic_json

def verify(folder):
    folder=Path(folder).resolve();data=download(Path.home()/'.cache/researchsquad/fashion-mnist')
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}','researchsquad-training:torch2.9.1-cu128'],capture_output=True,text=True,check=True).stdout.strip()
    task={'goal':'Fault mechanism readiness only','inputs':{},'network':False,
        'budget':{'max_calls':1,'max_seconds':180,'max_assignments':2,'max_depth':1},
        'training':{'profiles':{'gpu':{'image':image,'gpu':'all','memory':'8g','cpus':4,'max_seconds':60,'max_output_bytes':150000000,'roles':['experiment_engineer']}}}}
    team=Team(folder,task);space=folder/'agents/fixture/workspace';space.mkdir(parents=True)
    actor=SimpleNamespace(folder=space.parent,workspace=space,config=team.definitions['experiment_engineer'],state={'steps':1})
    did=team.training.register_dataset('official train',{'images.gz':data/'train-images-idx3-ubyte.gz','labels.gz':data/'train-labels-idx1-ubyte.gz'})
    for n in ('fashion_model.py','fashion_study_models.py'):(space/n).write_bytes((ROOT/'goalagent'/n).read_bytes())
    results=[]
    try:
        for kind in ('interruption','shape','loss'):
            (space/'train.py').write_text(source_for(kind))
            packet={'profile':'gpu','code_files':['train.py','fashion_model.py','fashion_study_models.py'],'entrypoint':'train.py','args':['--data','/datasets/'+did,'--epochs','3'],'dataset_ids':[did]}
            start=team.training.start(actor,packet,kind);j=team.training.state['jobs'][start['job_id']];deadline=time.monotonic()+90;killed=False
            while True:
                out=team.training.root/'jobs'/j['id']/'output'
                if kind=='interruption' and (out/'boundary.json').exists() and not killed:
                    team.training.docker('kill','--signal','KILL',j['container']);killed=True
                status=team.training.status(j)
                if status['status'] not in {'RUNNING','STARTING'}:break
                if time.monotonic()>deadline:raise TimeoutError(kind)
                time.sleep(.15)
            assert status['status']=='FAILED',status
            log=(team.training.root/'jobs'/j['id']/'job.log').read_text()
            if kind=='interruption':assert status['docker']['ExitCode']==137 and (out/'checkpoint.pt').exists()
            if kind=='shape':assert 'mat1 and mat2 shapes cannot be multiplied' in log
            if kind=='loss':assert json.loads((out/'failure.json').read_text())['loss']=='nan'
            results.append({'kind':kind,'job_id':j['id'],'status':status['status'],'exit':status['docker']['ExitCode'],'external_kill':killed,'log_tail':status['log_tail']})
        atomic_json(folder/'verification.json',{'scope':'Fault preparation, no model calls or agent recovery choices','results':results})
        print(json.dumps(results,indent=2))
    finally:team.close()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();verify(a.run_dir)
