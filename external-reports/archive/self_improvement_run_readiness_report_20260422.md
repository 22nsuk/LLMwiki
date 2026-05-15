# LLM Wiki vNext 현재 코드 검토 및 자가 개선 실행 직전 개선 방안 보고서

작성 기준 시점: 자가 개선(auto-improve) 런을 **지금 막 실행하기 직전**의 운영 관점  
작성 대상: 업로드된 `LLM Wiki vNext(20).zip` 기준 저장소 전체 인벤토리와 핵심 실행 경로  
작성 언어: 한국어

---

## 1. 보고서 목적

본 보고서는 현재 저장소를 **자가 개선 런을 실제로 시작하기 직전**의 시점에서 검토한 결과를 정리한 것이다. 
단순 코드 스타일 리뷰가 아니라, 다음 질문에 답하도록 구성했다.

1. 이 저장소는 현재 **스스로를 개선하는 실험/운영 루프**를 어느 정도까지 갖추고 있는가?
2. 지금 상태에서 자가 개선 런을 돌리면 **안전하고 의미 있는 결과**를 낼 가능성이 높은가?
3. 실제 실행 직전에 반드시 보완하거나 재확인해야 할 것은 무엇인가?
4. 이 시스템의 자가 개선 성숙도는 어느 수준이며, **완전한 폐루프 self-improvement**까지 무엇이 남았는가?

---

## 2. 검토 범위와 방법

### 2.1 검토 범위

이번 검토는 저장소 전체를 대상으로 하되, 특히 아래 영역에 집중했다.

- 자가 개선 루프 진입점과 오케스트레이션
  - `ops/scripts/auto_improve_runtime.py`
  - `ops/scripts/auto_improve_iteration_runtime.py`
  - `ops/scripts/auto_improve_execute_runtime.py`
  - `ops/scripts/auto_improve_outcome_runtime.py`
  - `ops/scripts/auto_improve_iteration_persistence_runtime.py`
  - `ops/scripts/auto_improve_route_scaffold_runtime.py`
  - `ops/scripts/run_mechanism_experiment_runtime.py`
  - `ops/scripts/mechanism_run_workspace_runtime.py`
  - `ops/scripts/behavior_delta_runtime.py`
  - `ops/scripts/codex_exec_executor.py`
- 운영 정책과 게이트
  - `ops/policies/wiki-maintainer-policy.yaml`
  - `ops/schemas/*`
- 생성 리포트와 현재 큐 상태
  - `ops/reports/mechanism-review-candidates.json`
  - `ops/reports/mutation-proposals.json`
  - `ops/reports/outcome-metrics.json`
  - `ops/reports/task-improvement-observations/*`
- 테스트/CI 및 실행성
  - `Makefile`
  - `.github/workflows/*`
  - `tests/*`
  - `README.md`, `ops/README.md`

### 2.2 검토 방식

- 저장소 전체 파일 인벤토리 확인
- 핵심 자가 개선/실험/적용 경로 정적 리뷰
- 정책 YAML과 스키마, 리포트 산출물 상호 대조
- 실행 직전 기준의 운영 readiness 점검
- 테스트 실행성 확인
  - `pytest -q` 직접 호출
  - `python -m pytest` 기반 핵심 테스트 일부 실행

### 2.3 이번 검토에서 확인한 저장소 규모

- 총 파일 수: **1,588개**
- Python 파일 수: **250개**
- 비주석 기준 대략 코드 라인 수: **53,875 line**
- 테스트 파일 수: **101개**
- 정규식 기준 테스트 케이스 수: **543개**

이 수치는 저장소가 실험성 스크립트 몇 개 수준이 아니라, 이미 상당한 수준의 운영/검증 체계를 가진 **메커니즘 저장소**라는 점을 보여준다.

---

## 3. 한 줄 결론

**현재 저장소는 “통제된 자가 개선 실험 플랫폼”으로서는 성숙도가 높다.**  
다만 **“스스로 안전하게 바꾸고, 스스로 확정하는 완전 폐루프 자가 개선 시스템”**이라고 부르기에는 아직 한 단계가 남아 있다.

