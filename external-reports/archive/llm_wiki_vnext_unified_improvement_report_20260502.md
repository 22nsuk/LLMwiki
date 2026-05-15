# LLM Wiki vNext 통합 개선 보고서

- 작성일: 2026-05-02 (Asia/Seoul)
- 작성 언어: 한국어
- 파일명: `llm_wiki_vnext_unified_improvement_report_20260502.md`
- 기준 체크포인트 ZIP SHA-256: `40ad7e10e25da049ca64e5f83dd4bc6802205bd941e2a54deeb12e69dc020219`
- 검토 기준 문서:
  - `external-reports/llm_wiki_vnext_integrated_improvement_report_final_20260501.md`
  - 업로드 리뷰 1: `llm_wiki_vnext_post_review_integrated_report_20260502.md`
  - 업로드 리뷰 2: `llm_wiki_vnext_integrated_post_review_report_20260502.md`
  - 기존 후속 리뷰: `llm_wiki_vnext_post_review_followup_report_20260502.md`
- 검토 대상 실물: `LLM Wiki vNext(75).zip` 전체 트리, `ops/reports/*`, `ops/scripts/*`, `Makefile`, `.github/workflows/*`, `tests/*`

---

## 1. Executive Summary

이번 통합 보고서의 결론은 단순한 “리뷰 합본”이 아니라, **기존 기준 리뷰 + 새 업로드 리뷰 2건 + 이전 후속 리뷰 + 실제 ZIP 내부 현재 파일 상태**를 함께 대조한 결과다.

핵심 결론은 다음과 같다.

1. **기준 리뷰(2026-05-01) 이후 구조적 개선은 실제로 많이 반영되었다.**
   - release decision state machine 도입
   - clean / conditional lane 분리
   - strict cohort 정상화
   - structured deselection 제거
   - canonical promote 적용 범위 확대

2. **현재 체크인 릴리스 상태는 여전히 `conditional_pass`다.**
   - `machine_release_allowed=false`
   - `operator_release_allowed=true`
   - `clean_release_ready=false`

3. **clean release를 막는 실질적 blocker는 여전히 accepted risk family와 closeout clean 조건이다.**
   - archive advisory
   - learning readiness signoff / revalidation
   - closeout 재생성 시 드러나는 source-tree coherence attention

4. **기존 통합 리뷰들 중 “광범위한 finalization drift” 서술은 실제 ZIP 기준으로 일부 교정이 필요하다.**
   실제 ZIP을 풀어 재검증한 결과:
   - `ops/reports/release-smoke-report.json`은 재생성 envelope fingerprint와 일치했다.
   - `ops/reports/generated-artifact-index.json`은 재생성 결과와 완전히 일치했다.
   - `ops/script-output-surfaces.json`도 재생성 결과와 완전히 일치했다.
   - 반면 **`ops/reports/release-closeout-summary.json`은 재생성 결과와 불일치**했고, 그 영향이 `release-evidence-cohort.json`, `release-evidence-dashboard.json`의 input fingerprint 계열로 전파되어 있었다.

5. 따라서 현재 상태를 가장 정확히 표현하면 다음과 같다.

> **현재 ZIP은 “대부분의 기반 산출물은 정합하지만, release-closeout 계열 최종 집계가 최신 상태를 완전히 반영하지 못한 conditional release 스냅샷”이다.**

즉, 이전 리뷰들이 지적한 “finalization/refresh 체인 불완전” 문제의 방향성은 맞지만, **실제 불일치 범위는 `release-closeout-summary`와 그 다운스트림 fingerprint 연쇄로 집중**되어 있으며, 리뷰 일부가 서술한 것처럼 `release-smoke`, `generated-artifact-index`, `script-output-surfaces` 전체가 모두 stale한 상태는 아니었다.

---

## 2. 검토 범위와 수행 방식

이번 점검은 다음 순서로 수행했다.

### 2.1 문서 검토

다음 문서를 끝까지 검토 대상으로 삼았다.

