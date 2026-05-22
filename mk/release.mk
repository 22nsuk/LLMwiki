REVIEW_ARCHIVE_OUT ?= build/review/llm-wiki-vnext-review.zip
REVIEW_ARCHIVE_REPORT_OUT ?= ops/reports/review-archive-report.json
REVIEW_ARCHIVE_PROFILE ?= clean
EXTERNAL_REPORT_REFERENCE_MANIFEST_OUT ?= external-reports/report-reference-manifest.json
EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE ?= advisory
EXTERNAL_REPORT_REVIEW_BASIS_ZIP_NAME ?=
EXTERNAL_REPORT_REVIEW_BASIS_ZIP_SHA256 ?=
EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT ?=
EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH ?=
EXTERNAL_REPORT_BASIS_ZIP_NAME ?=
EXTERNAL_REPORT_BASIS_ZIP_SHA256 ?=
EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT ?=
EXTERNAL_REPORT_BASIS_ZIP_PATH ?=
EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME = $(if $(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_NAME),$(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_NAME),$(EXTERNAL_REPORT_BASIS_ZIP_NAME))
EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256 = $(if $(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_SHA256),$(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_SHA256),$(EXTERNAL_REPORT_BASIS_ZIP_SHA256))
EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT = $(if $(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT),$(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_ENTRY_COUNT),$(EXTERNAL_REPORT_BASIS_ZIP_ENTRY_COUNT))
EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH = $(if $(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_BASIS_ZIP_PATH))
EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_NAME ?=
EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_SHA256 ?=
EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_ENTRY_COUNT ?=
EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH ?=
EXTERNAL_REPORT_ACTION_MATRIX_OUT ?= ops/reports/external-report-action-matrix.json
RELEASE_SMOKE_OUT ?= ops/reports/release-smoke-report.json
RELEASE_SMOKE_FAST_OUT ?= ops/reports/release-smoke-report-fast.json
RELEASE_SMOKE_REUSE_FROM ?= $(RELEASE_SMOKE_OUT)
RELEASE_SMOKE_CURRENT_CHECK_OUT ?= tmp/release-smoke-report-current-check.json
RELEASE_SOURCE_READY_COMMIT_MESSAGE ?= release: converge source-ready surfaces
RELEASE_SOURCE_READY_PRE_STATUS_OUT ?= tmp/release-source-ready-pre-status.json
RELEASE_SOURCE_READY_COMMIT_OUT ?= tmp/release-source-ready-commit.json
RELEASE_SOURCE_READY_AMEND_OUT ?= tmp/release-source-ready-amend.json
RELEASE_SOURCE_READY_FINAL_GUARD_AMEND_OUT ?= tmp/release-source-ready-final-guard-amend.json
RELEASE_SOURCE_READY_STATUS_OUT ?= tmp/release-source-ready-status.json
RELEASE_WORKTREE_CLEAN_CHECK_OUT ?= tmp/release-worktree-clean-check.json
SOURCE_PACKAGE_CHECK_ROOT ?= build/source-package-check
SOURCE_PACKAGE_TEST_SUMMARY_OUT ?= $(SOURCE_PACKAGE_CHECK_ROOT)/test-source-package-summary.json
SOURCE_PACKAGE_TEST_DESELECT_POLICY ?= ops/policies/source-package-test-deselections.json
SOURCE_PACKAGE_TEST_MARK_EXPR ?= not artifact_finalization and not release_sealing
SOURCE_PACKAGE_TESTS ?= tests
SOURCE_PACKAGE_TEST_DESELECTS ?= --deselect=tests/test_generated_report_contracts.py --deselect=tests/test_external_report_lifecycle_static.py
SOURCE_PACKAGE_ZIP_OUT ?= $(SOURCE_PACKAGE_CHECK_ROOT)/LLMwiki-source.zip
SOURCE_PACKAGE_ZIP_SMOKE_OUT ?= $(SOURCE_PACKAGE_CHECK_ROOT)/release-distribution-zip-smoke.json
SOURCE_PACKAGE_EXTRACT_PARENT ?= $(SOURCE_PACKAGE_CHECK_ROOT)/extract
SOURCE_PACKAGE_PYTHON ?= $(PUBLIC_PYTHON)
SOURCE_PACKAGE_CLEAN_EXTRACT_OUT ?= ops/reports/source-package-clean-extract.json
SOURCE_PACKAGE_CLEAN_EXTRACT_CANDIDATE_OUT ?= tmp/source-package-clean-extract.candidate.json
SOURCE_PACKAGE_HEARTBEAT_INTERVAL_SECONDS ?= 30
RELEASE_CLOSEOUT_SUMMARY_OUT ?= ops/reports/release-closeout-summary.json
RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT ?= tmp/release-closeout-summary.candidate.json
RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_OUT ?= tmp/release-clean-lane-evidence-review.json
RELEASE_EVIDENCE_DASHBOARD_OUT ?= ops/reports/release-evidence-dashboard.json
RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT ?= tmp/release-evidence-dashboard.candidate.json
RELEASE_EVIDENCE_COHORT_OUT ?= ops/reports/release-evidence-cohort.json
RELEASE_EVIDENCE_COHORT_STAGING_OUT ?= tmp/release-evidence-cohort.candidate.json
RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT ?= tmp/release-evidence-cohort-check.json
RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT ?= ops/reports/release-closeout-batch-manifest.json
RELEASE_CLOSEOUT_BATCH_MANIFEST_CANDIDATE_OUT ?= tmp/release-closeout-batch-manifest.candidate.json
RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA ?=
RELEASE_CLOSEOUT_DISTRIBUTION_ZIP ?=
RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE ?= UTC
RELEASE_CLOSEOUT_FIXED_POINT_OUT ?= ops/reports/release-closeout-fixed-point.json
RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT ?= tmp/release-closeout-fixed-point.candidate.json
RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_OUT ?= tmp/release-closeout-post-check-finalizer.json
RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_RECOMMENDED_TARGETS_OUT ?= tmp/release-closeout-post-check-finalizer-recommended-targets.txt
RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_PLAN_OUT ?= tmp/release-closeout-post-check-finalizer-plan.json
RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS ?=
RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_OUT ?= ops/reports/release-closeout-fixed-point-cost-trend.json
RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_CANDIDATE_OUT ?= tmp/release-closeout-fixed-point-cost-trend.candidate.json
RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS ?= 10
RELEASE_CLOSEOUT_FIXED_POINT_TIMEOUT_SECONDS ?= 600
RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT ?= ops/reports/release-closeout-finality-attestation.json
RELEASE_CLOSEOUT_FINALITY_ATTESTATION_CANDIDATE_OUT ?= tmp/release-closeout-finality-attestation.candidate.json
RELEASE_DISTRIBUTION_ZIP_OUT ?= build/release/LLMwiki-source.zip
RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT ?= build/release/release-distribution-zip-smoke.json
RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP ?= $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),$(RELEASE_DISTRIBUTION_ZIP_OUT))
RELEASE_CLOSEOUT_SEALED_ZIP_METADATA ?= $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP))
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT ?= tmp/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT ?= ops/reports/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT ?= build/release/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT ?= build/release/release-closeout-sealed-dry-run
RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP ?= $(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)/LLMwiki-source.zip
RELEASE_CLOSEOUT_SEALED_DRY_RUN_SMOKE_OUT ?= $(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)/release-distribution-zip-smoke.json
RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT ?= $(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)/external-report-reference-manifest.json
RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT ?= $(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)/release-closeout-batch-manifest.json
RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_OUT ?= $(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS ?= --no-fail
RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_OUT ?= ops/reports/release-evidence-closeout-self-check.json
RELEASE_AUDIT_PACK_OUT ?= build/release/release-audit-pack.zip
RELEASE_AUDIT_PACK_INCLUDE_OPTIONAL_PAYLOADS ?=
RELEASE_POST_SEAL_ATTESTATION_OUT ?= build/release/release-post-seal-attestation.json
RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP ?= $(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)
RELEASE_LANE_SUMMARY_OUT ?= ops/reports/release-lane-summary.json
RELEASE_LANE_SUMMARY_CANDIDATE_OUT ?= tmp/release-lane-summary.candidate.json
RELEASE_CLEAN_BLOCKER_LEDGER_OUT ?= ops/reports/release-clean-blocker-ledger.json
RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT ?= tmp/release-clean-blocker-ledger.candidate.json
OPERATOR_RELEASE_SUMMARY_OUT ?= ops/operator/operator-release-summary.json
RELEASE_CLOSEOUT_PROFILE ?= base
RELEASE_EVIDENCE_COHORT_POLICY ?= allowed_divergence_with_explicit_risk
RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE ?= embedded_currentness
RELEASE_EVIDENCE_COHORT_ZIP_METADATA ?=
LEARNING_READINESS_SIGNOFF_OUT ?= ops/reports/learning-readiness-signoff.json
LEARNING_READINESS_SIGNOFF_ACCEPTED_BY ?=
LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS ?= 7
LEARNING_READINESS_SIGNOFF_RISK_OWNER ?= runtime-maintainer
LEARNING_READINESS_SIGNOFF_REVALIDATION_CONDITION ?= Rerun make release-evidence-closeout and inspect learning readiness metrics before release.
LEARNING_READINESS_SIGNOFF_ROLLBACK_TRIGGER ?= Treat learning_blocked_by_review_required as active again if release evidence changes, learning telemetry regresses, or this signoff expires.
LEARNING_READINESS_SIGNOFF_NOTES ?=
LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT ?= ops/reports/learning-readiness-signoff-revalidation.json
LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT ?= tmp/learning-readiness-signoff-revalidation-check.json
LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS ?= 7
LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND ?= make release-evidence-converge PYTHON=.venv/bin/python
LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT ?= .venv clean release-builder
LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT ?= ops/reports/learning-claim-evidence-bundle.json
LEARNING_CLAIM_EVIDENCE_BUNDLE_CANDIDATE_OUT ?= tmp/learning-claim-evidence-bundle.candidate.json
LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_OUT ?= ops/reports/learning-confirmed-legacy-reconstruction.json
LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_CANDIDATE_OUT ?= tmp/learning-confirmed-legacy-reconstruction.candidate.json
LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT ?= ops/reports/learning-confirmed-evidence-cohort.json
LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT ?= tmp/learning-confirmed-evidence-cohort.candidate.json
LEARNING_CLAIM_UNLOCK_REVIEW_OUT ?= ops/reports/learning-claim-unlock-review.json
LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT ?= tmp/learning-claim-unlock-review.candidate.json
LEARNING_CLAIM_AUTO_UNLOCK_POLICY ?= ops/policies/learning-claim-auto-unlock.json
LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY ?= ops/policies/learning-claim-confirmed-improvement.json
LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY ?=
LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT ?=
LEARNING_DELTA_SCOREBOARD_OUT ?= ops/reports/learning-delta-scoreboard.json
LEARNING_DELTA_SCOREBOARD_CANDIDATE_OUT ?= tmp/learning-delta-scoreboard.candidate.json
LEARNING_CLAIM_ACTIVATION_REPORT_OUT ?= ops/reports/learning_claim_activation_report.json
LEARNING_CLAIM_ACTIVATION_REPORT_CANDIDATE_OUT ?= tmp/learning-claim-activation-report.candidate.json
SESSION_SYNOPSIS_OUT ?= ops/reports/session-synopsis.json
SESSION_SYNOPSIS_CANDIDATE_OUT ?= tmp/session-synopsis.candidate.json
SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT ?= ops/reports/self-improvement-negative-lessons.json
SELF_IMPROVEMENT_NEGATIVE_LESSONS_CANDIDATE_OUT ?= tmp/self-improvement-negative-lessons.candidate.json
REMEDIATION_BACKLOG_OUT ?= ops/reports/remediation-backlog.json
REMEDIATION_BACKLOG_CANDIDATE_OUT ?= tmp/remediation-backlog.candidate.json

.PHONY: release-evidence-converge release-evidence-converge-lane-guard release-evidence-converge-phase-1 release-evidence-converge-phase-2 release-evidence-converge-phase-3 release-finality-resettle release-verify-current release-sealed-verify release-evidence-closeout release-evidence-closeout-lane-guard release-distribution-zip release-distribution-zip-lane-guard test-source-package release-source-package-check release-evidence-closeout-sealed release-evidence-closeout-sealed-check release-evidence-closeout-sealed-dry-run release-evidence-closeout-sealed-dry-run-check release-authority-sealed-preflight release-evidence-refresh-fast release-builder-full release-builder-full-lane-guard release-smoke release-smoke-lane-guard release-smoke-full release-smoke-full-reuse release-smoke-full-current-check release-smoke-fast release-closeout-summary release-closeout-summary-report release-closeout-summary-conditional release-clean-lane-evidence-review release-evidence-cohort release-evidence-cohort-check learning-readiness-signoff learning-readiness-signoff-check learning-readiness-signoff-revalidation learning-readiness-signoff-revalidation-check release-evidence-dashboard release-evidence-dashboard-report release-lane-summary release-clean-blocker-ledger operator-release-summary learning-readiness-signoff-template learning-confirmed-legacy-reconstruction learning-claim-evidence-bundle learning-confirmed-evidence-cohort learning-claim-unlock-review learning-delta-scoreboard learning-claim-activation-report session-synopsis self-improvement-negative-lessons remediation-backlog review-archive external-report-reference-manifest external-report-reference-manifest-strict external-report-reference-manifest-release-check external-report-reference-manifest-settle external-report-action-matrix external-report-lifecycle-refresh release-worktree-clean-check release-converge-preflight release-converge-post release-converge release-converge-all-surfaces release-source-ready-snapshot release-source-ready-commit release-source-ready-post-commit-converge release-source-ready-amend release-source-ready-final-guard-amend release-source-ready-status release-source-ready release-check-preflight-converge release-check-core release-check-post-check release-check-post-converge release-check release-check-all-surfaces release-check-finalized release-conditional release-clean release-provenance-clean release-sbom-clean release-closeout-fixed-point release-closeout-post-check-finalizer-dry-run release-closeout-post-check-finalizer-ci-artifact release-closeout-fixed-point-cost-trend release-closeout-finality-attestation release-closeout-finality-verify release-closeout-batch-manifest-promote release-closeout-batch-manifest-replay-verify release-closeout-batch-manifest-verify release-audit-pack release-post-seal-attestation release-evidence-closeout-self-check

release-evidence-converge: release-evidence-converge-phase-3

release-evidence-closeout: release-evidence-converge
	@echo "release-evidence-closeout is a compatibility alias; prefer release-evidence-converge."

release-evidence-converge-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-evidence-converge

release-evidence-closeout-lane-guard: release-evidence-converge-lane-guard
	@echo "release-evidence-closeout-lane-guard is a compatibility alias; prefer release-evidence-converge-lane-guard."

release-evidence-converge-phase-1:
	$(MAKE) release-evidence-converge-lane-guard
	$(MAKE) refresh-generated-core
	$(MAKE) bootstrap-preflight
	$(MAKE) registry-preflight
	$(MAKE) static
	$(MAKE) report-schema-samples-check
	$(MAKE) external-report-reference-manifest-settle
	$(MAKE) release-smoke-full
	$(MAKE) release-source-package-check
	$(MAKE) generated-artifact-converge
	$(MAKE) test-execution-summary-report-contract-refresh
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) tmp-json-clean

