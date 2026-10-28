"""Version an evaluation correction without rewriting the original agent history."""
import argparse,json,shutil
from pathlib import Path
from scorebench.run import ROOT
from .contracts import atomic_json


def fork_for_recheck(source,destination,evidence):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Fork destination already exists')
    state=json.loads((source/'state.json').read_text())
    if state['status']=='running':raise ValueError('Checkpoint or finish the source before forking')
    shutil.copytree(source,destination)
    old_prefix=str(source.relative_to(ROOT));new_prefix=str(destination.relative_to(ROOT))
    # Preserve model prompts/events verbatim. Only redirect artifact paths for reinspection.
    for trace_path in (destination/'experiments').glob('*/sample-*/trace.json'):
        trace=json.loads(trace_path.read_text())
        if (trace.get('output') or '').startswith(old_prefix+'/'):
            trace['output']=new_prefix+trace['output'][len(old_prefix):]
        atomic_json(trace_path,trace)
    for experiment in (destination/'experiments').iterdir():
        for name in ['evaluation.json','detailed-results.json']:
            path=experiment/name
            if path.exists():path.rename(experiment/('prior-'+name))
    state.update(status='running',goal_met=False,best_experiment=None,evaluations={},pending=None,parent_run=old_prefix)
    state.setdefault('external_evidence',[]).append(evidence)
    state['known_evidence'].append(evidence['id'])
    atomic_json(destination/'state.json',state)
    atomic_json(destination/'evaluation-correction.json',evidence)
    return destination

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--destination',required=True);p.add_argument('--evidence',required=True)
    a=p.parse_args();print(fork_for_recheck(ROOT/a.source,ROOT/a.destination,json.loads((ROOT/a.evidence).read_text())))
