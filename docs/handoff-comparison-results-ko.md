# 작업 출력 직접 전달·보고서 입력 개선: 실제 에이전트 재실험 비교

작성일: 2026-10-31. 두 기능을 각각 구현·커밋했고, 같은 Fashion-MNIST 과제를 실제 Codex 에이전트로 다시 실행했다. 고정 응답은 사용하지 않았다. 결과는 부분 개선이다. Engineering의 자료 포장과 보고서 필드 오류는 줄었지만, 전체 호출 수와 반복 읽기는 줄지 않았다.

## 구현과 커밋

- `24e4b82`: publish_job_outputs. 종료한 소유 작업의 파일을 검증하고 원본 바이트로 산출물 등록·리뷰용 복사를 수행한다. 최대 16개 파일, 파일당 16 MB, 묶음 64 MB다. 다른 담당자의 작업, 실행 중인 작업, 경로 이탈·링크·입력 덮어쓰기·내용이 다른 목적지 덮어쓰기는 거부한다. 출처는 Team 이벤트와 산출물, 담당자의 지속 문맥에 남는다.
- `3dffce5`: 보고서의 구조화된 입력과 check_report. 주장마다 document/empirical 범위를 요구하는 스키마와 실제 분류 enum을 제공한다. 내부 도구 프로토콜로 변환만 하고 근거나 판단을 자동 추정·수정하지 않는다. 기존 근거 검증은 그대로 적용한다. 선택적인 check_report는 같은 검증을 제출 전에 실행하지만 최종 승인이나 과학적 검증을 뜻하지 않는다.
- `1175aaf`: 기존 과제의 과학적 조건을 유지하면서 새 전달 방식만 안내하는 --efficient-handoff 실행 옵션을 별도로 기록했다.

## 비교 조건과 측정 정의

기준은 2026-10-30의 실제 에이전트 실행이고, 개선 후는 2026-10-31의 새 실행이다. 모델은 두 실행 모두 gpt-6-astra이며 역할별 effort·총 호출/시간 예산·승인 GPU 이미지·메모리/CPU 한도·공식 데이터 분리·필수 리뷰·최종 test 제한은 유지했다. 추가된 필수 행동은 새 출력 전달 도구 사용이다. 두 개선을 함께 적용한 한 번의 재실험이므로 각각의 인과 효과를 분리한 실험은 아니다.

에이전트의 선택은 고정하지 않았다. 기준 실행은 CNN width 16, 3 epoch, 마지막 epoch 선택이었다. 새 실행은 width 32, 5 epoch, validation 최고 checkpoint 선택이었다. 이는 같은 과제의 허용 범위 안이지만 구체적인 실험 계획은 다르다. 아래의 정확도 차이는 도구 개선의 효과로 해석하면 안 된다. 과거 기준 한 번과 새 실행 한 번의 관찰이며 제공자 지연과 모델 판단의 변동도 통제하지 못했다.

소요 시간은 가장 이른 trace 시작부터 마지막 종료까지의 벽시계 시간이다. 읽기 수는 성공한 read_file/read_job_output/read_evidence/read_artifact 호출이다. 동일 대상 재읽기는 같은 담당 업무 안에서의 같은 도구·파일/근거를 재조회한 횟수로, 다른 페이지를 읽은 경우도 포함한다. 동일 범위 재읽기는 offset·limit와 반환 내용까지 같은 경우만 센다. 재읽기가 모두 불필요한 작업이라는 뜻은 아니다.

## 전체 결과

| 지표 | 기준 | 개선 후 | 관찰 |
| --- | ---: | ---: | --- |
| 모델 호출 예약 | 145 | 146 | 1회 증가 |
| 제공자가 반환한 원본 응답 | 144 | 146 | 기준에는 서비스 용량 오류 1회, 새 실행에는 잘못된 도구/인자 조합 1회가 별도로 있음 |
| 런타임 액션으로 변환된 응답 | 144 | 145 | 1회 증가 |
| 벽시계 시간 | 36.36분 | 32.41분 | 약 10.9% 짧게 관측됨 |
| 성공한 읽기 | 81 | 85 | 4회 증가 |
| 동일 대상 추가 읽기 | 30 | 34 | 4회 증가; 페이지 분할 포함 |
| 동일 범위·동일 내용 추가 읽기 | 13 | 15 | 2회 증가 |

