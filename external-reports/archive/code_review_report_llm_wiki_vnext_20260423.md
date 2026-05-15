# LLM Wiki vNext 코드 검토 및 개선 보고서
## 1. 검토 범위 및 방법
- 업로드된 `LLM Wiki vNext(21).zip`의 공개 가능한 코드/설정/문서 영역을 기준으로 점검했습니다.
- 주요 대상: `ops/`, `tests/`, `tools/`, `.github/workflows/`, 루트 문서/설정 파일.
- 분석 방식: 구조/문서 검토, AST 기반 정적 지표 수집, 핵심 경로 샘플 점검, 선택적 pytest 실행.
- 원본 압축에 매우 긴 파일명이 포함되어 전체 무손실 압축 해제는 환경상 제약이 있었으나, 코드 검토 대상인 핵심 공개 surface는 선별 추출하여 분석했습니다.
## 2. 전체 판단
이 저장소는 **실험성 스크립트 묶음**이 아니라, 이미 상당한 수준의 **운영형 meta-maintainer runtime**으로 진화한 상태입니다. 특히 테스트 수, 타입 힌트, schema/정책/리포트 산출물 중심의 설계는 성숙한 편입니다. 다만 현재의 강점이 곧 리스크이기도 합니다. 자동개선, promotion, validation, provenance, supply-chain, observability가 모두 한 저장소에서 촘촘히 연결되면서, 일부 중심 모듈에 **복잡도와 책임이 집중**되고 있습니다. 따라서 “기능이 없는 상태”가 아니라, **다음 성숙도 단계로 가기 위해 구조적 분해와 anti-slop 장치의 고도화가 필요한 상태**라고 보는 것이 정확합니다.
## 3. 핵심 지표 요약
- Python 파일 수: **255개**
- 함수 수: **2128개**
- 클래스 수: **267개**
- 인자 타입 힌트 완비 비율(rough): **99.3%**
- 반환 타입 명시 비율(rough): **99.9%**
- `bare except` 수: **0건**
- `except Exception` 수: **12건**
- `subprocess.run/Popen/os.system` 사용 수: **8건**
- direct-script fallback(`if __package__ in (None, "")`) 사용 파일 수: **43개**
- `validate_or_raise(...)` 사용 파일 수: **33개**
- `@dataclass` 사용 횟수(rough): **93회**
- 테스트 파일 수: **107개**
- 런타임/도구 파일 수: **148개**
### 선택 실행 테스트 결과
- 실행 대상: `--capture=sys, -q, tests/test_ci_workflow_static.py, tests/test_release_workflow_static.py, tests/test_import_fallback_contract.py, tests/test_script_module_surface_contract.py`
  - 종료 코드: **0**
  - 출력 요약:

```text
....uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu.uuuuuuuuuuuuuuuuuuuuuuuuu [ 42%]
uuuuuuuuuuuuuuuuu.....uuuuuuuuuuuuuuu.uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu [ 85%]
uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu [ 85%]
uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu.uuuuuuuuuuuuuuu.uuuuuuuuuuuuuuu.     [100%]
```
- 실행 대상: `--capture=sys, -q, tests/test_auto_improve_readiness_runtime.py, tests/test_auto_improve_queue_runtime.py, tests/test_auto_improve_iteration_runtime.py, tests/test_auto_improve_session_runtime.py`
  - 종료 코드: **0**
  - 출력 요약:

```text
.................                                                        [100%]
```
## 4. 잘하고 있는 점
- **높은 타입 힌트 일관성**
- **매우 넓은 테스트 커버리지 표면**
- **schema 기반 계약 검증 활용**
- **무분별한 bare except 부재**
- **운영 계약의 명시성**: `README.md`, `ARCHITECTURE.md`, `AGENTS.md`, `ops/README.md`가 public/private 경계, 역할, 루프, 검증 절차를 비교적 명확히 기술합니다.
- **정책/스키마/리포트 중심 설계**: 단순 스크립트 실행이 아니라 정책 파일, JSON Schema, readiness/report 산출물 중심으로 runtime을 통제합니다.
- **실패를 기록 가능한 형태로 만드는 문화**: observability, promotion decision trends, outcome metrics, provenance 같은 산출물이 존재해 자기개선 루프를 “증거 기반”으로 운영하려는 의도가 분명합니다.
- **테스트가 구현을 끌고 가는 구조**: 테스트 파일 규모가 매우 크고, 단순 smoke 수준을 넘어서 contract/static/public boundary까지 다룹니다.
## 5. 자가 개선(self-improvement) 성숙도 평가
### 종합 등급: **4/5 (상당히 높음, 하지만 완전 자율 운영 단계는 아님)**
이 저장소의 자기개선 성숙도는 다음 이유로 높게 평가할 수 있습니다.
- 개선 대상이 “모델 출력 품질”에 머무르지 않고 **메커니즘 자체**(routing, proposal, promotion, validation, observability)를 대상으로 설정되어 있습니다.
- 개선 실험 전후를 비교할 수 있는 **report artifact**와 **gate**가 존재합니다.
- promotion/discard, readiness, scope freeze, signoff 등 **보수적 운영 제어장치**가 이미 들어가 있습니다.
- `auto_improve_*`, `mechanism_*`, `promotion_*`, `run_mechanism_experiment*` 계열이 분화되어 있어, 적어도 개념 수준에서는 루프 단계가 분리되어 있습니다.

그러나 아직 5/5가 아닌 이유도 분명합니다.
- 핵심 오케스트레이션 파일과 runtime 파일 몇 곳에 책임이 많이 몰려 있습니다. 자기개선 시스템은 보통 **복잡도 자체가 거짓 양성 개선**을 낳기 쉬운데, 지금은 그 위험이 시작되는 구간입니다.
- CLI 경계에서의 broad exception, direct-script fallback 반복, 긴 함수 존재는 “현실적인 운영 편의”라는 장점이 있지만, 동시에 **비정상 경로를 표준 경로처럼 누적**시키는 신호이기도 합니다.
- 관찰/리포트는 풍부하지만, 일부 모듈은 관찰과 실행과 정책 판단이 같은 파일 근처에 엮여 있어, 향후 회귀 원인 분리가 어려워질 수 있습니다.
### 세부 점수
| 항목 | 평가 | 근거 |
|---|---:|---|
| 테스트/검증 문화 | 5/5 | 테스트 파일 107개, static/public/contract 테스트 존재 |
| 타입/정적 규율 | 5/5 | 타입 힌트 비율 매우 높음 (99.3% / 99.9%) |
| 운영 안전장치 | 4/5 | readiness, promotion, signoff, schema gate 존재 |
| 구조적 단순성 | 2.5/5 | 일부 중심 런타임 파일과 함수가 길고 결합도 높음 |
| 완전 자율 개선 준비도 | 3.5/5 | 충분한 근거는 있으나 책임 집중과 실행 경계 반복이 남아 있음 |
## 6. anti-slop 관점 진단
여기서 말하는 anti-slop은 “그럴듯한 산출물은 많지만, 실제로는 품질과 인과가 불분명한 상태”를 방지하는 관점입니다. 이 기준에서 보면 현재 코드는 **중상급 방어선**을 갖추고 있습니다.

### 긍정 신호
- **schema와 policy가 존재**하여, 출력 형식이 단순 자유형 텍스트로 방치되지 않습니다.
- **promotion/discard 같은 이산 결정 구조**가 있어, 개선 제안이 자동으로 항상 채택되지 않습니다.
- **observability/report artifact**가 있어, “좋아진 것처럼 보이는 변화”를 기록 가능한 형태로 검토할 수 있습니다.
- **public/private boundary hygiene**를 별도 계약으로 관리해, 데이터와 코드 표면을 섞지 않으려는 의식이 있습니다.

