"""Durable work, owned by Team's existing state/event writer (not a second DB)."""
from __future__ import annotations

import copy
from .contracts import digest
from .reports import text, strings

STATES = {'QUEUED', 'READY', 'RUNNING', 'CHECKPOINTED', 'SUBMITTED',
          'IN_REVIEW', 'REWORK', 'WAITING', 'DONE', 'STALE'}
KINDS = {'owner', 'support', 'review', 'environment'}


class WorkBoard:
    def __init__(self, team):
        self.team = team
        state = team.state.setdefault('managed', {})
        state.setdefault('work', {})
        state.setdefault('epochs', {})
        state.setdefault('candidates', {})
        state.setdefault('candidate_decisions', [])
        self.state = state

    @property
    def jobs(self):
        return self.state['work']

    def add(self, *, key, owner, objective, acceptance_check, stage, kind='support',
            inputs=None, required_outputs=None, required_tools=(), depends_on=(),
            blocking=True, **metadata):
        external = owner in {'operator','executor'}
        if kind not in KINDS or owner not in self.team.definitions and not external:
            raise ValueError('Work needs a configured owner and known kind')
        text(objective, 'work objective', 8000)
        text(acceptance_check, 'work acceptance', 8000)
        if type(blocking) is not bool:
            raise ValueError('Work blocking must be boolean')
        if not set(depends_on) <= set(self.jobs):
            raise ValueError('Unknown work dependency')
        old = next((j for j in self.jobs.values() if j['key'] == key), None)
        if old:
            return old
        if not external and not set(required_tools) <= set(self.team.definitions[owner]['tools']):
            raise ValueError('Work owner lacks required tools')
        wid = f'W-{len(self.jobs)+1:04}'
        job = {'work_id': wid, 'key': key, 'owner': owner, 'objective': objective,
               'acceptance_check': acceptance_check, 'stage': stage, 'kind': kind,
               'inputs': dict(inputs or {}), 'required_outputs': list(required_outputs or []),
               'required_tools': list(required_tools), 'depends_on': list(depends_on),
               'blocking': blocking, 'status': 'WAITING' if external else 'QUEUED', 'attempts': [],
               'feedback': ['External owner must supply the stated result and verification'] if external else [],
               'assignment_id': None, 'checkpoint_id': None, 'result_artifact_ids': [],
               'epoch': self.state['epochs'].get(stage, 0), **metadata}
        self.jobs[wid] = job
        self.team.event('work_created', copy.deepcopy(job))
        return job

    def reference(self, work_id):
        if work_id not in self.jobs:
            raise ValueError('Unknown work ID')
        return self.jobs[work_id]

    def depend(self, work_id, dependency):
        job = self.reference(work_id)
        self.reference(dependency)
        def ancestors(wid):
            result = set()
            for parent in self.jobs[wid]['depends_on']:
                result.add(parent)
                result.update(ancestors(parent))
            return result
        if work_id == dependency or work_id in ancestors(dependency):
            raise ValueError('Cyclic work dependency')
        if dependency not in job['depends_on']:
            job['depends_on'].append(dependency)
        self.team.event('work_dependency', {'work_id': work_id, 'depends_on': dependency})

    def set_status(self, job, status, reason=None):
        if status not in STATES:
            raise ValueError('Unknown work status')
        job['status'] = status
        if reason:
            job['feedback'].append(reason)
            job['feedback'] = job['feedback'][-12:]
        self.team.event('work_status', {'work_id': job['work_id'], 'status': status, 'reason': reason})

    def ready(self, stage):
        eligible = []
        for job in self.jobs.values():
            if job['stage'] != stage or job['status'] not in {'QUEUED', 'READY', 'REWORK', 'CHECKPOINTED'}:
                continue
            if all(self.jobs[dep]['status'] == 'DONE' for dep in job['depends_on']):
                eligible.append(job)
        priority = {'environment': 0, 'support': 1, 'owner': 2, 'review': 3}
        return sorted(eligible, key=lambda j: (not j['blocking'],
            0 if j['status'] == 'REWORK' else 1, priority[j['kind']], j['work_id']))

    def pending(self, stage):
        return [j for j in self.jobs.values() if j['stage'] == stage and j['blocking']
                and j['status'] not in {'DONE', 'STALE'}]

    def summary(self, limit=32):
        return [{k: j[k] for k in ('work_id', 'owner', 'objective', 'stage', 'kind', 'status',
                  'blocking', 'assignment_id', 'checkpoint_id', 'depends_on', 'feedback')}
                for j in list(self.jobs.values())[-limit:]]

    def add_report_work(self, report, source):
        """Only typed work_items dispatch. next_actions remain readable proposals."""
        created = []
        for item in report.get('work_items', []):
            existing = item.get('existing_work_id')
            if existing:
                job = self.reference(existing)
                if job['stage'] != source['stage']:
                    raise ValueError('Work reference belongs to another stage')
                created.append(job)
                continue
            owner = item['owner']
            binding = self.team.workflow_spec['role_bindings']
            owner = binding.get(owner, owner)
            required = item['required_tools']
            if owner not in self.team.definitions or not set(required) <= set(self.team.definitions[owner]['tools']):
                owner=next((r for r,c in self.team.definitions.items() if set(required)<=set(c['tools'])), 'operator') if required else 'operator'
            inputs = item['input_artifact_ids'] or source['result_artifact_ids']
            if not set(inputs) <= set(self.team.state['artifacts']):
                raise ValueError('Work references an unknown artifact')
            mapped = {f'item-{n}/'+self.team.state['artifacts'][aid]['path']: aid for n, aid in enumerate(inputs)}
            key = digest([source['stage'], owner, ' '.join(item['objective'].split()).casefold()])
            job = self.add(key='report-'+key, owner=owner, objective=item['objective'],
                acceptance_check=item['acceptance_check'], stage=source['stage'], inputs=mapped,
                required_tools=required, blocking=item['blocking'], source_work=source['work_id'])
            created.append(job)
        return created
