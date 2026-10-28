"""Human-readable failure investigation, including blind-review counterexamples."""
import argparse
import html
import json
import os
from pathlib import Path
from scorebench.run import ROOT


def read(path):return json.loads(Path(path).read_text())
def esc(value):return html.escape(str(value))


def write_report(folder):
    folder=Path(folder).resolve();result=read(folder/'results.json')
    protocol=read(folder/'protocol.json');state=read(folder/'state.json')
    investigation=read(ROOT/'research/failure-investigation.json')
    sources=read(ROOT/'research/existing-solutions.json')
    def link(path,label):
        return f'<a href="{esc(os.path.relpath(ROOT/path,folder))}">{esc(label)}</a>'
    b,a=result['summary']['before'],result['summary']['after']
    comparisons=''
    for name,key in [('Melody event edits','melody'),('Chord label edits','chords'),('Chord + onset edits (scorable subset)','timed_chords')]:
        comparisons+=f'<tr><td>{name}</td><td>{b[key]["errors"]} / {b[key]["reference_count"]}</td><td>{a[key]["errors"]} / {a[key]["reference_count"]}</td></tr>'
    findings=''
    for item in investigation['findings']:
        evidence=' · '.join(link(p,Path(p).name) for p in item['evidence'])
        findings+=f'<details><summary>{esc(item["id"])} — {esc(item["status"])}</summary><p>{esc(item["what"])}</p><p><b>Why:</b> {esc(item["why"])}</p><p><b>Discriminating test:</b> {esc(item["next_test"])}</p><p>{evidence}</p></details>'
    cases=''
    for row in result['rows']:
        case=row['case'];answer=row['review']['answer']
        before=row['before'];after=row['after']
        delta=after['melody']['errors']+after['chords']['errors']-before['melody']['errors']-before['chords']['errors']
        status='improved' if delta<0 else 'worsened' if delta>0 else 'unchanged'
        details=''
        for f in answer['findings']:
            details+=f'<li><b>{esc(f["category"])} — {esc(f["location"])}</b>: {esc(f["observation"])} Proposed: {esc(f["change"])}</li>'
        errors=json.dumps({arm:{k:row[arm][k].get('edits',row[arm][k]) for k in ['melody','chords','timed_chords']} for arm in ['before','after']},ensure_ascii=False,indent=2)
        cases+=f'''<details><summary>{esc(row['sample'])} — {status}; reviewer: {esc(answer['verdict'])}</summary>
        <p>Melody edits {before['melody']['errors']} → {after['melody']['errors']}; chord-label edits {before['chords']['errors']} → {after['chords']['errors']}.</p>
        <div class="score"><img src="cases/{case}/input.png" alt="Source excerpt"></div>
        <p><a href="cases/{case}/candidate.krn">Original prediction</a> · <a href="cases/{case}/prediction.krn">Reviewed prediction</a> · <a href="cases/{case}/model/prompt.txt">Exact blind prompt</a> · <a href="cases/{case}/review.json">Review receipt</a></p>
        <ul>{details}</ul><p><b>Uncertainties:</b> {esc('; '.join(answer['uncertainties']) or 'None reported — this does not certify correctness.')}</p>
        <details><summary>Reference differences, released only after freezing</summary><pre>{esc(errors)}</pre></details></details>'''
    roles=''.join(f'<tr><td>{esc(name)}</td><td>{esc(role["goal"])}</td><td>{esc(", ".join(role["allowed_inputs"]))}</td></tr>' for name,role in protocol['roles'].items())
    source_html=''
    for s in sources['sources']:
        source_html+=f'<details><summary>{esc(s["name"])} — {esc(s["category"])}</summary><p>{esc(s["why_relevant"])}</p><p>{esc(s["verified"])}</p><p><b>Limits:</b> {esc(s["limitations"])}</p><p><b>Decision:</b> {esc(s["decision"])}</p><a href="{esc(s["url"])}">Primary source</a></details>'
    controls=''.join(f'<li>{esc(x)}</li>' for x in investigation['answer_separation']['new_controls'])
    limits=''.join(f'<li>{esc(x)}</li>' for x in result['limits']+investigation['answer_separation']['limits'])
    c=result['comparison']
    body=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Why the music system fails — blind review experiment</title>
    <style>body{{font:17px/1.55 system-ui;color:#17232c;background:#faf9f6;max-width:1040px;margin:32px auto;padding:0 24px 64px}}h1{{line-height:1.13;font-size:38px}}h2{{margin-top:36px}}a{{color:#075b91}}table{{border-collapse:collapse;width:100%;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ced6dc;vertical-align:top}}details{{background:white;border:1px solid #d4dbe0;border-radius:8px;padding:14px;margin:12px 0}}summary{{cursor:pointer;font-weight:650}}pre{{overflow:auto;font-size:12px;background:#eef1f4;padding:12px}}.score{{overflow:auto}}img{{max-width:none}}.callout{{background:#e7efe9;border-left:4px solid #356b47;padding:16px}}.muted{{color:#52626d}}.table{{overflow:auto}}</style>
    <p class="muted">Church music • Failure investigation • 28 October 2026</p><h1>Does an independent reviewer help?</h1>
    <p class="callout">On the same seven development excerpts: {c['improved_samples']} improved, {c['worsened_samples']} worsened and {c['unchanged_samples']} were unchanged on melody/chord-label edits. {c['originally_exact_samples_regressed']} originally exact cases regressed. This is a measured intervention, not evidence that more agents always help.</p>
    <div class="table"><table><thead><tr><th>Metric</th><th>Original vision output</th><th>After blind review</th></tr></thead><tbody>{comparisons}</tbody></table></div>
    <p>Timing coverage: {a['timing_scorable_samples']} / {result['samples']} excerpts. A null melody row makes some chord onsets under-specified; those are marked unknown. The earlier 38/38 chord-label result did not establish correct placement.</p>
    <p>{state['model_calls']} additional model calls; {state['active_seconds']:.1f} seconds of review-stage wall time; {result['review_failures']} failed review calls. Model: {esc(protocol['model'])}, high effort. One review per case, no score-directed retries. Existing account usage; dollar cost unavailable.</p>
    <h2>What failed, and why</h2>{findings}
    <h2>Per-case review: repairs and damage both count</h2>{cases}
    <h2>Each role has one goal and restricted inputs</h2><div class="table"><table><tr><th>Role</th><th>Goal</th><th>Allowed structured inputs</th></tr>{roles}</table></div>
    <p>Transcriber and reviewer also receive the image attachment. The scorer is trusted deterministic code, not an LLM. It must see references to calculate accuracy, but can do so only after the batch is frozen. It cannot revise predictions or send answers back into this run.</p>
    <ul>{controls}</ul><p><b>Scope of protection:</b> explicit model-input and tool separation. The CLI process is not inside an OS filesystem jail; tool-using workers need a separately isolated service/container with no reference mount.</p>
    <h2>Existing solutions selected for this task</h2><p>{esc(sources['selection_method'])}</p>{source_html}
    <h2>What this does not establish</h2><ul>{limits}</ul>
    <p><a href="results.json">Complete measurements</a> · <a href="protocol.json">Frozen experiment protocol</a> · <a href="seal.json">Prediction hashes</a> · <a href="audit.json">Boundary audit</a></p>
    </html>'''
    (folder/'report.html').write_text(body)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');write_report(p.parse_args().folder)
