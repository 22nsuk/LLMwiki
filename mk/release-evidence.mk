.PHONY: collaboration-governance external-report-action-matrix external-report-lifecycle-refresh external-report-reference-manifest external-report-reference-manifest-release-check external-report-reference-manifest-settle external-report-reference-manifest-strict freshness-source-identity-converge github-governance-live-drift github-governance-live-drift-check operator-evidence-closeout-current-or-refresh operator-evidence-closeout-finality-resettle operator-release-summary release-audit-pack release-builder-full release-builder-full-lane-guard release-clean release-clean-blocker-ledger release-clean-lane-evidence-review release-closeout-batch-manifest-promote release-closeout-batch-manifest-replay-verify release-closeout-batch-manifest-verify release-closeout-finality-attestation release-closeout-finality-verify release-closeout-fixed-point release-closeout-fixed-point-cost-trend release-closeout-post-check-finalizer-ci-artifact release-closeout-post-check-finalizer-dry-run release-closeout-summary release-closeout-summary-conditional release-closeout-summary-report release-conditional release-distribution-zip release-distribution-zip-lane-guard release-evidence-closeout release-evidence-closeout-lane-guard release-evidence-closeout-self-check release-evidence-cohort release-evidence-cohort-check release-evidence-cohort-preseal-refresh release-evidence-cohort-report release-evidence-converge release-evidence-converge-lane-guard release-evidence-converge-phase-1 release-evidence-converge-phase-2 release-evidence-converge-phase-3 release-evidence-dashboard release-evidence-dashboard-report release-evidence-refresh-fast release-finality-resettle release-finality-resettle-current-check release-finality-resettle-current-or-refresh release-freshness-sensitive-evidence-refresh release-lane-summary release-post-seal-attestation release-provenance-clean release-sbom-clean release-sealed-verify release-smoke release-smoke-fast release-smoke-fast-current-check release-smoke-fast-refresh-check release-smoke-full release-smoke-full-current-check release-smoke-full-reuse release-smoke-lane-guard release-source-package-check release-verify-current review-archive review-archive-clean

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
	$(MAKE) test-execution-summary-current-or-refresh
	$(MAKE) function-budget-refactor-proposals
	$(MAKE) outcome-provenance-gate-policy
	$(MAKE) release-freshness-sensitive-evidence-refresh
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
	$(MAKE) release-closeout-summary-report
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) release-evidence-cohort-report RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) release-evidence-dashboard-report
	$(MAKE) release-lane-summary
	$(MAKE) release-clean-blocker-ledger
	$(MAKE) generated-artifact-converge

release-evidence-converge-phase-3: release-evidence-converge-phase-2
	$(MAKE) release-closeout-post-check-finalizer-dry-run
	$(MAKE) release-closeout-fixed-point
	$(MAKE) operator-release-summary
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-fixed-point
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

release-finality-resettle:
	$(MAKE) workflow-dependency-planner
	$(MAKE) release-authority-sealed-preflight
	$(MAKE) generated-artifact-finality-suffix
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-closeout-fixed-point
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

release-finality-resettle-current-check:
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-batch-manifest-replay-verify
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

release-finality-resettle-current-or-refresh:
	@if $(MAKE) release-finality-resettle-current-check; then \
		echo "release finality evidence is current"; \
	else \
		$(MAKE) tmp-json-clean; \
		$(MAKE) release-finality-resettle; \
	fi

operator-evidence-closeout-finality-resettle:
	$(MAKE) generated-artifact-finality-suffix
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_FIXED_POINT_INITIAL_TARGETS="$(OPERATOR_EVIDENCE_FINALITY_INITIAL_TARGETS)"
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

operator-evidence-closeout-current-or-refresh:
	@if $(MAKE) release-finality-resettle-current-check; then \
		echo "operator evidence finality is current"; \
	else \
		$(MAKE) tmp-json-clean; \
		$(MAKE) operator-evidence-closeout-finality-resettle; \
	fi

freshness-source-identity-converge:
	$(MAKE) artifact-freshness-refresh-check
	$(MAKE) generated-artifact-index
	$(MAKE) artifact-freshness-refresh-check
	$(MAKE) release-finality-resettle-current-or-refresh