release-evidence-converge-phase-2: release-evidence-converge-phase-1
	$(MAKE) test-execution-summary-full-refresh
	$(MAKE) test-execution-summary
	$(MAKE) function-budget-refactor-proposals
	$(MAKE) outcome-provenance-gate-policy
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) generated-artifact-converge
	$(MAKE) public-check-summary
	$(MAKE) learning-claim-evidence-bundle
	$(MAKE) learning-confirmed-evidence-cohort
	$(MAKE) learning-claim-unlock-review
	$(MAKE) learning-delta-scoreboard
	$(MAKE) learning-claim-activation-report
	$(MAKE) session-synopsis
	$(MAKE) self-improvement-negative-lessons
	$(MAKE) remediation-backlog
	$(MAKE) release-closeout-summary
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) release-evidence-dashboard
	$(MAKE) release-lane-summary
	$(MAKE) release-clean-blocker-ledger
	$(MAKE) generated-artifact-converge

release-evidence-converge-phase-3: release-evidence-converge-phase-2
	$(MAKE) test-artifact-finalization
	$(MAKE) release-closeout-post-check-finalizer-dry-run
	$(MAKE) release-closeout-fixed-point
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

release-finality-resettle:
	$(MAKE) workflow-dependency-planner
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-fixed-point
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

