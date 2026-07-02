PUBLIC_CHECK_SUMMARY_OUT ?= ops/reports/public-check-summary.json
PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT ?= tmp/public-check-summary.candidate.json
PUBLIC_CHECK_SUMMARY_CHECK_OUT ?= tmp/public-check-summary-check.json
PUBLIC_CHECK_SUMMARY_REUSE_FROM ?= $(PUBLIC_CHECK_SUMMARY_OUT)
PUBLIC_CHECK_TIMEOUT_SECONDS ?= 5400
PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS ?= 30
PUBLIC_OUT ?= $(if $(TMPDIR),$(TMPDIR),/tmp)/llm-wiki-public-repo
PUBLIC_PYTHON ?= $(if $(wildcard $(firstword $(PYTHON))),$(abspath $(firstword $(PYTHON))),$(shell command -v $(firstword $(PYTHON))))
PUBLIC_GITIGNORE_TEMPLATE ?= ops/templates/public-mirror.gitignore

.PHONY: sync-public-policy sync-public-policy-check public-export public-check-summary public-check-summary-check public-check-summary-current-check public-check-summary-current-or-refresh ci-public-tier public-check public-check-serial public-check-parallel public-check-all public-check-all-check public-check-all-serial public-check-all-parallel review-surface-manifest

review-surface-manifest:
	$(PYTHON) -m ops.scripts.public.review_surface_manifest --vault "$(VAULT)"

sync-public-policy:
	$(PYTHON) -m ops.scripts.public.sync_public_surface_gitignore --gitignore "$(PUBLIC_GITIGNORE_TEMPLATE)"

sync-public-policy-check:
	$(PYTHON) -m ops.scripts.public.sync_public_surface_gitignore --gitignore "$(PUBLIC_GITIGNORE_TEMPLATE)" --check

public-export:
	$(PYTHON) -m ops.scripts.export_public_repo --vault "$(VAULT)" --out "$(PUBLIC_OUT)"

public-check-summary: script-output-surfaces-check
	$(PYTHON) -m ops.scripts.public_check_summary --vault "$(VAULT)" --out "$(PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT)" --public-out "$(PUBLIC_OUT)" --public-python "$(PUBLIC_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --pytest-mark-expr "$(PYTEST_PUBLIC_MARK_EXPR)" --pytest-flags "$(PYTEST_FLAGS)" --timeout-seconds "$(PUBLIC_CHECK_TIMEOUT_SECONDS)" --heartbeat-interval-seconds "$(PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT)" --out "$(PUBLIC_CHECK_SUMMARY_OUT)" --schema ops/schemas/public-check-summary.schema.json --expected-artifact-kind public_check_summary --expected-producer ops.scripts.public_check_summary

public-check-summary-check:
	$(PYTHON) -m ops.scripts.public_check_summary --vault "$(VAULT)" --out "$(PUBLIC_CHECK_SUMMARY_CHECK_OUT)" --public-out "$(PUBLIC_OUT)" --public-python "$(PUBLIC_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --pytest-mark-expr "$(PYTEST_PUBLIC_MARK_EXPR)" --pytest-flags "$(PYTEST_FLAGS)" --timeout-seconds "$(PUBLIC_CHECK_TIMEOUT_SECONDS)" --heartbeat-interval-seconds "$(PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS)"

public-check-summary-current-check:
	$(PYTHON) -m ops.scripts.public_check_summary --vault "$(VAULT)" --out "$(PUBLIC_CHECK_SUMMARY_CHECK_OUT)" --public-out "$(PUBLIC_OUT)" --public-python "$(PUBLIC_PYTHON)" --ruff-targets "$(RUFF_TARGETS)" --mypy-targets "$(MYPY_TARGETS)" --pytest-mark-expr "$(PYTEST_PUBLIC_MARK_EXPR)" --pytest-flags "$(PYTEST_FLAGS)" --timeout-seconds "$(PUBLIC_CHECK_TIMEOUT_SECONDS)" --heartbeat-interval-seconds "$(PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS)" --reuse-if-current --reuse-only --reuse-from "$(PUBLIC_CHECK_SUMMARY_REUSE_FROM)"

public-check-summary-current-or-refresh:
	@if $(MAKE) public-check-summary-current-check; then \
		echo "public check summary is current; reused $(PUBLIC_CHECK_SUMMARY_REUSE_FROM)"; \
	else \
		$(MAKE) public-check-summary; \
	fi

ci-public-tier:
	$(MAKE) public-check

public-check: public-check-summary

public-check-serial:
	$(MAKE) public-check-summary PYTEST_FLAGS="$(PYTEST_SERIAL_FLAGS)"

public-check-parallel:
	$(MAKE) public-check-summary PYTEST_FLAGS="$(PYTEST_PARALLEL_FLAGS)"

public-check-all:
	$(MAKE) public-check-summary PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_FLAGS)"

public-check-all-check:
	$(MAKE) public-check-summary-current-check PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_FLAGS)"

public-check-all-serial:
	$(MAKE) public-check-summary PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_SERIAL_FLAGS)"

public-check-all-parallel:
	$(MAKE) public-check-summary PYTEST_PUBLIC_MARK_EXPR="" PYTEST_FLAGS="$(PYTEST_PARALLEL_FLAGS)"
