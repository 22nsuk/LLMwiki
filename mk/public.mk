PUBLIC_CHECK_SUMMARY_OUT ?= ops/reports/public-check-summary.json
PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT ?= tmp/public-check-summary.candidate.json
PUBLIC_CHECK_SUMMARY_CHECK_OUT ?= tmp/public-check-summary-check.json
PUBLIC_CHECK_SUMMARY_REUSE_FROM ?= $(PUBLIC_CHECK_SUMMARY_OUT)
PUBLIC_CHECK_TIMEOUT_SECONDS ?= 5400
PUBLIC_CHECK_HEARTBEAT_INTERVAL_SECONDS ?= 30
PUBLIC_OUT ?= $(if $(TMPDIR),$(TMPDIR),/tmp)/llm-wiki-public-repo
PUBLIC_PYTHON ?= $(if $(wildcard $(firstword $(PYTHON))),$(abspath $(firstword $(PYTHON))),$(shell command -v $(firstword $(PYTHON))))
PUBLIC_GITIGNORE_TEMPLATE ?= ops/templates/public-mirror.gitignore
CBM_BIN ?= codebase-memory-mcp
CBM_CACHE_ROOT ?= $(if $(XDG_CACHE_HOME),$(XDG_CACHE_HOME),$(HOME)/.cache)
CBM_PUBLIC_OUT ?= $(CBM_CACHE_ROOT)/llmwiki/codebase-memory-mcp/public-surface
CBM_CACHE_DIR ?= $(CBM_CACHE_ROOT)/codebase-memory-mcp/llmwiki-public
CBM_IGNORE_TEMPLATE ?= ops/templates/codebase-memory-mcp.cbmignore
CBM_PROJECT_NAME ?= $(subst /,-,$(patsubst /%,%,$(CBM_PUBLIC_OUT)))
CBM_SMOKE_PATTERN ?= cbm_public_export
CBM_EXPORT_FLAGS ?= --summary
CBM_SEARCH_PATTERN ?= $(CBM_SMOKE_PATTERN)
CBM_SEARCH_LIMIT ?= 10

.PHONY: sync-public-policy sync-public-policy-check public-export public-check-summary public-check-summary-check public-check-summary-current-check public-check-summary-current-or-refresh ci-public-tier public-check public-check-serial public-check-parallel public-check-all public-check-all-check public-check-all-serial public-check-all-parallel cbm-require-bin cbm-safe-local-paths cbm-export-public cbm-index-public cbm-list-projects-public cbm-schema-public cbm-architecture-public cbm-search-public cbm-smoke-public cbm-reset-local

sync-public-policy:
	$(PYTHON) -m ops.scripts.sync_public_surface_gitignore --gitignore "$(PUBLIC_GITIGNORE_TEMPLATE)"

sync-public-policy-check:
	$(PYTHON) -m ops.scripts.sync_public_surface_gitignore --gitignore "$(PUBLIC_GITIGNORE_TEMPLATE)" --check

public-export:
	$(PYTHON) -m ops.scripts.export_public_repo --vault "$(VAULT)" --out "$(PUBLIC_OUT)"

cbm-require-bin:
	@command -v "$(CBM_BIN)" >/dev/null 2>&1 || { printf '%s\n' "codebase-memory-mcp binary not found; install a verified operator-local binary or set CBM_BIN=/path/to/codebase-memory-mcp"; exit 127; }

cbm-safe-local-paths:
	$(PYTHON) -m ops.scripts.cbm_public_export --vault "$(VAULT)" --out "$(CBM_PUBLIC_OUT)" --cache-dir "$(CBM_CACHE_DIR)" --cache-root "$(CBM_CACHE_ROOT)" --check-local-paths

cbm-export-public: cbm-safe-local-paths
	$(PYTHON) -m ops.scripts.cbm_public_export --vault "$(VAULT)" --out "$(CBM_PUBLIC_OUT)" --cbmignore-template "$(CBM_IGNORE_TEMPLATE)" $(CBM_EXPORT_FLAGS)

cbm-index-public: cbm-require-bin cbm-export-public
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli index_repository '{"repo_path":"$(CBM_PUBLIC_OUT)"}'

cbm-list-projects-public: cbm-require-bin
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli list_projects

cbm-schema-public: cbm-require-bin
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli get_graph_schema '{"project":"$(CBM_PROJECT_NAME)"}'

cbm-architecture-public: cbm-require-bin
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli get_architecture '{"project":"$(CBM_PROJECT_NAME)"}'

cbm-search-public: cbm-require-bin
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli search_code '{"project":"$(CBM_PROJECT_NAME)","pattern":"$(CBM_SEARCH_PATTERN)","limit":$(CBM_SEARCH_LIMIT)}'

cbm-smoke-public: cbm-index-public
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli get_graph_schema '{"project":"$(CBM_PROJECT_NAME)"}'
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli get_architecture '{"project":"$(CBM_PROJECT_NAME)"}'
	CBM_CACHE_DIR="$(CBM_CACHE_DIR)" "$(CBM_BIN)" cli search_code '{"project":"$(CBM_PROJECT_NAME)","pattern":"$(CBM_SMOKE_PATTERN)","limit":5}'

cbm-reset-local: cbm-safe-local-paths
	@test -n "$(CBM_CACHE_DIR)" && test "$(CBM_CACHE_DIR)" != "/" || { printf '%s\n' "refusing to reset unsafe CBM_CACHE_DIR=$(CBM_CACHE_DIR)"; exit 2; }
	@test -n "$(CBM_PUBLIC_OUT)" && test "$(CBM_PUBLIC_OUT)" != "/" || { printf '%s\n' "refusing to reset unsafe CBM_PUBLIC_OUT=$(CBM_PUBLIC_OUT)"; exit 2; }
	rm -rf "$(CBM_CACHE_DIR)" "$(CBM_PUBLIC_OUT)"

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
