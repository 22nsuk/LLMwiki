.PHONY: head-aligned-evidence-converge release-authority-archive-candidate-gate release-authority-inventory release-authority-post-ready-finality release-authority-post-ready-finality-current-check release-authority-post-ready-finality-current-or-refresh release-authority-sealed-preflight release-authority-settle release-auto-promotion-goal-run-id-guard release-auto-promotion-goal-run-id-verified-check release-auto-promotion-operator-summary release-auto-promotion-preflight release-auto-promotion-preflight-check release-auto-promotion-preflight-prerequisites release-auto-promotion-preseal release-auto-promotion-preseal-check release-auto-promotion-ready release-auto-promotion-ready-check release-auto-promotion-ready-invalidate release-auto-promotion-ready-plan release-auto-promotion-safe-cleanup release-auto-promotion-safe-cleanup-cleanup-only release-auto-promotion-safe-cleanup-finalize release-check release-check-all-surfaces release-check-core release-check-finalized release-check-post-check release-check-post-converge release-check-preflight-converge release-converge release-converge-all-surfaces release-converge-post release-converge-preflight release-evidence-closeout-sealed release-evidence-closeout-sealed-check release-evidence-closeout-sealed-core-sidecars release-evidence-closeout-sealed-dry-run release-evidence-closeout-sealed-dry-run-check release-evidence-closeout-sealed-sidecars release-package-current release-package-current-check release-package-current-or-refresh release-post-commit-finalize release-preflight-current release-public-current release-run-ready release-run-ready-check release-run-ready-plan release-run-ready-plan-check release-seal-current release-sealed-post-seal-attestation release-sealed-run-ready release-sealed-run-ready-check release-sealed-run-ready-plan release-source-package-clean-extract release-source-package-clean-extract-current-check release-source-package-clean-extract-current-or-refresh release-source-package-smoke release-source-package-smoke-current-check release-source-package-smoke-current-or-refresh release-source-ready release-source-ready-commit release-source-ready-post-verify release-source-ready-prepare release-source-ready-snapshot release-source-ready-status release-test-current release-worktree-clean-check

release-authority-inventory:
	$(PYTHON) -m ops.scripts.release_authority_inventory --vault "$(VAULT)" --out "$(RELEASE_AUTHORITY_INVENTORY_OUT)"

release-run-ready:
	$(MAKE) release-run-ready-plan
	$(MAKE) release-auto-promotion-ready-invalidate
	$(PYTHON) -m ops.scripts.release_run_ready --vault "$(VAULT)" --out "$(RELEASE_RUN_MANIFEST_OUT)" --make-bin "$(RELEASE_RUN_READY_MAKE_BIN)" --timeout-seconds "$(RELEASE_RUN_READY_TIMEOUT_SECONDS)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"

release-run-ready-plan:
	$(PYTHON) -m ops.scripts.release_run_ready --vault "$(VAULT)" --plan --plan-out "$(RELEASE_RUN_READY_PLAN_OUT)" --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"

release-run-ready-plan-check:
	$(PYTHON) -m ops.scripts.release_run_ready --vault "$(VAULT)" --plan --plan-out "$(RELEASE_RUN_READY_PLAN_CHECK_OUT)" --require-ready --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"

release-run-ready-check:
	$(PYTHON) -m ops.scripts.release_run_manifest --vault "$(VAULT)" --out "$(RELEASE_RUN_MANIFEST_OUT)" --check --distribution-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --source-package-smoke "$(SOURCE_PACKAGE_SMOKE_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)"

release-sealed-run-ready-plan:
	$(PYTHON) -m ops.scripts.release_evidence_planner --vault "$(VAULT)" --stage sealed-run-ready --out "$(RELEASE_SEALED_RUN_READY_PLAN_OUT)" --require-ready

release-sealed-run-ready:
	$(MAKE) release-auto-promotion-ready-invalidate
	$(MAKE) release-sealed-run-ready-plan
	$(MAKE) release-evidence-closeout-sealed-sidecars
	$(MAKE) release-sealed-post-seal-attestation
	$(MAKE) release-evidence-closeout-sealed-check RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT="$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"
	$(PYTHON) -m ops.scripts.release_sealed_run_manifest --vault "$(VAULT)" --out "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --post-seal-attestation "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)"

release-sealed-run-ready-check:
	$(PYTHON) -m ops.scripts.release_sealed_run_manifest --vault "$(VAULT)" --out "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --post-seal-attestation "$(RELEASE_SEALED_POST_SEAL_ATTESTATION_OUT)" --check

release-auto-promotion-goal-run-id-guard:
	$(PYTHON) -m ops.scripts.release_goal_run_identity_guard --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --goal-run-id "$(GOAL_RUN_ID)" --goal-run-id-origin "$(origin GOAL_RUN_ID)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --check

