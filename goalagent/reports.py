"""Assignment reports are separate from tool actions and project completion."""
FAILURES = {'environment', 'implementation', 'measurement', 'performance', 'missing_input', 'interrupted', 'other'}


def text(value, name, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name} must be nonempty text, at most {maximum} characters')
    return value


def strings(value, name, maximum=16):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f'{name} must be a list of at most {maximum} strings')
    return [text(item, name) for item in value]


def validate_progress(data):
    if not isinstance(data, dict) or set(data) - {'summary', 'findings', 'failures', 'next_test', 'files'}:
        raise ValueError('Invalid checkpoint fields')
    result = {'summary': text(data.get('summary'), 'summary'),
              'findings': strings(data.get('findings', []), 'findings'),
              'failures': strings(data.get('failures', []), 'failures'),
              'next_test': text(data.get('next_test'), 'next_test'), 'files': data.get('files', [])}
    if not isinstance(result['files'], list) or any(not isinstance(p, str) for p in result['files']):
        raise ValueError('files must contain relative paths')
    return result


def validate_report(data, evidence_ids=(), targets=()):
    allowed = {'status', 'summary', 'files', 'claims', 'objections', 'next_actions', 'open_questions', 'failure_kind'}
    if not isinstance(data, dict) or set(data) - allowed or data.get('status') not in {'DONE', 'NEEDS_INPUT', 'FAILED'}:
        raise ValueError('Report requires status DONE, NEEDS_INPUT or FAILED')
    text(data.get('summary'), 'summary')
    if not isinstance(data.get('files'), list) or len(data['files'])>256 or any(not isinstance(path,str) for path in data['files']):
        raise ValueError('Report requires a files list (empty is allowed for blocked work)')
    if data.get('failure_kind') is not None and data['failure_kind'] not in FAILURES:
        raise ValueError('Unknown failure kind')
    if data['status'] == 'FAILED' and not data.get('failure_kind'):
        raise ValueError('FAILED reports require failure_kind')
    known = set(evidence_ids)
    for name in ('claims', 'objections', 'next_actions'):
        if not isinstance(data.get(name, []), list) or len(data.get(name, [])) > 32:
            raise ValueError(f'Invalid {name}')
    for claim in data.get('claims', []):
        if not isinstance(claim, dict) or set(claim) != {'statement', 'epistemic_status', 'evidence_ids', 'limitations'}:
            raise ValueError('Claims require statement, epistemic_status, evidence_ids, limitations')
        text(claim['statement'], 'claim'); text(claim['limitations'], 'limitations')
        if claim['epistemic_status'] not in {'observed', 'inferred', 'hypothesis', 'unknown'}:
            raise ValueError('Invalid claim status')
        ids = strings(claim['evidence_ids'], 'evidence_ids', 32)
        if not set(ids) <= known:
            raise ValueError('Unknown claim evidence')
        if claim['epistemic_status'] in {'observed', 'inferred'} and not ids:
            raise ValueError('Observed/inferred claims require registered evidence')
    for objection in data.get('objections', []):
        if not isinstance(objection, dict) or set(objection) != {'target_id', 'category', 'severity', 'statement', 'evidence_ids', 'resolution_test'}:
            raise ValueError('Invalid objection fields')
        if objection['target_id'] not in targets:
            raise ValueError('Unknown objection target')
        if objection['category'] not in {'FACT', 'FEASIBILITY', 'EXPERIENCE', 'RESOURCE', 'OBJECTIVE', 'AUTHORIZATION'} or objection['severity'] not in {'BLOCKER', 'MAJOR', 'MINOR'}:
            raise ValueError('Invalid objection category/severity')
        text(objection['statement'], 'objection'); text(objection['resolution_test'], 'resolution_test')
        if not set(strings(objection['evidence_ids'], 'evidence_ids', 32)) <= known:
            raise ValueError('Unknown objection evidence')
    for item in data.get('next_actions', []):
        if not isinstance(item, dict) or set(item) != {'action', 'owner', 'expected_information', 'acceptance_check', 'requires_external'}:
            raise ValueError('Invalid next action')
        for field in ('action', 'owner', 'expected_information', 'acceptance_check'):
            text(item[field], field)
        if type(item['requires_external']) is not bool:
            raise ValueError('requires_external must be boolean')
    strings(data.get('open_questions', []), 'open_questions', 32)
    return data


def assignment_requirements(data):
    outputs=data.get('required_outputs',[])
    checks=data.get('acceptance_checks',[])
    for name,items in [('required_outputs',outputs),('acceptance_checks',checks)]:
        if not isinstance(items,list) or len(items)>32:raise ValueError(f'Invalid {name}')
    for item in outputs:
        if not isinstance(item,dict) or set(item)!={'path','kind','description'}:raise ValueError('Outputs require path, kind, description')
        for key in item:text(item[key],key)
    if len({item['path'] for item in outputs})!=len(outputs):raise ValueError('Duplicate required output')
    for item in checks:
        if not isinstance(item,dict) or set(item)!={'check_id','description','required_evidence_kind'}:raise ValueError('Invalid acceptance check')
        text(item['check_id'],'check_id');text(item['description'],'description')
        if item['required_evidence_kind'] not in {'source','tool_result','observation','decision_record','simulation'}:raise ValueError('Invalid required evidence kind')
    return outputs,checks
