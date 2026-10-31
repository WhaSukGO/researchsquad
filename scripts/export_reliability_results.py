"""Collect existing repair evidence; never executes agent code or edits run state."""
import argparse
import json
from pathlib import Path
import shutil
from goalagent.team import ROOT
from goalagent.tracing import Trace


def export(output,passed,skipped):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    names={'windows_lock':'reliability-windows-lock-01','managed':'reliability-managed-04',
           'gpu':'reliability-fashion-03','reader':'reliability-reader-03','sources':'reliability-source-readiness-01'}
    evidence={name:json.loads((ROOT/'tmp'/run/'verification.json').read_text()) for name,run in names.items()}
    assert all(v.get('status')=='passed' for k,v in evidence.items() if k!='sources')
    assert all(r['status']=='retrieved' for r in evidence['sources']['results'])
    record={'scope':'Existing runtime repair verification, not a new scientific study or cross-run memory implementation',
        'regression':{'passed':passed,'skipped':skipped,'source':'Maintainer-recorded WSL Python 3.12 pytest -q result'},
        'runs':names,'evidence':evidence}
    lifecycle=Path('/tmp/rsq-reliability-training-03/verification.json')
    record['linux_ext4_training_lifecycle']=json.loads(lifecycle.read_text())
    assert record['linux_ext4_training_lifecycle']['status']=='passed'
    record['artifact_mount_probe']=json.loads((ROOT/'tmp/reliability-artifact-probe-02/verification.json').read_text())
    record['additional_findings']=[
        {'finding':'Initial CI supervisor could not read mode-0600 job.json with DAC override dropped',
         'resolution':'Publish only read-only non-secret control files as 0644 and directory as 0755; keep private Team state 0600',
         'verification':'Real ext4 Docker lifecycle and Unix permission assertions'},
        {'finding':'One DrvFS managed run blocked on artifact content.tmp rename with EXDEV',
         'affected_run':'reliability-managed-03','status':'Unresolved cause; preserved failed run; fresh managed-04 passed; 100 register/read probes on each of DrvFS and ext4 did not reproduce',
         'scope':'No cross-device copy fallback or uncertain execution replay was added'}]
    record['reader_restart']=json.loads((ROOT/'tmp'/names['reader']/'restart-verification.json').read_text())
    (output/'verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'docs/verification/runtime-reliability-20261031.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(ROOT/'docs/TODO-ko.md',output/'TODO-ko.md')
    shutil.copyfile(ROOT/'docs/runtime-reliability-results-ko.md',output/'report-ko.md')
    for key in ('reader','managed','gpu'):
        Trace(ROOT/'tmp'/names[key]/'traces').export(output/(key+'-trace.html'))
    print(json.dumps({'output':str(output),'reader_calls':evidence['reader']['calls'],'regression':record['regression']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True)
    p.add_argument('--passed',type=int,required=True);p.add_argument('--skipped',type=int,required=True)
    a=p.parse_args();export(a.output,a.passed,a.skipped)
