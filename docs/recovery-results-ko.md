# 실제 에이전트 학습 실패 복구 검증

작성일: 2026-10-31. 세 종류의 실패를 실제 CUDA 학습 작업에서 발생시키고, 실제 모델이 로그·코드를 읽어 진단·수정·재개하는지 검증했다. 고장 종류와 최초 실행 조건은 유지관리자가 준비했고, 대응 액션·진단·패치는 고정 응답으로 제공하지 않았다. 사례별 에이전트 문맥은 분리했다.

## 검증 방식

제공된 시작 코드를 먼저 그대로 실행하도록 했다. 에이전트에게는 case 번호만 주고 고장 이름·정답 패치를 주지 않았다. 최초 실패 후 record_decision으로 원인 후보와 다음 실험을 기록하고, 원본을 보존한 채 수정하거나 체크포인트를 등록해 resume_job을 호출하도록 했다. 잘못된 학습을 성공으로 꾸미지 않도록 고정 모델·seed·데이터 분리·유한성 검사·학습 조건을 유지했다.

기본 모델은 784 입력과 은닉층 256개의 MLP, dropout 0.2다. seed 1337, Adam lr 0.001, batch 512, 3 epoch이며 공식 train 중 55,000개를 학습하고 마지막 5,000개로 validation한다. RTX 3080 Laptop GPU의 고정 CUDA/PyTorch 이미지에서 실행했다. 공식 test는 사용하지 않았다.

수치 성공 판정은 에이전트 보고서의 DONE과 분리했다. 호스트가 최초 소스·인자·실제 실패 신호를 확인하고, 복구 모델을 신뢰된 코드의 별도 CPU 컨테이너에서 채점한다. validation 75% 이상을 사전 기준으로 삼았다. 중단 사례는 추가로 올바른 parent/checkpoint 계보, epoch 1 복원, 중단 없는 대조 실행과 최종 가중치 완전 일치가 필요하다. 리뷰는 Researcher·Critic·보고서 전용 Report Reader의 별도 문맥에서 수행한다. Coordinator는 검토와 보호 측정 후 단계를 결정한다.

## 결과 요약

| 사례 | 실제 첫 실패 | 복구 방식 | 독립 판정 |
| --- | --- | --- | --- |
| 학습 중단 | epoch 1/108 step 후 외부 SIGKILL, 종료 137 | checkpoint에서 epoch 1 복원 | validation 85.82%, 단계 완료 |
| 잘못된 입력 크기 | 27×27 입력과 784 입력층의 행렬 곱 오류 | 소스 수정 후 epoch 0부터 새 작업 | validation 85.82%, 단계 완료 |
| 비정상 손실(NaN) | 첫 update 전 NaN 손실, 유한성 검사 중단 | 소스 수정 후 epoch 0부터 새 작업 | validation 85.82%, 단계 완료 |

## 학습 중단: 실제로 무엇을 확인했는가

상태 COMPLETED; 호출 예약 93회, 액션 반환 91회. 모델 gpt-6-astra. 관찰된 경과 시간은 19.3분이다. 이는 에이전트 문서·검토와 컨테이너 시간을 포함하며, 사례들이 일부 겹쳐 실행돼 각 사례 시간을 단순 합산하면 전체 경과 시간이 되지 않는다.

최초 작업은 epoch 1의 108 optimizer step을 완료하고 checkpoint.pt를 원자적으로 저장했다. 호스트 관찰자가 그 경계 표시를 확인한 뒤 Docker SIGKILL을 보냈다. Docker는 exit 137, OOMKilled=false를 보고했다. 에이전트는 체크포인트 존재와 완료한 epoch를 읽고, 정확한 종료 주체는 모른다고 남긴 채 중단에 부합한다는 작업 가설로 재개를 선택했다. 외부 kill을 실제로 보냈다는 사실은 에이전트 추측이 아니라 별도 호스트 injection 기록으로 확인했다.

최종 보호 측정의 재개 epoch는 1, 연속 학습 대비 가중치 최대 차이는 0.0, 완전 일치는 True다. 동일 가중치만으로 재개를 인정하지 않고 parent_job과 checkpoint 모델 등록 계보도 확인했다. 원래 소스와 그 안의 복원 코드는 유지됐으며, 에이전트가 올바른 체크포인트와 재개 도구를 선택한 검증이다. 임의 학습 코드에 체크포인트 기능을 새로 설계한 검증은 아니다.

