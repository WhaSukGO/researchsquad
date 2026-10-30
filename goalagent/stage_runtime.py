"""One sequential scheduler over the reusable Agent, explicit work and frozen gates."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

from .contracts import atomic_json, digest
from .claim_checks import successful, validate_claims
from .workboard import WorkBoard
from . import workflow


class StageRuntime:
    def __init__(self, team):
        self.team = team
        self.board = WorkBoard(team)
        self.spec = team.workflow_spec
        self.role('auditor')
        self.role('environment')
        for stage in self.spec['stages']:
            owner = self.role(stage['owner'])
            if not set(stage['required_tools']) <= set(team.definitions[owner]['tools']):
                raise ValueError('Stage owner lacks required tools')
            for role in stage['required_reviewers']:
                config = team.definitions[self.role(role)]
                if 'review_gate' not in config['tools']:
                    raise ValueError('Required reviewer needs review_gate grant')
                if stage['review_scopes'].get(role) == 'report_only':
                    if set(config['tools']) - {'read_file','view_image','checkpoint','submit_report','review_gate'}:
                        raise ValueError('Report-only reviewer has excessive tool grants')
                    if not stage['report_paths']:
                        raise ValueError('Report-only reviewer needs report_paths')
        for job in self.board.jobs.values():
            if job['status'] == 'RUNNING':
                job['status'] = 'CHECKPOINTED'
        team.save()

    def role(self, name):
        result = self.spec['role_bindings'].get(name, name)
        if result not in self.team.definitions:
            raise ValueError('Managed workflow references missing role: '+name)
        return result

    def stage(self):
        return next(s for s in self.spec['stages'] if s['id'] == self.team.state['workflow']['stage'])

    def host(self):
        folder = self.team.folder/'agents'/'lead'
        workspace = folder/'workspace'
        workspace.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(folder=folder, workspace=workspace, assignment={'depth':0}, state={'steps':0})

    def context(self, assignment):
        if assignment.get('review_scope') == 'report_only':
            return {'review_scope':'report_only', 'candidate_receipt_id':assignment['candidate_receipt_id']}
        if assignment.get('review_of'):
            return {'review_scope':'full','candidate_receipt_id':assignment['candidate_receipt_id'],
                    'current_work':copy.deepcopy(self.board.jobs.get(assignment.get('work_id'))),
                    'stage':assignment['stage']}
        return {'run_id':self.team.folder.name, 'workflow':copy.deepcopy(self.team.state['workflow']),
                'definition':self.spec, 'work':self.board.summary(),
                'current_work':self.board.jobs.get(assignment.get('work_id')),
                'candidate_decisions':self.board.state['candidate_decisions'][-24:],
                'goal_met':self.team.state['goal_met']}

    def instructions(self, assignment):
        common = """