### 아직 slop이 스며들 수 있는 지점
- **리포트 과잉, 실행 근거 분산**: 보고서/산출물은 많지만, 운영자가 “이 산출물 중 무엇이 결정적 근거인가”를 빠르게 파악하기 어렵다면 slop은 문서화된 형태로 축적됩니다.
- **긴 오케스트레이션 함수**: 함수 길이 100줄 이상인 핵심 런타임 함수가 다수 존재합니다. 자기개선 루프에서 이런 함수는 정상/예외/기록/판단이 뒤섞여 **의도치 않은 암묵 규칙**을 만듭니다.
- **fallback의 제도화**: direct script fallback 패턴이 43개 파일에 반복됩니다. 이는 배포/실행 편의에는 좋지만, 장기적으로는 패키지 경계를 흐리고 “어떤 진입 방식이 정식 경로인지”를 약화시킬 수 있습니다.
- **광범위한 `except Exception`**: 총 12건이 보입니다. 많은 경우 CLI 경계 방어 목적이라 합리적이지만, anti-slop 관점에서는 예외 분류가 충분히 구체적이지 않으면 문제의 실제 원인이 flatten될 수 있습니다.
- **실행기와 정책의 인접 결합**: executor, promotion, workspace, observability가 서로 근접해 있어, 잘못 다루면 개선 실험의 결과와 런타임의 자체 bookkeeping이 서로를 오염시킬 수 있습니다.
### 현재 anti-slop 상태 요약
**“방어 장치는 강하지만, 구조적 복잡도가 올라가면서 slop이 ‘문서화된 정교함’의 형태로 침투할 위험이 커지는 단계”**입니다. 즉, 지금 문제는 허술함보다도 **복잡성이 품질처럼 보이기 시작할 가능성**에 더 가깝습니다.
## 7. 구체적 우려 지점
### 7.1 큰 런타임 파일과 긴 함수
LOC 기준 상위 런타임 파일 일부는 다음과 같습니다.
- `ops/scripts/raw_intake_promotion_runtime.py` — 789 LOC (874 lines)
- `ops/scripts/filesystem_runtime.py` — 771 LOC (876 lines)
- `ops/scripts/observability_artifacts_runtime.py` — 767 LOC (847 lines)
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py` — 673 LOC (741 lines)
- `ops/scripts/mechanism_run_workspace_runtime.py` — 660 LOC (708 lines)
- `ops/scripts/policy_validation_runtime.py` — 658 LOC (726 lines)
- `ops/scripts/mechanism_run_validation_runtime.py` — 617 LOC (684 lines)
- `ops/scripts/codex_exec_executor.py` — 606 LOC (687 lines)
- `ops/scripts/mechanism_review_candidate_runtime.py` — 606 LOC (679 lines)
- `ops/scripts/wiki_lint_review_runtime.py` — 587 LOC (658 lines)

함수 길이 기준 상위 런타임 함수 일부는 다음과 같습니다.
- `tools/manual_mutate_auto_improve_timeout_telemetry.py::main` — 206 lines
- `ops/scripts/wiki_eval.py::evaluate` — 179 lines
- `tools/manual_mutate_auto_improve_decision_record_fallback.py::main` — 172 lines
- `ops/scripts/auto_improve_readiness_runtime.py::build_readiness_report` — 141 lines
- `ops/scripts/promotion_gate_mechanism_state_runtime.py::build_mechanism_promotion_state` — 138 lines
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py::build_outcome_metrics_calibration_diagnostics` — 132 lines
- `ops/scripts/mechanism_review_history_runtime.py::load_mechanism_run_snapshots` — 127 lines
- `ops/scripts/mechanism_review_session_calibration_runtime.py::session_calibration_summary` — 126 lines
- `ops/scripts/structural_complexity_budget_runtime.py::build_report` — 124 lines
- `ops/scripts/policy_validation_runtime.py::validate_policy_safety_invariants` — 120 lines
- `ops/scripts/mutation_proposal_runtime.py::build_report` — 117 lines
- `ops/scripts/mechanism_run_scaffold_templates_runtime.py::starter_seed_text` — 116 lines
이 자체가 곧 문제는 아니지만, 오케스트레이션/판단/직렬화/예외처리/리포팅이 한 함수 내부에서 함께 처리되면 회귀 시 영향 범위가 커집니다.
### 7.2 import 및 책임 결합도
import 개수 기준 상위 런타임 파일 일부는 다음과 같습니다.
- `ops/scripts/supply_chain_artifacts.py` — import 32개
- `ops/scripts/wiki_lint.py` — import 32개
- `ops/scripts/auto_improve_runtime.py` — import 28개
- `ops/scripts/supply_chain_benchmark.py` — import 27개
- `ops/scripts/supply_chain_artifact_model.py` — import 25개
- `ops/scripts/cyclonedx_sbom.py` — import 24개
- `ops/scripts/openvex_draft.py` — import 23개
- `ops/scripts/release_smoke.py` — import 22개
- `ops/scripts/sbom_export_mapping.py` — import 21개
- `ops/scripts/supply_chain_provenance.py` — import 21개
특히 auto-improve, executor, validation, promotion 계열은 도메인 로직보다 **조율자 역할**이 커지고 있습니다. 이런 파일은 기능 추가보다 **phase object / command object / immutable event** 중심으로 재분해하는 것이 장기 유지보수에 유리합니다.
### 7.3 예외 처리 경계
- `except Exception` 총 12건은 대부분 CLI boundary 방어로 보입니다.
- 이 패턴은 사용자 경험에는 친절하지만, 장애 분석에는 불리할 수 있습니다. 최소한 `UsageError`, `PolicyError`, `SchemaValidationError`, `ExecutorError`, `WorkspaceMutationError`처럼 분류된 예외 체계와 exit code 매핑을 더 엄격히 두는 편이 좋습니다.
### 7.4 실행 환경 가정
- 선택 테스트 실행 중 캐시 디렉터리 쓰기 권한과 같은 환경성 경고가 관찰될 수 있습니다. 이는 코드 버그라기보다도, 저장소가 여전히 **실행 환경의 정상성**을 어느 정도 가정하고 있다는 신호입니다.
- 자기개선 루프는 실험 환경 편차에 취약하므로, cache/temp/artifact 디렉터리 정책을 더 명시적으로 통제하는 편이 안전합니다.
## 8. 개선 우선순위
### P0 — 즉시 권장
1. **긴 오케스트레이션 함수 분해**
   - 대상 후보: `ops/scripts/wiki_eval.py::evaluate`, `ops/scripts/auto_improve_readiness_runtime.py::build_readiness_report`, `ops/scripts/promotion_gate_mechanism_state_runtime.py::build_mechanism_promotion_state`, `ops/scripts/run_mechanism_experiment_runtime.py::_run_workspace_experiment_phase` 등.
   - 기준: 한 함수에서 판단/부수효과/직렬화/출력경로 결정을 동시에 하지 않도록 분해.