release-verify-current:
	$(MAKE) release-check-finalized
	$(MAKE) release-closeout-finality-verify

release-sealed-verify:
	$(MAKE) release-verify-current
	$(MAKE) release-evidence-closeout-sealed-check

release-distribution-zip: release-distribution-zip-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"

release-distribution-zip-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-distribution-zip

test-source-package:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(SOURCE_PACKAGE_TEST_SUMMARY_OUT)" --suite source-package --collect-nodeids --deselection-policy "$(SOURCE_PACKAGE_TEST_DESELECT_POLICY)" -- $(PYTHON) -m pytest -m "$(SOURCE_PACKAGE_TEST_MARK_EXPR)" $(SOURCE_PACKAGE_TESTS) $(SOURCE_PACKAGE_TEST_DESELECTS) $(PYTEST_SERIAL_FLAGS)

release-source-package-check:
	rm -rf "$(SOURCE_PACKAGE_CHECK_ROOT)"
	$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(SOURCE_PACKAGE_ZIP_OUT)" RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT="$(SOURCE_PACKAGE_ZIP_SMOKE_OUT)"
	@status=0; $(PYTHON) -m ops.scripts.source_package_clean_extract --vault "$(VAULT)" --source-zip "$(SOURCE_PACKAGE_ZIP_OUT)" --extract-parent "$(SOURCE_PACKAGE_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --test-summary-out "$(SOURCE_PACKAGE_TEST_SUMMARY_OUT)" --deselection-policy "$(SOURCE_PACKAGE_TEST_DESELECT_POLICY)" --pytest-mark-expr "$(SOURCE_PACKAGE_TEST_MARK_EXPR)" --tests "$(SOURCE_PACKAGE_TESTS)" --deselects="$(SOURCE_PACKAGE_TEST_DESELECTS)" --pytest-flags="$(PYTEST_SERIAL_FLAGS)" --zip-smoke-report "$(SOURCE_PACKAGE_ZIP_SMOKE_OUT)" --heartbeat-interval-seconds "$(SOURCE_PACKAGE_HEARTBEAT_INTERVAL_SECONDS)" --out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_CANDIDATE_OUT)" || status=$$?; if [ ! -f "$(SOURCE_PACKAGE_CLEAN_EXTRACT_CANDIDATE_OUT)" ]; then exit $$status; fi; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(SOURCE_PACKAGE_CLEAN_EXTRACT_CANDIDATE_OUT)" --out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)" --schema ops/schemas/source-package-clean-extract.schema.json --expected-artifact-kind source_package_clean_extract --expected-producer ops.scripts.source_package_clean_extract; exit $$status

