BOOTSTRAP_PREFLIGHT_OUT ?= ops/reports/bootstrap-preflight-report.json
BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS ?= developer

.PHONY: dev-install bootstrap-preflight 

dev-install:
	@if command -v uv >/dev/null 2>&1; then \
		echo "Using uv to create/update $(VENV_DIR)"; \
		uv venv --allow-existing --python "$(BOOTSTRAP_PYTHON)" "$(VENV_DIR)"; \
		uv pip install --python "$(VENV_PYTHON)" -r requirements-dev.txt; \
		uv pip install --python "$(VENV_PYTHON)" -e .; \
	else \
		echo "uv not found; falling back to stdlib venv via $(BOOTSTRAP_PYTHON)"; \
		"$(BOOTSTRAP_PYTHON)" -m venv "$(VENV_DIR)"; \
		"$(VENV_PYTHON)" -m pip install --upgrade pip; \
		"$(VENV_PYTHON)" -m pip install -r requirements-dev.txt; \
		"$(VENV_PYTHON)" -m pip install -e .; \
	fi
	@echo "Development environment is ready at $(VENV_PYTHON)"
	@echo "Subsequent 'make check' and 'make test' invocations will auto-use $(VENV_PYTHON) when it exists."

bootstrap-preflight:
	$(PYTHON) -m ops.scripts.bootstrap_preflight --vault "$(VAULT)" --dev --environment-class "$(BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS)" --out "$(BOOTSTRAP_PREFLIGHT_OUT)"
