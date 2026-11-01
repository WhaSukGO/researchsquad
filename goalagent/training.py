"""Team-owned detached jobs, explicit profiles and large immutable references."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import stat
from .contracts import atomic_json, digest
from .large_store import LargeStore
from .sandbox import workspace_path, read_file

TERMINAL={'SUCCEEDED','FAILED','CANCELLED','LOST','START_FAILED'}


def output_inventory(root,limit=128):
    pending=[(os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),Path())];files=[];seen=0
    try:
        while pending and seen<4096 and len(files)<limit:
            fd,relative=pending.pop()
            try:
                with os.scandir(fd) as entries:
                    for entry in entries:
                        seen+=1
                        if seen>4096 or len(files)>=limit:break
                        try:
                            if entry.is_symlink():continue
                            path=relative/entry.name
                            if entry.is_dir(follow_symlinks=False) and len(pending)<128:
                                child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                                pending.append((child,path))
                            elif stat.S_ISREG(entry.stat(follow_symlinks=False).st_mode):
                                files.append({'path':path.as_posix(),'bytes':entry.stat(follow_symlinks=False).st_size})
                        except OSError:continue
            finally:os.close(fd)
        return files
    finally:
        for fd,_ in pending:os.close(fd)
TOOLS={
 'training_catalog':'Empty argument; list owner-approved profiles, datasets and registered models; no host paths.',
 'register_dataset':'JSON {name,files:{destination:workspace_path},metadata:{source,split,...}}. Stream explicit workspace files into versioned public training data. Cannot nominate host paths or access protected labels.',
 'start_job':'JSON {profile,code_files:[workspace paths],entrypoint,args:[strings],dataset_ids:[ids],resume_model?:model_id}. Start a frozen Python job and return immediately. Output directory is /workspace/output; datasets are under /datasets/ID/; checkpoint input is /checkpoints/resume. No host execution.',
 'job_status':'Job ID; observe actual Docker status, bounded logs and output inventory. Terminal jobs have no running worker.',
 'read_job_output':'JSON {job_id,path}. Read a bounded regular UTF-8 job output (max 1 MB), such as progress/metrics JSON. This is reported experiment output, not protected measurement.',
 'publish_job_outputs':'JSON {job_id,files:{job_output_path:workspace_destination}}. After exit, freeze and copy up to 16 outputs directly into reviewable workspace artifacts without retyping content. Returns IDs/provenance, not file bodies. Include destinations in submit_report.files. Reported experiment output, not independent measurement.',
 'await_job':'Job ID; yield the current managed assignment while its job runs. Host observes completion without spending model calls, then continues this same assignment.',
 'cancel_job':'Job ID; stop your job, preserving completed output. Cancellation is not a valid training result.',
 'resume_job':'JSON {parent_job,model_id,args:[strings]}. New frozen attempt with the same source/profile/data and a registered checkpoint. Code must explicitly restore optimizer/RNG/data order; the host does not claim equivalence.',
 'register_model':'JSON {job_id,path,kind:model|checkpoint}. Stream a completed job output into immutable large storage; return model ID.',
 'evaluate_model':'JSON {model_id,evaluator}. Run a maintainer-registered model evaluator. Cannot supply evaluator source.',
 'record_decision':'JSON {summary,candidates:[{kind,target,status,reason}]}. Log a concise explicit decision and reported alternatives, not hidden reasoning.',
}


class TrainingRuntime:
    def __init__(self,team,model_evaluators=None):
        self.team=team;self.config=team.task.get('training',{});self.evaluators=model_evaluators or {}
        self.state=team.state.setdefault('training',{'jobs':{},'datasets':{},'models':{}})
        self.root=team.folder/'training';self.root.mkdir(exist_ok=True)
        self.store=LargeStore(self.root/'blobs',self.config.get('max_blob_bytes',8_000_000_000))
        if set(self.config)-{'profiles','max_blob_bytes'}:raise ValueError('Unknown training configuration')
        self.profiles=self.config.get('profiles',{})
        for name,p in self.profiles.items():
            if not re.fullmatch('[a-z][a-z0-9_-]{0,40}',name):raise ValueError('Invalid profile ID')
            if set(p)!={'image','gpu','memory','cpus','max_seconds','max_output_bytes','roles'}:raise ValueError('Invalid training profile')
            if not re.fullmatch(r'(?:sha256:|.+@sha256:)[a-f0-9]{64}',p['image']):raise ValueError('Training images must be immutable IDs/digests')
            if p['gpu'] not in (False,'all') or not re.fullmatch(r'[1-9][0-9]*[mg]',p['memory']):raise ValueError('Invalid GPU/memory profile')
            for k in ('cpus','max_seconds','max_output_bytes'):
                if type(p[k]) is not int or p[k]<=0:raise ValueError('Profile limits must be positive integers')
            if not isinstance(p['roles'],list) or not p['roles'] or not set(p['roles'])<=set(team.definitions):raise ValueError('Invalid profile role grants')
        if any(not isinstance(getattr(e,'version',None),str) for e in self.evaluators.values()):raise ValueError('Model evaluators require versions')
    def emit(self,kind,data):self.team.event('training_'+kind,data)
    def docker(self,*args,check=True):
        result=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,timeout=30)
        if check and result.returncode:raise RuntimeError('Docker '+str(args[0])+' failed: '+result.stderr[-4000:])
        return result
    def owner(self,agent):return str(agent.folder.relative_to(self.team.folder))
    def owned(self,agent,jid):
        if jid not in self.state['jobs']:raise ValueError('Unknown job')
        j=self.state['jobs'][jid]
        coordinator=agent.config['id']=='coordinator' and getattr(agent,'assignment',{}).get('depth',1)==0
        if j['owner']!=self.owner(agent) and not coordinator:raise ValueError('Job belongs to another assignment')
        return j
    def register_dataset(self,name,files,metadata=None):
        """Trusted owner API. Agents cannot nominate host paths or discover private files."""
        if not files or len(files)>256:raise ValueError('Dataset needs 1..256 explicit files')
        refs={}
        for dest,source in files.items():
            workspace_path(Path('/dataset'),dest)
            refs[dest]=self.store.register(source,kind='dataset',metadata={'path':dest})
        record={'name':name,'files':refs,'metadata':metadata or {}}
        did='dataset-'+digest(record)[:24];record['id']=did
        self.state['datasets'][did]=record;self.emit('dataset_registered',{'id':did,'name':name,'files':len(refs)})
        return did
    def catalog(self):
        return {'profiles':{k:{a:b for a,b in v.items() if a!='image'} for k,v in self.profiles.items()},
                'datasets':[{k:r[k] for k in ('id','name','metadata')} for r in self.state['datasets'].values()],
                'models':list(self.state['models'].values())}
    def dispatch(self,agent,action,timeout):
        tool=action['tool'];raw=action['argument']
        if tool=='training_catalog':return self.catalog()
        if tool=='register_dataset':
            d=json.loads(raw)
            if set(d)!={'name','files','metadata'} or not isinstance(d['files'],dict) or not isinstance(d['metadata'],dict):raise ValueError('Invalid dataset registration')
            files={dest:workspace_path(agent.workspace,source) for dest,source in d['files'].items()}
            did=self.register_dataset(d['name'],files,{**d['metadata'],'registered_by':self.owner(agent)})
            return {'dataset_id':did,'scope':'Published training material, not protected evaluation gold'}
        if tool=='record_decision':
            d=json.loads(raw)
            if len(raw)>32000 or set(d)!={'summary','candidates'} or not isinstance(d['summary'],str) or not isinstance(d['candidates'],list):raise ValueError('Invalid decision record')
            if len(d['candidates'])>16:raise ValueError('Too many reported candidates')
            for c in d['candidates']:
                if set(c)!={'kind','target','status','reason'} or any(not isinstance(v,str) for v in c.values()):raise ValueError('Invalid reported candidate')
            self.emit('decision',{'agent':self.owner(agent),**d})
            return {'recorded':True,'scope':'Explicitly reported alternatives only'}
        if tool=='start_job':return self.start(agent,json.loads(raw),self.team.dispatch_id(agent,action))
        if tool=='job_status':return self.status(self.owned(agent,raw))
        if tool=='publish_job_outputs':
            d=json.loads(raw)
            if set(d)!={'job_id','files'} or not isinstance(d['files'],dict) or not 1<=len(d['files'])<=16:raise ValueError('Expected 1..16 output mappings')
            j=self.owned(agent,d['job_id'])
            if self.status(j)['status'] not in {'SUCCEEDED','FAILED','CANCELLED'}:raise ValueError('Publish only exited jobs')
            if len(set(d['files'].values()))!=len(d['files']):raise ValueError('Duplicate destinations')
            pending=[];total=0
            for source,destination in d['files'].items():
                target=workspace_path(agent.workspace,destination)
                if target.relative_to(agent.workspace).parts[0] in {'inputs','baselines'}:raise ValueError('Inputs are read-only')
                content=read_file(self.root/'jobs'/j['id']/'output',source,limit=16_000_000)
                total+=len(content)
                if total>64_000_000:raise ValueError('Output bundle exceeds 64 MB')
                if target.exists() and read_file(agent.workspace,destination)!=content:raise ValueError('Destination has different content')
                pending.append((source,destination,target,content))
            results=[]
            for source,destination,target,content in pending:
                artifact=self.team.register_artifact(content,owner='job:'+j['id'],path=source)
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():
                    with target.open('xb') as stream:stream.write(content)
                record={'job_id':j['id'],'source':source,'destination':destination,'artifact_id':artifact['artifact_id'],'bytes':len(content)}
                agent.state.setdefault('job_output_files',{})[destination]=record
                results.append(record)
            if hasattr(agent,'save'):agent.save()
            self.emit('outputs_published',{'owner':self.owner(agent),'files':results})
            return {'files':results,'scope':'Frozen reported outputs; not independent evaluation'}
        if tool=='read_job_output':
            d=json.loads(raw)
            if set(d)!={'job_id','path'}:raise ValueError('Invalid output read')
            j=self.owned(agent,d['job_id'])
            content=read_file(self.root/'jobs'/j['id']/'output',d['path'],limit=1_000_000)
            return {'job_id':j['id'],'path':d['path'],'text':content.decode('utf-8'),
                    'scope':'Reported output; not independent validation'}
        if tool=='await_job':
            if not self.team.managed:raise ValueError('await_job requires managed workflow')
            result=self.status(self.owned(agent,raw))
            if result['status'] in {'RUNNING','STARTING'}:
                self.team.state['assignments'][agent.folder.name]['waiting_training_job']=raw
                agent.state['status']='checkpointed';agent.save();self.team.save()
            return result
        if tool=='cancel_job':
            j=self.owned(agent,raw)
            if self.status(j)['status'] not in TERMINAL:
                self.docker('stop','-t','5',j['container'])
                j['cancel_requested']=True
            return self.status(j)
        if tool=='register_model':return self.register_model(agent,**json.loads(raw))
        if tool=='evaluate_model':return self.evaluate(agent,**json.loads(raw))
        if tool=='resume_job':
            d=json.loads(raw)
            if set(d)!={'parent_job','model_id','args'}:raise ValueError('Invalid resume fields')
            parent=self.owned(agent,d['parent_job'])
            if self.status(parent)['status'] not in TERMINAL:raise ValueError('Stop the parent job before resuming')
            model=self.state['models'].get(d['model_id'])
            if not model or model['job_id']!=parent['id'] or model['kind']!='checkpoint':raise ValueError('Resume checkpoint must belong to parent')
            packet={k:parent['request'][k] for k in ('profile','code_files','entrypoint','args','dataset_ids')}
            packet.update(args=d['args'],resume_model=d['model_id'])
            return self.start(agent,packet,self.team.dispatch_id(agent,action),parent=parent)
        raise ValueError('Unknown training tool')
    def start(self,agent,d,key,parent=None):
        required={'profile','code_files','entrypoint','args','dataset_ids'}
        if not isinstance(d,dict) or not required<=set(d) or set(d)-required-{'resume_model'}:raise ValueError('Invalid job fields')
        profile=self.profiles.get(d['profile'])
        if not profile or agent.config['id'] not in profile['roles']:raise ValueError('Training profile not granted to role')
        if not isinstance(d['args'],list) or len(d['args'])>64 or any(not isinstance(x,str) or len(x)>2000 for x in d['args']):raise ValueError('Invalid job arguments')
        if not isinstance(d['code_files'],list) or not 1<=len(d['code_files'])<=32 or d['entrypoint'] not in d['code_files']:raise ValueError('Invalid code inventory')
        if not isinstance(d['dataset_ids'],list) or len(d['dataset_ids'])>8 or not set(d['dataset_ids'])<=set(self.state['datasets']):raise ValueError('Unknown dataset')
        jid='job-'+digest([self.team.folder.name,self.owner(agent),key])[:24]
        if jid in self.state['jobs']:
            j=self.owned(agent,jid)
            if j['request']!=d:raise ValueError('Job key reused with changed request')
            return self.status(j)
        folder=self.root/'jobs'/jid;code=folder/'code';out=folder/'output'
        code.mkdir(parents=True);out.mkdir();out.chmod(0o777)
        for name in d['code_files']:
            src=(self.root/'jobs'/parent['id']/'code') if parent else agent.workspace
            blob=read_file(src,name,limit=1_000_000)
            target=workspace_path(code,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
        command=['python','/workspace/code/'+d['entrypoint'],*d['args']]
        control=folder/'control';control.mkdir();control.chmod(0o755)
        atomic_json(control/'job.json',{'command':command,'uid':os.getuid() or 1000,'gid':os.getgid() or 1000,
            'max_seconds':profile['max_seconds'],'max_output_bytes':profile['max_output_bytes']})
        # PID 1 runs with DAC override dropped and a different UID from the host.
        # Publish only this non-secret, read-only control packet for it to read;
        # private Team state keeps atomic_json's restrictive temporary-file mode.
        (control/'job.json').chmod(0o644)
        shutil.copyfile(Path(__file__).with_name('job_supervisor.py'),control/'supervisor.py')
        (control/'supervisor.py').chmod(0o644)
        container='rsq-'+digest([str(self.team.folder),jid])[:24]
        j={'id':jid,'owner':self.owner(agent),'request':d,'parent_job':parent['id'] if parent else None,
           'profile':profile,'container':container,'status':'STARTING','created_at':time.time()}
        self.state['jobs'][jid]=j;self.emit('job_reserved',j)
        cmd=['run','-d','--name',container,'--label','researchsquad.training=true','--read-only',
            '--network','none','--cap-drop=ALL','--cap-add=SETUID','--cap-add=SETGID','--cap-add=KILL',
            '--security-opt','no-new-privileges','--pids-limit','128','--memory',profile['memory'],
            '--cpus',profile['cpus'],'--tmpfs','/tmp:rw,nosuid,nodev,size=512m',
            '--log-driver','local','--log-opt','max-size=16m','--log-opt','max-file=1','--log-opt','compress=false']
        def mount(source,destination,readonly=True):
            cmd.extend(['--mount',f'type=bind,src={source},dst={destination}'+(',readonly' if readonly else '')])
        mount(code,'/workspace/code');mount(control,'/control');mount(out,'/workspace/output',False)
        for did in d['dataset_ids']:
            for dest,ref in self.state['datasets'][did]['files'].items():mount(self.store.verify(ref),'/datasets/'+did+'/'+dest)
        if d.get('resume_model'):
            m=self.state['models'].get(d['resume_model'])
            if not m:raise ValueError('Unknown resume model')
            mount(self.store.verify(m['blob']),'/checkpoints/resume')
        gpu_lock=Path.home()/'.cache/researchsquad/gpu-start.lock';gpu_lock.parent.mkdir(parents=True,exist_ok=True)
        try:
            with gpu_lock.open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                if profile['gpu']:
                    running=self.docker('ps','-q','--filter','label=researchsquad.training.gpu=all').stdout.strip()
                    if running:raise ValueError('GPU_BUSY: another ResearchSquad training job is running')
                    cmd.extend(['--gpus','all','--label','researchsquad.training.gpu=all'])
                cmd.extend([profile['image'],'python','/control/supervisor.py'])
                self.docker(*cmd)
        except Exception as error:
            j['start_error']=str(error)
            self.emit('job_start_uncertain',{'job_id':jid,'error':str(error)})
            # A CLI failure/timeout is not evidence that no container started.
            raise
        self.emit('job_started',{'job_id':jid,'container':container})
        return self.status(j)
    def status(self,j):
        result=self.docker('inspect','--format','{{json .State}}',j['container'],check=False)
        if result.returncode:
            if j['status']=='STARTING':status='START_UNCERTAIN'
            else:status='LOST'
            observation={'diagnostic':result.stderr[-1000:]}
        else:
            observation=json.loads(result.stdout)
            status=('START_FAILED' if observation.get('Status')=='created' else
                'RUNNING' if observation['Running'] else 'CANCELLED' if j.get('cancel_requested') else
                'SUCCEEDED' if observation['ExitCode']==0 else 'FAILED')
        if j['status']!=status:
            j['status']=status;self.emit('job_state',{'job_id':j['id'],'status':status,'docker':observation})
        logs=self.docker('logs','--tail','40',j['container'],check=False)
        if status in TERMINAL and result.returncode==0:
            log_path=self.root/'jobs'/j['id']/'job.log'
            if not log_path.exists():
                full=self.docker('logs',j['container'],check=False)
                log_path.write_text((full.stdout+full.stderr)[-16_000_000:])
        folder=self.root/'jobs'/j['id']/'output'
        files=output_inventory(folder)
        return {'job_id':j['id'],'owner':j['owner'],'status':status,'parent_job':j['parent_job'],'docker':observation,
                'log_tail':(logs.stdout+logs.stderr)[-6000:],'outputs':files}
    def register_model(self,agent,job_id,path,kind,*,trusted=False):
        j=self.state['jobs'][job_id] if trusted else self.owned(agent,job_id)  # trusted: the caller (the ledger) already decided who may use this job
        if self.status(j)['status'] not in {'SUCCEEDED','FAILED','CANCELLED'}:raise ValueError('Freeze model only after job exits')
        if kind not in {'model','checkpoint'}:raise ValueError('Invalid model kind')
        source=workspace_path(self.root/'jobs'/job_id/'output',path)
        ref=self.store.register(source,kind=kind,metadata={'job':job_id,'path':path})
        mid='model-'+digest([job_id,path,ref['id']])[:24]
        record={'id':mid,'job_id':job_id,'kind':kind,'blob':ref}
        self.state['models'][mid]=record;self.emit('model_registered',record);return record
    def evaluate(self,agent,model_id,evaluator,*,trusted=False):
        m=self.state['models'].get(model_id)
        if not m:raise ValueError('Unknown model')
        if not trusted:self.owned(agent,m['job_id'])
        e=self.evaluators.get(evaluator)
        if not e:raise ValueError('No maintainer model evaluator registered')
        path=self.store.verify(m['blob'])
        key='model-evaluation-'+digest([model_id,evaluator,e.version])[:24]
        if key in self.team.state['evidence']:return self.team.receipt(key)
        result=e(path,self.state['jobs'][m['job_id']])
        if not isinstance(result,dict) or type(result.get('accepted')) is not bool:raise ValueError('Invalid model evaluation')
        self.emit('model_evaluated',{'model_id':model_id,'evaluator':evaluator,'measurement':result})
        return self.team.record(key,{'model_id':model_id,'evaluator':evaluator,'evaluator_version':e.version,
            'measurement':result,'scope':'Independent model adapter measurement; does not alone complete project gates'})
