# LLM Wiki vNext 코드 리뷰 및 개선 보고서

## 1. 검토 개요

본 검토는 업로드된 `LLM Wiki vNext(18).zip`을 기준으로 수행했다. 목표는 다음 네 가지였다.

1. 현재 코드 구조와 운영 체계를 전반적으로 검토한다.
2. 실제 품질 게이트와 핵심 테스트를 가능한 범위에서 재실행해 신뢰도를 확인한다.
3. 자가 개선(self-improvement) 체계의 성숙도를 평가한다.
4. 우선순위가 분명한 개선 방안을 상세히 정리한다.

이번 리뷰는 **코드 품질**, **운영 안전성**, **검증 가능성**, **자가 개선의 폐루프 성숙도**, **배포/패키징 일관성**을 중심으로 봤다.

---

## 2. 검토 범위와 방법

### 2.1 검토 대상
- Python 파일: 235개
- `ops/scripts/*.py`: 132개
- 테스트 파일: 94개
- 테스트 함수: 약 489개
- 업로드 ZIP 내부 총 파일 수: 6,593개
- ZIP 상위 구성 비중
  - `.venv`: 5,018개
  - `ops`: 463개
  - `raw`: 404개
  - `tests`: 326개
  - `wiki`: 195개

### 2.2 수행한 검토 방식
- 저장소 구조/문서/정책 파일 검토
- 핵심 orchestration runtime 수동 리뷰
- 정적 점검 재실행
- 구조적 복잡도 리포트 생성
- 자가 개선 관련 보고서 재생성
- 대표 테스트 묶음 재실행

### 2.3 실제로 확인한 명령/결과 요약

#### 정적 점검
- `python3 -m ruff check ops/scripts tests tools` → **통과**
- `python3 -m mypy @ops/mypy-allowlist.txt` → **통과**
  - `132 source files` 기준 이슈 없음

#### 대표 테스트 재실행
- `tests/test_auto_improve_runtime.py`
- `tests/test_policy_runtime.py`
- `tests/test_structural_complexity_budget_runtime.py`
- `tests/test_mechanism_review.py`
- `tests/test_promotion_gate_exit_codes.py`
- `tests/test_run_mechanism_experiment_contracts.py`
- `tests/test_executor_runtime.py`
- `tests/test_observability_artifacts_runtime.py`
- `tests/test_filesystem_runtime.py`
- `tests/test_release_smoke.py`

위 대표 테스트 묶음은 모두 **통과**했다.

#### 생성/확인한 운영 리포트
- `structural_complexity_budget` → **attention**
- `mechanism_review` → **pass**
- `mutation_proposal` → **pass**
- `outcome_metrics` → 생성 성공
- `planning_gate_validate` → **pass**

---

## 3. 전체 진단 요약

### 총평
이 저장소는 단순한 스크립트 모음이 아니라, **정책 기반의 유지보수 런타임 + 검증 파이프라인 + 자가 개선 후보 선정 체계**를 갖춘 운영형 코드베이스다. 코드 품질의 기본기(정적 분석, 스키마 계약, 정책 검증, 리포트 산출, 테스트 계층화)는 상당히 잘 잡혀 있다.

다만, 자가 개선을 “돌릴 수 있는 상태”와 “지속적으로 최적화되는 상태”는 다르다. 현재 코드는 전자에는 도달해 있지만, 후자까지는 아직 아니다.

### 한 줄 판단
- **코드베이스 성숙도:** 높음
- **운영 안전성:** 높음
- **자가 개선 운영 성숙도:** 중상
- **정량 최적화/폐루프 자동화 성숙도:** 중간 이하

---

## 4. 강점

### 4.1 정책 중심의 설계가 명확하다
이 저장소의 가장 큰 장점은 “규칙이 코드 밖에서도 보인다”는 점이다.