보다 정확히 말하면:

- **강점**: 범위 통제, 증적 관리, 스키마 기반 산출물, 정책 게이트, 롤백 리허설, 공급망/출처 검증 표면이 매우 잘 설계되어 있다.
- **약점**: 현재 큐가 stale 상태일 가능성이 높고, 기본 적용 모드가 `canary_only`이며, 텔레메트리 보존이 allowlist 기반이고, 일부 대형 오케스트레이션 모듈과 strict allowlist 부채가 남아 있다.
- **실행 직전 판단**: **“돌릴 수는 있으나, refresh-generated와 preflight를 먼저 수행하지 않으면 의미 없는 런 또는 outdated 입력 기반 런이 될 위험이 있다.”**

---

## 4. 자가 개선 성숙도 평가

### 4.1 종합 등급

**종합 성숙도: 4.0 / 5.0**

해석:

- **3.0 수준**: 자가 개선 실험이 가능하다.
- **4.0 수준**: 자가 개선 실험이 운영 규율, 게이트, 산출물, 회귀 방지 체계 안에서 반복 가능하다.
- **5.0 수준**: 큐 최신성, 적용 안전성, 증적 보존, 자동 확정, 회귀 검증, 장기 보정 루프까지 완전히 닫힌 상태다.

현재 상태는 **4.0 수준**, 즉 **관리되고 통제된 self-improvement 운영 단계**에 가깝다.  
반면 **완전 자율 self-application 단계(5.0)** 로 보려면 아직 몇 가지 결정적 보완이 필요하다.

### 4.2 세부 항목별 점수

| 항목 | 평가 | 점수 |
|---|---:|---:|
| 개선 범위 통제 | 매우 우수 | 4.8/5 |
| 증적/관측 가능성 | 매우 우수 | 4.8/5 |
| 정책/게이트 구조 | 우수 | 4.5/5 |
| 실행 안전성(rollback/apply) | 우수 | 4.4/5 |
| 테스트/회귀 방지 | 우수 | 4.2/5 |
| 큐 최신성/운영 신뢰성 | 보통 이상 | 3.4/5 |
| 장기적 유지보수성 | 보통 이상 | 3.7/5 |
| 완전 폐루프 자율성 | 아직 제한적 | 3.2/5 |

### 4.3 성숙도 판단 근거

#### 높은 점수를 준 이유

1. **허용된 변경 범위가 명시적으로 제한**되어 있다.  
   `auto_improve_policy.allowed_apply_roots`는 다음으로 제한된다.
   - `ops/`
   - `tests/`
   - `system/system-log.md`

2. **기본 적용 모드가 공격적이지 않다.**  
   `auto_improve_policy.apply_mode: canary_only`로 설정되어 있어, 기본 상태에서 무분별한 self-apply를 하지 않는다.

3. **스키마 중심 산출물 구조가 강하다.**  
   `ops/schemas/`에 많은 리포트/런 산출물 스키마가 있고, 실행 결과가 제각각의 ad hoc 로그로 끝나지 않는다.

4. **실행 전후 증적 체계가 풍부하다.**  
   `scope-freeze`, `routing report`, `executor report`, `behavior-delta`, `run-telemetry`, `artifact fingerprint`, `promotion report` 등으로 판단 근거가 남는다.

5. **workspace apply 전에 shadow apply와 rollback rehearsal을 두는 구조**가 존재한다.  
   이는 단순 “패치 적용”이 아니라, 적용 경로 자체를 실험 가능한 대상으로 관리하고 있음을 뜻한다.

#### 만점이 아닌 이유

1. **현재 proposal queue가 stale/empty일 수 있다.**  
   최신 태스크 개선 관찰 리포트는 2026-04-22까지 있는데, 
   `mechanism-review-candidates.json`과 `mutation-proposals.json`의 생성 시각은 2026-04-14로 뒤처져 있다.

2. **기본 상태는 self-apply가 아니라 canary 중심**이다.  
   이는 안전 측면에서는 장점이지만, “완전히 닫힌 자가 개선 시스템”이라는 의미에서는 아직 보수적이다.

