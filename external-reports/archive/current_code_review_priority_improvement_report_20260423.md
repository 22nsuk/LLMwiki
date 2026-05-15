# 현재 코드 검토 및 우선순위 개선 보고서

- 작성일: 2026-04-23
- 대상: `LLM Wiki vNext`
- 목적: 현재 코드, `external-reports`, `ops/reports/task-improvement-observations`, 주요 운영 산출물을 교차 검토하여 **지금 시점에 실제로 의미 있는 개선 우선순위**를 재정렬하고, 바로 실행 가능한 개선 방향을 정리한다.
- 작성 원칙:
  - 과거 보고서의 문제 제기를 그대로 반복하지 않고 **현재 코드 기준으로 아직 남아 있는 문제**와 **이미 상당 부분 해소된 문제**를 분리한다.
  - 운영 보고서의 상태값과 실제 코드 구조를 함께 보고 판단한다.
  - “구조적으로 중요하지만 당장 실행 순위는 낮은 과제”와 “지금 바로 손대지 않으면 개선 루프가 멈추는 과제”를 구분한다.

---

## 1. 결론 요약

이 저장소는 기초 체력이 약한 상태가 아니다. 오히려 다음 특성이 뚜렷하다.

1. **정책·스키마·리포트 중심의 제어면(control plane)** 이 이미 상당히 성숙해 있다.
2. 공급망(SBOM/VEX/attestation) 계열과 공개/비공개 경계는 비교적 잘 정리돼 있다.
3. 테스트와 자동 생성 산출물의 폭도 넓다.
4. 다만, 저장소의 차별점인 **self-improvement 루프가 “존재”하는 것과 “지금 바로 안정적으로 돌릴 수 있는 것” 사이에는 아직 간극**이 있다.

현재 가장 중요한 문제는 “코드가 전반적으로 엉성하다”가 아니라 아래 두 가지다.

- **(가장 중요)** auto-improve 체인이 현재 기준으로는 제안은 만들지만 **실행 가능한 runnable proposal** 을 만들지 못하고 있다.
- **(그 다음 중요)** 내부 런타임 경계가 아직 완전히 정리되지 않아, 일부 핵심 표면에서 여전히
  - raw dict 중심 산출물 조립,
  - hotspot을 충분히 감시하지 못하는 complexity budget,
  - 일관되지 않은 schema loader 경계,
  - 구조화 로그 부족,
  - direct-script/bootstrap 중복
  이 남아 있다.

따라서 현재 시점의 최우선 개선 방향은 다음 순서가 맞다.

### 최우선 우선순위

1. **P0 — auto-improve readiness / queue runnability 복구**
2. **P1 — typed artifact payload 경계 강화**
3. **P1 — structural complexity budget을 실제 hotspot에 재정렬**
4. **P1 — schema loader boundary 단일화**
5. **P1 — runtime structured logging / cross-artifact fault 검증 강화**
6. **P2 — direct-script entrypoint/bootstrap 중복 축소**
7. **P3 — 포터블리티·raw/synthesis 계열 품질 개선을 후속으로 정리**

핵심적으로, 지금은 새로운 기능을 더 만드는 것보다 **기존 self-improvement 운영면을 실제로 굴러가게 만들고, 그 내부 계약을 균질화하는 것**이 맞다.

---

## 2. 검토 범위와 방법

이번 검토에는 아래 범위를 반영했다.

### 2.1 현재 코드/설정/테스트

- `ops/scripts/`
- `tests/`
- `tools/`
- 루트 설정/문서 (`README.md`, `ops/README.md`, `pyproject.toml`, `pytest.ini`, `Makefile` 등)
- 주요 운영 산출물:
  - `ops/reports/auto-improve-readiness.json`
  - `ops/reports/outcome-metrics.json`
  - `ops/reports/structural-complexity-budget.json`
  - `ops/reports/mechanism-review-candidates.json`
  - `ops/reports/mutation-proposals.json`
  - `ops/reports/supply-chain-gate-report.json`
  - `ops/reports/sbom-readiness-gate-report.json`

### 2.2 external-reports 전체 검토 반영

- `external-reports/anti_slop_self_improvement_code_review_report_20260423.md`
- `external-reports/code_review_report_20260421.md`
- `external-reports/code_review_report_llm_wiki_vnext_20260423.md`
- `external-reports/current_code_review_and_improvement_report_20260421.md`
- `external-reports/llm_wiki_vnext_anti_slop_self_improvement_report_20260423.md`
- `external-reports/llm_wiki_vnext_code_report_20260421.md`
- `external-reports/llm_wiki_vnext_code_review_report_20260421.md`
- `external-reports/llm_wiki_vnext_code_review_report_260422.md`
- `external-reports/llm_wiki_vnext_code_review_report_ko_20260420.md`
- `external-reports/llm_wiki_vnext_code_review_report_ko_20260421.md`
- `external-reports/llm_wiki_vnext_code_review_report_kor_20260421.md`
- `external-reports/llm_wiki_vnext_detailed_review_ko_20260419.md`
- `external-reports/self_improvement_run_readiness_report_20260422.md`

