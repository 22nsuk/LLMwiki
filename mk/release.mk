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
RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT ?= tmp/release-smoke-report-fast-current-check.json
RELEASE_SOURCE_READY_COMMIT_MESSAGE ?= release: converge source-ready surfaces
RELEASE_SOURCE_READY_PRE_STATUS_OUT ?= tmp/release-source-ready-pre-status.json
RELEASE_SOURCE_READY_COMMIT_OUT ?= tmp/release-source-ready-commit.json
RELEASE_SOURCE_READY_STATUS_OUT ?= tmp/release-source-ready-status.json
RELEASE_WORKTREE_CLEAN_CHECK_OUT ?= tmp/release-worktree-clean-check.json
RELEASE_RUN_MANIFEST_OUT ?= build/release/release-run-manifest.json
RELEASE_SEALED_RUN_MANIFEST_OUT ?= build/release/release-sealed-run-manifest.json
RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT ?= build/release/release-auto-promotion-ready-manifest.json
RELEASE_AUTHORITY_INVENTORY_OUT ?= tmp/release-authority-inventory.json
RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT ?= build/release/release-auto-promotion-preflight.json
RELEASE_AUTO_PROMOTION_PRESEAL_OUT ?= build/release/release-auto-promotion-preseal.json
RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT ?= build/release/release-auto-promotion-goal-run-identity.json
RELEASE_SEALED_RUN_READY_PLAN_OUT ?= build/release/release-sealed-run-ready-plan.json
RELEASE_AUTO_PROMOTION_READY_PLAN_OUT ?= build/release/release-auto-promotion-ready-plan.json
RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT ?= $(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)
RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT ?= build/release/release-sealed-post-seal-attestation.json
RELEASE_RUN_READY_MAKE_BIN ?= make
RELEASE_RUN_READY_TIMEOUT_SECONDS ?= 7200
SOURCE_PACKAGE_SMOKE_ROOT ?= build/source-package-smoke
SOURCE_PACKAGE_SMOKE_OUT ?= $(SOURCE_PACKAGE_SMOKE_ROOT)/source-package-smoke.json
SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT ?= $(SOURCE_PACKAGE_SMOKE_ROOT)/extract
SOURCE_PACKAGE_SMOKE_PYTHON ?= $(PUBLIC_PYTHON)
SOURCE_PACKAGE_CLEAN_EXTRACT_OUT ?= ops/reports/source-package-clean-extract.json
SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT ?= tmp/source-package-clean-extract
SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT ?= $(SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT)/extract
SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT ?= tmp/source-package-clean-extract/test-execution-summary.json
SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTION_POLICY ?= ops/policies/report-contract-deselections.json
SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_MARK_EXPR ?= not release_sealing
SOURCE_PACKAGE_CLEAN_EXTRACT_TESTS ?= tests/test_release_run_manifest.py tests/test_source_tree_fingerprint_runtime.py
SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTS ?=
SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS ?= -q
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
RELEASE_AUTO_PROMOTION_RUN_MANIFEST_DISTRIBUTION_ZIP = $(shell $(PYTHON) -m ops.scripts.release_run_manifest --vault "$(VAULT)" --out "$(RELEASE_RUN_MANIFEST_OUT)" --print-distribution-zip 2>/dev/null)
RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP = $(strip $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),$(RELEASE_AUTO_PROMOTION_RUN_MANIFEST_DISTRIBUTION_ZIP)))
RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA = $(strip $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)))
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT ?= build/release/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_CANONICAL_OUT ?= ops/reports/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT ?= build/release/release-closeout-sealed-rehearsal-check.json
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST ?= build/release/release-closeout-batch-manifest.json
RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST ?= build/release/external-report-reference-manifest.json
RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT ?= build/release/external-report-reference-manifest.json
RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT ?= build/release/release-closeout-batch-manifest.json
RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT ?= build/release/release-evidence-closeout-self-check.json
RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT ?= build/release/operator-release-summary.json
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
RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST ?=
RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK ?=
RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY ?=
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
LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS ?= 14
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

