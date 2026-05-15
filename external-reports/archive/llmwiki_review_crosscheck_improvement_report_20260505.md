# LLMwiki Review Crosscheck Improvement Report

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-05 (Asia/Seoul) |
| 보고서 파일 | `llmwiki_review_crosscheck_improvement_report_20260505.md` |
| 직접 검토한 신규 리뷰 1 | `llmwiki_post_review_integrated_report_20260505.md` |
| 직접 검토한 신규 리뷰 2 | `llmwiki_integrated_review_report_20260505.md` |
| 대조한 기존 리뷰 | `llmwiki14_post_review_delta_improvement_report_20260505.md` |
| 기준 리뷰 | `external-reports/llmwiki_two_integrated_reviews_actual_file_improvement_report_20260504.md` |
| 실제 ZIP | `LLMwiki(14).zip` |
| 실제 ZIP SHA-256 | `78a7cd8739ce4866a6c467d63e436d2a1e0ce290e31c1f0d1a8e757e9f30f145` |
| 실제 ZIP entry / files / dirs | 1,836 / 1,738 / 98 |
| 검증용 fresh extract | `/mnt/data/llmwiki_fresh_meta` |
| 핵심 판정 | 후속 구현이 상당히 반영된 conditional package이나 clean/machine release는 아직 차단. 두 리뷰의 대다수 결론은 유효하되, batch verify/source-tree mismatch와 subprocess 실패 표현은 실제 재검증 기준으로 정밀 보정 필요. |

---

## 1. 종합 결론

두 신규 리뷰와 기존 리뷰는 큰 방향에서 같은 결론에 도달한다. 현재 배포물은 기준 리뷰 이후 `status namespace`, external report provenance, operator summary reason, workflow dependency planner, schema sample regeneration, release closeout evidence 등 여러 핵심 개선이 실제 파일에 반영된 스냅샷이다. 그러나 이 스냅샷은 아직 **clean release** 또는 **machine release**가 아니며, 더 정확한 상태는 다음과 같다.

> **artifact-digest-sealed conditional package with improved release evidence surfaces, but blocked clean/machine release due to stale distribution provenance, incomplete full-suite evidence, accepted learning/index risk, recursive tmp contamination, test-runner instability, and subprocess timeout/drain race.**

이번 재검토에서 가장 중요한 보정점은 두 가지다.

1. `make release-closeout-batch-manifest-verify`는 현재 fresh extract 및 현재 Make target 기준으로 **통과**했다. 따라서 “fresh extract verify가 지금도 source_tree_fingerprint mismatch로 실패한다”는 표현은 현재 실제 파일 기준으로는 그대로 유지하면 안 된다. 다만 batch manifest의 `generated_at=2026-05-04T15:38:12Z` 이후 source-surface 파일 30개가 ZIP timestamp상 갱신되어 있어, **evidence-after-source-edit stale risk**는 여전히 P0로 남겨야 한다.
2. `make test-subprocess`는 단순히 항상 실패하는 lane이 아니라 **비결정적 race**다. fresh extract에서 1회 pass 후 반복 2회차에 `returncode=-15`, `timed_out=True`, `phase_observed=drain_after_signal`, stdout 수신 상태로 fail이 재현됐다. 즉 결론은 “실패 재현”보다 더 정확히는 **pass/fail이 섞이는 timeout/drain race**다.

따라서 두 리뷰의 권고 방향은 대체로 유효하지만, 향후 작업 지시서와 release gate 문구에서는 위 보정점을 반영해야 한다.

---

## 2. 검토 입력 및 무결성

### 2.1 리뷰 파일 무결성

| 파일 | SHA-256 앞 16자 | bytes | lines | title |
| --- | --- | --- | --- | --- |
| llmwiki_post_review_integrated_report_20260505.md | 8e4681639ab3b2a7… | 50,268 | 798 | # LLMwiki 통합 리뷰 보고서: Post-Review Delta & Actual Status Integrated Report |
| llmwiki_integrated_review_report_20260505.md | 548d44b004dba8cf… | 55,688 | 897 | # LLMwiki 리뷰 후속 통합 보고서 |
| llmwiki14_post_review_delta_improvement_report_20260505.md | 5a82afe325081980… | 42,520 | 702 | # LLMwiki ZIP 14 리뷰 이후 작업 및 잔여 개선 보고서 |
| llmwiki_two_integrated_reviews_actual_file_improvement_report_20260504.md | 0732f9c38ce4ce21… | 40,177 | 642 | # LLMwiki 두 통합 리뷰 실제 파일 대조 기반 개선 보고서 |


### 2.2 실제 ZIP 인벤토리

| 항목 | 값 |
| --- | --- |
| SHA-256 | 78a7cd8739ce4866a6c467d63e436d2a1e0ce290e31c1f0d1a8e757e9f30f145 |
| entries / files / dirs | 1,836 / 1,738 / 98 |
| compressed file bytes | 191,373,364 |
| uncompressed file bytes | 243,523,901 |
| timestamp range | 2026-04-12 16:03:06 ~ 2026-05-05 00:38:22 |
| 기준 리뷰 ZIP timestamp | 2026-05-04 19:07:46 |
| 기준 리뷰 이후 ZIP entries | 68 entries / 2,140,857 bytes |


### 2.3 최상위 경로 분포

| top-level | entry count |
| --- | --- |
| raw | 448 |
| ops | 442 |
| wiki | 418 |
| runs | 185 |
| tests | 154 |
| system | 74 |
| external-reports | 56 |
| <root> | 18 |
| .codex | 12 |
| tmp | 9 |
| .obsidian | 6 |
| tools | 6 |
| .github | 4 |
| .ouroboros | 2 |
| .vscode | 2 |


### 2.4 확장자 분포

