"""WSL half of a real Windows read-lock probe, not a model/research experiment.

An external Windows reader holds state.json until 150 ms after attempted appears.
The wrapper records real OS errors; it never injects a replace failure.
"""
import argparse
import json
import os
from pathlib import Path
import time
from goalagent.contracts import atomic_json


def verify(folder):
    folder=Path(folder).resolve();target=folder/'state.json';started=time.monotonic()
    while not (folder/'locked').exists():
        if time.monotonic()-started>15:raise TimeoutError('Windows lock sentinel missing')
        time.sleep(.01)
    original=os.replace;attempts=[]
    def observe(source,dest,**kwargs):
        if dest!=target.name:return original(source,dest,**kwargs)
        (folder/'attempted').write_text('Actual replacement attempt')
        try:
            result=original(source,dest,**kwargs);attempts.append({'result':'replaced'});return result
        except OSError as error:
            attempts.append({'result':'os_error','errno':error.errno,'error':str(error)});raise
    os.replace=observe
    try:atomic_json(target,{'value':'after'})
    finally:os.replace=original
    assert json.loads(target.read_text())=={'value':'after'}
    record={'status':'passed','attempts':attempts,'sharing_error_reproduced':any(a['result']=='os_error' for a in attempts),
        'scope':'Real OS read-lock/replacement probe; no model calls or forced OS exceptions. Does not establish the original incident cause.'}
    atomic_json(folder/'verification.json',record)
    print(json.dumps(record))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();verify(a.run_dir)
