import json
from types import SimpleNamespace

import pytest

from goalagent.artifacts import ArtifactStore
from goalagent.literature_live import source_verdict


def delivery(tmp_path):
    store = ArtifactStore(tmp_path / 'artifacts')
    records, artifacts, snapshot, sources = {}, {}, {}, []
    discovery = 'Method title; org/reference'
    records['discovery'] = {'assignment_id': 'owner', 'receipt': {
        'tool': 'web_search', 'observation': {'status': 'retrieved', 'text_excerpt': discovery}}}
    for kind, url, term in [
        ('paper', 'https://journal/method.pdf', 'Method title'),
        ('implementation', 'https://raw.githubusercontent.com/org/reference/' + 'a' * 40 + '/train.py', 'org/reference'),
    ]:
        path = kind + '.txt'
        body = ('[PDF page 2]\n' + 'method body ' * 1000) if kind == 'paper' else 'class Model:\n    pass\n'
        raw = body.encode()
        artifact = store.register(raw, owner='web', path=path)
        artifacts[artifact['artifact_id']] = artifact
        snapshot[path] = body
        records[kind] = {'assignment_id': 'owner', 'receipt': {'tool': 'web_fetch', 'observation': {
            'status': 'retrieved', 'url': url, 'text_file': path, 'text_artifact_id': artifact['artifact_id'],
            'format': 'pdf' if kind == 'paper' else 'text'}}}
        reads = []
        for offset in ([0, 6000] if kind == 'paper' else [0]):
            eid = kind + str(offset)
            reads.append(eid)
            records[eid] = {'assignment_id': 'owner', 'receipt': {'tool': 'read_file',
                'argument': json.dumps({'path': path, 'offset': offset, 'limit': 6000}),
                'observation': {'text': raw[offset:offset + 6000].decode()}}}
        sources.append({'id': kind, 'kind': kind, 'url': url, 'fetch_evidence_id': kind,
            'read_evidence_ids': reads, 'discovery_evidence_id': 'discovery', 'discovery_term': term,
            'sections_read': ['method'], 'finding': 'finding', 'decision': 'test', 'limitations': 'bounded'})
    snapshot['sources.json'] = json.dumps({'sources': sources})
    team = SimpleNamespace(artifact_store=store, state={'artifacts': artifacts}, evidence_record=records.__getitem__)
    return team, snapshot, records


def test_original_paper_body_and_pinned_code_are_accepted(tmp_path):
    team, snapshot, _ = delivery(tmp_path)
    assert source_verdict(team, snapshot, 'owner')['accepted']


@pytest.mark.parametrize('fault', ['rewritten', 'fake_read', 'wrong_owner', 'metadata', 'missing_discovery','duplicate_window'])
def test_source_gate_rejects_unsupported_provenance(tmp_path, fault):
    team, snapshot, records = delivery(tmp_path)
    if fault == 'rewritten': snapshot['paper.txt'] = 'agent-authored summary'
    elif fault == 'fake_read': records['paper6000']['receipt']['observation']['text'] = 'claimed full reading'
    elif fault == 'wrong_owner': records['paper']['assignment_id'] = 'someone-else'
    elif fault == 'metadata': records['paper']['receipt']['observation']['format'] = 'search_metadata'
    elif fault=='duplicate_window':
        rows=json.loads(snapshot['sources.json']);rows['sources'][0]['read_evidence_ids']=['paper0','paper0']
        snapshot['sources.json']=json.dumps(rows)
    else: records['discovery']['receipt']['observation']['text_excerpt'] = 'unrelated result'
    assert not source_verdict(team, snapshot, 'owner')['accepted']