.PHONY: release-run-ready release-run-ready-check release-sealed-run-ready release-sealed-run-ready-plan release-sealed-run-ready-check release-auto-promotion-goal-run-id-guard release-auto-promotion-preflight release-auto-promotion-preflight-check release-auto-promotion-safe-cleanup release-auto-promotion-preseal release-auto-promotion-preseal-check release-auto-promotion-ready release-auto-promotion-ready-plan release-auto-promotion-operator-summary release-auto-promotion-ready-check release-preflight-current release-test-current release-public-current release-package-current release-source-package-smoke release-source-package-clean-extract release-seal-current release-evidence-converge release-evidence-converge-lane-guard release-evidence-converge-phase-1 release-evidence-converge-phase-2 release-evidence-converge-phase-3 release-finality-resettle release-verify-current release-sealed-verify release-evidence-closeout release-evidence-closeout-lane-guard release-distribution-zip release-distribution-zip-lane-guard release-source-package-check release-evidence-closeout-sealed release-evidence-closeout-sealed-core-sidecars release-evidence-closeout-sealed-sidecars release-sealed-post-seal-attestation release-evidence-closeout-sealed-check release-evidence-closeout-sealed-dry-run release-evidence-closeout-sealed-dry-run-check release-authority-sealed-preflight release-evidence-refresh-fast release-builder-full release-builder-full-lane-guard release-smoke release-smoke-lane-guard release-smoke-full release-smoke-full-reuse release-smoke-full-current-check release-smoke-fast release-smoke-fast-current-check release-smoke-fast-refresh-check release-closeout-summary release-closeout-summary-report release-closeout-summary-conditional release-clean-lane-evidence-review release-evidence-cohort release-evidence-cohort-preseal-refresh release-evidence-cohort-check learning-readiness-signoff learning-readiness-signoff-check learning-readiness-signoff-revalidation learning-readiness-signoff-revalidation-check release-evidence-dashboard release-evidence-dashboard-report release-lane-summary release-clean-blocker-ledger operator-release-summary learning-readiness-signoff-template learning-confirmed-legacy-reconstruction learning-claim-evidence-bundle learning-confirmed-evidence-cohort learning-claim-unlock-review learning-delta-scoreboard learning-claim-activation-report session-synopsis self-improvement-negative-lessons remediation-backlog review-archive external-report-reference-manifest external-report-reference-manifest-strict external-report-reference-manifest-release-check external-report-reference-manifest-settle external-report-action-matrix external-report-lifecycle-refresh release-worktree-clean-check release-converge-preflight release-converge-post release-converge release-converge-all-surfaces release-source-ready-snapshot release-source-ready-prepare release-source-ready-commit release-source-ready-post-verify release-source-ready-status release-source-ready release-check-preflight-converge release-check-core release-check-post-check release-check-post-converge release-check release-check-all-surfaces release-check-finalized release-conditional release-clean release-provenance-clean release-sbom-clean release-closeout-fixed-point release-closeout-post-check-finalizer-dry-run release-closeout-post-check-finalizer-ci-artifact release-closeout-fixed-point-cost-trend release-closeout-finality-attestation release-closeout-finality-verify release-closeout-batch-manifest-promote release-closeout-batch-manifest-replay-verify release-closeout-batch-manifest-verify release-audit-pack release-post-seal-attestation release-evidence-closeout-self-check
.PHONY: release-authority-inventory

release-authority-inventory:
	$(PYTHON) -m ops.scripts.release_authority_inventory --vault "$(VAULT)" --out "$(RELEASE_AUTHORITY_INVENTORY_OUT)"

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
	$(MAKE) release-closeout-post-check-finalizer-dry-run
	$(MAKE) release-closeout-fixed-point
	$(MAKE) operator-release-summary
	$(MAKE) generated-artifact-converge
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

release-run-ready:
	$(PYTHON) -m ops.scripts.release_run_ready --vault "$(VAULT)" --out "$(RELEASE_RUN_MANIFEST_OUT)" --make-bin "$(RELEASE_RUN_READY_MAKE_BIN)" --timeout-seconds "$(RELEASE_RUN_READY_TIMEOUT_SECONDS)"