Managed workflow policy version 2 is active. The host dispatches required work.
Use the SAME Agent loop: write files, run tools and inspect actual outputs before
submit_report. Saving code and executing it are steps of the same work ID.
Each claim has scope=document or empirical. Attribute another worker's measurement;
do not call reading a report an independent execution. execution_records entries
{action:searched|read|executed|image_received|job_started|job_completed,target,evidence_ids} must match your
successful action receipts. Copy the target from that receipt.
job_completed requires an observed SUCCEEDED job_status/await_job receipt; a started job is not completed training.
Optional report work_items have {existing_work_id,owner,objective,input_artifact_ids,
required_tools,acceptance_check,blocking}. Use an existing W-ID when referring to
the same job, and an empty existing_work_id only for new work. Missing data or
capabilities require concrete work or NEEDS_INPUT, never invented observations.
candidate_decisions entries have {candidate,decision:SELECTED|REJECTED|DEFERRED|
UNTESTED,reason,evidence_ids,followup_action}. Record every required named candidate.
DEFERRED/UNTESTED require a concrete next action. SELECTED does not mean measured winner.
next_actions are recorded proposals; only typed work_items request additional dispatch.
"""
        if assignment.get('review_of'):
            common += "\nThis is an independent review. Inspect the frozen candidate, call review_gate, then submit_report. A FAIL is a valid review result. Do not change the candidate or approve other gates. "
            common += 'The review_gate candidate field is the assignment ID '+assignment['review_of']+'. '
            common += 'The different receipt ID '+assignment['candidate_receipt_id']+' belongs in evidence_ids. '
            common += 'Copy this call shape, changing only verdict/summary and adding inspected evidence: '+json.dumps({
                'gate_id':assignment['acceptance_checks'][0]['check_id'],'candidate':assignment['review_of'],
                'verdict':'PASS|FAIL|UNKNOWN','evidence_ids':[assignment['candidate_receipt_id']],
                'summary':'Your scoped findings'})+'\n'
        if assignment.get('review_scope') == 'report_only':
            return ("\nRead ONLY the delivered report and terminology. Read the exact workspace paths in assignment.review_files: "
                    +json.dumps(assignment['review_files'])+". Artifact IDs are not file paths. Do not reconstruct earlier conversations, inspect code or fetch global evidence. Report comprehension gaps, ambiguous responsibility, scope and unsupported presentation.\n" + common)
        if assignment.get('depth') == 0:
            common += "\ndelegate and continue_assignment QUEUE work; they do not synchronously execute children in managed mode. The host runs one period and returns results. Read project_state, use the host-selected current candidate for decisions, and do not bypass required owners/reviewers. propose_decision ADVANCE requires all gates; REVISE needs owner and resume_when. A measured but inaccurate parent uses improve, failed execution uses debug, and a submitted parent rejected by review uses revise.\n"
        return common

    def validate_report(self, report, assignment):
        if any('scope' not in c for c in report.get('claims', [])):
            raise ValueError('Managed claims require document/empirical scope')
        validate_claims(self.team, report, assignment)
        for item in report.get('work_items', []):
            if item['existing_work_id']:
                self.board.reference(item['existing_work_id'])
            if not set(item['input_artifact_ids']) <= set(self.team.state['artifacts']):
                raise ValueError('Unknown work input')

    def seed(self):
        stage = self.stage()
        epoch = self.board.state['epochs'].get(stage['id'], 0)
        inputs = dict(self.team.public_inputs)
        for sid, aid in self.board.state['candidates'].items():
            if sid == stage['id']:
                continue
            entry = self.team.state['assignments'][aid]
            for artifact in entry.get('submitted_artifact_ids', []):
                path = self.team.state['artifacts'][artifact]['path']
                inputs[f'prior-{sid}/'+path] = artifact
        outputs=list(stage['required_outputs'])
        if any(g['kind']=='evaluation' for g in stage['gates']):
            outputs=list(dict.fromkeys(outputs+self.team.task.get('submission_outputs',[])))
        return self.board.add(key=f"owner:{stage['id']}:{epoch}", owner=self.role(stage['owner']),
            objective=stage['description']+'. Deliver the required files and evidence; preserve unknowns.',
            acceptance_check='Deliver '+', '.join(stage['required_outputs'])+'; meet the frozen stage criteria and all independent reviews.',
            stage=stage['id'], kind='owner', inputs=inputs, required_outputs=outputs,
            required_tools=stage['required_tools'])

    def delegate(self, agent, action, timeout):
        if agent.assignment.get('depth',0) != 0:
            raise ValueError('Only the coordinator proposes new managed assignments')
        data = json.loads(action['argument'])
        allowed = {'agent','objective','success_criteria','inputs','input_artifact_ids','parent','mode',
                   'review_of','required_outputs','acceptance_checks','work_id','review_scope','report_paths'}
        if not isinstance(data,dict) or set(data)-allowed:
            raise ValueError('Unknown managed assignment fields')
        if data.get('work_id'):
            job = self.board.reference(data['work_id'])
            if job['owner'] != data['agent'] or job['stage'] != self.stage()['id']:
                raise ValueError('Existing work identity/owner must be preserved')
            if job['status'] in {'DONE','STALE'}:
                raise ValueError('Work is already complete or superseded')
            job['blocking'] = True
            return {'status':'QUEUED','work_id':job['work_id'],'assignment_id':job['assignment_id']}
        dispatch = self.team.dispatch_id(agent,action)
        old = next((j for j in self.board.jobs.values() if j['key']=='delegate:'+dispatch),None)
        if old:
            return {'status':'QUEUED','work_id':old['work_id'],'assignment_id':old['assignment_id']}
        aid, frozen_dispatch = self.team._delegate(agent,action,timeout,defer=True)
        entry = self.team.state['assignments'][aid]
        job = self.board.add(key='delegate:'+dispatch, owner=entry['agent'], objective=data['objective'],
            acceptance_check=data['success_criteria'], stage=self.stage()['id'], kind='support',
            required_outputs=[x['path'] for x in data.get('required_outputs',[])])
        job['assignment_id']=aid; job['dispatch_id']=frozen_dispatch; job['attempts'].append(aid)
        entry['assignment']['work_id']=job['work_id']
        atomic_json(self.team.folder/'tasks'/f'{aid}.json',entry['assignment'])
        self.team.event('managed_delegation',{'work_id':job['work_id'],'assignment_id':aid})
        return {'status':'QUEUED','work_id':job['work_id'],'assignment_id':aid}

    def continue_assignment(self, agent, action, timeout):
        data=json.loads(action['argument'])
        if not isinstance(data,dict) or set(data)!={'assignment_id','checkpoint_id','guidance'}:
            raise ValueError('Invalid continuation fields')
        from .reports import text
        text(data['guidance'],'continuation guidance')
        job=next((j for j in self.board.jobs.values() if j['assignment_id']==data['assignment_id']),None)
        if not job or job['status']!='CHECKPOINTED' or job['checkpoint_id']!=data['checkpoint_id']:
            raise ValueError('Only the current checkpoint can continue')
        entry=self.team.state['assignments'][job['assignment_id']]
        if entry['caller']!=str(agent.folder.relative_to(self.team.folder)):
            raise ValueError('Only the assigning coordinator can continue this work')
        job['feedback'].append(data['guidance'])
        self.team.event('continuation_queued',{'work_id':job['work_id']})
        return {'status':'QUEUED','work_id':job['work_id'],'assignment_id':job['assignment_id']}

    def _new_assignment(self, job):
        parent=job.get('parent_assignment')
        mode=job.get('retry_mode','explore') if parent else 'explore'
        data={'agent':job['owner'],'objective':job['objective'],
              'success_criteria':job['acceptance_check'],'work_id':job['work_id'],
              'input_artifact_ids':job['inputs'], 'mode':mode,
              'required_outputs':[{'path':p,'kind':'document','description':'Required work output'} for p in job['required_outputs']],
              'acceptance_checks':[{'check_id':job.get('gate_id',job['work_id']+'-review'),
                  'description':job['acceptance_check'],'required_evidence_kind':'decision_record'}]}
        if parent:data['parent']=parent
        if job['kind']=='review':
            data.update(review_of=job['review_of'], mode='explore',input_artifact_ids={},
                        review_scope=job.get('review_scope','full'),report_paths=job.get('report_paths',[]))
            data.pop('parent',None)
        dispatch='dispatch-'+digest([job['work_id'],len(job['attempts'])])[:24]
        action={'tool':'delegate','argument':json.dumps(data),'why':'Host-enforced work assignment'}
        aid,dispatch=self.team._delegate(self.host(),action,self.team.remaining(),defer=True,dispatch_override=dispatch)
        job['assignment_id']=aid;job['dispatch_id']=dispatch;job['attempts'].append(aid)
        self.team.event('work_dispatched',{'work_id':job['work_id'],'assignment_id':aid,'mode':mode})
        return aid

    def _period(self, job):
        if not job['assignment_id']:
            if len(job['attempts'])>=self.spec['work_policy']['max_attempts']:
                self.board.set_status(job,'WAITING','Rework attempt limit; a concrete operator decision is required')
                return
            self._new_assignment(job)
        aid=job['assignment_id'];entry=self.team.state['assignments'][aid]
        worker_path=self.team.folder/'agents'/aid/'worker-state.json'
        if worker_path.exists() and entry.get('active_dispatch'):
            worker=json.loads(worker_path.read_text())
            if worker['status']=='interrupted':
                worker['status']='running'
                atomic_json(worker_path,worker)
        continuation=None
        dispatch=entry.get('active_dispatch',job['dispatch_id'])
        if entry.get('outcome',{}).get('status')=='checkpointed' and 'active_dispatch' not in entry:
            dispatch='dispatch-'+digest([job['work_id'],aid,entry['periods']])[:24]
            continuation={'dispatch_id':dispatch,'guidance':'\n'.join(job['feedback']) or 'Continue the smallest useful test and submit required outputs.'}
        self.board.set_status(job,'RUNNING')
        receipt=self.team.execute_assignment(self.host(),aid,dispatch,continuation)
        self._returned(job,receipt)

    def _tool_records(self, aid):
        return [(eid,self.team.evidence_record(eid)) for eid in self.team.state['evidence']
                if eid.startswith('action-'+aid+'-')]

    def _host_fail(self, job, reason):
        aid=job['assignment_id'];entry=self.team.state['assignments'][aid]
        eid='host-check-'+digest([aid,reason])[:24]
        review={'gate_id':job['work_id']+'-execution','candidate':aid,
                'candidate_revision':entry['candidate_revision'],'verdict':'FAIL',
                'reviewer_assignment':'host','summary':reason,'evidence_id':eid}
        self.team.record(eid,review)
        if not any(r['evidence_id']==eid for r in self.team.state['workflow']['reviews']):
            self.team.state['workflow']['reviews'].append(review)
        self._rework(job,reason,'revise')

    def _rework(self, job, reason, mode='revise'):
        parent=job.get('assignment_id')
        for other in self.board.jobs.values():
            if other.get('source_work')==job['work_id'] and other['kind']=='review' and other['status']!='DONE':
                other['status']='STALE'
        job.update(parent_assignment=parent,retry_mode=mode,assignment_id=None,checkpoint_id=None)
        self.board.set_status(job,'REWORK',reason)

    def _returned(self, job, receipt):
        aid=receipt['assignment_id'];entry=self.team.state['assignments'][aid]
        status=entry['outcome']['status']
        job['checkpoint_id']=receipt['checkpoint_id'];job['result_artifact_ids']=entry.get('submitted_artifact_ids',[]) or entry.get('artifact_ids',[])
        if status=='checkpointed':
            self.board.set_status(job,'CHECKPOINTED')
            return
        report=entry['outcome'].get('report') or {}
        marker=aid+':'+entry['candidate_revision']
        if job.get('processed_report')!=marker:
            children=self.board.add_report_work(report,job)
            for child in children:
                if child['work_id']!=job['work_id'] and child['blocking']:
                    self.board.depend(job['work_id'],child['work_id'])
            for decision in report.get('candidate_decisions',[]):
                self.board.state['candidate_decisions'].append({**decision,'stage':job['stage'],
                    'epoch':job['epoch'],'assignment_id':aid,'work_id':job['work_id']})
            job['processed_report']=marker
        if status!='submitted':
            if status=='environment_blocked' and job['kind']!='environment':
                self._environment(job,entry['outcome'])
            else:
                self.board.set_status(job,'WAITING',report.get('summary') or entry['outcome'].get('uncertain_reason') or entry['outcome'].get('error') or status)
            return
        records=self._tool_records(aid)
        actual={r['receipt']['tool'] for _,r in records if successful(r['receipt'])}
        missing=set(job['required_tools'])-actual
        if missing:
            self._host_fail(job,'Missing actual required actions: '+', '.join(sorted(missing)))
            return
        if any(self.board.jobs[d]['status']!='DONE' for d in job['depends_on']):
            self.board.set_status(job,'WAITING','Required dependency work must finish before accepting this submission')
            return
        important=[o for o in report.get('objections',[]) if o['severity'] in {'MAJOR','BLOCKER'}]
        if important and job['kind'] not in {'review','environment'}:
            self._issues(job,important)
            self._host_fail(job,'Resolve important objections before accepting this work')
            return
        if job['kind']=='review':
            self._review_returned(job)
            return
        if job['kind']=='environment':
            if not self.team.state['environment'] or self.team.state['environment']['status']!='ready':
                self._host_fail(job,'Environment did not produce a ready capability receipt')
                return
            self.board.set_status(job,'DONE')
            self._wake()
            return
        if job['kind']=='owner':
            named={d['candidate'] for d in self.board.state['candidate_decisions'] if d['stage']==job['stage'] and d['epoch']==job['epoch']}
            missing=set(self.stage()['required_candidates'])-named
            if missing:
                self._host_fail(job,'Missing reasoned candidate decisions: '+', '.join(sorted(missing)))
                return
        self.board.set_status(job,'SUBMITTED')
        if job['kind']=='owner':
            self.board.state['candidates'][job['stage']]=aid
            self.team.state['workflow'].update(candidate=aid,candidate_revision=entry['candidate_revision'])
            stage=self.stage()
            rules=[(r,stage['id']+'-review-'+r,stage['review_scopes'].get(r,'full')) for r in stage['required_reviewers']]
        else:
            rules=[('auditor',job['work_id']+'-review','full')]
        if not rules:
            self.board.set_status(job,'DONE');self._wake();return
        for role,gate,scope in rules:
            reviewer=self.role(role)
            criterion=("Read only the report. Identify unclear actors, inputs, actions, results, scope and limitations; no code or experiment audit."
                       if scope=='report_only' else job['acceptance_check'])
            self.board.add(key='review:'+aid+':'+gate, owner=reviewer,
                objective='Independently review the frozen submission for '+gate,
                acceptance_check=criterion+'; submit an explicit PASS/FAIL/UNKNOWN through '+gate,
                stage=job['stage'],kind='review',review_of=aid,source_work=job['work_id'],gate_id=gate,
                review_scope=scope,report_paths=self.stage()['report_paths'] if scope=='report_only' else [])
        self.board.set_status(job,'IN_REVIEW')

    def _review_returned(self, job):
        entry=self.team.state['assignments'][job['review_of']]
        reviews=[r for r in self.team.state['workflow']['reviews'] if r['gate_id']==job['gate_id']
                 and r['candidate']==job['review_of'] and r['candidate_revision']==entry['candidate_revision']
                 and r['reviewer_assignment']==job['assignment_id']]
        if not reviews:
            self._host_fail(job,'Review report omitted its required review_gate verdict')
            return
        verdict=reviews[-1]
        self.board.set_status(job,'DONE')
        source=self.board.reference(job['source_work'])
        if source['assignment_id']!=job['review_of']:
            return
        report=self.team.state['assignments'][job['assignment_id']]['outcome'].get('report',{})
        important=[o for o in report.get('objections',[]) if o['severity'] in {'MAJOR','BLOCKER'}]
        if important:
            self._issues(source,important)
            self._host_fail(source,'Resolve the important review objections against their explicit resolution tests')
        elif verdict['verdict']=='FAIL':
            self._rework(source,verdict['summary'])
        elif verdict['verdict']=='UNKNOWN':
            self.board.set_status(source,'WAITING',verdict['summary'])
        else:
            siblings=[j for j in self.board.jobs.values() if j.get('source_work')==source['work_id']
                      and j.get('review_of')==job['review_of'] and j['kind']=='review']
            if all(j['status']=='DONE' for j in siblings):
                self.board.set_status(source,'DONE');self._wake()

    def _issues(self, source, objections):
        owners={'FACT':'research','FEASIBILITY':'engineering','EXPERIENCE':'experience',
                'RESOURCE':'strategy','OBJECTIVE':'strategy','AUTHORIZATION':'strategy'}
        entry=self.team.state['assignments'][source['assignment_id']]
        inputs={f'candidate/{self.team.state["artifacts"][a]["path"]}':a for a in entry.get('submitted_artifact_ids',[])}
        for objection in objections:
            key='issue:'+digest([source['work_id'],objection['statement'],objection['resolution_test']])
            issue=self.board.add(key=key,owner=self.role(owners[objection['category']]),
                objective=objection['statement'],acceptance_check=objection['resolution_test'],
                stage=source['stage'],inputs=inputs,source_work=source['work_id'])
            if issue['work_id']!=source['work_id']:
                self.board.depend(source['work_id'],issue['work_id'])

    def review_rules(self, gate_id):
        return [{'id':gate_id,'kind':'review','reviewers':[j['owner']]} for j in self.board.jobs.values()
                if j['kind']=='review' and j['gate_id']==gate_id and not gate_id.startswith(self.stage()['id']+'-review-')]

    def _environment(self, source, outcome):
        job=self.board.add(key='environment:'+source['assignment_id'],owner=self.role('environment'),
            objective='Resolve the observed missing capability. '+str(outcome.get('last_observation',{})),
            acceptance_check='prepare_environment returns ready after the required isolated smoke test; do not claim research accuracy.',
            stage=source['stage'],kind='environment',required_tools=['prepare_environment'],inputs=source['inputs'])
        self.board.depend(source['work_id'],job['work_id'])
        source['wait_kind']='environment'
        self.board.set_status(source,'WAITING','Awaiting '+job['work_id']+' for the observed environment failure')

    def _wake(self):
        for job in self.board.jobs.values():
            if job.get('wait_kind')=='training':
                entry=self.team.state['assignments'][job['assignment_id']]
                jid=entry.get('waiting_training_job')
                if jid and self.team.training.status(self.team.training.state['jobs'][jid])['status'] in {'RUNNING','STARTING'}:continue
                entry.pop('waiting_training_job',None);job.pop('wait_kind',None)
                self.board.set_status(job,'CHECKPOINTED');continue
            if job['status']=='WAITING' and job['depends_on'] and all(self.board.jobs[d]['status']=='DONE' for d in job['depends_on']):
                for dep in job['depends_on']:
                    for aid in self.board.jobs[dep]['result_artifact_ids']:
                        job['inputs']['work-'+dep+'/'+self.team.state['artifacts'][aid]['path']]=aid
                entry=self.team.state['assignments'].get(job['assignment_id'],{})
                if entry.get('outcome',{}).get('status')=='submitted':
                    self._host_fail(job,'Dependency results must be incorporated into a revised submission')
                else:self._rework(job,'Required input/capability work completed; preserve the original work ID','debug')

    def extra_gates(self, candidate):
        stage=self.stage();epoch=self.board.state['epochs'].get(stage['id'],0)
        expected=self.board.state['candidates'].get(stage['id'])
        pending=self.board.pending(stage['id'])
        gates=[{'gate_id':stage['id']+'-accountable-work','criterion':'All blocking work and required owners/reviewers complete',
            'kind':'work','status':'PASS' if not pending and candidate and candidate==expected else 'UNKNOWN',
            'candidate':candidate,'candidate_revision':self.team.state['assignments'].get(candidate,{}).get('candidate_revision'),
            'evidence_ids':[],'pending_work_ids':[j['work_id'] for j in pending]}]
        named={d['candidate'] for d in self.board.state['candidate_decisions'] if d['stage']==stage['id'] and d['epoch']==epoch}
        missing=set(stage['required_candidates'])-named
        if stage['required_candidates']:
            gates.append({'gate_id':stage['id']+'-candidate-decisions','kind':'source',
                'criterion':'Reasoned decisions for every required named method',
                'status':'UNKNOWN' if missing else 'PASS','candidate':candidate,'evidence_ids':[],
                'missing_candidates':sorted(missing)})
        return gates

    def validate_decision(self, kind, candidate, data):
        if kind=='ADVANCE' and candidate!=self.board.state['candidates'].get(self.stage()['id']):
            raise ValueError('Only the current stage owner submission can advance')
        if kind=='REVISE' and self.role(data['owner'])!=self.role(self.stage()['owner']):
            raise ValueError('Revision must preserve the stage owner')

    def after_decision(self, kind, record):
        if kind=='REVISE':
            target=record['target_stage']
            if target==record['stage']:
                source=next((j for j in self.board.jobs.values() if j['kind']=='owner' and j['assignment_id']==record['candidate']),None)
                if source:
                    if record['candidate'] in self.team.state['evaluations']:
                        self._rework(source,record['rationale'],'improve')
                    else:self._host_fail(source,'Coordinator requested a revised submission: '+record['rationale'])
                    self.board.state['candidates'].pop(target,None)
                    self.team.state['workflow'].update(candidate=None,candidate_revision=None)
                    self.team.event('managed_revision',{'stage':target,'work_id':source['work_id'],'reason':record['rationale']})
                    return
            target_index=[s['id'] for s in self.spec['stages']].index(target)
            affected={s['id'] for s in self.spec['stages'][target_index:]}
            for job in self.board.jobs.values():
                if job['stage'] in affected and job['kind'] in {'owner','review'}:job['status']='STALE'
            for sid in affected:
                self.board.state['epochs'][sid]=self.board.state['epochs'].get(sid,0)+1
                self.board.state['candidates'].pop(sid,None)
            self.team.state['workflow'].update(candidate=None,candidate_revision=None)
            self.team.event('managed_revision',{'stage':target,'reason':record['rationale']})

    def external_received(self, record):
        for job in self.board.jobs.values():
            if job['stage']==self.stage()['id'] and job['status']=='WAITING' and job['owner'] in {'operator','executor'}:
                verdict=record.get('gate_verdicts',{}).get(job['work_id'])
                if verdict=='PASS':
                    job['result_artifact_ids']=record['artifact_ids'];self.board.set_status(job,'DONE')
                continue
            if job['stage']==self.stage()['id'] and job['status']=='WAITING' and not job['depends_on']:
                for aid in record['artifact_ids']:
                    job['inputs']['external/'+self.team.state['artifacts'][aid]['path']]=aid
                if self.team.state['assignments'][job['assignment_id']].get('outcome',{}).get('status')=='submitted':
                    self._host_fail(job,'External material requires a revised submission under the original acceptance')
                elif self.team.state['assignments'][job['assignment_id']].get('outcome',{}).get('status')=='action_uncertain':
                    continue
                else:self._rework(job,'Trusted external input received; re-check original acceptance','debug')

    def _wait(self, reason):
        state=self.team.state['workflow']
        request='work-wait-'+digest([self.stage()['id'],state['state_revision'],reason])[:24]
        state.update(run_status='WAITING_EXTERNAL',pending_external={'request_id':request,'owner':'operator','resume_when':reason})
        state['state_revision']+=1
        self.team.event('managed_wait',{'request_id':request,'reason':reason})

    def run(self, lead_assignment):
        while self.team.state['workflow']['run_status']=='ACTIVE':
            maximum=self.team.task['budget']['max_calls']
            if self.team.remaining()<=1 or maximum is not None and self.team.state['calls']>=maximum:
                self.team.state['workflow']['run_status']='STOPPED'
                self.team.event('managed_budget_stop',{'reason':'Effort budget exhausted, not goal completion'})
                break
            self.seed();self._wake()
            ready=[j for j in self.board.ready(self.stage()['id']) if j['blocking']]
            if ready:
                entry=self.team.state['assignments'].get(ready[0]['assignment_id'],{})
                if entry.get('waiting_training_job'):
                    ready[0]['wait_kind']='training';self.board.set_status(ready[0],'WAITING');continue
                try:self._period(ready[0])
                except (OSError,ValueError,RuntimeError) as error:
                    self.board.set_status(ready[0],'WAITING',str(error))
                continue
            blocked=[j for j in self.board.pending(self.stage()['id']) if j['status']=='WAITING' and j.get('wait_kind')!='training']
            if blocked:
                self._wait('; '.join(j['work_id']+' '+j['owner']+': '+'; '.join(j['feedback'][-2:]) for j in blocked))
                break
            if any(j.get('wait_kind')=='training' for j in self.board.pending(self.stage()['id'])):
                time.sleep(.5);continue
            lead_file=self.team.folder/'agents'/'lead'/'worker-state.json'
            continuation=None
            if lead_file.exists():
                saved=json.loads(lead_file.read_text())
                if saved['status']=='checkpointed':
                    continuation={'dispatch_id':'coordinator-'+str(saved['steps']),
                                  'guidance':'Read updated project_state. Required work and reviews have returned.'}
            result=self.team.run_agent('lead',self.team.definitions['coordinator'],lead_assignment,continuation)
            self.team.state['outcome']=result
            if result['status'] not in {'checkpointed','running','completed','waiting_external','stopped','escalated'}:
                self.team.state['workflow']['run_status']='STOPPED'
                self.team.event('coordinator_returned',{'status':result['status'],'scope':'Report submission is not project completion'})
        outcome={'status':self.team.state['workflow']['run_status'].lower(),
                 'goal_met':self.team.state['goal_met'],'scope':self.spec.get('completion_stage',self.spec['stages'][-1]['id']),
                 'work':self.board.summary()}
        self.team.state['outcome']=outcome;self.team.save()
        return outcome