- 기준 리뷰: `external-reports/llm_wiki_vnext_integrated_improvement_report_final_20260501.md`
- 업로드 리뷰: `llm_wiki_vnext_post_review_integrated_report_20260502.md`
- 업로드 리뷰: `llm_wiki_vnext_integrated_post_review_report_20260502.md`
- 기존 후속 리뷰: `llm_wiki_vnext_post_review_followup_report_20260502.md`

### 2.2 실물 ZIP 검토

`LLM Wiki vNext(75).zip` 전체를 풀어 다음을 확인했다.

- ZIP 엔트리 수: **1,786**
- 일반 파일 수: **1,694**
- 디렉터리 수: **92**
- `ops/` 엔트리 수: **411**
- `tests/` 엔트리 수: **141**
- `external-reports/` 엔트리 수: **49**
- `runs/` 엔트리 수: **174**

### 2.3 실제 대조 방법

단순 텍스트 비교가 아니라 아래 방식으로 검토했다.

1. `ops/reports/*.json` 핵심 필드 실측
2. `Makefile`, `.github/workflows/*.yml` 정적 검토
3. `tests/test_*.py` 전체 함수 수 / 중복 이름 분석
4. 핵심 재생성 함수 직접 호출
   - `release_source_tree_fingerprint(...)`
   - `build_canonical_report_envelope(...)`
   - `generated_artifact_index.build_report(...)`
   - `script_output_surfaces.build_registry(...)`
   - `release_closeout_summary.build_report(...)`
   - `release_evidence_cohort.build_report(...)`
   - `release_evidence_dashboard.build_report(...)`

### 2.4 중요한 방법론상 메모

전체 pytest finalization lane 전체 재실행까지는 수행하지 않았다. 이 저장소는 plain `pytest` entrypoint를 허용하지 않고, 일부 고비용 재생성/검증은 실행 시간 제약이 있었다. 대신 **해당 테스트들이 실제로 비교하는 핵심 report builder와 fingerprint 함수를 직접 호출**하여, 체크인 산출물과 재생성 산출물의 실제 일치 여부를 검증했다.

이번 보고서의 사실 판정은 이 재생성 결과를 기준으로 교정했다.

---

## 3. 기준 리뷰 이후 실제로 반영된 작업분

아래 항목은 기준 리뷰(2026-05-01) 이후 실제 ZIP 기준으로 반영이 확인된 내용이다.

### 3.1 Release Decision State Machine 도입

`ops/reports/release-closeout-summary.json`에는 다음 필드가 실제로 존재한다.

- `release_readiness_state = conditional_pass`
- `machine_release_allowed = false`
- `operator_release_allowed = true`
- `requires_accepted_risk_review = true`
- `checked_in_release_ready = true`
- `live_rerun_release_ready = true`
- `conditional_release_ready = true`
- `clean_release_ready = false`

이는 기준 리뷰 당시 문제였던 단일 `release_ready` 중심 판정을 실질적으로 해소한 구조 변화다.

### 3.2 Clean / Conditional Lane 분리

`Makefile`에 다음 target이 실제 존재한다.

- `check-conditional`
- `check-clean`
- `release-conditional`
- `release-clean`
- `release-provenance-clean`
- `release-sbom-clean`

즉 lane 분리 자체는 구조적으로 완료되었다.

### 3.3 Strict Release Evidence Cohort 정상화

`ops/reports/release-evidence-cohort.json` 기준:

- `status = pass`
- `summary.issue_count = 0`
- `summary.strict_same_fingerprint = true`
- `summary.component_fingerprint_count = 1`
- `summary.modified_after_generated_at_count = 0`
- `summary.deselected_test_count = 0`

기준 리뷰 시점에 `fail`이던 strict cohort 자체는 정상화된 상태다.

### 3.4 Structured Deselection 제거

`ops/reports/test-execution-summary.json` 기준:

- `status = pass`
- `counts.passed = 116`
- `counts.failed = 0`
- `deselected_tests = []`
- `deselection_lifecycle.actual_deselected_count = 0`
- `deselection_lifecycle.max_allowed_deselected_count = 0`