3. **텔레메트리 보존이 schema-derived가 아니라 allowlist 기반**이다.  
   미래 필드가 추가될 때 조용히 누락될 수 있다.

4. **대형 런타임 모듈이 아직 남아 있다.**  
   구조는 분해 중이지만, 핵심 오케스트레이션 일부는 계속 큰 상태다.

5. **실행 이력 깊이가 얕다.**  
   활성 promotion history가 충분히 풍부하지 않아 calibration 신뢰도가 아직 제한적이다.

---

## 5. 핵심 강점

## 5.1 자가 개선 루프가 실제로 “단계 분해”되어 있다

이 저장소의 장점은 auto-improve가 단일 거대 스크립트가 아니라, 다음과 같이 단계적으로 분해되어 있다는 점이다.

- proposal queue 구성 및 선택
- scope freeze / route scaffold
- execution / mutation / review / validation
- outcome 평가
- iteration persistence
- session completion

이 구조는 다음 측면에서 유리하다.

- 실패 원인 분리가 쉽다.
- 실험 단계별 artifact를 남기기 쉽다.
- 일부 단계만 교체하거나 강화하기 좋다.
- 후속적으로 calibration/telemetry를 붙이기 쉽다.

즉, 현재 구조는 “작동하면 다행” 수준이 아니라, **자가 개선 루프를 운영 시스템으로 다루기 위한 최소한의 구조적 분해**를 이미 달성하고 있다.

## 5.2 개선 범위가 정책적으로 강하게 제한되어 있다

`wiki-maintainer-policy.yaml`의 `auto_improve_policy`는 위험한 self-modification이 퍼지지 않게 설계되어 있다.

핵심은 다음과 같다.

- 허용 executor 제한: `codex_exec`
- 허용 apply roots 제한: `ops/`, `tests/`, `system/system-log.md`
- 기본 apply mode: `canary_only`
- missing test는 fail-closed
- reviewer target prefix와 risk flag override 별도 관리
- schema/policy/log surface에 auditor role이 붙는다

즉, 시스템이 “무엇이든 고치는 자가 개선기”가 아니라, **허용된 메커니즘 표면만 다루는 bounded self-improvement system**으로 설계되어 있다.

## 5.3 실행 증적과 검증 흔적이 매우 잘 남는다

자가 개선 시스템이 위험해지는 가장 큰 이유는 “왜 그 변경이 나왔는지”와 “무엇을 근거로 통과시켰는지”가 남지 않는 데 있다.

이 저장소는 그 반대다.

- `runs/<run-id>/scope-freeze.json`
- `runs/<run-id>/subagent-routing.<role>.json`
- `runs/<run-id>/<role>-executor-report.json`
- `runs/<run-id>/behavior-delta.json`
- `runs/<run-id>/run-telemetry.json`
- `runs/<run-id>/run-artifact-fingerprint.json`
- `promotion-report.json`
- `ops/reports/outcome-metrics.json`
- `ops/reports/promotion-decision-trends.json`
- `ops/reports/auto-improve-sessions/<session-id>.json`

이런 구조는 사후 디버깅뿐 아니라, “시스템이 스스로 낸 결과물의 품질을 이후에 다시 평가하는 루프”를 가능하게 한다.

## 5.4 apply 전에 shadow apply와 rollback rehearsal을 두는 점이 매우 좋다

`mechanism_run_workspace_runtime.py`를 보면 live apply 전에 최소한 아래 산출물을 의식적으로 남긴다.

- `shadow-apply-report.json`
- `rollback-rehearsal-report.json`

또한 rollback rehearsal이 실패하면 live apply 이전에 중단되도록 설계되어 있다.

이것은 단순히 “patch를 적용했다/안 했다”의 문제가 아니다.  
이 시스템은 **변경 자체만이 아니라 변경 적용 메커니즘도 검증 대상으로 취급**하고 있다.

## 5.5 behavior delta와 changed-files manifest가 잘 연결되어 있다

