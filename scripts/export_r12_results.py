"""Collect existing R12 evidence without changing runs or executing agents."""
import argparse
import json
from pathlib import Path
import re
import shutil

from goalagent.team import ROOT
from goalagent.tracing import Trace


def export(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    locations={'drvfs_mount':ROOT/'tmp/r12-production-mount-01/verification.json',
               'ext4_mount':Path('/tmp/rsq-r12-production-mount-01/verification.json'),
               'windows_read_lock':ROOT/'tmp/r12-windows-lock-02/verification.json',
               'managed':ROOT/'tmp/r12-managed-01/verification.json',
               'training_lifecycle':Path('/tmp/rsq-r12-training-01/verification.json')}
    evidence={key:json.loads(path.read_text()) for key,path in locations.items()}
    assert all(item['status']=='passed' for item in evidence.values())
    log=(ROOT/'tmp/r12-final-pytest.log').read_text()
    counts=re.search(r'(\d+) passed, (\d+) skipped in ([\d.]+)s',log)
    if not counts:raise ValueError('Completed regression result missing')
    events=[json.loads(line) for line in (ROOT/'tmp/reliability-managed-03/events.jsonl').read_text().splitlines()]
    record={'status':'passed','scope':'R12 publication mechanism reproduction and regression; no actual model calls or historical-trigger attribution',
            'historical_trigger_proven':False,'actual_model_calls':0,
            'regression':{'passed':int(counts[1]),'skipped':int(counts[2]),'seconds':float(counts[3])},
            'original_failure':[event for event in events if 'Invalid cross-device link' in str(event)],
            'evidence':evidence,
            'windows_lock_matrix':json.loads((ROOT/'tmp/r12-lock-matrix-01/verification.json').read_text(encoding='utf-8-sig'))}
    text=json.dumps(record,ensure_ascii=False,indent=2)+'\n'
    (output/'verification.json').write_text(text)
    (ROOT/'docs/verification/r12-publication-20261031.json').write_text(text)
    shutil.copyfile(ROOT/'docs/r12-publication-results-ko.md',output/'report-ko.md')
    shutil.copyfile(ROOT/'docs/TODO-ko.md',output/'TODO-ko.md')
    Trace(ROOT/'tmp/r12-managed-01/traces').export(output/'managed-trace.html')
    print(json.dumps({'output':str(output),'regression':record['regression'],'status':record['status']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    export(parser.parse_args().output)
