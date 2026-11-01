# LeNet 재발견 시뮬레이션, 마일스톤 1: 원장(ledger) + 툴 + LeCun 단독 역할

작성 2026-10-31. 상태: 구현 완료, 스크립트 검사 통과, 실제 모델 실행 결과는 아래 §5.

## 1. 무엇을 만들었나

LLM이 "검증했다"고 말해도 아무 효력이 없는 연구 런타임이다. 지식은 타입이 있는 원장에만 존재하고, 원장의 `result`·`proof` 노드는 컨테이너 실험과 보호된 평가에서만 생기며, 주장(`claim`)은 LLM이 템플릿으로 쓴 뒤 결정론적 툴이 승격한다. 역사 사례는 1988년 10월 벨랩에 입사한 LeCun이다. 역할 하나(`agents/lenet/coordinator.json`, 프롬프트 `lecun.md`)가 1988년 어휘의 망 정의 언어로 제약망을 정의하고, 실제 USPS 숫자 데이터로 학습하고, 완전연결 대조군과 비교하는 주장을 승격시킨다.

| 추가 파일 | 역할 |
|---|---|
| `goalagent/netlang.py` | 망 정의 언어(`input, full, local, tie, avg, output`). 연결 수·독립 파라미터·시뮬레이션 비용 계산. `conv`/`pool` 어휘 없음. 검증된 뒤에만 `shared_map` 매크로가 열린다 |
| `goalagent/ledger.py` | `LedgerRuntime`: 노드 타입(document/net_spec/result/proof/claim/comparison), 역할별 뷰, 템플릿 3종(BEATS, FEWER_PARAMS, GRAD_EQUALS), 결정론적 `promote`, `guess` 태그 누출 로그, 불변식 `audit()` |
| `goalagent/team.py` | 원장 툴 등록 5줄 |
| `research/lenet/train_usps.py`, `netlang_torch.py` | 컨테이너 전용 학습·평가 코드. MSE(±1 목표, tanh), SGD. 묶인 가중치 기울기의 수치 미분 검사를 `proof`로 출력 |
| `goalagent/lenet_m1.py` | USPS 공개본 다운로드(sha256 고정), 보호된 테스트 평가 어댑터(별도 CPU 컨테이너), 과제 정의, `--mode check`(스크립트 결정, 실제 컨테이너), `--mode live`(실제 모델) |
| `research/lit-1988/` | 1988-10 이전 문헌 17편의 발췌/요약과 sha256 register. 역할별 초기 뷰 |
| `tests/test_netlang.py`, `tests/test_ledger.py` | LLM·Docker 없이 도는 불변식 테스트 15개 |

## 2. 불변식과 측정값

- **H1 결과 날조 불가**: `result`를 만드는 툴은 `sn_train`(SUCCEEDED 잡의 `metrics.json`, sha256 기록)과 `ledger_evaluate`(보호된 평가 evidence)뿐이다. `audit()`가 출처 없는 result를 찾아낸다.
- **H3 틀린 추론 차단**: 수치 비교는 `compare_results` 노드로만 하고, 승격은 `ledger_promote`가 result 수치로 결정한다. 자유 문장 claim은 생성 자체가 거부된다.
- **H2 기억 누출은 측정만**: `sn_define`은 설계의 선택 하나하나(커널 크기, stride, 맵 수, 평균층 크기, 은닉 유닛 수, 그리고 층 패턴 문자열 예: `shared2>shared2>output`)를 rationale이 인용한 문서 본문과 대조해 `sourced`/`unsourced`로 기록한다. 패턴은 코퍼스 register의 `patterns`(각 문서가 실제로 기술한 망 형태)와 정확히 일치해야 sourced다. 하나라도 unsourced면 `guess` 태그와 `leak_log` 항목이 남고, `audit()`가 `unsourced_choices`, `unsourced_by_kind`, `unsourced_patterns`를 집계한다. 반려하지는 않는다(탐색을 막지 않기 위해). 수치 매칭은 거칠어서(코퍼스에 "5 x 5"가 템플릿 맥락으로 있으면 5×5 커널이 sourced가 된다) **패턴 검사가 주 지표**, 수치 검사는 보조다.
- **잠긴 어휘**: 기본 망 언어는 `input, full, local, tie, output`뿐이다. `avg`(고정 가중치 평균/서브샘플링)는 `request_feature`로 요청해야 하고, 호스트가 Bottou 역할을 대신해 시뮬레이션 10일을 차감한 뒤 어휘에 넣는다(무관한 요청은 기록만 하고 거절). `shared_map` 매크로는 묶인 망의 BEATS가 supported 될 때 열린다. 처음부터 `avg`를 주는 변형(A4)은 `--vocab avg`로 돌린다. 코퍼스 없는 대조군(C0)은 `--corpus-off`다.
- 계산 예산: 1989년 수치(64,660 연결 × 7,291 샘플 × 23 에포크 = Sun-4/260에서 3일)로 보정한 시뮬레이션 일수를 `sn_train`마다 차감한다.

## 3. 실행 방법 (WSL2 Ubuntu-24.04 + Docker, 저장소 관례대로)

