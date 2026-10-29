"""Protected music scoring and parser checks for the configurable team.

Candidate implementations belong to agents. This module only inspects and measures
frozen predictions; historical fixed-menu recognition runners have been retired.
"""
from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path
from scorebench.metrics import parse_events, kern_melody_only, reference_chords, sequence_metrics, transpose_reference_dialect
from scorebench.evaluate import aggregate, freeze
from scorebench.run import ROOT
from .contracts import atomic_json
from .provider import run_process
from .inputs import BASELINE_ROOT



def inspect_prediction(path):
    """Run in an isolated worker; unsupported harmonies are errors, never silently dropped."""
    from scorebench.inspect_prediction import inspect
    path=Path(path)
    if path.suffix!='.krn':return inspect(path)
    text=path.read_text();out={'events':[],'chords':[],'parse_ok':False,'render_ok':False,'errors':[]}
    try:
        out['events'],out['parser_warnings']=parse_events(kern_melody_only(text),'humdrum')
        out['parse_ok']=True
    except Exception as e:out['errors'].append('melody: '+repr(e))
    try:out['chords']=reference_chords(text)
    except Exception as e:out['errors'].append('chords: '+repr(e))
    try:
        import verovio
        tk=verovio.toolkit();tk.setOptions({'inputFrom':'humdrum','pageWidth':2200,'pageHeight':800,'scale':40,'adjustPageHeight':True})
        if tk.loadData(text):
            svg=tk.renderToSVG(1);(path.parent/'prediction.svg').write_text(svg)
            out['render_ok']='class="note"' in svg or 'class="rest"' in svg
    except Exception as e:out['errors'].append('render: '+repr(e))
    return out

def transpose_check(path):
    import music21 as m21
    text=Path(path).read_text();shifted=transpose_reference_dialect(text,'M2')
    a=parse_events(kern_melody_only(text),'humdrum')[0]
    b=parse_events(kern_melody_only(shifted),'humdrum')[0]
    ca,cb=reference_chords(text),reference_chords(shifted)
    def raised(x,y):
        return x==y if x=='REST' else m21.pitch.Pitch(y).midi-m21.pitch.Pitch(x).midi==2
    good=len(a)==len(b) and len(ca)==len(cb)
    good=good and all(da==db and len(pa)==len(pb) and all(raised(x,y) for x,y in zip(pa,pb)) for (pa,da),(pb,db) in zip(a,b))
    # Chord labels have pitch classes, not octaves: B -> C# wraps modulo 12.
    def raised_class(x,y):return (m21.pitch.Pitch(y).pitchClass-m21.pitch.Pitch(x).pitchClass)%12==2
    good=good and all(raised_class(x[0],y[0]) and raised_class(x[2],y[2]) and x[1]==y[1] and x[3]==y[3] for x,y in zip(ca,cb))
    if not good:raise ValueError('Independent interval/rhythm/harmony checks failed')
    target=Path(path).with_name('transposed-M2.krn');target.write_text(shifted)
    return str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target)