release-run-ready-check:
	$(PYTHON) -m ops.scripts.release_run_manifest --vault "$(VAULT)" --out "$(RELEASE_RUN_MANIFEST_OUT)" --check

release-sealed-run-ready-plan:
	$(PYTHON) -m ops.scripts.release_evidence_planner --vault "$(VAULT)" --stage sealed-run-ready --out "$(RELEASE_SEALED_RUN_READY_PLAN_OUT)" --require-ready

release-sealed-run-ready:
	$(MAKE) release-sealed-run-ready-plan
	$(MAKE) release-evidence-closeout-sealed-sidecars
	$(MAKE) release-sealed-post-seal-attestation
	$(MAKE) release-evidence-closeout-sealed-check RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT="$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"
	$(PYTHON) -m ops.scripts.release_sealed_run_manifest --vault "$(VAULT)" --out "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --post-seal-attestation "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)"

release-sealed-run-ready-check:
	$(PYTHON) -m ops.scripts.release_sealed_run_manifest --vault "$(VAULT)" --out "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --post-seal-attestation "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)" --check

release-auto-promotion-goal-run-id-guard:
	$(PYTHON) -m ops.scripts.release_goal_run_identity_guard --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --goal-run-id "$(GOAL_RUN_ID)" --goal-run-id-origin "$(origin GOAL_RUN_ID)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --check

release-auto-promotion-preflight:
	$(MAKE) release-auto-promotion-goal-run-id-guard
	$(MAKE) release-smoke-fast-refresh-check
	$(MAKE) test-execution-summary-report-contract
	$(MAKE) artifact-freshness-refresh-check
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) tmp-json-clean
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preflight --out "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)"

release-auto-promotion-preflight-check:
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preflight --out "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --check

release-auto-promotion-safe-cleanup:
	$(MAKE) goal-runtime-clean-transient
	$(MAKE) tmp-json-clean
	$(PYTHON) -m ops.scripts.backfill_archived_run_artifacts --vault "$(VAULT)"
	$(MAKE) generated-artifact-index
	$(MAKE) artifact-freshness-refresh-check
	@if [ -n "$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" ]; then \
		$(MAKE) external-report-reference-manifest-release-check EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
		$(MAKE) release-closeout-batch-manifest-promote RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
		$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
	else \
		$(MAKE) external-report-reference-manifest-release-check; \
	fi
	$(MAKE) release-closeout-summary-report
	$(MAKE) tmp-json-clean

release-auto-promotion-preseal:
	$(MAKE) release-auto-promotion-goal-run-id-guard
	$(MAKE) release-run-ready-check
	$(MAKE) bootstrap-preflight
	$(MAKE) registry-preflight
	$(MAKE) release-smoke-full-current-check
	$(MAKE) release-smoke-fast-refresh-check
	$(MAKE) release-auto-promotion-safe-cleanup
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) release-evidence-cohort-preseal-refresh RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"
	$(MAKE) release-evidence-dashboard-report
	$(MAKE) release-lane-summary
	$(MAKE) release-clean-blocker-ledger
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) tmp-json-clean
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preseal --out "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)"

release-auto-promotion-preseal-check:
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preseal --out "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --check

release-auto-promotion-ready-plan:
	$(PYTHON) -m ops.scripts.release_evidence_planner --vault "$(VAULT)" --stage auto-promotion-ready --out "$(RELEASE_AUTO_PROMOTION_READY_PLAN_OUT)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --require-ready

release-auto-promotion-operator-summary:
	$(PYTHON) -m ops.scripts.operator_release_summary --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" --self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"

release-auto-promotion-ready:
	$(MAKE) release-auto-promotion-ready-plan
	$(PYTHON) -m ops.scripts.release_auto_promotion_ready --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)"

release-auto-promotion-ready-check:
	$(PYTHON) -m ops.scripts.release_auto_promotion_ready --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --check

release-preflight-current:
	$(MAKE) release-worktree-clean-check

