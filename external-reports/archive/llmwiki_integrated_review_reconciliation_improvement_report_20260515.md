# LLMwiki 통합 리뷰 재대조 및 실제 장기 자동 런 개선 보고서

- 작성일: 2026-05-15 KST
- 작성 언어: 한국어
- 파일명: `llmwiki_integrated_review_reconciliation_improvement_report_20260515.md`
- 요청 범위: 업로드된 통합 리뷰 `llmwiki_integrated_review_report_20260515.md`를 누락 없이 검토하고, 기존 리뷰 및 실제 원본 저장소 압축 파일 `LLMwiki.zip`과 대조하여 개선 방안을 정리한다.
- 기준 원본 ZIP SHA-256: `16279fcc3023537bf219ce90b862dd5b012c58a7eabff3f47fa4771027f3c797`
- 통합 리뷰 SHA-256: `342686594c03dc78a9b32f0b5a45516ea5668ec45559ed2161bb9c9b55f2c8d9`
- 기존 직접 산출 보고서 SHA-256: `dad1f1f0dc2f7cd61dd4aedff824ac36fa371f830c7e19b34561fd0dc40675c0`
- 기존 reconciled 보고서 SHA-256: `1fd30714fef78201a8c493e919860b7f3737fd511160cd856da5f49b3cb499a5`
- 운영 계약 ZIP SHA-256: `8104b09cf90c269165a79ac702cca02cea59ee0f399e48f64a619f6705f36092`

---

## 1. 최종 결론

업로드된 통합 리뷰의 큰 방향은 실제 파일과 대체로 일치한다. 특히 다음 네 결론은 현재 원본 ZIP 기준으로도 유지된다.

1. `LLMwiki.zip`은 배포용 source package가 아니라 full vault 원본 스냅샷이다.
2. 기존 `external-reports/llmwiki_review_reconciled_improvement_report.md`가 제기한 P0/P1 상당수는 현재 저장소에 구현되어 있다.
3. 현재 저장소는 `can_execute_trial=true`라서 bounded trial은 가능하지만, `can_promote_result=false`라서 promotion 가능한 장기 무인 런은 아직 허용되지 않는다.
4. 며칠 이상 자동 런을 실제로 안전하게 만들려면 기존 `auto_improve_loop`와 `codex_exec` 위에 goal contract, checkpoint/status/audit log, heartbeat, resume, canonical blocker promotion, release authority seal gate를 연결해야 한다.

다만 통합 리뷰는 몇 지점을 보정해야 한다.

- 일부 파일 경로가 실제 저장소와 다르다. 예를 들어 release smoke 구현 파일은 `ops/scripts/release/release_smoke.py`이고, readiness constants는 `ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py`다.
- `artifact-freshness-report.json` 자체는 원본 ZIP에서 `status=pass`, `operational_attention_issue_count=0`이지만, `auto-improve-readiness.json`은 별도로 `ops/reports/test-execution-summary.json` drift를 promotion blocker로 잡고 있다. 즉, “artifact freshness 전체 실패”가 아니라 “readiness가 선택한 artifact contract 계층의 promotion blocker”로 표현해야 한다.
- fresh temporary rerun에서 `make release-authority-sealed-preflight`는 실행 자체는 PASS했지만, 산출된 sealed rehearsal check의 핵심 상태는 `authority_preflight_status=blocked`, `status=fail`, `preflight_status=binding_pass_authority_blocked`다. 따라서 “preflight target이 돌지 않는다”가 아니라 “preflight는 실행 가능하지만 release authority가 아직 clean pass가 아니다”가 더 정확하다.
- 통합 리뷰의 Codex App Server `thread/goal/set`류 메서드 이름은 공식 문서만으로는 안정 API라고 단정하면 안 된다. 저장소 구현은 반드시 generated schema 또는 SDK/CLI feature detection을 거치는 adapter 형태여야 한다.
- integrated review가 제시한 신규 `codex_goal_*`, `goal_run_*`, negative ledger, remediation backlog 파일은 현재 원본 ZIP에는 아직 없다. 따라서 해당 항목은 “이미 구현”이 아니라 “장기 자동 런을 위해 구현할 신규 계층”으로 유지해야 한다.

---

## 2. 검토 입력과 실제 확인 범위

### 2.1 확인한 입력

| 입력 | 경로 | 판정 |
|---|---|---|
| 운영 계약 ZIP | `/mnt/data/Codex-Subagent-Orchestrator.zip` | 추출 후 root `AGENTS.md`와 관련 workflow skill 확인 |
| 원본 저장소 ZIP | `/mnt/data/LLMwiki.zip` | 추출 후 root `AGENTS.md`, `AGENTS.local.md`, `ops/README.md`, reports, scripts, Make targets 확인 |
| 통합 리뷰 | `/mnt/data/llmwiki_integrated_review_report_20260515.md` | 전체 내용 확인 |
| 직전 산출 보고서 | `/mnt/data/llmwiki_goal_run_readiness_improvement_report_20260515.md` | 비교 기준으로 확인 |
| 기존 reconciled 보고서 | `external-reports/llmwiki_review_reconciled_improvement_report.md` | 실제 원본 ZIP 내부 파일로 확인 |

### 2.2 원본 ZIP 구조 확인

| 항목 | 값 |
|---|---:|
| ZIP entry 수 | 2410 |
| 파일 수 | 2265 |
| 디렉터리 entry 수 | 145 |
| duplicate entry 수 | 0 |
| `.md` | 986 |
| `.json` | 459 |
| `.py` | 415 |
| `.pyc` | 234 |
| `ops/` 파일 | 767 |
| `tests/` 파일 | 180 |
| `external-reports/` 파일 | 68 |
| `runs/` 파일 | 263 |
| `raw/` 파일 | 446 |
| `wiki/` 파일 | 417 |
| `system/` 파일 | 71 |