예시 런(`run-20260415-mechanism-planning-gate-second-clean`)의 `changed-files-manifest.json`을 보면 실제 변경 파일이 아래처럼 매우 좁다.

- `ops/scripts/planning_gate_validate_runtime.py`
- `tests/test_planning_gate_validate.py`

이처럼 실제 변경 파일 수와 declared target, test file이 서로 대응되고 있다는 점은 중요하다.  
자가 개선 시스템에서 가장 위험한 것은 “원래 목표보다 변경 범위가 은근히 커지는 현상”인데, 현재 구조는 이를 잘 제어하려고 한다.

## 5.6 메커니즘 리뷰와 mutation proposal 생성이 분리되어 있다

이 저장소는 단순히 실패한 런을 쌓아두는 것이 아니라,

1. outcome metrics를 정리하고
2. mechanism review candidate를 만들고
3. mutation proposal로 연결하는

다운스트림 큐 구조를 갖고 있다.

`README.md`에서도 `refresh-generated` 시 `outcome-metrics -> mechanism-review -> mutation-proposal` 순서를 고정하라고 명시한다.  
이는 self-improvement가 단순 재시도가 아니라, **관찰 → 후보화 → 제안화**의 구조를 가진다는 뜻이다.

---

## 6. 실행 직전 기준의 주요 문제점

## 6.1 가장 먼저 지적할 문제: 현재 큐가 stale할 가능성이 높다

현재 저장소에서 확인된 generated report 시각은 다음과 같다.

- `ops/reports/mechanism-review-candidates.json`  
  - `generated_at: 2026-04-14T19:30:21.578506Z`
  - `candidates_emitted: 0`
- `ops/reports/mutation-proposals.json`  
  - `generated_at: 2026-04-14T19:30:23.054495Z`
  - `proposals_emitted: 0`
- `ops/reports/outcome-metrics.json`  
  - `generated_at: 2026-04-19T18:43:25Z`

반면 `ops/reports/task-improvement-observations/`에는 **2026-04-21, 2026-04-22** 날짜의 후속 관찰이 존재한다.

즉, 현 시점의 해석은 이렇다.

- 저장소는 최근까지 개선 관찰을 축적했다.
- 하지만 **review candidate/proposal queue는 최신 상태로 regenerate되지 않았을 수 있다.**
- 이 상태에서 바로 auto-improve를 돌리면, 시스템은 “할 일이 없음”으로 판단하거나, 최신 개선 힌트를 반영하지 못한 채 런을 시작할 수 있다.

### 판단

이 문제는 사소하지 않다.  
**실행 직전 readiness 관점에서 가장 중요한 블로커 중 하나**다.

### 조치 권고

런 직전 반드시 다음을 수행해야 한다.

1. `make refresh-generated`
2. `outcome-metrics`, `mechanism-review-candidates`, `mutation-proposals` 재생성 확인
3. queue가 실제로 최신 observation과 run history를 반영하는지 검증

---

## 6.2 기본 apply 모드가 `canary_only`라는 점은 장점이지만, 완전 자가 개선은 아니다

정책상 `auto_improve_policy.apply_mode`는 `canary_only`다.  
또한 `run_mechanism_experiment_runtime.py`에서는 finalize가 다음 조건과 연결되어 있다.

- `finalize=request.finalize and workspace_apply.live_applied`

즉, live apply가 일어나지 않으면 finalize 단계도 제한된다.

### 해석

이는 안전성 면에서는 매우 합리적이다.  
그러나 질문이 “자가 개선 성숙도가 어느 정도인가?”라면, 다음처럼 답해야 한다.

- 현재 시스템은 **자가 개선 결과를 생성하고 검증하는 능력**은 높다.
- 하지만 기본 상태는 **스스로 라이브 저장소에 확정 반영하는 단계**까지는 가지 않는다.

즉, 현재 구조는 **self-improvement execution platform**에는 가깝지만, 
아직 **fully autonomous self-application platform**이라고 보기는 어렵다.

### 조치 권고

- 보고/검증 전용 `canary_only`
- 제한된 범위의 `shadow/live gated`
- 최종 승인형 `live finalize`

