"""Maintainer-dispatched actual reader probe of existing runtime interfaces.

Synthetic document/marker and an existing diagram, not new scientific results.
The model chooses its review findings; dispatch and the continuation check are fixed.
"""
import argparse
import json
from pathlib import Path
from goalagent.team import Team,ROOT
from goalagent.agent import Agent
from goalagent.contracts import atomic_json


def verify(folder):
    folder=Path(folder).resolve();configs=folder/'config';configs.mkdir(parents=True,exist_ok=True)
    for p in (ROOT/'agents/training').iterdir():
        if p.suffix=='.json':
            config=json.loads(p.read_text())
            if config['id']=='report_reader':
                config['tools']=[t for t in config['tools'] if t!='review_gate']
                config['limits'].update(max_steps=32,max_seconds=1200,model_call_timeout=180)
                config['checkpoint_interval']=24
            atomic_json(configs/p.name,config)
        else:(configs/p.name).write_text(p.read_text())
    prompt=(configs/'report_reader.md').read_text()
    prompt+='''\nStandalone runtime probe: there is no gate/review_of. Do not call review_gate. Read note.txt (one <=8000-byte window) and report.md completely and visually inspect figure.png. After your first file read, checkpoint once with a check citing that real read receipt. On continuation retain completed coverage instead of reopening without a reason. Then submit_report DONE with files=[], scoped document claims, concrete objections if warranted and the inspection marker from note.txt in your summary. Read artifacts only, no factual/scientific re-evaluation. Use report_context for targets. The source report contains prior reviewer findings as historical text, not conclusions you should adopt.\n'''
    (configs/'report_reader.md').write_text(prompt)
    task={'goal':'Validate actual report reading, continuation, image grant and submission using the existing runtime.',
          'inputs':{},'network':False,'budget':{'max_calls':32,'max_seconds':1500,'max_assignments':2,'max_depth':1}}
    team=Team(folder,task,agents_dir=configs)
    c=team.definitions['coordinator'];host=Agent(folder/'agents/lead',{'depth':0},None,team.policy(c),c,team.registry,trace=team.trace)
    report=(ROOT/'docs/external-source-results-ko.md').read_text()
    report=report.replace('| 총 optimizer step 수 | 2,150 | 2,150 |\n| 총 epoch 수 | 5 | 5 |','| optimizer step / epoch | 2,150 / 5 | 2,150 / 5 |')
    (host.workspace/'report.md').write_text(report)
    prefix='# Synthetic runtime reading probe\nThese are maintainer fixture notes, not experimental measurements.\n'
    filler='Evidence is a bounded observation. A reader review does not independently reproduce a training experiment.\n'
    tail='\nInspection marker: delta-seven.\n'
    note=prefix+(filler*100)[:7900-len(prefix)-len(tail)]+tail
    assert len(note.encode())==7900
    (host.workspace/'note.txt').write_text(note)
    (host.workspace/'figure.png').write_bytes((ROOT/'docs/diagrams/source-study-handoff.png').read_bytes())
    packet={'agent':'report_reader','objective':'Review the full delivered report and included figure, identify any concrete clarity issue, read the tail marker in note.txt and verify a single progress checkpoint/continuation.',
            'success_criteria':'Scope conclusions to comprehension, preserve reading coverage, inspect the image and submit valid findings.',
            'inputs':{name:name for name in ('report.md','note.txt','figure.png')}}
    try:
        result=host.execute({'tool':'delegate','argument':json.dumps(packet),'why':'Maintainer interface regression probe, actual reader judgment'},1400)
        for n in range(4):
            if result['outcome']['status']!='checkpointed':break
            host.state['steps']+=1
            continuation={'assignment_id':result['assignment_id'],'checkpoint_id':result['checkpoint_id'],
                'guidance':'Continue this same reader assignment. Preserve completed reading/checklist evidence. The known artifact grants and report_context are available; finish the remaining inspections and submit the scoped report.'}
            result=host.execute({'tool':'continue_assignment','argument':json.dumps(continuation),'why':'Resume the known checkpoint without a duplicate assignment'},1400)
        aid=result['assignment_id'];worker=json.loads((folder/'agents'/aid/'worker-state.json').read_text())
        history=worker['history'];errors=[r for r in history if 'error' in r.get('observation',{})]
        visible=False
        for p in (folder/'agents'/aid/'turns').glob('*/prompt.txt'):
            data=json.loads(p.read_text().rsplit('\nTask data:\n',1)[1])
            for action in data.get('recent_actions',[]):
                if action.get('tool')=='read_file' and action.get('observation',{}).get('path')=='inputs/note.txt':
                    visible |= action['observation'].get('text')==note
        checks={'submitted':worker['status']=='submitted','image_viewed':any(r['tool']=='view_image' for r in history),
                'full_7900_byte_note_in_model_context':visible,'one_assignment':len(team.state['assignments'])==1,
                'checklist_retained':bool(worker.get('review_checklist')),'marker_reported':'delta-seven' in json.dumps(worker.get('report')),
                'no_tool_errors':not errors}
        verification={'status':'passed' if all(checks.values()) else 'incomplete','checks':checks,'calls':team.state['calls'],
                      'report':worker.get('report'),'errors':errors,
                      'scope':'Actual model reading/continuation/submission probe with fixed maintainer dispatch and a seeded label ambiguity; not scientific research or an A/B efficiency claim'}
        atomic_json(folder/'verification.json',verification)
        print(json.dumps(verification,ensure_ascii=False))
    finally:team.trace.export(folder/'trace.html');team.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();verify(a.run_dir)