다만 `stdout_tail`에는 `116 passed, 4 deselected`가 남아 있으며, 이는 policy deselection이 아니라 `-m 'not finalization'` marker deselection이다. 즉 **release risk deselection은 0건**이지만, **pytest marker deselection과 policy deselection은 여전히 구분 표시가 약하다.**

### 3.5 Canonical Promote 범위 확대

현재 promote 체계가 적용된 핵심 산출물은 다음과 같다.

- `release-closeout-summary`
- `release-evidence-cohort`
- `release-evidence-dashboard`
- `generated-artifact-index`
- `artifact-freshness`
- `test-execution-summary`
- `auto-improve-readiness`
- `script-output-surfaces`
- `raw-registry-cross-environment-evidence-bundle`

기준 리뷰의 “candidate → validate → promote 경로 확대” 요구는 상당 부분 반영되었다.

### 3.6 Output Surface / Entrypoint 정합성 유지

실측 결과:

- `pyproject.toml` console scripts: **52**
- `ops/direct-script-entrypoints.txt` 실제 entry 수: **52**
- `ops/scripts/*.py`: **171**
- `ops/script-output-surfaces.json` surfaces: **170**

entrypoint drift는 정리된 상태를 유지 중이다.

### 3.7 테스트/보호 장치 보강

다음 유형의 보호 테스트는 실제 저장소에 존재한다.

- source tree fingerprint 규칙
- manifest export symlink safety
- Makefile static gates
- generated report contract consistency

즉 구조상 “실패를 잡아낼 장치”는 이미 들어와 있다.

---

## 4. 현재 실제 파일 기준으로 남아 있는 작업분

### 4.1 전체 릴리스 상태는 여전히 conditional

`release-closeout-summary.json` checked-in 기준:

- `release_readiness_state = conditional_pass`
- `machine_release_allowed = false`
- `operator_release_allowed = true`
- `requires_accepted_risk_review = true`

따라서 clean release는 아직 아니다.

### 4.2 clean lane contract 실패

`release-evidence-cohort.json`의 clean lane contract는 다음과 같이 실패 상태다.

- `strict_cohort_pass = true`
- `zero_deselection = true`
- `cohort_risk_count = 0`
- `accepted_risk_count = 2`
- `zero_accepted_risk_family = false`
- `release_closeout_clean = false`
- `clean_lane_contract.status = fail`

즉 strict cohort나 structured deselection 문제가 아니라, **accepted risk family와 closeout clean 의미론이 clean lane blocker**다.

### 4.3 accepted risk 계열 미해소

현재 checked-in closeout이 직접 포함하는 accepted risk는 2건이다.

1. `generated_index_archive_advisory`
2. `learning_blocked_by_review_required`

그러나 dashboard는 accepted risk를 3건으로 집계한다. 이는 다음 세 gate 때문이다.

- `generated_index` → `generated_index_archive_advisory`
- `auto_improve_readiness` → `learning_blocked_by_review_required`
- `learning_readiness_signoff_revalidation` → `learning_readiness_signoff_attention`

즉 **closeout 2건 vs dashboard 3건** 불일치가 실제로 존재한다.

### 4.4 archive advisory 미해소

`ops/reports/generated-artifact-index.json`은 `status=attention`이다. 또한 `ops/reports/archive-execution-manifest.json` 기준:

- `summary.candidate_count = 3`
- `summary.planned_move_count = 3`
- `summary.applied_move_count = 0`

planned 상태로 남은 대상은 다음 3건이다.

- `external-reports/integrated_improvement_crosscheck_report_20260430_kr.md`
- `external-reports/llm_wiki_vnext_dual_integrated_review_crosscheck_improvement_report_20260430.md`
- `external-reports/two_review_crosscheck_improvement_report_20260430.md`

즉 archive prune은 아직 dry-run 수준에 머물러 있다.

### 4.5 learning readiness revalidation 미해소

`ops/reports/learning-readiness-signoff-revalidation.json` 기준:

- `status = attention`
- `revalidation.status = due`
- `signoff.signoff_status = active`
- `signoff.linked_blocker_id = learning_blocked_by_review_required`
- `signoff.expires_at = 2026-05-07T06:02:10Z`

또한 `ops/reports/auto-improve-readiness.json` 실측상:

