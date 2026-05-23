PYTEST_SERIAL_FLAGS ?=
PYTEST_PARALLEL_FLAGS ?= -p xdist.plugin -n auto --dist=loadfile
PYTEST_FLAGS ?= $(PYTEST_PARALLEL_FLAGS)
PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1
PYTEST_FAST_MARK_EXPR ?= not slow and not integration and not integration_heavy and not public and not report_contract and not release_sealing and not subprocess
PYTEST_FAST_SMOKE_MARK_EXPR ?= not slow and not integration_heavy
PYTEST_RELEASE_CHECK_MARK_EXPR ?= not report_contract
PYTEST_SLOW_MARK_EXPR ?= slow and not integration and not integration_heavy and not public
PYTEST_INTEGRATION_MARK_EXPR ?= integration and not integration_heavy and not public
PYTEST_INTEGRATION_HEAVY_MARK_EXPR ?= integration_heavy and not public
PYTEST_PUBLIC_MARK_EXPR ?= public
PYTEST_REPORT_CONTRACT_MARK_EXPR ?= report_contract
PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing
PYTEST_SUBPROCESS_MARK_EXPR ?= subprocess
FAST_SMOKE_TESTS ?= \
	tests/test_import_fallback_contract.py \
	tests/test_script_module_surface_contract.py \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_eval_report_validates_and_requires_policy_identity \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_lint_report_validates_and_requires_policy_identity \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_warning_budget_report_validates_and_requires_policy_identity \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_structural_complexity_budget_report_validates_and_requires_policy_identity \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_eval_coverage_report_validates_and_requires_policy_identity \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_stage2_eval_report_validates_and_requires_policy_identity \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_auto_improve_readiness_report_validates_and_requires_queue_block \
	tests/test_report_schemas.py::ReportSchemaContractTest::test_sample_proposal_scope_report_validates_and_requires_apply_guardrails \
	tests/test_artifact_io_runtime.py \
	tests/test_mechanism_review.py \
	tests/test_mechanism_review_candidate_runtime.py \
	tests/test_mechanism_review_history_runtime.py \
	tests/test_mutation_proposal.py::MutationProposalTest::test_missing_artifact_envelope_fails_fast_for_primary_evidence \
	tests/test_mutation_proposal.py::MutationProposalTest::test_unknown_currentness_fails_fast_for_primary_evidence \
	tests/test_auto_improve_readiness_runtime.py \
	tests/test_artifact_freshness_runtime.py::test_no_root_ephemeral_test_artifacts \
	tests/test_artifact_freshness_runtime.py::ArtifactFreshnessRuntimeTests::test_report_accepts_enveloped_current_json_artifact \
	tests/test_release_smoke.py::ReleaseSmokeTest::test_build_smoke_commands_match_release_gate_profiles \
	tests/test_release_smoke.py::ReleaseSmokeTest::test_run_smoke_commands_captures_returncodes_and_tails \
	tests/test_release_smoke.py::ReleaseSmokeTest::test_build_report_uses_runtime_context_and_sanitizes_ephemeral_paths \
	tests/test_release_smoke.py::ReleaseSmokeTest::test_main_exits_with_report_status_and_prints_written_destination
REPORT_CONTRACT_CORE_TESTS ?= \
	tests/test_test_execution_summary.py \
	tests/test_makefile_static_gates.py \
	tests/test_ci_workflow_static.py \
	tests/test_pytest_entrypoint_guidance.py \
	tests/test_report_schemas.py \
	tests/test_report_schema_sample_regeneration.py \
	tests/test_workflow_dependency_planner.py \
	tests/test_clean_fixture_regeneration_guard.py \
	tests/test_auto_improve_iteration_runtime.py::AutoImproveIterationRuntimeTests::test_run_telemetry_preservation_contract_matches_schema_surface \
	tests/test_goal_runtime_clean_transient.py \
	tests/test_goal_runtime_fixed_point_check.py \
	tests/test_run_templates.py