release-freshness-sensitive-evidence-refresh:
	$(MAKE) supply-chain-artifacts-cached
	$(MAKE) lint-uplift-plan
	$(MAKE) type-uplift-plan
	$(MAKE) complexity-budget

release-verify-current:
	$(MAKE) release-check-finalized
	$(MAKE) release-closeout-finality-verify

release-sealed-verify:
	$(MAKE) release-verify-current
	$(MAKE) release-evidence-closeout-sealed-check

release-distribution-zip: release-distribution-zip-lane-guard
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_DISTRIBUTION_ZIP_OUT)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"

release-distribution-zip-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-distribution-zip

release-source-package-check:
	$(MAKE) release-package-current-or-refresh
	$(MAKE) release-source-package-smoke-current-or-refresh
	$(MAKE) release-source-package-clean-extract-current-or-refresh

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
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile full --archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_OUT)"

release-smoke-full: release-smoke

release-smoke-full-reuse: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile full --archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_OUT)" --reuse-if-current --reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"

release-smoke-full-current-check: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile full --archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_CURRENT_CHECK_OUT)" --reuse-if-current --reuse-only --reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"

release-smoke-fast: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_SMOKE_FAST_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_FAST_OUT)"

release-smoke-fast-current-check: release-smoke-lane-guard
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_SMOKE_FAST_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT)" --reuse-if-current --reuse-only --reuse-from "$(RELEASE_SMOKE_FAST_OUT)"

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

release-evidence-cohort-report:
	$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy "$(RELEASE_EVIDENCE_COHORT_POLICY)" --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)" $(if $(RELEASE_EVIDENCE_COHORT_ZIP_METADATA),--zip-metadata "$(RELEASE_EVIDENCE_COHORT_ZIP_METADATA)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --out "$(RELEASE_EVIDENCE_COHORT_OUT)" --schema ops/schemas/release-evidence-cohort.schema.json --expected-artifact-kind release_evidence_cohort --expected-producer ops.scripts.release_evidence_cohort

release-evidence-cohort-preseal-refresh:
	$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy strict_same_fingerprint --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)" $(if $(RELEASE_EVIDENCE_COHORT_ZIP_METADATA),--zip-metadata "$(RELEASE_EVIDENCE_COHORT_ZIP_METADATA)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_EVIDENCE_COHORT_STAGING_OUT)" --out "$(RELEASE_EVIDENCE_COHORT_OUT)" --schema ops/schemas/release-evidence-cohort.schema.json --expected-artifact-kind release_evidence_cohort --expected-producer ops.scripts.release_evidence_cohort

release-evidence-cohort-check:
	$(PYTHON) -m ops.scripts.release_evidence_cohort --vault "$(VAULT)" --out "$(RELEASE_EVIDENCE_COHORT_DIAGNOSTIC_OUT)" --profile "$(RELEASE_CLOSEOUT_PROFILE)" --cohort-policy strict_same_fingerprint --provenance-mode "$(RELEASE_EVIDENCE_COHORT_PROVENANCE_MODE)" $(if $(RELEASE_EVIDENCE_COHORT_ZIP_METADATA),--zip-metadata "$(RELEASE_EVIDENCE_COHORT_ZIP_METADATA)",) --fail-on-attention --require-clean-lane

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

review-archive:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.release.review_archive --vault "$(VAULT)" --archive-out "$(REVIEW_ARCHIVE_OUT)" --out "$(REVIEW_ARCHIVE_REPORT_OUT)" --profile "$(REVIEW_ARCHIVE_PROFILE)"

review-archive-clean:
	$(MAKE) local-cache-clean
	$(MAKE) tmp-json-clean
	$(MAKE) review-archive REVIEW_ARCHIVE_PROFILE=clean

