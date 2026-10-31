"""Evidence-only recovery report; never executes agent source or edits run state."""
import argparse
import difflib
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from goalagent.tracing import Trace

LABELS={'case-01':'학습 중단','case-02':'잘못된 입력 크기','case-03':'비정상 손실(NaN)'}

def load(p):return json.loads(p.read_text())

def summarize(folder):
    state=load(folder/'team-state.json');spans=Trace(folder/'traces').records()
    roles=[];decisions=[];errors=[];bad_citations=[]
    entries={**state['assignments'],'lead':{'agent':'coordinator','assignment':{}}}
    for aid,e in entries.items():
        p=folder/'agents'/aid/'worker-state.json'
        if not p.exists():continue
        worker=load(p)
        roles.append({'assignment':aid,'role':e['agent'],'scope':e['assignment'].get('review_scope'),
            'status':worker['status'],'steps':worker['steps'],'report':worker.get('report'),
            'input_names':list(e['assignment'].get('inputs',{})),
            'parent_paths':[state['artifacts'][x]['path'] for x in e['assignment'].get('parent_artifacts',[])]})
        for h in worker['history']:
            if h['tool']=='record_decision':
                data=json.loads(h['argument']);decisions.append({'role':e['agent'],'step':h['step'],**data})
                for eid in set(re.findall(r'action-[A-Za-z0-9_-]+-\d{6}',json.dumps(data))):
                    if eid not in state['evidence']:bad_citations.append({'role':e['agent'],'step':h['step'],'unregistered_text_id':eid})
            if isinstance(h.get('observation'),dict) and 'error' in h['observation']:
                errors.append({'role':e['agent'],'step':h.get('step'),'tool':h['tool'],'error':h['observation']})
    jobs=[]
    for j in state['training']['jobs'].values():
        root=folder/'training/jobs'/j['id'];source=root/'code/train.py';metrics=root/'output/metrics.json'
        events=[e['data'] for e in state['events'] if e['kind']=='training_job_state' and e['data']['job_id']==j['id']]
        jobs.append({'id':j['id'],'status':j['status'],'parent':j['parent_job'],'request':j['request'],
            'source':source.read_text(),'metrics':load(metrics) if metrics.exists() else None,'terminal_observation':events[-1] if events else None,
            'log':(root/'job.log').read_text() if (root/'job.log').exists() else None})
    verification=load(folder/'verification.json') if (folder/'verification.json').exists() else None
    first=next((j for j in jobs if verification and j['id']==verification['initial_job']),jobs[0] if jobs else None)
    fixed=next((j for j in jobs if verification and j['id']==verification['recovered_job']),next((j for j in jobs if j['status']=='SUCCEEDED'),None))
    patch=''.join(difflib.unified_diff(first['source'].splitlines(True),fixed['source'].splitlines(True),fromfile='initial/train.py',tofile='recovered/train.py')) if first and fixed else None
    provider_errors=[];wire_errors=[]
    for p in (folder/'agents').glob('*/turns/*/metadata.json'):
        metadata=load(p)
        if metadata.get('exit_code'):
            events=[]
            for line in p.with_name('events.jsonl').read_text().splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if event.get('type')=='error':events.append(event.get('message'))
            provider_errors.append({'turn':str(p.parent.relative_to(folder)),'exit_code':metadata['exit_code'],'errors':events})
        answer=p.with_name('answer.json')
        if answer.exists():
            raw=load(answer)
            if isinstance(raw.get('argument'),dict) and raw.get('tool') not in {'submit_report','check_report'}:
                wire_errors.append({'source':str(answer.relative_to(folder)),'action':raw})
    returned=[r for r in spans if r['kind']=='model' and (r.get('output') or {}).get('selected_action')]
    return {'case':folder.name,'goal_met':state['goal_met'],'run_status':state['workflow']['run_status'],
        'reservations':state['calls'],'returned_actions':len(returned),'models':sorted(set(r['output']['metadata'].get('model','unknown') for r in returned)),
        'wall_seconds':(max(datetime.fromisoformat(r.get('ended_at',r['started_at'])) for r in spans)-min(datetime.fromisoformat(r['started_at']) for r in spans)).total_seconds(),
        'verification':verification,'roles':roles,'decisions':decisions,'errors':errors,'unvalidated_decision_citation_typos':bad_citations,
        'jobs':jobs,'source_patch':patch,'review_verdicts':state['workflow'].get('reviews',[]),
        'provider_errors':provider_errors,'wire_rejected_outputs':wire_errors,
        'injection':load(folder/'injection.json') if (folder/'injection.json').exists() else None}