REPORT_CONTRACT_EXTENDED_TESTS ?= \
	tests/test_improvement_observations_runtime.py \
	tests/test_artifact_freshness_runtime.py \
	tests/test_backfill_archived_run_artifacts.py \
	tests/test_backfill_historical_bootstrap_reports.py \
	tests/test_auto_improve_iteration_runtime.py \
	tests/test_observability_artifacts_runtime.py \
	tests/test_raw_registry_cross_environment_matrix.py \
	tests/test_raw_registry_cross_environment_evidence_bundle.py \
	tests/test_release_smoke.py \
	tests/test_archive_execution_manifest.py \
	tests/test_release_closeout_summary.py \
	tests/test_release_evidence_cohort.py \
	tests/test_release_evidence_dashboard.py \
	tests/test_learning_readiness_signoff.py \
	tests/test_bootstrap_preflight.py \
	tests/test_make_target_inventory.py \
	tests/test_manifest_export_symlink_safety.py \
	tests/test_report_generation_smoke.py
REPORT_CONTRACT_TESTS ?= $(REPORT_CONTRACT_CORE_TESTS)
REPORT_CONTRACT_ALL_TESTS ?= -m "$(PYTEST_REPORT_CONTRACT_MARK_EXPR)"
REPORT_CONTRACT_SUMMARY_MARK_EXPR ?= $(PYTEST_REPORT_CONTRACT_MARK_EXPR)
REPORT_CONTRACT_SUMMARY_TESTS ?= -m "$(REPORT_CONTRACT_SUMMARY_MARK_EXPR)" $(REPORT_CONTRACT_TESTS)
RELEASE_SEALING_CORE_TESTS ?= \
	tests/test_release_closeout_batch_manifest.py \
	tests/test_release_evidence_closeout_self_check.py \
	tests/test_release_run_manifest.py \
	tests/test_release_sealed_post_seal_attestation.py \
	tests/test_release_sealed_run_manifest.py \
	tests/test_release_auto_promotion_ready.py \
	tests/test_release_evidence_planner.py \
	tests/test_source_package_smoke.py \
	tests/test_release_sealing_lane.py
RELEASE_SEALING_TESTS ?= $(RELEASE_SEALING_CORE_TESTS)
SUBPROCESS_TESTS ?= \
	tests/test_command_runtime_subprocess.py
TEST_EXECUTION_SUMMARY_OUT ?= ops/reports/test-execution-summary.json
TEST_EXECUTION_SUMMARY_CANDIDATE_OUT ?= tmp/test-execution-summary.candidate.json
TEST_EXECUTION_SUMMARY_CHECK_OUT ?= tmp/test-execution-summary-check.json
TEST_EXECUTION_SUMMARY_FAST_OUT ?= ops/reports/test-execution-summary-fast.json
TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT ?= tmp/test-execution-summary-fast.candidate.json
TEST_EXECUTION_SUMMARY_FULL_OUT ?= ops/reports/test-execution-summary-full.json
TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT ?= tmp/test-execution-summary-full.candidate.json
TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT ?= tmp/test-execution-summary-full-check.json
TEST_EXECUTION_SUMMARY_FAST_SUITE ?= fast
TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE ?= report-contract-summary
TEST_EXECUTION_SUMMARY_FULL_SUITE ?= full
TEST_EXECUTION_SUMMARY_FULL_SHARD_SUITE ?= full-shard-1
RELEASE_AUDIT_PAYLOAD_STAGING_DIR ?= build/release-payloads
TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT ?= $(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.junit.xml
TEST_EXECUTION_SUMMARY_FULL_LOG_OUT ?= $(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.log
TEST_EXECUTION_SUMMARY_REUSE_FROM ?= $(TEST_EXECUTION_SUMMARY_OUT)
TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM ?= $(TEST_EXECUTION_SUMMARY_FULL_OUT)
TEST_EXECUTION_SUMMARY_SHARD_DIR ?= ops/reports/test-execution-summary-shards
TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR ?= ops/reports/test-execution-summary-full-shards
REPORT_CONTRACT_SUMMARY_DESELECT_POLICY ?= ops/policies/report-contract-deselections.json
RELEASE_CLOSEOUT_REGRESSION_TESTS ?= tests/test_release_closeout_finality_attestation.py::ReleaseCloseoutFinalityAttestationTests::test_finality_verify_fails_after_tracked_digest_drift tests/test_release_closeout_batch_manifest.py::ReleaseCloseoutBatchManifestTests::test_batch_manifest_finality_points_to_attestation_without_digest_ownership tests/test_source_package_clean_extract.py::SourcePackageCleanExtractTests::test_clean_extract_fails_when_zip_smoke_archive_budget_fails tests/test_release_closeout_summary.py::ReleaseCloseoutSummaryTests::test_release_smoke_archive_budget_failure_blocks_clean_release
RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT ?= tmp/release-closeout-regression-artifact-freshness-check.json
RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT ?= tmp/release-closeout-fixed-point-cost-trend-ci.json

.PHONY: fast-smoke report-contracts report-contracts-core report-contracts-all report-contracts-extended test-release-closeout-regression-pack release-closeout-regression-dry-run release-closeout-cost-evidence-ci-artifact test-report-contract test-report-contract-core test-report-contract-all report-contract-summary test-release-sealing test-release-sealing-core test-release-sealing-all test-subprocess report-schema-samples-check report-schema-samples-regenerate report-contract-closeout-precheck report-contract-closeout test-execution-summary-fast test-execution-summary-report-contract test-execution-summary-report-contract-refresh test-execution-summary-report-contract-refresh-no-smoke test-execution-summary test-execution-summary-current-check test-execution-summary-full test-execution-summary-full-refresh test-execution-summary-full-current-check test-execution-summary-reuse test-execution-summary-aggregate test-fast unit-tests unit-tests-serial unit-tests-parallel unit-tests-all unit-tests-all-serial unit-tests-all-parallel unit-tests-release-check test test-serial test-parallel test-all test-all-serial test-all-parallel test-slow test-slow-serial test-integration test-integration-serial test-integration-heavy test-integration-heavy-serial test-public test-public-serial

fast-smoke:
	$(PYTHON) -m pytest -m "$(PYTEST_FAST_SMOKE_MARK_EXPR)" $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)

report-contracts: report-contracts-all
	@echo "report-contracts is a compatibility alias; prefer report-contracts-all or test-report-contract-all."

report-contracts-core:
	$(PYTHON) -m pytest -m "$(PYTEST_REPORT_CONTRACT_MARK_EXPR)" $(REPORT_CONTRACT_TESTS) $(PYTEST_SERIAL_FLAGS)

report-contracts-all:
	$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_SERIAL_FLAGS)