판정: 통합 리뷰의 “현재 ZIP은 원본 full vault이고 source package count와 직접 비교하면 안 된다”는 해석은 맞다. 압축 관련 문제는 저장소의 release/source package 생성 경로를 확인하는 선에서 충분하며, 현 ZIP의 `runs/`, `external-reports/`, `ops/reports/`, `.pyc` 포함을 배포 ZIP 결함으로 보지 않는 것이 맞다.

---

## 3. 통합 리뷰 주장별 대조 판정

### 3.1 그대로 유지되는 주장

| 통합 리뷰 주장 | 실제 파일 대조 | 판정 |
|---|---|---|
| Strict preview 게이트가 구현되어 있다 | `mk/static.mk`, `ops/ruff-strict-preview-allowlist.txt`, `ops/mypy-strict-preview-allowlist.txt` 존재. fresh audit에서 `make static` PASS. | 유지 |
| Source-trace profile-aware 분류가 구현되어 있다 | `ops/scripts/core/source_trace_profile_runtime.py` 존재. | 유지 |
| Source-package lane guard가 구현되어 있다 | `ops/scripts/core/execution_lane_guard.py`, `ops/policies/execution-lanes.json`, `mk/release.mk` 관련 target 존재. | 유지 |
| Learning claim activation report가 구현되어 있다 | `ops/reports/learning_claim_activation_report.json`, schema 존재. | 유지 |
| Canonical session synopsis가 구현되어 있다 | `ops/reports/session-synopsis.json`, `ops/scripts/learning/session_synopsis.py` 존재. | 유지 |
| Auto-improve readiness가 분해되어 있다 | queue/learning/release_authority runtime 파일 존재. | 유지 |
| 현재 trial 가능, promotion 불가 | 원본 `ops/reports/auto-improve-readiness.json`에서 `can_execute_trial=true`, `can_promote_result=false`. | 유지 |
| Goal-native 실행 계층은 없다 | `set_goal`, `get_goal`, `update_goal`, `codex_goal`, `goal_contract`, `/goal`, `thread/goal` 문자열 검색 결과 source 내 0건. | 유지 |
| Negative learning standalone artifact와 remediation backlog는 없다 | `ops/reports/self-improvement-negative-lessons.json`, `ops/reports/remediation-backlog.json` 부재. | 유지 |

### 3.2 보정이 필요한 주장

| 통합 리뷰 표현 | 실제 확인 | 보정된 표현 |
|---|---|---|
| `release_smoke.py` 존재 | 실제 구현은 `ops/scripts/release/release_smoke.py`; `ops/scripts/release_smoke.py`는 부재. | path를 release package 하위로 수정 |
| `auto_improve_readiness_constants` 존재 | 실제 파일은 `ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py`. | `_runtime` suffix 반영 |
| `artifact-freshness-report.json` pass와 동시에 artifact freshness drift가 blocker | artifact freshness report 자체는 pass이며 stale/missing/schema invalid/operational attention count가 0. auto readiness가 별도 promotion blocker로 `test-execution-summary.json` drift를 들고 있음. | “artifact freshness 전체 실패”가 아니라 “readiness promotion contract drift”라고 표현 |
| `release-closeout-summary.json`은 `conditional_release` 상태 | top-level `status=pass`; `status_v2.status_classification=conditional_release`; `release_authority_status=conditional_pass`; `sealed_release_status=unsealed_distribution_not_provided`; `machine_release_allowed=false`. | legacy status와 v2 classification을 분리해서 표기 |
| `blocker_reason_count=4` | `status_v2.summary`에는 blocker_reason_count=4가 있으나 `blockers` 배열은 1개이고 `summary.blocker_count=1`. | reason id 4개와 blocker item 1개를 구분 |
| `make release-authority-sealed-preflight` 미확정 | fresh temporary audit에서 target은 29.50초에 return 0. 그러나 sealed rehearsal check는 authority blocked. | “명령 실행성은 확인, release authority clean pass는 미달”로 수정 |
| Codex App Server `thread/goal/set` 고정 | 공식 app-server 문서는 JSON-RPC와 generated schemas를 안내하지만, goal method 이름은 현재 저장소/문서 기준으로 안정 계약이라고 단정하지 않는다. | feature detection/adapter/generate schema 기반 구현으로 변경 |

### 3.3 실제 파일 존재 대조

| 항목 | 경로 | 현재 원본 ZIP 상태 |
|---|---|---|
| source_trace_profile_runtime | `ops/scripts/core/source_trace_profile_runtime.py` | 존재 |
| execution_lane_guard | `ops/scripts/core/execution_lane_guard.py` | 존재 |
| release_smoke 실제 경로 | `ops/scripts/release/release_smoke.py` | 존재 |
| release_smoke 통합 리뷰 표기 경로 | `ops/scripts/release_smoke.py` | 부재 |
| session_synopsis | `ops/scripts/learning/session_synopsis.py` | 존재 |
| auto_improve_readiness constants 실제 경로 | `ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py` | 존재 |
| auto_improve_readiness constants 통합 리뷰 표기 경로 | `ops/scripts/mechanism/auto_improve_readiness_constants.py` | 부재 |
| codex_exec_executor | `ops/scripts/core/codex_exec_executor.py` | 존재 |
| codex_goal_client 제안 파일 | `ops/scripts/core/codex_goal_client.py` | 부재 |
| codex_goal_executor 제안 파일 | `ops/scripts/core/codex_goal_executor.py` | 부재 |
| goal_run_contract 제안 파일 | `ops/scripts/mechanism/goal_run_contract.py` | 부재 |
| goal_run_status 제안 파일 | `ops/scripts/mechanism/goal_run_status.py` | 부재 |
| negative learning standalone 제안 artifact | `ops/reports/self-improvement-negative-lessons.json` | 부재 |
| remediation backlog 제안 artifact | `ops/reports/remediation-backlog.json` | 부재 |