| extension | file count |
| --- | --- |
| .md | 963 |
| .py | 328 |
| .json | 310 |
| .pdf | 62 |
| .txt | 27 |
| .yaml | 14 |
| .jsonl | 12 |
| .toml | 11 |
| <none> | 5 |
| .yml | 2 |
| .docx | 2 |
| .ini | 1 |
| .lock | 1 |


### 2.5 기준 리뷰 이후 변경 흔적

기준 리뷰 파일 `external-reports/llmwiki_two_integrated_reviews_actual_file_improvement_report_20260504.md`의 ZIP timestamp 이후 변경된 entry는 68개다. 이 수치는 git diff가 아니라 ZIP entry timestamp 기준이므로 packaging 과정의 timestamp 갱신을 포함할 수 있다. 그럼에도 현재 배포물만으로 확인 가능한 post-review delta의 직접 근거다.

| top-level | post-review entry count |
| --- | --- |
| ops | 50 |
| tests | 12 |
| runs | 2 |
| external-reports | 1 |
| Makefile | 1 |
| pyproject.toml | 1 |
| tools | 1 |


---

## 3. 두 신규 리뷰/기존 리뷰/실제 파일 대조 판정표

| 리뷰 주장 또는 결론 | 대조 판정 | 실제 파일 기준 확인 내용 |
| --- | --- | --- |
| 동일 체크포인트: ZIP 14/15/LLMwiki.zip는 SHA가 같은 동일 배포물 | 확인 | 실제 ZIP SHA `78a7cd8739ce4866a6c467d63e436d2a1e0ce290e31c1f0d1a8e757e9f30f145` 및 entry `1836` 확인. 업로드된 실제 파일명은 `LLMwiki(14).zip`이지만 리뷰들이 말한 hash/entry와 일치. |
| 기준 리뷰 이후 후속 구현이 실제 반영됨 | 확인 | 기준 리뷰 timestamp 이후 ZIP entry `68`개, scripts/schemas/tests/reports 중심 변경 확인. |
| status namespace 분리 및 batch manifest axis 도입 | 확인 | `batch_integrity_status=pass`, `clean_lane_status=fail`, `machine_release_status=blocked`, `operator_release_status=allowed` 확인. |
| required artifact digest sealing 10/10 유지 | 확인 | 10개 required artifact 모두 존재하고 SHA-256이 batch manifest와 일치. |
| clean release 및 machine release 차단 | 확인 | `clean_release_ready=False`, `machine_release_allowed=False`, `clean_lane_status=fail`, `machine_release_status=blocked`. |
| external report manifest two-layer provenance 구조 도입 | 확인 | `review_basis_zip`/`current_distribution_zip` 분리 구조 존재. |
| 현재 배포 ZIP provenance stale | 확인 | manifest의 current_distribution는 `LLMwiki(12).zip`/entry 1829이나 실제 ZIP은 `LLMwiki(14).zip`/entry 1836. |
| full-suite evidence 부재 | 확인 | `ops/reports/test-execution-summary-full.json` 없음, shard directory는 있으나 파일 없음, targeted summary만 존재. |
| subprocess lane 실패 | 수정 필요: 비결정적 race로 정정 | fresh extract에서 1회 pass 후 반복 2회차 fail을 재현. 따라서 “항상 실패”가 아니라 pass/fail이 섞이는 timeout/drain race로 표현해야 정확. |
| fresh extract batch manifest verify 실패/source_tree_fingerprint mismatch | 현재 Make target 기준 미재현 | fresh extract에서 현재 fingerprint `dd2e3bdfaeaa4410…`와 batch 값이 일치하고 `make release-closeout-batch-manifest-verify`도 통과. 단, batch `generated_at` 이후 source-surface file 30개가 있어 stale evidence-after-source-edit 위험은 유효. |
| release surface 31개가 evidence 이후 수정 | 부분 확인/정정 | batch manifest file timestamp 이후는 0개, batch manifest `generated_at` 이후 기준은 30개. 리뷰의 31개는 산정 기준 차이 또는 off-by-one 가능성. |
| recursive tmp hygiene 미해소 | 확인 | 원본 ZIP에 `tmp/**` 파일 7개 존재. 검증 과정 생성물은 제외하고 원본 ZIP 기준으로도 오염 존재. |
| workflow dependency planner 추가 | 확인 | script/schema/test/Make target/report 존재, check 및 test 8개 pass. 다만 `selected_change_path_count=0`. |
| pytest/report schema sample 계층 hang | 확인/심화 | direct unittest는 pass하나 `python3 -m pytest tests/test_report_schema_sample_regeneration.py`는 별도 kill 필요할 정도로 hang 재현. |
| release-provenance-clean timeout | 확인/단계 정정 | 300초 제한에서 artifact freshness와 raw_registry_preflight 이후 `raw_registry_cross_environment_matrix --require-live` 단계에서 timeout. 120초 제한에서는 artifact freshness 단계에서 조기 종료될 수 있었음. |


---

## 4. 실제 artifact 상태 상세

### 4.1 Batch manifest status axis

| axis | actual value |
| --- | --- |
| status | fail |
| batch_integrity_status | pass |
| release_authority_status | conditional_pass |
| semantic_release_status | conditional_pass |
| sealed_release_status | sealed_conditional_pass |
| artifact_generation_status | pass |
| artifact_digest_sealing_status | pass |
| source_tree_rebuild_status | pass |
| clean_lane_status | fail |
| machine_release_status | blocked |
| operator_release_status | allowed |
| source_tree_fingerprint | dd2e3bdfaeaa441019dedc1aee42c9c27820d470c758dc32f277c1a8a67cc7aa |


판정: status namespace 분리는 실제로 반영됐다. 다만 top-level `status=fail`과 axis-specific status가 병존하므로 consumer가 단일 `status`만 읽지 않도록 schema/deprecation/documentation을 더 강화해야 한다.