- `can_execute_trial = true`
- `can_promote_result = false`
- `execution_readiness.status = pass`
- `learning_readiness.status = learning_uncertain`
- `learning_readiness.metrics.attempts_considered = 6`
- `learning_readiness.metrics.min_attempts_considered = 10`
- `learning_readiness.metrics.telemetry_coverage_ratio = 0.5`

즉 trial은 가능하지만 promotion/confirmed learning 판정은 여전히 막혀 있다.

### 4.6 CI / Release Workflow에 clean gate 미강제

`Makefile`에는 clean target이 존재하지만, `.github/workflows/release.yml` publish job에는 publish 전에 아래가 없다.

- `make release-clean`
- `make release-provenance-clean`
- `machine_release_allowed=true` 강제 검증

현재 workflow는 의존성 설치 후 곧바로 build / supply-chain artifact / PyPI publish로 이어진다. 따라서 **conditional 상태가 실수로 publish 경로까지 이어질 수 있는 설계상 틈**이 남아 있다.

---

## 5. 새 업로드 리뷰들과 실제 ZIP 대조 결과

이번 통합에서 가장 중요한 부분은 **리뷰 문서들끼리의 공통분모를 정리하는 것**보다, **그 주장이 실제 ZIP 현재 상태와 맞는지 교정하는 것**이었다.

### 5.1 실제 ZIP과 일치하는 주장

다음 주장은 실제 ZIP과 일치했다.

1. `conditional_pass` 상태
2. `machine_release_allowed=false`
3. `clean_release_ready=false`
4. strict cohort pass
5. structured deselection 0건
6. clean lane contract fail
7. archive candidate 3건
8. learning readiness revalidation due
9. dashboard accepted risk count 3
10. release workflow clean gate 미강제
11. duplicate test name 3개 그룹 존재
12. artifact-freshness가 test-execution-summary shard에 대해 4건의 fingerprint mismatch issue를 지적하고 있음

### 5.2 실제 ZIP과 다르게 과장되었거나 교정이 필요한 주장

기존 리뷰들 가운데 가장 크게 교정해야 하는 포인트는 다음이다.

#### 5.2.1 “release-smoke / generated-index / script-output-surfaces까지 모두 stale”라는 서술

실제 재생성 결과는 다음과 같았다.

- `release_source_tree_fingerprint(REPO_ROOT)` 결과: `f3dc81c29eb9d0d0a153b44ee5b0c15bcf611a2297aa27db91c9e00e1f683831`
- `release-smoke-report.json`의 `source_tree_fingerprint`와 `input_fingerprints`는 재생성 envelope와 일치
- `generated-artifact-index.json`은 재생성 결과와 **완전 일치**
- `script-output-surfaces.json`도 재생성 결과와 **완전 일치**

즉 **광범위한 base artifact stale**는 현재 ZIP 기준으로는 확인되지 않았다.

#### 5.2.2 현재 ZIP 전체 source tree fingerprint가 이미 다른 값(`a799...`)이라는 서술

실제 ZIP 추출본에서 계산한 현재 release source tree fingerprint는 **`f3dc81c2...`**로, 체크인된 core artifact와 일치했다. 따라서 이전 리뷰에 나온 `a799...` 값은 **이 ZIP 외부의 다른 작업 디렉터리 상태**를 반영했을 가능성이 크며, 이번 최종 통합 보고서의 기준 값으로 채택하면 안 된다.

### 5.3 실제로 남아 있는 finalization drift의 정확한 범위

실제 재생성 비교 결과, drift는 다음과 같이 이해하는 것이 가장 정확하다.

#### A. 정합한 checked-in artifact

- `ops/reports/release-smoke-report.json`
- `ops/reports/generated-artifact-index.json`
- `ops/script-output-surfaces.json`

#### B. 재생성 시 달라지는 핵심 artifact

- `ops/reports/release-closeout-summary.json`

재생성 closeout 결과의 핵심 차이:

- `accepted_risk_count_by_scope.total`: **2 → 3**
- `accepted_risk_count_by_scope.policy`: **1 → 2**
- `summary.accepted_risk_count`: **2 → 3**
- `summary.source_tree_coherence_status`: **pass → attention**
- 새롭게 포함되는 risk: `source_tree_coherence_attention`

