import json
from pathlib import Path
import pytest
from goalagent.blind_review import prepare,review,score,verify_seal,sha,validate_review
from goalagent.contracts import atomic_json
from goalagent.roles import role_prompt
from goalagent.timing import timed_chords
from scorebench.metrics import sequence_metrics

KERN='**kern\t**mxhm\n*clefG2\t*\n4c\tC:maj\n4d\tG:maj\n*-\t*-\n'


def fixture_run(tmp_path):
    source=tmp_path/'source';case=source/'sample-001';case.mkdir(parents=True)
    (case/'input.png').write_bytes(b'image-only')
    (case/'prediction.krn').write_text(KERN)
    atomic_json(case/'trace.json',{'source_image_sha256':sha(case/'input.png'),'output_sha256':sha(case/'prediction.krn')})
    atomic_json(source/'receipt.json',{'samples':1})
    return prepare(source,tmp_path/'run','test-model')


class Reviewer:
    model='test-model'
    def __init__(self):self.calls=0
    def call(self,prompt,schema,folder,**kw):
        self.calls+=1
        assert 'SECRET_GOLD' not in prompt and 'reference_index' not in prompt and 'melody_errors' not in prompt
        data=json.loads(prompt.split('Task data (JSON):\n')[1])
        assert set(data)=={'candidate','format'}
        return {'verdict':'keep','kern':data['candidate'],'findings':[],'uncertainties':[]},{'unexpected_tool_events':[]}


def test_reviewer_rejects_answer_or_accuracy_payload():
    for extra in ['reference','accuracy','error_locations','history']:
        with pytest.raises(ValueError,match='contract'):
            role_prompt('reviewer',{'candidate':KERN,'format':'format',extra:'SECRET_GOLD'})


def test_scorer_is_never_an_llm():
    with pytest.raises(ValueError,match='deterministic'):role_prompt('scorer',{})


def test_score_cannot_even_open_manifest_before_freeze(tmp_path):
    run=fixture_run(tmp_path)
    with pytest.raises(ValueError,match='whole batch'):
        score(run,tmp_path/'nonexistent-secret-manifest.json')


def test_blind_review_runs_with_no_reference_files_and_seals(tmp_path):
    run=fixture_run(tmp_path)
    (tmp_path/'private-answers.txt').write_text('SECRET_GOLD')
    provider=Reviewer();state=review(run,provider)
    assert state['phase']=='sealed' and provider.calls==1
    assert verify_seal(run)['model_calls']==1


def test_sealed_batch_cannot_be_revised_even_if_model_wants_to(tmp_path):
    run=fixture_run(tmp_path);provider=Reviewer();review(run,provider)
    review(run,provider)
    assert provider.calls==1


def test_frozen_prediction_tampering_is_rejected(tmp_path):
    run=fixture_run(tmp_path);review(run,Reviewer())
    (run/'cases/case-001/prediction.krn').write_text(KERN.replace('4c','4e'))
    with pytest.raises(ValueError,match='Frozen'):verify_seal(run)


def test_prompt_and_budget_cannot_change_mid_experiment(tmp_path):
    run=fixture_run(tmp_path)
    p=json.loads((run/'protocol.json').read_text());p['budget']['max_model_calls']=100
    atomic_json(run/'protocol.json',p)
    with pytest.raises(ValueError,match='manifest'):review(run,Reviewer())


def test_interrupted_attempt_is_not_silently_retried(tmp_path):
    run=fixture_run(tmp_path);state=json.loads((run/'state.json').read_text())
    state['attempted']=['case-001'];state['model_calls']=1;atomic_json(run/'state.json',state)
    provider=Reviewer();review(run,provider)
    assert provider.calls==0
    r=json.loads((run/'cases/case-001/review.json').read_text())
    assert r['status']=='error' and r['answer']['kern']==KERN


def test_keep_cannot_hide_an_edit():
    with pytest.raises(ValueError,match='silently'):
        validate_review({'verdict':'keep','kern':KERN.replace('4c','4e'),'findings':[],'uncertainties':[]},KERN)


def test_timing_detects_right_chord_on_wrong_beat():
    early=KERN.replace('4c\tC:maj\n4d\tG:maj','8c\tC:maj\n4.d\tG:maj')
    result=sequence_metrics(timed_chords(KERN),timed_chords(early))
    assert result['errors']==1 and result['edits'][0]['expected'][0]=='1'
    assert result['edits'][0]['actual'][0]=='1/2'


def test_timing_preserves_tied_row_time_not_merged_note_time():
    t=KERN.replace('4c\tC:maj\n4d\tG:maj','[8.c\tC:maj\n16c]\tG:maj')
    assert timed_chords(t)[1][0]=='3/4'


def test_null_chord_row_is_unknown_not_assumed_correct():
    t=KERN.replace('4d\tG:maj','.\tG:maj')
    with pytest.raises(ValueError,match='onset'):timed_chords(t)


def test_model_side_tool_use_cannot_pass_as_review(tmp_path):
    class Bad(Reviewer):
        def call(self,*a,**kw):
            answer,meta=super().call(*a,**kw)
            return answer,{'unexpected_tool_events':['command_execution']}
    run=fixture_run(tmp_path);review(run,Bad())
    assert json.loads((run/'cases/case-001/review.json').read_text())['status']=='error'


def test_provider_context_has_only_explicit_inputs(tmp_path,monkeypatch):
    import goalagent.provider as module
    def process(command,*,cwd,stdin,timeout):
        assert not str(cwd).startswith(str(tmp_path))
        assert set(p.name for p in Path(cwd).iterdir())=={'schema.json','input.png'}
        Path(command[command.index('-o')+1]).write_text('{"ok":true}')
        return 0,'{"type":"item.completed","item":{"type":"agent_message"}}\n',''
    monkeypatch.setattr(module,'run_process',process)
    img=tmp_path/'input.png';img.write_bytes(b'pixels')
    answer,metadata=module.CodexProvider('test').call('explicit prompt',{'type':'object'},tmp_path/'out',image=img)
    assert answer=={'ok':True} and metadata['os_read_isolation'] is False


def test_controller_review_tool_cannot_escape_run_directory():
    from goalagent.music import MusicTools
    domain=object.__new__(MusicTools)
    with pytest.raises(ValueError,match='experiment ID'):
        domain.experiment_config('{"kind":"blind_review","source":"../../research/data"}')


def test_controller_review_tool_requires_recognition_first(tmp_path):
    from goalagent.music import MusicTools
    domain=object.__new__(MusicTools);domain.run_dir=tmp_path
    with pytest.raises(ValueError,match='completed vision'):
        domain.run_blind_review({'kind':'blind_review','source':'exp-123456abcdef'},tmp_path/'new',lambda:None,lambda:100)


def test_external_call_budget_is_respected_and_failure_is_retained(tmp_path):
    run=fixture_run(tmp_path);provider=Reviewer()
    def exhausted():raise RuntimeError('Controller call cap reached')
    state=review(run,provider,charge_model=exhausted)
    assert provider.calls==0 and state['model_calls']==0 and state['phase']=='sealed'
    assert (run/'cases/case-001/prediction.krn').read_text()==KERN


def test_input_tampering_is_rejected_before_model_call(tmp_path):
    run=fixture_run(tmp_path);provider=Reviewer()
    (run/'cases/case-001/candidate.krn').write_text('SECRET_GOLD')
    with pytest.raises(ValueError,match='Public input changed'):review(run,provider)
    assert provider.calls==0
