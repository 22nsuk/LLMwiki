PUBLIC_CHECK_SUMMARY_OUT ?= ops/reports/public-check-summary.json
PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT ?= tmp/public-check-summary.candidate.json
PUBLIC_CHECK_TIMEOUT_SECONDS ?= 5400
PUBLIC_OUT ?= $(if $(TMPDIR),$(TMPDIR),/tmp)/llm-wiki-public-repo
PUBLIC_PYTHON ?= $(if $(wildcard $(firstword $(PYTHON))),$(abspath $(firstword $(PYTHON))),$(shell command -v $(firstword $(PYTHON))))

.PHONY: sync-public-policy public-export public-check-summary public-check public-check-serial public-check-parallel public-check-all public-check-all-serial public-check-all-parallel 

sync-public-policy:
	$(PYTHON) -m ops.scripts.sync_public_surface_gitignore --gitignore ".gitignore"

public-export:
	$(PYTHON) -m ops.scripts.export_public_repo --vault "$(VAULT)" --out "$(PUBLIC_OUT)"

public-check-summary: script-output-surfaces
	$(PYTHON) -m ops.scripts.public_check_summary --vault "$(VAULT)" --out "$(PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT)" --public-out "$(PUBLIC_OUT)" --public-python "$(PUBLIC_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --pytest-mark-expr "$(PYTEST_PUBLIC_MARK_EXPR)" --pytest-flags "$(PYTEST_FLAGS)" --timeout-seconds "$(PUBLIC_CHECK_TIMEOUT_SECONDS)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT)" --out "$(PUBLIC_CHECK_SUMMARY_OUT)" --schema ops/schemas/public-check-summary.schema.json --expected-artifact-kind public_check_summary --expected-producer ops.scripts.public_check_summary

public-check: public-check-summary

public-check-serial:
	$(MAKE) public-check-summary PYTEST_FLAGS="$(PYTEST_SERIAL_FLAGS)"

public-check-parallel:
	$(MAKE) public-check-summary PYTEST_FLAGS="$(PYTEST_PARALLEL_FLAGS)"

public-check-all:
	$(MAKE) public-check-summary PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_FLAGS)"

public-check-all-serial:
	$(MAKE) public-check-summary PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_SERIAL_FLAGS)"

public-check-all-parallel:
	$(MAKE) public-check-summary PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_PARALLEL_FLAGS)"