---

## 4. Canonical report 상태: 원본 ZIP 기준

| Artifact | 원본 ZIP 내 상태 | 핵심 의미 |
|---|---|---|
| `ops/reports/auto-improve-readiness.json` | `can_execute_trial=True`, `can_promote_result=False` | trial은 가능, promotion은 차단 |
| `ops/reports/session-synopsis.json` | `status=attention` | next action은 “Trial only; do not promote” |
| `ops/reports/learning_claim_activation_report.json` | `status=pass`, `activation_status=blocked`, `claim_level=none` | learning-improved claim 금지 |
| `ops/reports/learning-delta-scoreboard.json` | `status=pass`, `improvement_claim_status=not_ready` | improvement claim not ready |
| `ops/reports/release-closeout-summary.json` | top-level `status=pass`, `release_authority_status=conditional_pass`, `sealed_release_status=unsealed_distribution_not_provided`, `machine_release_allowed=False` | legacy pass와 conditional/sealed blocker를 분리해서 읽어야 함 |
| `ops/reports/artifact-freshness-report.json` | `status=pass`, `operational_attention_issue_count=0` | freshness report 자체는 pass |
| `ops/reports/source-package-clean-extract.json` | `status=pass`, `ruff_status=pass` | source package clean extract evidence 존재 |
| `ops/reports/test-execution-summary-full.json` | `status=pass`, `represents_full_suite=True` | full suite summary evidence 존재 |
| `ops/reports/public-check-summary.json` | `status=pass` | public check summary evidence 존재 |
| `ops/reports/external-report-action-matrix.json` | `status=pass`, active action count `10` | external report action matrix는 현재 pass |

원본 ZIP 기준 promotion blocker는 두 개다.

1. `promotion_blocked_by_release_authority_preflight_failure`
   - 원본 이유: release authority sealed preflight report missing/unusable.
2. `promotion_blocked_by_artifact_contract_failure`
   - 원본 이유: `ops/reports/test-execution-summary.json` operational currentness drift.

fresh temporary audit 후에는 blocker 표현이 바뀐다. `make release-authority-sealed-preflight`와 `make auto-improve-readiness-report-body`를 실행하면 artifact contract blocker는 사라지고, release authority preflight blocker가 `distribution binding pass; release authority blocked`로 구체화된다. 따라서 장기 런 전 첫 작업은 “preflight 명령이 존재하는지 확인”이 아니라 “preflight outcome을 canonical하게 보존하고 release authority blocked 원인을 해소”하는 것이다.

---

## 5. Fresh temporary audit 결과

검증은 이전 추출 workspace의 `.venv`를 사용하여 수행했다. 현재 ChatGPT 실행 환경에는 장시간 무제한 백그라운드 실행 기능이 없고, 개별 Python tool call의 wall-time 한도가 있으므로 full multi-day run이나 전체 `check-serial`/`public-check-serial`을 끝까지 재실행하지는 않았다. 다만 핵심 gate와 targeted tests는 직접 실행했다.

| 명령 | 결과 | 시간 |
|---|---:|---:|
| `make artifact-freshness-check` | PASS | 7.77s |
| `make external-report-action-matrix` | PASS | 1.95s |
| `.venv/bin/python -m pytest -q tests/test_codex_exec_executor.py tests/test_auto_improve_queue_runtime.py` | FAIL(4) | 0.64s |
| `.venv/bin/python -m pytest -q tests/test_auto_improve_queue_runtime.py tests/test_auto_improve_route_scaffold_runtime.py tests/test_auto_improve_iteration_runtime.py` | PASS | 2.15s |
| `.venv/bin/python -m pytest -q tests/test_command_runtime.py tests/test_auto_improve_runtime.py` | PASS | 36.04s |
| `make static` | PASS | 1.97s |
| `make release-authority-sealed-preflight` | PASS | 29.50s |
| `make auto-improve-readiness-report-body` | PASS | 1.46s |
| `make session-synopsis` | PASS | 3.79s |

주의할 점:

- `tests/test_codex_exec_executor.py`는 실제 저장소에 없는 파일이므로 해당 시도는 파일 부재로 실패했다. 이는 저장소 품질 실패가 아니라 본 재검토 과정에서 잘못 지정한 테스트명이다.
- 이후 실제 존재하는 targeted tests인 `tests/test_auto_improve_queue_runtime.py`, `tests/test_auto_improve_route_scaffold_runtime.py`, `tests/test_auto_improve_iteration_runtime.py`, `tests/test_command_runtime.py`, `tests/test_auto_improve_runtime.py`는 모두 PASS했다.
- `make release-authority-sealed-preflight`는 return 0으로 실행 완료되었지만, tmp 산출물 `release-closeout-sealed-rehearsal-check.json`의 실제 상태는 `status=fail`, `authority_preflight_status=blocked`, `preflight_status=binding_pass_authority_blocked`였다. 이 target의 return 0은 “operator handoff용 expected blocked preflight까지 산출했다”는 의미로 읽어야 하며, promotion 허용 의미가 아니다.
- fresh rerun 후 `ops/reports/auto-improve-readiness.json`은 여전히 `can_execute_trial=true`, `can_promote_result=false`다.
- fresh rerun 후 learning claim activation은 `blocked_predicate_count`가 원본 3에서 4로 바뀌며 `post_seal_learning_claim_linkage`까지 명시한다. 장기 런 설계는 이처럼 rerun에 따라 blocker surface가 바뀌는 점을 audit log에 남겨야 한다.