### 2.3 ops observation 산출물 전체 검토 반영

- `ops/reports/task-improvement-observations/task-20260416-detailed-review-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260416-standalone-observation-generalization/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260418-policy-contract-registry-validation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-code-review-report-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-detailed-review-current-code-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-import-fallback-mypy-migration/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-promotion-rule-registry-declarative/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-rule-spec-function-budget/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260420-review-sbom-vex-alignment/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-code-review-report-kor-current-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-raw-intake-batch-review/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-raw-warn-triage/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-runtime-decomposition/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-auto-improve-workspace-preparation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-code-review-report-260422-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-concept-synthesis-quality-review/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-live-auto-improve-run-readiness/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-synthesis-format-and-absorption-review/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260423-structural-budget-schema-boundary/improvement-observations.json`

### 2.4 직접 점검한 실행/검증

- `python -m ops.scripts.planning_gate_validate --vault .` 실행 확인
- `python -m ops.scripts.structural_complexity_budget --vault .` 실행 확인
- `pytest tests/test_command_runtime.py` 단일 테스트 재현 점검
- 대형 런타임 파일/함수 길이와 hotspot 분포 정적 스캔
- schema loader 호출 패턴, direct-script bootstrap 패턴 정적 스캔

---

## 3. 검토 한계와 해석 기준

### 3.1 압축 해제 한계

원본 ZIP 안의 `raw/web-snapshots/...` 일부는 경로 길이 문제로 전체를 동일하게 풀 수 없었다.  
그래서 로컬 재현 환경에서 `raw_registry_preflight`가 다수의 `raw_path_mismatch`를 보고했지만, 이 결과는 **현재 코드 결함으로 직접 해석하지 않았다**. 이는 저장소 자체 문제라기보다 **부분 추출 환경의 왜곡** 가능성이 높다.

### 3.2 실행 환경 의존성

`tests/test_command_runtime.py`의 정상 완료 케이스는 현재 컨테이너의 기본 `sys.executable` 환경에서 `returncode == -15`로 재현되었지만, 시스템 Python에서는 동일 스크립트가 정상 완료됐다.  
따라서 이 항목은 “현재 코드가 항상 실패한다”로 적지 않고, **실행기/인터프리터 경계의 포터블리티 리스크**로 분류했다.

---

## 4. 현재 상태 진단

## 4.1 현재 저장소의 분명한 강점

### 4.1.1 운영면이 이미 매우 체계적이다

이 저장소는 단순한 스크립트 모음이 아니다. 정책, 산출물 스키마, 게이트, review, proposal, readiness, promotion이 서로 연결된 운영면을 갖고 있다.  
이 점은 다수의 external report가 반복적으로 높게 평가한 부분이며, 현재 코드와 산출물 상태에서도 그대로 확인된다.

### 4.1.2 공급망·공개 경계는 상대적으로 안정적이다

현재 보고서 상태를 보면 supply-chain 계열 산출물은 비교적 안정적이다.  
이 영역은 “없어서 위험한 상태”가 아니라 “이미 기본선은 확보된 상태”에 가깝다.

### 4.1.3 분해 작업은 실제로 진전됐다

과거 보고서들은 monolith 성격의 runtime과 orchestration 집중도를 반복 지적했는데, 현재는 분해가 꽤 진행돼 있다.  
문제는 “아무것도 안 바뀌었다”가 아니라, **분해는 됐지만 핵심 조정면 몇 곳에 복잡도가 다시 응집되고 있는 상태**라는 점이다.

---

## 4.2 지금 가장 중요한 사실: auto-improve는 준비돼 보이지만 아직 “굴러가는 상태”는 아니다

현재 `ops/reports/auto-improve-readiness.json` 기준:

- `status = warn`
- `queue.ready = false`
- `proposals_emitted = 1`
- `runnable_proposal_count = 0`
- `blocked_proposal_count = 1`
- `attempts_considered = 7`
- `session_reports_considered = 0`

즉, 지금 상태는 “제안 생성 기능이 있다”가 아니라 **제안은 나오지만 바로 돌릴 수 있는 제안이 없다**는 뜻이다.

관련해서 현재 보고서는 다음 네 가지를 직접 시사한다.

1. **최근 히스토리 overlap이 blocker로 작동**
2. **session rollup 근거가 비어 있음**
3. **attempt 수가 readiness 임계치보다 부족**
4. **후속 실험을 좁게 설계해야 하는데, 아직 운영 queue가 그 다음 스텝을 매끄럽게 열어주지 못함**

이 저장소의 핵심 가치가 self-improvement loop라면, 이 문제는 문서 품질이나 부수적 lint 이슈보다 훨씬 앞선다.

---

## 5. 현재 코드에서 확인된 핵심 병목

## 5.1 complexity budget이 존재하지만, 실제 hotspot을 완전히 감시하지 못한다

현재 `structural-complexity-budget.json`은 `pass`이고, 모니터링 대상은 14개 파일이다.  
문제는 **pass라는 결과 자체보다, 무엇을 보고 있고 무엇을 안 보고 있는가**다.

현재 대형 hotspot 스캔 결과 상위 파일은 아래와 같다.