release-auto-promotion-goal-run-id-verified-check:
	$(PYTHON) -m ops.scripts.release_goal_run_identity_guard --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --goal-run-id "$(GOAL_RUN_ID)" --goal-run-id-origin "$(origin GOAL_RUN_ID)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --check --require-verified

release-auto-promotion-preflight:
	$(MAKE) release-auto-promotion-ready-invalidate
	$(MAKE) release-auto-promotion-goal-run-id-guard
	$(MAKE) release-auto-promotion-preflight-prerequisites
	$(MAKE) release-smoke-fast-refresh-check
	$(MAKE) test-execution-summary-current-or-refresh
	$(MAKE) artifact-freshness-refresh-check
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) tmp-json-clean
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preflight --out "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)"

release-auto-promotion-preflight-check:
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preflight --out "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --check

release-auto-promotion-preflight-prerequisites:
	$(MAKE) external-report-action-matrix
	$(MAKE) generated-artifact-index-body

release-auto-promotion-safe-cleanup: release-auto-promotion-safe-cleanup-cleanup-only
	$(MAKE) release-auto-promotion-safe-cleanup-finalize
	$(MAKE) tmp-json-clean

release-auto-promotion-safe-cleanup-cleanup-only:
	$(MAKE) goal-runtime-clean-transient
	$(MAKE) tmp-json-clean
	$(PYTHON) -m ops.scripts.backfill_archived_run_artifacts --vault "$(VAULT)"
	$(MAKE) generated-artifact-index
	$(MAKE) artifact-freshness-refresh-check

release-auto-promotion-safe-cleanup-finalize:
	@if [ -n "$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" ]; then \
		$(MAKE) external-report-reference-manifest-release-check EXTERNAL_REPORT_REVIEW_BASIS_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
		$(MAKE) release-closeout-batch-manifest-promote RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
		$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"; \
	else \
		$(MAKE) external-report-reference-manifest-release-check; \
	fi

release-auto-promotion-preseal:
	$(MAKE) release-auto-promotion-ready-invalidate
	$(MAKE) release-auto-promotion-goal-run-id-guard
	$(MAKE) release-run-ready-plan-check
	$(MAKE) release-run-ready-check
	$(MAKE) bootstrap-preflight
	$(MAKE) registry-preflight
	$(MAKE) release-smoke-full-current-check
	$(MAKE) release-smoke-fast-refresh-check
	$(MAKE) external-report-reference-manifest-settle
	$(MAKE) release-auto-promotion-safe-cleanup-cleanup-only
	$(MAKE) learning-readiness-signoff-revalidation
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=1
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-evidence-cohort-preseal-refresh RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"
	$(MAKE) artifact-freshness-refresh-check
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-run-ready-check
	$(MAKE) release-evidence-dashboard-report
	$(MAKE) release-lane-summary
	$(MAKE) release-clean-blocker-ledger
	$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"
	$(MAKE) release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint RELEASE_EVIDENCE_COHORT_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)"
	$(MAKE) tmp-json-clean
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preseal --out "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)"

release-auto-promotion-preseal-check:
	$(PYTHON) -m ops.scripts.release_auto_promotion_preflight --vault "$(VAULT)" --phase preseal --out "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --remediation-backlog "$(REMEDIATION_BACKLOG_OUT)" --learning-revalidation "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --closeout-summary "$(RELEASE_CLOSEOUT_SUMMARY_OUT)" --evidence-cohort "$(RELEASE_EVIDENCE_COHORT_OUT)" --goal-run-identity "$(RELEASE_AUTO_PROMOTION_GOAL_RUN_IDENTITY_OUT)" --check

release-auto-promotion-ready-plan:
	$(PYTHON) -m ops.scripts.release_evidence_planner --vault "$(VAULT)" --stage auto-promotion-ready --out "$(RELEASE_AUTO_PROMOTION_READY_PLAN_OUT)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --require-ready

release-auto-promotion-ready-invalidate:
	rm -f "$(RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT)" "$(RELEASE_AUTO_PROMOTION_READY_PLAN_OUT)" "$(RELEASE_SEALED_RUN_READY_PLAN_OUT)" "$(RELEASE_RUN_READY_PLAN_OUT)"

release-auto-promotion-operator-summary:
	$(MAKE) release-auto-promotion-ready-invalidate
	$(PYTHON) -m ops.scripts.operator_release_summary --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --batch-manifest "$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" --self-check "$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)"