이 세 모드를 더 명확히 문서화하고, 운영자가 어떤 위험 수준을 선택하는지 분명히 보이게 할 필요가 있다.

---

## 6.3 텔레메트리 보존 로직이 allowlist 기반이다

`auto_improve_iteration_persistence_runtime.py`에는 다음과 같은 보존 필드 묶음이 존재한다.

- `primary_targets`
- `supporting_targets`
- `test_files`
- `workspace_preparation`
- `apply_mode`
- `apply_status`
- `live_applied`
- `shadow_apply_report`
- `rollback_rehearsal_report`

문제는 이것이 **명시적 allowlist**라는 점이다.

실제로 `task-20260422-auto-improve-workspace-preparation/improvement-observations.json`도 이를 후속 과제로 지적한다.

핵심 메시지는 다음과 같다.

- 현재 필요한 필드는 보존하고 있다.
- 하지만 미래의 `run-telemetry` 필드가 추가될 경우, 
  allowlist가 함께 업데이트되지 않으면 **조용히 누락될 수 있다.**

### 왜 중요한가

자가 개선 시스템에서는 나중에 가장 중요한 정보가 “이번에 새로 추가된 필드”인 경우가 많다.  
그 필드가 iteration persistence에서 silently drop되면,

- calibration 품질이 떨어지고
- 회귀 원인 추적이 어려워지며
- 나중에 보안/품질 사고가 났을 때 증적이 불완전해진다.

### 조치 권고

- 스키마 기반 preservation set 도출
- 최소한 schema drift regression test 추가
- optional telemetry field 누락 시 테스트가 실패하도록 고정

이 항목은 **실행 직전 즉시 막아야 할 블로커는 아니지만**, 
현재 자가 개선 성숙도를 5.0으로 올리지 못하는 중요한 이유다.

---

## 6.4 실행성 측면의 작은 함정: `pytest -q` 직접 호출은 깨진다

실제로 저장소 루트에서 `pytest -q`를 직접 호출하면, 테스트 수집 단계에서 다수의 `ModuleNotFoundError: No module named 'ops'`가 발생한다.

반면 `Makefile`은 `"$(PYTHON)" -m pytest ...` 형태를 사용한다.  
핵심 테스트 일부를 `python -m pytest`로 실행했을 때는 정상 종료되었다.

### 해석

이것은 “코드가 근본적으로 깨졌다”는 뜻은 아니다.  
하지만 **실행 직전의 운영 경험** 관점에서는 분명한 문제다.

- 저장소 사용자가 관성적으로 `pytest`를 치면 실패한다.
- 공식 실행 경로는 `python -m pytest` 혹은 `make unit-tests...`인데, 이 차이가 충분히 강제/안내되지 않으면 preflight에서 혼선이 생긴다.

### 조치 권고

- README 상단의 canonical test invocation 더 전면 배치
- 필요 시 `conftest.py` 또는 packaging/pytest 설정 보강
- “plain pytest는 보장하지 않는다”가 아니라 “어떤 방식으로 호출해도 일관되게 동작”하도록 맞추는 것이 이상적

실행 직전 관점에서는 **즉시 치명적 버그는 아니지만, 운영성 마찰이 분명 존재**한다.

---

## 6.5 대형 오케스트레이션 모듈이 아직 남아 있다

비주석 기준 상위 대형 모듈 일부는 다음과 같다.