| 순위 | 파일 | non-empty line | 최장 함수 |
|---|---|---:|---|
| 1 | `ops/scripts/filesystem_runtime.py` | 771 | rehearse_manifest_apply_rollback (82 lines) |
| 2 | `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py` | 673 | build_outcome_metrics_calibration_diagnostics (132 lines) |
| 3 | `ops/scripts/mechanism_run_workspace_runtime.py` | 660 | _apply_or_discard_workspace_changes (79 lines) |
| 4 | `ops/scripts/policy_validation_runtime.py` | 646 | _validate_subagent_role_registry (61 lines) |
| 5 | `ops/scripts/mechanism_run_validation_runtime.py` | 617 | build_report_consistency_checks (61 lines) |
| 6 | `ops/scripts/mechanism_review_candidate_runtime.py` | 606 | bootstrap_diagnostics (81 lines) |
| 7 | `ops/scripts/codex_exec_executor.py` | 606 | execute_codex_exec_role (109 lines) |
| 8 | `ops/scripts/mutation_proposal_runtime.py` | 590 | build_report (121 lines) |
| 9 | `ops/scripts/wiki_lint_review_runtime.py` | 587 | concept_carryover_continuity_candidates (78 lines) |
| 10 | `ops/scripts/auto_improve_runtime.py` | 581 | _start_auto_improve_session (54 lines) |
| 11 | `ops/scripts/mechanism_assess.py` | 544 | build_report (56 lines) |
| 12 | `ops/scripts/raw_markdown_runtime.py` | 541 | raw_markdown_quality_pass (98 lines) |

현재 budget의 기본 대상에는 일부 핵심 표면이 포함되지만, 실제로 눈에 띄는 hotspot 중 아래 파일들은 기본 감시 표면에서 상대적으로 약하다.

