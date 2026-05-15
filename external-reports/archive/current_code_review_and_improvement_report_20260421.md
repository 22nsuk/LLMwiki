# Current Code Review and Improvement Report

작성일: 2026-04-21  
대상: `LLM Wiki vNext` 현재 코드베이스  
형식: 상세 코드 검토 및 개선 권고 보고서

---

## 1. 요약

이번 검토의 결론은 다음과 같습니다.

- **설계 성숙도는 높다.** 저장소는 단순 스크립트 모음이 아니라, `policy → schema → lint/eval → planning gate → mechanism review → mutation proposal → auto-improve`로 이어지는 **운영 메커니즘 중심 구조**를 이미 갖추고 있습니다.
- **그러나 기본 품질 게이트의 일관성은 아직 완전히 닫히지 않았다.** 실제로 현재 상태에서 **fast tier 테스트 수집이 깨지고**, **mypy hard gate도 실패**합니다.
- **즉, 구조는 L3~L4 수준으로 올라가고 있지만, 실행 안정성은 아직 그 수준에 완전히 합류하지 못했다**고 판단됩니다.
- 자가 개선 관점에서 보면, 이 저장소는 **아이디어 수준의 self-improvement가 아니라 실제 artifact와 telemetry를 남기는 운영형 self-improvement 시스템**입니다. 다만 **폐루프(closed loop) 완결성**과 **인터페이스 안정성**이 더 보완되어야 합니다.

### 총평

> **아키텍처와 운영 철학은 매우 좋다.**  
> 하지만 **모듈 경계 계약(export/import contract)**, **정적 타입 게이트**, **복잡도 예산의 실제 강제력**에서 아직 운영 부채가 남아 있다.

---

## 2. 검토 범위와 방법

### 2.1 검토 범위

압축 파일에는 raw 문서, generated artifact, external report, cache, 가상환경 흔적까지 함께 포함되어 있었습니다. 따라서 이번 보고서는 다음과 같이 범위를 분리했습니다.

#### 주 검토 대상
- `ops/scripts/*.py`
- `tests/*.py`
- `tools/*.py`
- `pyproject.toml`
- `pytest.ini`
- `Makefile`
- `.github/workflows/*.yml`
- `ops/policies/*.yaml`
- `ops/schemas/*.json`
- `ops/reports/task-improvement-observations/*`
- 구조 설명 문서 (`README.md`, `ARCHITECTURE.md`, `ops/README.md`)

#### 보조 참고 대상
- `external-reports/` 기존 보고서
- `ops/reports/*.json` 생성 artifact 일부
- `system/` 내 self-improvement 개념 문서

#### 제외 또는 축소 대상
- `raw/web-snapshots/` 및 대용량 raw source 본문 전체
- `.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`
- 실행 코드가 아닌 binary report 본문 전체

### 2.2 실제 검토 방식

- 압축 내부 파일 구조 확인
- 실행 코드와 테스트 코드 분리 추출
- 저장소 구조/정책/CI/빌드 설정 검토
- 정적 검사 재현
  - `ruff check`
  - `mypy`
- 테스트 수집 및 fast tier 일부 재현
- 복잡도/함수 예산 관련 runtime 산출물 재계산
- self-improvement 관련 artifact와 운영 루프 검토

---

## 3. 저장소 스냅샷

이번 검토에서 파악한 현재 코드베이스의 대략적 규모는 다음과 같습니다.

- Python 파일 수: **223개**
- Python 비공백 LOC: **48,004줄**
- `ops/` 비공백 LOC: **26,298줄**
- `tests/` 비공백 LOC: **21,390줄**
- Python function budget candidate 수: **49개**

이 수치는 다음을 의미합니다.

1. 이 저장소는 더 이상 “작은 자동화 스크립트 묶음”이 아닙니다.  
2. 유지보수 전략 없이 두면 빠르게 복잡도 부채가 쌓일 수 있는 규모입니다.  
3. 반대로 말하면, **복잡도 예산**, **정책 기반 분해**, **artifact 기반 운영**이 반드시 필요한 단계까지 이미 성장했습니다.

---

## 4. 확인된 강점

