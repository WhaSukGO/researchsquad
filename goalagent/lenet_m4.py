"""Milestone 4: ablation conditions over the M3 department simulation, and the cross-run report.

Every condition is the M3 task with one setting changed. The report never judges whether "a convnet appeared";
it tabulates what the host measured: the invariant, unsourced choices, path marks, agreement, cost.
"""
import argparse
import json
import statistics
from pathlib import Path
from .team import ROOT
from .lenet_m3 import live, ROLE_DOCS

VARIANTS=json.loads((ROOT/'research/lit-1988-variants/register.json').read_text())
CONDITIONS={
 'C0':{'corpus':False},                                   # no corpus for LeCun: leakage baseline
 'C1':{},                                                 # default
 'A1':{'drop':{'coordinator':['RHW86-TC']}},              # weight tying without the T-C problem
 'A2':{'drop':{r:['DENKER88'] for r in ROLE_DOCS}},       # no hand-designed pipeline paper anywhere
 'A3':{'compute_days':200.0,'max_compute_days':600.0},    # ten times the compute
 'A4':{'vocabulary':('avg',)},                            # averaging available from day 0
 'A5':{'drop':{'hinton':['FUKUSHIMA82']}},                # Hinton without Fukushima
 'A6':{'overrides':{'LECUN89TR':VARIANTS['LECUN89TR']}},  # Toronto report with the results table removed
}
# X1 (a non-digit task) needs another dataset and evaluator; it is not a setting of this task.


def run(condition,base,n,image,cache,model,start=1):
    outs=[]
    for i in range(start,start+n):
        folder=Path(base)/f'm4-{condition}-{i}'
        s=live(folder,image,cache,model,**CONDITIONS[condition]);s['condition']=condition
        (folder/'summary.json').write_text(json.dumps(s,indent=1,default=str));outs.append(s)
    return outs


def first_agreement_day(folder):
    """Day of the first endorsement (agreement), read from the event log; mail events carry the clock."""
    day=0.0
    for line in (Path(folder)/'events.jsonl').read_text().splitlines():
        e=json.loads(line)
        if e['kind']=='ledger_mail':day=e['data'].get('day',day)
        if e['kind']=='ledger_endorse':return day
    return None


def measure(folder):
    s=json.loads((Path(folder)/'summary.json').read_text());a=s['audit']
    patterns=sorted({v for n in s['nets'].values() for c,v in n['unsourced'] if c=='pattern'})
    return {'condition':s.get('condition','?'),'run':Path(folder).name,'invariant':a['invariant_holds'],
            'unsourced':a['unsourced_choices'],'choices':a['choices_total'],'unsourced_patterns':patterns,
            'path':s['path']['score'],'marks':s['path']['marks'],'agreed':len(a['agreed_claims']),'refuted':a['claims_by_status'].get('refuted',0),
            'test_beats_agreed':s['path']['marks'].get('agreed_test_beats_at_0.09',False),
            'avg_opened':any(f.get('granted')=='avg' for f in a['feature_requests']),'avg_used':any('avg' in n['pattern'] for k,n in s['nets'].items() if k!='PIPELINE88'),
            'meetings':len(s['meetings']),'demo':s['demo_day'] is not None,'letters':a['mail']['sent'],'rejected':a['mail']['rejected'],
            'first_agreement_day':first_agreement_day(folder),'end_day':round(s['day'],1),'calls':s['calls']}


def report(base):
    rows=[measure(p.parent) for p in sorted(Path(base).glob('m4-*/summary.json'))]
    by={}
    for r in rows:by.setdefault(r['condition'],[]).append(r)
    def ratio(r):return r['unsourced']/r['choices'] if r['choices'] else 0.0
    def mean(xs):return statistics.mean(xs) if xs else float('nan')
    lines=['# M4 report','','| condition | runs | invariant | unsourced ratio (mean) | unsourced patterns | path scores | agreed (mean) | test BEATS agreed | avg opened / used | meetings (mean) | demo | first agreement day | calls (mean) |','|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for c,rs in sorted(by.items()):
        fa=[r['first_agreement_day'] for r in rs if r['first_agreement_day'] is not None]
        lines.append(f"| {c} | {len(rs)} | {sum(r['invariant'] for r in rs)}/{len(rs)} | {mean([ratio(r) for r in rs]):.2f} | {', '.join(sorted({p for r in rs for p in r['unsourced_patterns']})) or '-'} | {[r['path'] for r in rs]} | {mean([r['agreed'] for r in rs]):.1f} | {sum(r['test_beats_agreed'] for r in rs)}/{len(rs)} | {sum(r['avg_opened'] for r in rs)} / {sum(r['avg_used'] for r in rs)} | {mean([r['meetings'] for r in rs]):.1f} | {sum(r['demo'] for r in rs)}/{len(rs)} | {mean(fa):.1f} | {mean([r['calls'] for r in rs]):.0f} |")
    lines+=['','## Runs','','| run | unsourced | path marks | agreed | refuted | letters (rejected) | end day | calls |','|---|---|---|---|---|---|---|---|']
    for r in rows:
        marks=''.join('1' if v else '0' for v in r['marks'].values())
        lines.append(f"| {r['run']} | {r['unsourced']}/{r['choices']} | {marks} | {r['agreed']} | {r['refuted']} | {r['letters']} ({r['rejected']}) | {r['end_day']} | {r['calls']} |")
    lines+=['','Path marks, in order: read_before_design, constraint_cited, small_before_large, budget_or_feature_driven, agreed_test_beats_at_0.09.',
            'Interpretation rule (PROPOSAL §8): no difference between conditions means the historical causal hypothesis is re-examined; zero failures everywhere is a leakage signal.']
    text='\n'.join(lines);(Path(base)/'report.md').write_text(text,encoding='utf-8');return text


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--condition',choices=sorted(CONDITIONS));p.add_argument('--runs',type=int,default=1);p.add_argument('--start',type=int,default=1)
    p.add_argument('--base',required=True);p.add_argument('--image',default='researchsquad-training:torch2.9.1-cu128');p.add_argument('--cache',default=str(Path.home()/'.cache/researchsquad/usps'))
    p.add_argument('--model',default=None);p.add_argument('--report',action='store_true')
    a=p.parse_args()
    if a.condition:
        for s in run(a.condition,a.base,a.runs,a.image,a.cache,a.model,a.start):print(json.dumps({k:s[k] for k in ('condition','calls','day','demo_day','meetings','path')},default=str))
    if a.report or not a.condition:print(report(a.base))
