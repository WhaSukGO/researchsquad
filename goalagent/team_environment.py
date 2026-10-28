"""Generic controlled package builds. Agent code is only executed inside Docker."""
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from .contracts import atomic_json,digest
from .sandbox import DockerSandbox,read_file,log_summary


def prepare(team,agent,data,timeout):
    from .team import BASE
    if set(data)!={'system_packages','python_packages','smoke_script'}:raise ValueError('Invalid environment request')
    for field,pattern in [('system_packages',r'[a-z0-9][a-z0-9+.-]*(=[a-zA-Z0-9:~+._-]+)?'),('python_packages',r'[a-zA-Z0-9][a-zA-Z0-9_.-]*==[a-zA-Z0-9][a-zA-Z0-9+._-]*')]:
        values=data[field]
        if not isinstance(values,list) or len(values)>64 or any(not isinstance(v,str) or not re.fullmatch(pattern,v) for v in values):raise ValueError('Invalid package requirements')
    source=read_file(agent.workspace,data['smoke_script'],limit=100000).decode()
    platform=subprocess.run(['docker','info','--format','{{.Architecture}}'],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    key=digest({'base':BASE,'system':data['system_packages'],'python':data['python_packages'],'smoke':source,'platform':platform,'uid':os.getuid(),'gid':os.getgid()})
    folder=team.folder/'environments'/key;receipt=folder/'receipt.json'
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        inspect=subprocess.run(['docker','image','inspect',saved['image']],capture_output=True,timeout=10)
        if saved['status']=='ready' and inspect.returncode==0 and (folder/'resolved-lock.txt').exists() and digest((folder/'resolved-lock.txt').read_text())==saved['lock_hash']:return {**saved,'cache_hit':True}
    if not team.task.get('network',False):raise ValueError('Environment builds require owner-granted network access')
    attempts=team.state.get('setup_attempts',0)
    if attempts>=3:raise ValueError('Setup attempt budget exhausted')
    team.state['setup_attempts']=attempts+1;team.save()
    folder.mkdir(parents=True,exist_ok=True);(folder/'readiness.py').write_text(source);context=folder/'build';context.mkdir(exist_ok=True)
    lines=['FROM '+BASE]
    if data['system_packages']:lines+=['RUN apt-get update && apt-get install -y --no-install-recommends '+' '.join(data['system_packages'])+' && rm -rf /var/lib/apt/lists/*']
    if data['python_packages']:lines+=['RUN python -m pip install --no-cache-dir '+' '.join(data['python_packages'])]
    lines+=['RUN python -m pip freeze > /opt/python-lock.txt && dpkg-query -W > /opt/system-lock.txt']
    (context/'Dockerfile').write_text('\n'.join(lines)+'\n');atomic_json(context/'requirements.json',data)
    tag='researchsquad-team:'+key[:16]+'-'+uuid.uuid4().hex[:10];started=time.monotonic()
    log=folder/'build.log'
    with log.open('wb') as stream:
        process=subprocess.Popen(['docker','build','--progress=plain','-t',tag,str(context)],stdout=stream,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if time.monotonic()-started>=timeout or log.stat().st_size>16000000:
                    process.kill();process.wait();return {'status':'environment_blocked','phase':'build','diagnostic':log_summary(log),'reason':'Build time/log limit'}
                time.sleep(.1)
        finally:
            if process.poll() is None:process.kill();process.wait()
    if process.returncode:return {'status':'environment_blocked','phase':'build','diagnostic':log_summary(log)}
    image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',tag],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    workspace=folder/'smoke-workspace'
    for name in ('inputs','tmp','output'):(workspace/name).mkdir(parents=True,exist_ok=True)
    (workspace/'smoke.py').write_text(source)
    sandbox=DockerSandbox(workspace,{'image':image,'network':False,'memory':'2g','cpus':2,'managed_environment':True})
    check=sandbox.run('python smoke.py',folder/'smoke.log',max(1,timeout-(time.monotonic()-started)))
    if check['exit_code'] or check['interrupted']:return {'status':'environment_blocked','phase':'readiness','diagnostic':check}
    lock=subprocess.run(['docker','run','--rm','--network','none','--read-only',image,'sh','-c','cat /opt/python-lock.txt /opt/system-lock.txt'],check=True,capture_output=True,text=True,timeout=10).stdout
    (folder/'resolved-lock.txt').write_text(lock)
    result={'status':'ready','image':image,'tag':tag,'key':key,'cache_hit':False,'elapsed_seconds':round(time.monotonic()-started,3),
            'readiness':check,'lock_hash':digest(lock),'scope':'Agent-proposed capability smoke test only; independent evaluation still required.'}
    atomic_json(receipt,result);return result