- 정책 파일을 기준으로 런타임이 움직인다.
- `planning_gate`, `promotion_gate`, `warning_budget`, `complexity_budget`, `mechanism_review`, `mutation_proposal`처럼 의사결정 지점이 명시적이다.
- `schema` 검증이 강하게 연결되어 있어 산출물 계약이 흐트러질 가능성이 낮다.

이 구조는 코드 변경이 늘어나도 통제 지점을 잃지 않게 해준다.

### 4.2 테스트 전략이 실무적으로 잘 나뉘어 있다
테스트를 `fast`, `slow`, `integration`, `integration-heavy`, `public` 계층으로 나눈 점은 매우 좋다.

장점은 다음과 같다.
- 개발 루프에서 빠른 피드백 가능
- 무거운 검증은 별도 분리 가능
- 공개 surface와 full-vault surface를 구분 가능
- 계약 테스트와 실제 생성 smoke를 분리하여 비용을 통제함

“테스트가 많다”보다 더 중요한 것은 “테스트가 운영 경로를 반영한다”인데, 이 저장소는 그 점이 잘 되어 있다.

### 4.3 자가 개선을 위한 운영 흔적이 잘 남는다
다음 요소들이 특히 좋다.
- session / iteration / routing / executor / telemetry rollup
- quarantine 정책
- proposal queue
- mechanism review candidate 산출
- mutation proposal 우선순위화
- promotion decision trend / outcome metrics / runtime event log

즉, 단순히 “실험을 실행”하는 것이 아니라 **왜 실행했고, 어떤 결과가 나왔고, 그 결과를 어떤 정책으로 해석했는지**를 남기도록 설계되어 있다.

### 4.4 공급망/감사 관점의 확장성이 좋다
다음 기능이 이미 코드 표면에 존재한다.
- CycloneDX SBOM
- SPDX SBOM
- OpenVEX draft
- in-toto statement
- Sigstore bundle verification
- supply-chain provenance / gate

이는 일반적인 내부 도구 수준을 넘는 장점이다. 외부 공개, 공급자 검증, 릴리스 신뢰성까지 고려하는 구조다.

---

## 5. 핵심 문제점과 개선 필요 사항

아래는 우선순위 순으로 정리한 개선 포인트다.

### 5.1 [상] 배포/검토 아카이브 위생이 일관되지 않다
이번 업로드 ZIP에는 `.venv`가 5,018개 파일로 포함되어 있었다. 전체 ZIP 6,593개 중 대부분이 가상환경이다. 또한 raw snapshot 파일명이 매우 길어 일반적인 추출 환경에서 경로/파일명 문제가 발생했다.

#### 왜 문제인가
- 리뷰/배포/협업 아카이브가 불필요하게 무거워진다.
- 운영 코드와 로컬 개발 흔적이 섞여 재현성이 흐려진다.
- 코드 리뷰 대상과 데이터/로컬 아티팩트가 섞여 검토 비용이 급증한다.
- OS/파일시스템 제약에 따라 추출 실패가 발생할 수 있다.

#### 이번 검토에 미친 영향
`raw/web-snapshots` 전체를 안정적으로 추출하기 어려워, `wiki_lint`/`raw_registry_preflight`의 일부 실패는 **코드 결함이 아니라 아카이브/추출 제약의 영향**으로 보는 것이 타당하다. 따라서 content corpus 계열 실패는 이번 보고서에서 코드 결함으로 단정하지 않았다.

#### 개선 제안
1. 배포용 ZIP과 개발용 작업트리를 분리한다.
2. `.venv`, `tmp`, generated artifact, 대용량 raw를 기본 제외하는 **review bundle**을 표준화한다.
3. 이미 존재하는 `review_archive`, `public-export`, `sanitize-run-artifacts` 계열 흐름을 실제 handoff 절차의 기본 경로로 강제한다.
4. CI에서 “업로드/릴리스용 산출물 크기/포함 경로”를 검사하는 gate를 추가한다.

---

### 5.2 [상] 자가 개선 체계는 존재하지만, 아직 충분히 닫힌 폐루프는 아니다
실행 가능한 자가 개선 루프는 존재한다. 하지만 현재 산출물 기준으로는 다음과 같은 한계가 보인다.