시간은 짧아졌지만 호출 수와 반복 읽기 감소라는 목표는 전체 흐름에서 달성하지 못했다. 이 관찰만으로 시스템이 10.9% 빨라졌다고 일반화하지 않는다.

## 어느 업무에서 줄었고 어디서 상쇄됐는가

| 역할 | 기준의 실행 액션 | 개선 후 |
| --- | ---: | ---: |
| experiment_engineer | 63 | 55 |
| researcher | 31 | 32 |
| critic | 37 | 46 |
| report_reader | 7 | 6 |
| coordinator | 6 | 6 |

이 표는 실제 도구 액션과 검증 거부를 포함하며, 도구 실행 이전에 거부된 응답은 제외한다. Researcher와 Critic은 계획 업무와 결과 검토를 합산했다.

Engineering에서는 원본 출력 파일을 포장하는 일이 줄었다. job 출력 읽기는 6회에서 2회로 줄었고, write_file은 10회에서 5회로 줄었다. 새 실행은 직접 전달 2회로 metrics·학습 로그·환경 정보 6개를 넘겼다. Engineering의 전체 읽기는 31→29회, 동일 범위 재읽기는 9→8회로 소폭 줄었다.

대신 Critic의 실행 액션은 37→46회로 늘었다. 새 실행에서 Critic은 출력 게시 근거를 두 작업 각각 확인하고, 모델 참조와 등록 기록도 대조했다. Researcher는 계획·결과 검토 합계 31→32회였다. 전달 도구가 줄인 자료 복사 비용이 검토와 재읽기 비용에 의해 상쇄됐다. 서로 다른 모델/epoch/선택 정책 때문에 모든 증가분을 새 도구 탓으로 귀속하지도 않는다.

새 Engineering도 checkpoint 뒤 계획과 코드를 다시 읽었다. 원본 전달 기능은 파일을 재생성하는 일을 줄였지만, 가설·선택 조건·확인 완료 사항을 지속적으로 기억하게 만드는 기능은 아니다. 다음 병목은 안정적인 실험 사실 요약과 이미 완료한 검토 항목의 재사용이다.

## 보고서 입력 개선의 효과와 남은 오류

보고서 필드/분류 형식으로 거부된 제출은 6→0회였다. 원본 모델 응답에서 기준 보고서는 문자열 인자였고, 새 실행의 보고서 인자 9개는 구조화된 객체였다. 새 실행에서는 scope 누락이나 잘못된 objection enum으로 거부되지 않았다.

근거가 전달 자료의 주장을 뒷받침하지 못해 거부된 보고서는 1→3회였다. 형식이 맞아도 근거가 맞지 않으면 기존 검증이 거부했고, 에이전트가 수정해 제출했다. 따라서 입력 구조 개선이 근거 판단의 정확성까지 해결한 것은 아니다.

새 입력 경로의 한계도 관찰됐다. 결과 검토 Researcher가 첫 list_files 액션에 보고서 객체를 인자로 넣었고, 정규화 단계가 실행 전에 거부했다. 현재 스키마는 문자열과 보고서 객체를 허용하지만 도구 이름과 인자 타입의 조합을 완전히 결합하지 않는다. 에이전트가 다음 호출에서 올바른 인자로 수정해 계속했다. 이 오류 1회를 원격 서비스 오류로 분류하거나 숨기지 않았다. 다음 스키마 개선은 도구별 판별 가능한 입력 분기다.

check_report는 구현·테스트했지만 이번 실제 재실험에서는 사용되지 않았다. 따라서 이 도구의 실사용 효과를 주장하지 않는다. 보고서 필드 오류 감소는 관찰된 구조화 입력 경로의 결과이고, 제출 전 점검 효과와는 구분한다.

## 검증 품질은 유지됐는가

기존 검증 장치는 유지됐으며 이번 실행에서도 다음 내용을 확인했다. 이는 일반적인 연구 품질의 비열등성을 통계적으로 입증한 결과는 아니다.

