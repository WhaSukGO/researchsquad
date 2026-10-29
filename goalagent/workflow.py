"""Host-enforced workflow proposals. Models never write gate verdicts or charters."""
from __future__ import annotations

import copy
from .contracts import digest
from .reports import text, strings

DECISIONS = {'ADVANCE', 'REVISE', 'WAIT_EXTERNAL', 'STOP', 'ESCALATE'}


def load_workflow(spec):
    if spec is None:
        spec = {'mode': 'research', 'stages': [{'id': 'research', 'description': 'Investigate, implement, measure and report',
                 'gates': [{'id': 'objective', 'kind': 'evaluation', 'criterion': 'Protected evaluator accepts the submitted candidate', 'accepted': True}]}]}
    spec = copy.deepcopy(spec)
    managed = isinstance(spec,dict) and spec.get('policy_version') == 2
    allowed = {'mode','stages','policy_version','role_bindings','work_policy','completion_stage'} if managed else {'mode','stages'}
    if not isinstance(spec, dict) or set(spec)-allowed or not {'mode','stages'} <= set(spec) or spec['mode'] not in {'research', 'product'}:
        raise ValueError('workflow requires mode and stages')
    if managed:
        bindings=spec.get('role_bindings')
        if not isinstance(bindings,dict) or not bindings or any(not isinstance(k,str) or not isinstance(v,str) for k,v in bindings.items()):
            raise ValueError('Managed workflow requires role_bindings')
        policy={'max_attempts':3,'checkpoint_interval':8,'coordinator_checkpoint_interval':1,**spec.get('work_policy',{})}
        if set(policy)!={'max_attempts','checkpoint_interval','coordinator_checkpoint_interval'} or any(type(v) is not int or not 1<=v<=1000 for v in policy.values()):
            raise ValueError('Invalid managed work policy')
        spec['work_policy']=policy
    if not isinstance(spec['stages'], list) or not spec['stages']:
        raise ValueError('workflow stages are required')
    stage_ids, gate_ids = set(), set()
    for stage in spec['stages']:
        fields={'id','description','gates','owner','required_reviewers','required_outputs','required_tools','required_candidates','report_paths','review_scopes'} if managed else {'id','description','gates'}
        if not isinstance(stage, dict) or set(stage)-fields or not {'id','description','gates'} <= set(stage):
            raise ValueError('Each stage requires id, description and gates')
        text(stage['id'], 'stage id', 64); text(stage['description'], 'stage description')
        if stage['id'] in stage_ids: raise ValueError('Duplicate stage')
        stage_ids.add(stage['id'])
        if managed:
            text(stage.get('owner'),'stage owner')
            for name in ('required_reviewers','required_outputs','required_tools','required_candidates','report_paths'):
                values=strings(stage.get(name,[]),name,64)
                if len(set(values))!=len(values):raise ValueError('Duplicate '+name)
                stage[name]=values
            scopes=stage.get('review_scopes',{})
            if not isinstance(scopes,dict) or set(scopes)-set(stage['required_reviewers']) or any(v not in {'full','report_only'} for v in scopes.values()):
                raise ValueError('Invalid reviewer scope')
            stage['review_scopes']=scopes
            for role in stage['required_reviewers']:
                gate={'id':stage['id']+'-review-'+role,'kind':'review',
                      'criterion':'Independent '+role+' review of this frozen stage submission',
                      'reviewers':[spec['role_bindings'].get(role,role)]}
                if any(g.get('id')==gate['id'] for g in stage['gates']):raise ValueError('Reserved managed review gate ID')
                stage['gates'].append(gate)
        if not isinstance(stage['gates'], list) or not stage['gates']: raise ValueError('Stage requires gates')
        for gate in stage['gates']:
            if not isinstance(gate, dict) or set(gate) - {'id', 'kind', 'criterion', 'path', 'accepted', 'reviewers'}:
                raise ValueError('Invalid gate fields')
            text(gate.get('id'), 'gate id', 64); text(gate.get('criterion'), 'criterion')
            if gate['id'] in gate_ids: raise ValueError('Duplicate gate')
            gate_ids.add(gate['id'])
            if gate.get('kind') not in {'artifact', 'evaluation', 'review', 'external'}: raise ValueError('Unknown gate kind')
            if gate['kind'] == 'artifact': text(gate.get('path'), 'required artifact path')
            if gate['kind'] == 'review': strings(gate.get('reviewers'), 'reviewers')
            if 'accepted' in gate and type(gate['accepted']) is not bool: raise ValueError('accepted must be boolean')
    if managed and spec.get('completion_stage',spec['stages'][-1]['id']) not in stage_ids:
        raise ValueError('Unknown managed completion stage')
    return spec


