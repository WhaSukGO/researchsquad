"""Receipt validation is narrower than semantic truth or scientific acceptance."""
from __future__ import annotations


def successful(receipt):
    observation = receipt.get('observation')
    if not isinstance(observation, dict):
        return True
    if 'error' in observation or observation.get('interrupted'):
        return False
    if observation.get('exit_code', 0) != 0:
        return False
    result = observation.get('result')
    if isinstance(result, dict) and (result.get('exit_code', 0) != 0 or result.get('interrupted')):
        return False
    return observation.get('status') not in {'test_failed', 'environment_blocked', 'access_blocked', 'retrieval_failed',
        'FAILED','CANCELLED','LOST','START_FAILED','START_UNCERTAIN'}


def validate_claims(team, report, assignment):
    receipts = {}
    for eid in team.state['evidence']:
        if eid.startswith('action-'):
            record = team.evidence_record(eid)
            if successful(record['receipt']):
                receipts[eid] = record
    actions = {'searched': {'web_search'}, 'read': {'web_fetch', 'read_file', 'read_artifact', 'read_evidence'},
               'executed': {'run'}, 'image_received': {'view_image'},
               'job_started':{'start_job','resume_job'},'job_completed':{'job_status','await_job'}}
    for action in report.get('execution_records', []):
        matches = [receipts.get(eid) for eid in action['evidence_ids']]
        if not matches or any(not r or r['assignment_id'] != assignment['task_id'] or
                r['receipt']['tool'] not in actions[action['action']] for r in matches):
            raise ValueError('Execution assertion requires successful actions by this assignment')
        if not any(r.get('target') == action['target'] for r in matches):
            raise ValueError('Execution assertion target does not match receipt')
        if action['action']=='job_completed' and not all(r['receipt']['observation'].get('status')=='SUCCEEDED' for r in matches):
            raise ValueError('Job completion requires an observed SUCCEEDED job, not a start receipt')
    delivered = {v['artifact_id'] for v in assignment.get('inputs', {}).values()}
    delivered.update(assignment.get('parent_artifacts', []))
    for claim in report.get('claims', []):
        if claim['epistemic_status'] != 'observed':
            continue
        if claim.get('scope') == 'empirical':
            if not any(eid in receipts for eid in claim['evidence_ids']):
                raise ValueError('Observed empirical claim needs successful source/execution evidence')
        else:
            supported = False
            for eid in claim['evidence_ids']:
                record = team.evidence_record(eid)
                if eid in receipts or set(record.get('artifact_ids', [])) & delivered:
                    supported = True
                if record.get('assignment_id') == assignment.get('review_of'):
                    supported = True
                if any(r.get('evidence_id')==eid and r.get('reviewer_assignment')==assignment.get('task_id')
                       and r.get('candidate')==assignment.get('review_of') for r in team.state['workflow']['reviews']):
                    supported = True
            if not supported:
                raise ValueError('Observed document claim needs evidence for delivered material')