---

## 6. 기존 reconciled 보고서 대비 현재 상태

기존 reconciled 보고서의 P0/P1은 “당시 기준으로 필요한 개선안”이었고, 현재 원본 ZIP은 상당 부분을 구현한 상태다.

| 기존 reconciled 항목 | 현재 판정 | 장기 런 관점의 남은 일 |
|---|---|---|
| Strict preview 복구 | 구현 완료 | 계속 gate로 유지 |
| Source-package wrong-lane 진단 강화 | 구현 완료 | 장기 run prompt에 lane guard 위반 중단 조건 추가 |
| Duplicate/self-description replay 차단 | 구현 완료 | source package smoke를 24시간 checkpoint에 포함 |
| `source_trace_profile_runtime.py` 도입 | 구현 완료 | public/source/full vault profile별 regression tests 유지 |
| `learning_claim_activation_report.json` 도입 | 구현 완료 | blocked 상태를 release/promotion 금지 조건으로 자동 반영 |
| 오케스트레이터 분해 시작 | 부분 구현 | 대형 release/test summary 및 goal executor 추가 시 더 분해 |
| Anti-slop 다축 ledger | 부분 구현/흡수 | standalone trend report로 승격 권장 |
| Negative learning ledger | 부분 구현/흡수 | standalone artifact 필요 |
| blocked → backlog 자동 전환 | 부분 구현/흡수 | `remediation-backlog.json`과 자동 승격 로직 필요 |
| Source package replay kit | 구현 완료 | long run periodic checkpoint에 결합 |
| Cross-eval ladder | 부분 구현 | promotion candidate gate에 명시 결합 |
| Canonical session synopsis | 구현 완료 | long run status와 상호 링크 필요 |

핵심 해석: “기존 backlog를 처음부터 다시 구현”할 필요는 없다. 이제 해야 할 일은 이미 구현된 evidence-first 표면을 Codex goal-style 장기 작업 루프와 연결하는 것이다.

---

## 7. Codex 장기 goal 실행 기준과 저장소 설계 함의

공식 Codex 문서 기준으로 `/goal`은 durable objective, verifiable stopping condition, checkpoint/progress log가 있는 long-running work에 적합하다. 또한 `/goal`은 experimental CLI feature로 안내되므로 저장소 구현이 특정 내부 명령이나 method name에 강하게 묶이면 안 된다. `codex exec`는 non-interactive scripting/CI에 적합하고, app-server는 JSON-RPC 기반 deep integration이며 자동화 작업에는 Codex SDK 사용을 권장한다.

따라서 저장소 개선은 다음 원칙을 따라야 한다.

1. `set_goal()`을 저장소 내부의 안정 adapter 함수로 정의한다.
2. adapter backend는 feature detection 기반이어야 한다.
3. 실제 Codex CLI `/goal`, SDK thread continuation, app-server generated schema, fake backend를 모두 같은 `GoalBackend` protocol 아래 둔다.
4. 외부 API/CLI가 goal feature를 제공하지 않는 환경에서는 `CodexExecContinuationBackend`가 동일 goal contract를 매 iteration prompt에 재주입하고, `get_goal` equivalent artifact를 로컬 JSON으로 관리한다.
5. “며칠 이상”은 무제한이 아니라 bounded wall-clock/proposal/failure budget으로 정의한다.
6. goal completion은 말이 아니라 artifact evidence로만 판단한다.

---

## 8. 현 저장소에서 며칠 런을 막는 실제 gap

### 8.1 Goal-native 계층 부재

현재 `auto_improve_loop.py`는 `--executor codex_exec`를 기본값으로 받는 얇은 CLI이며, `--goal-contract`, `--status-out`, `--audit-jsonl`, `--heartbeat-interval`, `--checkpoint-interval`이 없다. `ops/scripts/core/codex_exec_executor.py`는 실행 report contract는 갖지만 durable Codex goal lifecycle은 관리하지 않는다.

필요한 보강:

- `ops/scripts/core/codex_goal_client.py`
- `ops/scripts/core/codex_goal_executor.py`
- `ops/scripts/mechanism/goal_run_contract.py`
- `ops/scripts/mechanism/codex_goal_prompt.py`
- `ops/scripts/mechanism/goal_run_status.py`
- `ops/scripts/mechanism/auto_improve_goal_loop.py`
- `ops/schemas/codex-goal-contract.schema.json`
- `ops/schemas/codex-goal-executor-report.schema.json`

### 8.2 Preflight outcome의 canonical화 부족

원본 ZIP에서는 auto readiness가 preflight report missing/unusable로 blocker를 잡는다. fresh audit에서는 target이 실행되어 tmp report가 생기지만 canonical promotion 허용은 여전히 실패한다.

필요한 보강:

- `make release-authority-sealed-preflight` 결과를 `tmp/`에만 두지 않고, operator handoff용 canonical summary 또는 readiness input으로 승격하는 명령을 분리한다.
- expected-blocked preflight와 clean preflight를 다른 status vocabulary로 분리한다.
- return 0이 “promotion 가능”으로 오해되지 않게 report field와 Make target 이름을 명확히 한다.
- readiness가 tmp 산출물을 소비할 때, run status에 “tmp evidence from current session”인지 “canonical committed evidence”인지 표시한다.

### 8.3 Artifact freshness drift 표현의 이중성

원본 artifact freshness report 자체는 pass이지만, auto readiness는 selected contract summary drift를 promotion blocker로 잡는다.

필요한 보강:

- `auto-improve-readiness.json`의 blocker 이름을 `artifact_freshness`보다 구체적인 `selected_contract_currentness` 또는 `test_execution_summary_contract_drift`로 나눈다.
- `artifact-freshness-report.json` summary와 readiness promotion blocker가 충돌해 보이지 않도록 `diagnostics.artifact_contract_summary`를 별도 필드로 둔다.
- long run 종료 시 `make artifact-freshness-check`뿐 아니라 `make auto-improve-readiness-report-body`까지 반드시 묶는다.

### 8.4 장시간 관측성 부족

`command_runtime.py`는 timeout 결과는 상세히 남기지만 heartbeat, last output timestamp, artifact touch timestamp는 없다. 장기 런에서는 “조용히 정상 실행 중”과 “hang”을 구분해야 한다.

필요한 보강:

- `last_stdout_at`
- `last_stderr_at`
- `last_artifact_touch_at`
- `last_checkpoint_at`
- `heartbeat_interval_seconds`
- `quiet_seconds`
- `budget_limited` termination reason
- `resume_command`
- `resume_from_checkpoint`

### 8.5 Negative learning과 remediation backlog의 first-class artifact 부재

Learning claim activation 내부에는 negative pattern count가 있지만, 장기 자동 런이 “같은 실패를 반복하지 않기 위한 작업 큐”로 사용하기에는 부족하다.

필요한 보강:

- `ops/reports/self-improvement-negative-lessons.json`
- `ops/reports/remediation-backlog.json`
- session synopsis → remediation backlog 자동 승격
- 반복 blocker 2회 이상이면 auto-improve proposal로 바로 재시도하지 않고 backlog item으로 전환

### 8.6 Git worktree/branch 전제

업로드된 ZIP에는 `.git/`이 없다. 실제 Codex App/CLI 장기 런은 review/rollback/parallel thread 안전성을 위해 Git repository + worktree 기반으로 수행해야 한다.

필요한 보강:

- 장기 run preflight에 `git rev-parse --is-inside-work-tree` 확인 추가
- ZIP extraction mode이면 “trial only” 또는 “report-only”로 제한
- Codex app background worktree 사용 시 run id와 branch/worktree path를 `goal-run-status.json`에 기록

---

## 9. P0/P1/P2/P3 개선 Backlog

### P0 — 장기 trial 전에 반드시 처리

| ID | 개선 | 변경 대상 | 검증 | 완료 기준 |
|---|---|---|---|---|
| P0-1 | 통합 리뷰 경로/상태 표현 정정 | external report 또는 follow-up report | report action matrix | `release_smoke.py`, constants path, blocker count 표현 수정 |
| P0-2 | Goal contract schema 추가 | `ops/schemas/codex-goal-contract.schema.json` | schema tests | objective, non_goals, allowed_roots, required_evidence, budgets, stop_conditions 검증 |
| P0-3 | `set_goal()` adapter protocol 추가 | `ops/scripts/core/codex_goal_client.py` | `tests/test_codex_goal_client.py` | fake backend에서 set/get/update/pause/resume/clear pass |
| P0-4 | Codex backend feature detection | `codex_goal_client.py` | fake/generated-schema fixture test | CLI goal, SDK continuation, app-server schema, exec fallback 중 하나를 명시 선택 |
| P0-5 | Goal prompt generator 추가 | `ops/scripts/mechanism/codex_goal_prompt.py` | schema + snapshot test | `can_promote_result=false`일 때 promotion 금지 문구가 반드시 포함 |
| P0-6 | Auto-improve loop contract input 추가 | `auto_improve_loop.py`, runtime | existing tests + new contract tests | `--goal-contract`가 policy/CLI보다 큰 budget을 거부 |
| P0-7 | Run status/audit artifact 추가 | `goal_run_status.py`, schemas | status schema validation | `runs/goal-<id>/status.md`, `runs/goal-<id>/audit-log.jsonl`, `ops/reports/goal-run-status.json` 생성 |
| P0-8 | Sealed preflight canonical summary 추가 | `ops/scripts/release/`, `mk/release.mk` | `make release-authority-sealed-preflight` + readiness | expected blocked vs clean pass가 명확히 구분 |
| P0-9 | Freshness/readiness blocker 명칭 정교화 | readiness release authority runtime | readiness tests | artifact freshness pass와 selected contract drift가 혼동되지 않음 |
| P0-10 | 30분 bounded trial만 허용 | policy/run prompt | dry-run | promotion/release/learning claim 금지 |

### P1 — 6시간 ramp 전에 처리

| ID | 개선 | 변경 대상 | 완료 기준 |
|---|---|---|---|
| P1-1 | command heartbeat 추가 | `ops/scripts/core/command_runtime.py` | long command fake backend tests |
| P1-2 | shard targets 추가 | `mk/test.mk` 또는 `mk/mechanism.mk` | `make check-auto-improve-shard`, `make check-readiness-shard` PASS |
| P1-3 | auto-improve goal Make targets | `mk/mechanism.mk` | `auto-improve-goal-run/status/resume/finalize` 존재 |
| P1-4 | release preflight target naming 정리 | `mk/release.mk` | expected-blocked target와 clean-required target 분리 |
| P1-5 | session synopsis와 goal status 상호 링크 | `session_synopsis.py`, `goal_run_status.py` | synopsis에서 active goal id 표시 |
| P1-6 | `codex_exec_executor.py` report builder 분리 | core executor helpers | 기존 executor tests 비회귀 |
| P1-7 | module complexity report 보정 | structural/function budget scripts | 대형 모듈 압력 후보가 0으로만 나오지 않음 |

### P2 — 2~3일 run 전에 처리