- `ops/scripts/codex_exec_executor.py`
- `ops/scripts/mutation_proposal_runtime.py`
- `ops/scripts/mechanism_review_candidate_runtime.py`
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py`
- `ops/scripts/filesystem_runtime.py`

즉, 현재 complexity budget은 **도입 자체는 의미 있지만, 실제 위험 표면과의 정렬이 아직 충분하지 않다.**

### 판단

이 이슈는 “있으면 좋은 개선”이 아니다.  
현재 저장소의 리스크가 “대형 helper/runtime의 복잡도 재응집”인 이상, budget이 실제 hotspot을 제대로 조준해야 한다.

---

## 5.2 typed artifact payload 경계가 아직 불균질하다

현재 코드는 dataclass/TypedDict seam을 일부 도입했지만, 여전히 많은 schema-backed 산출물이 runtime 내부에서 raw dict 조립 방식으로 만들어진다.

정적 스캔상 `ops/scripts/` 안에서 `dict[str, object]` 또는 유사한 loose payload 패턴이 확인되는 파일이 35개였다.  
이것이 곧바로 모두 잘못이라는 뜻은 아니지만, 다음 문제를 만든다.

- 산출물 필드 드리프트가 runtime 내부에서 늦게 발견됨
- builder 로직이 길어질수록 “필수 필드/선택 필드/파생 필드”의 구분이 흐려짐
- cross-artifact consistency 검증이 테스트 쪽으로 과도하게 밀림
- schema validation 통과와 runtime 의미 일관성이 분리될 수 있음

### 판단

현재 저장소는 이미 artifact-driven 시스템이므로, 다음 단계는 “스키마가 있다”에서 멈추지 않고 **typed builder / typed result model로 내부 조립 경계를 좁히는 것**이다.

---

## 5.3 schema loader 경계가 아직 통일되지 않았다

현재 `schema_runtime`에는 bundled fallback helper가 존재하지만, 정적 스캔상 아직도 다수 파일이 직접 `load_schema(vault / ...)` 패턴을 사용한다.

- helper 사용 파일: 6개
- direct `load_schema(vault / ...)` 사용 파일: 30개
- direct 호출 수: 42회

즉, “fallback-aware boundary”가 새로 생겼지만 **저장소 전반으로 이관이 끝난 상태는 아니다.**

이 문제는 겉보기에 사소해 보이지만 실제로는 중요하다.

- 패키지 실행/직접 실행/부분 workspace 상황에서 동작 차이가 생길 수 있음
- schema path resolution 정책이 호출부마다 달라질 수 있음
- 향후 배포/테스트/packaged execution 경로에서 drift가 누적될 수 있음

### 판단

이 항목은 typed artifact 경계 강화와 함께 묶어서 처리해야 한다.  
내부 계약이 강해지려면 **“어떤 schema를 어디서 어떻게 로드하는가”도 단일 정책**이어야 한다.

---

## 5.4 runtime structured logging이 artifact 수준만큼 성숙하지 못했다

현재 저장소는 JSON 산출물이 풍부하다.  
하지만 runtime 진행 상황과 실패 맥락은 상대적으로 덜 구조화돼 있고, 일부 경로는 여전히 CLI/print 중심이다.

이는 다음 비용을 만든다.

- 장애 재현 시 “최종 산출물”은 남아도 중간 경로를 복원하기 어렵다
- mechanism candidate/proposal/readiness의 연결 고리를 사람이 다시 읽어야 한다
- failure triage가 artifact diff보다 느려진다
- local/CI/OS 차이에서 실행기 이슈를 좁히는 시간이 길어진다

### 판단

artifact-rich 시스템은 결국 **runtime event도 artifact 수준으로 구조화**되어야 한다.  
지금은 그 과도기 상태다.

---

## 5.5 direct-script bootstrap / import fallback 중복이 아직 많다

정적 스캔상 `ops/scripts/` 내에서 `sys.path.insert(...)` 또는 유사 bootstrap 패턴이 확인된 파일 수는 42개였다.  
이는 direct-script 호환성을 유지하기 위한 의도적 설계지만, 현재는 아래 문제가 남아 있다.

- 진입점별 bootstrap 방식이 분산됨
- mypy/strictness 확장 시 방해 요인이 됨
- 진짜 비즈니스 로직과 실행 호환성 로직이 한 파일에 섞임
- interpreter/venv 차이에서 예외 케이스가 늘어남

### 판단

이 영역은 당장 P0는 아니지만, **runtime 표면 정리와 정적 엄격성 확대의 공통 선행 작업**이다.

---

## 5.6 교차 산출물 fault 방어가 더 필요하다

현재 테스트는 넓지만, 보고서/게이트/queue/proposal/readiness 간의 **교차 일관성 깨짐**을 한 번에 잡는 fault test는 더 강화할 여지가 크다.

예를 들어 다음과 같은 경우다.

- outcome metrics는 갱신됐는데 readiness 해석이 이전 상태를 읽는 경우
- candidate는 생성되는데 mutation proposal에서 blocker 정책이 drift하는 경우
- schema는 통과하지만 downstream summary가 기대 필드를 누락하는 경우

### 판단

이 저장소는 artifact 간 연결이 촘촘하기 때문에, 단일 단위 테스트보다 **cross-artifact contract test**의 가치가 크다.

---

## 5.7 실행기/포터블리티 리스크는 현재 “보조 우선순위”로 유지하는 것이 맞다

로컬 재현에서 `tests/test_command_runtime.py` 정상 완료 케이스가 현재 pyvenv Python 기준으로 실패했다.  
그러나 시스템 Python에서는 동일 호출이 정상 종료되므로, 이를 곧바로 “현재 코드의 결정적 기능 결함”으로 단정하지는 않았다.

다만 이것은 다음을 시사한다.

- `sys.executable` 신뢰 방식이 환경마다 다를 수 있다
- timeout/process-session/termination 계약이 interpreter boundary에서 흔들릴 수 있다
- Windows/Linux/venv 차이를 smoke 수준 이상으로 계속 다뤄야 한다

### 판단

이 항목은 중요하지만 **지금 가장 먼저 막아야 할 병목은 아니다.**  
P3 또는 P2 하위로 유지하되, executor/command runtime 리팩터링 시 함께 묶는 것이 적절하다.

---

## 6. external-reports와 observation을 반영한 최종 우선순위

## 6.1 P0 — 지금 바로 손봐야 하는 과제

### P0-1. auto-improve readiness를 “제안 생성”이 아니라 “실행 가능” 상태로 복구

#### 왜 지금인가
현재 저장소의 핵심 차별점은 self-improvement loop다.  
그런데 현재 상태는 proposal이 생겨도 runnable proposal이 0이다.  
이 상태가 계속되면 저장소는 “고급 보고서를 잘 만드는 시스템”으로 남고, 실제 개선 루프는 정지한다.

#### 현재 근거
- `auto-improve-readiness.json`: `ready=false`
- `mutation-proposals.json`: blocked proposal 존재
- `mechanism-review-candidates.json`: 후보는 있으나 calibration depth가 낮음
- observation:
  - `auto_improve_queue_threshold_history_followup`
  - `blocked_proposal_queue_policy_next`
  - `semantic_regression_signal_gap`

#### 권장 조치
1. readiness 판정 로직을 **“proposal emitted” 중심이 아니라 “runnable proposal 확보” 중심**으로 더 노골적으로 정렬
2. `recent_log_overlap` blocker를 단순 경고가 아니라 **queue-level 재시도 정책**으로 흡수
3. `session_reports_considered=0` 상태를 readiness의 강한 경고로 유지하되, session rollup이 비었을 때의 대체 경로를 명시
4. single-mechanism scope 축소를 실제 next action generator까지 연결

#### 핵심 대상 파일
- `ops/scripts/auto_improve_readiness_runtime.py`
- `ops/scripts/mechanism_review_candidate_runtime.py`
- `ops/scripts/mutation_proposal_runtime.py`
- `ops/scripts/auto_improve_iteration_persistence_runtime.py`

#### 완료 기준
- `runnable_proposal_count >= 1` 을 반복적으로 확보
- blocker가 있어도 queue가 “왜 멈췄는지 / 언제 재시도 가능한지 / 다음 기계적 액션이 무엇인지”를 명확히 출력
- 동일 failure mode에서 사람이 수동으로 다음 실험 범위를 다시 설계하지 않아도 됨

---

## 6.2 P1 — 저장소의 내부 품질을 실제로 끌어올리는 핵심 과제

### P1-1. typed artifact payload contract 강화

#### 왜 중요한가
이 저장소는 artifact-driven이다.  
그런데 내부 조립이 raw dict 중심이면, 스키마 기반이라는 장점이 runtime 내부에서 반감된다.

#### 권장 조치
1. report builder가 긴 파일부터 typed builder/dataclass 도입
2. “schema validation 통과”와 “runtime 의미 일관성”을 같은 builder에서 보장
3. summary/diagnostics/queue item/proposal payload를 우선 typed화
4. loose `dict[str, object]` 패턴을 신규 코드에서 금지하고, 기존 코드엔 점진 마이그레이션 정책 부여

#### 우선 대상
- `ops/scripts/auto_improve_readiness_runtime.py`
- `ops/scripts/mutation_proposal_runtime.py`
- `ops/scripts/mechanism_review_candidate_runtime.py`
- `ops/scripts/planning_gate_report_runtime.py`
- `ops/scripts/promotion_gate_mechanism_report_runtime.py`

#### 완료 기준
- 핵심 report builder가 “typed input -> typed intermediate -> validated output” 흐름을 갖춤
- 테스트가 필드 존재 여부만 보지 않고 typed invariant를 검증

---

### P1-2. structural complexity budget을 실제 hotspot 기반으로 재설계

#### 왜 중요한가
현재 budget이 `pass`여도, 감시 대상이 핵심 hotspot을 충분히 덮지 않으면 운영 리스크는 줄지 않는다.

#### 권장 조치
1. 현재 profile에 아래 파일을 우선 편입 또는 별도 profile 생성
   - `ops/scripts/codex_exec_executor.py`
   - `ops/scripts/mutation_proposal_runtime.py`
   - `ops/scripts/mechanism_review_candidate_runtime.py`
   - `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py`
   - `ops/scripts/filesystem_runtime.py`
2. 파일 단위 뿐 아니라 **최장 함수 budget**을 별도 attention 신호로 승격
3. readiness / proposal 계열 파일에는 “branch node 증가율” 기준도 추가

#### 완료 기준
- budget report의 monitored target이 현재 hotspot 현실과 일치
- “pass인데도 실제 위험 파일은 비켜감” 상태 제거

---

### P1-3. schema loader boundary 단일화

#### 왜 중요한가
schema path 정책이 호출부마다 달라지면 packaged execution, sparse workspace, direct run에서 일관성이 깨진다.

#### 권장 조치
1. schema load entry를 하나의 helper로 집중
2. direct `load_schema(vault / ...)` 호출을 단계적으로 제거
3. schema resolution 실패 시 진단 메시지 형식 통일
4. package fallback 동작을 테스트로 고정

#### 우선 대상
- direct 호출이 남아 있는 schema consumer 전반
- 특히 report/gate/security/supply-chain 계열 writer

#### 완료 기준
- schema load 경로가 저장소 전반에서 단일 규약으로 보임
- packaged/direct/sparse 실행에서 동일 의미 보장

---

### P1-4. runtime structured logging + cross-artifact fault test 강화

#### 왜 중요한가
이 시스템은 artifact가 풍부한 대신, 중간 단계 실패 추적 비용이 높다.  
구조화 로그와 교차 산출물 검증을 같이 올려야 triage 시간이 줄어든다.

#### 권장 조치
1. readiness / candidate / proposal / promotion 경로에 공통 event schema 부여
2. `run_id`, `candidate_id`, `proposal_id`, `blocker`, `decision_reason` 연결 키를 로그에 강제
3. cross-artifact fault test 추가:
   - stale outcome metrics
   - missing session rollup
   - candidate/proposal drift
   - schema valid but summary inconsistent
4. human-readable report와 machine-readable diagnostics를 함께 유지

#### 완료 기준
- 실패한 run 하나를 열었을 때 intermediate decision chain을 기계적으로 복원 가능
- “왜 blocked 됐는지”가 JSON artifact와 runtime log 양쪽에서 일치

---

### P1-5. auto-improve/promotion/runtime 분해를 한 단계 더 밀기

#### 왜 중요한가
분해는 진행됐지만, 일부 핵심 orchestration surface는 여전히 크고 기능이 많다.

#### 권장 조치
1. phase/state assembly와 report assembly를 분리
2. decision policy / mutation scope / persistence / logging을 더 분리
3. executor·workspace·promotion 경계에서 side effect owner를 명확히 구분

#### 우선 대상
- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/promotion_gate_mechanism_runtime.py`
- `ops/scripts/mechanism_run_workspace_runtime.py`
- `ops/scripts/auto_improve_iteration_persistence_runtime.py`