## 4.1 자가 개선 루프가 코드와 artifact로 실체화되어 있음

이 저장소의 가장 큰 강점은 “자가 개선”이 구호가 아니라 **구조**로 구현되어 있다는 점입니다.

대표 근거:
- `ops/scripts/mechanism_review.py`
- `ops/scripts/mutation_proposal.py`
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/auto_improve_session_runtime.py`
- `ops/scripts/improvement_observations_runtime.py`
- `ops/reports/task-improvement-observations/*`

즉, 이 프로젝트는 아래 단계가 분리되어 있습니다.

- 메커니즘 후보 식별
- 후보를 proposal로 정제
- proposal을 queue로 관리
- 실험 실행
- 결과를 telemetry / session report / outcome metrics로 축적
- 그 과정에서 다시 improvement observation을 남김

이 수준은 일반적인 “테스트 자동화 있음” 수준보다 훨씬 성숙합니다.

## 4.2 정책과 스키마가 단일 운영 계약으로 작동함

다음 구조는 매우 좋습니다.

- 정책: `ops/policies/wiki-maintainer-policy.yaml`
- 스키마: `ops/schemas/*.json`
- 런타임: `ops/scripts/*.py`
- 테스트: `tests/*.py`

특히 README와 ops/README에서 **policy가 single source of truth**로 다뤄지고 있고, 실제 코드도 이를 전제로 구성되어 있습니다. 이런 구조는 장기적으로 prompt나 운영 습관에 의존하지 않고, **기계적으로 검증 가능한 운영 계약**으로 이동하기 위한 좋은 기반입니다.

## 4.3 운영 게이트가 다층 구조로 분해되어 있음

`make check` / `make check-all` / `make test-*` / `make public-check` / `make supply-chain-check` / `make sbom-readiness-check`처럼 게이트가 층별로 나뉘어 있습니다.

이 점은 다음 관점에서 좋습니다.

- 빠른 루프와 무거운 루프가 분리됨
- public/private surface가 분리됨
- release 전 검증이 별도 경로로 존재함
- supply chain 검증이 부가 기능이 아니라 운영 경로에 편입됨

## 4.4 공급망/출처 무결성에 대한 감수성이 높음

다음 artifact 경로와 workflow는 이 저장소가 공급망 무결성을 **실제 운영 이슈**로 다룬다는 증거입니다.

- `ops/scripts/cyclonedx_sbom.py`
- `ops/scripts/spdx_sbom.py`
- `ops/scripts/openvex_draft.py`
- `ops/scripts/in_toto_statement.py`
- `ops/scripts/sigstore_bundle.py`
- `.github/workflows/release.yml`
- `.github/workflows/ci.yml`

이는 단순 “패키지 빌드 가능” 수준을 넘어, 배포 artifact의 provenance와 설명가능성을 확보하려는 시도로 읽힙니다.

## 4.5 self-review의 흔적이 반복적으로 남아 있음

`ops/reports/task-improvement-observations/` 아래에는 이미 여러 maintenance task에 대한 개선 관찰이 누적되어 있습니다.

예를 들어 `task-20260421-runtime-decomposition`에는 다음과 같은 문제의식이 명시되어 있습니다.

- promotion gate 분해가 아직 덜 끝남
- structural complexity budget artifact를 정식 gate로 올려야 함

즉, 이 저장소는 **스스로의 유지보수 문제를 인식하고, 이를 artifact로 남기며, 다음 개선 항목으로 연결하는 문화**를 이미 갖고 있습니다.

---

## 5. 핵심 문제점

아래는 현재 상태에서 우선순위가 높은 이슈입니다.

| 우선순위 | 영역 | 문제 | 영향 |
|---|---|---|---|
| P0 | 테스트/계약 | `tests/test_mechanism_review_candidate_runtime.py`가 존재하지 않는 export를 import함 | fast tier 수집 단계 중단 |
| P1 | 정적 타입 | `planning_gate_validate_runtime.py`에서 mypy hard gate 실패 | `make static` 불통과 |
| P1 | 복잡도 | `planning_gate_validate_runtime.py`, `finalize_run_runtime.py`가 closeout 예산 초과 | 변경 리스크, 회귀 가능성 증가 |
| P2 | 인터페이스 안정성 | 모듈 간 public surface가 암묵적이라 export drift 발생 | 테스트/리팩터링 시 파손 가능 |
| P2 | 함수 설계 | parameter count 및 function length 초과 함수 다수 | 호출 계약 비대화, 추론 비용 증가 |
| P2 | 개선 루프 완결성 | observation → proposal → hard gate 승격이 아직 반자동/부분 수동 | self-improvement 효과가 누적되기 어려움 |
| P3 | 배포/검토 위생 | 압축 산출물에 cache/venv/generated artifact가 많이 섞여 있음 | 리뷰 재현성 및 전달 효율 저하 |

---

## 6. 상세 진단

## 6.1 P0 — 테스트 수집 단계가 현재 깨져 있음

### 확인 내용
fast tier 재현 중 다음 문제가 확인됐습니다.

- 파일: `tests/test_mechanism_review_candidate_runtime.py`
- import 대상: `ops.scripts.mechanism_review_candidate_runtime`
- 실패 심볼: `build_session_calibration_diagnostics`

즉, 테스트는 아래를 기대합니다.

```python
from ops.scripts.mechanism_review_candidate_runtime import (
    build_candidates,
    build_session_calibration_diagnostics,
    candidate_template,
)
```

하지만 실제 구현은 `build_session_calibration_diagnostics`를
`mechanism_review_session_calibration_runtime.py`에 두고 있으며,
`mechanism_review_candidate_runtime.py`에서는 이를 export하지 않습니다.

### 왜 중요한가
이 문제는 단순 import typo가 아닙니다.

이 문제는 **모듈 경계의 계약이 코드로 명시되지 않았기 때문에 생긴 export drift**입니다.

즉,
- 어느 모듈이 canonical public surface인지 불명확하고
- 테스트가 암묵적 barrel module처럼 사용하며
- 구현은 분리되었지만 테스트/계약은 그 변경을 따라가지 못했습니다.

### 영향
- fast tier 수집 단계 중단
- CI fast contract tier 불안정 가능성
- refactor 후 계약 안정성에 대한 신뢰 저하

### 권고
1. **즉시 조치**
   - 둘 중 하나를 선택해야 합니다.
     - A안: `mechanism_review_candidate_runtime.py`에서 `build_session_calibration_diagnostics`를 명시 re-export
     - B안: 테스트 import를 실제 소유 모듈인 `mechanism_review_session_calibration_runtime.py`로 이동
2. **근본 조치**
   - runtime helper module의 public API를 `__all__` 또는 명시적 barrel module로 고정
   - “어느 모듈이 외부 계약 표면인지”를 테스트로 보증
   - import contract test를 별도로 추가

### 권장 방향
개인적으로는 **B안(테스트 import를 소유 모듈로 이동)** + **barrel module를 정말 필요할 때만 유지**가 더 낫습니다.  
지금 구조는 분해가 진행 중이므로, barrel surface를 무분별하게 늘리면 이후 또 다른 drift가 생길 가능성이 큽니다.

---

## 6.2 P1 — mypy hard gate 실패

### 확인 내용
정적 검사 재현 결과, `ruff`는 통과했지만 `mypy`는 다음 2건에서 실패했습니다.

- 파일: `ops/scripts/planning_gate_validate_runtime.py`
- 라인 324
  - 반환 타입: `list[ValidationCheckResult]` 기대
  - 실제 추론: `list[dict[Any, Any]]`
- 라인 614
  - 반환 타입: `PlanningValidationReport` 기대
  - 실제 추론: 일반 `dict[...]`

### 해석
이 문제는 실제 런타임 버그라기보다, **TypedDict 기반 계약을 선언했지만 딕셔너리 literal 조립부가 타입 시스템과 완전히 정렬되지 않은 상태**입니다.

즉, 코드는 “스키마적으로는 맞을 가능성”이 있어도, 타입 시스템 입장에서는
- helper가 `ValidationCheckResult`를 반환한다고 충분히 증명되지 않고
- 최종 report도 `PlanningValidationReport`로 좁혀지지 않습니다.

### 왜 중요한가
이 저장소는 “정책/스키마/정적 게이트”를 강하게 가져가려는 프로젝트입니다. 그렇다면 mypy 실패는 단순 취향 문제가 아니라 **운영 계약 불일치**입니다.

### 권고
- `_in_progress_phase_checks()` 류의 함수에서 리스트 초기화를 명시적으로 typed list로 고정
- phase check builder들이 `ValidationCheckResult`를 명시적으로 반환하도록 타입 시그니처를 맞춤
- 최종 report는
  ```python
  report: PlanningValidationReport = {...}
  ```
  형태로 명시하거나, 생성 helper를 별도 함수로 분리
- 가능하면 class-based `TypedDict` 또는 전용 builder helper로 “typed object construction”을 중앙화

### 기대 효과
- `make static` 회복
- planning gate 주변 refactor 안정성 향상
- schema-valid 이면서 mypy-valid 인 이중 계약 확보

---

## 6.3 P1 — closeout 계열 오케스트레이터가 복잡도 예산을 초과

재계산한 structural complexity budget 결과를 보면, 특히 closeout orchestration 계열에 경고가 큽니다.

### 주요 경고 대상

#### `ops/scripts/planning_gate_validate_runtime.py`
- 비공백 LOC: **571**
- 함수 수: **18**
- branch node 수: **49**
- closeout profile budget:
  - LOC **260**
  - 함수 수 **18**
  - branch node **40**

#### `ops/scripts/finalize_run_runtime.py`
- 비공백 LOC: **448**
- 함수 수: **16**
- branch node 수: **33**
- closeout profile budget:
  - LOC **260**
  - 함수 수 **18**
  - branch node **40**

### 해석
두 파일 모두 기능 자체는 타당하지만, **상태 전이 + artifact 정렬 + 검증 + 로그/출력 처리**가 한 파일 안에 많이 응집되어 있습니다.

이런 파일은 보통 다음 문제를 유발합니다.
- 리팩터링 시 회귀 범위가 넓음
- 부분 기능 테스트가 어려움
- 타입 시그니처가 흐려짐
- “조금만 덧붙여도” 금방 더 커짐

### 권고
이 둘은 다음 스프린트에서 **가장 먼저 분해해야 하는 1순위 대상**입니다.

#### `planning_gate_validate_runtime.py` 분해 제안
- artifact loading / schema validation
- phase-state derivation
- cross-check assembly
- phase-check assembly
- final report emission / runtime event logging

#### `finalize_run_runtime.py` 분해 제안
- decision record 검증
- atomic write plan 생성
- log append / refresh planning validation
- rollback / compensation 처리
- closeout report assembly

---

## 6.4 P2 — 함수 수준 설계 부채가 누적 중

function budget candidate를 보면 총 **49개**가 잡혔고, 그중 핵심 runtime에서 반복적으로 다음 유형이 나타납니다.

### 대표 사례

- `ops/scripts/behavior_delta_runtime.py::build_behavior_delta_report`
  - 166 lines, 11 params
- `ops/scripts/finalize_run_runtime.py::finalize_run`
  - 183 lines
- `ops/scripts/planning_gate_validate_runtime.py::validate_run_dir`
  - 142 lines
- `ops/scripts/wiki_eval.py::evaluate`
  - 179 lines
- `ops/scripts/wiki_stage2_eval.py::evaluate`
  - 184 lines
- `ops/scripts/codex_exec_executor.py::_materialize_prompt`
  - 16 params
- `ops/scripts/auto_improve_execute_runtime.py::evaluate_execution_outcome`
  - 13 params
- `ops/scripts/auto_improve_execute_runtime.py::execute_evaluate_phase`
  - 13 params

### 진단
이 패턴은 크게 두 종류입니다.

1. **오케스트레이터 과대화**
   - 한 함수가 “조립 + 검증 + 상태 전이 + 출력”을 동시에 담당
2. **파라미터 폭증**
   - 함수 경계가 도메인 객체 대신 primitive argument 묶음을 직접 전달

### 권고
- parameter object 도입 (`dataclass`/TypedDict/Context object)
- orchestration function은 80~120줄 안쪽으로 관리
- pure helper와 side-effect helper를 분리
- `evaluate()` 계열은 입력 해석/채점/요약/출력의 단계를 나눔

---

## 6.5 P2 — self-improvement는 존재하지만, 아직 “완전 폐루프”는 아님

이 저장소는 self-improvement artifact를 잘 남깁니다. 이것은 분명 강점입니다.

하지만 현재는 아래와 같은 간극이 보입니다.

- observation이 남음
- complexity budget report도 생성됨
- strict preview allowlist도 있음
- 그러나 그 신호가 **항상 hard gate 승격**으로 이어지지는 않음
- 일부는 여전히 preview / planned / optional strict target에 머묾

예를 들어,
- structural complexity budget은 존재하지만 현재 기본 hard gate는 아님
- strict mypy/ruff preview가 있지만 핵심 helper surface 전체를 강제하진 않음
- improvement observation이 proposal queue로 자동 연결되는 닫힌 체계는 아직 약함

### 의미
지금은 **self-improvement capable** 단계이지, **self-improvement fully self-enforcing** 단계는 아닙니다.

즉,
- “개선 항목을 감지하고 기록하는 능력”은 충분히 있음
- “감지된 항목을 자동으로 누적 교정하는 능력”은 아직 부분적임

---

## 6.6 P3 — 리뷰/배포 위생 측면에서 압축 산출물이 무거움

이번 압축에는 다음이 함께 들어 있었습니다.

- `.venv/`
- `__pycache__`
- `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`
- `external-reports/`
- 대용량 raw PDF
- 긴 파일명의 web snapshot

이것이 코드 품질 자체의 결함은 아닙니다. 다만 다음 문제가 있습니다.

- 리뷰 전달 비용 증가
- 재현 경로 혼선
- 압축 해제 실패 가능성 증가
- code review와 runtime artifact review가 섞임

### 권고
외부 전달용 아카이브는 최소 두 종류로 분리하는 편이 좋습니다.

1. **source review bundle**
   - `ops/`, `tests/`, `tools/`, workflow, config
2. **full vault / evidence bundle**
   - raw, reports, runs, system, external-reports

---

## 7. 자가 개선 성숙도 평가

## 7.1 결론

자가 개선(self-improvement) 관련 성숙도는 다음과 같이 평가합니다.

> **종합 성숙도: 3.6 / 5.0**  
> **해석: CMMI 관점으로는 L3(Defined) 후반에서 L4(Quantitatively Managed) 초입**

즉,
- 운영 표준과 역할 분리가 이미 정립되어 있고
- 정량 artifact와 telemetry도 존재하며
- 실험/제안/평가 루프도 구현돼 있지만
- 아직 **정량 통제의 일관된 강제력**과 **폐루프 자동성**이 충분히 안정화되지는 않았습니다.

## 7.2 왜 L3 후반~L4 초입인가

### L3(Defined) 수준 근거
- policy, schema, template, script 역할이 명확함
- 운영 절차가 README/ops/README/Makefile/CI로 명문화됨
- mechanism review / mutation proposal / auto improve session이 표준화되어 있음
- public/private surface 분리가 설계 문서와 workflow에 반영됨

### L4(Quantitatively Managed) 징후
- outcome metrics, warning budget, complexity budget, session rollup, routing provenance 등 **정량 artifact**가 존재함
- promotion / hold / discard / rollback 신호를 수집하려는 구조가 있음
- session calibration, outcome metrics calibration 같은 **정량 보정 계층**이 구현됨

### 아직 L4 전면 진입이 아닌 이유
- 기본 gate가 현재 깨져 있음 (테스트 수집, mypy)
- complexity budget이 아직 hard contract로 완전히 승격되지 않음
- 인터페이스 drift를 사전에 막는 export/import contract가 약함
- observation이 자동 시정으로 닫히는 수준까지는 아님

### 아직 L5(Optimizing)가 아닌 이유
L5라면 보통 아래가 안정적으로 돌아야 합니다.

- 회귀 신호가 자동으로 분류되고
- 우선순위가 정량적으로 보정되며
- 개선이 운영 표준으로 빠르게 승격되고
- 구조적 부채가 장기 누적되기 전에 지속적으로 상쇄됩니다.

현재 저장소는 이 방향으로 가고 있지만, 아직 **운영적 일관성**이 완전히 닫히진 않았습니다.

## 7.3 세부 점수

| 평가 축 | 점수(5점 만점) | 판단 |
|---|---:|---|
| 운영 표준화 | 4.5 | policy/schema/template 기반 운영이 명확함 |
| 계측/관측성 | 4.0 | telemetry, session rollup, outcome metrics가 존재 |
| 자동 검증/게이팅 | 3.2 | 구조는 좋지만 현재 실제 게이트 실패가 존재 |
| 실험 통제/rollback | 4.0 | promote/hold/discard/rollback 감수성이 높음 |
| 인터페이스 안정성 | 2.7 | export drift와 typed boundary 불안정 존재 |
| 복잡도 관리 | 3.1 | budget와 preview는 있으나 강제력이 부분적 |
| self-improvement 폐루프성 | 3.6 | observation/proposal/session은 있으나 fully self-enforcing는 아님 |

---

## 8. 보완 방안

## 8.1 즉시 조치(1~2일)

### A. 깨진 fast tier 복구
- `build_session_calibration_diagnostics` import/export 정렬
- 관련 contract test 추가
- 최소한 `pytest --collect-only`를 CI fast tier에서 별도 확인

### B. mypy gate 복구
- `planning_gate_validate_runtime.py`의 TypedDict 반환값 정렬
- report assembly typed helper 도입
- `ValidationCheckResult`/`PlanningValidationReport` 생성 helper 통일

### C. public surface 명시
- 각 runtime helper module의 public API를 명시
- `__all__` 또는 dedicated barrel module 적용
- refactor 시 import path drift를 잡는 테스트 추가

## 8.2 단기 조치(1~2주)

### D. closeout orchestration 분해
우선순위:
1. `planning_gate_validate_runtime.py`
2. `finalize_run_runtime.py`
3. `behavior_delta_runtime.py`
4. `wiki_eval.py`, `wiki_stage2_eval.py`

### E. parameter object 도입
대상 예시:
- `codex_exec_executor._materialize_prompt`
- `auto_improve_execute_runtime.evaluate_execution_outcome`
- `auto_improve_execute_runtime.execute_evaluate_phase`

효과:
- 함수 경계 단순화
- 테스트 fixture 단순화
- 타입 안정성 향상

### F. complexity signal의 gate 승격
- 현재 budget report를 생성만 하지 말고
- **touched path** 또는 **high-risk runtime subset**에 한해 fail-on-attention 또는 delta gate 도입
- strict preview allowlist 확대는 “최근 수정 표면” 중심으로 진행

## 8.3 중기 조치(2~4주)

### G. self-improvement 폐루프 강화
다음 연결을 자동화하는 것이 좋습니다.

- `improvement-observations.json`
  → mutation proposal 후보 생성
  → priority 보정
  → proposal queue 반영
  → 결과가 다시 observation close 여부로 연결

즉, observation을 “기록”에서 끝내지 말고 **실험 큐 입력**으로 승격해야 합니다.

### H. 메트릭 운영 체계 정교화
다음 축을 주기적으로 합쳐 보는 것이 좋습니다.

- failure taxonomy
- rollback signal
- rework count
- defect escape proxy
- function budget delta
- complexity budget delta
- queue quarantine rate

이렇게 해야 “많이 돌렸다”가 아니라 **실제로 개선됐는지**를 더 선명하게 볼 수 있습니다.

### I. 전달/보관 번들 표준화
- review bundle
- release bundle
- full vault bundle

을 분리하여 운영하면 외부 검토와 내부 운영 모두가 쉬워집니다.

---

## 9. 추천 우선순위 로드맵

## 단계 1 — 오늘 바로 고칠 것
1. `tests/test_mechanism_review_candidate_runtime.py` import 경로 정렬
2. `planning_gate_validate_runtime.py` mypy 오류 수정
3. fast tier에 import/export contract test 추가

## 단계 2 — 이번 주에 끝낼 것
1. `planning_gate_validate_runtime.py` 분해
2. `finalize_run_runtime.py` 분해
3. parameter object 도입 시작
4. touched-path complexity delta gate 시범 적용

## 단계 3 — 다음 개선 사이클에서 할 것
1. observation → proposal 자동 연결
2. complexity/warning/outcome metric 통합 대시보드화
3. preview strict gate를 점진적으로 기본 gate로 승격

---

## 10. 최종 판단

이 프로젝트는 **설계 철학과 운영 사고가 매우 성숙한 편**입니다.  
특히 아래 세 가지는 분명한 장점입니다.

1. **자가 개선 구조가 실제 코드와 artifact로 존재한다**  
2. **정책/스키마/테스트/CI가 같은 방향을 보고 있다**  
3. **공급망 무결성과 운영 추적성에 대한 감수성이 높다**

하지만 지금 당장 운영 신뢰도를 떨어뜨리는 문제도 분명합니다.

1. **테스트 수집이 깨지는 계약 drift**  
2. **mypy hard gate 불통과**  
3. **핵심 closeout orchestrator의 과도한 응집도**

따라서 현재 상태를 한 문장으로 정리하면 다음과 같습니다.

> **“자가 개선 시스템으로서의 방향성은 매우 좋고, 중상급 성숙도에 올라와 있지만, 기본 게이트 안정성과 모듈 경계 계약을 먼저 다져야 다음 단계로 안전하게 올라갈 수 있다.”**

---

## 부록 A. 이번 검토에서 바로 확인된 재현 포인트

### A-1. ruff
- 결과: 통과

### A-2. mypy
- 결과: 실패 2건
- 대상: `ops/scripts/planning_gate_validate_runtime.py`

### A-3. fast tier pytest
- 결과: 수집 단계에서 import error 발생
- 대상: `tests/test_mechanism_review_candidate_runtime.py`

### A-4. structural complexity budget
- 결과: `attention`
- 다만 attention list 자체는 비어 있고, 여러 핵심 파일이 `warn`
- 특히 closeout orchestrator 예산 초과가 두드러짐

### A-5. python function budget
- 결과: candidate 49건
- 핵심 runtime 일부에서 function length / parameter count 초과 다수

---

## 부록 B. 외부 기준으로 참고한 프레임

이번 보고서의 성숙도 해석과 보완 방향은 아래 성격의 외부 기준을 참고해 정리했습니다.

- OpenAI Evals / agent eval best practices  
  - https://developers.openai.com/api/docs/guides/evaluation-best-practices  
  - https://developers.openai.com/api/docs/guides/agent-evals
- CMMI maturity levels  
  - https://cmmiinstitute.com/learning/appraisals/levels
- NIST SSDF  
  - https://csrc.nist.gov/pubs/sp/800/218/final
- SLSA  
  - https://slsa.dev/  
  - https://slsa.dev/spec/v1.0/
- in-toto  
  - https://in-toto.io/  
  - https://slsa.dev/blog/2023/05/in-toto-and-slsa
- OpenVEX  
  - https://github.com/openvex/spec  
  - https://openssf.org/projects/openvex/
- PyPI Trusted Publishing / attestations  
  - https://docs.pypi.org/trusted-publishers/using-a-publisher/  
  - https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/  
  - https://docs.pypi.org/attestations/producing-attestations/
- DORA metrics  
  - https://dora.dev/guides/dora-metrics/  
  - https://dora.dev/research/
- pytest-xdist / 병렬 테스트 운영 참고  
  - https://pytest-xdist.readthedocs.io/en/stable/distribution.html  
  - https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html
- mypy TypedDict 참고  
  - https://mypy.readthedocs.io/en/stable/typed_dict.html  
  - https://typing.python.org/en/latest/spec/typeddict.html

이 외부 기준은 이번 저장소의 문제를 “그 기준에 딱 맞는지”를 판정하기 위해 쓴 것이 아니라, **현재 self-improvement/quality gate/supply-chain 운영이 어느 단계까지 와 있는지 해석하기 위한 참조축**으로 사용했습니다.