class MusicScorer:
    def __init__(self, run_dir, spec):
        self.run_dir = Path(run_dir)
        self.spec = spec
        self.manifest = json.loads((ROOT / 'research/manifest.json').read_text())
        self.baseline = json.loads((BASELINE_ROOT / 'results.json').read_text())


    def assert_originals(self):
        for sample in self.manifest:
            for name in ['image','reference']:
                if hashlib.sha256((ROOT/sample[name]).read_bytes()).hexdigest()!=sample[name+'_sha256']:
                    raise ValueError('Original data integrity violation: '+sample['id'])

    def selected(self):
        if self.spec['budget']['experiment_sample_scope']=='all':return list(enumerate(self.manifest,1))
        seen=set();rows=[]
        for i,s in enumerate(self.manifest,1):
            if s['song'] not in seen:rows.append((i,s));seen.add(s['song'])
        return rows

    def baseline_summary(self):
        chosen={s['id'] for _,s in self.selected()};out={}
        for engine in self.baseline['summary']:
            rows=[r for r in self.baseline['results'] if r['engine']==engine and r['id'] in chosen]
            out[engine]={'samples':len(rows),'melody':aggregate(rows,'melody'),'chords':aggregate(rows,'chords'),
                         'failure_flags':dict(Counter(f for r in rows for f in r['failure_flags']))}
        return {'id':'baseline','paired_subset':out,'all_32':{e:{'melody_error_rate':s['melody']['error_rate'],'chord_matches':s['chords']['matches']} for e,s in self.baseline['summary'].items()},
                'limits':self.baseline['limits']}


    def evaluate(self,eid,remaining_seconds):
        if not re.fullmatch(r'exp-[0-9a-f]{12}',eid):raise ValueError('Invalid experiment ID')
        folder=self.run_dir/'experiments'/eid
        if not (folder/'receipt.json').exists():raise ValueError('Experiment must finish before evaluation')
        summary_path=folder/'evaluation.json'
        if summary_path.exists():return json.loads(summary_path.read_text())
        rows=[];transpose_failures=0;transpose_checked=0
        for index,sample in self.selected():
            out=folder/f'sample-{index:03}';trace=json.loads((out/'trace.json').read_text())
            inspection={'events':[],'chords':[],'parse_ok':False,'render_ok':False,'errors':[]}
            if trace.get('output'):
                pred=ROOT/trace['output']
                if hashlib.sha256(pred.read_bytes()).hexdigest()!=trace['output_sha256']:raise ValueError('Prediction integrity violation')
                inspection_path=out/'inspection.json'
                try:
                    code,stdout,stderr=run_process([sys.executable,'-m','goalagent.inspect',str(pred),str(inspection_path)],cwd=ROOT,timeout=min(20,remaining_seconds()))
                    (out/'inspection.log').write_text(stdout+stderr)
                    if code==0:inspection=json.loads(inspection_path.read_text())
                    else:inspection['errors'].append('Parser worker failed')
                except Exception as e:inspection['errors'].append(repr(e))
                if pred.suffix=='.krn' and inspection['parse_ok']:
                    transpose_checked+=1
                    try:trace['transposed']=transpose_check(pred)
                    except Exception as e:transpose_failures+=1;inspection['errors'].append('transpose: '+repr(e))
            reference=(ROOT/sample['reference']).read_text()
            notes,_=parse_events(kern_melody_only(reference),'humdrum');chords=reference_chords(reference)
            row={'id':sample['id'],'song':sample['song'],'sample_index':index,'trace':trace,'inspection':inspection,
                 'melody':sequence_metrics(notes,[freeze(x) for x in inspection['events']]),
                 'chords':sequence_metrics(chords,[freeze(x) for x in inspection['chords']])}
            rows.append(row)
        chosen={r['id'] for r in rows}
        comparison={}
        for engine in self.baseline['summary']:
            base=[r for r in self.baseline['results'] if r['engine']==engine and r['id'] in chosen]
            comparison[engine]={k:aggregate(base,k) for k in ['melody','chords']}
        result={'id':eid+'-evaluation','experiment_id':eid,'samples':len(rows),'parseable':sum(r['inspection']['parse_ok'] for r in rows),
                'melody':aggregate(rows,'melody'),'chords':aggregate(rows,'chords'),
                'exact_measured':sum(r['melody']['errors']==0 and r['chords']['errors']==0 and r['inspection']['parse_ok'] for r in rows),
                'transposition_checked':transpose_checked,'transposition_failures':transpose_failures if transpose_checked==len(rows) else None,
                'chord_timing_audited':False,'musician_accepted':False,'paired_baselines':comparison,
                'per_sample':[{'id':r['id'],'melody_errors':r['melody']['errors'],'chord_errors':r['chords']['errors'],'parse_ok':r['inspection']['parse_ok'],'uncertainties':r['trace'].get('uncertainties',[])} for r in rows],
                'limits':['Development pilot, not held-out performance.','Chord labels scored in order; beat timing unmeasured.','Reference files are supplied labels, not musician-audited gold.','Transposition, when checked, only covers an upward major second.']}
        atomic_json(folder/'detailed-results.json',rows);atomic_json(summary_path,result)
        return result