---

## 6.3 P2 — 구조 안정화를 위한 후속 과제

### P2-1. direct-script bootstrap 중복 축소
- 공통 bootstrap helper 또는 thin entrypoint layer로 정리
- `sys.path` 삽입 패턴을 신규 코드에서 금지
- strict typing 확대 전 선행 정리

### P2-2. strictness/mypy 확장
- 현재는 `follow_imports = skip`, `ignore_missing_imports = true` 중심
- typed payload 마이그레이션 이후 모듈별 allowlist 축소가 적절
- 지금 당장 전면 강화하면 운영 속도만 떨어질 가능성이 큼

### P2-3. output path policy 마이그레이션 마무리
- `resolve_repo_output_path`는 좋은 방향
- 하지만 older permissive resolver와 이원화가 남아 있어 정책 표면이 넓다
- repo-internal writer와 export/user-output writer를 더 선명히 나누는 편이 좋다

### P2-4. 대형 fixture / 시나리오 테스트 분리
- 테스트 이해 비용을 줄이고, contract test를 더 명확히 만들기 위함
- 단, 지금 당장 핵심 병목은 아니다

---

## 6.4 P3 — 중요하지만 지금은 후순위로 두는 과제

### P3-1. raw intake 품질 게이트 정교화
다수 observation이 raw intake route/source quality/absorption decision을 지적한다.  
이는 분명 중요하지만, 현재 최우선은 **핵심 self-improvement 루프의 runnability** 복구다.