report-contracts-extended:
	$(PYTHON) -m pytest $(REPORT_CONTRACT_EXTENDED_TESTS) $(PYTEST_SERIAL_FLAGS)

test-release-closeout-regression-pack:
	$(PYTHON) -m pytest $(RELEASE_CLOSEOUT_REGRESSION_TESTS) $(PYTEST_SERIAL_FLAGS)

release-closeout-regression-dry-run: tmp-json-clean
	$(MAKE) test-release-closeout-regression-pack
	$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",) --fail-on-fail
	$(PYTHON) -m ops.scripts.release_closeout_finality_attestation --vault "$(VAULT)" --attestation "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT)" --verify

release-closeout-cost-evidence-ci-artifact:
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point_cost_trend --vault "$(VAULT)" --previous "$(RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_OUT)" --out "$(RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT)" --no-fail

test-report-contract: test-report-contract-all
	@echo "test-report-contract is a compatibility alias; prefer test-report-contract-all or test-report-contract-core."

test-report-contract-core:
	$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS)

test-report-contract-all:
	$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_SERIAL_FLAGS)

report-contract-summary: test-report-contract-core

test-release-sealing: test-release-sealing-all
	@echo "test-release-sealing is a compatibility alias; prefer test-release-sealing-all or test-release-sealing-core."

test-release-sealing-core:
	$(PYTHON) -m pytest $(RELEASE_SEALING_TESTS) $(PYTEST_SERIAL_FLAGS)

test-release-sealing-all:
	$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_SEALING_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)

test-subprocess:
	$(PYTHON) -m pytest $(SUBPROCESS_TESTS) $(PYTEST_SERIAL_FLAGS)

report-schema-samples-check:
	$(PYTHON) tools/regenerate_report_schema_samples.py --check

report-schema-samples-regenerate: clean-fixture-regeneration-guard
	$(PYTHON) tools/regenerate_report_schema_samples.py

report-contract-closeout-precheck:
	@for target in $$($(PYTHON) -m ops.scripts.report_contract_closeout_runtime --vault "$(VAULT)"); do \
		$(MAKE) $$target; \
	done

report-contract-closeout:
	$(MAKE) report-contract-closeout-precheck
	$(MAKE) release-smoke-full-reuse
	$(MAKE) test-execution-summary
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-evidence-cohort
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) generated-artifact-converge
	@echo "report-contract-closeout refreshed generated precheck evidence, report-contract test evidence, closeout artifacts, and auto-improve readiness without rerunning the pytest wrapper."