release-evidence-closeout-sealed:
	$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"
	$(MAKE) external-report-reference-manifest-strict EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"
	$(MAKE) release-evidence-converge RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_CLOSEOUT_SEALED_ZIP_METADATA)" EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"
	$(MAKE) operator-release-summary
	$(MAKE) release-post-seal-attestation RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"
	$(MAKE) release-sealed-verify RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT="$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT)"

release-evidence-closeout-sealed-check:
	$(PYTHON) -m ops.scripts.release_closeout_sealed_rehearsal_check --vault "$(VAULT)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --out "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT)"

release-evidence-closeout-sealed-dry-run:
	rm -rf "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)"
	mkdir -p "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_ROOT)"
	$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)" RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT="$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_SMOKE_OUT)"
	$(PYTHON) -m ops.scripts.external_report_reference_manifest --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT)" --mode strict_review_release --basis-zip-path "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)" --current-distribution-zip-path "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)"
	$(PYTHON) -m ops.scripts.release_closeout_batch_manifest --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT)" --zip-metadata "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)" --zip-timestamp-timezone "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)"
	$(PYTHON) -m ops.scripts.release_closeout_sealed_rehearsal_check --vault "$(VAULT)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_DISTRIBUTION_ZIP)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_BATCH_MANIFEST_OUT)" --external-manifest "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_EXTERNAL_MANIFEST_OUT)" --out "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_OUT)" $(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS)

release-evidence-closeout-sealed-dry-run-check:
	$(MAKE) release-evidence-closeout-sealed-dry-run RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS=

