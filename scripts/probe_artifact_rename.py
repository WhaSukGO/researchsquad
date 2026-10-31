"""Register/read fresh artifacts on supplied mounts; never changes failed runs."""
import argparse
import json
import os
from pathlib import Path

from goalagent.artifacts import ArtifactStore


def probe(roots, count=100):
    roots=[Path(root).resolve() for root in roots]
    if any(root.exists() for root in roots):
        raise ValueError('Use fresh probe directories')
    results=[]
    for root in roots:
        store=ArtifactStore(root/'artifacts')
        errors=[]
        completed=0
        for i in range(count):
            raw=os.urandom(100+i*53)
            try:
                record=store.register(raw,owner='probe',path=f'result-{i}.bin')
                assert store.read(record)==raw
                completed+=1
            except OSError as error:
                errors.append({'iteration':i,'errno':error.errno,'message':str(error)})
        results.append({'root':str(root),'registrations':completed,'errors':errors})
    result={'status':'passed' if all(not r['errors'] for r in results) else 'failed',
            'results':results,
            'scope':'Artifact register/read probe without injected faults. A pass does not explain prior EXDEV or prove absence.'}
    (roots[0]/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roots',nargs='+',required=True)
    args=parser.parse_args()
    print(json.dumps(probe(args.roots),indent=2))