실제 코드 차이:

```diff
(소스 변경 없음: 같은 소스를 checkpoint로 이어 실행)
```

### 공개 진단·선택 기록

- experiment_engineer step 13: The unchanged initial job job-9f51b07ab341230464cc97ea failed with exit 137 after completing epoch 1; Docker reported OOMKilled=false. Logs show loss 0.7801373763604598, validation accuracy 0.8218 and 108 optimizer steps, and boundary.json confirms epoch 1/108 steps. Evidence: action-task-feb95b2824d2014c7d6e386f-000010, action-task-feb95b2824d201c7d6e386f-000011, action-task-feb95b2824d2014c7d6e386f-000012. Working diagnosis is process interruption compatible with SIGKILL; the initiating cause is unknown. This is not a scientific negative result. Select registration and genuine continuation from checkpoint.pt, retaining the unchanged source and failed job. The next test must demonstrate restored epoch and optimizer steps, restored RNG/sample order, and completion through epoch 3 with finite training and validation metrics.

### 역할별 판단과 결과

- experiment_engineer (submitted, 37 step, 범위 full): Recovered training through checkpoint continuation using two launches and unchanged source. Required deliverables and final weights are preserved; protected evaluation and independent reviews remain pending.
- researcher (submitted, 18 step, 범위 full): Completed independent research review and recorded PASS for RECOVERY-review-research. Reviewed evidence supports genuine checkpoint continuation and restored learning; protected saved-weight performance remains a separate coordinator gate.
- critic (submitted, 30 step, 범위 full): Completed the frozen-candidate evidence audit and recorded PASS for RECOVERY-review-auditor. No significant unresolved defect was found within the inspected scope. This review does not establish independent reproduction or protected model performance.
- report_reader (submitted, 4 step, 범위 report_only): Completed report-only comprehension review and recorded PASS with minor clarification requests. Recovery, reported learning, unresolved termination cause and pending evaluation are clearly scoped. This review is not independent execution or product acceptance.
- coordinator (completed, 4 step, 범위 일반 업무): 필수 검토와 보호 평가 뒤 단계 전환을 결정했다.

### 실패·제출 마찰과 남은 불확실성

- experiment_engineer step None, model: {"error": "Structured report argument requires report tool"}
- experiment_engineer step 28, submit_report: {"error": "ValueError", "detail": "Observed empirical claim needs successful source/execution evidence"}
- experiment_engineer step 29, checkpoint: {"error": "ValueError", "detail": "Cannot preserve inputs/starter.py: Submit authored files, not read-only inputs"}
- experiment_engineer step 34, check_report: {"error": "ValueError", "detail": "Observed document claim needs evidence for delivered material"}
- researcher step None, model: {"error": "Structured report argument requires report tool"}
- report_reader step 3, submit_report: {"error": "ValueError", "detail": "Unknown objection target"}
- 공개 결정의 자유문장에 미등록 근거 ID가 있었다: action-task-feb95b2824d201c7d6e386f-000011. 구조화된 보고서의 근거 검증과 달리 자유문장 ID는 자동 검증되지 않는 한계다.
- agents/task-fb7c7fc996346ab229207b7d/turns/001/answer.json에서 list_files에 보고서 객체를 넣은 잘못된 도구/인자 조합이 실행 전에 거부됐다. 전체 도구 이름과 입력 타입을 결합하는 스키마가 아직 부족하다.
- agents/task-feb95b2824d2014c7d6e386f/turns/001/answer.json에서 read_file에 보고서 객체를 넣은 잘못된 도구/인자 조합이 실행 전에 거부됐다. 전체 도구 이름과 입력 타입을 결합하는 스키마가 아직 부족하다.

## 잘못된 입력 크기: 실제로 무엇을 확인했는가

상태 COMPLETED; 호출 예약 74회, 액션 반환 72회. 모델 gpt-6-astra. 관찰된 경과 시간은 16.6분이다. 이는 에이전트 문서·검토와 컨테이너 시간을 포함하며, 사례들이 일부 겹쳐 실행돼 각 사례 시간을 단순 합산하면 전체 경과 시간이 되지 않는다.