release-test-current:
	$(MAKE) static
	$(MAKE) report-schema-samples-check
	$(MAKE) test-execution-summary-report-contract
	$(MAKE) test-execution-summary-full-current-or-refresh

release-public-current:
	$(MAKE) public-check-summary-check

release-package-current:
	$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"

release-source-package-smoke:
	rm -rf "$(SOURCE_PACKAGE_SMOKE_ROOT)"
	$(PYTHON) -m ops.scripts.source_package_smoke --vault "$(VAULT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --extract-parent "$(SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --out "$(SOURCE_PACKAGE_SMOKE_OUT)"

release-source-package-clean-extract:
	rm -rf "$(SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT)"
	$(PYTHON) -m ops.scripts.source_package_clean_extract --vault "$(VAULT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --extract-parent "$(SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --test-summary-out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT)" --deselection-policy "$(SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTION_POLICY)" --pytest-mark-expr "$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_MARK_EXPR)" --tests "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TESTS)" --deselects "$(SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTS)" --pytest-flags="$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS)" --zip-smoke-report "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)" --out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"

release-seal-current:
	$(MAKE) release-evidence-closeout-sealed-sidecars
	$(MAKE) release-post-seal-attestation RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK="$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)" RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY="$(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)"
	$(MAKE) release-evidence-closeout-sealed-check RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT="$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"

release-distribution-zip: release-distribution-zip-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"

release-distribution-zip-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-distribution-zip

release-source-package-check:
	$(MAKE) release-package-current
	$(MAKE) release-source-package-smoke
	$(MAKE) release-source-package-clean-extract

release-evidence-closeout-sealed:
	$(MAKE) release-worktree-clean-check
	$(MAKE) release-package-current
	$(MAKE) release-seal-current

release-evidence-closeout-sealed-core-sidecars:
	$(PYTHON) -m ops.scripts.external_report_reference_manifest --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)" --mode strict_review_release --basis-zip-path "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --current-distribution-zip-path "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"
	$(PYTHON) -m ops.scripts.release_closeout_batch_manifest --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" --zip-metadata "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --zip-timestamp-timezone "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"
	$(PYTHON) -m ops.scripts.release_evidence_closeout_self_check --vault "$(VAULT)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --out "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"
	$(MAKE) tmp-json-clean

release-evidence-closeout-sealed-sidecars:
	$(MAKE) release-evidence-closeout-sealed-core-sidecars
	$(PYTHON) -m ops.scripts.operator_release_summary --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" --self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"

release-sealed-post-seal-attestation:
	$(PYTHON) -m ops.scripts.release_sealed_post_seal_attestation --vault "$(VAULT)" --out "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" --external-manifest "$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)" --self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"

release-evidence-closeout-sealed-check:
	$(PYTHON) -m ops.scripts.release_closeout_sealed_rehearsal_check --vault "$(VAULT)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST)" --external-manifest "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST)" --out "$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT)"

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

release-smoke-fast-current-check: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release_smoke --vault "$(VAULT)" --profile fast --out "$(RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT)" --reuse-if-current --reuse-only --reuse-from "$(RELEASE_SMOKE_FAST_OUT)"

release-smoke-fast-refresh-check:
	@if $(MAKE) release-smoke-fast-current-check; then \
		echo "fast release smoke evidence is current; reused $(RELEASE_SMOKE_FAST_OUT)"; \
	else \
		$(MAKE) release-smoke-fast; \
		$(MAKE) release-smoke-fast-current-check; \
	fi

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

release-evidence-cohort-preseal-refresh:
	$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy strict_same_fingerprint --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)" $(if $(RELEASE_EVIDENCE_COHORT_ZIP_METADATA),--zip-metadata "$(RELEASE_EVIDENCE_COHORT_ZIP_METADATA)",)
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

learning-confirmed-evidence-cohort: learning-claim-evidence-bundle
	$(PYTHON) -m ops.scripts.learning_confirmed_evidence_cohort --vault "$(VAULT)" --out "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT)" --evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" --confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT)" --out "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT)" --schema ops/schemas/learning-confirmed-evidence-cohort.schema.json --expected-artifact-kind learning_confirmed_evidence_cohort --expected-producer ops.scripts.learning_confirmed_evidence_cohort

