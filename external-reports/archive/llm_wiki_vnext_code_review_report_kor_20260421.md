# LLM Wiki vNext 코드 리뷰 및 개선 보고서

작성일: 2026-04-21  
대상 저장소: `LLM Wiki vNext`  
검토 산출물: 현재 업로드된 소스 아카이브 전체(압축 해제 후 정적 검토 + 일부 실행 검증)  
문서 언어: 한국어

---

## 1. 검토 목적

현재 코드베이스를 가능한 한 누락 없이 면밀하게 검토하여 다음을 정리한다.

1. 현재 구조와 구현의 강점
2. 품질, 유지보수성, 운영 안정성 관점의 핵심 리스크
3. 우선순위가 분명한 개선 방안
4. **자가 개선(self-improvement) 체계의 성숙도 평가**
5. 자가 개선 체계를 한 단계 높이기 위한 보완 방안

---

## 2. 검토 범위와 방법

### 2.1 검토 범위

압축 해제 후 확인한 주요 범위는 다음과 같다.

- `ops/` : 운영 스크립트, 정책, 스키마, 리포트
- `tests/` : 자동화 테스트
- `wiki/`, `system/`, `raw/` : 문서 및 원천 데이터
- 루트 설정 파일: `pyproject.toml`, `Makefile`, `README.md`, `ARCHITECTURE.md`

### 2.2 검토 방법

이번 검토는 다음 방식으로 수행했다.

- 저장소 전체 구조와 핵심 진입점 확인
- 설정 파일(`pyproject.toml`, `Makefile`, `README.md`) 검토
- `ops/scripts` 중심의 정적 코드 검토
- 파일 크기, 함수 길이, 예외 처리 패턴, 출력/로깅 패턴 등의 구조 분석
- 자가 개선 관련 런타임/리포트/정책 경로 집중 검토
- 일부 핵심 테스트 셋 실행을 통한 현재 상태 점검

### 2.3 이번 검토의 한계

아래 사항은 명확히 구분해 두는 것이 좋다.

- 전체 테스트 스위트 전량을 완전 소진했다고 보기는 어렵다.
- 대신 **자가 개선, planning gate, provenance, complexity budget**와 직접 관련된 핵심 테스트 일부를 실행했고, 해당 범위는 현재 환경에서 통과를 확인했다.
- 따라서 본 보고서는 **정적 분석 + 핵심 경로 중심 실행 검토**에 기반한 실무형 평가다.

---

## 3. 전체 결론 요약

이 저장소는 단순한 스크립트 집합이 아니라, 다음 특성을 가진 **운영 통제형 코드베이스**에 가깝다.

- 스키마 기반 산출물
- 정책 기반 gate
- 파일시스템 안전 장치
- provenance / audit artifact
- self-improvement 실행 파이프라인
- 비교적 촘촘한 테스트 체계

즉, **“실험적인 자동화 코드” 수준은 이미 넘어섰다.**  
특히 안전성, 재현성, 감사 가능성(auditability), 공급망 산출물 관리 측면은 강하다.

반면, 다음 한계도 분명하다.

- 오케스트레이션 계층의 일부 파일이 너무 크고 책임이 많다.
- 자가 개선 루프가 존재하지만, 아직은 **“진단/기록 중심”** 이고 **“우선순위 변경까지 닫힌 루프”** 로 완전히 발전한 상태는 아니다.
- 관측성과 유지보수성은 강한 산출물 구조에 비해 런타임 개발 경험 측면에서 다소 거칠다.
- 타입 엄격성, 모듈 경계, 대형 함수 분해는 다음 단계 개선 여지가 크다.

### 최종 한 줄 평가

- **전체 엔지니어링 성숙도:** 중상
- **자가 개선 체계 성숙도:** **Level 3 / 5 (관리형·통제형 단계)**  
  → 안전장치와 기록 체계는 잘 갖췄지만, 아직 **실측 결과가 자동 우선순위 결정에 반영되는 Level 4(폐루프 최적화)** 에는 도달하지 못했다.

---

## 4. 구조적 관찰 요약

### 4.1 코드베이스 규모 관찰