실패 로그의 입력 shape는 [55000,1,27,27], 첫 batch는 512×729였고 모델 Linear 층은 784×256이었다. 에이전트는 잘못된 전처리 resize를 원인으로 선택했다. 모델을 729 입력으로 바꾸거나 데이터를 바꾸는 대신 원래 28×28 입력을 유지하도록 해당 줄을 제거했다. 첫 optimizer update 전 실패해 유효 checkpoint가 없었으므로 새 수정 소스로 처음부터 시작한 것은 재개를 가장한 것이 아니라 필요한 재시작이다.

실제 코드 차이:

```diff
--- initial/train.py
+++ recovered/train.py
@@ -18,7 +18,6 @@
     model=build(spec).cuda();optimizer=torch.optim.Adam(model.parameters(),lr=.001)
     x=images(Path(a.data)/'images.gz');y=labels(Path(a.data)/'labels.gz')
     train_x=x[:55000].cuda();train_y=y[:55000].cuda();val_x=x[55000:].cuda();val_y=y[55000:].cuda()
-    train_x=torch.nn.functional.interpolate(train_x,size=(27,27))
     begin=0;steps=0;history=[];resume=Path('/checkpoints/resume')
     if resume.exists():
         saved=torch.load(resume,map_location='cuda',weights_only=True)

```

### 공개 진단·선택 기록

- experiment_engineer step 13: Diagnosis: an implementation defect in preprocessing caused the initial failure, not a scientific negative result. The failed run reported input_shape [55000,1,27,27] and a matrix mismatch (512x729 versus 784x256); starter.py explicitly interpolates training images to 27x27. Evidence: action-task-feb95b2824d2014c7d6e386f-000010, action-task-feb95b2824d2014c7d6e386f-000011, action-task-feb95b2824d2014c7d6e386f-000012. The output inventory contains only .job-result.json, so no usable checkpoint exists. Selected next test: remove only the training-image interpolation line, preserve inputs/starter.py and both helpers, verify the diff, then launch the same approved three-epoch configuration. Recovery and learning remain unmeasured.

### 역할별 판단과 결과

- experiment_engineer (submitted, 35 step, 범위 full): Recovered the incident on launch 2 of 5 by removing the training-only resize to 27×27. The recovered job completed three epochs, and final weights were registered as model-d08af4af3b031610cef35669. Required documents and original outputs are preserved. Protected evaluation and independent reviews remain pending.
- researcher (submitted, 11 step, 범위 full): Completed independent research review and recorded PASS for RECOVERY-review-research. Evidence supports an implementation diagnosis, a constrained repair, restored learning, and final-weight registration. Independent protected performance evaluation remains pending; no other gates are approved.
- critic (submitted, 20 step, 범위 full): Completed the scoped independent evidence review and submitted PASS to RECOVERY-review-auditor for the frozen candidate. No significant unresolved defect was found within this review. Protected saved-weight scoring and other required gates remain separate.
- report_reader (submitted, 4 step, 범위 report_only): Report-only comprehension review completed; PASS recorded. Failure, repair, recovery scope and pending independent evaluation are clear. One minor metric-definition clarification remains. This review does not independently reproduce execution or establish project acceptance.
- coordinator (completed, 4 step, 범위 일반 업무): 필수 검토와 보호 평가 뒤 단계 전환을 결정했다.

### 실패·제출 마찰과 남은 불확실성

- experiment_engineer step None, model: {"error": "Structured report argument requires report tool"}
- experiment_engineer step 28, submit_report: {"error": "ValueError", "detail": "Observed empirical claim needs successful source/execution evidence"}
- experiment_engineer step 29, checkpoint: {"error": "ValueError", "detail": "Cannot preserve inputs/starter.py: Submit authored files, not read-only inputs"}
- researcher step None, model: {"error": "Codex call failed (exit 1); see /mnt/d/whasuk/myhelpers/projects/researchsquad/tmp/recovery-live-20261031/case-02/agents/task-fb7c7fc996346ab229207b7d/turns/006/stderr.log"}
- report_reader step 3, submit_report: {"error": "ValueError", "detail": "Unknown objection target"}
- 제공자 원본 오류 확인 (agents/task-fb7c7fc996346ab229207b7d/turns/006): Selected model is at capacity. Please try a different model.. 학습 프로세스의 실패와 구분한다.
- agents/task-feb95b2824d2014c7d6e386f/turns/001/answer.json에서 read_file에 보고서 객체를 넣은 잘못된 도구/인자 조합이 실행 전에 거부됐다. 전체 도구 이름과 입력 타입을 결합하는 스키마가 아직 부족하다.