#### 관측된 사실
- `mechanism_review`: 후보 0건
- `mutation_proposal`: proposal 0건
- `outcome_metrics.summary.attempts_considered`: 2
- `session_reports_considered`: 0
- `rollback_rehearsal_coverage_count`: 0
- `outcome_metrics_calibration.mode`: `audit_only`
- `gate_effect`: `none`
- `shadow_priority.status`: `disabled`

#### 해석
즉, 시스템은 다음 상태다.
- 실험을 관리할 구조는 있다.
- 실험 결과를 요약/관측하는 기능도 있다.
- 하지만 그 결과가 아직 충분히 누적되지 않았고,
- 누적된 결과가 후보 우선순위나 gate에 강하게 반영되지는 않는다.

이것은 “자가 개선 기능이 없다”가 아니라, **자가 개선이 아직 운영 데이터 기반의 양적 최적화 단계까지 올라오지 않았다**는 뜻이다.

#### 개선 제안
1. session report를 실제 운영 루프에서 지속적으로 남기도록 강제한다.
2. `outcome_metrics`를 audit-only에서 끝내지 말고, 제한된 범위에서 shadow mode → advisory mode → gated mode로 단계 승격한다.
3. rollback rehearsal을 최소한 핵심 proposal family에 대해 의무화한다.
4. candidate가 0개로 유지될 때도 “왜 0개인지”를 더 공격적으로 드러내는 deficit report를 만든다.
5. 최소 표본 수가 쌓이기 전까지는 family별 bootstrap target을 별도 운영한다.

---

### 5.3 [상] 핵심 orchestration 모듈에 복잡도가 집중된다
프로젝트 자체의 `structural_complexity_budget` 결과가 이를 잘 보여준다.