즉 closeout은 현재 ZIP에서도 재생성 시 더 보수적으로 바뀐다.

#### C. downstream fingerprint drift가 발생하는 artifact

- `ops/reports/release-evidence-cohort.json`
- `ops/reports/release-evidence-dashboard.json`

이 둘은 **핵심 summary 자체가 크게 틀린 상태는 아니지만**, stale upstream closeout / freshness lineage 때문에 `input_fingerprints`가 재생성 결과와 달라진다.

요약하면,

> **실제 finalization drift는 “모든 artifact가 stale”가 아니라, “closeout이 stale하고 cohort/dashboard가 그 stale upstream fingerprint를 물고 있는 상태”로 보는 것이 정확하다.**

---

## 6. 기존 리뷰 이후 새로 식별되거나 더 명확해진 개선 포인트

### 6.1 closeout을 최종 authority로 두되, current-tree coherence를 더 직접 노출해야 함

현재 checked-in closeout은 `source_tree_coherence.status=pass`를 유지하지만, 같은 ZIP에서 closeout 재생성 시 `attention`으로 바뀐다. 이는 다음을 뜻한다.

- base source tree fingerprint 자체가 완전히 뒤집힌 것은 아님
- 그러나 closeout가 자신이 취합하는 upstream report 집합을 최신 current-tree 관점에서 다시 보면 더 보수적인 결과를 내야 함

권장 개선:

- closeout에 `current_recomputed_source_tree_coherence_status`를 별도 필드로 노출
- checked-in 기준과 regenerated 기준을 한 artifact 안에서 동시 제시
- `source_tree_coherence_attention`를 conditional accepted risk가 아니라 clean/conditional 모두의 하향 근거로 명시

### 6.2 closeout / cohort / dashboard의 batch finalization manifest 필요

이전 리뷰들의 방향성은 타당했다. 지금 필요한 것은 “모든 artifact stale”라는 표현이 아니라, **어떤 배치가 같은 finalization batch인지 기계적으로 고정하는 것**이다.

권장:

- `release-closeout-batch-manifest.json` 도입
- 포함 항목:
  - batch id
  - canonical artifact path 목록
  - batch source tree fingerprint
  - 각 artifact digest
  - dependency order
  - final authority artifact
  - clean / conditional 판정 스냅샷

### 6.3 dashboard accepted risk semantics 정규화

현재 dashboard는 accepted risk 3건, closeout은 2건이다. 운영자 관점에서 혼동이 있다.

권장 필드:

- `accepted_risk_instance_count`
- `accepted_risk_family_count`
- `release_blocking_risk_count`
- `advisory_risk_count`
- `operator_review_required_risk_count`

### 6.4 archive candidate 처리 자동화

현재 archive 관련 manifest는 dry-run만 수행했다. 권장 개선:

- `make generated-artifact-index-archive-prune-dry-run`
- `make generated-artifact-index-archive-prune`
- prune 이후 closeout / dashboard / cohort / artifact-freshness를 동일 batch로 재생성

### 6.5 learning readiness 의미 계층 분리

현재 상태는 “실행 가능하지만 promotion 불가”다. 이 의미를 릴리스 UI/리포트에서 더 명확히 분리해야 한다.

권장 계층:

- `runnable`
- `promotable`
- `learn-confirmed`
- `operator-signoff-bound`

### 6.6 pytest marker deselection과 policy deselection 구분

현재 summary에는 `deselected_tests=[]`인데 `stdout_tail`에는 `4 deselected`가 남아 있어 혼동된다.

권장:

- `policy_deselected_count`
- `pytest_marker_deselected_count`
- `lane_excluded_count`

을 별도 필드로 분리한다.

### 6.7 artifact-freshness top-level summary와 record-level operational attention의 관계 정리

현재 `artifact-freshness-report.json`의 top-level summary는 깨끗하지만, `ops/reports/test-execution-summary-shards/report-contract-summary.json` 레코드에는 다음 4건 issue가 존재한다.

