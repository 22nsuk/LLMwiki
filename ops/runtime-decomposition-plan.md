# Runtime Decomposition Plan

이 문서는 외부 코드 리뷰 보고서의 6-1, 6-3, 8-1 항목을 현재 저장소 표면에 맞게 반영한 얇은 설계 메모다.

## 원칙

- 분해 기준은 기능 묶음이 아니라 상태 전이 경계다.
- 기존 공개 API와 테스트 표면은 유지하고, 오케스트레이터는 phase coordination만 남긴다.
- stricter static gate는 전체 surface에 즉시 확대하지 않고, 새로 분리한 helper surface에 먼저 opt-in 적용한다.

## Auto Improve

현재 1차 분해:

- `ops/scripts/auto_improve_runtime.py`
  - 세션 시작/루프 제어/phase orchestration 유지
- `ops/scripts/auto_improve_execution_runtime.py`
  - executor command materialization for codex-exec role dispatch
- `ops/scripts/auto_improve_execute_runtime.py`
  - execute/evaluate phase request shaping, experiment invocation, and outcome mapping
- `ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py`
  - iteration telemetry merge/write

다음 분해 우선순위:

1. `session_start`
2. `proposal_selection`
3. `routing_scaffold`
4. `execution_evaluation`
5. `iteration_persistence`
6. `session_finalize`

이번 단계에서는 execution, execute/evaluate, iteration persistence를 분리해, run-local artifact write, executor invocation shaping, experiment outcome mapping을 오케스트레이터 본문에서 떼어냈다. `auto_improve_execution_runtime.py`는 codex-exec 명령 문자열 생성에 집중하고, `auto_improve_execute_runtime.py`는 실제 execute/evaluate phase orchestration을 `ExecuteEvaluateRequest`로 받는다.

## Mechanism Review Candidate

현재 1차 분해:

- `ops/scripts/mechanism_review_candidate_runtime.py`
  - candidate identity, threshold evaluation, candidate assembly 유지
- `ops/scripts/mechanism_review_session_calibration_runtime.py`
  - session signal lookup, aggregation, priority calibration
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py`
  - outcome metrics preview, target/family aggregate, audit-only diagnostics

다음 분해 우선순위:

1. `candidate_rules`
2. `candidate_identity`
3. `report_builders`

이번 단계에서는 보고서가 지적한 calibration 축을 먼저 분리했다. candidate rule과 identity는 기존 파일 안에서도 경계가 비교적 명확하고, 현재 테스트가 직접 커버하는 핵심 계산 경로이므로 다음 단계 후보로 남긴다.

## Promotion Gate Mechanism

현재 1차 분해:

- `ops/scripts/promotion_gate_mechanism_runtime.py`
  - rule registry wiring, decision collapse, orchestration 유지
- `ops/scripts/promotion_gate_mechanism_state_runtime.py`
  - artifact input collection, equal-score/signoff decisions, promotion state 계산
- `ops/scripts/promotion_gate_mechanism_report_runtime.py`
  - promotion report input 정규화와 최종 report assembly

다음 분해 우선순위:

1. `state_evaluation`
2. `rule_registry`
3. `report_finalize`

이번 단계에서는 외부 리뷰와 observation artifact가 지적한 promotion gate의 첫 상태 전이 경계로 input/state 계산과 report assembly를 먼저 떼어냈다. 이렇게 하면 다음 단계에서 rule registry와 decision finalize를 별도 helper로 더 분해할 때 기존 외부 API를 유지한 채 오케스트레이터를 더 얇게 만들 수 있다.

## Static Preview

- `make ruff-strict-preview`는 `B`, `SIM`, `UP`, `I` 규칙을 새 helper runtime 표면에만 적용한다.
- preview 대상은 `ops/ruff-strict-preview-allowlist.txt`로 고정해, 상태 전이 분해가 끝난 helper surface를 파일/폴더 단위로 추가한다.
- `make mypy-strict-preview`는 `ops/mypy-strict-preview-allowlist.txt`를 source of truth로 삼아, 최근 변경이 잦고 이미 helper로 분해된 runtime 표면에만 stricter type flags를 단계적으로 확대한다.
- 이 타깃은 experimental branch 대신 export-tree에서도 재현 가능한 opt-in gate로 둔다.
- 저장소가 현재 Git metadata 없는 export tree일 수 있으므로, branch 기반 실험 대신 deterministic Make target을 canonical preview entrypoint로 사용한다.
