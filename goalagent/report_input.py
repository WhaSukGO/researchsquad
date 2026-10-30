"""Typed model wire input; existing report/evidence validators remain authoritative."""
import json
from .reports import FAILURES

def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}

def array(item):return {'type':'array','items':item}
S={'type':'string'}
STRINGS=array(S)
def enum(values):return {'type':'string','enum':values}

REPORT_SCHEMA=obj({
    'status':enum(['DONE','NEEDS_INPUT','FAILED']),'summary':S,'files':STRINGS,
    'failure_kind':{'type':['string','null'],'enum':[None,*sorted(FAILURES)]},
    'claims':array(obj({'scope':enum(['document','empirical']),'statement':S,
        'epistemic_status':enum(['observed','inferred','hypothesis','unknown']),
        'evidence_ids':STRINGS,'limitations':S})),
    'objections':array(obj({'target_id':S,'category':enum(['FACT','FEASIBILITY','EXPERIENCE','RESOURCE','OBJECTIVE','AUTHORIZATION']),
        'severity':enum(['BLOCKER','MAJOR','MINOR']),'statement':S,'evidence_ids':STRINGS,'resolution_test':S})),
    'next_actions':array(obj({'action':S,'owner':S,'expected_information':S,'acceptance_check':S,'requires_external':{'type':'boolean'}})),
    'open_questions':STRINGS,
    'work_items':array(obj({'existing_work_id':S,'owner':S,'objective':S,'input_artifact_ids':STRINGS,
        'required_tools':STRINGS,'acceptance_check':S,'blocking':{'type':'boolean'}})),
    'execution_records':array(obj({'action':enum(['searched','read','executed','image_received','job_started','job_completed']),
        'target':S,'evidence_ids':STRINGS})),
    'candidate_decisions':array(obj({'candidate':S,'decision':enum(['SELECTED','REJECTED','DEFERRED','UNTESTED']),
        'reason':S,'evidence_ids':STRINGS,'followup_action':S}))})

def action_schema(tools):
    return obj({'tool':enum(tools),'argument':{'anyOf':[S,REPORT_SCHEMA]} if set(tools)&{'submit_report','check_report'} else S,'why':S})

def normalize_action(action):
    if isinstance(action,dict) and isinstance(action.get('argument'),dict):
        if action.get('tool') not in {'submit_report','check_report'}:raise ValueError('Structured report argument requires report tool')
        action={**action,'argument':json.dumps(action['argument'],ensure_ascii=False)}
    return action
