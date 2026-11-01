"""Offline count of report claims by verification. Reads a run folder; never executes run code.

A claim marked observed or inferred is *verified* when at least one of its evidence IDs is a record the host verified
(verification VERIFIED, e.g. evaluation-*), a maintainer model evaluation (model-evaluation-*), or a ledger claim the host
promoted to supported. Otherwise it is *unverified*: it rests on execution receipts (verification PENDING), reviews or
artifacts. hypothesis/unknown claims are honest conjectures and are counted apart.
"""
import argparse
import json
from pathlib import Path


def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def count(folder):
    folder=Path(folder);state=load(folder/'team-state.json')
    ledger_ok={i for i,n in state.get('ledger',{}).get('nodes',{}).items() if n.get('type')=='claim' and n.get('status')=='supported'}
    def via(eid):
        if eid in ledger_ok:return 'ledger'
        p=folder/'evidence'/f'{eid}.json'
        if not p.exists():return None
        r=load(p)
        if r.get('verification')=='VERIFIED':return 'verified_record'
        if eid.startswith('model-evaluation-'):return 'model_evaluation'
        return None
    rows=[]
    for rp in sorted((folder/'reports').glob('*.json')):
        rep=load(rp);aid=rp.stem;role=state.get('assignments',{}).get(aid,{}).get('agent','coordinator' if aid=='lead' else aid)
        for c in rep.get('claims',[]):
            kinds=sorted({k for k in (via(e) for e in c.get('evidence_ids',[])) if k});status=c['epistemic_status']
            cls='conjecture' if status in ('hypothesis','unknown') else ('verified' if kinds else 'unverified')
            rows.append({'assignment':aid,'role':role,'status':status,'scope':c.get('scope'),'class':cls,'via':kinds,'statement':c['statement'][:160]})
    by={}
    for r in rows:
        d=by.setdefault(r['role'],{'claims':0,'verified':0,'unverified':0,'conjecture':0});d['claims']+=1;d[r['class']]+=1
    total={'claims':len(rows),**{k:sum(1 for r in rows if r['class']==k) for k in ('verified','unverified','conjecture')}}
    return {'run':folder.name,'by_role':by,'total':total,'claims':rows}


def table(out):
    lines=[f"# {out['run']}",'','| role | claims | verified | unverified | conjecture |','|---|---|---|---|---|']
    for role,d in sorted(out['by_role'].items()):lines.append(f"| {role} | {d['claims']} | {d['verified']} | {d['unverified']} | {d['conjecture']} |")
    t=out['total'];lines.append(f"| **total** | {t['claims']} | {t['verified']} | {t['unverified']} | {t['conjecture']} |")
    return '\n'.join(lines)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+');p.add_argument('--json',action='store_true');a=p.parse_args()
    for r in a.runs:
        out=count(r);print(json.dumps(out,indent=1,ensure_ascii=False) if a.json else table(out));print()