정적 집계 기준 주요 수치는 다음과 같다.

- `ops/scripts` Python 파일 수: **117**
- `tests` 파일 수: **92**
- 스키마 파일 수: **44**
- `wiki` 페이지 수: **194**
- `system` 페이지 수: **52**
- `ops/scripts` 비공백 LOC: **25,550**
- 함수 수: **1,096**
- 클래스 수: **114**

이 수치만 보더라도, 저장소는 작은 유틸리티 수준이 아니라 **정책/실행/검증/리포트가 결합된 중형 운영 코드베이스**로 보는 것이 맞다.

### 4.2 가장 큰 런타임 파일

비공백 LOC 기준 상위 파일은 다음과 같다.

1. `ops/scripts/filesystem_runtime.py` — 771
2. `ops/scripts/auto_improve_runtime.py` — 724
3. `ops/scripts/observability_artifacts_runtime.py` — 720
4. `ops/scripts/mechanism_run_workspace_runtime.py` — 678
5. `ops/scripts/policy_runtime.py` — 619
6. `ops/scripts/mechanism_run_validation_runtime.py` — 616
7. `ops/scripts/planning_gate_validate_runtime.py` — 505
8. `ops/scripts/codex_exec_executor.py` — 500

이 목록은 개선 우선순위를 거의 그대로 말해준다.  
즉, **핵심 위험은 알고리즘 자체보다 “오케스트레이션과 운영 표면의 비대화”** 에 있다.

### 4.3 긴 함수 관찰

특히 다음 함수들은 책임이 과도하게 몰린 신호로 보인다.

- `wiki_stage2_eval.py:evaluate` — 184 lines
- `finalize_run_runtime.py:finalize_run` — 183 lines
- `wiki_eval.py:evaluate` — 179 lines
- `registry_review_candidate_passes_runtime.py:_backlog_refactor_threshold_pass` — 178 lines
- `behavior_delta_runtime.py:build_behavior_delta_report` — 166 lines
- `policy_runtime.py:validate_policy_registry_references` — 145 lines
- `auto_improve_runtime.py:_route_scaffold_phase` — 145 lines
- `planning_gate_validate_runtime.py:validate_run_dir` — 124 lines
- `observability_artifacts_runtime.py:build_routing_provenance_aggregate` — 101 lines

이 수준의 함수 길이는 대부분 **“규칙 집약 + 조건 분기 + 산출물 조합 + 검증”** 이 한곳에 겹쳐 있을 가능성이 높다.  
현재도 동작은 가능하지만, 변경 비용과 회귀 위험을 키운다.

---

## 5. 현재 코드의 강점

## 5.1 안전한 파일시스템 처리

`filesystem_runtime.py`는 이번 검토에서 인상적인 강점 중 하나였다.

좋았던 점:

- 원자적 쓰기(atomic write) 성격의 보호
- 중복 대상 충돌 방지
- 경로 정규화
- 루트 밖 경로 탈출 방지
- symlink 세그먼트 감시
- shadow apply / rollback rehearsal 지원

즉, “파일을 만지는 자동화”에서 자주 문제되는 위험을 상당 부분 선제 차단한다.  
자가 개선 루프가 실제 파일 변경을 동반한다는 점을 감안하면, 이 계층은 매우 중요하며 잘 설계된 편이다.

## 5.2 스키마 기반 산출물 문화

저장소 전반에 다음 특성이 강하게 보인다.

- report를 JSON schema로 고정
- 실행 결과를 artifact로 남김
- gate 입력/출력을 정형화
- session / run 단위 산출물 연결

이는 장기적으로 큰 장점이다.  
왜냐하면 self-improvement 같은 체계는 “코드만 좋다”로는 부족하고, **나중에 무엇을 근거로 어떤 결정을 내렸는지 재구성 가능해야** 하기 때문이다.

## 5.3 정책과 실행의 결합 방식이 명확함

`README.md`와 관련 runtime을 보면 다음이 분명하다.

- planning gate
- promotion gate
- behavior delta
- scope freeze
- routing provenance aggregate
- outcome metrics
- mechanism review / mutation proposal

