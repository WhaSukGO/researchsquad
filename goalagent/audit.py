"""Deterministic checks on a completed or checkpointed live agent run."""
import argparse,hashlib,json
from pathlib import Path
from .contracts import atomic_json,success_gate,validate_decision
from scorebench.run import ROOT


def audit(folder):
    folder=Path(folder);s=json.loads((folder/'state.json').read_text());met=success_gate(s['evaluations'].get(s['best_experiment']),s['goal'])
    metadata=[json.loads(p.read_text()) for p in folder.rglob('metadata.json')]
    tokens={k:sum(m.get('usage',{}).get(k,0) for m in metadata) for k in ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens']}
    known=['goal']+[x['id'] for x in s.get('external_evidence',[])];invalid=[]
    for r in s['history']:
        if r.get('decision'):
            try:
                decision=r['decision']
                if s.get('architecture')=='research-coordinator-v1' and decision['tool']=='read_record':
                    decision={**decision,'tool':'read_evidence'}
                validate_decision(decision,known)
            except ValueError as err:invalid.append({'step':r['step'],'error':str(err)})
        obs=r['observation'];known.append(obs['id'])
        if (r.get('decision') or {}).get('tool')=='read_evidence':known += [x['id'] for x in obs.get('sources',[])]
    manifest=json.loads((ROOT/'research/manifest.json').read_text())
    changed=[smp[field] for smp in manifest for field in ['image','reference'] if hashlib.sha256((ROOT/smp[field]).read_bytes()).hexdigest()!=smp[field+'_sha256']]
    checks={'all_executed_decisions_schema_and_citations_valid':not invalid,'completion_gate_consistent':s['goal_met']==met,
            'steps_within_budget':s['steps']<=s['goal']['budget']['max_steps'],
            'model_calls_within_budget':s['model_calls']<=s['goal']['budget']['max_model_calls'],
            'experiments_within_budget':len(s['experiments'])<=s['goal']['budget']['max_experiments'],
            'original_files_unchanged':not changed,'no_unexpected_model_side_tools':all(not m.get('unexpected_tool_events') for m in metadata)}
    if s.get('architecture')=='research-coordinator-v1':
        from .research import ResearchTools,sha
        from .contracts import digest
        try:
            domain=ResearchTools(folder,s['goal'])
            domain.assert_originals()
            for eid in s['experiments']:
                experiment=folder/'experiments'/eid
                if not (experiment/'receipt.json').exists():continue
                seal=domain.verify_seal(experiment)
                if eid in s['evaluations']:
                    evaluation=experiment/'evaluation.json'
                    proof=json.loads((experiment/'evaluation-attestation.json').read_text())
                    if proof!={'seal_hash':digest(seal),'evaluation_hash':sha(evaluation.read_bytes())}:
                        raise ValueError('Evaluation attestation mismatch')
                    if json.loads(evaluation.read_text())!=s['evaluations'][eid]:
                        raise ValueError('State evaluation mismatch')
            for record in s['history']:
                key=f'{record["step"]:03}-{digest(record)[:12]}'
                if json.loads((folder/'evidence'/f'{key}.json').read_text())!=record:
                    raise ValueError('Evidence record mismatch')
            checks['protected_research_artifacts_intact']=True
        except (OSError,ValueError,KeyError):
            checks['protected_research_artifacts_intact']=False
    checkpoint=folder/'checkpoint-before-resume.json'
    if checkpoint.exists():
        before=json.loads(checkpoint.read_text())
        checks['pre_resume_history_preserved']=before['observations']==[r['observation']['id'] for r in s['history'][:len(before['observations'])]]
        checks['pre_resume_steps_not_duplicated']=len({r['step'] for r in s['history']})==len(s['history'])
    result={'type':'live_run_process_audit','status':s['status'],'goal_met':s['goal_met'],'checks':checks,'all_checks_passed':all(checks.values()),
            'decisions':len(s['history']),'invalid_decision_attempts':sum(r.get('decision') is None for r in s['history']),
            'tool_error_observations':sum(bool(r['observation'].get('error')) for r in s['history']),
            'model_calls_reserved_or_attempted':s['model_calls'],'completed_model_receipts':len(metadata),'tokens':tokens,
            'active_seconds':s['active_seconds'],'evaluated_experiments':len(s['evaluations']),
            'limits':['Process checks do not prove musical correctness or calibrated confidence.','Citation IDs are checked, not semantic support of every claim.','Reserved calls can exceed completed receipts after failure. Monetary billing unavailable.'],
            'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'goalagent').glob('*.py')}}
    atomic_json(folder/'agent-evaluation.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',nargs='?',default='runs/goal-agent-001');args=p.parse_args();print(json.dumps(audit(ROOT/args.folder),ensure_ascii=False,indent=2))