- `ops/scripts/raw_intake_promotion_runtime.py` — 789 line
- `ops/scripts/filesystem_runtime.py` — 771 line
- `ops/scripts/observability_artifacts_runtime.py` — 767 line
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py` — 673 line
- `ops/scripts/mechanism_run_workspace_runtime.py` — 660 line
- `ops/scripts/policy_validation_runtime.py` — 658 line
- `ops/scripts/mechanism_run_validation_runtime.py` — 617 line
- `ops/scripts/codex_exec_executor.py` — 606 line
- `ops/scripts/mechanism_review_candidate_runtime.py` — 606 line
- `ops/scripts/auto_improve_runtime.py` — 581 line

또한 최신 관찰 리포트 중 하나인 `task-20260421-runtime-decomposition`은 다음 후속 과제를 남긴다.

- promotion gate rule-registry wiring과 finalize flow 일부가 여전히 큰 orchestration surface에 남아 있음
- large test fixture split 필요

### 해석

현재 구조는 “이미 분해를 시작했고 실제로 진전도 있다.”  
그러나 핵심 오케스트레이션의 일부가 여전히 크기 때문에,

- 신규 기여자의 진입 비용이 높고
- 특정 버그 수정이 의도치 않게 다른 정책 경로에 영향 줄 수 있으며
- 자가 개선 시스템 자체를 다시 자가 개선하기가 어려워질 수 있다.

즉, 이 항목은 기능 결함보다는 **성숙도 ceiling**과 관련 있다.

---

## 6.6 strict allowlist 부채가 아직 남아 있다

확인 결과 다음 allowlist가 존재한다.

- `ops/mypy-allowlist.txt` — **138개 항목**
- `ops/mypy-strict-preview-allowlist.txt` — **10개 항목**
- `ops/ruff-strict-preview-allowlist.txt` — **10개 항목**

### 해석

이는 프로젝트가 정적 품질 게이트를 포기한 것이 아니라, **점진적 엄격화 전략**을 취하고 있음을 뜻한다.  
다만 자가 개선 관점에서는 다음 우려가 있다.

- strict 밖에 남아 있는 surface가 계속 중요한 런타임에 머물면,
- 시스템이 스스로를 개선하더라도 “가장 어려운 부분”은 계속 보호막 밖에 남는다.

### 조치 권고

- auto-improve와 직접 연결되는 런타임부터 strict preview allowlist를 줄이기
- 대형 모듈 분해와 strict 전환을 같은 작업으로 묶지 말고 분리해 진행하기

---

## 6.7 활성 run history가 아직 깊지 않다

확인된 핵심 promotion report 흐름은 대략 다음과 같다.

- `runs/run-20260414-mechanism-planning-gate/promotion-report.json` → `PROMOTE`
- `runs/run-20260415-mechanism-planning-gate-second-clean/promotion-report.json` → `PROMOTE`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/promotion-report.json` → `DISCARD`, 
  archived reason: `false discard from runner defect; excluded from active mechanism history`

### 해석

히스토리가 전혀 없는 것은 아니지만, **calibration과 trend 분석에 충분히 깊은 표본**이라고 보기는 어렵다.

- 메커니즘 리뷰 후보가 비어 있는 이유가 정말 “문제가 없어서”인지
- 아니면 “표본이 적어서 why-now가 잘 안 잡히는 것인지”를 구분하려면
- 더 많은 정상/실패/보류 run history가 필요하다.

즉, 현재 시스템은 구조적으로 self-improvement를 잘 설계했지만, 
통계적/운영적 신뢰도는 아직 **초기-중기 구간**이다.

---

## 7. 자가 개선 실행 직전 체크리스트

지금 이 저장소에서 auto-improve 런을 시작하기 직전에, 최소한 아래를 확인해야 한다.

### 7.1 반드시 먼저 할 것

1. **generated artifact 갱신**
   - `make refresh-generated`
   - `outcome-metrics -> mechanism-review -> mutation-proposal` 순서 유지 확인

2. **proposal queue 최신성 확인**
   - `ops/reports/mechanism-review-candidates.json`
   - `ops/reports/mutation-proposals.json`
   - 생성 시각과 proposal 수 재검토

3. **테스트 실행 경로 통일**
   - `python -m pytest` 또는 Makefile 경로 사용
   - plain `pytest` 호출에 의존하지 않기

4. **정책 파일과 실제 운영 모드 일치 확인**
   - `apply_mode`
   - `allowed_apply_roots`
   - `max_proposals`
   - `max_consecutive_failures`
   - `require_unblocked`

5. **workspace apply 보호장치 활성 확인**
   - shadow apply report 생성 여부
   - rollback rehearsal report 생성 여부

### 7.2 가능하면 같이 할 것