즉, 무분별한 자동 변경이 아니라 **정책적으로 제어되는 개선 루프** 를 지향하고 있다.  
이는 자가 개선 시스템에서 매우 중요한 방향성이다.

## 5.4 의존성이 적고 보수적임

`pyproject.toml` 기준 런타임 의존성은 매우 적다.

- `PyYAML`
- `jsonschema`

이 선택은 장점이 크다.

- 공격 표면 감소
- 설치/복제 단순화
- 장기 유지보수 부담 완화
- 핵심 기능을 내부 통제로 유지 가능

## 5.5 테스트 표면이 넓음

테스트 파일 수와 Makefile 구성을 보면, 이 저장소는 “테스트가 없는 자동화 코드”가 아니다.  
특히 quality gate가 Make 타깃으로 정리되어 있어 운영 습관 측면이 좋다.

---

## 6. 핵심 문제점 및 개선 필요 사항

## 6.1 오케스트레이션 파일 비대화

### 문제

다음 파일들은 지금도 기능적으로는 가치가 높지만, 책임 집중이 지나치다.

- `auto_improve_runtime.py`
- `observability_artifacts_runtime.py`
- `planning_gate_validate_runtime.py`
- `policy_runtime.py`
- `codex_exec_executor.py`
- `mechanism_run_validation_runtime.py`

이 패턴이 지속되면 생기는 문제는 다음과 같다.

- 변경 영향 범위 예측이 어려워짐
- 테스트가 있어도 “조합 폭발”이 발생
- 코드 리뷰 난도가 올라감
- 버그가 기능 로직이 아닌 glue code에서 발생
- 특정 작성자 맥락이 없으면 유지보수 비용이 급격히 증가

### 판단

현재는 “이미 망가졌다” 수준은 아니다.  
그러나 **다음 개선 사이클에서 반드시 다뤄야 할 기술 부채** 다.

### 권고

- phase 단위 helper 분리
- 산출물 생성 로직과 판단 로직 분리
- pure function / IO boundary 분리
- `*_runtime.py` 하나가 여러 역할을 맡지 않도록 재조정

---

## 6.2 자가 개선 루프가 아직 ‘보고 중심’이다

### 관찰 근거

`README.md`에는 다음이 명시돼 있다.

- `outcome-metrics.json`은 audit-only report
- 이 값은 아직 mechanism review priority, promotion gate, release gate 판정을 바꾸지 않음
- `mechanism-review-candidates.json`에는 runs considered가 적고 candidate emitted가 0
- `mutation-proposals.json`도 proposals emitted가 0
- `outcome-metrics.json`의 attempts considered가 매우 작음

### 해석

즉, 현재 체계는 다음 단계까지는 왔다.

1. 실행한다
2. 기록한다
3. 비교한다
4. 진단한다

하지만 아직 충분히 닫히지 않았다.

5. **그 결과를 기반으로 다음 개선 우선순위를 자동 조정한다**
6. **조정 결과가 실제 실험 성공률 향상으로 이어졌는지 다시 검증한다**

이 5~6단계가 약하다.

### 판단

현재 self-improvement는 **존재한다.**  
그러나 실효성 측면에서는 아직 **“관리형 관측 단계”** 이며, **“폐루프 최적화 단계”** 는 아니다.

### 권고

- outcome metrics를 즉시 gate에 넣기보다, 먼저 **shadow priority mode** 로 연결
- 일정 기간 동안 “현재 priority vs metrics-aware priority”를 병행 기록
- calibration 안정화 후 일부 낮은 위험군에 한해 실제 우선순위 반영
- gate 영향은 마지막 단계에서만 점진 적용

---

## 6.3 런타임 관측성이 산출물에는 강하지만 개발자 경험에는 약함

### 관찰

- `ops/scripts`에서 `logging` 사용이 사실상 거의 보이지 않았고,
- `print()` 사용 파일이 다수 존재했다.
- JSON artifact는 풍부하지만, 런타임 진단 로그 체계는 상대적으로 약하다.

### 해석