2. **예외 taxonomy 정리**
   - broad exception을 얇은 CLI boundary 하나로만 몰고, 내부는 도메인 예외로 세분화.
3. **정식 진입점 일원화**
   - direct-script fallback을 무조건 제거하라는 뜻은 아니지만, “지원되는 실행 경로”와 “호환용 fallback”을 문서/테스트/코드에서 더 명확히 분리해야 합니다.
### P1 — 다음 단계
4. **관찰 산출물의 계층화**
   - report artifact가 많은 만큼, 운영자가 가장 먼저 봐야 하는 canonical summary를 1~2개로 줄이고 나머지는 drill-down으로 두는 구조가 좋습니다.
5. **복잡도 budget을 함수/phase 단위로 적용**
   - 현재는 리포트 생성과 구조 예산이 보이지만, 핵심 phase 함수에 대한 line/branch/dependency budget을 더 직접적으로 거는 것이 효과적입니다.
6. **workspace mutation과 observability 분리 강화**
   - 실행 결과를 기록하는 코드와 실제 workspace를 변형하는 코드를 더 엄격히 분리하면, 자기개선 루프의 인과 추적이 쉬워집니다.
### P2 — 중장기
7. **상태기계(state machine) 기반 문서화/구현 정합성 강화**
   - auto-improve / promotion / experiment run의 상태 전이를 코드와 문서에서 동일한 state model로 고정하면 회귀 억제가 쉬워집니다.
8. **anti-slop scorecard 추가**
   - “보고서 수가 많다”가 아니라, 결정 근거의 선명도/중복률/미결정 경고의 잔존률/실패 원인 분류 적중률 같은 지표를 별도 scorecard로 두는 것을 권장합니다.
