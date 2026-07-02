PYTEST_SERIAL_FLAGS ?=
PYTEST_XDIST_WORKERS ?= 4
PYTEST_XDIST_MAXPROCESSES ?= 4
PYTEST_XDIST_MAXPROCESSES_FLAGS ?= --maxprocesses=$(PYTEST_XDIST_MAXPROCESSES)
PYTEST_LOADFILE_FLAGS ?= -p xdist.plugin -n $(PYTEST_XDIST_WORKERS) $(PYTEST_XDIST_MAXPROCESSES_FLAGS) --dist=loadfile
PYTEST_PARALLEL_FLAGS ?= $(PYTEST_LOADFILE_FLAGS)
PYTEST_CACHE_ISOLATION_FLAGS ?= -p no:cacheprovider
PYTEST_FLAGS ?= $(PYTEST_PARALLEL_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)
PYTEST_REPORT_CONTRACT_FLAGS ?= $(PYTEST_LOADFILE_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)
PYTEST_RELEASE_SEALING_FLAGS ?= $(PYTEST_LOADFILE_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)
PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1
LLMWIKI_MAKE_PYTEST_ENTRYPOINT ?= 1
PYTHONDONTWRITEBYTECODE ?= 1
PYTEST_FAST_MARK_EXPR ?= not slow and not integration and not integration_heavy and not public and not report_contract and not release_sealing and not subprocess
PYTEST_FAST_SMOKE_MARK_EXPR ?= fast_smoke
PYTEST_DEFAULT_TEST_BOUNDARY_MARK_EXPR ?= default_test_boundary
PYTEST_RUNTIME_HOTSPOT_SMOKE_MARK_EXPR ?= runtime_hotspot_smoke
PYTEST_SCHEMA_STATIC_SMOKE_MARK_EXPR ?= schema_static_smoke
PYTEST_RELEASE_CHECK_MARK_EXPR ?= not report_contract
PYTEST_SLOW_MARK_EXPR ?= slow and not integration and not integration_heavy and not public
PYTEST_INTEGRATION_MARK_EXPR ?= integration and not integration_heavy and not public
PYTEST_INTEGRATION_HEAVY_MARK_EXPR ?= integration_heavy and not public
PYTEST_PUBLIC_MARK_EXPR ?= public
PYTEST_REPORT_CONTRACT_CORE_MARK_EXPR ?= report_contract_core
PYTEST_REPORT_CONTRACT_MARK_EXPR ?= report_contract
PYTEST_RELEASE_SEALING_CORE_MARK_EXPR ?= release_sealing_core
PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing
PYTEST_SUBPROCESS_MARK_EXPR ?= subprocess
PYTEST_RELEASE_CLOSEOUT_REGRESSION_MARK_EXPR ?= release_closeout_regression
CI_REPORT_CONTRACT_EVENT_NAME ?= $(GITHUB_EVENT_NAME)
CI_REPORT_CONTRACT_REF ?= $(GITHUB_REF)
# Pytest marker registration and selector variables are generated from
# ops/test-lane-registry.json (see: make pytest-markers-sync and
# make test-selectors-sync).
include mk/test-selectors.generated.mk