현재 철학은 “최종 artifact를 진실의 원천으로 삼는다”에 가깝다.  
그 방향 자체는 맞다. 다만 실제 장애 분석, 반복 실험 디버깅, 운영자 피드백 속도 관점에서는 다음 문제가 생길 수 있다.

- 중간 단계 실패 맥락을 즉시 읽기 어렵다
- 터미널/CI 로그에서 사건 흐름 파악이 불편하다
- artifact가 풍부해도 인간이 빠르게 원인 추적하기 어렵다

### 권고

- structured logging을 도입하되 artifact 중심 철학은 유지
- 권장 필드 예시:
  - `run_id`
  - `session_id`
  - `phase`
  - `component`
  - `decision`
  - `artifact_path`
  - `duration_ms`
  - `policy_version`
- 즉, **artifact = 최종 감사 기록**, **logging = 실행 중 추적 신호** 로 역할을 분리하는 것이 좋다.

---

## 6.4 타입 엄격성이 부분적으로만 적용됨

### 관찰

`pyproject.toml`의 mypy 설정은 엄격한 편으로 보기 어렵다.

- `follow_imports = "skip"`
- `ignore_missing_imports = true`

물론 별도의 strict preview 타깃이 존재하므로 방향은 잡혀 있다.  
하지만 현재 상태는 “타입을 쓰고는 있으나, 핵심 변경을 전부 강하게 막는 수준”까지는 아니다.

### 문제

- orchestration 계층에서는 잘못된 dict shape, optional 누락, 산출물 payload drift가 비용이 크다
- 런타임 실패가 테스트에서만 잡히는 구조로 남을 수 있다

### 권고

- 전체 strict 전환을 한 번에 시도하지 말 것
- 대신 다음 순서로 좁혀갈 것:
  1. report payload builder
  2. policy parsing layer
  3. executor report / planning gate input-output
  4. self-improve session summary model
- TypedDict / dataclass / Protocol 기반으로 경계 타입을 강화
- “엄격 타입 적용 대상 allowlist”를 점진적으로 확대

---

## 6.5 광범위 예외 처리와 대형 함수 결합

### 관찰

`except Exception:` 패턴이 일부 핵심 파일에 존재한다.

- `filesystem_runtime.py`
- `mechanism_review.py`
- `mutation_proposal.py`
- `observability_artifacts_runtime.py`
- `planning_gate_validate_runtime.py`
- `promotion_gate.py`
- `raw_markdown_runtime.py`

### 해석

CLI 경계에서 broad catch를 두는 것은 합리적일 수 있다.  
하지만 도메인 로직 중간에서 broad catch가 많아지면 다음이 발생한다.

- 실제 결함 유형이 숨겨짐
- 회복 가능한 예외와 치명적 예외가 섞임
- report는 남지만 원인 분리가 흐려짐

### 권고

- CLI entrypoint에서만 broad catch 허용
- 내부 로직은 도메인 예외 계층을 정의
  - `PolicyValidationError`
  - `ArtifactAssemblyError`
  - `WorkspaceIntegrityError`
  - `ExecutorContractError`
- 예외마다 operator-facing message / audit payload 분리

---

## 6.6 대형 리포트/정책 조합 로직의 회귀 위험

### 문제

`observability_artifacts_runtime.py`, `behavior_delta_runtime.py`, `planning_gate_validate_runtime.py`처럼  
다수의 소스 입력을 모아 리포트를 합성하는 계층은 변경이 자주 생기면 회귀가 쉽게 발생한다.

### 권고

다음 테스트를 더 강화하는 것이 좋다.

- golden-file 테스트
- schema round-trip 테스트
- cross-artifact consistency 테스트
- property-based 테스트(경계값, 누락 필드, empty input)
- fault injection 테스트(파일 누락, invalid JSON, partial run, stale artifact)

---

## 6.7 문서화와 실제 코드 구조 사이의 긴장

`README.md`는 매우 충실하고 운영 개념도 명확하다.  
하지만 코드 구조는 일부 구간에서 문서의 개념 모델보다 더 복잡하게 얽혀 있다.

즉, **설계 설명은 깔끔한데 실제 구현은 glue code가 다소 두껍다.**