#### attention 대상
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/mechanism_run_workspace_runtime.py`
- `ops/scripts/policy_runtime.py`
- `ops/scripts/finalize_run_state_runtime.py`

#### function budget candidate
- `auto_improve_runtime._execute_evaluate_phase` → parameter count 초과
- `mechanism_run_workspace_runtime._execute_mutation_step` → function lines 초과
- `mechanism_run_workspace_runtime._repo_health_step` → function lines 초과
- `policy_runtime.validate_policy_registry_references` → function lines 초과
- `promotion_gate_mechanism_runtime.assemble_mechanism_promotion_report` → parameter count 초과

#### 왜 문제인가
현재는 테스트가 받쳐주고 있어 당장 위험하지는 않다. 그러나 orchestration 코드가 계속 커지면 다음 문제가 생긴다.
- 정책 추가 시 수정 지점이 넓어진다.
- 동작은 맞지만 변경 비용이 커진다.
- phase 간 책임 경계가 흐려진다.
- 회귀 시 원인 파악이 느려진다.

#### 개선 제안
1. **parameter object / dataclass request object**를 더 적극 도입한다.
2. `_execute_mutation_step`, `_repo_health_step`의 공통 흐름을 `command step executor`로 추상화한다.
3. `policy_runtime`는 validator registry 패턴으로 쪼개서 규칙 단위 테스트 가능성을 높인다.
4. 복잡도 budget을 지금보다 조금 더 실질적으로 운영한다.
   - 현재는 preview/attention 성격이 강하다.
   - 핵심 파일군부터 changed-files 기반 fail-on-attention을 점진적으로 강화하는 편이 좋다.

---

### 5.4 [중] 명령 실행/로그 기록/타임아웃 처리 패턴이 반복된다
`mechanism_run_workspace_runtime.py`를 보면 mutation command와 repo health command가 상당히 유사한 흐름을 가진다.

공통 요소:
- 명령 구성
- 실행
- stdout/stderr sanitize
- 로그 파일 기록
- timeout artifact 기록
- ledger append
- telemetry 기록
- 실패시 예외 전환

#### 문제점
반복 구조는 지금 당장 이해 가능하지만, 한쪽만 수정되면 동작/로그 계약이 엇갈릴 수 있다.

#### 개선 제안
- `run_command_step(spec, context, artifact_hooks, timeout_policy)` 같은 추상화 계층을 만들고,
- mutation / repo_health / validation command를 동일 골격 위에 태운다.

이렇게 하면 로깅 필드, artifact naming, timeout taxonomy, ledger event schema를 더 일관되게 유지할 수 있다.

---

### 5.5 [중] `policy_runtime.py`가 장기적으로 병목이 될 가능성이 높다
현재 `policy_runtime.py`는 정책 로딩 이상의 역할을 한다.

- safety invariant 검증
- registry reference 검증
- 복수 설정값 계약 검증
- error message 구성

즉, “정책 해석기”이자 “정책 정적 검증기” 역할을 동시에 맡고 있다.

#### 문제점
정책이 늘수록 이 파일은 유지보수 병목이 된다.

#### 개선 제안
다음처럼 분리하는 편이 좋다.
- `policy_loader_runtime.py`
- `policy_schema_runtime.py`
- `policy_safety_rules_runtime.py`
- `policy_registry_reference_runtime.py`
- `policy_error_format_runtime.py`

이렇게 나누면 정책 변경이 잦은 프로젝트에서 훨씬 버티기 쉽다.

---

### 5.6 [중] 자가 개선의 정량 지표는 있지만, 승격 로직 연결은 아직 약하다
`outcome_metrics`와 `mechanism_review`의 calibration 정보는 잘 만들어져 있다. 그러나 현재는 대부분 **진단용**이다.

이는 초기 단계에서는 바람직하지만, 계속 이 상태로 남아 있으면 다음 문제가 생긴다.
- 관측은 되는데 의사결정은 바뀌지 않는다.
- 지표 피로(metric fatigue)가 발생한다.
- 리포트가 많아질수록 실질 우선순위 개선이 느려진다.

#### 개선 제안
1. `gate_effect: none` → `advisory_only` → `bounded_priority_delta` → `gated` 순으로 승격한다.
2. family별로 먼저 승격한다. 전체 전면 적용보다 안전하다.
3. 승격 전제조건을 명시한다.
   - 최소 attempt 수
   - 최소 target attempt 수
   - rollback rehearsal coverage
   - defect escape proxy 안정성

---

### 5.7 [하] CLI wrapper 보일러플레이트가 반복된다
여러 스크립트가 다음 패턴을 반복한다.
- `if __package__ in (None, "")`
- fallback import
- `main()` wrapper
- 예외 → 종료코드 전환

이 패턴 자체는 나쁘지 않다. 다만 파일 수가 많아질수록 drift 가능성이 생긴다.

#### 개선 제안
- CLI bootstrap helper를 하나 만들고,
- 공통 종료 코드 처리, fallback path 설정, `display_path` 출력 패턴을 공용화한다.

이는 큰 문제가 아니라, 유지보수 피로를 줄이는 정리 작업에 가깝다.

---

### 5.8 [하] 커버리지/회귀 품질의 “보이는 숫자”가 더 있으면 좋다
테스트는 강하다. 다만 현재 표면상으로는 다음 숫자가 상대적으로 덜 보인다.
- coverage threshold
- changed-files coverage
- mutation testing 결과
- perf regression budget

#### 개선 제안
1. 핵심 orchestration 파일에 대해서만 먼저 branch coverage 기준을 둔다.
2. changed-files coverage warning을 도입한다.
3. perf budget은 전역이 아니라 대표 CLI 몇 개만 관리한다.
4. outcome metrics와 테스트 품질 지표를 같이 보는 dashboard를 추가한다.

---

## 6. 자가 개선 성숙도 평가

### 6.1 결론
현재 자가 개선 체계의 성숙도는 **“관리됨을 넘어 정의됨 단계에 들어선 상태”**로 판단한다.

가볍게 비유하면:
- **CMMI 관점:** Level 3 초중반에 가까움
- 아직 Level 4(정량적으로 관리되는 단계)라고 보기는 어렵다.

### 6.2 그렇게 본 이유

#### 이미 잘 된 것
- 정책/예산/허용 범위가 명시적이다.
- proposal → scaffold → execute/evaluate → persist → complete 흐름이 구조화되어 있다.
- quarantine, promotion, telemetry, artifact fingerprint, routing provenance가 있다.
- 실패를 숨기지 않고 ledger/event/report로 남긴다.
- 테스트와 정적 분석이 실제 운영 표면에 붙어 있다.

#### 아직 부족한 것
- 실험 표본이 너무 적다.
- session rollup 축적이 없다.
- rollback rehearsal coverage가 0이다.
- outcome metric이 우선순위/게이트에 실질 반영되지 않는다.
- candidate queue가 실제로 꾸준히 돌아가는 모습이 아직 보이지 않는다.

즉,
- **구조 성숙도는 높다.**
- **운영 데이터 축적 성숙도는 아직 낮다.**
- **정량 최적화 성숙도는 더 낮다.**

### 6.3 세부 점수(실무형 내부 평가)
다음은 이번 코드베이스에 맞춘 실무형 상대평가다.

| 영역 | 평가 | 코멘트 |
|---|---:|---|
| 정책/거버넌스 | 4.5 / 5 | 매우 강함 |
| 테스트/검증 | 4.2 / 5 | 구조와 계층화가 좋음 |
| 관측/감사 가능성 | 4.3 / 5 | artifact 중심 설계가 인상적 |
| 공급망/릴리스 신뢰성 | 4.0 / 5 | 기능은 강하나 handoff 일관성 보완 필요 |
| 자가 개선 실행 루프 | 3.4 / 5 | 실제로 돌릴 수 있음 |
| 자가 개선의 정량 최적화 | 2.6 / 5 | audit-only 성격이 강함 |
| 전체 자가 개선 성숙도 | **3.5 / 5** | 구조는 좋고, 운영 데이터가 더 필요 |

### 6.4 한 문장 판정
**“자동 개선을 안전하게 시도할 수 있는 구조는 갖췄지만, 아직 데이터 기반으로 스스로 더 잘 고른다고 말할 단계는 아니다.”**

---

## 7. 우선순위별 권고안

### P0 — 바로 손봐야 하는 것
1. 리뷰/배포용 bundle 표준화
   - `.venv`, 대형 raw, local artifact 기본 제외
2. 자가 개선 세션 산출물 강제 축적
   - session report 비어 있는 상태 해소
3. rollback rehearsal coverage 확보
   - 핵심 proposal family부터 의무화

### P1 — 다음 스프린트 권장
1. `policy_runtime.py` 분해
2. command step 공통 실행 추상화 도입
3. 복잡도 candidate 5개 우선 분해
4. outcome metric shadow priority를 bounded advisory로 승격

### P2 — 중기 개선
1. changed-files coverage 경고 도입
2. perf regression budget 일부 도입
3. proposal deficit report 추가
4. family별 자가 개선 bootstrap strategy 분리

---

## 8. 파일 단위 집중 개선 제안

### `ops/scripts/auto_improve_runtime.py`
#### 관찰
- orchestrator로서 역할은 명확하다.
- phase 분리는 꽤 잘 되어 있다.
- 다만 일부 함수는 호출 인자가 많고, phase 간 전달 데이터가 dict 중심이라 인터페이스가 점점 무거워질 위험이 있다.

#### 제안
- `ExecuteEvaluateContext`, `IterationContextPayload` 같은 dataclass를 늘린다.
- iteration-level state와 persistence payload를 더 강하게 구조화한다.
- 현재 phase helper 분리 방향은 맞으므로, 여기서는 “더 쪼개기”보다 “더 강한 타입 인터페이스”가 우선이다.

### `ops/scripts/mechanism_run_workspace_runtime.py`
#### 관찰
- 실제 작업공간에서 mutation/check/apply/discard를 다루는 핵심 파일이다.
- 운영상 중요한 만큼 artifact와 로그를 꼼꼼히 남긴다.
- 그러나 mutation step과 repo health step이 유사한 구조를 반복한다.

#### 제안
- command execution template을 도입한다.
- sanitize/log/timeout/ledger/telemetry를 동일 계약으로 묶는다.
- 이후 새로운 step이 생겨도 복제보다 조합으로 확장되게 만든다.

### `ops/scripts/policy_runtime.py`
#### 관찰
- policy gatekeeper 역할이 크다.
- 현재는 이 파일 하나가 너무 많은 종류의 검증을 담당한다.

#### 제안
- validator registry 패턴 도입
- 규칙 단위 함수 + 규칙 목록 등록 방식으로 전환
- 에러 메시지 포맷터 분리

### `ops/scripts/finalize_run_state_runtime.py`
#### 관찰
- closeout orchestration 특성상 라인 수가 budget 초과 상태다.
- 지금은 큰 문제는 아니지만, 릴리스/정산 로직은 자주 예외가 붙는 영역이라 선제 분해가 좋다.

#### 제안
- output assembly, state resolution, policy closeout decision을 별도 helper로 분리
- “무엇을 계산하는지”와 “어떻게 파일을 쓴다”를 나눈다.

---

## 9. 이번 검토에서 신뢰도 높게 본 항목 / 낮게 본 항목

### 신뢰도 높게 본 항목
- Python runtime 구조 품질
- 정적 분석 품질
- 대표 테스트 안정성
- 자가 개선 orchestration 구조
- 정책/스키마/리포트 기반 운영 방식

### 신뢰도 낮게 본 항목
- content corpus 자체의 무결성 상태
- raw snapshot 경로/등록 불일치 여부
- full-vault lint/eval 결과의 결함 귀속

이유는 업로드된 ZIP이 리뷰 친화적인 번들 형태가 아니었고, 긴 파일명 raw snapshot 전체를 안정적으로 추출하기 어려웠기 때문이다. 따라서 content corpus 계열 경고/실패는 **코드 결함**보다 **패키징/추출 조건의 영향**이 크다.

---

## 10. 최종 결론

이 저장소는 전반적으로 **잘 만든 운영형 코드베이스**다. 특히 다음이 인상적이다.
- 정책 중심 제어
- 테스트 계층화
- schema 기반 산출물 계약
- 자가 개선 실행 흐름의 명시성
- 공급망/감사 기능의 확장성

반면, 다음 두 가지는 반드시 보완해야 한다.

1. **자가 개선의 운영 데이터 축적과 정량 폐루프 강화**
   - 지금은 구조가 앞서 있고, 데이터 기반 최적화는 뒤따라가는 상태다.
2. **배포/검토 번들 위생의 표준화**
   - 지금 상태로는 리뷰 비용이 너무 높고 환경 의존 실패가 생긴다.

### 최종 판정
- **현재 품질 수준:** 높음
- **자가 개선 성숙도:** 중상
- **즉시 개선 필요도:** 높음
- **가장 중요한 보완 포인트:**
  - review/release bundle 표준화
  - session/rollback/metric 기반 폐루프 강화
  - orchestration 복잡도 분산

---

## 11. 참고한 외부 기준(평가 관점)

이번 성숙도 평가는 저장소 내부 실측을 우선으로 하고, 다음 공개 프레임워크의 관점을 보조적으로 참고했다.

- NIST Secure Software Development Framework (SSDF)
- NIST AI Risk Management Framework (AI RMF) / Generative AI Profile
- OWASP SAMM
- CMMI Maturity Levels
- SLSA
- Sigstore
- in-toto
- SPDX
- CycloneDX
- OpenVEX

주의할 점은, 이 보고서의 성숙도 평가는 위 프레임워크의 공식 인증이 아니라 **비유적/실무적 정렬 평가**라는 점이다.