### 4.2 Required artifact digest sealing

| artifact | required | expected SHA 앞 16자 | actual SHA 앞 16자 | 판정 |
| --- | --- | --- | --- | --- |
| ops/reports/release-smoke-report.json | Y | 1a24cf6b0dae8433… | 1a24cf6b0dae8433… | 일치 |
| ops/reports/generated-artifact-index.json | Y | b74c48d08874e923… | b74c48d08874e923… | 일치 |
| ops/reports/artifact-freshness-report.json | Y | a97cf01883c61e1d… | a97cf01883c61e1d… | 일치 |
| ops/reports/test-execution-summary.json | Y | 8e61f21abbbaeecf… | 8e61f21abbbaeecf… | 일치 |
| ops/reports/release-closeout-summary.json | Y | 5b5fc08733fa2741… | 5b5fc08733fa2741… | 일치 |
| ops/reports/learning-readiness-signoff-revalidation.json | Y | 507f7f316590b750… | 507f7f316590b750… | 일치 |
| ops/reports/release-evidence-cohort.json | Y | c825e7caa0d64e7f… | c825e7caa0d64e7f… | 일치 |
| ops/reports/release-evidence-dashboard.json | Y | 7772e1055c86cdf7… | 7772e1055c86cdf7… | 일치 |
| ops/reports/release-lane-summary.json | Y | 05790c3fccf7f7dd… | 05790c3fccf7f7dd… | 일치 |
| ops/reports/release-clean-blocker-ledger.json | Y | 458a9b7cf15d32db… | 458a9b7cf15d32db… | 일치 |


판정: required artifact 10개는 모두 현재 파일 digest와 batch manifest digest가 일치한다. 이 부분은 두 리뷰와 기존 리뷰의 긍정적 평가가 실제 파일과 일치한다.

### 4.3 Release closeout summary

| field | actual value |
| --- | --- |
| release_readiness_state | conditional_pass |
| clean_release_ready | False |
| machine_release_allowed | False |
| operator_release_allowed | True |
| live_rerun_release_ready | True |
| source_tree_fingerprint | dd2e3bdfaeaa441019dedc1aee42c9c27820d470c758dc32f277c1a8a67cc7aa |
| summary.component_count | 7 |
| summary.ready_component_count | 6 |
| summary.blocker_count | 0 |
| summary.accepted_risk_instance_count | 2 |
| summary.accepted_risk_family_count | 2 |
| summary.release_blocking_risk_count | 1 |
| summary.advisory_risk_count | 1 |
| summary.source_tree_coherence_status | pass |
| summary.test_failure_lane_fail_count | 0 |
| summary.test_failure_lane_not_run_count | 0 |


잔여 downstream mismatch는 다음 2건이다.

| input | source path | expected SHA 앞 16자 | actual SHA 앞 16자 |
| --- | --- | --- | --- |
| artifact_freshness | ops/reports/artifact-freshness-report.json | 8f06249743fbadac… | a97cf01883c61e1d… |
| generated_index | ops/reports/generated-artifact-index.json | bfa78fa603da7f0d… | b74c48d08874e923… |


판정: `live_rerun_release_ready=True`와 source-tree coherence pass는 개선으로 인정된다. 그러나 `clean_release_ready=False`, `machine_release_allowed=False`, downstream mismatch 2건은 release finalization이 아직 완료되지 않았음을 의미한다.

### 4.4 External report reference manifest

| field | actual value |
| --- | --- |
| review_basis_zip | `{"name": "LLMwiki.zip", "sha256": "0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93", "entry_count": 1819, "source": "reported"}` |
| current_distribution_zip | `{"name": "LLMwiki(12).zip", "sha256": "470475533932575a0e42dc5e770b005290ee94e5775f9faa7707fc4f196cf209", "entry_count": 1829, "source": "reported"}` |
| actual uploaded ZIP | `LLMwiki(14).zip` / `78a7cd8739ce4866a6c467d63e436d2a1e0ce290e31c1f0d1a8e757e9f30f145` / entry `1836` |
| manifest summary | `{"report_count": 6, "basis_zip_known": true, "review_basis_zip_known": true, "current_distribution_zip_known": true, "archive_included": false, "excluded_file_count": 47}` |


판정: two-layer provenance 구조는 구현됐지만 `current_distribution_zip`이 실제 배포 ZIP을 가리키지 않는다. 이 문제는 수동 metadata 갱신 누락이 아니라 packaging finalizer 부재로 보는 것이 맞다.

### 4.5 Test evidence와 full-suite 공백