이 경우 장기적으로 생기는 문제:

- 문서를 믿고 들어온 기여자가 코드에서 길을 잃음
- 개념 경계와 파일 경계가 다르게 느껴짐
- review 시간 증가

### 권고

문서 개념 단위와 코드 모듈 단위를 좀 더 정렬할 필요가 있다.

예시:

- `auto_improve/selection.py`
- `auto_improve/routing.py`
- `auto_improve/execution.py`
- `auto_improve/persistence.py`
- `artifacts/provenance.py`
- `artifacts/outcome_metrics.py`
- `gates/planning.py`
- `gates/promotion.py`

---

## 7. 자가 개선(Self-Improvement) 성숙도 평가

## 7.1 평가 기준

이번 평가는 아래 다섯 축으로 보았다.

1. **안전성** — 잘못된 개선을 막는 장치가 있는가
2. **관측성** — 무엇이 일어났는지 재구성 가능한가
3. **폐루프성** — 결과가 다음 개선 결정으로 이어지는가
4. **통제성** — 정책, 스코프, 승인 경계가 분명한가
5. **축적성** — 히스토리가 쌓일수록 더 똑똑해지는 구조인가

## 7.2 축별 평가

### A. 안전성 — 높음

강점:

- allowed roots / allowed executors
- scope freeze
- behavior delta
- planning gate / promotion gate
- filesystem safety
- shadow apply / rollback rehearsal

평가: **강함**

### B. 관측성 — 중상

강점:

- session report
- executor report
- routing provenance aggregate
- promotion decision trends
- outcome metrics
- artifact fingerprint

한계:

- runtime logging 체계는 상대적으로 약함
- 운영자 입장에서 “실행 중간 흐름”보다 “실행 후 artifact” 해석 의존이 큼

평가: **중상**

### C. 폐루프성 — 중간

강점:

- mechanism review
- mutation proposal
- outcome metrics calibration preview
- historical run 기반 진단

한계:

- priority, gate, release decision에 아직 직접 영향이 약함
- audit-only 모드가 많음
- metrics-aware adaptation이 실효적 피드백까지 닫히지 않음

평가: **중간**

### D. 통제성 — 높음

강점:

- policy versioning
- schema-backed artifacts
- deterministic report surface
- executor 제한
- write allowlist 동결

평가: **강함**

### E. 축적성 — 중하 ~ 중간

강점:

- 히스토리를 쌓기 위한 구조는 존재
- comparable run history를 읽는 구조도 있음

한계:

- 실제 누적 표본이 아직 너무 작음
- emitted candidate / proposal이 거의 없어, 학습 루프의 실효성이 증명되지 않음

평가: **아직 충분히 입증되지 않음**

## 7.3 종합 성숙도 판정

### 판정: **Level 3 / 5 — 관리형(Managed) 자기개선**

의미:

- 자가 개선을 실행할 수 있다
- 실행 결과를 신뢰 가능한 산출물로 남긴다
- 정책과 안전장치가 있다
- 진단과 감사가 가능하다

하지만 아직 다음 단계는 아니다.

### 아직 도달하지 못한 Level 4의 조건

- outcome metrics가 실제 다음 실험 우선순위를 바꾼다
- 바뀐 우선순위가 성과 개선으로 이어졌는지 다시 검증한다
- calibration drift와 false positive를 제어한다
- 충분한 히스토리로 인해 추천 신뢰도가 누적 향상된다

즉, 현재 수준은 **“자가 개선을 안전하게 운영하는 체계”** 이지,  
아직 **“자가 개선이 스스로의 효율을 안정적으로 높이는 체계”** 로 완전히 넘어가진 않았다.

---

## 8. 우선순위별 개선 권고안

## 8.1 즉시 착수 권고 (1~2주)

### 1) `auto_improve_runtime.py` 분해 시작
가장 먼저 분해해야 할 표면이다.

권장 분리 축:

- candidate selection
- route/scaffold
- execute/evaluate
- persistence/session report
- error mapping

### 2) structured logging 도입
artifact 중심 철학은 유지하되, 실행 중 가시성을 보완해야 한다.

최소 범위:

- auto improve session
- planning gate
- executor
- provenance aggregate builder

### 3) 대형 함수에 대한 golden test 추가
우선 대상:

- `_route_scaffold_phase`
- `validate_run_dir`
- `build_behavior_delta_report`
- `build_routing_provenance_aggregate`

### 4) broad exception 축소
CLI boundary를 제외하고는 도메인 예외로 교체를 시작한다.

---

## 8.2 단기 개선 (1~2개월)

### 5) 타입 엄격성 확대
`mypy-strict-preview`를 실제 품질 향상 수단으로 연결해야 한다.

권장 순서:

- artifact payload model
- policy model
- executor contract
- self-improve session summary

### 6) 리포트 합성 계층 분리
현재는 “산출물 생성 + 정책 해석 + 진단 메시지 조립”이 함께 있는 구간이 보인다.

권장 구조:

- `collect_*`
- `validate_*`
- `summarize_*`
- `render_*`

### 7) cross-artifact consistency 검증 도입
예:

- scope freeze와 apply allowlist 일치 여부
- executor report와 routing aggregate 연결 일치 여부
- behavior delta와 changed-files manifest 일치 여부
- outcome metrics 입력 run set과 promotion trend run set의 일관성

---

## 8.3 중기 개선 (분기 단위)

### 8) outcome metrics를 shadow priority에 연결
바로 gate로 넣지 말고 다음 단계를 밟는 것이 적절하다.

1. audit-only
2. shadow priority
3. low-risk cohort partial activation
4. calibrated gate influence

### 9) self-improvement efficacy dashboard 또는 요약 리포트 추가
현재 artifact는 풍부하지만 사람이 빠르게 읽기엔 분산돼 있다.

필요한 질문 예시:

- 최근 20회에서 어떤 유형의 변경이 가장 자주 HOLD 되었는가
- 어떤 primary target에서 rework가 반복되는가
- 어떤 routing 조합이 discard/HOLD와 상관이 큰가
- behavior delta risk flag가 실제 promotion 결과와 어떤 상관이 있는가

### 10) 운영 개념과 코드 패키지 경계 정렬
문서 개념과 파일 경계를 더 일치시키면 유지보수성이 크게 개선된다.

---

## 9. 개선 우선순위 표

| 우선순위 | 항목 | 기대 효과 | 난이도 | 권고 |
|---|---|---:|---:|---|
| P0 | `auto_improve_runtime.py` 분해 | 변경 안정성, 리뷰 속도, 회귀 감소 | 중 | 즉시 |
| P0 | structured logging 도입 | 장애 분석, 실험 디버깅 개선 | 중 | 즉시 |
| P0 | 대형 함수 golden/fault tests | 리포트/게이트 회귀 방지 | 중 | 즉시 |
| P1 | 타입 엄격성 확대 | payload drift 조기 차단 | 중 | 단기 |
| P1 | broad exception 정제 | 원인 분석 품질 향상 | 중 | 단기 |
| P1 | 리포트 합성 계층 분리 | 유지보수성 향상 | 중상 | 단기 |
| P2 | outcome metrics → shadow priority | self-improvement 실효성 향상 | 중상 | 중기 |
| P2 | cross-artifact consistency suite | 감사 신뢰도 향상 | 중상 | 중기 |
| P2 | 운영 대시보드/요약 리포트 | 운영자 판단 속도 개선 | 중 | 중기 |

---

## 10. 실무적으로 가장 중요한 개선 시나리오

이번 검토에서 가장 중요한 판단은 다음이다.

### 지금 당장 필요한 것은 “더 많은 기능”이 아니다.

필요한 것은 아래 세 가지다.

1. **오케스트레이션 분해**
2. **관측성 보강**
3. **자가 개선 결과의 제한적 폐루프 연결**

즉, 지금 단계의 핵심은 “새로운 automation 추가”보다  
**이미 존재하는 자동화가 더 읽기 쉽고, 더 추적 가능하고, 더 근거 있게 스스로 우선순위를 조정하도록 만드는 것** 이다.

---

## 11. 구체적 리팩터링 제안

## 11.1 `auto_improve_runtime.py`