6. **핵심 fast-tier 테스트 세트 재실행**
   - auto-improve / mechanism experiment / policy validation 관련 핵심 스위트 우선

7. **최근 observation을 proposal에 연결하는지 확인**
   - 특히 2026-04-21, 2026-04-22 observation이 downstream queue에 반영되는지 검증

8. **run history 상태 점검**
   - archived / quarantined / active 구분이 올바른지 확인

### 7.3 런을 바로 막을 정도는 아니지만 빨리 개선할 것

9. **run telemetry preservation contract 강화**
10. **strict allowlist 축소 계획 정리**
11. **대형 orchestration/runtime 분해 로드맵 유지**

---

## 8. 실행 직전 관점의 최종 판정

## 8.1 지금 당장 auto-improve를 실행해도 되는가?

**조건부로 가능하다.**  
다만 **그 전에 generated artifact refresh와 preflight를 하지 않으면, 운영적으로는 “준비되지 않은 런”에 가깝다.**

다시 말해,

- 코드 구조와 정책 구조는 충분히 준비되어 있다.
- 그러나 현재 저장소 스냅샷 기준으로는 queue/report freshness가 뒤처져 보인다.
- 따라서 지금 바로 실행하는 것보다, **refresh-generated → 핵심 테스트 → queue 확인 → run** 순으로 들어가는 것이 맞다.

## 8.2 지금 실행하면 가장 걱정되는 실패 양상은 무엇인가?

가장 우려되는 것은 다음 세 가지다.

1. **큐가 비어서 의미 없는 런이 되는 경우**
   - 실제 개선 아이디어는 최신 observation에 있는데, proposal queue가 stale해서 잡지 못함

2. **실행은 되지만 finalize/self-apply 기대와 다른 경우**
   - 기본 모드가 `canary_only`라서, 운영자가 기대한 수준의 자동 적용이 일어나지 않을 수 있음

3. **나중에 telemetry 해석이 비는 경우**
   - 필드 보존 allowlist가 미래 변화에 취약해, 반복 런 비교 시 데이터 누락 가능

---

## 9. 보완 우선순위 제안

## 9.1 즉시(런 전)

### P0-1. generated artifact 재생성 강제

- 목적: stale queue 제거
- 조치:
  - `make refresh-generated`
  - 생성 시각과 proposal/candidate 수 확인
- 기대 효과:
  - “이번 런이 최신 판단 근거 위에서 시작되는가”를 보장

### P0-2. canonical test entrypoint 고정

- 목적: preflight 혼선 제거
- 조치:
  - `python -m pytest` / Makefile 경로를 공식 경로로 더 강하게 노출
  - 필요시 plain `pytest`도 동작하도록 보정
- 기대 효과:
  - 실행 직전 실패의 상당 부분 제거

### P0-3. 실제 적용 모드 의도 재확인

- 목적: 기대와 실제 apply semantics 정렬
- 조치:
  - 이번 런의 목적이 canary인지 live finalize인지 명시
  - 정책/CLI/문서 상 모두 같은 의미로 보이게 정리
- 기대 효과:
  - “왜 변경이 적용되지 않았지?” 같은 운영 혼선 감소

## 9.2 단기(1~2 iteration)

### P1-1. telemetry preservation을 schema contract 기반으로 전환

- 목적: 미래 필드 누락 방지
- 조치:
  - schema-derived merge/preservation rule
  - regression fixture 추가
- 기대 효과:
  - 장기 비교 가능성 향상

### P1-2. large orchestration module 추가 분해

- 대상 예시:
  - `mechanism_run_workspace_runtime.py`
  - `policy_validation_runtime.py`
  - `codex_exec_executor.py`
  - `auto_improve_runtime.py`
- 기대 효과:
  - self-improvement 대상 자체가 더 좁고 안전해짐

### P1-3. auto-improve session report 실제 축적 시작

- 현재 스냅샷 기준 `ops/reports/auto-improve-sessions/*.json`은 확인되지 않았다.
- session rollup이 실제로 누적되기 시작하면,
  - session calibration
  - failure family clustering
  - why-now candidate 품질이 개선된다.

