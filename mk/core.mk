BOOTSTRAP_PREFLIGHT_OUT ?= ops/reports/bootstrap-preflight-report.json
BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS ?= developer
TOOLS_MIGRATION_PLAN_OUT ?= tmp/tools-migration-plan.json
SUBAGENT_PROFILE_SCHEMA_OUT ?= tmp/subagent-profile-schema.json
COMPATIBILITY_ALIAS_DEPRECATION_OUT ?= tmp/compatibility-alias-deprecation.json

.PHONY: help dev-install bootstrap-preflight tools-migration-plan subagent-profile-schema compatibility-alias-deprecation

help:
	@printf '%s\n' \
		"LLMwiki operator entrypoints" \
		"" \
		"Setup:" \
		"  make dev-install                  install/update the local developer environment" \
		"  make bootstrap-preflight          write the environment preflight report" \
		"" \
		"Source checks:" \
		"  make static                       run Ruff and mypy base gates" \
		"  make ruff-strict-preview          run strict Ruff preview across ops/scripts tests tools" \
		"  make mypy-strict-preview          run strict mypy preview across ops/scripts tests tools" \
		"  make strict-preview-audit         audit strict preview debt across ops/scripts tests tools" \
		"" \
		"Report contracts:" \
		"  make report-contracts-core        run core report contract tests" \
		"  make external-report-lifecycle-refresh refresh active external-report evidence" \
		"  make remediation-backlog          refresh remediation backlog evidence" \
		"" \
		"Public mirror:" \
		"  make sync-public-policy           update public mirror policy templates" \
		"  make public-check                 export and verify the public mirror" \
		"  make public-check-all             export and run the full public check suite" \
		"" \
		"Mechanism:" \
		"  make auto-improve-readiness       refresh maintainer readiness evidence" \
		"  make goal-runtime-run-admission   check whether a goal-native run may start" \
		"" \
		"Release:" \
		"  make release-run-ready            converge and verify run-ready evidence" \
		"  make release-sealed-run-ready     verify sealed release readiness" \
		"  make release-auto-promotion-ready verify auto-promotion readiness"

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

tools-migration-plan:
	$(PYTHON) -m ops.scripts.tools_migration_plan --vault "$(VAULT)" --out "$(TOOLS_MIGRATION_PLAN_OUT)"

subagent-profile-schema:
	$(PYTHON) -m ops.scripts.subagent_profile_schema --vault "$(VAULT)" --out "$(SUBAGENT_PROFILE_SCHEMA_OUT)"

compatibility-alias-deprecation:
	$(PYTHON) -m ops.scripts.compatibility_alias_deprecation --vault "$(VAULT)" --out "$(COMPATIBILITY_ALIAS_DEPRECATION_OUT)"