def export(root,output,repo=None):
    root=Path(root).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    cases=[summarize(root/k) for k in LABELS]
    record={'scope':'Actual model diagnosis/repair/reviews; fixed seeded faults and host interruption, not scripted recovery actions',
        'cases':cases,'readiness_scope':'Separate scripted command checks validate fault mechanisms only; not agent ability',
        'local_regression':{'passed':131,'skipped':3,'seconds':97.59},
        'reopen_added_reservations':{'case-01':cases[0]['reservations']-93,'case-02':cases[1]['reservations']-74,'case-03':cases[2]['reservations']-83}}
    (output/'verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    lines=['# 실제 에이전트 학습 실패 복구 검증','',
        '작성일: 2026-10-31. 세 종류의 실패를 실제 CUDA 학습 작업에서 발생시키고, 실제 모델이 로그·코드를 읽어 진단·수정·재개하는지 검증했다. 고장 종류와 최초 실행 조건은 유지관리자가 준비했고, 대응 액션·진단·패치는 고정 응답으로 제공하지 않았다. 사례별 에이전트 문맥은 분리했다.','',
        '## 검증 방식','',
        '제공된 시작 코드를 먼저 그대로 실행하도록 했다. 에이전트에게는 case 번호만 주고 고장 이름·정답 패치를 주지 않았다. 최초 실패 후 record_decision으로 원인 후보와 다음 실험을 기록하고, 원본을 보존한 채 수정하거나 체크포인트를 등록해 resume_job을 호출하도록 했다. 잘못된 학습을 성공으로 꾸미지 않도록 고정 모델·seed·데이터 분리·유한성 검사·학습 조건을 유지했다.','',
        '기본 모델은 784 입력과 은닉층 256개의 MLP, dropout 0.2다. seed 1337, Adam lr 0.001, batch 512, 3 epoch이며 공식 train 중 55,000개를 학습하고 마지막 5,000개로 validation한다. RTX 3080 Laptop GPU의 고정 CUDA/PyTorch 이미지에서 실행했다. 공식 test는 사용하지 않았다.','',
        '수치 성공 판정은 에이전트 보고서의 DONE과 분리했다. 호스트가 최초 소스·인자·실제 실패 신호를 확인하고, 복구 모델을 신뢰된 코드의 별도 CPU 컨테이너에서 채점한다. validation 75% 이상을 사전 기준으로 삼았다. 중단 사례는 추가로 올바른 parent/checkpoint 계보, epoch 1 복원, 중단 없는 대조 실행과 최종 가중치 완전 일치가 필요하다. 리뷰는 Researcher·Critic·보고서 전용 Report Reader의 별도 문맥에서 수행한다. Coordinator는 검토와 보호 측정 후 단계를 결정한다.','',
        '## 결과 요약','',
        '| 사례 | 실제 첫 실패 | 복구 방식 | 독립 판정 |','| --- | --- | --- | --- |']
    for c in cases:
        v=c['verification'] or {};accuracy=v.get('validation',{}).get('accuracy')
        signal={'case-01':'epoch 1/108 step 후 외부 SIGKILL, 종료 137','case-02':'27×27 입력과 784 입력층의 행렬 곱 오류','case-03':'첫 update 전 NaN 손실, 유한성 검사 중단'}[c['case']]
        mode='checkpoint에서 epoch 1 복원' if c['case']=='case-01' else '소스 수정 후 epoch 0부터 새 작업'
        verdict=f"validation {accuracy*100:.2f}%, "+('단계 완료' if c['goal_met'] else '단계 미완료') if accuracy is not None else '보호 측정 없음'
        lines.append(f"| {LABELS[c['case']]} | {signal} | {mode} | {verdict} |")
    for c in cases:
        key=c['case'];v=c['verification'] or {}
        lines +=['',f"## {LABELS[key]}: 실제로 무엇을 확인했는가",'',
            f"상태 {c['run_status']}; 호출 예약 {c['reservations']}회, 액션 반환 {c['returned_actions']}회. 모델 {', '.join(c['models'])}. 관찰된 경과 시간은 {c['wall_seconds']/60:.1f}분이다. 이는 에이전트 문서·검토와 컨테이너 시간을 포함하며, 사례들이 일부 겹쳐 실행돼 각 사례 시간을 단순 합산하면 전체 경과 시간이 되지 않는다.",'']
        if key=='case-01':
            comp=v.get('resume_comparison',{})
            lines +=['최초 작업은 epoch 1의 108 optimizer step을 완료하고 checkpoint.pt를 원자적으로 저장했다. 호스트 관찰자가 그 경계 표시를 확인한 뒤 Docker SIGKILL을 보냈다. Docker는 exit 137, OOMKilled=false를 보고했다. 에이전트는 체크포인트 존재와 완료한 epoch를 읽고, 정확한 종료 주체는 모른다고 남긴 채 중단에 부합한다는 작업 가설로 재개를 선택했다. 외부 kill을 실제로 보냈다는 사실은 에이전트 추측이 아니라 별도 호스트 injection 기록으로 확인했다.','',
                f"최종 보호 측정의 재개 epoch는 {v.get('resumed_from_epoch')}, 연속 학습 대비 가중치 최대 차이는 {comp.get('max_abs_difference')}, 완전 일치는 {comp.get('identical')}다. 동일 가중치만으로 재개를 인정하지 않고 parent_job과 checkpoint 모델 등록 계보도 확인했다. 원래 소스와 그 안의 복원 코드는 유지됐으며, 에이전트가 올바른 체크포인트와 재개 도구를 선택한 검증이다. 임의 학습 코드에 체크포인트 기능을 새로 설계한 검증은 아니다.",'']
        elif key=='case-02':
            lines +=['실패 로그의 입력 shape는 [55000,1,27,27], 첫 batch는 512×729였고 모델 Linear 층은 784×256이었다. 에이전트는 잘못된 전처리 resize를 원인으로 선택했다. 모델을 729 입력으로 바꾸거나 데이터를 바꾸는 대신 원래 28×28 입력을 유지하도록 해당 줄을 제거했다. 첫 optimizer update 전 실패해 유효 checkpoint가 없었으므로 새 수정 소스로 처음부터 시작한 것은 재개를 가장한 것이 아니라 필요한 재시작이다.','']
        else:
            lines +=['실패 시점은 epoch 1, optimizer step 0이었다. 진단 파일은 입력이 유한하지만 logits에 음수가 있고 loss가 nan이라고 보고했다. 에이전트는 raw logits에 torch.log를 적용하고 레이블도 쓰지 않는 손실식을 원인으로 골랐다. 입력 데이터의 NaN과 외부 종료 가능성을 관측 근거로 배제하고, 지도 분류에 맞는 안정적인 cross-entropy로 손실식 한 줄을 수정했다. 유한성 검사를 없애거나 NaN을 0으로 바꾸지 않았다. checkpoint가 없어서 새 작업으로 재시작했다.','']
        lines +=['실제 코드 차이:','', '```diff',c['source_patch'] or '(소스 변경 없음: 같은 소스를 checkpoint로 이어 실행)','```','', '### 공개 진단·선택 기록','']
        for d in c['decisions']:lines +=[f"- {d['role']} step {d['step']}: {d['summary']}"]
        lines +=['','### 역할별 판단과 결과','']
        for role in c['roles']:
            report=role.get('report')
            text=report['summary'] if report else ('필수 검토와 보호 평가 뒤 단계 전환을 결정했다.' if role['role']=='coordinator' else '제출된 역할 보고서 없음')
            lines +=[f"- {role['role']} ({role['status']}, {role['steps']} step, 범위 {role['scope'] or '일반 업무'}): {text}"]
        lines +=['','### 실패·제출 마찰과 남은 불확실성','']
        if not c['errors']:lines +=['추가 도구/모델 오류가 기록되지 않았다. 이것이 모든 실패 형태의 복구 능력을 뜻하지는 않는다.']
        for e in c['errors']:lines +=[f"- {e['role']} step {e['step']}, {e['tool']}: {json.dumps(e['error'],ensure_ascii=False)}"]
        for typo in c['unvalidated_decision_citation_typos']:lines +=[f"- 공개 결정의 자유문장에 미등록 근거 ID가 있었다: {typo['unregistered_text_id']}. 구조화된 보고서의 근거 검증과 달리 자유문장 ID는 자동 검증되지 않는 한계다."]
        for error in c['provider_errors']:lines +=[f"- 제공자 원본 오류 확인 ({error['turn']}): {'; '.join(str(x) for x in error['errors'])}. 학습 프로세스의 실패와 구분한다."]
        for error in c['wire_rejected_outputs']:lines +=[f"- {error['source']}에서 {error['action']['tool']}에 보고서 객체를 넣은 잘못된 도구/인자 조합이 실행 전에 거부됐다. 전체 도구 이름과 입력 타입을 결합하는 스키마가 아직 부족하다."]
        dest=output/key;dest.mkdir(exist_ok=True)
        folder=root/key;Trace(folder/'traces').export(output/(key+'-trace.html'))
        if (folder/'verification.json').exists():shutil.copyfile(folder/'verification.json',dest/'protected-verification.json')
        for j in c['jobs']:
            (dest/(j['id']+'-train.py')).write_text(j['source'])
            if j['log']:(dest/(j['id']+'-job.log')).write_text(j['log'])
            if j['metrics']:(dest/(j['id']+'-metrics.json')).write_text(json.dumps(j['metrics'],indent=2))
        (dest/'repair.patch').write_text(c['source_patch'] or '')
    lines +=['','## 구현과 운영에서 부족했던 부분','',
        '실패한 작업을 관찰한 사실과 성공한 실험의 근거가 보고서 검증에서 충분히 분리되지 않았다. failed job_status/await_job은 성공 근거 필터에서 빠지므로, 에이전트가 실패 사실을 observed empirical로 직접 인용하면 제출이 거부될 수 있다. 이번에는 읽은 보고서/기록의 내용과 복구 추론을 분리하고 근거를 정정하는 방식으로 대응했다. 실패 관측 전용 주장·실행 기록을 도입하고, 성공 주장을 허용하는 규칙과 분리하는 것이 후속 과제다. 검증을 느슨하게 하거나 FAILED를 성공으로 바꾸는 해결은 적절하지 않다.','',
        '원본이 inputs/에 이미 보존돼 있는데도 이를 checkpoint/제출 files에 다시 넣어 거부되는 사례가 있었다. 보존 목록에는 작업자가 만든 파일만 넣어야 한다. check_report가 실제 사용돼 제출 전 문제를 드러냈지만, 학습 완료 후 문서 정정·재읽기 비용은 여전히 발생했다. 자유문장 근거 ID 오타도 구조화된 인용과 달리 자동 검증되지 않는다.','',
        '보호 측정과 별개로 역할 리뷰는 같은 계열 모델의 서로 다른 문맥이다. 읽기만으로 optimizer/RNG 복원의 완전성을 증명하지 않으며, 중단 사례의 대조 가중치 비교가 그 별도 수치 근거다. 보고서 전용 검토자는 코드·원시 수치를 독립 실행한 사람이 아니다.','',
        '## 이번 결과로 아직 말할 수 없는 것','',
        '- 원래 학습 루프·체크포인트 복원 기능은 제공했다. 이 검증은 실제 진단·수정·도구 선택 능력이며, 임의 framework의 복원 기능을 처음부터 만드는 능력 검증은 아니다.',
        '- 외부 중단은 epoch 경계의 저장 직후 대기 구간에서 발생했다. 중간 batch, 저장 중 손상, 호스트 재부팅, GPU 드라이버 리셋까지 검증하지 않았다.',
        '- 입력 크기 오류와 NaN은 각각 하나의 의도적으로 심은 결함이다. 늦은 학습 발산, AMP overflow, 간헐적 데이터 오염 등으로 일반화할 수 없다.',
        '- validation은 복구 동작 확인용이며 일반화 성능이나 악보 인식 성능의 증거가 아니다. 공식 test를 반복 소비하지 않았다.',
        '- 준비 단계의 세 고장 발생 확인은 고정 명령으로 수행했다. 실제 에이전트의 진단·패치·복원 및 역할 리뷰와 구분해야 한다.','',
        '## 산출물과 재현','',
        '열람용 묶음은 sessions/01a183b6-agent-system/reports/failure-recovery-20261031/이다. case-01-trace.html, case-02-trace.html, case-03-trace.html과 verification.json, 사례별 원본/수정 코드·작업 로그·metrics·patch를 보존했다. trace에는 전달된 프롬프트, 도구 권한, 공개 판단·후보, 도구 결과·오류와 호스트 고장 주입이 기록된다. 비공개 내부 사고는 수집하지 않는다. 완료한 세 실행을 다시 열어도 호출 예약은 각각 93/74/83회로 유지됐고 추가 학습이 없었다.','',
        '진입점은 python -m goalagent.recovery_live --case case-01|case-02|case-03 --run-dir <새 폴더>다. 고장과 조건은 같아도 실제 모델의 진단·행동·소요 시간은 달라질 수 있다. 원본 실행은 projects/researchsquad/tmp/recovery-live-20261031/ 아래에 있다. 준비 검증은 python -m scripts.recovery_readiness --run-dir <새 폴더>이며 모델 호출이 없다.','',
        '호스트 회귀 테스트는 131 passed, 3개의 명시적 Docker opt-in 항목 skipped였다. 실제 GPU 고장·복구와 별도 CPU 평가는 이 실행에서 별도로 수행했다.','']
    report=re.sub(r'\b[a-f0-9]{64}\b','(고정된 산출물)','\n'.join(lines))
    (output/'report-ko.md').write_text(report,encoding='utf-8')
    if repo:
        repo=Path(repo);(repo/'docs/recovery-results-ko.md').write_text(report,encoding='utf-8')
        (repo/'docs/verification/recovery-20261031.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(output),'cases':[{'case':c['case'],'goal_met':c['goal_met'],'verification':c['verification']} for c in cases]},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-root',required=True);p.add_argument('--output',required=True);p.add_argument('--repo');a=p.parse_args();export(a.run_root,a.output,a.repo)