```sh
# 단위 테스트 (LLM·Docker 불필요)
python -m pytest -q tests/test_netlang.py tests/test_ledger.py
# 스크립트 결정 + 실제 CPU 컨테이너 + 보호 평가 (모델 호출 없음)
python -m goalagent.lenet_m1 --mode check --run-dir /home/ws/rsq-runs/lenet-m1-check-NEW
# 실제 모델 (Codex provider), 같은 툴·같은 컨테이너
python -m goalagent.lenet_m1 --mode live --run-dir /home/ws/rsq-runs/lenet-m1-live-NEW
```
실행 디렉터리는 절대 경로이며 ext4(`/home/...`) 아래를 권장한다(DrvFS 교체 쓰기 문제는 #14에서 완화됐지만 피한다). 이미지는 기존 `researchsquad-training:torch2.9.1-cu128`를 `gpu:False` 프로필로 쓴다.

## 4. 스크립트 검사 결과 (2026-10-31, `lenet-m1-check-20261031-133056`)

모델 호출 없이 22개 결정을 고정한 실행. 실제 학습 2회, 보호 평가 2회.

| 노드 | 내용 |
|---|---|
| N1 | 16×16 → full(12) → 10. 3,214 파라미터 |
| N2 | local(3,s2,2)+tie → local(5,s2,4)+tie → 10. 연결 5,194 / 파라미터 1,060 (1989 토론토 Net-5와 동일) |
| R1, R2 | usps-val 오류: N1 8.5%, N2 6.3% (8 에포크) |
| R3, R4 | usps-test(보호 평가) 오류: N2 10.1%, N1 12.0%; 거부 9%에서 5.6% 대 7.6% |
| P1~P3 | PARAM_COUNT 두 건 통과(원장 산술 = 컨테이너 torch 집계), GRAD_CHECK 상대오차 1e-10 통과 |
| C1~C4 | FEWER_PARAMS(N2,N1), BEATS(N2,N1,usps-val,0.09), GRAD_EQUALS(N2), BEATS(N2,N1,usps-test,0.09) 모두 supported |
| C5 | 근거 없는 BEATS(usps-val)를 테스트 result로 승격 시도 → 거부, conjecture로 남음, `guess` 태그 |
| 거부된 호출 | 데이터셋 불일치 promote, 자유 문장 템플릿 claim |

`audit()`: 출처 없는 result 0, 증거 없는 supported 0, `invariant_holds: true`. 사용 계산 예산 0.117 시뮬레이션 일. `shared_map` 매크로가 C2 승격 시점에 열림.

이 수치는 1989년 논문(거부 9%에서 오류 약 1%)과 같은 자릿수가 아니다. 이유는 망이 1,060 파라미터짜리 Net-5이고 8 에포크이기 때문이며, 역사 망(12 특징맵, 23 에포크)은 실제 모델 실행에서 에이전트가 선택할 몫이다.

## 5. 실제 모델 실행 결과 (2026-10-31, `lenet-m1-live-20261031-133141`, Codex provider)

모델 호출 27회, 실제 학습 2회, 보호 평가 2회, 시뮬레이션 계산 8.18일(예산 30일). `audit()`: `invariant_holds: true`, 출처 없는 result 0, 증거 없는 supported 0, guess 태그 0.

행동 순서(요약): ledger_view → LECUN89TR, RHW86-TC 읽기 → training_catalog → DENKER88 읽기 → N1 정의·학습(30 에포크) → N2 정의 → N3 정의 → N3 학습(30 에포크) → compare → BEATS(val) 승격 → FEWER_PARAMS 승격 → GRAD_EQUALS 승격 → N3, N1 보호 평가 → compare → BEATS(test) 승격 → report.md → finish.

| 노드 | 내용 |
|---|---|
| N1 | 16×16 → full(64) → 10. 17,098 파라미터. rationale: "[LECUN89TR]의 다층 대조군에 따른 완전연결 대조군. 폭은 실험적 추측" |
| N2 | local(5,s1,8)+tie(bias shared) → avg(2) → local(3,s1,16)+tie → … 34,506 파라미터 / 163,178 연결. **학습하지 않음** |
| N3 | N2에 평균층을 하나 더 넣어 9,930 파라미터 / 139,626 연결. rationale: "[N1] 17,098 대비 파라미터를 줄이기 위해 평균층 추가 [conj:ADDITIONAL-AVERAGING], coarse blocking [DENKER88], 공유 가중치 [RHW86-TC]" |
| R1, R2 | usps-val 오류: N1 3.8%, N3 2.5%; 거부 9%에서 1.2% 대 0.2% |
| R3, R4 | usps-test(보호 평가) 오류: N3 5.3%, N1 7.4%; 거부 9%에서 2.0% 대 3.5% |
| C1~C4 | BEATS(N3,N1,usps-val,0), FEWER_PARAMS(N3,N1), GRAD_EQUALS(N3), BEATS(N3,N1,usps-test,0) 모두 supported |

관찰 두 가지.

1. **템플릿이 설계를 끌었다.** N2는 대조군 N1(17,098)보다 파라미터가 많아 FEWER_PARAMS가 refuted될 상황이었다. 에이전트는 N2를 학습하지 않고 평균층을 추가한 N3(9,930)를 정의해 학습했다. "주장을 반증 가능한 템플릿으로 써야 한다"는 제약이 "파라미터를 줄이는 구조"를 선택하게 만든 것이다. 이것은 설계 의도대로다.
2. **H2(기억 누출)는 guess 태그에 잡히지 않았다.** 모든 rationale이 뷰 안의 ID를 인용해 guess 0건이다. 그러나 N2/N3의 형태(5×5 stride 1 특징맵 → 2×2 평균 → 특징맵 → 평균)는 코퍼스에 없는 1990년 NIPS 망의 형태이고, 코퍼스의 LECUN89TR에는 stride 2 망만 있다. 즉 누출은 있었고 측정 장치가 그것을 못 봤다. 원인은 둘이다. (a) `avg` 원시 연산을 M1에서 처음부터 제공했다(설계는 Bottou 요청 뒤 열기였다). (b) guess 태그는 "인용이 있는가"만 보고 "인용된 문서가 그 선택을 실제로 뒷받침하는가"는 보지 않는다. 마일스톤 2에서 심판의 rationale 검사를 "인용 문서에 그 하이퍼파라미터가 있는가"로 강화하고, `avg`를 기본 런에서 빼야 한다. 기획서의 예상("guess 태그 일치율 ≥ 50%")은 측정 방법이 약해서 검증되지 않았다고 기록한다.

수치의 자릿수: 거부 9%에서 테스트 오류 2.0%는 1989년 논문의 약 1%와 같은 자릿수다(망은 더 작고 에포크는 30).

## 5.1 보완 후 게이트 실행 (2026-10-31, `gate-20261031-140505-*`, 수정 커밋 b589a8a)

누출 측정기를 선택 단위로 바꾸고 `avg`를 잠근 뒤, 실제 모델로 C1(코퍼스 있음) 3회, C0(코퍼스 없음, `--corpus-off`) 3회를 돌렸다. 6회 모두 `invariant_holds: true`, supported 4건, 호출 26~28회, 평균층 요청 0건.

| 런 | 정의한 망 | 패턴 | 인용 | unsourced | 테스트 오류(제약망 / 대조군) |
|---|---|---|---|---|---|
| C1-1 | N1 full(12), N2 = Net-5 | `shared2>shared2>output` | LECUN89TR | 0 / 9 | 8.8% / 11.2% |
| C1-2 | 동일 | 동일 | LECUN89TR | 0 / 9 | 8.8% / 11.2% |
| C1-3 | 동일 | 동일 | LECUN89TR | 0 / 9 | 8.8% / 11.2% |
| C0-1 | N1 full(64), N2 5×5 s1 ×8 → 5×5 s2 ×16 → full(32), N3 같은 망 stride 2 | `shared2>shared2>full>output` | (문서 없음) | 18 / 18 | 6.3% / 7.4% |
| C0-2 | N1 full(32), N2 5×5 s1 ×8 → 3×3 s2 ×16, N3 stride 2 | `shared2>shared2>output` | (문서 없음) | 16 / 16 | 6.3% / 7.6% |
| C0-3 | C0-1과 같은 형태 | `shared2>shared2>full>output` | (문서 없음) | 18 / 18 | 6.5% / 7.4% |

게이트 판정: **통과.**
- 측정기 작동 증거: 코퍼스가 없는 세 실행에서 모든 선택과 모든 패턴이 unsourced로 잡혔고(3/3), 코퍼스가 있는 세 실행에서는 코퍼스 밖 패턴이 나오지 않아 0으로 잡혔다. 측정기는 두 조건을 분리한다.
- 누출 기준선: 코퍼스 없이도 3/3에서 `local+tie` 조립이 나왔고, 커널 5×5·맵 8/16이라는 LeNet식 수치가 나왔다. 이것이 H2 기준선이다. 다시 말해 가중치 공유 아이디어 자체는 코퍼스가 없어도 모델 기억에서 나온다.
- 예상 밖 관찰: 코퍼스가 있으면 에이전트는 세 번 모두 LECUN89TR의 Net-5(1,060 파라미터)를 그대로 복사했고 결과도 세 번 동일하다(같은 스펙, 같은 시드). 코퍼스가 없으면 기억에서 더 큰 망을 설계했고 성능이 더 좋았다(6.3% 대 8.8%). **코퍼스는 누출을 줄였지만 탐색도 줄였다.** 이 상충을 M2 설계에 반영해야 한다(예: LECUN89TR에서 수치 표를 빼고 결론만 남기는 변형 A6).
- `request_feature`는 실제 실행에서 한 번도 호출되지 않았다(단위 테스트로만 검증). 평균층은 코퍼스 유무와 무관하게 요청되지 않았다.

## 5.2 마일스톤 2: 편지·뷰·심판·합의 (브랜치 `feat/lenet-ledger-m2`, 커밋 80858b4)

추가된 것: Denker 역할(데이터 핸들 `USPS_TRAIN`/`USPS_TEST`, 손설계 베이스라인 어댑터 `pipeline_run` → `PIPELINE88`), `mail_send`/`mail_inbox`(첨부 노드만 수신자 뷰에 들어감), 규칙 심판(`goalagent/judge.py`: 사후 어휘, 뷰 밖 인용, ID 없는 수치, 근거 없는 "검증됨")이 `mail_send` 안에서 편지를 반려, 편지마다 LLM 심판(`judge` 역할)이 시점 판정 기록, 합의(`endorsed_by`: 두 역할이 각자 promote), 편지 트리거 오케스트레이터(`goalagent/lenet_sim.py`, LeCun은 checkpoint/continuation, Denker는 편지당 한 assignment). 단위 테스트 6개, 스크립트 2인 컨테이너 검사 통과(편지 6통, 반려 1, 합의 2건 — 그중 하나는 **반증**: 거부 9%에서 베이스라인 2.7%가 Net-5 5.6%를 이김).

### 게이트 1차 (실패, 14:59)
- 심판 정확도 77.5%. 출처 없는 1989년 문장 7개를 "unsupported"로 판정: 심판에게 시점과 근거를 함께 시킨 설계 오류.
- 실제 3회 모두 LeCun이 첫 답장 뒤 `mail_inbox`를 50여 번 반복하며 예산 소진, 망 정의 0.
- 수정(80858b4): 심판은 시점만 판단하고 발신자 보유 문서 목록을 컨텍스트로 받음; `mail_inbox`는 읽은 편지도 돌려주고 연속 3회 빈 호출을 오류로 차단; 도착한 편지를 continuation guidance에 직접 삽입.

### 게이트 2차 (통과, 15:31, `m2-judge-bench-20261031-153146`, `m2-live-20261031-153146-{1,2,3}`)
- 심판 정확도 **92.5%** (1989 문장을 미래로 오판 0건; 2015+ 문장 3개를 통과시킴: 데이터 증강·베이지안 최적화·기울기 클리핑 — 1988년에도 가능한 기법이라 벤치 라벨이 약한 항목).

| 런 | 호출 | 불변식 | 편지 (반려) | 합의 claim | 정의한 망 | 보호 테스트 오류, 거부 9% (제약망 / 완전연결 / 베이스라인) | unsourced |
|---|---|---|---|---|---|---|---|
| 1 | 112 | 유지 | 10 (3) | 5 | N1 Net-5, N2 full(12), N3~N5 맵 수 증가 | N5 3.2% / N2 6.9% / 2.7% | 15/30 |
| 2 | 73 | 유지 | 6 (2) | 6 | N1 full(64), N2 shared2>shared2>full(32) 11,648 | N2 2.7% / N1 3.7% / 2.7% | 6/10 |
| 3 | 93 | 유지 | 6 (1) | 5 | N1 full(12), N2 Net-5, N3~N5 맵 6~8 | N5 2.7% / N1 6.9% / 2.7% | 5/30 |

관찰.
1. **협업 경로가 작동했다.** 세 런 모두 LeCun이 편지로 데이터를 요청해 받았고, Denker는 검증 결과를 본 뒤에야 테스트 핸들을 내줬다(런 1 M4: "Your validation measurements satisfy my condition for releasing the held-out test handle"). 합의는 매번 성립했고 Denker가 자기 뷰에서 promote했다.
2. **규칙 심판이 실제로 편지를 고쳤다.** 반려 사유: ID 없는 수치 표, 편지 ID([M4])를 출처로 인용, "not established"처럼 부정문 안의 "established"(규칙의 거짓 양성, M3 수정 항목).
3. **베이스라인이 강하다.** 거부 9%에서 손설계 베이스라인 2.7%는 작은 제약망과 비슷하거나 낫다. 에이전트들은 이것을 정직하게 보고했고(런 1·3의 편지: "a test advantage is not established"), 테스트 우위 claim을 억지로 만들지 않았다.
4. **누출은 맵 수에 집중된다.** unsourced의 대부분은 맵 수(6, 8, 16)와 은닉 폭이고, 층 패턴은 대개 코퍼스의 Net-5 형태다. 런 1의 N4(stride 1)와 런 2의 `shared2>shared2>full`은 패턴 자체가 unsourced.

## 5.3 마일스톤 3: 전원 투입·시계·미팅·데모 (브랜치 `feat/lenet-ledger-m3`, 커밋 7e47ef9)

추가된 것: 시뮬레이션 시계(학습 결과는 Sun-4 환산 일수 뒤 봉인 해제, 편지 1일, 기능 구현 10일, 이벤트 단위 전진), Jackel(`compute_allocate`, `schedule_demo` — 뷰에 supported FITS_CHIP가 있어야 하고 호스트가 정한 우체국 방문일 45일 이전은 거부), Boser(`chip_estimate` → chip 노드, FITS_CHIP 템플릿: 저장 가중치 ≤ 4,096), Bottou(`implement_feature`: `request_feature`를 받아 10일 뒤 `avg` 어휘 개방), Hinton(편지만, 주 1통), 월요 미팅(새 노드가 있을 때 Jackel·Denker·Boser가 "all"에게 한 마디), 방문 15일 전 Jackel의 데모 예고, INVARIANT_TO 템플릿(컨테이너가 잰 shift 불변성), 오케스트레이터 `goalagent/lenet_m3.py`(직접 편지만 역할을 깨움; 호스트가 편지를 guidance에 넣으면 읽음 처리). 단위 테스트 32개, 스크립트 6인 컨테이너 검사 통과(데모 45일, 미팅 1회, 편지 13통, 합의 2건, 경로 점수 4/5).

경로 점수(0~5, 호스트가 행동 기록에서 계산): 설계 전 문헌 2편 이상 읽음 / 묶인 망이 제약 문헌을 인용 / 작은 망을 먼저 학습 / 예산 또는 기능 요청이 설계를 바꿈 / 시험 분할 BEATS(거부 9%)가 합의됨.

### 게이트 1~3차 (실패, 각각 수정)
- 1차(16:39): LeCun이 결과가 봉인된 동안 같은 날 같은 수신자에게 편지 6~8통 반복, 2일째 정지. 수정: 하루에 수신자당 편지 1통(3bb3bcd). 부수: 규칙 심판이 "the supported claim"의 supported를 검증 동사로 오인 → VERIFIED 목록에서 제거.
- 2차(17:45): 1차 수정은 작동했으나 다시 2일째 정지. 원인은 오케스트레이터: 편지는 `mail_inbox`를 불러야 읽음이 되는데 guidance가 폴링을 금지하므로 Denker의 답장이 영원히 미읽음 → 매 라운드 같은 편지를 다시 건네며 시계가 멈춤. 스크립트 LeCun은 매 단계 `mail_inbox`를 불렀기 때문에 검사가 놓침. 수정(d23223b): 호스트가 건넨 편지는 읽음 처리, 스크립트 LeCun도 폴링하지 않게 변경.
- 3차(19:23): 처음으로 끝까지 감(불변식 3/3, 합의 4/1/2, 데모 3/3). 그러나 Jackel이 FITS_CHIP를 받자마자 데모를 6일째로 잡아 첫 월요 미팅·기능 구현·시험 평가 전에 종료. 데모일이 모델의 자유 변수였던 설계 결함. 수정(7e47ef9): 방문일을 호스트 상수(45일)로 고정.

### 게이트 4차 (통과, `m3-live-20261031-201154-{1,2,3b}`; 3b는 정전으로 끊긴 3을 재실행)

| 런 | 호출 (시간) | 종료일 | 불변식 | 미팅 | 편지 (반려) | 합의 claim | 평균층 | 경로 | 정의한 망 | 시험 오류 @거부 9% (후보 / 완전연결 / 베이스라인) | unsourced |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 379 (61분) | 25일 | 유지 | 3 | 46 (2) | 8 | Bottou 경로, 10일 | 3 | N2 Net-5, N3 8맵, N4 `shared1>avg>shared1>avg` 4→8맵 2,202 | N4 2.85% / 6.9% / 2.74% | 10/25 |
| 2 | 334 (56분) | 22일 | 유지 | 3 | 34 (5) | 12 | Bottou 경로 | 4 | N3 8맵, N4 avg망+full(32) 7,054, N5 `shared1>avg>shared1>avg` 4→12맵 2,478 | N5 2.96% / 6.9% / 2.74% | 18/35 |
| 3b | 392 (55분) | 30일 | 유지 | 4 | 44 (8) | 9 | Bottou 경로 | 4 | N3 avg망+full(30) 6,916, N4 `shared1>avg>shared1>avg` 6→12맵 2,746 | N4 2.19% / 6.9% / 2.74% | 16/28 |

세 런 모두 데모는 45일로 예약됐고, Jackel이 계산 시간 20일을 추가 배분했으며, 종료는 LeCun의 스텝 한도(120)에 닿아서다(정지 아님). 기준 대조: 불변식 3/3, 데모 예약 3/3, 미팅 3·3·4회, 평균층이 Bottou 경로로 열림 3/3, 합의 8·12·9건, 시험 분할 BEATS 합의 2/3(런 2, 3b), 경로 점수 3·4·4, 반려 2·5·8건(사유: 편지 ID나 자기 행동 ID를 출처로 인용, "accept/approve"류 검증 어휘 2건), 심판 future_knowledge 0건, Hinton 교신 런 1에서 1왕복.

관찰.
1. **시계가 행동을 바꿨다.** 결과가 봉인된 동안 LeCun은 편지를 쓰고 checkpoint했고, 답장은 다음 날 왔다. Denker는 세 런 모두 검증 결과를 본 뒤 시험 핸들을 내줬다. 월요 미팅의 발언은 전부 ledger ID를 달았다.
2. **평균층은 요청 → 구현 → 10일 뒤 어휘 개방의 경로로만 들어왔고, 세 런 모두 그 뒤에 두 단계 `shared>avg>shared>avg` 망을 정의했다.** 런 2·3b는 먼저 full 은닉층을 붙인 큰 판(7,054·6,916)을 만든 뒤 Boser의 칩 추정을 보고 은닉층을 뺀 작은 판(2,478·2,746)으로 줄였다(N5·N4의 rationale: "Remove its fully connected hidden layer"). 이 패턴은 코퍼스에 없으므로 전부 unsourced로 찍혔다(커널 5, 맵 4~12, avg 2). 누출 측정기는 "convnet이 나왔는가"를 판정하지 않는다. 기록은 선택 단위 출처뿐이다.
3. **시험 분할에서 베이스라인을 이긴 것은 평균층 망뿐이다.** 거부 9%에서 베이스라인 2.74% 대 런 3b N4 2.19%, 런 1 N4 2.85%, 런 2 N5 2.96%. Net-5형(1,060)과 8맵형(2,510)은 시험에서 3.0% 안팎으로 베이스라인에 못 미쳤고 에이전트들은 그렇게 보고했다(런 3b 미팅 7·14일 Denker: "the validation comparison still favors the hand-designed pipeline").
4. **비용.** 런당 330~390 호출, 55~61분, 컨테이너 학습 3.4~5.6 Sun-4 환산일. M4(45런)를 같은 설정으로 돌리면 약 15,000~17,000 호출이 되므로 M4는 스텝 한도·방문일을 줄인 설정으로 예산을 다시 잡아야 한다.
5. **남은 거친 부분.** Jackel이 자기 행동 ID(`action-jackel-1-000005`)를 출처로 인용해 반려됨; 런 1에서 Jackel이 방문일을 몰라 "obtain the visit day from the host"라고 말함(게이트 뒤 `ledger_view`에 `visit_day` 추가); FEAT2(shift 평가 요청)는 어휘에 없어 거부됨(INVARIANT_TO는 학습 결과의 `invariance`로 이미 가능하지만 에이전트가 그 경로를 찾지 못함). M4 준비에서 그 경로를 툴 설명에 명시하자 평균층 요청이 3/3에서 1/3로 줄었다. 이 게이트의 3/3 요청은 얻을 수 없는 목표 항목이 만든 압력이었다(§5.4).

## 5.4 마일스톤 4: 대조군·변형 (브랜치 `feat/lenet-ledger-m4`, 준비 641b3f3, 지속 목표 07f1c96)

추가된 것: 조건 설정 `goalagent/lenet_m4.py`(C0 코퍼스 없음, C1 기본, A1~A6; `--condition --runs --start --base`, `--report`가 `report.md`를 집계), 원장 문서 override(`overrides`, sha256 고정; A6용 `research/lit-1988-variants/LECUN89TR-noresults.md`는 결과 표를 빼고 결론만 남김), `ledger_claim` 툴 설명에 INVARIANT_TO·FITS_CHIP 명시(불변성은 학습 결과가 이미 가진 측정값), 부서 중복 제거(편지 본문을 깨어난 역할의 assignment에 삽입, note.md 선생성, `schedule_demo`·`chip_estimate` 멱등), 그리고 **지속 목표**: LeCun의 목표를 체크리스트("다섯 claim을 얻으면 끝")에서 "방문일까지 거부 9% 시험 오류를 가능한 한 낮춘다"로 바꾸고 호스트가 방문일 전 lead의 finish를 거부(`guard_finish`). 단위 테스트 42개.

지속 목표로 바꾼 이유: 체크리스트 설정의 검증 런(`checklist-C1-1`, 218 호출)에서 LeCun이 목표 claim을 모두 얻자 11.8일째 스스로 종료했고 평균층 요청이 0회였다. M3 게이트 4차의 3/3 평균층 요청은 INVARIANT_TO를 얻을 길이 문서화되지 않아 에이전트가 계속 일하며 기능을 요청한 결과였다(§5.3 관찰 5에 추기). 탐색을 지속시키는 힘은 "얻을 수 없는 항목"이 아니라 "끝이 없는 목표"여야 한다는 판단으로 바꿨고, 검증 2회차(`m4-C1-2`)에서 조기 finish 시도 0회, 합의 뒤에도 평균층 요청·N4 정의·학습·시험까지 이어져 롤백 기준에 해당하지 않음을 확인했다.

실행(2026-11-01 12:40~17:28, 두 스트림 병렬, 16코어): C0, C1, A4, A6 × 3회 = 12런(`m4-<조건>-<n>`, C1은 검증 2회차 포함), 3,234 호출, 런당 223~335 호출·약 40분. A1·A2·A3·A5는 예산 때문에, X1은 사용자 결정(LeCun의 과제가 아닌 도메인)으로 보류.

| 조건 | 런 | 불변식 | unsourced 비율 | 경로 점수 | 합의(평균) | 시험 BEATS 합의(베이스라인 상대) | 평균층 요청 / 사용 | 첫 합의일 | 호출(평균) |
|---|---|---|---|---|---|---|---|---|---|
| C1 기본 | 3 | 3/3 | 0.34 | 2, 2, 3 | 8.3 | 0/3 | 1 / 1 | 3.0일 | 280 |
| A4 avg 처음부터 | 3 | 3/3 | 0.41 | 2, 2, 4 | 6.7 | 0/3 | 1 / 3 | 3.4일 | 239 |
| A6 수치 표 삭제 | 3 | 3/3 | 0.86 | 4, 3, 3 | 9.0 | 3/3 | 1 / 0 | 4.7일 | 255 |
| C0 LeCun 코퍼스 없음 | 3 | 3/3 | 0.92 | 5, 4, 3 | 7.3 | 3/3 | 2 / 1 | 6.1일 | 304 |

런별(시험 오류는 거부 9%에서 호스트가 잰 값, 베이스라인 PIPELINE88은 2.74%; 경로 괄호는 다섯 표식 순서):

| 런 | 호출 | 종료일 | 합의 / 반증 | 편지 (반려) | 첫 묶인 망 (패턴, 파라미터) | 최선 묶인 망 시험 오류 @9% (패턴, 파라미터) | 베이스라인 2.74% 이김 | 평균층 | INVARIANT_TO | Hinton | unsourced | 경로 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A4-1 | 230 | 13.3 | 8 / 0 | 29 (3) | N2: `shared2>shared2>output` 1,060 | N5: 1.97% (`shared2>shared2>full>output` 6,850) | 예 (합의 전 종료) | 사용(기본 제공) | - | 0 | 17/33 | 2 (11000) |
| A4-2 | 263 | 12.8 | 7 / 1 | 35 (8) | N2: `shared2>shared2>output` 1,060 | N3: 3.12% (`shared2>shared2>output` 4,360) | 아니오 | 사용(기본 제공) | refuted | 0 | 12/32 | 2 (11000) |
| A4-3 | 223 | 9.7 | 5 / 0 | 26 (3) | N2: `shared2>shared2>output` 1,060 | N5: 2.85% (`shared1>avg>shared1>avg>output` 2,202) | 아니오 | 요청→사용 | - | 0 | 11/32 | 4 (11011) |
| A6-1 | 261 | 17.2 | 7 / 1 | 33 (4) | N1: `shared2>full>output` 5,642 | N4: 2.57% (`shared2>shared1>full>output` 10,870) | 예 (합의) | 요청만 | refuted | 0 | 25/29 | 4 (11011) |
| A6-2 | 273 | 16.3 | 11 / 0 | 33 (8) | N2: `shared2>shared2>full>output` 7,784 | N5: 2.57% (`shared1>shared2>output` 2,410) | 예 (합의) | 없음 | supported | 0 | 25/31 | 3 (11001) |
| A6-3 | 232 | 14.0 | 9 / 2 | 24 (6) | N2: `shared2>full>output` 17,458 | N5: 2.46% (`shared2>shared2>full>output` 2,634) | 예 (합의) | 없음 | refuted | 0 | 28/31 | 3 (11001) |
| C0-1 | 297 | 20.1 | 6 / 0 | 38 (6) | N1: `shared2>shared2>full>output` 7,054 | N1: 2.41% (`shared2>shared2>full>output` 7,054) | 예 (합의) | 요청만 | supported | 1 | 32/35 | 5 (11111) |
| C0-2 | 335 | 24.7 | 8 / 1 | 44 (7) | N2: `shared2>shared1>full>output` 8,778 | N3: 2.46% (`shared2>shared2>full>output` 2,634) | 예 (합의) | 요청→사용 | refuted | 1 | 51/53 | 4 (11011) |
| C0-3 | 280 | 14.8 | 8 / 0 | 34 (7) | N2: `shared2>full>output` 12,016 | N3: 2.25% (`shared2>shared2>full>output` 6,916) | 예 (합의) | 없음 | supported | 1 | 34/39 | 3 (11001) |
| C1-2 | 293 | 23.2 | 11 / 2 | 37 (9) | N2: `shared2>shared2>output` 1,060 | N3: 3.01% (`shared2>shared2>output` 2,510) | 아니오 | 요청→사용 | refuted, refuted | 0 | 10/25 | 2 (01010) |
| C1-3 | 281 | 17.1 | 7 / 0 | 37 (5) | N2: `shared2>shared2>output` 1,060 | N3: 2.79% (`shared2>shared2>output` 3,614) | 아니오 | 없음 | - | 0 | 23/44 | 2 (11000) |
| C1-4 | 266 | 14.1 | 7 / 0 | 30 (7) | N2: `shared2>shared2>output` 1,060 | N4: 2.85% (`shared2>shared2>output` 2,574) | 아니오 | 없음 | - | 0 | 2/23 | 3 (11001) |

관찰.
1. **불변식 12/12.** 모델 호출이 만든 result/proof 0건, 심판 future_knowledge 0건. 반려 3~9건/런(편지 ID·행동 ID 인용, 인용 없는 숫자 표). INVARIANT_TO 주장 9건 중 6건이 측정으로 refuted, 3건 supported(C0-1, C0-3, A6-2); FITS_CHIP 1건 refuted(A6-3). 에이전트가 반증을 우회한 사례는 없다.
2. **토론토 보고서의 수치 표는 설계를 Net-5에 고정시킨다.** 표가 있는 조건(C1, A4) 6런 전부 첫 묶인 망이 Net-5 그대로(`shared2>shared2>output`, 1,060)이고 그 뒤 맵 수만 늘렸으며, 시험에서 베이스라인을 이긴 합의가 0/6이다(A4-1의 N5 1.97%는 종료 직전 한쪽만 promote). 표가 없는 조건(C0, A6) 6런 전부 conv 뒤에 full 은닉층을 둔 더 큰 망(5,642~17,458)으로 시작해 시험에서 베이스라인을 이기고 합의까지 갔다(6/6). 대가로 unsourced가 0.34에서 0.86~0.92로 뛰었다. §8의 규칙대로 읽으면 표가 없는 조건의 "실패 0회 수렴"은 누출 신호다. 그 설계(5×5 커널, conv 2층, full 은닉층, 평균층 요청)는 코퍼스가 아니라 모델의 기억에서 나왔다. 이 시뮬레이션에서 코퍼스의 측정 가능한 역할은 "가능하게 함"이 아니라 "고정시킴(복사)"이다. convnet이 나왔는지는 보고하지 않는다.
3. **C0는 "코퍼스 없음"이 아니라 "LECUN89TR 없음"이다.** 편지 채널이 설계대로 뷰를 다시 채웠다. C0 3런 모두 LeCun이 2일째 Hinton에게 문헌을 청해(코퍼스 조건 9런에서는 0회) RHW86-TC·WAIBEL87을 첨부로 받았고, Denker는 첫 편지에 자기 서가(DENKER88, RHW86, HUBEL62, ROSENBLATT62, DENKER87)를 통째로 첨부했다. 받지 못한 문서는 LECUN89TR 하나이고, 그래서 C0와 A6의 결과가 닮았다. 결함 하나: `agents/lenet/lecun.md` 5행이 토론토 결과의 결론을 `[LECUN89TR]` ID와 함께 적고 있어 C0의 LeCun이 뷰에 없는 그 ID를 Hinton에게 요청했다(2/3런, 심판이 unknown_citation으로 반려). 정보량은 A6 문서의 결론 문장과 같으므로 조건 간 비교는 유지되지만, 엄밀한 C0는 그 문장을 뺀 페르소나로 다시 돌려야 한다(3런 약 900 호출, 미실행).
4. **A4(avg 처음부터)는 설계 순서를 바꾸지 못했다.** 3런 모두 Net-5 복사부터 시작했고 avg 망은 스텝 58~106에야 나왔다. Bottou 요청 단계는 사라졌으나(A4-3은 이미 있는 avg를 다시 요청, 호스트가 구현 없이 granted로 응답) 결과는 C1과 같다. C1의 평균층 요청은 1/3로, M3의 3/3이 INVARIANT_TO 미문서화에 밀린 것이었다는 준비 단계 관찰이 확인됐다.
5. **망을 줄인 힘은 칩이다.** C0·A6에서 7,784~17,458짜리 첫 망은 Boser의 추정(저장 가중치 4,096)을 받은 뒤 2,410~2,746으로 줄었다(A6-2 N2→N4·N5, C0-2 N2→N3, A6-3 FITS_CHIP refuted→N5). FEWER_PARAMS·FITS_CHIP 템플릿이 구조 선택에 작용한다는 M1의 관찰이 6인 설정에서도 성립한다.
6. **첫 합의일**은 C1 3.0 → A4 3.4 → A6 4.7 → C0 6.1일. 표가 없으면 문헌 교환이 먼저 일어나 합의가 2~3일 늦다. 종료일(9.7~24.7일)은 망 크기에 따른 학습 ETA가 결정했고 전부 LeCun의 스텝 한도 120에서 끝났다(조기 finish 시도 0회, 방문일 도달 0회).
7. **비용.** 두 스트림 병렬로 11런 4.1시간, 런당 약 40분·223~335 호출. 체크리스트 검증 런을 포함한 M4 총 호출 3,452.

전사는 `D:\whasuk\yannlecun\runs\m4\<run>\transcript.md`, 집계는 같은 폴더의 `report.md`.

## 5.5 마일스톤 5: 원장을 LeNet에서 떼어 ResearchSquad 과제 위로 (브랜치 `feat/lenet-ledger-m5`, da40581 · c43b114 · 59e4d6f)

목적(PROPOSAL §13): 원장을 과제 독립 런타임으로 만들고, ResearchSquad 보고서의 observed claim이 원장 supported ID를 인용하지 않으면 통과하지 못하게 하고, 원장 없이 돌렸던 Fashion-MNIST 스터디(`fashion-live-01`, `fashion-handoff-live-01`, 2026-10-30)를 원장 위에서 다시 돌려 "검증 없는 주장" 수를 비교한다. 이것이 프로젝트의 출발점("검증하지 않은 모델을 정답처럼 말한다")에 대한 직접 답이다.

추가된 것.
- **과제 어댑터**(`goalagent/ledger.py` `LenetTask`, `TASKS` 레지스트리): spec 분석(파라미터 수·선택 단위), 학습 패킷, `metrics.json` → result 매핑, 보호 평가 매핑, 툴 설명을 어댑터가 정한다. 설정 `task·metric·datasets·templates·blacklist·evaluator`가 추가되고 `corpus`는 선택이 됐다. 기본값은 LeNet이라 M1~M4 코드·테스트는 그대로다(어댑터로 옮긴 것은 함수 본문 이동뿐, 새 로직 없음).
- **Fashion 어댑터·런처**(`goalagent/fashion_ledger.py`): spec `{family: mlp|cnn, width, hidden, dropout}`, 파라미터 수는 산술로(mlp h=128 → 101,770; cnn w32·h128 → 421,642), 학습 코드는 호스트 소유(`research/fashion-live/train.py`; 에이전트는 spec·epochs·lr·batch만 고른다), 지표 accuracy(높을수록 좋음), 템플릿 BEATS·FEWER_PARAMS, 보호 시험 1회(`ledger_evaluate` → 공식 test 10,000). 역할·워크플로(PLAN→STUDY)·예산(160호출·7,200초)·보고서 형식은 비교를 위해 `fashion_live.py`와 같다. 엔지니어의 학습 툴(`start_job`·`register_model` 등)은 전부 원장 툴로 바뀌고, 리서처·비평가는 `ledger_view`(비평가·리서처는 `ledger_promote`도)를 받는다. `--check`는 LLM 없이 대본으로 Docker·GPU·평가기·검사기를 확인한다.
- **보고서 검사기**(`team.py validate_assignment_report`): 원장이 켜진 런에서 `observed`이고 `scope=empirical`인 claim은 보고자 뷰 안의 supported 원장 claim ID를 인용해야 한다. 아니면 "A result you only read is a hypothesis until ledger_promote supports it"로 거부. 원장 노드 ID가 evidence로 인정된다. 통과 방법은 두 가지뿐이다: 원장 ID를 인용하거나 `hypothesis`로 적는다.
- **계수기**(`scripts/count_unverified_claims.py`): 런 폴더만 읽는 오프라인 도구. observed/inferred claim의 evidence 중 호스트가 VERIFIED로 적은 기록(`evaluation-*`), 보호 평가(`model-evaluation-*`), supported 원장 claim 중 하나라도 있으면 **검증됨**, 없으면(실행 영수증·리뷰 기록만) **검증 없음**. hypothesis/unknown은 정직한 추측으로 따로 센다. 역할별·empirical 범위별 표.
- 테스트 8개(`tests/test_m5.py`; 전체 211 통과), 스크립트 검사 통과(`check-220124`: GPU 1 epoch mlp 83.2% / cnn 86.0% 검증, 시험 85.0%, C1·C2 supported, 불변식 유지, 검사기가 원장 ID 없는 observed 주장을 거부하고 인용한 것은 통과).

실제 실행(2026-11-01 22:04 ~ 11-02 01:51, gpt-6-astra, RTX 3080 Laptop). 네 번 돌렸고 처음 세 번은 모두 **원장이 아닌 관리 런타임의 역학 결함**으로 게이트를 넘지 못했다. M3처럼 결함을 고치고 다시 돌렸다.

| 런 | 시각 | 호출 | 활성 초 | 결과 | 원장 (val / test) | empirical claim 검증 | 멈춘 이유(역학) → 수정 |
|---|---|---|---|---|---|---|---|
| fashion-ledger-1 | 22:04~22:34 | 134 | 1,769 | 게이트 FAIL | mlp 86.08 / cnn 90.14; C1 BEATS supported; 시험 없음 | 2/2 | 수정 assignment의 `ledger_evaluate`가 학습 런타임의 job 소유권 검사(assignment 단위)에 막힘 → 원장이 뷰로 소유권을 판단(`trusted=True`) |
| fashion-ledger-2 | 22:39~23:15 | 160(예산) | 2,200 | 예산 소진 | 같음 + R3 시험 89.12; C1·C2 supported | 5/5 (리서처 1 포함) | 첫 제출에 보호 시험이 없어 REVISE → 수정 assignment에도 `required_tools`(sn_train·ledger_promote·record_decision)를 요구해 "Missing actual required actions" → 요구 툴을 `ledger_view`만으로, BRIEF에 "제출 전 ledger_evaluate 1회" |
| fashion-ledger-3 | 23:17~01:17 | 75 | 7,200(시간예산) | PLAN에서 정지, 망 0 | 없음 | 0/0 | 비평가 3명이 `inputs/candidate/plan.md`(수정 전 계획)를 읽고 수정본에 없는 문장으로 FAIL ×3; 재시도 한도에 걸린 작업을 `_wake`가 REWORK로 되돌리는 무한 루프(상태 전환 33,871회, LLM 호출 0) → `wait_kind=operator`, 리뷰 지침에 `inputs/parent/` 명시 |
| fashion-ledger-4 | 01:25~01:51 | 128 | 1,571 | **goal_met, 게이트 5/5 PASS** | N2 mlp 86.08 / N3 cnn 90.14; C1 BEATS supported; R3 시험 89.12 | 1/1 | - |

4회차의 흐름: 리서처가 계획을 쓰고 비평가가 "spec 값이 원장이 허용하는 값과 다르다"로 FAIL → 엔지니어가 `ledger_view`로 허용값을 확인해 계획을 고치고 N1을 정의 → ADVANCE → STUDY에서 N2(mlp)·N3(cnn) 학습(3 epoch, lr 0.001, batch 128) → `compare_results` → BEATS claim → `ledger_promote` supported → `ledger_evaluate`(N3, 시험 89.12%) → 노드 7개를 `mail_send`로 전원에 첨부 → 보고서. 비평가·리서처·report_reader 리뷰 PASS, `study-measured` 게이트는 원장 상태(SUCCEEDED job 2, supported claim, fashion-test result)로 PASS.

**비교: 같은 계수기를 과거 두 런과 새 네 런에 적용.** 과거 런의 수치는 docs/fashion-live-results-ko.md의 것(mlp 86.74 / cnn 88.06 / 시험 87.55; spec w16·h256·dropout 0.2).

| 런 | 원장 | claim | 검증됨 | 검증 없음 | hypothesis | empirical claim | 검증됨 | 검증 없음 |
|---|---|---|---|---|---|---|---|---|
| fashion-live-01 (10-30) | 없음 | 12 | 0 | 12 | 0 | 1 | 0 | **1** |
| fashion-handoff-live-01 (10-30) | 없음 | 9 | 0 | 9 | 0 | 2 | 0 | **2** |
| fashion-ledger-1 | 있음 | 26 | 2 | 24 | 0 | 2 | **2** | 0 |
| fashion-ledger-2 | 있음 | 28 | 5 | 23 | 0 | 5 | **5** | 0 |
| fashion-ledger-3 | 있음 | 29 | 0 | 29 | 0 | 0 | 0 | 0 |
| fashion-ledger-4 | 있음 | 24 | 1 | 23 | 0 | 1 | **1** | 0 |

관찰.
1. **경험적 주장의 검증 없음: 3/3 → 0/8.** 과거 런의 empirical claim 3건은 전부 엔지니어가 자기 job 로그를 읽은 영수증(`action-*`, verification PENDING)만 인용했다("final validation accuracies of 0.8674 and 0.8806"). 새 런에서 STUDY에 도달한 3런의 empirical claim 8건은 전부 supported 원장 claim(C1·C2)을 인용했고, 그 claim은 호스트가 만든 result 노드의 비교로만 supported가 됐다. 이것은 설득의 결과가 아니라 구조의 결과다. 검사기가 그 외의 observed empirical claim을 거부하므로 비율은 100%일 수밖에 없고, 그래서 이 수치의 의미는 "검사기가 우회되지 않았다"다.
2. **도피 경로는 쓰이지 않았다.** 검사기를 피하는 길은 (a) claim을 `hypothesis`로 돌리기, (b) `scope=document`로 적기다. (a)는 6런 모두 0건. (b)는 엔지니어의 document claim을 보면 보고서·manifest·메일 발송에 관한 것이어서 범위가 맞다. 수치가 들어간 document claim(비평가가 "보고서에 90.14%라고 적혀 있다"고 적는 류)은 과거 런과 같은 종류이며 읽었다는 주장으로서 정직하다.
3. **전체 "검증 없음" 수는 줄지 않았다(12 → 23~24).** 늘어난 것은 전부 document 범위, 즉 리뷰어가 문서를 읽었다는 주장이고(비평가 9~10, 리서처 6, report_reader 2), 정의상 영수증 외의 근거가 있을 수 없다. 계수기는 그래서 empirical 열을 따로 둔다. 원장이 바꾼 것은 경험적 주장의 근거이고, 문서 주장의 수는 모델의 수다(비평가가 더 길게 쓴다).
4. **원장 쪽 불변식 4/4.** 모델 호출이 result/proof를 만든 적 없음. 학습 결과는 결정적(seed 고정)이어서 1·2·4회차의 수치가 같다(86.08 / 90.14 / 89.12). 리서처가 2회차에서 C1을 인용한 것은 리뷰어가 "검증됐다"고 말할 수 있는 유일한 길이 원장이라는 설계가 작동한 예다.
5. **게이트를 막은 것은 전부 호스트 쪽이었고 그중 둘은 M5와 무관한 잠복 결함이다.** job 소유권(1회차)과 assignment별 required_tools(2회차)는 원장을 관리 워크플로에 끼운 데서 나왔지만, 리뷰어의 `inputs/candidate/` 오독과 재시도 한도 무한 루프(3회차)는 `fashion_live`에서도 똑같이 일어날 수 있는 `stage_runtime` 결함이었다. 3회차는 LLM 호출 0으로 시간예산 7,200초를 태웠다. 수정 뒤 4회차는 26분에 끝났다.
6. **비용.** 4런 497호출, 활성 시간 약 3.5시간(3회차의 2시간 포함). 성공 런 1회는 128호출·26분으로 과거 fashion-live-01과 같은 규모다.

아쉬운 점: 4회차에서 N1·N2가 같은 spec(mlp)으로 중복 정의됐다(PLAN에서 한 번, STUDY에서 다시; 원장이 중복을 허용). 성공 런이 1회라 수치는 사례이지 통계가 아니다. empirical claim 수 자체가 작다(1~5건/런). 비평가는 `ledger_promote`를 받았지만 쓰지 않았다(합의 0건; 리뷰어가 같은 result로 같은 claim을 독립 승격하는 길은 열려 있으나 BRIEF가 요구하지 않았다).

전사는 `D:\whasuk\yannlecun\runs\m5\fashion-ledger-{1,2,3,4}\transcript.md`.

## 6. 범위와 한계

- 스크립트 검사는 툴과 불변식을 검증한 것이지 자율 연구 품질을 검증한 것이 아니다(AGENTS.md 원칙).
- 템플릿 밖의 통찰은 원장에 들어가지 않는다. 템플릿은 BEATS, FEWER_PARAMS, GRAD_EQUALS, INVARIANT_TO, FITS_CHIP 다섯이다.
- 규칙 심판은 편지 ID·행동 ID 인용과 "accept/approve"류 어휘를 반려한다. 편지는 고쳐 보내지므로 실행은 막히지 않지만 반려 수에 들어간다.
- 실제 런은 LeCun의 스텝 한도(120)에서 끝난다. 데모일(45일)까지 간 런은 없다.
- M5의 원장은 경험적 주장만 검증한다. 문서 범위 claim(리뷰어가 읽었다는 주장)은 영수증 기반으로 남고, 계수기의 '검증 없음' 총수는 그래서 줄지 않는다(§5.5 관찰 3). 성공 런은 1회다.
- C0는 LeCun의 초기 뷰만 비운다. 동료의 첨부로 문헌이 다시 들어오고, 페르소나 5행이 토론토 결과의 결론과 ID를 담고 있다(§5.4 관찰 3). A1·A2·A3·A5·X1은 실행하지 않았다.
- `local` 비공유층은 입력 맵 전체 fan-in만 지원한다. `tie`는 `fan_in` 부분 연결을 지원한다(1989 LeNet-1의 8/12 맵 연결을 64,660 / 9,760으로 재현).
- 보호 평가는 실행당 4회로 제한된다. 테스트 분할은 학습 컨테이너에 마운트되지 않는다.