release-authority-sealed-preflight:
	$(MAKE) release-evidence-closeout-sealed-dry-run RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_FLAGS=--allow-blocked-preflight
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_SEALED_DRY_RUN_CHECK_OUT)" --out "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT)" --schema ops/schemas/release-closeout-sealed-rehearsal-check.schema.json --expected-artifact-kind release_closeout_sealed_rehearsal_check

release-evidence-refresh-fast:
	$(MAKE) bootstrap-preflight
	$(MAKE) release-smoke-full-reuse
	$(MAKE) registry-preflight
	$(MAKE) auto-improve-readiness-report
	$(MAKE) tmp-json-clean
	$(MAKE) generated-artifact-converge
	$(MAKE) test-execution-summary-reuse
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) tmp-json-clean
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-conditional
	$(MAKE) release-evidence-cohort
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) release-evidence-dashboard-report
	@echo "release-evidence-refresh-fast refreshed partial evidence using reusable expensive evidence and operator-readable conditional closeout state."

release-builder-full-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-builder-full

release-builder-full: release-builder-full-lane-guard bootstrap-preflight static release-evidence-converge

release-smoke-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-smoke

release-smoke: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile full --out "$(RELEASE_SMOKE_OUT)"

release-smoke-full: release-smoke

release-smoke-full-reuse: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile full --out "$(RELEASE_SMOKE_OUT)" --reuse-if-current --reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"

release-smoke-full-current-check: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile full --out "$(RELEASE_SMOKE_CURRENT_CHECK_OUT)" --reuse-if-current --reuse-only --reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"

release-smoke-fast: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --out "$(RELEASE_SMOKE_FAST_OUT)"

release-closeout-summary:
	$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --schema ops/schemas/release-closeout-summary.schema.json --expected-artifact-kind release_closeout_summary --expected-producer ops.scripts.release_closeout_summary

# Write-only refresh target: keep closeout JSON shape current without enforcing final release authority.
release-closeout-summary-report:
	$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --no-fail
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --schema ops/schemas/release-closeout-summary.schema.json --expected-artifact-kind release_closeout_summary --expected-producer ops.scripts.release_closeout_summary

release-closeout-summary-conditional:
	$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --allow-conditional
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_SUMMARY_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --schema ops/schemas/release-closeout-summary.schema.json --expected-artifact-kind release_closeout_summary --expected-producer ops.scripts.release_closeout_summary

release-clean-lane-evidence-review:
	$(PYTHON) -m ops.scripts.release_clean_lane_evidence_review --vault "$(VAULT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --out "$(RELEASE_CLEAN_LANE_EVIDENCE_REVIEW_OUT)"

release-evidence-cohort:
	$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy "$(RELEASE_EVIDENCE_COHORT_POLICY)" --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)" $(if $(RELEASE_EVIDENCE_COHORT_ZIP_METADATA),--zip-metadata "$(RELEASE_EVIDENCE_COHORT_ZIP_METADATA)",) $(if $(filter strict_same_fingerprint,$(RELEASE_EVIDENCE_COHORT_POLICY)),--fail-on-attention --require-clean-lane,)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --out "$(RELEASE_EVIDENCE_COHORT_OUT)" --schema ops/schemas/release-evidence-cohort.schema.json --expected-artifact-kind release_evidence_cohort --expected-producer ops.scripts.release_evidence_cohort

release-evidence-cohort-check:
	$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy strict_same_fingerprint --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)" $(if $(RELEASE_EVIDENCE_COHORT_ZIP_METADATA),--zip-metadata "$(RELEASE_EVIDENCE_COHORT_ZIP_METADATA)",) --fail-on-attention --require-clean-lane

learning-readiness-signoff:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff --vault "$(VAULT)" --out "$(LEARNING_READINESS_SIGNOFF_OUT)" --accepted-by "$(LEARNING_READINESS_SIGNOFF_ACCEPTED_BY)" --expiry-days "$(LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS)" --risk-owner "$(LEARNING_READINESS_SIGNOFF_RISK_OWNER)" --revalidation-condition "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CONDITION)" --rollback-trigger "$(LEARNING_READINESS_SIGNOFF_ROLLBACK_TRIGGER)" $(if $(LEARNING_READINESS_SIGNOFF_NOTES),--notes "$(LEARNING_READINESS_SIGNOFF_NOTES)",)

learning-readiness-signoff-check:
	$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out tmp/learning-readiness-signoff-check-release-closeout-summary.json --profile "$(RELEASE_CLOSEOUT_PROFILE)" --no-fail

learning-readiness-signoff-revalidation:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff_revalidation --vault "$(VAULT)" --out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)" --required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)" --required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)"

learning-readiness-signoff-revalidation-check:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff_revalidation --vault "$(VAULT)" --out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT)" --window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)" --required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)" --required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)" --fail-on-due

release-evidence-dashboard:
	$(PYTHON) -m ops.scripts.release_evidence_dashboard --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_OUT)" --schema ops/schemas/release-evidence-dashboard.schema.json --expected-artifact-kind release_evidence_dashboard --expected-producer ops.scripts.release_evidence_dashboard

