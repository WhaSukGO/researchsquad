"""Re-score frozen job outputs using only maintainer inference code and validation."""
import argparse
import json
from pathlib import Path
from goalagent.fashion_live import score

def audit(folder):
    folder=Path(folder);state=json.loads((folder/'team-state.json').read_text());rows=[]
    for job in state['training']['jobs'].values():
        if job['status']!='SUCCEEDED':continue
        out=folder/'training/jobs'/job['id']/'output'
        metrics=json.loads((out/'metrics.json').read_text())
        if 'best_validation_accuracy' in metrics:reported=metrics['best_validation_accuracy']
        else:reported=metrics['per_epoch'][-1]['validation_accuracy']
        actual=score(job['profile']['image'],Path.home()/'.cache/researchsquad/fashion-mnist',out/'weights.safetensors',True)
        rows.append({'job_id':job['id'],'reported_selected_accuracy':reported,
            'exported_epoch':metrics.get('exported_checkpoint_epoch',len(metrics.get('per_epoch',[]))),
            'independent_validation':actual,'accuracy_matches':actual['accuracy']==reported})
    (folder/'validation-audit.json').write_text(json.dumps(rows,indent=2)+'\n')
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();print(json.dumps(audit(a.run_dir),indent=2))