| ID | 개선 | 변경 대상 | 완료 기준 |
|---|---|---|---|
| P2-1 | standalone negative learning ledger | `ops/reports/self-improvement-negative-lessons.json`, generator | repeated pattern count와 next action 존재 |
| P2-2 | remediation backlog artifact | `ops/reports/remediation-backlog.json`, schema | blocker → backlog 자동 승격 |
| P2-3 | repeated blocker stop rule | auto improve runtime | 같은 blocker 2회 이상이면 safe stop |
| P2-4 | Git worktree preflight | goal loop preflight | ZIP mode와 git mode가 구분됨 |
| P2-5 | periodic evidence checkpoint | goal loop | 6h/12h/24h 주기 command evidence |
| P2-6 | resume integration test | goal loop tests | budget_limited 후 resume가 같은 contract digest 사용 |

### P3 — promotion 전에 처리

| ID | 조건 | 완료 기준 |
|---|---|---|
| P3-1 | `can_promote_result=true` | `ops/reports/auto-improve-readiness.json` |
| P3-2 | sealed authority clean pass | clean-required preflight artifact |
| P3-3 | artifact freshness + readiness currentness clean | `artifact-freshness-check`, readiness no promotion blocker |
| P3-4 | full suite current pass | `test-execution-summary-full.json` fresh |
| P3-5 | public check pass | `public-check-summary.json` fresh |
| P3-6 | source package clean extract pass | clean source package report fresh |
| P3-7 | learning claim activation allowed | `claim_wording_allowed=true` only if intended |
| P3-8 | operator/human approval | explicit approval record |

---

## 10. 파일/모듈 복잡도 재확인

통합 리뷰의 module decomposition 후보는 방향이 맞다. 다만 현재 원본 ZIP에서 raw LOC는 통합 리뷰 표보다 약간 더 크다. 이는 공백/주석 포함 방식 또는 extraction 기준 차이일 수 있으므로, 장기 개선에서는 “정확한 숫자”보다 “분해 우선순위”를 보는 것이 안전하다.

| 파일 | 현재 raw LOC | 함수 수 | 클래스 수 | 긴 함수 상위 |
|---|---:|---:|---:|---|
| `ops/scripts/core/codex_exec_executor.py` | 846 | 33 | 11 | _materialize_prompt(91), build_execution_request(62), persist_execution_outcome(53), _build_executor_report(49) |
| `ops/scripts/learning/learning_claim_activation_report.py` | 683 | 27 | 1 | _anti_slop_preview_ledger(91), build_report(65), _blocked_predicates(64), _negative_learning_ledger(64) |
| `ops/scripts/mechanism/auto_improve_readiness_runtime.py` | 687 | 22 | 2 | load_readiness_inputs(98), render_readiness_report(91), _load_readiness_report_payloads(35), assess_execution_readiness(33) |
| `ops/scripts/mechanism/auto_improve_readiness_learning_runtime.py` | 767 | 22 | 2 | _learning_readiness_assessment(101), _build_loop_health_summary(62), _outcome_quality_shadow_signals(61), _learning_release_blockers(40) |
| `ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py` | 629 | 23 | 2 | _readiness_remediations(98), _checks(55), _same_eval_telemetry_summary(49), _readiness_next_action(45) |
| `ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py` | 693 | 16 | 0 | _release_gate_promotion_blockers(100), _artifact_contract_promotion_blockers(64), _release_batch_manifest_gate(58), _release_authority_preflight_promotion_blockers(55) |
| `ops/scripts/test/test_execution_summary.py` | 1818 | 74 | 3 | _deselection_lifecycle(108), build_aggregate_report(93), _aggregate_deselection_lifecycle(59), _render_test_execution_summary(56) |
| `ops/scripts/release/release_closeout_summary.py` | 2372 | 69 | 11 | _evaluate_test_summary(106), _source_tree_coherence(90), _evaluate_auto_improve(73), _accepted_risk_count_by_scope(71) |

분해 원칙:

1. goal 계층 추가 전에 기존 대형 파일을 무리하게 대분해하지 않는다.
2. P0에서는 `codex_goal_client`, `goal_run_contract`, `goal_run_status`처럼 새 책임을 별도 파일로 추가해 기존 파일 변경을 최소화한다.
3. P1 이후 release/test summary의 decision kernel과 rendering/IO를 분리한다.
4. `function-budget-refactor-proposals.json`이 proposal 0을 내는 현상은 “문제가 없다”는 뜻이 아니라 “현재 detector가 대형 모듈 압력을 refactor proposal로 승격하지 못한다”는 신호로 본다.

---

## 11. `set_goal()`/goal adapter 설계안

### 11.1 저장소 내부 안정 interface

```python
@dataclass(frozen=True)
class GoalSpec:
    objective: str
    success_criteria: list[str]
    non_goals: list[str]
    allowed_roots: list[str]
    required_evidence: list[str]
    stop_conditions: list[str]
    max_proposals: int
    wall_clock_budget_seconds: int
    max_consecutive_failures: int
    checkpoint_interval_seconds: int
    promotion_allowed: bool

class CodexGoalBackend(Protocol):
    def set_goal(self, thread_id: str, spec: GoalSpec) -> GoalState: ...
    def get_goal(self, thread_id: str) -> GoalState: ...
    def update_goal(self, thread_id: str, patch: GoalPatch) -> GoalState: ...
    def pause_goal(self, thread_id: str, reason: str) -> GoalState: ...
    def resume_goal(self, thread_id: str) -> GoalState: ...
    def clear_goal(self, thread_id: str, reason: str) -> GoalState: ...
```

중요: 이 interface가 저장소의 안정 계약이고, 외부 Codex 구현은 backend detail이다.

### 11.2 Backend 우선순위