- `test_target_fingerprint_mismatch:tests/test_generated_report_contracts.py`
- `test_target_fingerprint_mismatch:tests/test_makefile_static_gates.py`
- `test_target_fingerprint_mismatch:tests/test_report_schemas.py`
- `test_target_fingerprint_mismatch:tests/test_test_execution_summary.py`

즉 “freshness summary는 clean한데 record-level operational attention은 남는” 구조다.

권장:

- top-level summary에도 `operational_attention_artifact_count` 추가
- stable contract debt와 별도로 operational attention 계층을 올려서 표시

### 6.8 개발 환경 ephemeral artifact hard-exclude

기존 리뷰의 지적은 여전히 유효하다.

권장 hard-exclude:

- `.venv/`
- `.mypy_cache/`
- `.ruff_cache/`
- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- `dist/`
- `build/`
- `*.egg-info/`

또한 `Makefile`의 dev-install 기본 venv를 repository 바깥으로 두는 것이 바람직하다.

---

## 7. 테스트 관련 중복 여부 통합 평가

실제 저장소 기준으로 다시 계산한 결과는 다음과 같다.

- `tests/test_*.py` 파일 수: **125**
- test function 정의 수: **829**
- exact duplicate function body 그룹: **0**
- duplicate test function name 그룹: **3**

### 7.1 duplicate name 그룹

1. `test_execute_mutation_step_records_timeout_failure`
   - `tests/test_mechanism_run_mutation_step_runtime.py`
   - `tests/test_run_mechanism_experiment_steps.py`

2. `test_write_report_validates_schema`
   - `tests/test_make_target_inventory.py`
   - `tests/test_release_evidence_dashboard.py`

3. `test_write_report_validates_schema_and_stays_under_vault`
   - `tests/test_artifact_freshness_runtime.py`
   - `tests/test_bootstrap_preflight.py`
   - `tests/test_release_closeout_summary.py`

### 7.2 통합 판정

- **완전한 의미의 복붙 중복 테스트는 없다.**
- **이름 중복과 역할 유사성은 존재한다.**
- 즉 문제의 본질은 “중복 실행 비용 폭증”보다 **failure triage 가독성**과 **공통 helper 미추출**에 가깝다.

### 7.3 권장 정리 방향

- target-specific 함수명으로 rename
- schema write assertion helper 공통화
- fingerprint freshness assertion을 parameterized suite로 통합
- test tier membership manifest 도입 검토

---

## 8. 워크플로우 개선 방안

### 8.1 release workflow 강제 개선

`release.yml` publish 전에 최소 다음 중 하나를 강제해야 한다.

- `make release-clean`
- 권장: `make release-provenance-clean`

그리고 publish 직전 artifact 조건으로 다음을 확인해야 한다.

- `machine_release_allowed = true`
- `clean_release_ready = true`

### 8.2 conditional release 별도 workflow 분리

현재 구조에서는 conditional 상태와 clean 상태가 workflow 레벨에서 분리되지 않는다. 권장 방안은 다음과 같다.

- `release-clean.yml` → PyPI publish 가능
- `release-conditional.yml` → artifact upload / operator review bundle까지만 허용

### 8.3 release operator bundle 제공

artifact upload에 다음 묶음을 포함하는 것이 좋다.

- closeout
- dashboard
- cohort
- artifact freshness
- test summary
- archive execution manifest
- learning readiness signoff revalidation

### 8.4 batch finalization 전용 target 도입

권장 target 예시:

- `make release-finalize-batch`
- `make release-finalize-batch-verify`

권장 순서:

1. `script-output-surfaces`
2. `generated-artifact-index`
3. `artifact-freshness`
4. `test-execution-summary`
5. `release-smoke`
6. `release-closeout-summary`
7. `learning-readiness-signoff-revalidation`
8. `release-evidence-cohort`
9. `release-evidence-dashboard`
10. finalization verification

---

## 9. 우선순위별 실행 계획

### P0 — 바로 처리해야 하는 항목

1. **release-closeout-summary 재생성 및 재체크인**
   - 현재 ZIP 기준으로 실제 drift가 가장 분명한 핵심 artifact다.
   - 재생성 후 `accepted_risk_count`가 3으로 반영되는지 확인해야 한다.

