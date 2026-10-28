"""Verify the reviewed environment without model calls or development labels."""
import argparse
import json
from pathlib import Path
from .contracts import atomic_json
from .environments import EnvironmentManager
from .sandbox import DockerSandbox
from scorebench.run import ROOT


class NoModel:
    def call(self, *args, **kwargs):
        raise RuntimeError('Reviewed profile failed; verification does not spend model calls')


def verify(folder, registry=None):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    spec=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    manager=EnvironmentManager(folder,spec['environment'],spec['worker'],NoModel(),registry)
    first=manager.ensure(lambda:None,lambda:900)
    if first['status']!='ready':
        atomic_json(folder/'verification.json',first)
        raise RuntimeError('Environment readiness failed: '+json.dumps(first))
    image=first['image']['id']; executions=[]
    for index in (1,2):
        receipt=manager.ensure(lambda:None,lambda:900)
        assert receipt['cache_hit'] and receipt['image']['id']==image
        workspace=folder/f'check-{index}'/'workspace'
        for name in ('inputs','baselines','output','tmp'):(workspace/name).mkdir(parents=True,exist_ok=True)
        (workspace/'baselines/prediction.txt').write_text('baseline')
        script="""test ! -e /workspace/other-experiment || exit 1
if echo changed > /workspace/baselines/prediction.txt; then exit 2; fi
if touch /opt/changed; then exit 3; fi
test ! -e /var/run/docker.sock || exit 4
python -c 'import music21, converter21; print("prepared imports available")'
echo own-work > /workspace/other-experiment
"""
        sandbox=DockerSandbox(workspace,{**spec['worker'],'image':image,'network':False,'managed_environment':True})
        result=sandbox.run(script,folder/f'check-{index}.log',30)
        assert result['exit_code']==0,result
        assert (workspace/'baselines/prediction.txt').read_text()=='baseline'
        executions.append(result)
    result={'status':'passed','first_lookup_cache_hit':first['cache_hit'],'image_id':image,
            'independent_workspaces':2,'reuse_without_rebuild':True,'read_only_baselines':True,
            'reference_labels_used':False,'model_calls':0,'executions':executions}
    atomic_json(folder/'verification.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True)
    parser.add_argument('--registry')
    args=parser.parse_args()
    print(json.dumps(verify(args.run_dir,args.registry),indent=2))


if __name__=='__main__':main()