| Backend | 사용 조건 | 주의점 |
|---|---|---|
| `CodexCliGoalBackend` | CLI `/goal` feature가 명시적으로 활성화된 경우 | experimental feature이므로 version/config detection 필수 |
| `CodexSdkThreadBackend` | Codex SDK가 설치되어 thread continuation이 가능한 경우 | automation에는 SDK 권장 문서와 가장 잘 맞음 |
| `CodexAppServerBackend` | generated schema에서 goal method가 확인되는 경우 | method name을 하드코딩하지 말고 generated schema 기반 |
| `CodexExecContinuationBackend` | 위 backend가 없고 `codex exec`만 가능한 경우 | goal contract를 매 iteration prompt에 재주입하고 local status를 source of truth로 사용 |
| `FakeGoalBackend` | tests | 네트워크/CLI 없이 deterministic state transition 검증 |

### 11.3 `set_goal()`에 넣을 목표는 code가 아니라 contract artifact에서 생성

권장 위치:

```text
ops/templates/goal-contracts/auto-improve-trial.yaml
ops/templates/goal-contracts/auto-improve-ramp.yaml
ops/templates/goal-contracts/auto-improve-multiday.yaml
runs/goal-<id>/goal-contract.json
runs/goal-<id>/status.md
runs/goal-<id>/audit-log.jsonl
ops/reports/goal-run-status.json
```

---

## 12. 실제 2~3일 run profile 권장안

### 12.1 30분 bounded trial

전제:

- `make static` PASS
- `make artifact-freshness-check` PASS
- `make auto-improve-readiness-report-body` PASS
- `can_execute_trial=true`
- `can_promote_result=false`이면 promotion 금지

실행:

```bash
.venv/bin/python -m ops.scripts.mechanism.auto_improve_loop \
  --vault . \
  --policy ops/policies/wiki-maintainer-policy.yaml \
  --max-proposals 1 \
  --max-minutes 30 \
  --max-consecutive-failures 1 \
  --executor codex_exec
```

완료 기준:

- proposal 1개 이하
- allowed roots 위반 없음
- status/audit log 존재
- readiness/session synopsis 갱신
- promotion 금지 유지

### 12.2 6시간 ramp

전제:

- 30분 trial 성공
- 반복 blocker 없음
- allowed root 위반 없음

실행:

```bash
.venv/bin/python -m ops.scripts.mechanism.auto_improve_loop \
  --vault . \
  --policy ops/policies/wiki-maintainer-policy.yaml \
  --max-proposals 6 \
  --max-minutes 360 \
  --max-consecutive-failures 2 \
  --executor codex_exec
```

추가 조건:

- 각 proposal 후 `make static`
- 2 proposal마다 targeted pytest shard
- 6시간 종료 시 readiness/session synopsis 재생성
- release/promotion 금지

### 12.3 2일 candidate long run

전제:

- 6시간 ramp 안정
- `goal-run-status.json`과 `audit-log.jsonl` 구현 완료
- preflight expected-blocked/clean-required vocabulary 정리
- repeated blocker backlog 승격 구현

실행:

```bash
.venv/bin/python -m ops.scripts.mechanism.auto_improve_goal_loop \
  --vault . \
  --goal-contract runs/goal-<id>/goal-contract.json \
  --max-proposals 24 \
  --max-minutes 2880 \
  --max-consecutive-failures 3
```

주기:

- 모든 proposal 후: `make static`
- 2 proposal마다: auto-improve targeted pytest shard
- 6시간마다: `make artifact-freshness-check`, `make auto-improve-readiness-report-body`, `make session-synopsis`
- 12시간마다: `make ruff-strict-preview`, `make mypy-strict-preview`
- 24시간마다: source package clean extract 또는 release smoke equivalent
- 종료 시: promotion candidate 조건을 만족하지 못하면 “candidate only”로 closeout

### 12.4 3일 확장

3일 확장은 2일 candidate long run이 다음 조건을 만족할 때만 별도 승인으로 수행한다.

- 연속 실패 0~1회
- blocker 반복 없음 또는 모두 backlog 승격
- artifact freshness/readiness가 주기적으로 clean
- audit log 누락 없음
- source package/public/release evidence 비회귀

확장 인자:

```bash
--max-proposals 36
--max-minutes 4320
--max-consecutive-failures 3
```

---

## 13. 중단 조건과 금지 조건

### 13.1 즉시 중단 조건

- allowed roots 밖 변경이 필요함
- release/promotion blocker를 우회해야만 진행 가능함
- `can_promote_result=false`인데 release/promotion/learning-improved claim이 필요해짐
- 같은 blocker가 2회 이상 반복되었는데 backlog 승격이 불가능함
- command heartbeat가 끊기고 artifact touch도 없음
- status/audit artifact를 쓸 수 없음
- ZIP extraction mode에서 Git worktree 전제가 필요한 변경을 하려 함

### 13.2 금지 조건

- test 삭제로 통과 만들기
- release authority vocabulary 약화
- `claim_wording_allowed` 우회
- allowed root 확장
- source package exclusion 완화
- generated artifact를 수동 편집해 freshness만 맞추기
- full vault/private corpus를 public surface에 복사
- `status=pass`만 보고 v2 conditional/sealed blocker를 무시

---

## 14. 통합 리뷰를 반영한 최종 개선 순서

가장 안전한 순서는 다음이다.

1. 통합 리뷰의 경로/상태 표현 오류를 follow-up report 또는 action matrix item으로 정정한다.
2. `goal-contract` schema와 prompt generator를 추가한다.
3. fake backend 기반 `set_goal()` adapter를 추가하고 tests로 고정한다.
4. 실제 Codex backend는 SDK/CLI/app-server generated schema를 feature detection으로 선택한다.
5. `auto_improve_loop`에 `--goal-contract`를 추가하되 기존 `codex_exec` path는 유지한다.
6. `goal-run-status.json`, `runs/goal-<id>/status.md`, `audit-log.jsonl`을 추가한다.
7. release-authority preflight 산출물의 expected-blocked/clean-required 의미를 분리한다.
8. selected contract currentness blocker를 artifact freshness pass와 혼동되지 않게 분리한다.
9. negative learning ledger와 remediation backlog를 first-class artifact로 만든다.
10. 30분 bounded trial을 실행한다.
11. 6시간 ramp를 실행한다.
12. 2일 candidate long run을 실행한다.
13. promotion은 오직 `can_promote_result=true`와 sealed clean pass 이후에만 검토한다.