- 실제 GPU 작업 두 개가 성공했고, baseline metrics 읽기 뒤 공개 결정이 기록된 다음 CNN이 시작됐다. 이 순서는 액션 step으로 확인했다.
- 두 저장 모델을 신뢰된 코드의 별도 CPU 컨테이너에서 재계산했다. MLP 87.38%, CNN 90.00%가 기록된 선택 checkpoint의 validation 결과와 각각 일치했다. CNN의 마지막 epoch 89.74%와 저장된 4번째 epoch 90.00%를 혼동하지 않았다.
- 직접 전달한 6개 파일은 등록된 원본과 일치했고, Researcher와 Critic에게 전달된 사본도 모두 원본과 일치했다. 실제 리뷰 입력까지 바이트를 비교했다.
- Report Reader는 report_only 범위를 유지했다. 부모 산출물은 report.md 하나이고 다른 입력은 없었다. 모델 코드와 metrics 파일을 받지 않았다.
- 계획 Critic과 결과 Researcher·Critic·Report Reader의 필수 리뷰가 모두 PASS였고, Coordinator가 마지막 평가 후 단계를 완료했다.
- 공식 test 10,000개는 학습 작업에 전달하지 않았고, 선택이 끝난 후 최종 평가에만 사용했다. 선택 CNN의 test 정확도는 89.56%였다. 기준 실행의 87.55%와 비교해 도구 개선으로 정확도가 올랐다고 주장하지 않는다.
- 완료한 새 실행을 다시 열어도 예약 146회가 유지돼 추가 학습·모델 호출이 없었다.
- 가짜 근거, 보호 입력 제출, 실행 중/다른 소유자의 출력 게시, 경로 이탈·링크·덮어쓰기를 거부하는 테스트를 통과했다. 전체 회귀는 129 passed, 기본 실행에서 빠진 실제 Docker 3개도 따로 모두 통과했다. 기존 실제 Docker managed 검증은 보호 측정 실패→개선→필수 리뷰→재시작을 통과했다. 그 검증의 선택은 고정 시나리오이며 이번 실제 에이전트 재실험과 구분한다. 비교 집계가 페이지 읽기와 동일 범위 재읽기를 구분하고 부모 산출물 전달을 정확히 판독하는 테스트 2개도 별도로 통과했다.

## 역할별 실제 검토 결과

- researcher: Delivered and inspected plan.md for W-0001: MLP baseline, CNN challenger, falsifiable improvement hypothesis, feedback-dependent adaptation, validation selection, and bounded stopping. Independent review remains pending.
- critic: Independent PLAN review completed. PASS recorded through PLAN-review-auditor for frozen candidate task-feb95b2824d2014c7d6e386f. No significant planning defect found.
- experiment_engineer: Completed two GPU experiments and validation-based selection. The selected CNN achieved 90.00% validation accuracy versus the MLP baseline's 87.38%. Required artifacts and original job outputs are preserved. Independent reviews and the coordinator's single protected evaluation remain pending.
- researcher: Completed the independent research review and recorded PASS for STUDY-review-research. Delivered the review artifact with evidence attribution and limitations. Protected-test performance remains unknown.
- critic: Completed the independent audit of frozen revision (고정된 산출물). Recorded PASS for STUDY-review-auditor. No significant defect was identified within scope; protected test performance and other gates remain unestablished.
- report_reader: Report-only comprehension review completed; PASS recorded. The report clearly presents the comparison, validation-based selection, reported results, limitations, and pending protected evaluation. One minor clarification remains. This review does not independently verify training or accuracy or establish product acceptance.

## 남겨 둔 산출물과 재현

같은 폴더의 before-trace.html과 after-trace.html에 각 실행의 프롬프트·도구·공개 판단·오류·리뷰·호스트 사건이 들어 있다. comparison.json에는 지표 정의, 역할별 액션, 전달 바이트 감사, validation 감사와 원본 검토 요약을 포함했다. 숨은 사고는 기록하지 않는다.

구현 계약은 docs/handoff-report-input.md, 과제 진입점은 python -m goalagent.fashion_live --efficient-handoff --run-dir <새 실행 폴더>다. 비교는 python -m scripts.compare_fashion_studies --before <기준> --after <새 실행> --output <json>으로 재현한다. 새 모델 호출은 선택과 지연이 달라질 수 있다.

원본 폴더는 projects/researchsquad/tmp/fashion-live-01과 tmp/fashion-handoff-live-01이다. 원본 실행·데이터·모델·trace는 Git에 커밋하지 않았다. 다음 개선은 작업 결과와 이미 완료한 검사 내용을 지속 문맥으로 전달하고, 도구 이름과 입력 타입을 스키마 수준에서 결합하는 것이다. 이후 같은 모델 선택까지 통제한 여러 쌍의 실행으로 효율과 검증 품질을 다시 비교해야 한다.