현재 상태:
- phase-oriented 설계는 좋음
- 그러나 `_route_scaffold_phase`와 session orchestration이 두꺼움

제안:
- `AutoImproveSessionContext`
- `SelectionResult`
- `RoutingPlan`
- `ExecutionOutcome`
- `PersistenceOutcome`

처럼 중간 상태 객체를 명시화하고,
phase 함수는 “입력/출력 계약”이 더 분명해지도록 재구성한다.

## 11.2 `observability_artifacts_runtime.py`

현재 상태:
- 산출물 가치는 높음
- 하지만 파일이 커서 변경 리스크가 높음

제안:
- fingerprint 계산
- telemetry 집계
- routing provenance aggregate
- report rendering/serialization

을 분리한다.

## 11.3 `planning_gate_validate_runtime.py`

현재 상태:
- 검증 규칙이 한 함수에 밀집
- 신규 정책 규칙 추가 시 회귀 우려가 큼

제안:
- rule function registry 방식으로 전환
- 각 규칙은 독립 테스트 가능하게 분해
- 최종 report assembler는 별도 계층으로 분리

## 11.4 `codex_exec_executor.py`

현재 상태:
- 보안/위생 조치가 좋음
- prompt materialization, command shaping, result synthesis가 한 파일에 응집

제안:
- prompt template build
- redaction/sanitization
- execution wrapper
- report normalize

로 분리한다.

---

## 12. 테스트 관점 권고

## 12.1 현재 테스트 전략의 장점

- 테스트 수가 충분히 많다
- Make 기반 진입점이 정리돼 있다
- 품질 게이트 문화가 형성돼 있다

## 12.2 추가 보강이 필요한 테스트

다음은 특히 효과가 크다.

### Golden file 테스트
리포트 JSON이 구조적으로 안정적인지 확인

### Fault injection 테스트
- 깨진 JSON
- 누락 artifact
- stale report
- 잘못된 path
- partial run directory

### Property-based 테스트
- path normalization
- schema-normalized message
- aggregate builder invariants

### Mutation-style 테스트
gate 규칙이 실제로 실패를 잡는지 확인

---

## 13. 공급망/감사 체계에 대한 평가

이 저장소는 supply chain artifact에 신경을 많이 쓴 편이다.

관찰 포인트:

- provenance report 존재
- SBOM / OpenVEX / in-toto 관련 타깃 존재
- pyproject/requirements/lock 정보를 조합한 산출물 생성

이 방향은 매우 바람직하다.  
다만 여기서도 중요한 것은 “생성 여부”보다 **운영에서 실제 의사결정에 쓰이고 있는가** 다.

권고:

- release 또는 public export 시 provenance 검증을 더 직접 연결
- 공급망 산출물 생성 실패가 어디까지 blocking인지 정책적으로 명확화
- artifact 사이 상호 참조 무결성 테스트 추가

---

## 14. 자가 개선 보완 방안 요약

자가 개선 체계를 한 단계 끌어올리려면 아래 순서가 적절하다.

### 1단계 — 구조 정리
- 오케스트레이션 분해
- 관측성 보강
- 타입/예외/테스트 경계 강화

### 2단계 — 진단의 신뢰도 확보
- outcome metrics 품질 개선
- cross-run sample 축적
- false positive / false confidence 방지

### 3단계 — shadow adaptation
- metrics-aware priority를 병행 계산
- 기존 priority와 비교 기록
- 사람 검토와의 일치율 측정

### 4단계 — 제한적 폐루프
- 저위험 영역에서만 자동 우선순위 반영
- 성과가 실제 개선되는지 검증
- drift 감시 및 rollback 가능성 유지

이 순서를 지키면, 현재의 강한 안전장치를 해치지 않으면서도  
자가 개선을 “보고 체계”에서 “성과를 내는 체계”로 진화시킬 수 있다.

---

## 15. 최종 평가

### 잘하고 있는 점

- 운영 자동화 코드로서 안전장치가 강하다
- schema-backed artifact 문화가 좋다
- 정책/게이트/실행/리포트의 연결이 명확하다
- self-improvement 방향성이 분명하다
- 공급망/감사 산출물에 대한 감각이 좋다