# Write-only refresh target: refresh dashboard evidence for downstream closeout aggregation.
release-evidence-dashboard-report:
	$(PYTHON) -m ops.scripts.release_evidence_dashboard --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)" --no-fail
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_EVIDENCE_DASHBOARD_CANDIDATE_OUT)" --out "$(RELEASE_EVIDENCE_DASHBOARD_OUT)" --schema ops/schemas/release-evidence-dashboard.schema.json --expected-artifact-kind release_evidence_dashboard --expected-producer ops.scripts.release_evidence_dashboard

release-lane-summary:
	$(PYTHON) -m ops.scripts.release_lane_summary --vault "$(VAULT)" --out "$(RELEASE_LANE_SUMMARY_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_LANE_SUMMARY_CANDIDATE_OUT)" --out "$(RELEASE_LANE_SUMMARY_OUT)" --schema ops/schemas/release-lane-summary.schema.json --expected-artifact-kind release_lane_summary --expected-producer ops.scripts.release_lane_summary

release-clean-blocker-ledger:
	$(PYTHON) -m ops.scripts.release_clean_blocker_ledger --vault "$(VAULT)" --out "$(RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLEAN_BLOCKER_LEDGER_CANDIDATE_OUT)" --out "$(RELEASE_CLEAN_BLOCKER_LEDGER_OUT)" --schema ops/schemas/release-clean-blocker-ledger.schema.json --expected-artifact-kind release_clean_blocker_ledger --expected-producer ops.scripts.release_clean_blocker_ledger

operator-release-summary:
	$(PYTHON) -m ops.scripts.operator_release_summary --vault "$(VAULT)" --out "$(OPERATOR_RELEASE_SUMMARY_OUT)"

learning-readiness-signoff-template:
	$(PYTHON) -m json.tool ops/templates/learning-readiness-signoff.json

learning-confirmed-legacy-reconstruction:
	$(PYTHON) -m ops.scripts.learning_confirmed_legacy_reconstruction --vault "$(VAULT)" --out "$(LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_CANDIDATE_OUT)" --out "$(LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_OUT)" --schema ops/schemas/learning-confirmed-legacy-reconstruction.schema.json --expected-artifact-kind learning_confirmed_legacy_reconstruction --expected-producer ops.scripts.learning_confirmed_legacy_reconstruction

learning-claim-evidence-bundle: learning-confirmed-legacy-reconstruction
	$(PYTHON) -m ops.scripts.learning_claim_evidence_bundle --vault "$(VAULT)" --out "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" --schema ops/schemas/learning-claim-evidence-bundle.schema.json --expected-artifact-kind learning_claim_evidence_bundle --expected-producer ops.scripts.learning_claim_evidence_bundle

learning-confirmed-evidence-cohort:
	$(PYTHON) -m ops.scripts.learning_confirmed_evidence_cohort --vault "$(VAULT)" --out "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT)" --evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" --confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT)" --out "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT)" --schema ops/schemas/learning-confirmed-evidence-cohort.schema.json --expected-artifact-kind learning_confirmed_evidence_cohort --expected-producer ops.scripts.learning_confirmed_evidence_cohort

learning-claim-unlock-review:
	$(PYTHON) -m ops.scripts.learning_claim_unlock_review --vault "$(VAULT)" --out "$(LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT)" $(if $(LEARNING_CLAIM_AUTO_UNLOCK_POLICY),--auto-policy "$(LEARNING_CLAIM_AUTO_UNLOCK_POLICY)",) --evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" $(if $(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY),--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)",) $(if $(LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY),--approved-by "$(LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY)",) $(if $(LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT),--reviewed-at "$(LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_UNLOCK_REVIEW_OUT)" --schema ops/schemas/learning-claim-unlock-review.schema.json --expected-artifact-kind learning_claim_unlock_review --expected-producer ops.scripts.learning_claim_unlock_review

learning-delta-scoreboard:
	$(PYTHON) -m ops.scripts.learning_delta_scoreboard --vault "$(VAULT)" --out "$(LEARNING_DELTA_SCOREBOARD_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_DELTA_SCOREBOARD_CANDIDATE_OUT)" --out "$(LEARNING_DELTA_SCOREBOARD_OUT)" --schema ops/schemas/learning-delta-scoreboard.schema.json --expected-artifact-kind learning_delta_scoreboard --expected-producer ops.scripts.learning_delta_scoreboard

learning-claim-activation-report: learning-delta-scoreboard
	$(PYTHON) -m ops.scripts.learning_claim_activation_report --vault "$(VAULT)" --out "$(LEARNING_CLAIM_ACTIVATION_REPORT_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_ACTIVATION_REPORT_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_ACTIVATION_REPORT_OUT)" --schema ops/schemas/learning-claim-activation-report.schema.json --expected-artifact-kind learning_claim_activation_report --expected-producer ops.scripts.learning_claim_activation_report

session-synopsis: learning-claim-activation-report
	$(PYTHON) -m ops.scripts.session_synopsis --vault "$(VAULT)" --out "$(SESSION_SYNOPSIS_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(SESSION_SYNOPSIS_CANDIDATE_OUT)" --out "$(SESSION_SYNOPSIS_OUT)" --schema ops/schemas/session-synopsis.schema.json --expected-artifact-kind session_synopsis --expected-producer ops.scripts.session_synopsis

self-improvement-negative-lessons: session-synopsis
	$(PYTHON) -m ops.scripts.self_improvement_negative_lessons --vault "$(VAULT)" --out "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_CANDIDATE_OUT)" --out "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT)" --schema ops/schemas/self-improvement-negative-lessons.schema.json --expected-artifact-kind self_improvement_negative_lessons --expected-producer ops.scripts.self_improvement_negative_lessons

remediation-backlog: self-improvement-negative-lessons session-synopsis
	$(PYTHON) -m ops.scripts.remediation_backlog --vault "$(VAULT)" --out "$(REMEDIATION_BACKLOG_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(REMEDIATION_BACKLOG_CANDIDATE_OUT)" --out "$(REMEDIATION_BACKLOG_OUT)" --schema ops/schemas/remediation-backlog.schema.json --expected-artifact-kind remediation_backlog --expected-producer ops.scripts.remediation_backlog

review-archive:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.review_archive --vault "$(VAULT)" --archive-out "$(REVIEW_ARCHIVE_OUT)" --out "$(REVIEW_ARCHIVE_REPORT_OUT)" --profile "$(REVIEW_ARCHIVE_PROFILE)"

external-report-reference-manifest:
	$(PYTHON) -m ops.scripts.external_report_reference_manifest --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_OUT)" --mode "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE)" $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME),--basis-zip-name "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256),--basis-zip-sha256 "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT),--basis-zip-entry-count "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),--basis-zip-path "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH),--current-distribution-zip-path "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_NAME),--current-distribution-zip-name "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_NAME)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_SHA256),--current-distribution-zip-sha256 "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_SHA256)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_ENTRY_COUNT),--current-distribution-zip-entry-count "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_ENTRY_COUNT)",)

