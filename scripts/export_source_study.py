"""Export observable source-study evidence without running submitted Python."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil

from goalagent.tracing import Trace


def load(path):
    return json.loads(path.read_text())


def summarize(folder):
    folder = Path(folder)
    state = load(folder / 'team-state.json')
    spans = Trace(folder / 'traces').records()
    roles, decisions, errors, searches, repeated, previews = [], [], [], [], [], []
    entries = {**state['assignments'], 'lead': {'agent': 'coordinator', 'assignment': {}}}
    for aid, entry in entries.items():
        root = folder / 'agents' / aid
        if not (root / 'worker-state.json').exists():
            continue
        worker = load(root / 'worker-state.json')
        metadata = [load(p) for p in root.glob('turns/*/metadata.json')]
        roles.append({'assignment': aid, 'role': entry['agent'], 'scope': entry['assignment'].get('review_scope'),
            'status': worker['status'], 'steps': worker['steps'], 'returned_actions': len(list(root.glob('turns/*/answer.json'))),
            'assignment_outcome': entry.get('outcome', {}).get('status'),
            'model_seconds': sum(m.get('elapsed_seconds', 0) for m in metadata),
            'usage': {k: sum(m.get('usage', {}).get(k, 0) for m in metadata)
                      for k in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')},
            'input_names': list(entry['assignment'].get('inputs', {})),
            'parent_paths': [state['artifacts'][a]['path'] for a in entry['assignment'].get('parent_artifacts', [])],
            'report': worker.get('report')})
        reads = Counter()
        receipt_reads = Counter()
        for action in worker['history']:
            tool, observation = action['tool'], action.get('observation', {})
            if tool == 'record_decision':
                decisions.append({'assignment': aid, 'role': entry['agent'], 'step': action['step'],
                                  **json.loads(action['argument'])})
            if tool in ('web_fetch', 'web_search'):
                searches.append({'assignment': aid, 'step': action['step'], 'tool': tool,
                    'argument': action['argument'], 'why': action.get('why'),
                    **{k: observation.get(k) for k in ('url', 'status', 'format', 'pages_total', 'pages_extracted',
                                                      'truncated', 'text_file', 'transport', 'document_error')}})
            if tool == 'read_file':
                arg = json.loads(action['argument'])
                reads[(arg['path'], arg.get('offset', 0), arg.get('limit', 4000))] += 1
            if tool == 'read_evidence':
                arg = json.loads(action['argument'])
                receipt_reads[(arg['id'], arg.get('offset', 0))] += 1
            if isinstance(observation, dict) and 'error' in observation:
                errors.append({'assignment': aid, 'step': action.get('step'), 'tool': tool, 'observation': observation})
        repeated.extend({'assignment': aid, 'role': entry['agent'], 'path': path, 'offset': offset,
                         'limit': limit, 'reads': count, 'extra_reads': count - 1}
                        for (path, offset, limit), count in reads.items() if count > 1)
        repeated.extend({'assignment': aid, 'role': entry['agent'], 'evidence_id': eid, 'offset': offset,
                         'reads': count, 'extra_reads': count - 1}
                        for (eid, offset), count in receipt_reads.items() if count > 1)
        for path in root.glob('turns/*/prompt.txt'):
            context = json.loads(path.read_text().rsplit('\nTask data:\n', 1)[1])
            for action in context.get('recent_actions', []):
                observation = action.get('observation', {})
                if action.get('tool') == 'read_file' and observation.get('truncated'):
                    previews.append({'assignment': aid, 'turn': path.parent.name,
                        'evidence_id': observation.get('read_full_evidence_id'), 'preview_characters': len(observation.get('preview', ''))})
    jobs = []
    for job in state.get('training', {}).get('jobs', {}).values():
        out = folder / 'training/jobs' / job['id'] / 'output'
        jobs.append({'id': job['id'], 'owner': job['owner'], 'status': job['status'], 'request': job['request'],
            'metrics': load(out / 'metrics.json') if (out / 'metrics.json').exists() else None})
    candidates = state.get('managed', {}).get('candidates', {})
    deliveries = {}
    for stage, aid in candidates.items():
        snapshot = load(folder / 'agents' / aid / 'source-snapshot.json')
        deliveries[stage] = {name: json.loads(snapshot[name]) for name in
            ('sources.json', 'source-influence.json', 'experiments.json', 'model-ref.json') if name in snapshot}
    final = {name: load(folder / name) for name in ('source-verification.json', 'source-visibility-audit.json', 'comparison-audit.json', 'final-test.json', 'validation-audit.json', 'restart-verification.json')
             if (folder / name).exists()}
    ends = [datetime.fromisoformat(s.get('ended_at', s['started_at'])) for s in spans]
    starts = [datetime.fromisoformat(s['started_at']) for s in spans]
    return {'run': folder.name, 'model_call_reservations': state['calls'], 'run_status': state['workflow']['run_status'],
        'goal_met': state['goal_met'], 'wall_seconds': (max(ends) - min(starts)).total_seconds() if spans else 0,
        'models': sorted({(s.get('output') or {}).get('metadata', {}).get('model') for s in spans
                          if s['kind'] == 'model' and (s.get('output') or {}).get('metadata', {}).get('model')}),
        'roles': roles, 'decisions': decisions, 'search_and_fetch': searches, 'tool_errors': errors,
        'exact_repeated_read_windows': repeated, 'source_read_context_previews': previews,
        'host_interventions': [e for e in state['events'] if e['kind'] in ('managed_wait', 'external_event')],
        'reviews': state['workflow']['reviews'], 'jobs': jobs, 'deliveries': deliveries, 'verification': final}


def export(folder, output):
    folder, output = Path(folder), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    record = summarize(folder)
    (output / 'verification.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    Trace(folder / 'traces').export(output / 'live-agent-trace.html')
    # Preserve our generated training code/results, not downloaded papers/source bodies.
    for job in record['jobs']:
        origin = folder / 'training/jobs' / job['id']
        dest = output / 'jobs' / job['id']
        dest.mkdir(parents=True, exist_ok=True)
        for relative in ('code/train.py', 'output/metrics.json', 'job.log'):
            source = origin / relative
            if source.exists():
                shutil.copyfile(source, dest / relative.replace('/', '-'))
    print(json.dumps({'run_status': record['run_status'], 'goal_met': record['goal_met'],
                      'reservations': record['model_call_reservations'], 'output': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    export(args.run_dir, args.output)