| field | actual value |
| --- | --- |
| test files | 136 |
| AST test function count | 904 |
| test-execution-summary.suite | report-contract-summary |
| test-execution-summary.represents_full_suite | False |
| test-execution-summary.counts | `{"passed": 132, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "warnings": 0}` |
| full_suite_evidence | `{"status": "not_represented", "required_command": "python -m pytest", "release_builder_environment": ".venv clean release-builder", "reason": "report-contract-summary is a targeted report-contract subset; use full release-builder evidence before treating this as full-suite proof."}` |
| ops/reports/test-execution-summary-full.json | 존재하지 않음 |
| ops/reports/test-execution-summary-shards/* | 비어 있음 |


가장 큰 test 파일은 다음과 같다.

| test functions | bytes | file |
| --- | --- | --- |
| 36 | 70453 | tests/test_makefile_static_gates.py |
| 32 | 60956 | tests/test_generated_report_contracts.py |
| 28 | 31937 | tests/test_report_schemas.py |
| 24 | 49516 | tests/test_release_closeout_summary.py |
| 21 | 19770 | tests/test_writer_output_paths.py |
| 20 | 71106 | tests/test_mutation_proposal.py |
| 20 | 51173 | tests/test_release_smoke.py |
| 17 | 21066 | tests/test_raw_registry_preflight.py |
| 16 | 46682 | tests/test_run_mechanism_experiment_steps.py |
| 16 | 37300 | tests/test_artifact_freshness_runtime.py |


판정: 132 passed summary는 report-contract targeted subset으로만 해석해야 한다. full-suite 품질 근거로 승격하면 안 된다.

### 4.6 Learning readiness / accepted risk / clean lane

| producer | 핵심 값 |
| --- | --- |
| operator summary | semantic=conditional_pass; sealed=sealed_conditional_pass; full_suite=not_run; learning_revalidation=due |
| operator test evidence | `{"primary_suite": "report-contract-summary", "primary_suite_scope": "report_contract_summary", "primary_represents_full_suite": false, "primary_status": "pass", "primary_passed_count": 132, "full_suite_status": "not_run", "full_suite_summary_load_status": "missing", "full_suite_reason": "full-suite summary artifact is missing or unreadable: missing"}` |
| operator learning | `{"load_status": "ok", "status": "attention", "revalidation_status": "due", "accepted_learning_risk": true, "release_effect": {"clean_release_effect": "conditional_operator_accepted", "operator_summary": "learning revalidation=due; release_readiness_state=conditional_pass; machine_release_allowed=False; operator_release_allowed=True"}}` |
| cohort clean_lane_contract | `{"status": "fail", "zero_deselection": true, "zero_accepted_risk_family": false, "strict_cohort_pass": true, "release_closeout_clean": false, "expired_risk_present": false, "expired_risk_count": 0, "deselected_test_count": 0, "clean_lane_blocking_family_count": 1, "total_accepted_risk_family_count": 2, "cohort_risk_count": 0, "failed_conditions": ["zero_accepted_risk_family", "release_closeout_clean"]}` |
| ledger summary | `{"blocker_count": 2, "accepted_risk_family_count": 2, "accepted_risk_instance_count": 2, "clean_lane_blocking_family_count": 1, "clean_lane_status": "fail", "conditional_lane_status": "pass", "machine_release_status": "blocked", "operator_release_status": "allowed", "release_authority_status": "conditional_pass"}` |
| learning revalidation | `{"status": "due", "window_days": 7, "window_ends_at": "2026-05-11T15:38:00Z", "clean_closeout_required": false, "status_reason": "learning readiness signoff expires within the revalidation window; release closeout evidence is present but metrics still leave the blocker open; release effect: release_readiness_state=conditional_pass; machine_release_allowed=False; operator_release_allowed=True; requires_accepted_risk_review=True"}` |
| learning release effect | `{"clean_release_effect": "conditional_operator_accepted", "release_readiness_state": "conditional_pass", "machine_release_allowed": false, "operator_release_allowed": true, "requires_accepted_risk_review": true, "operator_summary": "learning revalidation=due; release_readiness_state=conditional_pass; machine_release_allowed=False; operator_release_allowed=True"}` |
| auto improve readiness | `{"status": "learning_uncertain", "gate_effect": "review_required", "can_run": true, "likely_to_learn": false, "reasons": ["runnable proposal queue is non-empty", "shadow learning signals require operator review before this run can count as confirmed learning"], "metrics": {"attempts_considered": 7, "min_attempts_considered": 10, "session_reports_considered": 3, "session_calibration_status": "active", "telemetry_coverage_ratio": 0.0, "rework_count": 2, "hold_moving_average": 0.2857, "discard_moving_average": 0.1429, "defect_escape_pair_count": 1}, "signals": [{"id": "outcome_metrics_attempt_history_below_minimum", "severity": "warn", "detail": "attempts_considered=7 is below min_attempts_considered=10", "owner": "runtime-maintainer", "required_evidence": ["ops/reports/outcome-metrics.json summary.attempts_considered is at or above min_attempts_considered.", "recent attempts include finali…` |


판정: `operator_release_status=allowed`는 conditional operator release에 한정된다. clean/machine release는 accepted risk와 learning due 때문에 계속 닫히지 않는다.

### 4.7 Workflow dependency planner

| field | actual value |
| --- | --- |
| workflow_rule_count | 7 |
| selected_change_path_count | 0 |
| selected_workflow_count | 0 |
| dependency_edge_count | 160 |
| missing_dependency_count | 0 |
| unknown_change_path_count | 0 |


판정: planner 표면은 실제로 추가됐고 check/test도 통과했다. 다만 `selected_change_path_count=0`이므로 기준 리뷰 이후 68개 변경을 어떤 workflow에 연결해야 하는지에 대한 evidence가 없다. 현재 상태는 “planner 구현 완료, changed-files input 연결 미완”이다.

### 4.8 Artifact freshness / generated artifact index

| artifact | status/summary |
| --- | --- |
| artifact-freshness-report.status | pass |
| artifact-freshness-report.summary | `{"artifact_count": 196, "json_artifact_count": 196, "scanned_text_artifact_count": 246, "stale_artifact_count": 0, "mtime_sensitive_artifact_count": 0, "root_ephemeral_artifact_count": 0, "run_log_placeholder_count": 15, "unknown_currentness_artifact_count": 0, "non_utf8_text_artifact_count": 0, "missing_schema_count": 0, "missing_artifact_envelope_count": 0, "schema_invalid_artifact_count": 0, "schema_unavailable_artifact_count": 0, "safe_to_backfill_artifact_count": 196, "stable_contract_debt_artifact_count": 0, "stable_contract_debt_issue_count": 0, "mtime_sensitive_attention_artifact_count": 0, "mtime_sensitive_attention_issue_count": 0, "operational_attention_artifact_count": 0, "operational_attention_issue_count": 0}` |
| generated-artifact-index.status | attention |
| generated-artifact-index.summary | `{"ops_reports_root_file_count": 38, "task_improvement_observation_count": 40, "external_reports_root_file_count": 7, "external_reports_archive_file_count": 47, "run_directory_count": 10, "run_archive_directory_count": 3, "canonical_report_count": 52, "archive_candidate_count": 3}` |


판정: artifact freshness는 pass이고 schema/currentness 측면의 안정화는 확인된다. 그러나 generated index는 `attention`, archive candidate 3건이 남아 clean lane risk와 연결된다.

### 4.9 Recursive tmp hygiene

원본 ZIP 기준 `tmp/**` 파일은 7개다. 검증 실행 후 fresh working tree에는 `tmp/artifact-freshness-report-check.json`이 추가로 생성되므로, release ZIP 자체 평가에는 아래 원본 ZIP 목록만 사용해야 한다.

| path | bytes | ZIP timestamp |
| --- | --- | --- |
| tmp/_patch_vocab_refs.py | 1587 | 2026-05-04 00:30:32 |
| tmp/codex-plan-review/archive-execution-manifest.json | 18411 | 2026-04-30 02:02:10 |
| tmp/codex-plan-review/artifact-freshness-report.json | 224422 | 2026-04-30 02:02:22 |
| tmp/codex-plan-review/current-raw-registry-evidence-bundle.json | 4702 | 2026-04-30 14:03:32 |
| tmp/codex-plan-review/current-release-evidence-cohort-strict.json | 7492 | 2026-04-30 14:03:32 |
| tmp/codex-plan-review/raw-registry-cross-environment-matrix.json | 22403 | 2026-04-30 02:02:10 |
| tmp/codex-plan-review/release-closeout-summary.json | 12876 | 2026-04-30 02:02:10 |


판정: `tmp-json-clean`이 top-level `tmp/*.json` 중심이면 subdirectory 오염을 놓친다. release package mode에서는 `tmp/**` 전체 정책이 필요하다.

### 4.10 Source-tree fingerprint 및 generated_at 이후 source 변경 위험

| 항목 | 값 |
| --- | --- |
| batch manifest generated_at | 2026-05-04T15:38:12Z |
| batch manifest ZIP timestamp | 2026-05-05 00:38:12 |
| current release_source_tree_fingerprint | dd2e3bdfaeaa441019dedc1aee42c9c27820d470c758dc32f277c1a8a67cc7aa |
| batch manifest source_tree_fingerprint | dd2e3bdfaeaa441019dedc1aee42c9c27820d470c758dc32f277c1a8a67cc7aa |
| fingerprint match | True |
| source-surface files after batch manifest file timestamp | 0 |
| source-surface files after batch manifest generated_at | 30 |


source-surface files after batch manifest `generated_at`:

| ZIP timestamp | path |
| --- | --- |
| 2026-05-05 00:27:56 | Makefile |
| 2026-05-05 00:28:36 | ops/README.md |
| 2026-05-04 19:18:36 | ops/schemas/external-report-reference-manifest.schema.json |
| 2026-05-04 19:17:50 | ops/schemas/learning-readiness-signoff-revalidation.schema.json |
| 2026-05-04 19:17:04 | ops/schemas/operator-release-summary.schema.json |
| 2026-05-04 19:20:02 | ops/schemas/release-closeout-batch-manifest.schema.json |
| 2026-05-04 19:19:34 | ops/schemas/release-closeout-summary.schema.json |
| 2026-05-05 00:17:26 | ops/schemas/workflow-dependency-planner.schema.json |
| 2026-05-04 19:18:20 | ops/scripts/external_report_reference_manifest.py |
| 2026-05-04 19:17:38 | ops/scripts/learning_readiness_signoff_revalidation.py |
| 2026-05-04 19:17:00 | ops/scripts/operator_release_summary.py |
| 2026-05-04 19:19:54 | ops/scripts/release_closeout_batch_manifest.py |
| 2026-05-04 19:19:30 | ops/scripts/release_closeout_summary.py |
| 2026-05-05 00:16:36 | ops/scripts/schema_constants_runtime.py |
| 2026-05-04 19:15:48 | ops/scripts/wiki_manifest.py |
| 2026-05-05 00:34:10 | ops/scripts/workflow_dependency_planner.py |
| 2026-05-05 00:20:48 | pyproject.toml |
| 2026-05-05 00:19:54 | tests/fixtures/report_schema_samples.json |
| 2026-05-05 00:17:32 | tests/minimal_vault_runtime.py |
| 2026-05-04 19:18:48 | tests/test_external_report_reference_manifest.py |
| 2026-05-05 00:25:02 | tests/test_generated_report_contracts.py |
| 2026-05-04 19:17:56 | tests/test_learning_readiness_signoff_revalidation.py |
| 2026-05-05 00:28:02 | tests/test_makefile_static_gates.py |
| 2026-05-04 19:17:18 | tests/test_operator_release_summary.py |
| 2026-05-04 19:20:14 | tests/test_release_closeout_batch_manifest.py |
| 2026-05-04 19:19:44 | tests/test_release_closeout_summary.py |
| 2026-05-05 00:19:30 | tests/test_report_schema_sample_regeneration.py |
| 2026-05-04 19:15:52 | tests/test_source_tree_fingerprint_runtime.py |
| 2026-05-05 00:34:22 | tests/test_workflow_dependency_planner.py |
| 2026-05-05 00:17:36 | tools/regenerate_report_schema_samples.py |


판정: 현재 fingerprint mismatch는 재현되지 않는다. 다만 `generated_at`이 source-surface mtimes보다 과거인 파일이 많으므로, “source changed after last evidence generation”을 별도 진단해야 한다. 이 진단은 fingerprint mismatch와 별개로 필요하다.

---

## 5. 실행 검증 결과

| 명령/검증 | 결과 | 비고 |
| --- | --- | --- |
| fresh extract source fingerprint | pass | current `dd2e3bdfaeaa4410…` = batch `dd2e3bdfaeaa4410…` |
| make release-closeout-batch-manifest-verify PYTHON=python3 | pass | 현재 Make target은 tmp/*.json 확인 후 `--check` 수행. fresh extract에서 통과. |
| python3 -m ruff check ops/scripts tests tools | pass | All checks passed. |
| python3 -m mypy @ops/mypy-allowlist.txt | pass | Success: no issues found in 178 source files. |
| make artifact-freshness-check PYTHON=python3 | pass | 13.33초 내 완료. |
| make workflow-dependency-planner-check PYTHON=python3 | pass | candidate JSON 생성. |
| PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_workflow_dependency_planner.py -q | pass | 8 passed. |
| PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest generated/external/batch tests -q | pass | 45 passed, 80초 shell timeout 내 정상 exit 0. |
| PYTHONPATH=. python3 tests/test_report_schema_sample_regeneration.py -v | pass | 2 tests passed in 12.206s. |
| PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_report_schema_sample_regeneration.py -q | hang/fail | 60초 timeout process가 남아 수동 kill 필요. unittest와 pytest runner 경로의 차이 확인. |
| make test-subprocess PYTHON=python3 반복 | flaky fail | 1회 pass 후 2회차 fail: `returncode=-15`, `timed_out=True`, `phase_observed=drain_after_signal`, stdout `ok\n` 수신. |
| timeout 300s make release-provenance-clean PYTHON=python3 | timeout | ruff/mypy/artifact freshness/raw_registry_preflight 이후 cross-environment matrix 단계에서 timeout. |


주의: 실행 환경의 tool-level timeout과 long-running pytest hang 때문에 full release gate를 끝까지 완주했다고 주장할 수 없다. 본 보고서는 통과한 단위 검증과 재현된 실패/비결정성을 분리해서 해석한다.

---

## 6. 리뷰별 보정 사항

### 6.1 `llmwiki_post_review_integrated_report_20260505.md`

이 보고서는 artifact digest sealing, stale distribution provenance, full-suite 부재, learning due, workflow planner input 미연결, recursive tmp hygiene, clean/machine blocked 판정을 대체로 정확히 포착했다. 다만 다음 표현은 보정이 필요하다.

- `make release-closeout-batch-manifest-verify` 실패: 현재 실제 fresh extract와 현재 Make target 기준으로는 통과한다. 실패 대신 **generated_at 이후 source edit risk**로 재표현하는 것이 정확하다.
- subprocess lane: “그대로 실패”보다 **비결정적 timeout/drain race**가 정확하다. 반복 실행에서 pass와 fail이 모두 관찰된다.
- release-provenance-clean timeout phase: 현 재검증에서는 300초 기준 `raw_registry_cross_environment_matrix --require-live` 단계에서 timeout이 발생했다. 단기 timeout에서는 앞 단계에서 끊길 수 있으므로 phase-specific checkpoint가 필요하다.

### 6.2 `llmwiki_integrated_review_report_20260505.md`

이 보고서는 세 리뷰를 통합하면서 상태 요약과 개선 우선순위를 잘 정리했다. 특히 final package self-provenance, batch verify reproducibility, subprocess state machine, shard-first full-suite, accepted-risk taxonomy, bootstrap repair guard, large test ownership split은 유효한 개선 묶음이다. 보정이 필요한 부분은 다음과 같다.

- source_tree_fingerprint mismatch 자체는 현재 재현되지 않는다. 그러나 `generated_at` 이후 source-surface file 30개가 있으므로 stale evidence gate 필요성은 유지한다.
- “release-surface 31개”는 actual ZIP 기준으로 `generated_at` 이후 30개, batch manifest ZIP timestamp 이후 0개로 재산정된다.
- `test-execution-summary-shards/` empty는 실제로 확인됐다. 이 항목은 full-suite shard design이 의도만 있고 산출물이 없다는 증거로 유지한다.
- bootstrap repair guard는 실제 파일에서 구현 흔적을 확인하지 못했다. 따라서 현 상태에서는 “신규 개선안”이지 “반영된 기능”으로 쓰면 안 된다.

### 6.3 기존 `llmwiki14_post_review_delta_improvement_report_20260505.md`

기존 리뷰의 핵심 판단은 대부분 유지된다. 특히 ZIP 인벤토리, post-review 68 entries, 10개 required artifact digest 일치, external manifest stale, full-suite 부재, learning due, recursive tmp, workflow planner selected_change_path_count=0은 재확인됐다. 이번 교차검토를 통해 기존 리뷰에 추가해야 할 보정은 다음이다.

- batch verify failure는 현재 Make target 기준으로 제거 또는 조건부 표현해야 한다.
- subprocess는 deterministic failure가 아니라 flaky race로 표현해야 한다.
- pytest sample regeneration은 direct unittest와 pytest 경로가 다르게 동작하므로 runner-level issue로 분리해야 한다.
- release-provenance-clean은 phase checkpoint/resume 없이는 “어디까지 통과했는지”가 매번 달라 보일 수 있다.

---

## 7. 우선순위별 개선 보고

### 7.1 P0 개선안

| ID | 개선안 | 문제 | 실행 방식 | 완료 조건 |
| --- | --- | --- | --- | --- |
| P0-1 | Distribution self-provenance finalizer | 현재 manifest가 ZIP 12를 가리켜 실제 ZIP 14의 SHA/entry와 불일치 | ZIP 생성 직후 자기 ZIP SHA/entry를 계산해 `distribution-provenance.json` 및 external manifest에 봉인 | manifest current_distribution_zip == actual ZIP SHA/entry |
| P0-2 | Subprocess timeout/drain race 수정 | pass/fail 비결정; stdout 수신 후에도 SIGTERM/timeout 처리됨 | signal 전 `proc.poll()` 재확인, EOF/no-signal drain 우선, `signal_race_recovered` 상태 추가 | 20회 반복 `make test-subprocess` 무실패 또는 diagnostic-only 격리 |
| P0-3 | Full-suite shard evidence 생성 | 904 test 함수 중 canonical summary는 132개 targeted subset만 표현 | shard manifest, shard JSON, aggregate full summary, interrupted shard resume 도입 | `test-execution-summary-full.json` 존재 + represents_full_suite=true |
| P0-4 | Clean lane accepted-risk closure | learning/generated-index risk가 clean lane 차단 | learning signoff 갱신 또는 risk를 conditional-only로 격리; archive advisory 정리 | `clean_lane_status=pass`, `machine_release_status=allowed` |
| P0-5 | Evidence-after-source-edit gate | batch generated_at 이후 source-surface file 30개 존재 | mtime/content fingerprint 기준 “source changed after evidence” machine-readable diagnostic 추가 | source-surface 변경 후 final evidence 재생성 없으면 gate fail |
| P0-6 | Release-provenance-clean checkpoint/resume | 300초 내 live cross-env matrix에서 중단 | 각 phase JSON checkpoint와 resume target, timeout 진단 artifact 생성 | 실패해도 마지막 phase/reason/candidate artifact 보존 |


### 7.2 P1 개선안

| ID | 개선안 | 문제 | 실행 방식 | 완료 조건 |
| --- | --- | --- | --- | --- |
| P1-1 | Status taxonomy single source | top-level status와 axis별 status가 혼재 | dashboard/operator/lane schema에서 axis-specific 필드 required, top-level status deprecated | operator가 clean/machine/operator 상태를 한 줄에서 오독하지 않음 |
| P1-2 | Workflow planner changed-files 연결 | planner는 존재하나 selected_change_path_count=0 | post-review changed-files manifest를 planner input으로 연결 | 68개 post-review change에 필요한 workflow가 선택됨 |
| P1-3 | Recursive tmp/package mode policy | 원본 ZIP에 tmp/** 7개 포함 | local/review/release package mode별 inclusion/exclusion rule 적용 | release mode에서 tmp/** 0개 |
| P1-4 | Generated index archive advisory closure | generated-index attention이 clean blocker로 연결 | archive candidate 3건 처분 또는 advisory taxonomy 재분류 | generated_index.status=pass 또는 clean-neutral advisory |
| P1-5 | pytest runner isolation | unittest pass/pytest hang의 runner 차이 존재 | plugin autoload policy, per-test timeout, stuck process cleanup fixture | pytest 경로에서도 종료 보장 |
| P1-6 | Bootstrap repair guard | 리뷰 2의 고유 제안이나 실제 구현 근거 없음 | venv/bootstrap repair 중단 감지 및 safe resume guard 추가 | 중단된 bootstrap/repair 이후 clean diagnostics 제공 |


### 7.3 P2 개선안

| ID | 개선안 | 문제 | 실행 방식 | 완료 조건 |
| --- | --- | --- | --- | --- |
| P2-1 | Large test ownership split | 대형 테스트 파일 집중으로 hang triage 어려움 | owner/marker별 분리 및 slow/integration split | 단일 파일 장애가 full-suite 전체를 막지 않음 |
| P2-2 | Packaging mtime normalization | ZIP timestamp와 generated_at 혼재로 provenance 해석 난이도 증가 | SOURCE_DATE_EPOCH 또는 deterministic zip timestamp 정책 | 동일 source 재패키징 시 안정적인 timestamp 정책 |
| P2-3 | Post-review delta manifest artifact화 | 68개 변경 흔적이 ZIP timestamp 분석에 의존 | `post-review-delta-manifest.json` 생성 및 signer/digest 포함 | 리뷰 이후 변경분이 machine-readable evidence로 제공 |


---

## 8. 권장 실행 순서

1. **Distribution self-provenance finalizer 구현**: 현재 ZIP의 SHA/entry가 manifest에 반영되지 않는 문제를 먼저 닫는다. 이 문제는 모든 후속 리뷰의 기준점을 흔든다.
2. **Subprocess timeout/drain race 수정**: stdout을 이미 받은 정상 종료 subprocess를 SIGTERM/timeout으로 처리하는 state machine을 수정한다. 반복 실행 기준을 도입한다.
3. **Full-suite shard evidence 생성**: `test-execution-summary-shards/`를 실제 shard JSON으로 채우고 aggregate full summary를 canonical artifact로 만든다.
4. **accepted risk closure**: learning revalidation due와 generated-index archive advisory를 clean lane에서 제거하거나 conditional-only로 명시 격리한다.
5. **evidence-after-source-edit gate 추가**: `generated_at` 이후 source-surface edit을 machine-readable하게 검출하고 final evidence regeneration을 강제한다.
6. **release-provenance-clean checkpoint/resume**: long-running live matrix에서 중단돼도 마지막 phase와 artifact가 남도록 만든다.
7. **recursive tmp/package mode 정리**: release ZIP에는 `tmp/**`가 들어가지 않도록 mode별 inclusion policy를 적용한다.

---

## 9. Definition of Done

### 9.1 Provenance / packaging

- `external-reports/report-reference-manifest.json.current_distribution_zip.sha256`이 실제 ZIP SHA-256과 일치한다.
- ZIP entry count와 manifest entry count가 일치한다.
- `distribution-provenance.json` 또는 동등 artifact가 final ZIP 생성 이후 자동 작성된다.
- package mode가 `local_workspace`가 아니라 `release_distribution` 또는 이에 준하는 명확한 값으로 봉인된다.

### 9.2 Release authority

- `clean_lane_status=pass`.
- `machine_release_status=allowed`.
- `operator_release_status=allowed`는 clean/machine과 별도 축으로 유지하되, operator summary에 clean/machine 상태가 함께 표기된다.
- top-level `status`만으로 release authority를 판단하는 consumer가 없도록 schema/test가 고정된다.

### 9.3 Test evidence

- `ops/reports/test-execution-summary-full.json`이 존재한다.
- `represents_full_suite=true`가 명시된다.
- shard artifacts가 존재하고 aggregate summary와 digest가 일치한다.
- subprocess lane은 반복 실행에서 안정적으로 pass하거나 diagnostic-only로 명확히 격리된다.
- pytest 경로와 unittest 경로의 결과 차이가 제거된다.

### 9.4 Learning / accepted risk

- `learning-readiness-signoff-revalidation.status`가 `pass` 또는 clean-neutral 상태가 된다.
- `auto-improve-readiness.learning_readiness.likely_to_learn=True` 또는 operator-approved clean-neutral exception이 문서화된다.
- generated-index archive advisory가 resolved 또는 clean-neutral advisory로 재분류된다.
- accepted risk count의 producer별 포함관계가 schema에 고정된다.

### 9.5 Hygiene / reproducibility

- 원본 release ZIP에 `tmp/**` 파일이 없다.
- batch manifest `generated_at` 이후 source-surface edit이 있으면 final seal이 fail한다.
- release-provenance-clean은 중단 시에도 phase/reason/candidate artifact를 남긴다.
- ZIP mtime 정책이 deterministic하게 문서화된다.

---

## 10. 부록 A — 원본 ZIP의 recursive tmp 파일 목록

| path | bytes | ZIP timestamp |
| --- | --- | --- |
| tmp/_patch_vocab_refs.py | 1587 | 2026-05-04 00:30:32 |
| tmp/codex-plan-review/archive-execution-manifest.json | 18411 | 2026-04-30 02:02:10 |
| tmp/codex-plan-review/artifact-freshness-report.json | 224422 | 2026-04-30 02:02:22 |
| tmp/codex-plan-review/current-raw-registry-evidence-bundle.json | 4702 | 2026-04-30 14:03:32 |
| tmp/codex-plan-review/current-release-evidence-cohort-strict.json | 7492 | 2026-04-30 14:03:32 |
| tmp/codex-plan-review/raw-registry-cross-environment-matrix.json | 22403 | 2026-04-30 02:02:10 |
| tmp/codex-plan-review/release-closeout-summary.json | 12876 | 2026-04-30 02:02:10 |


## 11. 부록 B — Batch manifest generated_at 이후 source-surface 파일

| ZIP timestamp | path |
| --- | --- |
| 2026-05-05 00:27:56 | Makefile |
| 2026-05-05 00:28:36 | ops/README.md |
| 2026-05-04 19:18:36 | ops/schemas/external-report-reference-manifest.schema.json |
| 2026-05-04 19:17:50 | ops/schemas/learning-readiness-signoff-revalidation.schema.json |
| 2026-05-04 19:17:04 | ops/schemas/operator-release-summary.schema.json |
| 2026-05-04 19:20:02 | ops/schemas/release-closeout-batch-manifest.schema.json |
| 2026-05-04 19:19:34 | ops/schemas/release-closeout-summary.schema.json |
| 2026-05-05 00:17:26 | ops/schemas/workflow-dependency-planner.schema.json |
| 2026-05-04 19:18:20 | ops/scripts/external_report_reference_manifest.py |
| 2026-05-04 19:17:38 | ops/scripts/learning_readiness_signoff_revalidation.py |
| 2026-05-04 19:17:00 | ops/scripts/operator_release_summary.py |
| 2026-05-04 19:19:54 | ops/scripts/release_closeout_batch_manifest.py |
| 2026-05-04 19:19:30 | ops/scripts/release_closeout_summary.py |
| 2026-05-05 00:16:36 | ops/scripts/schema_constants_runtime.py |
| 2026-05-04 19:15:48 | ops/scripts/wiki_manifest.py |
| 2026-05-05 00:34:10 | ops/scripts/workflow_dependency_planner.py |
| 2026-05-05 00:20:48 | pyproject.toml |
| 2026-05-05 00:19:54 | tests/fixtures/report_schema_samples.json |
| 2026-05-05 00:17:32 | tests/minimal_vault_runtime.py |
| 2026-05-04 19:18:48 | tests/test_external_report_reference_manifest.py |
| 2026-05-05 00:25:02 | tests/test_generated_report_contracts.py |
| 2026-05-04 19:17:56 | tests/test_learning_readiness_signoff_revalidation.py |
| 2026-05-05 00:28:02 | tests/test_makefile_static_gates.py |
| 2026-05-04 19:17:18 | tests/test_operator_release_summary.py |
| 2026-05-04 19:20:14 | tests/test_release_closeout_batch_manifest.py |
| 2026-05-04 19:19:44 | tests/test_release_closeout_summary.py |
| 2026-05-05 00:19:30 | tests/test_report_schema_sample_regeneration.py |
| 2026-05-04 19:15:52 | tests/test_source_tree_fingerprint_runtime.py |
| 2026-05-05 00:34:22 | tests/test_workflow_dependency_planner.py |
| 2026-05-05 00:17:36 | tools/regenerate_report_schema_samples.py |


## 12. 부록 C — 핵심 판단 요약

- 후속 구현 반영: **확인**.
- clean release: **아님**.
- machine release: **blocked**.
- operator conditional release: **allowed**.
- artifact digest sealing: **10/10 확인**.
- actual ZIP provenance: **stale**.
- full-suite evidence: **부재**.
- subprocess lane: **비결정적 race**.
- batch verify mismatch: **현재 Make target 기준 미재현**, 단 stale evidence-after-source-edit gate 필요.
- recursive tmp hygiene: **미해소**.
- workflow planner: **구현됨, changed-files input 미연결**.

