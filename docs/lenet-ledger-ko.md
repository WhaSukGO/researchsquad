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

## 6. 범위와 한계

- 스크립트 검사는 툴과 불변식을 검증한 것이지 자율 연구 품질을 검증한 것이 아니다(AGENTS.md 원칙).
- 템플릿 밖의 통찰은 원장에 들어가지 않는다. INVARIANT_TO, FITS_CHIP 템플릿과 다른 인물(Denker, Jackel, Boser, Bottou, Hinton), 심판의 LLM 시점 검사, 편지·미팅 트리거는 마일스톤 2다.
- `local` 비공유층은 입력 맵 전체 fan-in만 지원한다. `tie`는 `fan_in` 부분 연결을 지원한다(1989 LeNet-1의 8/12 맵 연결을 64,660 / 9,760으로 재현).
- 보호 평가는 실행당 4회로 제한된다. 테스트 분할은 학습 컨테이너에 마운트되지 않는다.