REPORT_CONTRACT_SUMMARY_TESTS ?= $(REPORT_CONTRACT_TESTS)
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
TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE ?= run
TEST_EXECUTION_SUMMARY_FULL_MODE ?= run
RELEASE_AUDIT_PAYLOAD_STAGING_DIR ?= build/release-payloads
TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT ?= $(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.junit.xml
TEST_EXECUTION_SUMMARY_FULL_LOG_OUT ?= $(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.log
TEST_EXECUTION_SUMMARY_REUSE_FROM ?= $(TEST_EXECUTION_SUMMARY_OUT)
TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM ?= $(TEST_EXECUTION_SUMMARY_FULL_OUT)
TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS ?= $(PYTEST_FLAGS)
TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR ?= ops/reports/test-execution-summary-full-shards
TEST_EXECUTION_SUMMARY_FULL_HEARTBEAT_INTERVAL_SECONDS ?= 30
REPORT_CONTRACT_SUMMARY_DESELECT_POLICY ?= ops/policies/report-contract-deselections.json
RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT ?= tmp/release-closeout-regression-artifact-freshness-check.json
RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT ?= tmp/release-closeout-fixed-point-cost-trend-ci.json
RELEASE_CLOSEOUT_FINALITY_VERIFY_CI_OUT ?= tmp/release-closeout-finality-verify-ci.json

.PHONY: fast-smoke runtime-hotspot-smoke test-boundary-contract-smoke test-release-closeout-regression-pack release-closeout-regression-dry-run release-closeout-cost-evidence-ci-artifact ci-report-contract-tier test-report-contract-core test-report-contract-all test-release-sealing-core test-release-sealing-all test-subprocess pytest-markers-sync pytest-markers-sync-check _internal-pytest-markers-sync-check test-selectors-sync test-selectors-sync-check _internal-test-selectors-sync-check release-governance-sync _internal-release-governance-sync-check release-governance-sync-check report-schema-samples-check report-schema-samples-regenerate _internal-report-schema-samples-check runtime-hotspot-goldens-check _internal-runtime-hotspot-goldens-check full-pytest-generated-preflight report-contract-closeout-precheck report-contract-closeout report-contract-closeout-generated-artifacts test-execution-summary-fast test-execution-summary-report-contract test-execution-summary test-execution-summary-report-contract-refresh test-execution-summary-report-contract-refresh-no-smoke test-execution-summary-current-check test-execution-summary-current-or-refresh test-execution-summary-reuse test-execution-summary-full test-execution-summary-full-body test-execution-summary-full-refresh test-execution-summary-full-refresh-no-converge test-execution-summary-full-aggregate-reuse test-execution-summary-full-current-check test-execution-summary-full-current-or-refresh test-fast unit-tests unit-tests-serial unit-tests-parallel unit-tests-all unit-tests-all-serial unit-tests-all-parallel unit-tests-release-check test test-serial test-parallel test-all test-all-serial test-all-parallel test-slow test-slow-serial test-integration test-integration-serial test-integration-heavy test-integration-heavy-serial test-public test-public-serial
.PHONY: test-schema-static-smoke release-closeout-finality-verify-ci-artifact

pytest-markers-sync:
	$(PYTHON) -m ops.scripts.test.generate_pytest_ini_markers --vault "$(VAULT)"

pytest-markers-sync-check:
	@$(MAKE) _internal-pytest-markers-sync-check

_internal-pytest-markers-sync-check:
	$(PYTHON) -m ops.scripts.test.generate_pytest_ini_markers --vault "$(VAULT)" --check

test-selectors-sync:
	$(PYTHON) -m ops.scripts.test.generate_test_mk_selectors --vault "$(VAULT)"

test-selectors-sync-check:
	@$(MAKE) _internal-test-selectors-sync-check

_internal-test-selectors-sync-check:
	$(PYTHON) -m ops.scripts.test.generate_test_mk_selectors --vault "$(VAULT)" --check

release-governance-sync:
	$(PYTHON) -m ops.scripts.test.generate_release_governance_from_lane_registry --vault "$(VAULT)"

release-governance-sync-check:
	@$(MAKE) _internal-release-governance-sync-check

_internal-release-governance-sync-check:
	$(PYTHON) -m ops.scripts.test.generate_release_governance_from_lane_registry --vault "$(VAULT)" --check --json

fast-smoke:
	$(PYTHON) -m pytest $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)

test-boundary-contract-smoke:
	$(PYTHON) -m pytest $(DEFAULT_TEST_BOUNDARY_TESTS) $(PYTEST_SERIAL_FLAGS)

runtime-hotspot-smoke:
	$(PYTHON) -m pytest -q $(RUNTIME_HOTSPOT_SMOKE_TESTS) $(PYTEST_CACHE_ISOLATION_FLAGS) $(PYTEST_SERIAL_FLAGS)

test-schema-static-smoke:
	$(PYTHON) -m pytest -q $(SCHEMA_STATIC_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)

test-release-closeout-regression-pack:
	$(PYTHON) -m pytest $(RELEASE_CLOSEOUT_REGRESSION_TESTS) $(PYTEST_SERIAL_FLAGS)

release-closeout-regression-dry-run: tmp-json-clean
	$(MAKE) test-release-closeout-regression-pack
	$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",) --fail-on-fail

release-closeout-finality-verify-ci-artifact:
	$(PYTHON) -m ops.scripts.release_closeout_finality_attestation --vault "$(VAULT)" --attestation "$(RELEASE_CLOSEOUT_FINALITY_ATTESTATION_OUT)" --verify --verify-out "$(RELEASE_CLOSEOUT_FINALITY_VERIFY_CI_OUT)"

release-closeout-cost-evidence-ci-artifact:
	$(PYTHON) -m ops.scripts.release_closeout_fixed_point_cost_trend --vault "$(VAULT)" --previous "$(RELEASE_CLOSEOUT_FIXED_POINT_COST_TREND_OUT)" --out "$(RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT)" --no-fail

ci-report-contract-tier:
	@case "$(CI_REPORT_CONTRACT_EVENT_NAME):$(CI_REPORT_CONTRACT_REF)" in \
		workflow_dispatch:*|push:refs/heads/release/*|push:refs/tags/*) \
			$(MAKE) test-report-contract-all ;; \
		*) \
			$(MAKE) test-report-contract-core ;; \
	esac
	$(MAKE) external-report-reference-manifest-release-check

test-report-contract-core:
	$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)

test-report-contract-all:
	$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)

test-release-sealing-core:
	$(PYTHON) -m pytest $(RELEASE_SEALING_TESTS) $(PYTEST_RELEASE_SEALING_FLAGS)

test-release-sealing-all:
	$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_SEALING_MARK_EXPR)" $(PYTEST_RELEASE_SEALING_FLAGS)

test-subprocess:
	$(PYTHON) -m pytest $(SUBPROCESS_TESTS) $(PYTEST_SERIAL_FLAGS)

report-schema-samples-check:
	@$(MAKE) _internal-report-schema-samples-check

_internal-report-schema-samples-check:
	$(PYTHON) tools/regenerate_report_schema_samples.py --check

report-schema-samples-regenerate: clean-fixture-regeneration-guard
	$(PYTHON) tools/regenerate_report_schema_samples.py

runtime-hotspot-goldens-check:
	@$(MAKE) _internal-runtime-hotspot-goldens-check

_internal-runtime-hotspot-goldens-check:
	$(PYTHON) -m pytest tests/test_runtime_hotspot_facade_golden_outputs.py $(PYTEST_CACHE_ISOLATION_FLAGS) $(PYTEST_SERIAL_FLAGS)

full-pytest-generated-preflight:
	$(MAKE) _internal-report-schema-samples-check
	$(MAKE) script-output-surfaces-check
	$(MAKE) _internal-runtime-hotspot-goldens-check

report-contract-closeout-precheck:
	@for target in $$($(PYTHON) -m ops.scripts.report_contract_closeout_runtime --vault "$(VAULT)"); do \
		$(MAKE) $$target; \
	done

report-contract-closeout:
	$(MAKE) report-contract-closeout-precheck
	$(MAKE) release-smoke-full-reuse
	$(MAKE) test-execution-summary-report-contract
	$(MAKE) report-contract-closeout-generated-artifacts
	@echo "report-contract-closeout refreshed generated precheck evidence, report-contract test evidence, closeout artifacts, and auto-improve readiness without rerunning the pytest wrapper."

report-contract-closeout-generated-artifacts:
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-summary-report
	$(MAKE) release-evidence-cohort
	$(MAKE) release-closeout-summary-report
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) generated-artifact-converge

test-execution-summary-fast:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FAST_SUITE)" --collect-nodeids -- $(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_SERIAL_FLAGS)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_FAST_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary

ifeq ($(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE),run)
test-execution-summary-report-contract:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary
else ifeq ($(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE),bootstrap-refresh)
test-execution-summary-report-contract:
	$(MAKE) auto-improve-readiness-report
	$(MAKE) release-smoke-full-reuse
	$(MAKE) generated-artifact-converge
	@status=0; $(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS) || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary || exit $$?; if [ $$status -ne 0 ]; then echo "test-execution-summary-report-contract bootstrap refresh promoted a non-pass summary; strict mode will rerun later in closeout."; fi
	$(MAKE) generated-artifact-converge
else ifeq ($(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE),bootstrap-refresh-no-smoke)
test-execution-summary-report-contract:
	$(MAKE) auto-improve-readiness-report
	$(MAKE) generated-artifact-converge
	@status=0; $(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS) || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary || exit $$?; if [ $$status -ne 0 ]; then echo "test-execution-summary-report-contract bootstrap refresh without smoke promoted a non-pass summary; strict mode will rerun later in closeout."; fi
	$(MAKE) generated-artifact-converge
else ifeq ($(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE),current-check)
test-execution-summary-report-contract:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CHECK_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --reuse-if-current --reuse-only --reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)" --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)
else ifeq ($(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE),current-or-refresh)
test-execution-summary-report-contract:
	@if $(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=current-check; then \
		echo "test execution summary is current; reused $(TEST_EXECUTION_SUMMARY_REUSE_FROM)"; \
	else \
		$(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=reuse; \
	fi
else ifeq ($(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE),reuse)
test-execution-summary-report-contract:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE)" --collect-nodeids --reuse-if-current --refresh-revision-if-same-tree --reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)" --deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)" -- $(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary
else
test-execution-summary-report-contract:
	@printf '%s\n' "unsupported TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=$(TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE)"; exit 2
endif

ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),run)
test-execution-summary-full:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=body
	$(MAKE) generated-artifact-converge
else ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),body)
test-execution-summary-full:
	$(MAKE) full-pytest-generated-preflight
	rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"
	mkdir -p "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)" "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)"
	@printf '%s\n' "test-execution-summary-full: suite=$(TEST_EXECUTION_SUMMARY_FULL_SUITE) shard=full-suite-shard-1 heartbeat_interval_seconds=$(TEST_EXECUTION_SUMMARY_FULL_HEARTBEAT_INTERVAL_SECONDS) log=$(TEST_EXECUTION_SUMMARY_FULL_LOG_OUT)"
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)/full-suite-shard-1.json" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_SUITE)" --collect-nodeids --heartbeat-interval-seconds "$(TEST_EXECUTION_SUMMARY_FULL_HEARTBEAT_INTERVAL_SECONDS)" --heartbeat-label "full-suite-shard-1" --junit-xml-path "$(TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT)" --execution-log-out "$(TEST_EXECUTION_SUMMARY_FULL_LOG_OUT)" --failed-nodeids-out "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.failed-nodeids.txt" -- $(PYTHON) -m pytest --junit-xml "$(TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT)" $(TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS)
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SUITE)" --aggregate --aggregate-dir "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary
else ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),refresh)
test-execution-summary-full:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=run
	@echo "full-suite evidence refreshed; collect-only nodeid digest and count recorded in $(TEST_EXECUTION_SUMMARY_FULL_OUT)"
else ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),refresh-no-converge)
test-execution-summary-full:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=body
	@echo "full-suite evidence refreshed without generated artifact convergence; release preseal must reuse $(TEST_EXECUTION_SUMMARY_FULL_OUT) by currentness check"
else ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),aggregate-reuse)
test-execution-summary-full:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SUITE)" --aggregate --aggregate-dir "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)" --reuse-if-current --refresh-revision-if-same-tree --reuse-from "$(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_OUT)" --schema ops/schemas/test-execution-summary.schema.json --expected-artifact-kind test_execution_summary --expected-producer ops.scripts.test_execution_summary
else ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),current-check)
test-execution-summary-full:
	$(PYTHON) -m ops.scripts.test_execution_summary --vault "$(VAULT)" --out "$(TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT)" --suite "$(TEST_EXECUTION_SUMMARY_FULL_SUITE)" --aggregate --reuse-if-current --reuse-only --reuse-from "$(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"
else ifeq ($(TEST_EXECUTION_SUMMARY_FULL_MODE),current-or-refresh)
test-execution-summary-full:
	@if $(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=current-check; then \
		echo "full-suite evidence is current; reused $(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"; \
	elif $(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=aggregate-reuse; then \
		echo "full-suite evidence metadata refreshed from current shards; reused $(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"; \
	else \
		$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=refresh-no-converge; \
	fi
else
test-execution-summary-full:
	@printf '%s\n' "unsupported TEST_EXECUTION_SUMMARY_FULL_MODE=$(TEST_EXECUTION_SUMMARY_FULL_MODE)"; exit 2
endif

test-execution-summary: test-execution-summary-report-contract

test-execution-summary-report-contract-refresh:
	$(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=bootstrap-refresh

test-execution-summary-report-contract-refresh-no-smoke:
	$(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=bootstrap-refresh-no-smoke

test-execution-summary-current-check:
	$(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=current-check

test-execution-summary-current-or-refresh:
	$(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=current-or-refresh

test-execution-summary-reuse:
	$(MAKE) test-execution-summary-report-contract TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=reuse

test-execution-summary-full-body:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=body

test-execution-summary-full-refresh:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=refresh

test-execution-summary-full-refresh-no-converge:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=refresh-no-converge

test-execution-summary-full-aggregate-reuse:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=aggregate-reuse

test-execution-summary-full-current-check:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=current-check

test-execution-summary-full-current-or-refresh:
	$(MAKE) test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=current-or-refresh

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

test: test-fast test-boundary-contract-smoke

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