## 9.3 중기(3~5 iteration)

### P2-1. strict allowlist 단계적 축소

- auto-improve 핵심 경로부터 우선 strict 강화
- 모듈 분해와 strict 전환을 단계적으로 분리

### P2-2. self-apply maturity model 명문화

예를 들어 다음 3단계로 운영 수준을 정의할 수 있다.

- Level A: report/canary only
- Level B: shadow + rollback rehearsed apply
- Level C: gated live finalize

이렇게 하면 자가 개선 성숙도를 “있다/없다”가 아니라 **운영 등급**으로 관리할 수 있다.

### P2-3. history depth 확보

- 정상 PROMOTE
- HOLD
- DISCARD
- quarantine
- runner defect 복구 사례

를 충분히 누적해 review calibration의 통계적 안정성을 높일 필요가 있다.

---

## 10. 자가 개선 관점의 최종 성숙도 판정

현재 저장소는 아래와 같이 평가할 수 있다.

### 10.1 이미 달성한 것

- 자가 개선 실험 루프의 단계 분해
- 정책 기반 범위 통제
- bounded mutation
- 스키마 기반 산출물
- rollback rehearsal과 shadow apply
- behavior delta와 changed-files manifest의 결합
- mechanism review와 mutation proposal의 분리
- 공급망/출처/증적 표면의 강한 의식

### 10.2 아직 남은 것

- 최신 observation과 proposal queue의 자동 정합성
- telemetry preservation의 계약화
- 대형 orchestration surface 추가 축소
- strict allowlist 축소
- 더 풍부한 실행 이력 기반 calibration
- canary와 live self-application의 운영 semantics 명확화

### 10.3 최종 문장

**이 시스템은 “자가 개선을 시도할 수 있는 수준”을 이미 넘어섰다.**  
현재는 **“안전하게 통제된 자가 개선을 반복 운영할 수 있는 수준”** 에 도달해 있다.  
다만 **“스스로 바꾸고, 스스로 확정하고, 그 결과를 장기적으로 안정적으로 재학습하는 완전 폐루프 시스템”** 으로 보려면,

- queue freshness,
- telemetry contract,
- orchestration 축소,
- history depth,
- self-apply semantics 정리

가 더 필요하다.

즉, 자가 개선 성숙도는 **높은 편이지만 아직 최종 단계는 아니다.**

---

## 11. 실무용 권고안

실제로 지금 이 저장소를 운영 중이라면, 자가 개선 런 직전 아래 순서를 권고한다.

1. `make refresh-generated`
2. proposal/candidate 생성 시각과 건수 확인
3. `python -m pytest` 또는 Makefile 기반 핵심 스위트 실행
4. 이번 런의 apply 목적이 canary인지 live인지 명시
5. auto-improve 런 시작
6. 산출물 확인
   - `scope-freeze`
   - `routing report`
   - `behavior-delta`
   - `run-telemetry`
   - `shadow/rollback report`
   - `promotion-report`
7. session rollup과 outcome metrics 업데이트
8. 이후 iteration에서 telemetry contract와 large module 분해를 우선 처리

---

## 12. 결론

현재 코드베이스는 **무질서한 자기 수정기(self-modifier)** 가 아니라, **정책·증적·스키마·검증을 동반한 자가 개선 메커니즘 저장소**다.  
그 점에서 성숙도는 분명 높다.

그러나 **실행 직전**이라는 현실적 시점에서 가장 중요한 판단은 다음이다.

> **지금 구조는 좋다. 하지만 지금 큐와 generated artifact가 최신 상태인지 먼저 보장해야 한다.**

따라서 최종 권고는 다음과 같다.

- **자가 개선 런 진행: 가능**
- **즉시 실행: 비권장**
- **refresh-generated + preflight 후 실행: 권장**

운영적으로 가장 바람직한 해석은 이렇다.

> **현재 저장소는 자가 개선을 “해볼 수 있는 시스템”이 아니라, “안전하게 돌릴 수 있는 자가 개선 시스템”에 가까우며, 이제 남은 과제는 품질 고도화와 완전 폐루프화다.**

