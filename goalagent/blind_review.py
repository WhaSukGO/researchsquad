"""Blind review -> seal the complete batch -> deterministic reference scoring.

The review process never loads the dataset manifest, reference files, old scores,
or controller history. The scorer runs only after every output is committed.
This enforces model-input separation; it is not an OS confidentiality sandbox.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from .contracts import atomic_json, digest
from .provider import CodexProvider, run_process
from .roles import role_prompt, public_roles

REVIEW_FORMAT = '''The candidate uses exactly two tab-separated spines: **kern and **mxhm.
Chord labels use root:quality[/bass]; qualities maj, min, 7, maj7, min7, min6, dim7, sus4, add9.
Compare every visible note, rest, accidental, duration, tie/slur and chord change with the image.
Ground any proposed change in a visible location. Check chord placement as well as chord spelling.
Do not assume the candidate contains mistakes. Do not invent notes to complete a cropped measure.
Keep correct content. Do not change a symbol merely because another reading seems more musical.
Return verdict keep/revise/abstain, complete kern, findings, and uncertainties.
For keep or abstain return the candidate byte-for-byte. For revise make only visually supported edits.
Findings are brief observable evidence, not private reasoning. If ambiguous, state it for human review.'''

REVIEW_SCHEMA = {
    'type':'object', 'additionalProperties':False,
    'properties':{
        'verdict':{'type':'string','enum':['keep','revise','abstain']},
        'kern':{'type':'string'},
        'findings':{'type':'array','items':{
            'type':'object','additionalProperties':False,
            'properties':{k:{'type':'string'} for k in ['category','location','observation','change']},
            'required':['category','location','observation','change']}},
        'uncertainties':{'type':'array','items':{'type':'string'}}},
    'required':['verdict','kern','findings','uncertainties']}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def validate_review(answer, candidate):
    if set(answer) != set(REVIEW_SCHEMA['required']):raise ValueError('Review output fields violate contract')
    if answer['verdict'] not in ['keep','revise','abstain']:raise ValueError('Unknown review verdict')
    if not isinstance(answer['kern'],str) or not answer['kern'].strip() or len(answer['kern'])>100000:
        raise ValueError('Invalid or oversized transcription')
    if answer['verdict'] != 'revise' and answer['kern'] != candidate:
        raise ValueError('Keep/abstain cannot silently change the candidate')
    if not isinstance(answer['uncertainties'],list) or not all(isinstance(v,str) for v in answer['uncertainties']):
        raise ValueError('Invalid uncertainties')
    if not isinstance(answer['findings'],list):raise ValueError('Invalid findings')
    for finding in answer['findings']:
        if (not isinstance(finding,dict) or set(finding)!={'category','location','observation','change'}
                or not all(isinstance(v,str) and v.strip() for v in finding.values())):
            raise ValueError('Findings require visible evidence and location')
    if answer['verdict']=='revise' and not answer['findings']:
        raise ValueError('Revision requires evidence')


def prepare(source, run_dir, model):
    """Import pixels and previously committed predictions, never reference data."""
    source, run_dir = Path(source).resolve(), Path(run_dir).resolve()
    if run_dir.exists():raise ValueError('Use a new run directory; existing experiments cannot be overwritten')
    if not (source/'receipt.json').exists():raise ValueError('Source batch must have completed')
    samples=[]
    for old in sorted(source.glob('sample-*')):
        pred, image = old/'prediction.krn', old/'input.png'
        trace=read(old/'trace.json')
        if not pred.exists() or sha(pred)!=trace.get('output_sha256'):
            raise ValueError('Source prediction is missing or changed')
        if not image.exists() or sha(image)!=trace.get('source_image_sha256'):
            raise ValueError('Source image changed')
        samples.append((pred,image))
    if not samples:raise ValueError('No source samples')
    run_dir.mkdir(parents=True)
    public=[]
    for index,(pred,image) in enumerate(samples,1):
        sid=f'case-{index:03}'
        out=run_dir/'cases'/sid;out.mkdir(parents=True)
        shutil.copyfile(pred,out/'candidate.krn');shutil.copyfile(image,out/'input.png')
        public.append({'id':sid,'candidate_sha256':sha(pred),'image_sha256':sha(image)})
    protocol={'version':1,'system_goal':'Reduce musician correction work while preserving melody, harmony and transposition.',
              'experiment_goal':'Test whether one independent blind review improves frozen transcriptions without introducing errors.',
              'hypothesis':'Image-grounded review reduces measured errors; unchanged or worse outputs contradict the benefit.',
              'model':model,'effort':'high','source_batch':str(source),
              'sample_policy':'Every supplied source prediction, including previously correct cases; no filtering by accuracy.',
              'data_status':'Development diagnostic; previously inspected songs are not a held-out test.',
              'roles':public_roles(),'review_prompt_sha256':digest(REVIEW_FORMAT),'schema_sha256':digest(REVIEW_SCHEMA),
              'budget':{'max_model_calls':len(samples),'max_active_seconds':1800,'call_timeout':240},
              'score_release':'Only after all case outputs are frozen; no further model calls in this run.',
              'boundary':'Fresh tool-disabled model contexts; application data-flow enforcement, not OS-level read isolation.'}
    atomic_json(run_dir/'public-inputs.json',public);atomic_json(run_dir/'protocol.json',protocol)
    atomic_json(run_dir/'state.json',{'phase':'reviewing','attempted':[],'model_calls':0,'active_seconds':0,
                                    'protocol_sha256':sha(run_dir/'protocol.json'),'inputs_sha256':sha(run_dir/'public-inputs.json')})
    return run_dir


def verify_inputs(run_dir, state):
    for name,key in [('protocol.json','protocol_sha256'),('public-inputs.json','inputs_sha256')]:
        if sha(run_dir/name)!=state[key]:raise ValueError('Protocol/input manifest changed')
    for sample in read(run_dir/'public-inputs.json'):
        out=run_dir/'cases'/sample['id']
        if sha(out/'candidate.krn')!=sample['candidate_sha256'] or sha(out/'input.png')!=sample['image_sha256']:
            raise ValueError('Public input changed')


def review(run_dir, provider=None, charge_model=None, remaining_seconds=None):
    """No reference-file parameter and no import of evaluation modules in this phase."""
    run_dir=Path(run_dir).resolve()
    with (run_dir/'run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=read(run_dir/'state.json');verify_inputs(run_dir,state)
        if state['phase']!='reviewing':return state
        protocol=read(run_dir/'protocol.json')
        if digest(REVIEW_FORMAT)!=protocol['review_prompt_sha256'] or digest(REVIEW_SCHEMA)!=protocol['schema_sha256']:
            raise ValueError('Reviewer prompt/schema changed: start a new development experiment')
        provider=provider or CodexProvider(protocol['model'],effort='high')
        if provider.model!=protocol['model']:raise ValueError('Reviewer model changed')
        started=time.monotonic();previous_active=state['active_seconds']
        for sample in read(run_dir/'public-inputs.json'):
            sid=sample['id'];out=run_dir/'cases'/sid
            if (out/'review.json').exists():continue
            candidate=(out/'candidate.krn').read_text()
            try:
                if sid in state['attempted']:raise RuntimeError('Interrupted attempt: no silent extra model call; retained original')
                remaining=protocol['budget']['max_active_seconds']-previous_active-(time.monotonic()-started)
                if remaining_seconds:remaining=min(remaining,remaining_seconds())
                if remaining<1 or state['model_calls']>=protocol['budget']['max_model_calls']:
                    raise RuntimeError('Review budget exhausted; retained original')
                if charge_model:charge_model()
                state['attempted'].append(sid);state['model_calls']+=1
                state['active_seconds']=previous_active+time.monotonic()-started
                atomic_json(run_dir/'state.json',state)
                prompt=role_prompt('reviewer',{'candidate':candidate,'format':REVIEW_FORMAT})
                answer,metadata=provider.call(prompt,REVIEW_SCHEMA,out/'model',image=out/'input.png',
                                              timeout=min(protocol['budget']['call_timeout'],remaining))
                if metadata.get('unexpected_tool_events'):raise ValueError('Reviewer attempted a tool')
                validate_review(answer,candidate)
                record={'status':'ok','answer':answer,'metadata':metadata}
            except Exception as error:
                record={'status':'error','error':repr(error),'answer':{'verdict':'abstain','kern':candidate,
                        'findings':[],'uncertainties':['Review failed; original retained, not verified.']}}
            (out/'prediction.krn').write_text(record['answer']['kern'])
            atomic_json(out/'review.json',record)
            print(json.dumps({'case':sid,'status':record['status'],'verdict':record['answer']['verdict']}),flush=True)
        verify_inputs(run_dir,state)
        seal={'protocol_sha256':state['protocol_sha256'],'inputs_sha256':state['inputs_sha256'],
              'samples':[{'id':s['id'],'prediction_sha256':sha(run_dir/'cases'/s['id']/'prediction.krn'),
                          'review_sha256':sha(run_dir/'cases'/s['id']/'review.json')}
                         for s in read(run_dir/'public-inputs.json')],
              'sealed_at_unix':time.time(),'model_calls':state['model_calls']}
        atomic_json(run_dir/'seal.json',seal)
        state.update(phase='sealed',seal_sha256=sha(run_dir/'seal.json'),active_seconds=previous_active+time.monotonic()-started)
        atomic_json(run_dir/'state.json',state)
        return state


def verify_seal(run_dir):
    run_dir=Path(run_dir);state=read(run_dir/'state.json')
    if state['phase'] not in ['sealed','scored']:raise ValueError('Scoring is forbidden until the whole batch is sealed')
    verify_inputs(run_dir,state)
    if sha(run_dir/'seal.json')!=state['seal_sha256']:raise ValueError('Seal changed')
    seal=read(run_dir/'seal.json')
    for sample in seal['samples']:
        out=run_dir/'cases'/sample['id']
        if sha(out/'prediction.krn')!=sample['prediction_sha256'] or sha(out/'review.json')!=sample['review_sha256']:
            raise ValueError('Frozen review/prediction changed')
    return seal


def score(run_dir, manifest_path):
    """Trusted scorer: references are opened only after verify_seal succeeds."""
    from scorebench.run import ROOT
    from scorebench.metrics import parse_events,kern_melody_only,reference_chords,sequence_metrics
    from scorebench.evaluate import aggregate,freeze
    from .timing import timed_chords, VERSION
    run_dir=Path(run_dir).resolve()
    with (run_dir/'run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        seal=verify_seal(run_dir)
        if (run_dir/'results.json').exists():return read(run_dir/'results.json')
        manifest=read(manifest_path);mapping={s['image_sha256']:s for s in manifest}
        rows=[]
        for public in read(run_dir/'public-inputs.json'):
            s=mapping[public['image_sha256']];out=run_dir/'cases'/public['id']
            if sha(ROOT/s['reference'])!=s['reference_sha256']:raise ValueError('Reference changed')
            ref=(ROOT/s['reference']).read_text()
            ref_notes=parse_events(kern_melody_only(ref),'humdrum')[0];ref_chords=reference_chords(ref)
            row={'case':public['id'],'sample':s['id'],'review':read(out/'review.json')}
            for arm,file in [('before','candidate.krn'),('after','prediction.krn')]:
                inspect_path=out/(arm+'-inspection.json')
                code,stdout,stderr=run_process([sys.executable,'-m','goalagent.inspect',str(out/file),str(inspect_path)],cwd=ROOT,timeout=20)
                (out/(arm+'-inspection.log')).write_text(stdout+stderr)
                inspection=read(inspect_path) if code==0 else {'events':[],'chords':[],'parse_ok':False,'errors':['Parser failed']}
                row[arm]={'melody':sequence_metrics(ref_notes,[freeze(x) for x in inspection['events']]),
                          'chords':sequence_metrics(ref_chords,[freeze(x) for x in inspection['chords']]),
                          'parse_ok':inspection['parse_ok'],'parse_errors':inspection['errors']}
                try:
                    row[arm]['timed_chords']=sequence_metrics(timed_chords(ref),timed_chords((out/file).read_text()))
                except (ValueError,StopIteration,IndexError) as error:
                    row[arm]['timed_chords']={'unscorable':str(error)}
            rows.append(row)
        summary={arm:{key:aggregate([r[arm] for r in rows],key) for key in ['melody','chords']} for arm in ['before','after']}
        for arm in summary:
            eligible=[r[arm] for r in rows if 'errors' in r['before']['timed_chords'] and 'errors' in r['after']['timed_chords']]
            summary[arm]['timed_chords']=aggregate(eligible,'timed_chords') if eligible else None
            summary[arm]['timing_scorable_samples']=len(eligible)
            summary[arm]['parseable']=sum(r[arm]['parse_ok'] for r in rows)
        def count(row,arm):return row[arm]['melody']['errors']+row[arm]['chords']['errors']
        result={'version':1,'seal_sha256':sha(run_dir/'seal.json'),'timing_metric':VERSION,
                'metric_code_sha256':{str(p):sha(ROOT/p) for p in ['scorebench/metrics.py','goalagent/timing.py','goalagent/blind_review.py']},
                'samples':len(rows),'summary':summary,'rows':rows,
                'comparison':{'improved_samples':sum(count(r,'after')<count(r,'before') for r in rows),
                              'worsened_samples':sum(count(r,'after')>count(r,'before') for r in rows),
                              'unchanged_samples':sum(count(r,'after')==count(r,'before') for r in rows),
                              'originally_exact_samples_regressed':sum(count(r,'before')==0 and count(r,'after')>0 for r in rows)},
                'review_failures':sum(r['review']['status']!='ok' for r in rows),
                'limits':['Development pilot, not held-out accuracy; labels were seen during prior development.',
                          'All outputs were frozen before this scorer loaded references; no answer feedback to the reviewer.',
                          'Same underlying model in two roles: independence of context does not ensure independence of errors.',
                          'Timed chords checked only where explicit rhythmic rows permit it; labels are not musician-audited.',
                          'Model confidence and blank uncertainty lists are not correctness certificates.']}
        verify_seal(run_dir)
        atomic_json(run_dir/'results.json',result)
        state=read(run_dir/'state.json');state['phase']='scored';atomic_json(run_dir/'state.json',state)
        return result


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','review','score'])
    p.add_argument('--run-dir',required=True);p.add_argument('--source');p.add_argument('--model')
    p.add_argument('--manifest',default='research/manifest.json');args=p.parse_args()
    if args.action=='prepare':
        if not args.source:p.error('--source is required for prepare')
        prepare(args.source,args.run_dir,CodexProvider(args.model).model)
    elif args.action=='review':review(args.run_dir)
    else:
        result=score(args.run_dir,args.manifest)
        print(json.dumps({'summary':result['summary'],'comparison':result['comparison']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
