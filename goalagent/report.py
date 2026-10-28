from pathlib import Path
import html,json,os
from scorebench.run import ROOT

def write_report(state,folder):
    e=html.escape
    def link(path,label):return f'<a href="{e(os.path.relpath(path,folder))}">{e(label)}</a>'
    s=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Goal agent — music experiment</title>',
       '<style>body{font:16px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;background:#faf9f6;color:#192a30}table{display:block;overflow-x:auto;border-collapse:collapse}td,th{padding:10px;border:1px solid #ddd;text-align:left}details,.card{padding:16px;background:white;border:1px solid #ddd;border-radius:8px;margin:16px 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}img{max-width:100%}a{color:#09634e}.status{background:#fff0d9;padding:18px}</style>',
       '<h1>Goal-solving agent: first music test</h1>',f'<p>{e(state["goal"]["goal"])}</p>',
       f'<p class="status"><b>Run status: {e(state["status"])} · Product goal met: {state["goal_met"]}</b><br>{state["steps"]} decisions · {state["model_calls"]} model calls reserved/attempted · {state["active_seconds"]:.1f} active seconds</p>',
       '<p>The model chooses tools from observations. The host executes them, scores predictions against protected labels and enforces the completion rule. A successful agent run can still leave the music goal unmet.</p>',
       '<p>Why one controller: establish a traceable baseline before adding coordination. Why separate evaluators: the model cannot approve its own output or change the reference labels. Why a fixed pilot: paired comparisons within a bounded budget; it cannot establish performance on new songs.</p>',
       '<h2>Recent evidence behind the design</h2>']
    if state.get('parent_run'):
        s.append('<p class="status">This is a versioned continuation after an evaluator correction. Recognition outputs were reused; the original measurements and decisions remain in '+link(ROOT/state['parent_run']/'report.html','the original run')+'.</p>')
        for correction in state.get('external_evidence',[]):
            s.append('<details><summary>Evaluator correction: preserve the audit trail</summary><pre>'+e(json.dumps(correction,ensure_ascii=False,indent=2))+'</pre></details>')
    sources=json.loads((ROOT/'research/recent-talks/review.json').read_text())['sources']
    for r in sources:
        s.append(f'<div class="card"><a href="{e(r["url"])}">{e(r["title"])}</a> · {r["date"]}<p>{e(r["application"])}</p><small>Full available transcript reviewed; frames not inspected. {e(r["limit"])}</small></div>')
    s.append('<h2>Measured candidates</h2><p>Lower edit rate is better. Melody compares pitch and duration; chord timing is not scored. Repeated invented events can produce rates above 100%.</p>')
    for eid,r in state['evaluations'].items():
        folder_e=folder/'experiments'/eid
        s.append(f'<div class="card"><h3>{e(eid)}</h3><pre>{e((folder_e/"config.json").read_text())}</pre><table><tr><th>Approach</th><th>Melody errors / events</th><th>Chord errors / labels</th></tr>')
        comparisons={eid:r,**r['paired_baselines']}
        for name,x in comparisons.items():
            m,c=x['melody'],x['chords'];s.append(f'<tr><td>{e(name)}</td><td>{m["errors"]}/{m["reference_count"]} ({m["error_rate"]:.1%})</td><td>{c["errors"]}/{c["reference_count"]} ({c["error_rate"]:.1%})</td></tr>')
        s.append(f'</table><p>Parseable: {r["parseable"]}/{r["samples"]}. Exact measured melody + chord labels: {r["exact_measured"]}/{r["samples"]}. Chord timing audited: false. Musician accepted: false.</p>'+link(folder_e/'evaluation.json','Evaluation JSON')+'</div>')
        for row in json.loads((folder_e/'detailed-results.json').read_text()):
            sample=folder_e/f'sample-{row["sample_index"]:03}'
            s.append(f'<details><summary>{e(row["id"])} · melody errors {row["melody"]["errors"]} · chord errors {row["chords"]["errors"]}</summary>')
            s.append(f'<p>Input</p><img src="{os.path.relpath(sample/"input.png",folder)}" alt="Source music excerpt">')
            if (sample/'prediction.svg').exists():s.append(f'<p>Prediction (first page)</p><img src="{os.path.relpath(sample/"prediction.svg",folder)}" alt="Predicted notation">')
            if row['trace'].get('output'):s.append('<p>'+link(ROOT/row['trace']['output'],'Editable prediction')+'</p>')
            if row['trace'].get('transposed'):s.append('<p>'+link(ROOT/row['trace']['transposed'],'Transposed up a major second')+'</p>')
            s.append('<pre>'+e(json.dumps({'status':row['trace']['status'],'errors':row['inspection']['errors'],'uncertainties':row['trace'].get('uncertainties',[]),'melody_edits':row['melody']['edits'][:20],'chord_edits':row['chords']['edits'][:20]},ensure_ascii=False,indent=2))+'</pre></details>')
    s.append('<h2>Decision trail: why, action, observation</h2>')
    for r in state['history']:
        d=r.get('decision') or {};obs=r['observation']
        s.append(f'<details><summary>Step {r["step"]}: {e(d.get("tool","invalid decision"))} → {e(obs["id"])}</summary><p>{e(d.get("why",""))}</p><p><b>Hypothesis:</b> {e(d.get("hypothesis",""))}</p><p><b>Expected observation:</b> {e(d.get("expected_observation",""))}</p><pre>{e(json.dumps(obs,ensure_ascii=False,indent=2))}</pre></details>')
    s.append('<h2>What is not established</h2><p>This is a bounded local agent with a music toolkit and a curated evidence library. It has no arbitrary code-editing or model-training tool, no automatic external event subscriptions, and no proven multi-agent benefit. Model self-reported uncertainty is not calibrated confidence. The acceptance guard requires all 32 samples, audited chord timing and musician acceptance; the pilot cannot satisfy it.</p><p>'+link(folder/'state.json','Complete durable state')+' · '+link(folder/'agent-evaluation.json','Independent process audit')+' · '+link(ROOT/'README.md','Rerun instructions')+'</p></html>')
    (folder/'report.html').write_text('\n'.join(s))