external-report-reference-manifest-strict:
	$(PYTHON) -m ops.scripts.external_report_reference_manifest --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_OUT)" --mode strict_review_release $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME),--basis-zip-name "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256),--basis-zip-sha256 "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT),--basis-zip-entry-count "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT)",) --basis-zip-path "$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH))" --current-distribution-zip-path "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH)"

external-report-reference-manifest-release-check:
	$(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH),$(MAKE) external-report-reference-manifest-strict,$(MAKE) external-report-reference-manifest EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE=advisory)

external-report-reference-manifest-settle:
	$(MAKE) external-report-reference-manifest-release-check
	$(MAKE) external-report-reference-manifest-release-check

external-report-action-matrix:
	$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"

external-report-lifecycle-refresh:
	$(MAKE) external-report-reference-manifest-settle
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-evidence-cohort
	$(MAKE) release-evidence-dashboard-report

release-worktree-clean-check:
	$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --requested-mode git --out "$(RELEASE_WORKTREE_CLEAN_CHECK_OUT)" --strict

release-converge-preflight:
	$(MAKE) report-schema-samples-regenerate CLEAN_FIXTURE_REGENERATION_ALLOW_DIRTY_REPORTS=1
	$(MAKE) goal-runtime-local-evidence-refresh
	$(MAKE) test-execution-summary-report-contract-refresh-no-smoke

release-converge-post:
	$(MAKE) generated-artifact-converge
	$(MAKE) remediation-backlog
	$(MAKE) release-closeout-fixed-point
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required
	$(MAKE) test-artifact-finalization

release-converge:
	$(MAKE) release-converge-preflight
	$(MAKE) registry-preflight
	$(MAKE) release-smoke-full-reuse
	$(MAKE) release-converge-post

release-converge-all-surfaces:
	$(MAKE) release-converge
	$(MAKE) sync-public-policy
	$(MAKE) public-check-all
	$(MAKE) release-converge-post

release-source-ready-snapshot:
	$(PYTHON) -m ops.scripts.release_source_ready_commit --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)" --snapshot-only

release-source-ready-commit:
	$(PYTHON) -m ops.scripts.release_source_ready_commit --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_COMMIT_OUT)" --pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)" --message "$(RELEASE_SOURCE_READY_COMMIT_MESSAGE)"

release-source-ready-post-commit-converge:
	$(MAKE) auto-improve-readiness-worktree-guard
	$(MAKE) goal-runtime-local-evidence-refresh
	$(MAKE) generated-artifact-converge
	$(MAKE) remediation-backlog
	$(MAKE) release-closeout-fixed-point
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required

release-source-ready-amend:
	$(PYTHON) -m ops.scripts.release_source_ready_commit --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_AMEND_OUT)" --pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)" --amend --amend-of "$(RELEASE_SOURCE_READY_COMMIT_OUT)"

release-source-ready-final-guard-amend:
	$(MAKE) auto-improve-readiness-worktree-guard
	$(PYTHON) -m ops.scripts.release_source_ready_commit --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_FINAL_GUARD_AMEND_OUT)" --pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)" --amend --amend-of "$(RELEASE_SOURCE_READY_AMEND_OUT)"

release-source-ready-status:
	$(PYTHON) -m ops.scripts.release_source_ready_status --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_STATUS_OUT)"

release-source-ready:
	$(MAKE) release-source-ready-snapshot
	$(MAKE) release-converge-all-surfaces
	$(MAKE) release-source-ready-commit
	$(MAKE) release-source-ready-post-commit-converge
	$(MAKE) release-source-ready-amend
	$(MAKE) release-source-ready-final-guard-amend
	$(MAKE) release-check-all-surfaces
	$(MAKE) release-source-ready-status