def initial_state(spec):
    return {'run_status': 'READY', 'state_revision': 0, 'stage': spec['stages'][0]['id'],
            'candidate': None, 'candidate_revision': None, 'gates': [], 'decisions': [], 'reviews': [],
            'external': {}, 'pending_external': None, 'no_evidence_cycles': 0, 'progress_fingerprint': None}


def gates(team, candidate):
    workflow = team.state['workflow']
    stage = next(s for s in team.workflow_spec['stages'] if s['id'] == workflow['stage'])
    entry = team.state['assignments'].get(candidate, {})
    revision = entry.get('candidate_revision')
    result = []
    for rule in stage['gates']:
        status, evidence = 'UNKNOWN', []
        if rule['kind'] == 'artifact' and entry.get('outcome', {}).get('status') == 'submitted':
            # This gate proves file delivery only, never semantic quality.
            matches = [a for a in entry.get('submitted_artifact_ids', []) if team.state['artifacts'][a]['path'] == rule['path']]
            if matches:
                for artifact_id in matches: team.artifact_store.read(team.state['artifacts'][artifact_id])
                status, evidence = 'PASS', [entry['receipt_id']]
        if rule['kind'] == 'evaluation' and candidate in team.state['evaluations']:
            team.verify_submission(candidate)
            measured = team.effective_evaluation(candidate)
            record = team.state.get('acceptances',{}).get(candidate,{}).get('evidence_id','evaluation-' + candidate)
            team.evidence_record(record)
            status = 'PASS' if 'accepted' not in rule or measured['accepted'] == rule['accepted'] else 'FAIL'
            evidence = [record]
        if rule['kind'] == 'review':
            reviews = [r for r in workflow['reviews'] if r['gate_id'] == rule['id'] and r['candidate'] == candidate and r['candidate_revision'] == revision]
            if reviews:
                latest = reviews[-1]
                team.evidence_record(latest['evidence_id'])
                status, evidence = latest['verdict'], [latest['evidence_id']]
        if rule['kind'] == 'external':
            event = workflow['external'].get(rule['id'])
            if event and event['candidate'] == candidate and event['candidate_revision'] == revision:
                for artifact_id in event['artifact_ids']: team.artifact_store.read(team.state['artifacts'][artifact_id])
                status, evidence = event['verdict'], [event['evidence_id']]
        result.append({'gate_id': rule['id'], 'criterion': rule['criterion'], 'kind': rule['kind'],
                       'status': status, 'candidate': candidate, 'candidate_revision': revision, 'evidence_ids': evidence})
    if getattr(team,'managed',None):
        result.extend(team.managed.extra_gates(candidate))
    return result