release-auto-promotion-ready:
	@status=0; $(MAKE) release-auto-promotion-ready-plan || status=$$?; \
	if [ $$status -ne 0 ]; then \
		echo "release-auto-promotion-ready-plan is blocked; writing blocked ready manifest for diagnostics"; \
	fi
	$(PYTHON) -m ops.scripts.release_auto_promotion_ready --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)"

release-auto-promotion-ready-check:
	$(PYTHON) -m ops.scripts.release_auto_promotion_ready --vault "$(VAULT)" --out "$(RELEASE_AUTO_PROMOTION_READY_MANIFEST_OUT)" --run-manifest "$(RELEASE_RUN_MANIFEST_OUT)" --sealed-run-manifest "$(RELEASE_SEALED_RUN_MANIFEST_OUT)" --operator-summary "$(RELEASE_AUTO_PROMOTION_OPERATOR_SUMMARY_OUT)" --auto-improve-readiness "$(AUTO_IMPROVE_READINESS_OUT)" --auto-promotion-preflight "$(RELEASE_AUTO_PROMOTION_PREFLIGHT_OUT)" --auto-promotion-preseal "$(RELEASE_AUTO_PROMOTION_PRESEAL_OUT)" --goal-run-status "$(GOAL_RUN_STATUS_OUT)" --goal-runtime-certificate "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --check

release-authority-post-ready-finality:
	$(MAKE) artifact-freshness-refresh-check
	$(MAKE) release-closeout-batch-manifest-promote RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"
	$(MAKE) release-closeout-fixed-point RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-batch-manifest-replay-verify RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)"
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-finality-verify

release-authority-post-ready-finality-current-check:
	@status=0; diagnose_on_fail=1; \
	$(MAKE) tmp-json-clean || status=$$?; \
	if [ $$status -eq 0 ]; then $(MAKE) release-closeout-batch-manifest-replay-verify RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_ZIP_METADATA)" RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_AUTO_PROMOTION_EFFECTIVE_DISTRIBUTION_ZIP)" || status=$$?; fi; \
	if [ $$status -eq 0 ]; then $(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required || status=$$?; fi; \
	if [ $$status -eq 0 ]; then $(MAKE) tmp-json-clean || status=$$?; fi; \
	if [ $$status -eq 0 ]; then $(MAKE) release-closeout-finality-verify || { status=$$?; diagnose_on_fail=0; }; fi; \
	if [ $$status -ne 0 ] && [ $$diagnose_on_fail -eq 1 ]; then $(MAKE) release-finality-resettle-current-diagnose || true; fi; \
	exit $$status

release-authority-post-ready-finality-current-or-refresh:
	@if $(MAKE) release-authority-post-ready-finality-current-check; then \
		echo "release authority post-ready finality evidence is current"; \
	else \
		$(MAKE) tmp-json-clean; \
		$(MAKE) release-authority-post-ready-finality; \
	fi

release-authority-archive-candidate-gate:
	$(MAKE) external-report-action-matrix
	$(MAKE) generated-artifact-index-body
	$(MAKE) archive-execution-manifest-check

release-authority-settle:
	$(MAKE) release-finality-resettle-current-or-refresh
	$(MAKE) release-auto-promotion-goal-run-id-verified-check
	$(MAKE) release-auto-promotion-preflight
	$(MAKE) release-run-ready
	$(MAKE) release-auto-promotion-preseal
	$(MAKE) release-sealed-run-ready
	@status=0; \
	$(MAKE) release-auto-promotion-ready || status=$$?; \
	$(MAKE) release-authority-archive-candidate-gate || exit $$?; \
	if [ $$status -eq 0 ]; then \
		$(MAKE) release-auto-promotion-preflight-check || exit $$?; \
		$(MAKE) release-run-ready-check || exit $$?; \
		$(MAKE) release-auto-promotion-preseal-check || exit $$?; \
		$(MAKE) release-sealed-run-ready-check || exit $$?; \
		$(MAKE) release-auto-promotion-ready-check || exit $$?; \
		$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" --mode verify --out "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)" --fail-on-attention --fail-on-authority-attention || exit $$?; \
	fi; \
	$(MAKE) release-authority-post-ready-finality-current-or-refresh || exit $$?; \
	if [ $$status -ne 0 ]; then exit $$status; fi

release-preflight-current:
	$(MAKE) release-worktree-clean-check

release-test-current:
	$(MAKE) static
	$(MAKE) report-schema-samples-check
	$(MAKE) test-execution-summary-full-current-or-refresh
	$(MAKE) test-execution-summary-current-or-refresh

release-public-current:
	$(MAKE) public-check-summary-current-or-refresh

release-package-current:
	$(MAKE) release-package-current-or-refresh

release-package-current-check:
	$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --out "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)" --reuse-if-current --reuse-only --reuse-from "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"

