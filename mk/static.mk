RUFF_TARGETS ?= ops/scripts tests tools
RUFF_STRICT_PREVIEW_RULES ?= PTH201
STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools
STRICT_PREVIEW_AUDIT_OUT ?= tmp/strict-preview-audit.json
RUFF_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)
MYPY_TARGETS ?= ops/scripts
MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs
MYPY_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)
TOOL_CACHE_ROOT ?= tmp/tool-cache
TOOL_CACHE_PLATFORM ?= $(shell $(PYTHON) -c 'import os, platform; release = platform.release().lower(); print("wsl" if os.environ.get("WSL_DISTRO_NAME") or "microsoft" in release else (platform.system().lower() or "local"))' 2>/dev/null || echo local)
RUFF_CACHE_DIR ?= $(TOOL_CACHE_ROOT)/ruff/$(TOOL_CACHE_PLATFORM)
MYPY_CACHE_DIR ?= $(TOOL_CACHE_ROOT)/mypy/$(TOOL_CACHE_PLATFORM)
RUFF_CACHE_FLAGS ?= --cache-dir $(RUFF_CACHE_DIR)
MYPY_CACHE_FLAGS ?= --cache-dir $(MYPY_CACHE_DIR)
LOCAL_CACHE_CLEAN_PATHS ?= .pytest_cache .hypothesis .ruff_cache .mypy_cache $(TOOL_CACHE_ROOT)
LOCAL_TOOL_STATE_CLEAN_PATHS ?= .agents .obsidian .serena .vscode .ouroboros .ouroboros_eval_artifact.md
LOCAL_CACHE_CLEAN_FIND_ROOTS ?= ops tests tools
UV_CACHE_PRUNE_FLAGS ?=
UV ?= uv
UV_CANONICAL_INDEX_URL ?= https://pypi.org/simple
UV_LOCK_CHECK_INDEX_FLAGS ?= --default-index "$(UV_CANONICAL_INDEX_URL)"

.PHONY: static ruff ruff-strict-preview strict-preview-audit typecheck mypy-strict-preview uv-lock-check local-cache-clean local-tool-state-clean uv-cache-prune

static: uv-lock-check ruff typecheck

uv-lock-check:
	UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) lock --check $(UV_LOCK_CHECK_INDEX_FLAGS)

ruff:
	$(PYTHON) -m ruff check $(RUFF_CACHE_FLAGS) $(RUFF_TARGETS)

ruff-strict-preview:
	$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --targets "$(RUFF_STRICT_PREVIEW_TARGETS)" --select "$(RUFF_STRICT_PREVIEW_RULES)" --cache-dir "$(RUFF_CACHE_DIR)" --exit-zero

strict-preview-audit:
	$(PYTHON) tools/strict_preview_audit.py --vault "$(VAULT)" --out "$(STRICT_PREVIEW_AUDIT_OUT)" --targets "$(STRICT_PREVIEW_AUDIT_TARGETS)" --ruff-select "$(RUFF_STRICT_PREVIEW_RULES)" --ruff-cache-dir "$(RUFF_CACHE_DIR)" --mypy-flags "$(MYPY_CACHE_FLAGS) $(MYPY_STRICT_PREVIEW_FLAGS)" --python "$(firstword $(PYTHON))"

typecheck:
	$(PYTHON) -m mypy $(MYPY_CACHE_FLAGS) $(MYPY_TARGETS)

mypy-strict-preview:
	$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_CACHE_FLAGS) $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)

local-cache-clean:
	rm -rf $(LOCAL_CACHE_CLEAN_PATHS)
	find $(LOCAL_CACHE_CLEAN_FIND_ROOTS) -type d -name __pycache__ -prune -exec rm -rf {} +
	find $(LOCAL_CACHE_CLEAN_FIND_ROOTS) -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

local-tool-state-clean:
	rm -rf $(LOCAL_TOOL_STATE_CLEAN_PATHS)

uv-cache-prune:
	$(UV) cache prune $(UV_CACHE_PRUNE_FLAGS)