---

## 15. 최종 판정

통합 리뷰는 기존 보고서와 실제 파일을 대체로 잘 종합했지만, 이번 재대조 결과 “실제 런을 며칠 이상 진행할 수 있게 만드는 보고서”로 쓰려면 다음 네 가지 보강이 특히 중요하다.

1. **Goal-native 구현은 아직 없다.** 통합 리뷰의 `codex_goal_*` 항목은 현재 상태 설명이 아니라 구현 backlog다.
2. **release-authority preflight는 실행 가능하지만 clean pass가 아니다.** fresh audit 결과가 이를 더 분명하게 보여준다.
3. **artifact freshness 표현을 정교화해야 한다.** freshness report pass와 readiness promotion blocker를 같은 층위로 쓰면 operator가 오판할 수 있다.
4. **Codex goal API는 adapter로 감싸야 한다.** CLI `/goal`은 experimental이고, app-server는 generated schema 기반으로 다뤄야 하며, 자동화에는 SDK 또는 `codex exec` fallback까지 포함해야 한다.

따라서 다음 산출물의 구현이 끝나기 전에는 2~3일 자동 개선 런을 “promotion-capable autonomous run”으로 부르면 안 된다.

- `codex-goal-contract.schema.json`
- `codex_goal_client.py`
- `codex_goal_executor.py`
- `goal_run_status.py`
- `goal-run-status.json`
- `audit-log.jsonl`
- `self-improvement-negative-lessons.json`
- `remediation-backlog.json`
- clean-required sealed preflight report
- selected contract currentness gate

이들이 갖춰지면 현재 저장소의 기존 evidence-first runtime을 바꾸지 않고도, bounded trial → 6시간 ramp → 2일 candidate → 3일 확장 → promotion candidate 검증으로 안전하게 승격할 수 있다.

---

## 부록 A. 직접 확인한 주요 경로

- `AGENTS.md`
- `AGENTS.local.md`
- `ops/README.md`
- `external-reports/llmwiki_review_reconciled_improvement_report.md`
- `ops/reports/auto-improve-readiness.json`
- `ops/reports/session-synopsis.json`
- `ops/reports/learning_claim_activation_report.json`
- `ops/reports/learning-delta-scoreboard.json`
- `ops/reports/release-closeout-summary.json`
- `ops/reports/artifact-freshness-report.json`
- `ops/reports/source-package-clean-extract.json`
- `ops/reports/release-smoke-report.json`
- `ops/reports/external-report-action-matrix.json`
- `ops/scripts/mechanism/auto_improve_loop.py`
- `ops/scripts/core/codex_exec_executor.py`
- `ops/scripts/core/command_runtime.py`
- `ops/scripts/core/execution_lane_guard.py`
- `ops/scripts/core/source_trace_profile_runtime.py`
- `ops/scripts/release/release_smoke.py`
- `mk/release.mk`
- `mk/static.mk`
- `Makefile`

## 부록 B. 장기 run용 최소 goal 문안

```text
LLMwiki 저장소에서 bounded long-horizon auto-improve candidate run을 수행하라.

절대 원칙:
- promotion, release, learning-improved claim은 can_promote_result=true와 sealed authority clean pass 전까지 금지한다.
- allowed roots는 ops/, tests/, system/system-log.md로 제한한다.
- 모든 변경은 command evidence, changed file list, status update, audit log entry와 함께 남긴다.
- 같은 blocker가 2회 이상 반복되면 계속 재시도하지 말고 remediation backlog로 승격한다.
- artifact freshness pass와 auto-improve readiness promotion blocker를 모두 확인한다.
- status=pass만 보고 release_status_v2 conditional/sealed blockers를 무시하지 않는다.

시작 전:
make static
make artifact-freshness-check
make auto-improve-readiness-report-body
make session-synopsis
make release-authority-sealed-preflight

실행:
최초 30분 trial은 max-proposals=1, max-minutes=30, max-consecutive-failures=1로 제한한다.
trial이 안정적이면 별도 승인된 6시간 ramp로만 확장한다.
2~3일 run은 goal-run-status, audit-log, heartbeat, resume, remediation backlog가 구현된 뒤에만 진행한다.

중단:
- allowed root 위반 필요
- promotion blocker 우회 필요
- heartbeat/audit/status 기록 불가
- release authority clean pass 없이 promotion 필요
- 반복 blocker backlog 승격 불가

완료:
- candidate result만 보고한다.
- can_promote_result=false이면 성공해도 promotion 완료라고 쓰지 않는다.
```

## 부록 C. 외부 기준 검토 메모

- Codex `/goal`은 durable objective와 verifiable stopping condition을 가진 long-running work에 적합한 실험적 CLI feature로 문서화되어 있다.
- Codex `exec`는 non-interactive scripting/CI 자동화에 적합한 subcommand로 문서화되어 있다.
- Codex app-server는 JSON-RPC 기반 deep integration surface이며, 자동화 jobs/CI에는 SDK 사용을 권장한다.
- 따라서 본 저장소는 `set_goal()`을 외부 API에 직접 결합하지 말고, CLI/SDK/app-server/fallback backend를 감싸는 local adapter로 구현해야 한다.
