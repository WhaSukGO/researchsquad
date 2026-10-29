"""Connect the configurable team to existing music inputs and protected scoring."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from .contracts import atomic_json,digest,success_gate
from .environments import EnvironmentManager
from .inputs import baseline_inventory
from .music import MusicScorer
from .team import Team,ROOT
from .team_evaluators import Evaluator


def music_evaluator(folder,spec,remaining=lambda:180):
    domain=MusicScorer(Path(folder)/'measurements',spec)
    domain.assert_originals()
    def score(snapshot,task):
        domain.assert_originals()
        eid='exp-'+digest(snapshot)[:12]
        target=domain.run_dir/'experiments'/eid
        target.mkdir(parents=True,exist_ok=True)
        for index,sample in domain.selected():
            out=target/f'sample-{index:03}';out.mkdir(exist_ok=True)
            text=snapshot.get(f'sample-{index:03}.krn','')
            if not isinstance(text,str):raise ValueError('Prediction must be text')
            prediction=out/'prediction.krn';prediction.write_text(text)
            atomic_json(out/'trace.json',{'status':'ok' if text.strip() else 'missing',
                'output':str(prediction.resolve()),'output_sha256':hashlib.sha256(prediction.read_bytes()).hexdigest()})
        atomic_json(target/'receipt.json',{'source':'sealed generic-team snapshot','snapshot_hash':digest(snapshot)})
        measured=domain.evaluate(eid,remaining)
        # Stable sample aliases, never reference sequences, enter the team context.
        public={k:v for k,v in measured.items() if k!='per_sample'}
        public['per_sample']=[{**{k:v for k,v in row.items() if k!='id'},'sample':f'sample-{index:03}'}
                              for (index,_),row in zip(domain.selected(),measured['per_sample'])]
        return {'accepted':success_gate(measured,spec),**public}
    version=digest({'adapter':Path(__file__).read_text(),'spec':spec,'manifest':domain.manifest})
    def finalize(measured,external):
        # Scoped human attestations never replace protected numeric scoring.
        measured['chord_timing_audited']=external.get('chord-timing-audit',{}).get('verdict')=='PASS'
        measured['musician_accepted']=external.get('musician-review',{}).get('verdict')=='PASS'
        measured['accepted']=success_gate(measured,spec)
        return measured
    return Evaluator('music-protected-'+version,score,finalize),domain


def task_inputs(domain):
    selected=domain.selected();assets={}
    for index,sample in selected:assets[f'images/sample-{index:03}.png']=str(ROOT/sample['image'])
    for entry in baseline_inventory(selected):assets[entry['path']]=str(ROOT/entry['source'])
    brief=f'''Run a real music-transcription study on the {len(selected)} supplied development excerpts.
The goal is editable kern with melody and chord symbols. References stay with the protected evaluator.
Read delivered-baseline.json for the directly scored supplied kern files; baseline.json contains historical engine scores and is not an identical artifact comparison. Use the explicitly supplied prediction files when preserving baseline melody.
The image and prediction paths are listed in the assignment inventory; delegate the actual files your engineer needs.
Use the actual environment capability inventory. Verify Python, Pillow, music21, converter21, Verovio and Tesseract before depending on them; request an environment when missing. Register converter21 before Humdrum import/export. Audiveris is not installed by this wrapper; its existing predictions and raw MusicXML exports are provided.
Choose a specific, measurable intervention. Evaluate the first submitted candidate, then use its measurements to refine it or try another feasible approach. Preserve the strongest measured candidate, and explain any decision to stop.
Each evaluated owner must submit {len(selected)} text artifacts named sample-NNN.krn at workspace root, plus source and a short report. Use submit_report.files to list them; unsubmitted files are not part of the scored candidate. Preserve provenance when reusing predictions. The required sample numbers are in samples.json. A submitted file should have **kern melody and **mxhm harmony, tab-separated rows, with matched terminators. Chords use root:quality[/bass]. Missing files count as failures. Do not invent notes or use evaluation answers.
Use request_environment for missing capabilities. Tool registration and extra specialists are optional; choose them only if useful. Do not spend the entire pilot making a new runtime.
This is development material, not held-out accuracy. Full acceptance requires all 32 samples plus explicit chord-timing audit and musician review. A smaller scope cannot complete that goal. Only matching trusted operator events supply those final human verdicts. Finish with measured deltas, limitations and next steps, even if the goal is unmet.
'''
    return assets,{'brief.txt':brief,'samples.json':json.dumps([f'sample-{i:03}' for i,_ in selected]),
                   'baseline.json':json.dumps(domain.baseline_summary())}


def run(folder,model='gpt-6.1-sol',*,unlimited=False,agents_dir=None,workflow_spec='research',
        completion_stage=None,sample_scope='all',external_event=None,resume_stopped=None,retry_action=None,retry_reason=None):
    folder=Path(folder).resolve()
    spec=json.loads((ROOT/'goals/music-research-v2.json').read_text())
    if sample_scope not in {'all','first_per_song'}:raise ValueError('Unknown music sample scope')
    spec['budget']['experiment_sample_scope']=sample_scope
    evaluator,domain=music_evaluator(folder,spec)
    assets,inputs=task_inputs(domain)
    baseline_snapshot={f"sample-{r['sample']:03}.krn":(ROOT/r['source']).read_text()
                       for r in baseline_inventory(domain.selected()) if r['path'].endswith('.krn')}
    baseline=evaluator(baseline_snapshot,{})
    atomic_json(folder/'delivered-baseline.json',baseline)
    inputs['delivered-baseline.json']=json.dumps(baseline)
    evaluator,domain=music_evaluator(folder,spec,lambda:team.remaining())
    task={'goal':spec['goal'],'acceptance':spec['acceptance'],'evaluator':'music','network':True,
          'assets':assets,'inputs':inputs,'unlimited':unlimited,
          'submission_outputs':[f'sample-{i:03}.krn' for i,_ in domain.selected()],
          'budget':{'max_calls':80,'max_seconds':3600,'max_assignments':80,'max_depth':2}}
    if workflow_spec:
        path=ROOT/'workflows'/f'{workflow_spec}.json' if workflow_spec in {'research','product'} else Path(workflow_spec)
        task['workflow']=json.loads(path.read_text())
        if completion_stage:task['workflow']['completion_stage']=completion_stage
        if task['workflow'].get('policy_version')==2:
            for stage in task['workflow']['stages']:
                if stage['id']=='R1':stage['required_candidates']=['HOMR','Audiveris']
            task['workflow']['stages'][-1]['gates'] += [
                {'id':'chord-timing-audit','kind':'external','criterion':'Original scoped chord-onset timing audit of this candidate'},
                {'id':'musician-review','kind':'external','criterion':'Musician acceptance of this frozen candidate and workflow'}]
    team=Team(folder,task,model=model,agents_dir=agents_dir,evaluators={'music':evaluator})
    atomic_json(folder/'pilot-plan.json',{'model':model,'scope':f'{len(domain.selected())} development excerpts ({sample_scope})','fresh_state':True,
        'new_team_runtime':True,'decisions':'live model, not scripted','baseline_predictions_delivered':len(baseline_inventory(domain.selected())),
        'reference_labels_delivered':0,'budget':team.task['budget'],'unlimited':unlimited,'comparison_limit':'Different architecture and total budget from old runs; not a controlled causal ablation.'})
    # Deterministic readiness reuses the reviewed profile; no setup model is needed on a cache hit.
    if team.state['environment'] is None and not team.managed:
        class NoSetupModel:
            def call(self,*args,**kwargs):raise RuntimeError('Automatic bootstrap repair unavailable; delegate an environment engineer')
        manager=EnvironmentManager(folder/'bootstrap',{'max_attempts':1,'max_model_calls':1,'max_seconds':180},spec['worker'],NoSetupModel())
        started=time.monotonic()
        receipt=manager.ensure(lambda:None,lambda:180-(time.monotonic()-started))
        team.state['active_seconds']+=time.monotonic()-started
        if receipt['status']=='ready':
            team.state['environment']={'status':'ready','image':receipt['image']['id'],'packages':manager.state['active_recipe'],
                                       'readiness':receipt,'scope':'Prepared Python notation and OCR; no Audiveris runtime'}
        team.record('bootstrap',receipt);team.save()
    from .operator_controls import apply_controls
    apply_controls(team,external_event=external_event,resume_stopped=resume_stopped,
                   retry_action=retry_action,retry_reason=retry_reason)
    result=team.run()
    atomic_json(folder/'outcome.json',{'outcome':result,'goal_met':team.state['goal_met'],'calls':team.state['calls'],
                                     'evaluations':team.state['evaluations'],'active_seconds':team.state['active_seconds']})
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True);parser.add_argument('--model',default='gpt-6.1-sol')
    budgets=parser.add_mutually_exclusive_group()
    budgets.add_argument('--unlimited',action='store_true',help='Explicitly remove effort limits')
    budgets.add_argument('--bounded',action='store_true',help='Use the finite default effort limits')
    parser.add_argument('--agents-dir');parser.add_argument('--workflow',default='research')
    parser.add_argument('--completion-stage')
    parser.add_argument('--sample-scope',choices=['all','first_per_song'],default='all')
    parser.add_argument('--external-event');parser.add_argument('--resume-stopped')
    parser.add_argument('--retry-action');parser.add_argument('--retry-reason')
    args=parser.parse_args()
    print(json.dumps(run(args.run_dir,args.model,unlimited=args.unlimited,agents_dir=args.agents_dir,
        workflow_spec=args.workflow,completion_stage=args.completion_stage,sample_scope=args.sample_scope,
        external_event=args.external_event,resume_stopped=args.resume_stopped,
        retry_action=args.retry_action,retry_reason=args.retry_reason)))
