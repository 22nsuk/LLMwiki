VENV_DIR ?= .venv
VENV_PYTHON ?= $(VENV_DIR)/bin/python
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)
BOOTSTRAP_PYTHON ?= python3
VAULT ?= .
EXECUTION_LANE_POLICY ?= ops/policies/execution-lanes.json

include mk/core.mk
include mk/static.mk
include mk/test.mk
include mk/eval.mk
include mk/artifact.mk
include mk/registry.mk
include mk/mechanism.mk
include mk/release.mk
include mk/public.mk
include mk/supply_chain.mk

export PYTEST_DISABLE_PLUGIN_AUTOLOAD
export PYTHONDONTWRITEBYTECODE

.PHONY: check check-finalized check-clean check-clean-lane-guard check-conditional check-serial check-all check-all-serial check-strict canonical-parity-guard

check: uv-lock-check static artifact-freshness-check registry-preflight-check lint eval stage2-eval planning-gate unit-tests

check-finalized:
	$(MAKE) auto-improve-readiness-report
	$(MAKE) check
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-post-check-finalizer-dry-run
	$(MAKE) release-closeout-fixed-point
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required
	$(MAKE) release-closeout-finality-verify

canonical-parity-guard:
	$(MAKE) generated-artifact-converge
	$(MAKE) release-closeout-post-check-finalizer-dry-run
	$(MAKE) release-closeout-fixed-point
	$(MAKE) tmp-json-clean
	$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required

check-conditional: check

check-clean-lane-guard:
	$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target check-clean

check-clean: check-clean-lane-guard check-conditional warning-budget release-evidence-cohort-check

check-serial: uv-lock-check static artifact-freshness-check registry-preflight-check lint eval stage2-eval planning-gate unit-tests-serial

check-all: uv-lock-check static artifact-freshness-check registry-preflight-check lint eval stage2-eval planning-gate unit-tests-all

check-all-serial: uv-lock-check static artifact-freshness-check registry-preflight-check lint eval stage2-eval planning-gate unit-tests-all-serial

check-strict: check warning-budget complexity-budget-touched-check