release-check-preflight-converge: release-converge-preflight
	@echo "release-check-preflight-converge is a mutating compatibility alias; prefer release-converge-preflight before committing, then release-check."

release-check-post-converge: release-converge-post
	@echo "release-check-post-converge is a mutating compatibility alias; prefer release-converge-post before committing, then release-check."

release-check-post-check:
	$(MAKE) test-artifact-finalization
	$(MAKE) release-worktree-clean-check

release-check-core:
	$(MAKE) release-worktree-clean-check
	$(MAKE) test-report-contract-all
	$(MAKE) static
	$(MAKE) artifact-freshness-check
	$(MAKE) registry-preflight-check
	$(MAKE) lint
	$(MAKE) eval
	$(MAKE) stage2-eval
	$(MAKE) planning-gate
	$(MAKE) unit-tests-release-check
	$(MAKE) release-smoke-full-current-check

release-check:
	$(MAKE) release-check-core
	$(MAKE) release-check-post-check

release-check-all-surfaces:
	$(MAKE) release-check-core
	$(MAKE) sync-public-policy-check
	$(MAKE) public-check-all-check
	$(MAKE) release-check-post-check

release-check-finalized: release-check
	@echo "release-check is check-only and already includes artifact finalization plus clean worktree assertions."

release-conditional: release-evidence-refresh-fast

release-clean: release-check warning-budget release-evidence-converge release-evidence-cohort-check

release-provenance-clean: release-clean supply-chain-check

release-sbom-clean: release-provenance-clean sbom-readiness-check
release-closeout-fixed-point:
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT)" --max-iterations "$(RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS)" --timeout-seconds "$(RELEASE_CLOSEOUT_FIXED_POINT_TIMEOUT_SECONDS)" $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)",) $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--make-variable "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_OUT)" --schema ops/schemas/release-closeout-fixed-point.schema.json --expected-artifact-kind release_closeout_fixed_point_report --expected-producer ops.scripts.release_closeout_fixed_point
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --bootstrap-post-promote --max-iterations "$(RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS)" --timeout-seconds "$(RELEASE_CLOSEOUT_FIXED_POINT_TIMEOUT_SECONDS)" $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)",) $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--make-variable "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)
	$(MAKE) release-closeout-finality-attestation

release-closeout-post-check-finalizer-dry-run:
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --dry-run --out "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_OUT)" $(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS)

release-closeout-post-check-finalizer-ci-artifact:
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --dry-run --out "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_OUT)" --recommended-targets-out "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_RECOMMENDED_TARGETS_OUT)" --plan-out "$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_PLAN_OUT)" $(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS) --no-fail

release-closeout-fixed-point-cost-trend:
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point_cost_trend --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_CANDIDATE_OUT)" --no-fail
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_OUT)" --schema ops/schemas/release-closeout-fixed-point-cost-trend.schema.json --expected-artifact-kind release_closeout_fixed_point_cost_trend --expected-producer ops.scripts.release_closeout_fixed_point_cost_trend

release-closeout-finality-attestation:
	$(PYTHON) -m ops.scripts.release_closeout_finality_attestation --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT)" --schema ops/schemas/release-closeout-finality-attestation.schema.json --expected-artifact-kind release_closeout_finality_attestation --expected-producer ops.scripts.release_closeout_finality_attestation

release-closeout-finality-verify:
	$(PYTHON) -m ops.scripts.release_closeout_finality_attestation --vault "$(VAULT)" --attestation "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT)" --verify

release-closeout-batch-manifest-promote:
	$(PYTHON) -m ops.scripts.release_closeout_batch_manifest --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_CANDIDATE_OUT)" $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--zip-metadata "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)" --zip-timestamp-timezone "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--distribution-zip "$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)" --schema ops/schemas/release-closeout-batch-manifest.schema.json --expected-artifact-kind release_closeout_batch_manifest --expected-producer ops.scripts.release_closeout_batch_manifest

release-closeout-batch-manifest-replay-verify:
	@if [ -d tmp ] && find tmp -mindepth 1 -type f | grep -q .; then \
		echo "release-closeout-batch-manifest-replay-verify requires a clean tmp workspace"; \
		exit 1; \
	fi
	$(PYTHON) -m ops.scripts.release_closeout_batch_manifest --vault "$(VAULT)" --check $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--zip-metadata "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)" --zip-timestamp-timezone "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--distribution-zip "$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)

release-closeout-batch-manifest-verify: release-closeout-batch-manifest-replay-verify

release-audit-pack:
	$(PYTHON) -m ops.scripts.release_audit_pack --vault "$(VAULT)" --batch-manifest "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)" --out "$(RELEASE_AUDIT_PACK_OUT)" $(if $(RELEASE_AUDIT_PACK_INCLUDE_OPTIONAL_PAYLOADS),--include-optional-payloads,)

release-post-seal-attestation: operator-release-summary
	$(PYTHON) -m ops.scripts.release_post_seal_attestation build --vault "$(VAULT)" --out "$(RELEASE_POST_SEAL_ATTESTATION_OUT)" $(if $(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP),--source-zip-path "$(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP)",)

release-evidence-closeout-self-check:
	$(PYTHON) -m ops.scripts.release_evidence_closeout_self_check --vault "$(VAULT)" --batch-manifest "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --out "$(RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_OUT)"
