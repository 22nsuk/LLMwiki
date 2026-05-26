RUFF_TARGETS ?= ops/scripts tests tools
RUFF_STRICT_PREVIEW_RULES ?= B,SIM,UP,I
STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools
STRICT_PREVIEW_AUDIT_OUT ?= tmp/strict-preview-audit.json
RUFF_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)
MYPY_TARGETS ?= ops/scripts
MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs
MYPY_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)
UV ?= uv

.PHONY: static ruff ruff-strict-preview strict-preview-audit typecheck mypy-strict-preview uv-lock-check

static: uv-lock-check ruff typecheck

uv-lock-check:
	$(UV) lock --check

ruff:
	$(PYTHON) -m ruff check $(RUFF_TARGETS)

ruff-strict-preview:
	$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --targets "$(RUFF_STRICT_PREVIEW_TARGETS)" --select "$(RUFF_STRICT_PREVIEW_RULES)"

strict-preview-audit:
	$(PYTHON) tools/strict_preview_audit.py --vault "$(VAULT)" --out "$(STRICT_PREVIEW_AUDIT_OUT)" --targets "$(STRICT_PREVIEW_AUDIT_TARGETS)" --ruff-select "$(RUFF_STRICT_PREVIEW_RULES)" --mypy-flags "$(MYPY_STRICT_PREVIEW_FLAGS)" --python "$(firstword $(PYTHON))"

typecheck:
	$(PYTHON) -m mypy $(MYPY_TARGETS)

mypy-strict-preview:
	$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)
