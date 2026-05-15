# LLM Wiki vNext Code Review and Improvement Report

작성일: 2026-04-22  
대상: `LLM Wiki vNext` 현재 코드베이스  
형식: 상세 코드 검토 및 개선 권고 보고서  
언어: 한국어

---

## 1. 검토 요약

이번 검토의 결론은 다음과 같습니다.

- 이 저장소는 단순한 스크립트 모음이 아니라 **정책(policy)·스키마(schema)·테스트·게이트·실험·자가개선 루프**를 결합한 운영형 코드베이스입니다.
- 코드 품질의 기본 체력은 높습니다. 특히 **계약 중심 설계**, **artifact 기반 추적성**, **세분화된 테스트**, **canary 성향의 보수적 적용 정책**이 강점입니다.
- 다만 현재도 구조적 부채가 뚜렷합니다. 핵심은 다음 네 축입니다.
  1. **내부 계약의 `dict` 중심성**
  2. **복잡도 상위 함수들의 집중**
  3. **워크스페이스 복사/스냅샷 비용**
  4. **자가 개선 상태 관리의 일부 미세 결함**
- 종합적으로 보면, 이 프로젝트는 **“성숙한 운영형 실험 시스템”** 에 가깝지만, 아직 **완전한 자율 최적화 시스템** 으로 보기는 어렵습니다.

### 총평

> **설계 방향은 매우 좋고, 운영 안전성에 대한 감수성도 높다.**  
> 그러나 현재 단계에서는 **구조적 정교함에 비해 내부 표현과 실행 비용이 아직 거칠다.**

---

## 2. 검토 범위와 방법

### 2.1 검토 범위

주 검토 대상:

- `ops/scripts/*.py`
- `tests/*.py`
- `tools/*.py`
- `ops/policies/*.yaml`
- `ops/schemas/*.json`
- `.github/workflows/*.yml`
- `Makefile`
- `pyproject.toml`
- 루트 설명 문서 (`README.md`, `ARCHITECTURE.md`, `AGENTS.md`)

보조 참고:

- `ops/reports/*.json`
- `ops/reports/task-improvement-observations/*`
- 기존 `external-reports/*.md`

### 2.2 실제 검토 방식

- 압축 파일 내부 구조 스캔
- Python 소스 전수 파싱 가능 여부 확인
- 코드/테스트 규모 및 구조 지표 산출
- 고복잡도 함수 및 큰 모듈 탐지
- 핵심 런타임 모듈 정밀 리뷰
- 선택된 테스트 파일 수집/실행 스모크 확인

### 2.3 이번 검토에서 확인한 스냅샷

확인된 정량 지표:

- 아카이브 엔트리 수: **1,484**
- Python 파일 수: **250**
- Python 비주석/비공백 LOC
  - `ops/`: **29,273**
  - `tests/`: **23,017**
  - `tools/`: **315**
- 테스트 파일 수: **101**
- `test_` 함수 수: **531**
- JSON Schema 수: **45**
- 전체 Python 파일 **AST 파싱 실패 0건**

선택 실행 확인:

- `pytest --collect-only`로 핵심 테스트 파일 수집 성공
- 아래 파일 묶음 실행 성공
  - `tests/test_mechanism_review_candidate_runtime.py`
  - `tests/test_planning_gate_validate_runtime.py`

주의:
- 전체 테스트 스위트 전량 실행까지는 본 검토에서 완료하지 않았습니다.
- 따라서 **“전체 green”를 단정하지는 않습니다.**
- 다만 **핵심 진입 테스트 수집과 일부 실행은 현재 정상** 으로 확인했습니다.

---

## 3. 구조적 강점

## 3.1 정책과 스키마가 실제 런타임 계약으로 작동한다

이 저장소의 가장 큰 장점은 문서상의 원칙이 아니라, **정책 파일과 스키마가 실제 실행 경로를 규정** 한다는 점입니다.

대표 근거:

- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/schemas/*.json`
- `ops/scripts/policy_runtime.py`
- `ops/scripts/schema_runtime.py`

특히 `load_policy()`, `validate_policy_contract()`, `validate_or_raise()` 계열은 “설정 파일을 읽는다” 수준이 아니라 **운영 계약을 강제하는 중앙 진입점**으로 기능합니다.

### 평가
이 구조는 장기 유지보수에 유리합니다.  
프롬프트/관습/암묵지에 기대는 시스템보다 훨씬 재현 가능성이 높습니다.

---

## 3.2 자가 개선 루프가 실제 artifact를 남긴다

이 프로젝트의 자가 개선은 선언적 구호가 아니라, 다음의 **실행 가능한 운영 루프** 로 구현돼 있습니다.

- mechanism review
- mutation proposal
- auto improve session
- outcome metrics
- improvement observations
- routing / ledger / telemetry artifact

대표 근거:

- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/auto_improve_session_runtime.py`
- `ops/scripts/auto_improve_outcome_runtime.py`
- `ops/scripts/improvement_observations_runtime.py`
- `ops/reports/task-improvement-observations/*`

즉, 이 저장소는 다음 사이클을 어느 정도 갖췄습니다.

1. 이상징후 식별
2. 후보 생성
3. 실험 실행
4. 결과 기록
5. 개선 관찰 축적
6. 다음 실험의 우선순위에 반영

### 평가
이 수준은 일반적인 “자동 테스트 있음” 수준을 넘습니다.  
**운영형 self-improvement scaffold**로 볼 수 있습니다.

---

## 3.3 적용 정책이 보수적이고 안전하다

`ops/policies/wiki-maintainer-policy.yaml`의 `auto_improve_policy`에는 다음과 같은 성향이 드러납니다.

- `allowed_apply_roots` 제한
- `apply_mode: canary_only`
- pre-promotion failure quarantine
- reviewer / auditor role dispatch
- signoff / validation / rehearsal 중심 흐름

이 말은 곧, 이 시스템이 “무작정 자가 변경”을 지향하지 않고 **제한된 표면에서만, 검증된 방식으로, 단계적으로 바꾸려는 설계**를 취한다는 뜻입니다.

### 평가
자가개선 시스템에서 가장 흔한 실패는 과도한 자율권입니다.  
이 저장소는 그 위험을 잘 이해하고 있습니다.

---

## 3.4 테스트 자산이 충분히 축적돼 있다

테스트 규모 자체가 이미 작지 않습니다.

- 테스트 파일 101개
- `test_` 함수 531개

게다가 테스트가 단순 happy-path만 다루는 것이 아니라,

- policy contract
- promotion gate
- planning gate
- executor runtime
- review candidate runtime
- filesystem transaction
- public export
- supply-chain artifact

등을 폭넓게 다룹니다.

### 평가
이 정도면 “테스트가 없는 운영 코드”가 아니라  
**테스트를 전제로 성장하는 운영 코드베이스** 라고 볼 수 있습니다.

---

## 4. 핵심 문제점

## 4.1 내부 계약이 여전히 `dict` 중심이다

이 코드베이스는 외부 계약 측면에서는 schema-driven이지만,  
내부 구현은 여전히 **raw `dict` 조립과 문자열 key 접근**이 매우 많습니다.

이번 검토에서 확인한 결과, **`dict` 계열 반환 타입을 가지는 함수가 매우 많고**,  
핵심 런타임도 내부 표현을 대부분 `dict[str, Any]` 중심으로 전달하고 있습니다.

대표 예시:

- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/auto_improve_session_runtime.py`
- `ops/scripts/filesystem_runtime.py`
- `ops/scripts/codex_exec_executor.py`
- `ops/scripts/run_mechanism_experiment_runtime.py`

### 왜 문제인가

이 구조는 다음 리스크를 키웁니다.

- 필드명 drift
- schema와 내부 구현의 미세 불일치
- refactor 비용 증가
- mypy가 제대로 도와주지 못하는 구간 확대
- 테스트가 세밀해질수록 fixture 유지비 상승

### 진단

현재 상태는 **“경계는 강하게 검증하지만, 내부는 다소 느슨한 구조”** 입니다.  
이 패턴은 초기에는 빠르지만, 규모가 커질수록 유지비가 올라갑니다.

### 권고

우선순위가 높은 payload부터 다음 순서로 정리하는 것이 좋습니다.

1. **session / run / promotion / executor report payload**를 전용 모델로 승격
2. `dict[str, Any]` 직접 조립 대신 **builder 함수 또는 dataclass/TypedDict wrapper** 사용
3. 읽기 전용 artifact는 `TypedDict`
4. 내부 변이 객체는 `@dataclass(slots=True)` 또는 작은 전용 value object 사용
5. 핵심 경로는 `dict.get()` 의존을 줄이고 필수 속성 접근을 명시화

### 기대 효과

- 리팩터링 안정성 향상
- 타입 검사 실효성 증가
- 테스트 fixture 단순화
- schema drift 탐지 속도 향상

---

## 4.2 복잡도 상위 함수가 특정 모듈에 집중되어 있다

복잡도 상위 함수는 일부 모듈에 집중되어 있습니다.

상위 복잡도 예시:

- `ops/scripts/wiki_doc_audit_runtime.py::external_report_reference_issues`
- `ops/scripts/raw_intake_promotion_runtime.py::_validate_synthesis_profile`
- `ops/scripts/registry_review_candidate_passes_runtime.py::_backlog_refactor_threshold_pass`
- `ops/scripts/wiki_lint_review_runtime.py::content_promotion_candidates`
- `ops/scripts/observability_artifacts_runtime.py::build_routing_provenance_aggregate`
- `ops/scripts/wiki_eval.py::evaluate`
- `ops/scripts/policy_validation_runtime.py::validate_policy_safety_invariants`

### 왜 문제인가

이 함수들은 대부분 다음 특징을 동시에 가집니다.

- 분기 수가 많음
- 여러 규칙을 한 함수에 압축
- 진단 메시지 생성까지 함께 담당
- 데이터 수집 + 판정 + 출력 형식 구성이 한곳에 섞임

이런 함수는 시간이 갈수록 다음 문제를 만듭니다.

- 회귀 위험 증가
- 테스트 fixture가 비대해짐
- “한 군데 수정했더니 다른 규칙이 깨짐” 현상
- 운영 규칙의 설명 가능성 저하

### 권고

다음 원칙으로 분해하십시오.

1. **수집(collection) / 판정(decision) / 보고(report formatting)** 분리
2. 규칙 하나당 predicate 함수 하나
3. 진단 문구는 별도 formatter로 분리
4. 점수 계산은 rule registry 기반으로 이동
5. “복잡한 if-elif 사슬”을 선언형 테이블 구조로 교체

### 즉시 효과가 큰 후보

- `raw_intake_promotion_runtime.py`
- `wiki_lint_review_runtime.py`
- `policy_validation_runtime.py`
- `observability_artifacts_runtime.py`

---

## 4.3 워크스페이스 준비 비용이 크고, 장기적으로 확장성이 떨어질 수 있다

`ops/scripts/mechanism_run_workspace_runtime.py`는 실행 전후에 매우 보수적으로 상태를 다룹니다.  
안전성 측면에서는 좋지만, 비용 측면에서는 부담이 큽니다.

대표 패턴:

- 전체 저장소 파일 digest 스냅샷
- 워크스페이스 전체 `copytree`
- 변경 파일 manifest 생성
- shadow apply / rollback rehearsal

특히 `_prepare_workspace_copy()`와 `_snapshot_repo_file_digests()` 흐름은  
저장소가 더 커질수록 실행당 고정 비용이 증가하는 구조입니다.

### 왜 문제인가

현재는 이 설계가 안전성을 주지만, 다음 단계에서는 병목이 됩니다.

- raw / wiki / system 자산이 커질수록 비용 증가
- 작은 수정도 큰 복사 비용 발생
- self-improve iteration 수가 늘수록 총 비용 급증
- CI/로컬 실행 체감 속도 저하

### 권고

1. 전체 복사 대신 **manifest 기반 sparse workspace** 도입
2. baseline digest를 전체 repo가 아니라 **candidate surface + declared dependencies** 로 축소
3. `allowed_apply_roots`와 `primary_targets`를 기준으로 preparation scope 최소화
4. shadow/rehearsal은 유지하되, **전체 복사와 전수 해시를 분리**
5. 캐시 가능한 해시/인벤토리 레이어를 별도 두기

### 판단

이건 설계가 나쁘다는 뜻이 아닙니다.  
**현재 방식은 안전하지만 비싸다**는 뜻입니다.

---

## 4.4 자가 개선 세션 상태 관리에 미세한 결함이 있다

`ops/scripts/auto_improve_runtime.py`를 보면, 자가 개선 루프는 꽤 잘 짜여 있습니다.  
그런데 세부적으로 보면 몇 가지 아쉬운 점이 있습니다.

### 문제 A: 예산 기본값 처리에 `or`를 사용한다

`_new_auto_improve_session()`에서 예산 기본값을 넣을 때 다음 식을 사용합니다.

- `max_proposals or default`
- `max_minutes or default`
- `max_consecutive_failures or default`

이 방식은 **0 또는 falsy 값이 구분되지 않는** 문제가 있습니다.

#### 영향
지금 당장 치명적 버그는 아닐 수 있지만,
- “0을 명시적으로 허용하고 싶은 경우”
- CLI/설정 확장에서 sentinel semantics가 필요할 경우
오동작 여지가 있습니다.

#### 권고
`x if x is not None else default` 형태로 바꾸는 것이 안전합니다.

---

### 문제 B: resume 시 failure streak 문맥이 충분히 복원되지 않는다

`_initial_auto_improve_loop_state()`는 `consecutive_failures=0`으로 시작합니다.  
재개(resume) 세션에서 이전 실패 연속성을 복원하지 않는다면,  
실제 운영 예산과 세션 해석이 달라질 수 있습니다.

#### 영향
- failure budget 해석 왜곡
- resume 후 stop behavior 불연속
- 운영 분석 리포트와 실제 정책 간 미세 불일치

#### 권고
세션 report에 연속 실패 카운터를 남기고, resume 시 복원하십시오.

---

### 문제 C: live apply 우회 경로가 존재한다

`_apply_or_discard_workspace_changes()`는 `run_id`와 `context`가 있으면 rehearsal을 포함한 live apply 경로를 타지만,  
없으면 단순 `apply_manifest_transaction()` 경로로 바로 적용합니다.

#### 해석
현재 호출 관례상 안전할 가능성이 크지만,  
함수 자체만 놓고 보면 **안전 절차를 우회할 수 있는 API 형태** 입니다.

#### 권고
- 이 분기를 private helper로 더 깊게 감추거나
- `live` 모드에는 항상 run context를 요구하거나
- rehearsal 없는 live apply를 명시적으로 금지하십시오

---

## 4.5 출력 경로 제어가 다소 느슨하다

`ops/scripts/output_runtime.py`의 `resolve_vault_path()`는 절대경로를 그대로 반환합니다.

이 설계는 도구 유연성을 주지만, 운영형 저장소 기준에서는 다음 의문이 남습니다.

- 정말 모든 writer가 repo 밖 절대경로를 허용해야 하는가?
- 산출물의 추적성과 재현성을 약화시키지 않는가?

### 권고

출력 경로 정책을 두 단계로 나누는 것이 좋습니다.

1. **운영 artifact writer**: repo 내부만 허용
2. **사용자 지정 export CLI**: 절대경로 허용

즉, 모든 writer가 동일한 자유도를 가질 필요는 없습니다.

---

## 5. 자가 개선 성숙도 평가

## 5.1 총평

이 프로젝트의 자가 개선 성숙도는 **“중상”** 입니다.  
정성적으로는 **상당히 성숙한 4단계 진입 수준**,  
5단계 척도로는 **약 3.7 / 5.0** 정도로 평가합니다.

---

## 5.2 왜 성숙하다고 보는가

다음 요소들이 이미 갖춰져 있습니다.

### 1) 후보 발굴이 있다
- mechanism review
- candidate registry
- mutation proposal

### 2) 실행 경로가 있다
- auto improve session
- executor routing
- experiment scaffolding

### 3) 기록과 회고가 있다
- session report
- outcome metrics
- routing provenance
- improvement observations

### 4) 적용 안전장치가 있다
- allowed apply roots
- canary only apply mode
- reviewer / auditor dispatch
- rollback rehearsal

즉, 이 저장소는 이미 **“바꿔본다 → 기록한다 → 다음 판단에 반영한다”** 를 코드 차원에서 구현하고 있습니다.

---

## 5.3 왜 아직 최고 수준은 아닌가

다만 다음 요소는 아직 부족합니다.

### 1) 내부 표현이 충분히 정형화되지 않았다
`dict` 중심 내부 계약이 많아,  
자가 개선의 품질이 코드 구조에 의해 자동 보정되지는 않습니다.

### 2) 비용 최적화가 부족하다
실험 루프의 실행 비용이 아직 큽니다.  
확장 시 throughput 병목이 생길 가능성이 있습니다.

### 3) 정책 학습이 아직 얕다
현재는 rule/heuristic 중심이며,  
실험 결과를 구조적으로 재학습해 **정책 자체를 정량 조정**하는 단계까지는 가지 않았습니다.

### 4) 상태 복원/장기 세션 품질이 약하다
resume semantics, failure streak continuity, budget accounting 같은 부분이 더 단단해져야 합니다.

### 5) “관찰 → 강제” 승격이 완전 자동은 아니다
improvement observation이 누적되지만,  
그것이 자동으로 hard gate 또는 default policy 강화로 이어지는 연결은 아직 부분적입니다.

---

## 5.4 성숙도 레벨 정의로 본 위치

제가 이번 리뷰에서 사용한 실무형 구분은 아래와 같습니다.

### Level 1 — 수동 개선
사람이 문제를 보고 직접 고친다.

### Level 2 — 계측 기반 개선
문제는 감지하고 리포트도 남기지만, 다음 행동은 대부분 수동이다.

### Level 3 — 반자동 개선
후보를 생성하고 일부 자동 실행/검증을 한다.

### Level 4 — 폐루프 개선
후보 선정, 실행, 검증, 기록, 재시도/격리까지 자동 루프가 상당 부분 닫혀 있다.

### Level 5 — 자기 최적화 운영
실험 결과가 정책과 실행 전략에 체계적으로 되먹임되고, 비용/위험/효율이 동적으로 최적화된다.

### 현재 위치
이 저장소는 **Level 4 초중반**으로 보는 것이 타당합니다.

---

## 6. 우선순위별 개선 권고

## 6.1 P0 — 바로 손대면 효과 큰 항목

### A. auto-improve 예산 기본값 처리 수정
- `or` 기반 fallback 제거
- `None` 명시 처리로 전환

### B. resume 상태 복원 강화
- `consecutive_failures`
- iteration-local state
- last blocking reason
- quarantine context
를 세션에 저장/복원

### C. live apply API 경로 봉쇄
- rehearsal 없는 live apply를 구조적으로 막기

---

## 6.2 P1 — 1차 구조 개선

### A. 핵심 payload 타입 정형화
우선 대상:
- auto improve session
- executor report
- promotion report
- planning validation payload
- workspace apply result

### B. 고복잡도 함수 분해
우선 대상:
- `raw_intake_promotion_runtime.py`
- `wiki_lint_review_runtime.py`
- `policy_validation_runtime.py`
- `observability_artifacts_runtime.py`

### C. sparse workspace 도입 설계 시작
- 전체 복사 최소화
- 전수 digest 범위 축소

---

## 6.3 P2 — 자가 개선 고도화

### A. observation → policy 승격 체계 만들기
예:
- N회 반복된 observation은 candidate priority 자동 상향
- M회 검증된 observation은 gate 경고 또는 default policy 강화 후보로 승격

### B. outcome 기반 정책 튜닝
예:
- failure mode별 quarantine 기간 조정
- reviewer/auditor dispatch 기준의 정량 재보정
- high-cost/low-yield proposal family 감쇠

### C. 실행 비용 텔레메트리 강화
세션별로 다음을 따로 측정하십시오.
- workspace prep time
- digest time
- repo health time
- promotion evaluation time
- rollback rehearsal cost

---

## 7. 권장 리팩터링 순서

가장 현실적인 순서는 아래와 같습니다.

### 1단계 — 안전성 미세 수정
- budget fallback 정정
- resume state 복원
- live apply API 안전성 강화

### 2단계 — 타입/표현 정리
- 핵심 report payload 모델 정형화
- dict 조립부를 builder로 이동

### 3단계 — 복잡도 분해
- rule table화
- formatter 분리
- predicate 단위 분해

### 4단계 — 비용 최적화
- sparse workspace
- selective hashing
- cacheable inventory

### 5단계 — 자가 개선 고도화
- observation 승격 파이프라인
- 정책 자동 미세보정
- 효과 대비 비용 최적화

---

## 8. 결론

이 코드베이스는 이미 충분히 진지한 운영 시스템입니다.  
무엇보다 중요한 점은, **자가 개선이 문구가 아니라 artifact와 runtime으로 존재한다**는 것입니다.

다만 현재의 성숙도는 다음 한 문장으로 요약할 수 있습니다.

> **“운영은 성숙했지만, 내부 표현과 실행 비용은 아직 더 다듬어야 한다.”**

즉,

- 아키텍처 방향: 좋음
- 운영 안전성: 좋음
- 테스트 기반: 좋음
- 자가개선 구조: 강함
- 내부 표현의 단단함: 보완 필요
- 실행 효율: 보완 필요
- 상태 복원/정책 정교화: 보완 필요

### 최종 판단

- **코드베이스 성숙도**: 높음
- **자가 개선 성숙도**: 중상, Level 4 초중반
- **즉시 보완 가치**: 매우 높음
- **장기 확장 가능성**: 큼

---

## 9. 한눈에 보는 액션 아이템

### 즉시
- `auto_improve_runtime`의 fallback 로직 수정
- resume 시 failure streak 복원
- rehearsal 없는 live apply 경로 차단

### 이번 스프린트
- 핵심 payload 타입 정형화
- 고복잡도 함수 분해 2~3개 착수
- workspace prep 비용 측정 계측 추가

### 다음 단계
- sparse workspace 설계
- observation → gate 승격 파이프라인 구축
- outcome 기반 정책 자동 보정 도입

---

## 10. 부록: 이번 검토에서 특히 좋았던 점

마지막으로, 이 코드베이스에서 특히 인상적이었던 점은 다음입니다.

- “공개 표면(public surface)”과 “비공개/운영 표면”을 분리하려는 의식이 분명함
- supply chain / provenance / schema / policy를 별도 시민권으로 다룸
- 자가 개선 결과를 메모 수준이 아니라 **보고서 artifact**로 축적함
- 테스트가 단순 기능 테스트가 아니라 **운영 계약 테스트** 성격을 많이 가짐

이 네 가지는 장기적으로 매우 큰 자산입니다.