external-report-reference-manifest:
	$(PYTHON) -m ops.scripts.external_report_reference_manifest --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_OUT)" --mode "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE)" $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME),--basis-zip-name "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256),--basis-zip-sha256 "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT),--basis-zip-entry-count "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),--basis-zip-path "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH),--current-distribution-zip-path "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_NAME),--current-distribution-zip-name "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_NAME)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_SHA256),--current-distribution-zip-sha256 "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_SHA256)",) $(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_ENTRY_COUNT),--current-distribution-zip-entry-count "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_ENTRY_COUNT)",)

external-report-reference-manifest-strict:
	$(PYTHON) -m ops.scripts.external_report_reference_manifest --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_REFERENCE_MANIFEST_OUT)" --mode strict_review_release $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME),--basis-zip-name "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_NAME)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256),--basis-zip-sha256 "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_SHA256)",) $(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT),--basis-zip-entry-count "$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_ENTRY_COUNT)",) --basis-zip-path "$(if $(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_EFFECTIVE_REVIEW_BASIS_ZIP_PATH),$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH))" --current-distribution-zip-path "$(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH)"

external-report-reference-manifest-release-check:
	$(if $(EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH),$(MAKE) external-report-reference-manifest-strict,$(MAKE) external-report-reference-manifest EXTERNAL_REPORT_REFERENCE_MANIFEST_MODE=advisory)

external-report-reference-manifest-settle:
	@if [ -n "$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" ]; then \
		$(MAKE) external-report-reference-manifest-release-check EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
		$(MAKE) external-report-reference-manifest-release-check EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
	else \
		$(MAKE) external-report-reference-manifest-release-check; \
		$(MAKE) external-report-reference-manifest-release-check; \
	fi

external-report-action-matrix:
	$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"

github-governance-live-drift:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.release.github_governance_live_drift --vault "$(VAULT)" --live-input "$(GITHUB_GOVERNANCE_LIVE_INPUT)" --out "$(GITHUB_GOVERNANCE_LIVE_DRIFT_OUT)"

github-governance-live-drift-check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m ops.scripts.release.github_governance_live_drift --vault "$(VAULT)" --live-input "$(GITHUB_GOVERNANCE_LIVE_INPUT)" --out "$(GITHUB_GOVERNANCE_LIVE_DRIFT_CHECK_OUT)"

collaboration-governance: github-governance-live-drift

external-report-lifecycle-refresh:
	$(MAKE) external-report-reference-manifest-settle
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-evidence-cohort
	$(MAKE) release-evidence-dashboard-report

release-conditional: release-evidence-refresh-fast

release-clean: release-check warning-budget release-evidence-converge release-evidence-cohort-check

release-provenance-clean: release-clean supply-chain-check

release-sbom-clean: release-provenance-clean sbom-readiness-check
release-closeout-fixed-point:
	$(MAKE) bootstrap-preflight
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT)" --max-iterations "$(RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS)" --timeout-seconds "$(RELEASE_CLOSEOUT_FIXED_POINT_TIMEOUT_SECONDS)" $(foreach target,$(RELEASE_CLOSEOUT_FIXED_POINT_INITIAL_TARGETS),--initial-target "$(target)") $(if $(RELEASE_CLOSEOUT_FIXED_POINT_INITIAL_TARGETS),--baseline-before-first-iteration,) $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)",) $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--make-variable "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_CLOSEOUT_FIXED_POINT_CANDIDATE_OUT)" --out "$(RELEASE_CLOSEOUT_FIXED_POINT_OUT)" --schema ops/schemas/release-closeout-fixed-point.schema.json --expected-artifact-kind release_closeout_fixed_point_report --expected-producer ops.scripts.release_closeout_fixed_point
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point --vault "$(VAULT)" --bootstrap-post-promote --max-iterations "$(RELEASE_CLOSEOUT_FIXED_POINT_MAX_ITERATIONS)" --timeout-seconds "$(RELEASE_CLOSEOUT_FIXED_POINT_TIMEOUT_SECONDS)" $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA)",) $(if $(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE),--make-variable "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE=$(RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_TIMESTAMP_TIMEZONE)",) $(if $(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP),--make-variable "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=$(RELEASE_CLOSEOUT_DISTRIBUTION_ZIP)",)
	$(MAKE) external-report-action-matrix
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