## 9. 추천 리팩터링 방향
### 방향 A — Phase object 도입
- 현재도 `*Dependencies`, `*Request`, `*Result` 패턴이 일부 보입니다. 이 방향은 좋습니다.
- 이를 더 밀어붙여, 각 phase를 **입력-판단-출력**이 분리된 작은 객체/함수 집합으로 재구성하면 테스트 단위와 회귀 원인이 더 선명해집니다.
### 방향 B — Domain event 명시화
- `append_ledger_event`, runtime event logging, outcome metrics가 이미 있으므로, 이벤트 모델을 더 중심에 두면 좋습니다.
- “무엇을 했다”보다 “무엇이 왜 결정되었는가”를 이벤트 수준에서 표준화하면 anti-slop에 강해집니다.
### 방향 C — canonical execution contract 강화
- direct execution, module execution, Make target execution 사이의 계약을 문서와 테스트에서 더 일관되게 강제하십시오.
- 자기개선 시스템은 실행 경로가 여러 개일수록 subtle drift가 쌓이기 쉽습니다.
## 10. 결론
현재 코드는 **이미 성숙한 실험 운영체계의 형태**를 상당 부분 갖췄습니다. 특히 테스트, 타입, 정책/스키마, 증거 산출물 중심 설계는 매우 강합니다. 반면, 바로 그 성숙함 때문에 복잡도와 결합도가 높아지고 있고, 이는 향후 slop이 “정교한 운영 절차”라는 모습으로 스며드는 출입구가 될 수 있습니다.

따라서 다음 단계의 핵심은 기능 추가가 아니라 **구조적 단순화와 결정 근거의 선명도 강화**입니다. 한 문장으로 요약하면 다음과 같습니다.
> **이 저장소는 자기개선을 시작할 준비는 충분하지만, 자기개선을 오래 안전하게 지속하려면 오케스트레이션 복잡도를 더 낮춰야 합니다.**
## 부록 A. 선택 실행 테스트 로그
### A-1

```text
....uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu.uuuuuuuuuuuuuuuuuuuuuuuuu [ 42%]
uuuuuuuuuuuuuuuuu.....uuuuuuuuuuuuuuu.uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu [ 85%]
uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu [ 85%]
uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu.uuuuuuuuuuuuuuu.uuuuuuuuuuuuuuu.     [100%]
```
### A-2

```text
.................                                                        [100%]
```
## 부록 B. 참고 지표
- direct-script fallback 사용 파일 예시:
  - `ops/scripts/auto_improve_loop.py`
  - `ops/scripts/auto_improve_readiness.py`
  - `ops/scripts/cyclonedx_sbom.py`
  - `ops/scripts/executor.py`
  - `ops/scripts/export_public_repo.py`
  - `ops/scripts/finalize_run.py`
  - `ops/scripts/improvement_observations.py`
  - `ops/scripts/in_toto_statement.py`
  - `ops/scripts/mechanism_assess.py`
  - `ops/scripts/mechanism_review.py`
  - `ops/scripts/mutation_proposal.py`
  - `ops/scripts/openvex_draft.py`
  - `ops/scripts/outcome_metrics.py`
  - `ops/scripts/planning_gate_validate.py`
  - `ops/scripts/promotion_gate.py`
  - `ops/scripts/raw_intake_promotion.py`
  - `ops/scripts/raw_markdown_normalize.py`
  - `ops/scripts/raw_registry_export.py`
  - `ops/scripts/raw_registry_preflight.py`
  - `ops/scripts/release_smoke.py`
- `except Exception` 사용 예시:
  - `ops/scripts/auto_improve_loop.py:47`
  - `ops/scripts/executor_runtime.py:119`
  - `ops/scripts/filesystem_runtime.py:66`
  - `ops/scripts/finalize_run.py:66`
  - `ops/scripts/mechanism_review.py:35`
  - `ops/scripts/mechanism_review.py:56`
  - `ops/scripts/mutation_proposal.py:37`
  - `ops/scripts/mutation_proposal.py:71`
  - `ops/scripts/promotion_gate.py:355`
  - `ops/scripts/raw_markdown_runtime.py:136`
  - `ops/scripts/run_mechanism_experiment.py:78`
  - `ops/scripts/set_mechanism_run_history.py:232`
- subprocess 사용 예시:
  - `ops/scripts/command_runtime.py:63` → `subprocess.Popen`
  - `ops/scripts/release_smoke.py:170` → `subprocess.run`
  - `tests/test_executor_runtime.py:574` → `subprocess.run`
  - `tests/test_promotion_gate_equal_score.py:381` → `subprocess.run`
  - `tests/test_promotion_gate_exit_codes.py:210` → `subprocess.run`
  - `tests/test_public_surface_policy.py:72` → `subprocess.run`
  - `tests/test_public_surface_policy.py:74` → `subprocess.run`
  - `tools/ruff_strict_preview.py:53` → `subprocess.run`