### P3-2. synthesis template / concept carryover 품질
synthesis 품질 계열은 가치가 높지만, 현재 저장소 전체 구조 우선순위에서는 후순위다.

### P3-3. command runtime / OS portability 추가 강화
현재 재현된 이슈는 추적 가치가 있으나, P0/P1가 해결되기 전 최상위로 올릴 필요는 없다.

---

## 7. “이미 해소됐거나 우선순위를 낮춰도 되는 항목”

과거 external report/observation에서 제기됐지만, 현재 기준으로는 우선순위를 낮춰도 되는 항목도 분명히 있다.

### 7.1 Python baseline 정렬
과거에는 Python 3.14 기준선과 실제 소스 해석 기준의 불일치가 지적됐지만, 현재 `pyproject.toml`은 `requires-python = ">=3.12"`, `ruff target-version = "py312"`, `mypy python_version = "3.12"`로 정렬돼 있다.  
이 항목은 현재 최우선 문제가 아니다.

### 7.2 external report markdown audit
과거 `.md external report`가 감사 대상에서 누락된 문제가 있었지만, 현재 정책/테스트 기준으로는 이 이슈가 상당 부분 반영된 것으로 보인다.  
따라서 재지적 우선순위는 낮다.

### 7.3 package metadata / manifest exclusion
editable install 산출물 제외 문제도 현재는 기본선이 보강돼 있는 편이다.

### 7.4 sparse workspace / telemetry preservation
해당 observation 계열도 현재는 구현 진전이 확인된다.  
즉, 이 저장소는 “아무것도 개선되지 않았다”가 아니라 **이미 많은 개선을 반영한 뒤, 이제 남은 병목이 더 구조적이고 정교한 종류로 바뀐 상태**다.

---

## 8. 바로 실행 가능한 3단계 실행 계획

## 8.1 1단계 — 1~3일: auto-improve runnable proposal 복구

### 목표
`make auto-improve-readiness` 결과를 “warn + blocked”에서 벗어나게 하는 것.

### 작업
1. `recent_log_overlap` blocker 해석을 queue 정책으로 승격
2. session rollup 부재 시 fallback diagnostics 강화
3. readiness 출력에 “다음 기계적 액션” 필드 추가
4. single-mechanism scope 제안을 실제 next proposal narrowing과 연결

### 산출물
- 개선된 `auto-improve-readiness.json`
- runnable proposal 1건 이상
- blocker reason/next action 일관화

---

## 8.2 2단계 — 3~7일: typed boundary + schema loader 경계 정리

### 목표
핵심 report builder 두세 개를 기준 모델로 삼아 내부 계약을 강하게 만드는 것.

### 작업
1. readiness/proposal/candidate builder부터 typed payload 도입
2. schema loader를 helper 기반으로 통일
3. cross-artifact fault test 최소 3종 추가

### 산출물
- typed intermediate model 도입
- direct schema load 호출 감소
- artifact drift 방어 테스트 확보

---

## 8.3 3단계 — 1~2주: hotspot budget과 runtime observability 재정렬

### 목표
“pass인데 위험은 남는” 상태를 없애는 것.

### 작업
1. budget monitored target 재편
2. function-length/branch-node hotspot attention 승격
3. runtime structured event 로그 추가
4. direct-script bootstrap 얇은 계층으로 이동 시작

### 산출물
- 현실 반영 budget profile
- triage 속도 향상
- 분해 다음 단계의 기준선 확보

---

## 9. 최종 판단

현재 저장소는 외부 보고서가 지적하던 초창기 문제를 많이 흡수했다.  
그래서 지금 필요한 것은 “문제 목록을 더 길게 만드는 것”이 아니다.

지금 가장 중요한 판단은 다음이다.

> **이 저장소의 다음 개선은 기능 추가가 아니라, self-improvement 루프를 실제로 굴러가게 만들고 그 내부 계약을 typed/observable/consistent하게 만드는 방향이어야 한다.**

정리하면:

- **가장 먼저** auto-improve readiness와 runnable proposal 문제를 해결해야 한다.
- 그 다음은 **typed artifact contract**, **complexity budget hotspot 정렬**, **schema loader boundary 통일**이다.
- structured logging과 cross-artifact fault test는 그 효과를 배가시키는 핵심 보강축이다.
- raw/synthesis/portability 개선은 중요하지만, 지금 이 시점의 최상위 과제는 아니다.

즉, 현재 저장소의 올바른 방향은 **“더 많은 자동화”가 아니라 “이미 있는 자동화가 실제로 신뢰 가능하게 작동하도록 만드는 것”**이다.

---

## 10. 부록 A — 검토에 반영한 external-reports 전체 목록

- `external-reports/anti_slop_self_improvement_code_review_report_20260423.md`
- `external-reports/code_review_report_20260421.md`
- `external-reports/code_review_report_llm_wiki_vnext_20260423.md`
- `external-reports/current_code_review_and_improvement_report_20260421.md`
- `external-reports/llm_wiki_vnext_anti_slop_self_improvement_report_20260423.md`
- `external-reports/llm_wiki_vnext_code_report_20260421.md`
- `external-reports/llm_wiki_vnext_code_review_report_20260421.md`
- `external-reports/llm_wiki_vnext_code_review_report_260422.md`
- `external-reports/llm_wiki_vnext_code_review_report_ko_20260420.md`
- `external-reports/llm_wiki_vnext_code_review_report_ko_20260421.md`
- `external-reports/llm_wiki_vnext_code_review_report_kor_20260421.md`
- `external-reports/llm_wiki_vnext_detailed_review_ko_20260419.md`
- `external-reports/self_improvement_run_readiness_report_20260422.md`

---

## 11. 부록 B — 검토에 반영한 observation 파일 전체 목록

- `ops/reports/task-improvement-observations/task-20260416-detailed-review-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260416-standalone-observation-generalization/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260418-policy-contract-registry-validation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-code-review-report-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-detailed-review-current-code-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-import-fallback-mypy-migration/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-promotion-rule-registry-declarative/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260419-rule-spec-function-budget/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260420-review-sbom-vex-alignment/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-code-review-report-kor-current-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-raw-intake-batch-review/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-raw-warn-triage/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260421-runtime-decomposition/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-auto-improve-workspace-preparation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-code-review-report-260422-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-concept-synthesis-quality-review/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-live-auto-improve-run-readiness/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260422-synthesis-format-and-absorption-review/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260423-structural-budget-schema-boundary/improvement-observations.json`

---

## 12. 부록 C — observation별 이번 보고서 최종 판단