def decide(team, agent, data, dispatch_id):
    if not isinstance(data, dict) or set(data) - {'decision', 'state_revision', 'candidate', 'target_stage', 'rationale', 'evidence_ids', 'owner', 'resume_when'}:
        raise ValueError('Invalid decision fields')
    workflow = team.state['workflow']
    for record in workflow['decisions']:
        if record['decision_id'] == dispatch_id: return record
    if data.get('state_revision') != workflow['state_revision']: raise ValueError('Stale decision snapshot; read project_state')
    kind = data.get('decision')
    if kind not in DECISIONS: raise ValueError('Unknown transition')
    text(data.get('rationale'), 'rationale')
    evidence = strings(data.get('evidence_ids', []), 'evidence_ids', 32)
    for item in evidence: team.evidence_record(item)
    candidate = data.get('candidate', workflow['candidate'])
    if candidate is not None and candidate not in team.state['assignments']: raise ValueError('Unknown candidate')
    if candidate:
        team.verify_submission(candidate)
    checked = gates(team, candidate)
    stages = [s['id'] for s in team.workflow_spec['stages']]
    current = stages.index(workflow['stage'])
    target = data.get('target_stage', workflow['stage'])
    if target not in stages: raise ValueError('Unknown target stage')
    next_status = 'ACTIVE'
    if kind == 'ADVANCE':
        if any(g['status'] != 'PASS' for g in checked): raise ValueError('Required gates are not all PASS')
        final = stages.index(team.workflow_spec.get('completion_stage', stages[-1]))
        if current == final:
            if target != workflow['stage']:raise ValueError('Cannot advance beyond the configured completion scope')
            # Valid negative research can succeed only if the owner-supplied evaluator accepts it.
            if final == len(stages)-1 and (candidate not in team.state['evaluations'] or not team.effective_evaluation(candidate)['accepted']):
                raise ValueError('Project completion requires protected acceptance of this candidate')
            next_status = 'COMPLETED'
        else:
            expected = stages[current + 1]
            if 'target_stage' in data and target != expected: raise ValueError('Cannot skip a workflow stage')
            target = expected
    elif kind == 'REVISE':
        if stages.index(target) > current: raise ValueError('Revision cannot skip forward')
        text(data.get('owner'), 'revision owner'); text(data.get('resume_when'), 'verification condition')
    elif kind in {'WAIT_EXTERNAL', 'ESCALATE'}:
        text(data.get('owner'), 'owner'); text(data.get('resume_when'), 'resume_when')
        next_status = 'WAITING_EXTERNAL' if kind == 'WAIT_EXTERNAL' else 'ESCALATED'
    elif kind == 'STOP':
        next_status = 'STOPPED'
    if getattr(team,'managed',None):team.managed.validate_decision(kind,candidate,data)
    fingerprint = digest({'artifacts': sorted(team.state['artifacts']), 'evaluations': team.state['evaluations'],
                          'candidate': candidate, 'gates': checked, 'stage': target})
    workflow['no_evidence_cycles'] = workflow['no_evidence_cycles'] + 1 if workflow['progress_fingerprint'] == fingerprint else 0
    workflow['progress_fingerprint'] = fingerprint
    record = {**data, 'decision_id': dispatch_id, 'stage': workflow['stage'], 'target_stage': target,
              'candidate': candidate, 'candidate_revision': team.state['assignments'].get(candidate, {}).get('candidate_revision'),
              'gates': checked, 'no_evidence_cycles': workflow['no_evidence_cycles']}
    workflow['decisions'].append(record)
    workflow.update(run_status=next_status, stage=target, candidate=candidate, candidate_revision=record['candidate_revision'])
    workflow['state_revision'] += 1
    # Historical gate decisions stay in records; the active stage is evaluated afresh.
    workflow['gates'] = gates(team, candidate)
    if kind in {'WAIT_EXTERNAL', 'ESCALATE'}:
        workflow['pending_external'] = {'request_id': dispatch_id, 'owner': data['owner'], 'resume_when': data['resume_when']}
    team.event('decision', record)
    if getattr(team,'managed',None):team.managed.after_decision(kind,record)
    if next_status != 'ACTIVE':
        agent.state['status'] = {'WAITING_EXTERNAL': 'waiting_external', 'ESCALATED': 'escalated', 'STOPPED': 'stopped', 'COMPLETED': 'completed'}[next_status]
        agent.save()
    return record
