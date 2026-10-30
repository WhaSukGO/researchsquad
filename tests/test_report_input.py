import json
import pytest
from goalagent.report_input import REPORT_SCHEMA,action_schema,normalize_action
from test_team import make,instance,action

def test_typed_report_requires_scope_enums_and_complete_fields():
    schema=action_schema(['submit_report','read_file'])
    report=schema['properties']['argument']['anyOf'][1]
    claim=report['properties']['claims']['items']
    assert 'scope' in claim['required']
    assert claim['properties']['scope']['enum']==['document','empirical']
    assert report['properties']['objections']['items']['properties']['severity']['enum']==['BLOCKER','MAJOR','MINOR']
    assert report['additionalProperties'] is False
    assert set(report['required'])==set(report['properties'])

def test_normalization_keeps_report_values_and_rejects_non_report_objects():
    payload={'status':'DONE','summary':'Delivered','files':[],'claims':[{'scope':'empirical','statement':'Unverified'}]}
    result=normalize_action({'tool':'submit_report','argument':payload,'why':'Submit'})
    assert json.loads(result['argument'])==payload
    with pytest.raises(ValueError):normalize_action({'tool':'run','argument':payload,'why':'Unsafe'})
    legacy=action('read_file',{'path':'file'})
    assert normalize_action(legacy)==legacy

def test_preflight_validates_same_evidence_without_submission(tmp_path):
    team=make(tmp_path);a=instance(team)
    (a.workspace/'report.md').write_text('A report')
    data={'status':'DONE','summary':'Delivered','files':['report.md']}
    result=a.execute(action('check_report',data),10)
    assert result['valid'] and a.state['status']=='running'
    assert 'report' not in a.state and not (a.folder/'submission.json').exists()
    bad={**data,'claims':[{'scope':'empirical','statement':'Measured','epistemic_status':'observed','evidence_ids':['invented'],'limitations':'Not verified'}]}
    from goalagent.reports import validate_report
    a.validate_report=lambda data:validate_report(data,team.state['evidence'])
    for tool in ('check_report','submit_report'):
        with pytest.raises(ValueError,match='Unknown claim'):a.execute(action(tool,bad),10)
    data['files']=['inputs/numbers.json']
    with pytest.raises(ValueError):a.execute(action('check_report',data),10)

def test_common_agent_accepts_typed_report_wire_action(tmp_path):
    from test_team import Scripted,FakeSandbox,task
    from goalagent.team import Team
    t=Team(tmp_path,task(),sandbox_factory=FakeSandbox,provider_factory=lambda c:Scripted([
        {'tool':'submit_report','argument':{'status':'DONE','summary':'No experiment claimed','files':[]},'why':'Finish'}]))
    assert t.run()['status']=='submitted' and not t.state['goal_met']
