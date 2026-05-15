RUFF_TARGETS ?= ops/scripts tests tools
RUFF_STRICT_PREVIEW_RULES ?= B,SIM,UP,I
RUFF_STRICT_PREVIEW_ALLOWLIST ?= ops/ruff-strict-preview-allowlist.txt
MYPY_TARGETS ?= @ops/mypy-allowlist.txt
MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs
MYPY_STRICT_PREVIEW_TARGETS ?= @ops/mypy-strict-preview-allowlist.txt

.PHONY: static ruff ruff-strict-preview typecheck mypy-strict-preview 

static: ruff typecheck

ruff:
	$(PYTHON) -m ruff check $(RUFF_TARGETS)

ruff-strict-preview:
	$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --allowlist "$(RUFF_STRICT_PREVIEW_ALLOWLIST)" --select "$(RUFF_STRICT_PREVIEW_RULES)"

typecheck:
	$(PYTHON) -m mypy $(MYPY_TARGETS)

mypy-strict-preview:
	$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)