2. **closeout downstream batch 재고정**
   - cohort/dashboard input_fingerprint를 closeout 최신값 기준으로 재동기화해야 한다.

3. **archive candidate 3건 처리**
   - archive 이동 또는 explicit waiver

4. **learning readiness signoff 재검증**
   - attempts / telemetry 기준을 만족시키거나, signoff를 새 closeout 기준으로 다시 갱신

5. **release workflow clean gate 강제**
   - publish 전에 clean gate를 강제하지 않으면 conditional artifact가 실수로 릴리스 경로에 진입할 수 있다.

### P1 — 구조 안정화

1. closeout batch manifest 도입
2. accepted risk family / instance semantics 통일
3. marker deselection vs policy deselection 분리
4. artifact-freshness operational attention 상향 노출
5. test tier membership manifest 도입

### P2 — 운영 UX / 유지보수성 개선

1. duplicate test name 정리
2. helper / parameterized suite 공통화
3. release decision state machine을 README/운영 문서에 반영
4. dev artifact hard-exclude / venv 외부화

---

## 10. 최종 판정

이번 최종 통합 점검 기준에서, 현재 저장소 상태는 다음처럼 정리하는 것이 가장 정확하다.

### 10.1 완료로 볼 수 있는 것

- release decision state machine 도입
- clean / conditional lane 구조 도입
- strict cohort 정상화
- structured deselection 제거
- canonical promote 확대
- entrypoint / output surface registry 유지
- release-smoke / generated-artifact-index / script-output-surfaces 정합성 유지

### 10.2 아직 미완료인 것

- clean release 진입
- accepted risk family 해소
- archive advisory 정리
- learning readiness signoff revalidation 해소
- release workflow clean gate 강제
- closeout lineage finalization 정합화

### 10.3 가장 중요한 한 줄 결론

> **이 ZIP은 “대부분의 기반 산출물은 정합하지만, release-closeout 최종 집계가 최신 operational risk를 완전히 반영하지 못한 상태의 conditional release 스냅샷”이다.**

즉, 기존 리뷰들의 핵심 방향은 대체로 타당하지만, **실제 drift 범위는 release-closeout 계열에 집중되어 있고, core artifact 전체가 광범위하게 stale하다는 표현은 현재 ZIP 기준으로는 과장**이다. 다음 액션은 광범위한 재작업이 아니라, **closeout lineage를 기준으로 한 짧고 강한 finalization 재고정**이어야 한다.

---

## 11. 부록: 핵심 수치 요약

### A. checked-in closeout 요약

- `release_readiness_state = conditional_pass`
- `machine_release_allowed = false`
- `operator_release_allowed = true`
- `requires_accepted_risk_review = true`
- `checked_in_release_ready = true`
- `live_rerun_release_ready = true`
- `conditional_release_ready = true`
- `clean_release_ready = false`
- `summary.accepted_risk_count = 2`
- `summary.source_tree_coherence_status = pass`

### B. regenerated closeout 요약

- `accepted_risk_count_by_scope.total = 3`
- `summary.accepted_risk_count = 3`
- `summary.source_tree_coherence_status = attention`
- 추가 accepted risk: `source_tree_coherence_attention`

### C. cohort 요약

- `status = pass`
- `summary.issue_count = 0`
- `summary.strict_same_fingerprint = true`
- `summary.component_fingerprint_count = 1`
- `summary.accepted_risk_count = 2`
- `clean_lane_contract.status = fail`

### D. dashboard 요약

- `status = attention`
- `summary.accepted_risk_count = 3`
- `summary.checked_in_fail_count = 0`
- `summary.live_rerun_fail_count = 0`
- `summary.live_rerun_not_run_count = 0`

### E. test summary 요약

- `status = pass`
- `counts.passed = 116`
- `counts.failed = 0`
- `deselected_tests = []`
- marker deselection 흔적: `4 deselected`

### F. duplicate test name 요약

- duplicate exact body: 0
- duplicate function name group: 3
- 총 test function 수: 829