release-package-current-or-refresh:
	@if $(MAKE) release-package-current-check; then \
		echo "release distribution zip evidence is current; reused $(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"; \
	else \
		$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"; \
	fi

release-source-package-smoke:
	$(MAKE) release-source-package-smoke-current-or-refresh

release-source-package-smoke-current-check:
	$(PYTHON) -m ops.scripts.source_package_smoke --vault "$(VAULT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --extract-parent "$(SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --out "$(SOURCE_PACKAGE_SMOKE_OUT)" --reuse-if-current --reuse-only --reuse-from "$(SOURCE_PACKAGE_SMOKE_OUT)"

release-source-package-smoke-current-or-refresh:
	@if $(MAKE) release-source-package-smoke-current-check; then \
		echo "source package smoke evidence is current; reused $(SOURCE_PACKAGE_SMOKE_OUT)"; \
	else \
		rm -rf "$(SOURCE_PACKAGE_SMOKE_ROOT)"; \
		$(PYTHON) -m ops.scripts.source_package_smoke --vault "$(VAULT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --extract-parent "$(SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --out "$(SOURCE_PACKAGE_SMOKE_OUT)"; \
	fi

release-source-package-clean-extract:
	$(MAKE) release-source-package-clean-extract-current-or-refresh

release-source-package-clean-extract-current-check:
	$(PYTHON) -m ops.scripts.source_package_clean_extract --vault "$(VAULT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --extract-parent "$(SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --test-summary-out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT)" --deselection-policy "$(SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTION_POLICY)" --pytest-mark-expr "$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_MARK_EXPR)" --tests "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TESTS)" --deselects "$(SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTS)" --pytest-flags="$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS)" --zip-smoke-report "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)" --out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)" --reuse-if-current --reuse-only --reuse-from "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"

release-source-package-clean-extract-current-or-refresh:
	@if $(MAKE) release-source-package-clean-extract-current-check; then \
		echo "source package clean extract evidence is current; reused $(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"; \
	else \
		rm -rf "$(SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT)"; \
		$(PYTHON) -m ops.scripts.source_package_clean_extract --vault "$(VAULT)" --source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" --extract-parent "$(SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT)" --source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --test-summary-out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT)" --deselection-policy "$(SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTION_POLICY)" --pytest-mark-expr "$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_MARK_EXPR)" --tests "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TESTS)" --deselects "$(SOURCE_PACKAGE_CLEAN_EXTRACT_DESELECTS)" --pytest-flags="$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS)" --zip-smoke-report "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)" --out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"; \
	fi

release-seal-current:
	$(MAKE) release-evidence-closeout-sealed-sidecars
	$(MAKE) release-post-seal-attestation RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_POST_SEAL_ATTESTATION_BATCH_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" RELEASE_POST_SEAL_ATTESTATION_SELF_CHECK="$(RELEASE_CLOSEOUT_SEALED_SELF_CHECK_OUT)" RELEASE_POST_SEAL_ATTESTATION_OPERATOR_SUMMARY="$(RELEASE_CLOSEOUT_SEALED_OPERATOR_SUMMARY_OUT)"
	$(MAKE) release-evidence-closeout-sealed-check RELEASE_CLOSEOUT_DISTRIBUTION_ZIP="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_OUT="$(RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_RELEASE_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_BATCH_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_BATCH_MANIFEST_OUT)" RELEASE_CLOSEOUT_SEALED_REHEARSAL_CHECK_EXTERNAL_MANIFEST="$(RELEASE_CLOSEOUT_SEALED_EXTERNAL_MANIFEST_OUT)"

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

release-worktree-clean-check:
	$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --requested-mode git --out "$(RELEASE_WORKTREE_CLEAN_CHECK_OUT)" --strict

release-converge-preflight:
	$(MAKE) generated-artifact-script-output
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

release-post-commit-finalize:
	$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" --mode snapshot --out "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"
	$(MAKE) script-output-surfaces-check
	$(MAKE) release-smoke-fast-current-check
	$(MAKE) test-execution-summary-current-check
	$(MAKE) test-execution-summary-full-current-check
	$(MAKE) sync-public-policy-check
	$(MAKE) public-check-summary-current-check
	$(MAKE) artifact-freshness-check
	$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" --mode verify --previous "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)" --out "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)" --fail-on-attention
	$(MAKE) release-closeout-finality-verify

head-aligned-evidence-converge: release-post-commit-finalize
	@echo "head-aligned-evidence-converge is a compatibility alias; prefer release-post-commit-finalize."

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
	$(MAKE) release-post-commit-finalize
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
	@echo "release-check-finalized is a compatibility alias; use release-check for check-only verification or release-post-commit-finalize after committing source-ready changes."