### 지금 가장 아쉬운 점

- 큰 파일과 긴 함수가 많아 오케스트레이션 복잡도가 높다
- self-improvement가 아직 실질적 폐루프 최적화까지 닫히지 않았다
- 관측성은 강한데 런타임 개발자 경험은 상대적으로 약하다
- 타입/예외/모듈 경계가 다음 단계만큼 단단하진 않다

### 최종 판정

이 코드는 **실험적 자동화 수준을 넘어선, 관리 가능한 운영형 코드베이스** 다.  
다만 자가 개선 관점에서는 아직 **“안전하게 수행하고 잘 기록하는 단계”** 이며,  
앞으로의 핵심 과제는 **“그 기록을 실제 우선순위 조정과 성과 향상으로 연결하는 것”** 이다.

따라서 현재 자가 개선 성숙도는 다음으로 판단한다.

> **자가 개선 성숙도: Level 3 / 5 (관리형·통제형 단계)**

적절한 다음 목표는 Level 4이며, 그 핵심은 다음 한 줄로 요약된다.

> **측정된 결과가 실제 다음 개선 결정을 바꾸고, 그 결정이 다시 성과로 검증되는 폐루프를 만드는 것**

---

## 16. 부록 A — 검토 중 확인한 주요 사실

### 설정/환경
- Python 요구 버전: `>=3.12`
- 런타임 핵심 의존성: `PyYAML`, `jsonschema`
- mypy 설정은 일부 완화되어 있으며 strict preview 타깃이 별도로 존재

### 품질 게이트
`Makefile` 상위 타깃 기준으로 다음 흐름이 정리돼 있다.

- static
- registry-preflight
- lint
- eval
- stage2-eval
- planning-gate
- unit-tests

### 핵심 self-improvement 관련 산출물
`README.md`에 명시된 주요 산출물 예시는 다음과 같다.

- `ops/reports/auto-improve-sessions/<session-id>.json`
- `ops/reports/routing-provenance-aggregates/<session-id>.json`
- `ops/reports/promotion-decision-trends.json`
- `ops/reports/outcome-metrics.json`
- `runs/<run-id>/scope-freeze.json`
- `runs/<run-id>/subagent-routing.<role>.json`
- `runs/<run-id>/<role>-executor-report.json`
- `runs/<run-id>/behavior-delta.json`
- `runs/<run-id>/run-telemetry.json`
- `runs/<run-id>/run-artifact-fingerprint.json`

### 자가 개선 성숙도 판단에 직접 영향을 준 관찰
- `outcome-metrics.json`은 아직 audit-only
- mechanism review candidate report에서 후보가 발생하지 않음
- mutation proposal report에서도 proposal이 발생하지 않음
- comparable history 자체는 아직 매우 작음

---

## 17. 부록 B — 이번 검토에서 실행 확인한 범위

다음 핵심 테스트 묶음은 현재 환경에서 통과를 확인했다.

- `tests/test_auto_improve_runtime.py`
- `tests/test_auto_improve_session_runtime.py`
- `tests/test_mechanism_review.py`
- `tests/test_planning_gate_validate_runtime.py`
- `tests/test_supply_chain_provenance.py`
- `tests/test_makefile_static_gates.py`
- `tests/test_structural_complexity_budget_runtime.py`

단, 전체 저장소 테스트 전량을 완전 소진했다고 단정하지는 않는다.  
이번 보고서는 **핵심 경로 중심 검증** 결과를 반영한 것이다.

---

## 18. 부록 C — 바로 실행 가능한 액션 아이템

### 이번 주
- `auto_improve_runtime.py` 분해 설계서 작성
- structured logging 최소 도입
- 4개 대형 함수에 golden/fault test 추가

### 이번 달
- artifact payload 타입 강화
- planning gate rule registry 분리
- cross-artifact consistency test 추가

### 다음 분기
- metrics-aware shadow priority 도입
- self-improvement efficacy dashboard 추가
- low-risk cohort에서 폐루프 우선순위 적용 실험

---

이상.