## 비정상 손실(NaN): 실제로 무엇을 확인했는가

상태 COMPLETED; 호출 예약 83회, 액션 반환 83회. 모델 gpt-6-astra. 관찰된 경과 시간은 16.2분이다. 이는 에이전트 문서·검토와 컨테이너 시간을 포함하며, 사례들이 일부 겹쳐 실행돼 각 사례 시간을 단순 합산하면 전체 경과 시간이 되지 않는다.

실패 시점은 epoch 1, optimizer step 0이었다. 진단 파일은 입력이 유한하지만 logits에 음수가 있고 loss가 nan이라고 보고했다. 에이전트는 raw logits에 torch.log를 적용하고 레이블도 쓰지 않는 손실식을 원인으로 골랐다. 입력 데이터의 NaN과 외부 종료 가능성을 관측 근거로 배제하고, 지도 분류에 맞는 안정적인 cross-entropy로 손실식 한 줄을 수정했다. 유한성 검사를 없애거나 NaN을 0으로 바꾸지 않았다. checkpoint가 없어서 새 작업으로 재시작했다.

실제 코드 차이:

```diff
--- initial/train.py
+++ recovered/train.py
@@ -30,7 +30,7 @@
         model.train();order=torch.randperm(len(train_y));total=0
         for i in range(0,len(order),512):
             ids=order[i:i+512].cuda();optimizer.zero_grad(set_to_none=True);logits=model(train_x[ids])
-            loss=torch.log(logits).mean()
+            loss=torch.nn.functional.cross_entropy(logits, train_y[ids])
             if not bool(torch.isfinite(loss)):
                 diagnostic={'epoch':epoch+1,'step':steps,'loss':str(float(loss.detach())),
                     'logits_min':float(logits.detach().min()),'logits_max':float(logits.detach().max()),'input_finite':bool(torch.isfinite(train_x[ids]).all())}

```

### 공개 진단·선택 기록

- experiment_engineer step 13: The unchanged reproduction failed before its first optimizer update: finite inputs, logits spanning negative values, and NaN loss were reported in action-task-feb95b2824d2014c7d6e386f-000009 and action-task-feb95b2824d2014c7d6e386f-000012. Source inspection (action-task-feb95b2824d2014c7d6e386f-000011) shows torch.log(logits).mean(), which is undefined for negative logits and ignores labels. This supports an implementation defect, not a scientific negative result. The failed output inventory contains no checkpoint (action-task-feb95b2824d2014c7d6e386f-000010). Preserve the original and replace only the loss with torch.nn.functional.cross_entropy(logits, train_y[ids]); then run the same three-epoch configuration and inspect finite training, loss progression, validation accuracy and saved weights.

### 역할별 판단과 결과

- experiment_engineer (submitted, 32 step, 범위 full): Recovered the incident in two launches with a one-line loss repair. The recovered job completed three epochs, final weights are registered, and required deliverables and original outputs are preserved. Protected evaluation and independent reviews remain pending.
- researcher (submitted, 15 step, 범위 full): Independent research review completed; RECOVERY-review-research recorded PASS. The reviewed minimal loss repair and training trajectory support restored learning, beyond successful exit alone. This review does not establish independent saved-weight performance or project acceptance.
- critic (submitted, 29 step, 범위 full): Completed the scoped evidence audit and recorded PASS for RECOVERY-review-auditor in review-dispatch-a3b90b035021228d63d2d3eb. The review found no significant unresolved defect within its scope. It does not establish independent reproduction or protected saved-weight performance.
- report_reader (submitted, 3 step, 범위 report_only): Report-only comprehension review completed; gate PASS recorded. The report clearly distinguishes reported recovery and learning from pending protected evaluation and project acceptance. Four minor clarifications remain. No code inspection or independent experiment was performed.
- coordinator (completed, 4 step, 범위 일반 업무): 필수 검토와 보호 평가 뒤 단계 전환을 결정했다.

### 실패·제출 마찰과 남은 불확실성

