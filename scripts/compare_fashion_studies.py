"""Offline observable-run comparison. Never executes experiment source."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

READS={'read_file','read_job_output','read_evidence','read_artifact'}

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def summarize(folder):
    folder=Path(folder);state=load(folder/'team-state.json')
    spans=[load(p) for p in (folder/'traces').glob('*.json')]
    start=min(datetime.fromisoformat(r['started_at']) for r in spans)
    end=max(datetime.fromisoformat(r.get('ended_at',r['started_at'])) for r in spans)
    returned=[r for r in spans if r['kind']=='model' and (r.get('output') or {}).get('selected_action')]
    tools=Counter();roles={};errors=[];repeat_resources=0;repeat_windows=0;read_calls=0;decisions=[]
    for f in sorted((folder/'agents').glob('*/worker-state.json')):
        aid=f.parent.name;a=load(f);entry=state['assignments'].get(aid,{})
        role=entry.get('agent','coordinator' if aid=='lead' else aid)
        row=roles.setdefault(role,{'returned_actions':0,'read_calls':0,'exact_repeat_reads':0,'actions':Counter()})
        seen=set();windows=set()
        for h in a['history']:
            tool=h['tool'];obs=h.get('observation') or {}
            if isinstance(obs,dict) and 'error' in obs:
                errors.append({'role':role,'assignment':aid,'step':h.get('step'),'tool':tool,'detail':obs})
            if tool=='model':continue
            tools[tool]+=1;row['actions'][tool]+=1;row['returned_actions']+=1
            if tool=='record_decision':decisions.append({'role':role,'step':h['step'],**json.loads(h['argument'])})
            if tool not in READS or 'error' in obs:continue
            read_calls+=1;row['read_calls']+=1
            raw=h.get('argument','')
            try:arg=json.loads(raw)
            except (ValueError,TypeError):arg={'id':raw}
            if not isinstance(arg,dict):arg={'id':str(arg)}
            resource=(tool,arg.get('job_id'),arg.get('path',arg.get('id',raw)))
            window=(*resource,arg.get('offset',0),arg.get('limit',4000),
                    hashlib.sha256(json.dumps(obs,sort_keys=True).encode()).hexdigest())
            if resource in seen:repeat_resources+=1
            if window in windows:repeat_windows+=1;row['exact_repeat_reads']+=1
            seen.add(resource);windows.add(window)
    quality={'goal_met':state['goal_met'],'workflow_status':state['workflow']['run_status'],
        'reviews':[{'gate':r.get('gate_id'),'verdict':r.get('verdict'),'reviewer':r.get('reviewer_assignment'),'summary':r.get('summary')}
            for r in state['workflow'].get('reviews',[])],
        'successful_jobs':sum(j['status']=='SUCCEEDED' for j in state['training']['jobs'].values()),
        'test':load(folder/'final-test.json') if (folder/'final-test.json').exists() else None}
    contracts=load(folder/'team-contract.json')
    wire_reports=Counter();raw_paths=list((folder/'agents').glob('*/turns/*/answer.json'));wire_rejected=[]
    for p in raw_paths:
        raw=load(p)
        if raw.get('tool') in {'submit_report','check_report'}:
            wire_reports['object' if isinstance(raw.get('argument'),dict) else 'string']+=1
        elif isinstance(raw.get('argument'),dict):
            wire_rejected.append({'source':str(p.relative_to(folder)),'action':raw})
    return {'folder':str(folder),'reservations':state['calls'],'returned_model_actions':len(returned),
        'model_errors':sum(r['kind']=='model' and r['status']=='ERROR' for r in spans),
        'raw_returned_outputs':len(raw_paths),
        'models':sorted(set(r['output']['metadata'].get('model','unknown') for r in returned)),
        'wall_seconds':(end-start).total_seconds(),'read_calls':read_calls,
        'same_resource_extra_reads':repeat_resources,'identical_window_extra_reads':repeat_windows,
        'tools':tools,'roles':roles,'errors':errors,'decisions':decisions,'quality':quality,
        'report_wire_arguments':wire_reports,
        'wire_rejected_outputs':wire_rejected,
        'task_budget':contracts['task']['budget'],'training_profiles':contracts['task'].get('training'),
        'workflow':contracts['task']['workflow']}

def handoff_audit(folder):
    folder=Path(folder);s=load(folder/'team-state.json');rows=[]
    for event in s['events']:
        if event['kind']!='training_outputs_published':continue
        for f in event['data']['files']:
            original=(folder/'training/jobs'/f['job_id']/'output'/f['source']).read_bytes()
            registered=(folder/'artifacts'/f['artifact_id']/'content').read_bytes()
            receivers=[]
            for aid,e in s['assignments'].items():
                assignment=e['assignment']
                if not assignment.get('review_of'):continue
                target='parent/'+f['destination']
                parent_paths={s['artifacts'][x]['path'] for x in assignment.get('parent_artifacts',[])}
                if target not in assignment.get('inputs',{}) and f['destination'] not in parent_paths:continue
                received=folder/'agents'/aid/'workspace/inputs'/target
                receivers.append({'role':e['agent'],'assignment':aid,'review_scope':assignment.get('review_scope'),
                    'identical':received.read_bytes()==original})
            rows.append({**f,'registered_identical':original==registered,'reviewer_receivers':receivers})
    return rows

def compare(before,after):
    a=summarize(before);b=summarize(after)
    deltas={}
    for key in ('reservations','returned_model_actions','wall_seconds','read_calls','same_resource_extra_reads','identical_window_extra_reads'):
        deltas[key]={'before':a[key],'after':b[key],'difference':b[key]-a[key],
            'reduction_percent':100*(a[key]-b[key])/a[key] if a[key] else None}
    return {'before':a,'after':b,'deltas':deltas,'handoff_audit':handoff_audit(after),
        'definitions':{
            'wall_seconds':'Earliest observable span start to latest span end; includes model latency, reviews and containers',
            'read_calls':'Successful read_file/read_job_output/read_evidence/read_artifact actions',
            'same_resource_extra_reads':'Repeated tool/resource within one assignment, including distinct pagination; not automatically waste',
            'identical_window_extra_reads':'Same tool/resource/offset/limit and identical returned observation within one assignment; may include legitimate confirmation',
            'scope':'One historical baseline and one new actual-agent study. Combined changes, model latency, stochastic choices and plans confound causal attribution.'}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--before',required=True);p.add_argument('--after',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();result=compare(a.before,a.after)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['deltas'],indent=2))

if __name__=='__main__':main()