| observation_id | source task | 상태 | 이번 보고서 판단 | 우선순위 |
|---|---|---|---|---|
| `executor_timeout_contract_gap` | `task-20260416-detailed-review-reconciliation` | `automated` | 지속 관리 | P2 |
| `semantic_regression_signal_gap` | `task-20260416-detailed-review-reconciliation` | `automated` | 핵심 유지 | P0 |
| `remaining_orchestrator_decomposition_gap` | `task-20260416-detailed-review-reconciliation` | `automated` | 핵심 유지 | P1 |
| `python_314_baseline_policy_gap` | `task-20260416-detailed-review-reconciliation` | `automated` | 우선순위 하향 | 완료 |
| `atomic_multi_write_duplicate_target_gap` | `task-20260416-detailed-review-reconciliation` | `automated` | 우선순위 하향 | 완료 |
| `standalone_observation_capture_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 우선순위 하향 | 완료 |
| `run_telemetry_schema_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 우선순위 하향 | 완료 |
| `hold_nonempty_manifest_contract_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 지속 관리 | P2 |
| `apply_allowlist_hard_barrier_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 우선순위 하향 | 완료 |
| `determinism_sweep_core_generator_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 우선순위 하향 | 완료 |
| `observability_artifact_contract_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 지속 관리 | P2 |
| `subagent_routing_polish_contract_gap` | `task-20260416-standalone-observation-generalization` | `automated` | 지속 관리 | P2 |
| `promotion_decision_registry_downstream_alignment` | `task-20260418-policy-contract-registry-validation` | `automated` | 우선순위 하향 | 완료 |
| `external_report_markdown_audit_gap` | `task-20260419-code-review-report-reconciliation` | `automated` | 우선순위 하향 | 완료 |
| `package_metadata_manifest_exclusion_gap` | `task-20260419-code-review-report-reconciliation` | `automated` | 우선순위 하향 | 완료 |
| `strict_warning_budget_gate_gap` | `task-20260419-code-review-report-reconciliation` | `automated` | 지속 관리 | P2 |
| `outcome_canary_provenance_maturity_gap` | `task-20260419-detailed-review-current-code-reconciliation` | `open` | 핵심 유지 | P1 |
| `mypy_allowlist_expansion_after_import_fallback` | `task-20260419-import-fallback-mypy-migration` | `automated` | 지속 관리 | P2 |
| `direct_script_entrypoint_allowlist` | `task-20260419-import-fallback-mypy-migration` | `automated` | 지속 관리 | P2 |
| `page_class_rule_metadata_gap` | `task-20260419-promotion-rule-registry-declarative` | `automated` | 우선순위 하향 | 완료 |
| `python_function_budget_candidate_triage` | `task-20260419-rule-spec-function-budget` | `open` | 핵심 유지 | P1 |
| `release_package_source_trace_parity_gap` | `task-20260419-rule-spec-function-budget` | `automated` | 지속 관리 | P2 |
| `sbom_generated_pipeline_reuses_prior_artifacts` | `task-20260420-review-sbom-vex-alignment` | `automated` | 우선순위 하향 | 완료 |
| `auto_improve_phase_split_gap` | `task-20260421-code-review-report-kor-current-reconciliation` | `automated` | 핵심 유지 | P1 |
| `runtime_structured_logging_gap` | `task-20260421-code-review-report-kor-current-reconciliation` | `automated` | 핵심 유지 | P1 |
| `outcome_metrics_shadow_priority_gap` | `task-20260421-code-review-report-kor-current-reconciliation` | `planned` | 핵심 유지 | P1 |
| `cross_artifact_fault_test_gap` | `task-20260421-code-review-report-kor-current-reconciliation` | `automated` | 핵심 유지 | P1 |
| `windows_command_runtime_smoke_gap` | `task-20260421-code-review-report-kor-current-reconciliation` | `automated` | 지속 관리 | P3 |
| `raw_intake_route_classifier_review_gate` | `task-20260421-raw-intake-batch-review` | `open` | 도메인별 지속 관리 | P3 |
| `raw_intake_source_content_quality_gate` | `task-20260421-raw-intake-batch-review` | `open` | 도메인별 지속 관리 | P3 |
| `raw_intake_absorption_decision_gate` | `task-20260421-raw-intake-batch-review` | `planned` | 도메인별 지속 관리 | P3 |
| `raw_backlog_triage_gap` | `task-20260421-raw-warn-triage` | `automated` | 도메인별 지속 관리 | P3 |
| `promotion_gate_state_split` | `task-20260421-runtime-decomposition` | `automated` | 핵심 유지 | P1 |
| `structural_complexity_budget` | `task-20260421-runtime-decomposition` | `automated` | 핵심 유지 | P1 |
| `large_test_fixture_split` | `task-20260421-runtime-decomposition` | `planned` | 지속 관리 | P2 |
| `sparse_workspace_preparation_runtime` | `task-20260422-auto-improve-workspace-preparation` | `automated` | 우선순위 하향 | 완료 |
| `telemetry_preservation_contract` | `task-20260422-auto-improve-workspace-preparation` | `automated` | 우선순위 하향 | 완료 |
| `typed_artifact_payload_contract_gap` | `task-20260422-code-review-report-260422-reconciliation` | `planned` | 핵심 유지 | P1 |
| `complexity_budget_hotspot_profile_gap` | `task-20260422-code-review-report-260422-reconciliation` | `automated` | 핵심 유지 | P1 |
| `output_path_policy_migration_gap` | `task-20260422-code-review-report-260422-reconciliation` | `automated` | 지속 관리 | P2 |
| `synthesis_template_localization_and_concept_gate` | `task-20260422-concept-synthesis-quality-review` | `automated` | 도메인별 지속 관리 | P3 |
| `concept_carryover_bridge_contract` | `task-20260422-concept-synthesis-quality-review` | `automated` | 도메인별 지속 관리 | P3 |
| `auto_improve_queue_threshold_history_followup` | `task-20260422-live-auto-improve-run-readiness` | `automated` | 핵심 유지 | P0 |
| `blocked_proposal_queue_policy_next` | `task-20260422-live-auto-improve-run-readiness` | `automated` | 핵심 유지 | P0 |
| `synthesis_refresh_presentation_contract_gap` | `task-20260422-synthesis-format-and-absorption-review` | `automated` | 도메인별 지속 관리 | P3 |
| `absorbed_source_title_first_labeling_gap` | `task-20260422-synthesis-format-and-absorption-review` | `automated` | 도메인별 지속 관리 | P3 |
| `new_synthesis_template_alignment_gap` | `task-20260422-synthesis-format-and-absorption-review` | `automated` | 도메인별 지속 관리 | P3 |
| `general_schema_loader_boundary_gap` | `task-20260423-structural-budget-schema-boundary` | `planned` | 핵심 유지 | P1 |

---

## 13. 부록 D — 이번 점검에서 별도 메모한 현재 코드 사실

- 현재 readiness는 `warn`, queue는 `ready=false`, runnable proposal은 `0`
- current outcome metrics는 `attempts_considered=7`, `session_reports_considered=0`
- structural complexity budget은 `pass`이지만 기본 monitored target은 14개
- 대형 hotspot은 budget 기본 감시 표면 바깥에 일부 존재
- direct bootstrap/sys.path 패턴이 여전히 여러 진입점에 분산
- schema loader fallback helper는 도입됐지만 전면 이관은 미완료
- local command runtime smoke에서는 interpreter boundary에 따른 종료 행태 차이가 관찰됨
- raw registry 검증 실패는 부분 추출 환경의 영향 가능성이 커 직접 결함 근거에서 제외

