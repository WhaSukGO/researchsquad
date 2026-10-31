"""Real mount-race reproducer. Run as root under unshare --mount --propagation private.

Only the fresh run directory is mounted, inside the private namespace. Worker
containers never receive mount permission. No Python failure is injected.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import threading
import time

from goalagent.artifacts import ArtifactStore
from goalagent.contracts import atomic_json


def verify(folder,iterations=5000,fixed_iterations=1000):
    if os.geteuid()!=0 or any(' shared:' in line for line in Path('/proc/self/mountinfo').read_text().splitlines()):
        raise RuntimeError('Requires root and private mount propagation: unshare --mount --propagation private')
    if os.readlink('/proc/self/ns/mnt')==os.readlink('/proc/1/ns/mnt'):
        raise RuntimeError('Refusing to mount in the init namespace')
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    publication=folder/'publication';publication.mkdir()
    libc=ctypes.CDLL(None,use_errno=True);encoded=os.fsencode(publication)
    changes=[];mount_errors=[];phases=[]
    def phase(name,count,operation):
        stop=threading.Event();errors={};success=0;started=time.monotonic()
        def churn():
            while not stop.is_set():
                if libc.mount(encoded,encoded,None,4096,None)!=0:
                    mount_errors.append({'operation':'bind','errno':ctypes.get_errno()});break
                changes.append(1)
                time.sleep(.0001)
                if libc.umount2(encoded,2)!=0:
                    mount_errors.append({'operation':'detach','errno':ctypes.get_errno()});break
        thread=threading.Thread(target=churn);thread.start()
        try:
            for i in range(count):
                try:operation(i);success+=1
                except OSError as error:errors[str(error.errno)]=errors.get(str(error.errno),0)+1
        finally:stop.set();thread.join()
        result={'name':name,'iterations':count,'success':success,'errors':errors,'seconds':round(time.monotonic()-started,3)}
        phases.append(result);print(json.dumps(result),flush=True)
    def legacy(i):
        source=publication/'content.tmp';source.write_bytes(b'complete-data')
        source.replace(publication/'content')
    def fixed_json(i):
        atomic_json(publication/'state.json',{'sequence':i,'body':'complete-data'})
        assert json.loads((publication/'state.json').read_text())['sequence']==i
    store=ArtifactStore(publication/'artifacts')
    def fixed_artifact(i):
        raw=f'complete-artifact-{i}'.encode()
        record=store.register(raw,owner='probe',path=f'result-{i}.bin')
        assert store.read(record)==raw
    phase('legacy_absolute_rename',iterations,legacy)
    phase('fixed_atomic_json',fixed_iterations,fixed_json)
    phase('fixed_artifact_register_read',fixed_iterations,fixed_artifact)
    reproduced=phases[0]['errors'].get('18',0)>0
    clean=not mount_errors and all(not p['errors'] for p in phases[1:])
    result={'status':'passed' if reproduced and clean else 'inconclusive' if clean else 'failed',
            'platform':platform.platform(),'folder':str(folder),'mount_changes':len(changes),
            'mount_errors':mount_errors,'exdev_reproduced':reproduced,'phases':phases,
            'scope':'Real same-directory mount-instance race and production publication calls. No injected errno. Historical trigger is not proven.'}
    (folder/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True)
    parser.add_argument('--iterations',type=int,default=5000)
    parser.add_argument('--fixed-iterations',type=int,default=1000)
    args=parser.parse_args()
    result=verify(args.run_dir,args.iterations,args.fixed_iterations)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='passed' else 1)