test-execution-summary-fast:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FAST_SUITE)" --collect-nodeids -- $(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_FAST_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary

test-execution-summary-report-contract:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary

test-execution-summary-report-contract-refresh:
	$(MAKE) auto-improve-readiness-report
	$(MAKE) release-smoke-full-reuse
	$(MAKE) generated-artifact-converge
	@status=0; $(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS) || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary || exit $$?; if [ $$status -ne 0 ]; then echo "test-execution-summary-report-contract-refresh promoted a non-pass bootstrap summary; strict test-execution-summary will rerun later in closeout."; fi; exit 0
	$(MAKE) generated-artifact-converge

test-execution-summary-report-contract-refresh-no-smoke:
	$(MAKE) auto-improve-readiness-report
	$(MAKE) generated-artifact-converge
	@status=0; $(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS) || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary || exit $$?; if [ $$status -ne 0 ]; then echo "test-execution-summary-report-contract-refresh-no-smoke promoted a non-pass bootstrap summary; strict test-execution-summary will rerun later in closeout."; fi; exit 0
	$(MAKE) generated-artifact-converge

test-execution-summary: test-execution-summary-report-contract

test-execution-summary-current-check:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CHECK_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --reuse-if-current --reuse-only --reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)" --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS)

test-execution-summary-full:
	rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"
	mkdir -p "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)/full-suite-shard-1.json" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_SUITE)" --collect-nodeids --junit-xml-path "$(TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT)" --execution-log-out "$(TEST_EXECUTION_SUMMARY_FULL_LOG_OUT)" --failed-nodeids-out "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.failed-nodeids.txt" -- $(PYTHON) -m pytest --junit-xml "$(TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT)" $(PYTEST_SERIAL_FLAGS)
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SUITE)" --aggregate --aggregate-dir "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary
	$(MAKE) generated-artifact-converge

test-execution-summary-full-refresh: test-execution-summary-full
	@echo "full-suite evidence refreshed; collect-only nodeid digest and count recorded in $(TEST_EXECUTION_SUMMARY_FULL_OUT)"

test-execution-summary-full-current-check:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SUITE)" --aggregate --reuse-if-current --reuse-only --reuse-from "$(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"

test-execution-summary-reuse:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --reuse-if-current --reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)" --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_SERIAL_FLAGS)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary

test-execution-summary-aggregate:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --aggregate --aggregate-dir "$(TEST_EXECUTION_SUMMARY_SHARD_DIR)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary
test-fast:
	$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_FLAGS)

unit-tests: test-fast

unit-tests-serial:
	$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)

unit-tests-parallel:
	$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_PARALLEL_FLAGS)

unit-tests-all:
	$(PYTHON) -m pytest $(PYTEST_FLAGS)

unit-tests-all-serial:
	$(PYTHON) -m pytest $(PYTEST_SERIAL_FLAGS)

unit-tests-all-parallel:
	$(PYTHON) -m pytest $(PYTEST_PARALLEL_FLAGS)

unit-tests-release-check:
	$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)

test: test-fast

test-serial: unit-tests-serial

test-parallel: unit-tests-parallel

test-all: unit-tests-all

test-all-serial: unit-tests-all-serial

test-all-parallel: unit-tests-all-parallel

test-slow:
	$(PYTHON) -m pytest -m "$(PYTEST_SLOW_MARK_EXPR)" $(PYTEST_FLAGS)

test-slow-serial:
	$(PYTHON) -m pytest -m "$(PYTEST_SLOW_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)

test-integration:
	$(PYTHON) -m pytest -m "$(PYTEST_INTEGRATION_MARK_EXPR)" $(PYTEST_FLAGS)

test-integration-serial:
	$(PYTHON) -m pytest -m "$(PYTEST_INTEGRATION_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)

test-integration-heavy:
	$(PYTHON) -m pytest -m "$(PYTEST_INTEGRATION_HEAVY_MARK_EXPR)" $(PYTEST_FLAGS)

test-integration-heavy-serial:
	$(PYTHON) -m pytest -m "$(PYTEST_INTEGRATION_HEAVY_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)

test-public:
	$(PYTHON) -m pytest -m "$(PYTEST_PUBLIC_MARK_EXPR)" $(PYTEST_FLAGS)

test-public-serial:
	$(PYTHON) -m pytest -m "$(PYTEST_PUBLIC_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)
