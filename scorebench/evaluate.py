"""Score every input, including errors and missing outputs. Produce a reviewable HTML report."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

from .metrics import kern_melody_only, parse_events, reference_chords, sequence_metrics
from .run import ROOT

ENGINES = ["audiveris-raw", "audiveris-enlarged", "transcoda-greedy"]
RATIONALE = {
    "audiveris-raw": "Established OMR software on untouched pixels: establishes out-of-box compatibility with the supplied low-resolution crops.",
    "audiveris-enlarged": "Same recognizer, fixed 3× Lanczos enlargement plus 60-pixel white border: tests a preprocessing intervention with no extra model or agent. Scale and border are changed together.",
    "transcoda-greedy": "A pretrained neural image-to-kern model, frozen weights, model-card preprocessing and greedy decoding: tests a different perception approach. Its training output omits chord-symbol spines.",
}


def freeze(item):
    return tuple(freeze(x) for x in item) if isinstance(item, list) else item


def aggregate(rows, key):
    counts = {k: sum(r[key][k] for r in rows) for k in
              ["reference_count", "prediction_count", "matches", "errors", "substitutions", "deletions", "insertions"]}
    denominator = counts["reference_count"]
    counts["error_rate"] = counts["errors"] / denominator if denominator else None
    counts["f1"] = 2 * counts["matches"] / (denominator + counts["prediction_count"]) if denominator + counts["prediction_count"] else 1
    return counts


def evaluate(run_root):
    samples = json.loads((ROOT / "research/manifest.json").read_text())
    missing = [str(run_root / e / f"sample-{i:03}" / "trace.json") for e in ENGINES
               for i in range(1, len(samples)+1)
               if not (run_root / e / f"sample-{i:03}" / "trace.json").exists()]
    if missing:
        raise RuntimeError(f"Benchmark is incomplete ({len(missing)} traces missing); wait for inference before scoring.")
    references = {}
    for sample in samples:
        path = ROOT / sample["reference"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != sample["reference_sha256"]:
            raise ValueError(f"Original reference changed: {path}")
        text = path.read_text()
        events, warnings = parse_events(kern_melody_only(text), "humdrum")
        references[sample["id"]] = (events, reference_chords(text), warnings)
    results = []
    for engine in ENGINES:
        for i, sample in enumerate(samples, 1):
            folder = run_root / engine / f"sample-{i:03}"
            trace_file = folder / "trace.json"
            trace = json.loads(trace_file.read_text()) if trace_file.exists() else {"status": "not_run", "output": None}
            inspection = {"events": [], "chords": [], "parse_ok": False, "render_ok": False, "errors": []}
            if trace.get("output"):
                output = ROOT / trace["output"]
                if hashlib.sha256(output.read_bytes()).hexdigest() != trace["output_sha256"]:
                    raise ValueError(f"Prediction changed: {output}")
                inspect_file = folder / "inspection.json"
                with (folder / "inspection.log").open("w") as log:
                    try:
                        worker = subprocess.run([sys.executable, "-m", "scorebench.inspect_prediction", str(output), str(inspect_file)],
                                                cwd=ROOT, stdout=log, stderr=log, timeout=20)
                        if worker.returncode == 0 and inspect_file.exists():
                            inspection = json.loads(inspect_file.read_text())
                        else:
                            inspection["errors"].append(f"inspection worker exited {worker.returncode}")
                    except subprocess.TimeoutExpired:
                        inspection["errors"].append("inspection timed out after 20 seconds")
            notes, chords, reference_warnings = references[sample["id"]]
            predicted = [freeze(e) for e in inspection["events"]]
            predicted_chords = [freeze(c) for c in inspection["chords"]]
            log_path = folder / "engine.log"
            log = log_path.read_text(errors="replace") if log_path.exists() else ""
            flags = []
            if "too low interline" in log:
                flags.append("input_resolution_rejected")
            if trace["status"] == "generation_limit":
                flags.append("generation_did_not_finish")
            if trace.get("output") and not inspection["parse_ok"]:
                flags.append("output_not_parseable")
            if chords and not predicted_chords:
                flags.append("all_chord_labels_missing")
            if not trace.get("output"):
                flags.append("no_transcription")
            row = {"id": sample["id"], "song": sample["song"], "engine": engine,
                   "source_image": sample["image"], "folder": str(folder.relative_to(ROOT)),
                   "trace": trace, "inspection": inspection, "failure_flags": flags,
                   "reference_warnings": reference_warnings,
                   "melody": sequence_metrics(notes, predicted),
                   "pitch_only": sequence_metrics([e[0] for e in notes], [e[0] for e in predicted]),
                   "chords": sequence_metrics(chords, predicted_chords),
                   "reference_events": notes, "reference_chords": chords}
            row["exact_melody_and_chords"] = (inspection["parse_ok"] and row["melody"]["errors"] == 0
                                                  and row["chords"]["errors"] == 0 and trace["status"] == "ok")
            results.append(row)
        print(f"Evaluated {engine}: {len(samples)} samples", flush=True)
    summary = {}
    for engine in ENGINES:
        rows = [r for r in results if r["engine"] == engine]
        latencies = [r["trace"]["elapsed_seconds"] for r in rows if "elapsed_seconds" in r["trace"]]
        summary[engine] = {"samples": len(rows), "execution_status": dict(Counter(r["trace"]["status"] for r in rows)),
                           "files_returned": sum(bool(r["trace"].get("output")) for r in rows),
                           "parseable": sum(r["inspection"]["parse_ok"] for r in rows),
                           "renderable": sum(r["inspection"]["render_ok"] for r in rows),
                           "exact_melody_and_chords": sum(r["exact_melody_and_chords"] for r in rows),
                           "exact_melody": sum(r["melody"]["errors"] == 0 for r in rows),
                           "median_melody_error_rate": statistics.median(r["melody"]["error_rate"] for r in rows),
                           "melody": aggregate(rows, "melody"), "pitch_only": aggregate(rows, "pitch_only"),
                           "chords": aggregate(rows, "chords"),
                           "median_seconds": statistics.median(latencies) if latencies else None,
                           "total_sample_seconds": sum(latencies),
                           "per_song": {song: {"melody": aggregate([r for r in rows if r["song"] == song], "melody"),
                                                "chords": aggregate([r for r in rows if r["song"] == song], "chords")}
                                        for song in sorted({r["song"] for r in rows})}}
    report = {"status": "diagnostic_development_benchmark", "date": "2026-10-27", "samples": len(samples),
              "song_groups": len({s["song"] for s in samples}), "rationale": RATIONALE,
              "not_run": {"openai_vision": "OPENAI_API_KEY unavailable in this process; no API credential integration tool available.",
                          "additional_agents": "No multi-agent comparison performed; its benefit is unmeasured."},
              "limits": ["References are supplied labels, not a musician-audited gold set.",
                         "Seven song groups, short excerpts, all with empty key signatures; no held-out generalization claim.",
                         "Primary metric is sequence edit error on pitch plus rational duration, with matching ties merged. Includes rests.",
                         "Chord score measures ordered root, kind, bass and explicit extensions; chord timing is not scored.",
                         "No full notation, voice alignment, repeat-playback, lyric or accidental-display fidelity metric.",
                         "Missing or unparseable outputs count as all reference events deleted; their unparsed insertions cannot be counted.",
                         "An edit error rate can exceed 100 percent; it is not accuracy.",
                         "No correction-time study or calibrated confidence thresholds yet.",
                         "Latency includes per-image Audiveris startup, excludes neural load time; some runs overlapped, so do not compare speed as controlled performance.",
                         "Transcoda canonical header/terminator restoration changes no pitches or durations. Raw outputs are retained.",
                         "No weights trained, no labels sent to inference, no paid API calls."],
              "summary": summary, "results": results}
    supplementary = {
        "transposition": run_root / "transposition-checks.json",
        "beam_pilot": run_root / "beam-pilot.json",
        "pipeline_control": ROOT / "runs/control/metrics.json",
    }
    report["supplementary"] = {name: json.loads(path.read_text())
                               for name, path in supplementary.items() if path.exists()}
    (run_root / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    write_html(report, run_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_html(report, run_root):
    esc = html.escape
    def relative(path):
        import os
        return os.path.relpath(ROOT / path, run_root)
    body = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
            '<title>First score recognition benchmark</title><style>body{font:16px/1.55 system-ui;margin:40px auto;max-width:1200px;padding:0 24px;color:#17212b;background:#faf9f6}h1{font-size:36px}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;border-bottom:1px solid #ddd;padding:12px}th{background:#edf2f0}details{margin:14px 0;padding:18px;background:white;border:1px solid #ddd;border-radius:8px}summary{cursor:pointer;font-weight:650}img{max-width:100%;height:auto}code,pre{background:#f0f1f2;padding:4px;white-space:pre-wrap}small{color:#53616a}.warning{border-left:4px solid #c76b26;padding:10px 20px;background:#fff5e9}a{color:#12614d}.controls{margin:20px 0}select{padding:8px;font:inherit}.metric{font-size:22px;font-weight:650}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:700px){.two{display:block}}</style>',
            '<h1>First score recognition benchmark</h1>',
            '<p>32 excerpts · 7 song groups · 27 October 2026 · frozen local recognizers</p>',
            '<p class="warning"><b>These are diagnostic results against supplied labels, not production accuracy.</b> A parseable file can contain wrong music. All failed inputs remain in the denominators.</p>',
            '<table><tr><th>Approach</th><th>Files / 32</th><th>Parse / render</th><th>Melody edits / reference events</th><th>Chord edits / reference chords</th><th>Exact combined</th></tr>']
    for engine, s in report['summary'].items():
        m,c=s['melody'],s['chords']
        body.append(f'<tr><td>{esc(engine)}</td><td>{s["files_returned"]}</td><td>{s["parseable"]} / {s["renderable"]}</td><td>{m["errors"]}/{m["reference_count"]} ({m["error_rate"]:.1%})</td><td>{c["errors"]}/{c["reference_count"]} ({c["error_rate"]:.1%})</td><td>{s["exact_melody_and_chords"]}/32</td></tr>')
    body.append('</table><style>table{display:block;overflow-x:auto}td,th{min-width:100px}@media(max-width:700px){body{padding:0 16px;margin:24px auto}h1{font-size:28px}}</style><p>Lower edit rate is better. Insertions can make it exceed 100%. Melody means pitch + duration; chord beat placement is not measured. On narrow screens, scroll tables sideways.</p><h2>Why these approaches</h2>')
    for name, why in report['rationale'].items():
        body.append(f'<p><b>{esc(name)}</b>: {esc(why)}</p>')
    body.append('<h2>What this benchmark cannot establish</h2><ul>')
    body.extend(f'<li>{esc(limit)}</li>' for limit in report['limits'])
    body.append('</ul><p>OpenAI vision and extra agents were not run. The local process has no OpenAI API key.</p>')
    transposition = run_root / 'transposition-checks.json'
    if transposition.exists():
        body.append('<h2>A conversion failure we can fix without another model</h2><p>The supplied chord dialect uses <code>G:maj/B</code>. The existing Humdrum transpose filter returns <code>A:maj/B</code> for an upward major second, leaving the bass unchanged. Our explicit chord adapter returns <code>A:maj/C#</code>. Original files are preserved.</p><p><a href="transposition-checks.json">Transposition checks and examples</a></p>')
    control = ROOT / 'runs/control/metrics.json'
    if control.exists():
        c = json.loads(control.read_text())
        body.append(f'<h2>Independent pipeline control</h2><p>Using the same Transcoda adapter on row 0 of the publisher’s released <a href="https://huggingface.co/datasets/btrkeks/verovio-synth-omr">synthetic benchmark</a> produced {c["errors"]} melody edits across {c["reference_count"]} reference events. This is one successful integration check, not a new estimate of the model’s published performance.</p><p><a href="../control/metrics.json">Control results</a></p>')
    pilot = run_root / 'beam-pilot.json'
    if pilot.exists():
        paired = json.loads(pilot.read_text())
        body.append('<h2>Does wider decoding search help?</h2><p>Exploratory paired check on the first listed excerpt of each of the seven songs. Same weights, preprocessing and limits; beam width 3 instead of greedy decoding. Selected by filename order after the first benchmark, not a held-out study.</p><table><tr><th>Excerpt</th><th>Reference events</th><th>Greedy edits</th><th>Beam edits</th></tr>')
        for item in paired:
            body.append(f'<tr><td>{esc(item["id"])}</td><td>{item["reference_count"]}</td><td>{item["greedy_errors"]}</td><td>{item["beam_errors"]}</td></tr>')
        body.append('</table><p>Wider search improves two excerpts, worsens three, and leaves two unchanged on this metric. Most aggregate improvement comes from one runaway output. It supplies no chord labels and is not evidence that additional agents would help.</p>')
    body.append('<h2>What to change next</h2><p><b>First address recognition coverage and integration.</b> Preserve slash bass explicitly, reject unfinished generation, and benchmark a chord-capable recognizer. Keep image scale and crop layout in the comparison. Extra agents have not been tested and cannot be credited with an improvement.</p><p>The human decision still needed is whether the corrected output saves band members time. This benchmark has not measured correction time or established a release threshold.</p>')
    body.append('<h2>Inspect every prediction</h2><p>Open a row to compare the source with the predicted score and exact edits. Rows are ordered by melody edit rate within each approach. The preview shows the first rendered page; raw outputs contain the full result.</p><div class="controls"><label>Approach <select id="filter"><option value="all">All</option>')
    body.extend(f'<option>{esc(e)}</option>' for e in ENGINES)
    body.append('</select></label></div>')
    for row in sorted(report['results'], key=lambda r:(r['engine'], -(r['melody']['error_rate'] or 0))):
        folder = ROOT / row['folder']
        rate = row['melody']['error_rate'] or 0
        body.append(f'<details data-engine="{esc(row["engine"])}"><summary>{esc(row["id"])} · {esc(row["engine"])} · melody {rate:.1%} · chord errors {row["chords"]["errors"]} · {esc(row["trace"]["status"])}</summary>')
        body.append(f'<p><a href="{esc(relative(row["folder"]+"/trace.json"))}">Execution trace</a> · <a href="{esc(relative(row["source_image"]))}">Original image</a></p><p><b>Source image</b></p><img loading="lazy" src="{esc(relative(row["source_image"]))}" alt="Original score excerpt">')
        if (folder/'prediction.svg').exists():
            body.append(f'<p><b>Predicted notation</b></p><img loading="lazy" src="{esc(relative(row["folder"]+"/prediction.svg"))}" alt="Predicted music notation">')
        else:
            body.append('<p>No usable notation preview was produced.</p>')
        if row['trace'].get('output'):
            body.append(f'<p><a href="{esc(relative(row["trace"]["output"]))}">Raw recognizer output</a></p>')
        for name in ['adapted.krn','converted.krn','engine.log','inspection.log']:
            if (folder/name).exists():
                body.append(f'<a href="{esc(relative(row["folder"]+"/"+name))}">{esc(name)}</a> · ')
        body.append(f'<p>{esc(", ".join(row["failure_flags"]))}</p>')
        if row['inspection']['errors']:
            body.append('<pre>'+esc('\n'.join(row['inspection']['errors']))+'</pre>')
        for label, key in [('Melody edits: pitch spelling and quarter-note duration','melody'),('Chord edits: root, quality, bass, extensions','chords')]:
            body.append(f'<h3>{label}</h3><table><tr><th>Operation</th><th>Expected</th><th>Actual</th></tr>')
            for edit in row[key]['edits'][:24]:
                body.append(f'<tr><td>{esc(edit["operation"])}</td><td>{esc(str(edit["expected"]))}</td><td>{esc(str(edit["actual"]))}</td></tr>')
            body.append('</table>')
            if len(row[key]['edits'])>24:
                body.append(f'<small>First 24 of {len(row[key]["edits"])} edits; all edits are in results.json.</small>')
        body.append('</details>')
    body.append('<p><a href="results.json">Complete machine-readable results</a></p><script>document.getElementById("filter").addEventListener("change",e=>{document.querySelectorAll("details[data-engine]").forEach(d=>d.hidden=e.target.value!=="all"&&d.dataset.engine!==e.target.value)})</script></html>')
    (run_root/'report.html').write_text('\n'.join(body))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-root',default='runs/first-benchmark')
    args=parser.parse_args();evaluate(ROOT/args.run_root)