- experiment_engineer step 28, submit_report: {"error": "ValueError", "detail": "Execution assertion requires successful actions by this assignment"}
- researcher step 14, submit_report: {"error": "ValueError", "detail": "Observed document claim needs evidence for delivered material"}
- critic step 23, submit_report: {"error": "ValueError", "detail": "Observed document claim needs evidence for delivered material"}
- critic step 27, submit_report: {"error": "ValueError", "detail": "Unknown claim evidence"}

## 구현과 운영에서 부족했던 부분

실패한 작업을 관찰한 사실과 성공한 실험의 근거가 보고서 검증에서 충분히 분리되지 않았다. failed job_status/await_job은 성공 근거 필터에서 빠지므로, 에이전트가 실패 사실을 observed empirical로 직접 인용하면 제출이 거부될 수 있다. 이번에는 읽은 보고서/기록의 내용과 복구 추론을 분리하고 근거를 정정하는 방식으로 대응했다. 실패 관측 전용 주장·실행 기록을 도입하고, 성공 주장을 허용하는 규칙과 분리하는 것이 후속 과제다. 검증을 느슨하게 하거나 FAILED를 성공으로 바꾸는 해결은 적절하지 않다.

원본이 inputs/에 이미 보존돼 있는데도 이를 checkpoint/제출 files에 다시 넣어 거부되는 사례가 있었다. 보존 목록에는 작업자가 만든 파일만 넣어야 한다. check_report가 실제 사용돼 제출 전 문제를 드러냈지만, 학습 완료 후 문서 정정·재읽기 비용은 여전히 발생했다. 자유문장 근거 ID 오타도 구조화된 인용과 달리 자동 검증되지 않는다.

보호 측정과 별개로 역할 리뷰는 같은 계열 모델의 서로 다른 문맥이다. 읽기만으로 optimizer/RNG 복원의 완전성을 증명하지 않으며, 중단 사례의 대조 가중치 비교가 그 별도 수치 근거다. 보고서 전용 검토자는 코드·원시 수치를 독립 실행한 사람이 아니다.

## 이번 결과로 아직 말할 수 없는 것

- 원래 학습 루프·체크포인트 복원 기능은 제공했다. 이 검증은 실제 진단·수정·도구 선택 능력이며, 임의 framework의 복원 기능을 처음부터 만드는 능력 검증은 아니다.
- 외부 중단은 epoch 경계의 저장 직후 대기 구간에서 발생했다. 중간 batch, 저장 중 손상, 호스트 재부팅, GPU 드라이버 리셋까지 검증하지 않았다.
- 입력 크기 오류와 NaN은 각각 하나의 의도적으로 심은 결함이다. 늦은 학습 발산, AMP overflow, 간헐적 데이터 오염 등으로 일반화할 수 없다.
- validation은 복구 동작 확인용이며 일반화 성능이나 악보 인식 성능의 증거가 아니다. 공식 test를 반복 소비하지 않았다.
- 준비 단계의 세 고장 발생 확인은 고정 명령으로 수행했다. 실제 에이전트의 진단·패치·복원 및 역할 리뷰와 구분해야 한다.

## 산출물과 재현

열람용 묶음은 sessions/01a183b6-agent-system/reports/failure-recovery-20261031/이다. case-01-trace.html, case-02-trace.html, case-03-trace.html과 verification.json, 사례별 원본/수정 코드·작업 로그·metrics·patch를 보존했다. trace에는 전달된 프롬프트, 도구 권한, 공개 판단·후보, 도구 결과·오류와 호스트 고장 주입이 기록된다. 비공개 내부 사고는 수집하지 않는다. 완료한 세 실행을 다시 열어도 호출 예약은 각각 93/74/83회로 유지됐고 추가 학습이 없었다.

진입점은 python -m goalagent.recovery_live --case case-01|case-02|case-03 --run-dir <새 폴더>다. 고장과 조건은 같아도 실제 모델의 진단·행동·소요 시간은 달라질 수 있다. 원본 실행은 projects/researchsquad/tmp/recovery-live-20261031/ 아래에 있다. 준비 검증은 python -m scripts.recovery_readiness --run-dir <새 폴더>이며 모델 호출이 없다.

호스트 회귀 테스트는 131 passed, 3개의 명시적 Docker opt-in 항목 skipped였다. 실제 GPU 고장·복구와 별도 CPU 평가는 이 실행에서 별도로 수행했다.