learning-claim-unlock-review: learning-confirmed-evidence-cohort
	$(PYTHON) -m ops.scripts.learning_claim_unlock_review --vault "$(VAULT)" --out "$(LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT)" $(if $(LEARNING_CLAIM_AUTO_UNLOCK_POLICY),--auto-policy "$(LEARNING_CLAIM_AUTO_UNLOCK_POLICY)",) --evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" $(if $(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY),--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)",) $(if $(LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY),--approved-by "$(LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY)",) $(if $(LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT),--reviewed-at "$(LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_UNLOCK_REVIEW_OUT)" --schema ops/schemas/learning-claim-unlock-review.schema.json --expected-artifact-kind learning_claim_unlock_review --expected-producer ops.scripts.learning_claim_unlock_review

learning-delta-scoreboard: learning-claim-unlock-review
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
	$(MAKE) report-schema-samples-regenerate
	$(MAKE) goal-runtime-local-evidence-refresh
	$(MAKE) test-execution-summary-report-contract-refresh-no-smoke

release-converge-post:
	$(MAKE) generated-artifact-converge
	$(MAKE) remediation-backlog
	$(MAKE) release-closeout-fixed-point
	$(MAKE) operator-release-summary
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-fixed-point
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required

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

release-source-ready-prepare:
	$(MAKE) release-source-ready-snapshot
	$(MAKE) release-converge-all-surfaces
	$(MAKE) test-execution-summary-full-current-or-refresh

release-source-ready-commit:
	$(PYTHON) -m ops.scripts.release_source_ready_commit --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_COMMIT_OUT)" --pre-status "$(RELEASE_SOURCE_READY_PRE_STATUS_OUT)" --message "$(RELEASE_SOURCE_READY_COMMIT_MESSAGE)"

release-source-ready-status:
	$(PYTHON) -m ops.scripts.release_source_ready_status --vault "$(VAULT)" --out "$(RELEASE_SOURCE_READY_STATUS_OUT)"

release-source-ready-post-verify:
	$(MAKE) release-check-all-surfaces
	$(MAKE) release-source-ready-status

release-source-ready:
	$(MAKE) release-source-ready-prepare
	$(MAKE) release-source-ready-commit
	$(MAKE) release-source-ready-post-verify

release-check-preflight-converge: release-converge-preflight
	@echo "release-check-preflight-converge is a mutating compatibility alias; prefer release-converge-preflight before committing, then release-check."

release-check-post-converge: release-converge-post
	@echo "release-check-post-converge is a mutating compatibility alias; prefer release-converge-post before committing, then release-check."

release-check-post-check:
	$(MAKE) release-worktree-clean-check

release-check-core:
	$(MAKE) release-worktree-clean-check
	$(MAKE) test-execution-summary-current-check
	$(MAKE) test-execution-summary-full-current-check
	$(MAKE) uv-lock-check
	$(MAKE) static
	$(MAKE) artifact-freshness-check
	$(MAKE) registry-preflight-check
	$(MAKE) lint
	$(MAKE) eval
	$(MAKE) stage2-eval
	$(MAKE) planning-gate
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
	$(MAKE) bootstrap-preflight
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

release-post-seal-attestation:
	$(PYTHON) -m ops.scripts.release_post_seal_attestation build --vault "$(VAULT)" --out "$(RELEASE_POST_SEAL_ATTESTATION_OUT)" $(if $(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP),--source-zip-path "$(RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP)",) $(if $(RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST),--batch-manifest-path "$(RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST)",) $(if $(RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK),--self-check-path "$(RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK)",) $(if $(RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY),--operator-summary-path "$(RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY)",)

release-evidence-closeout-self-check:
	$(PYTHON) -m ops.scripts.release_evidence_closeout_self_check --vault "$(VAULT)" --batch-manifest "$(RELEASE_CLOSEOUT_BATCH_MANIFEST_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --out "$(RELEASE_EVIDENCE_CLOSEOUT_SELF_CHECK_OUT)"
