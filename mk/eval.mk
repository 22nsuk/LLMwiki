ARTIFACT_DIR ?=
EVAL_FLAGS ?= --require-max-score
STRUCTURAL_COMPLEXITY_BUDGET_OUT ?= ops/reports/structural-complexity-budget.json
STRUCTURAL_COMPLEXITY_BUDGET_TOUCHED_OUT ?= ops/reports/structural-complexity-budget-touched.json
CHANGED_FILES_MANIFEST ?=
STRUCTURAL_COMPLEXITY_BUDGET_TARGETS ?=
WIKI_LINT_REVIEW_CLASSIFICATION_OUT ?= tmp/wiki-lint-review-classification.json
FUNCTION_BUDGET_REFACTOR_PROPOSALS_OUT ?= ops/reports/function-budget-refactor-proposals.json
FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT ?= tmp/function-budget-refactor-proposals.candidate.json
LINT_UPLIFT_PLAN_OUT ?= ops/reports/lint-uplift-plan.json
TYPE_UPLIFT_PLAN_OUT ?= ops/reports/type-uplift-plan.json

.PHONY: lint lint-uplift-plan type-uplift-plan wiki-lint-review-classification function-budget-refactor-proposals eval stage2-eval planning-gate warning-budget complexity-budget complexity-budget-check complexity-budget-touched-check

lint:
	$(PYTHON) -m ops.scripts.wiki_lint --vault "$(VAULT)"

lint-uplift-plan:
	$(PYTHON) -m ops.scripts.lint_uplift_plan --vault "$(VAULT)" --out "$(LINT_UPLIFT_PLAN_OUT)" --targets "$(STRICT_PREVIEW_AUDIT_TARGETS)" --ruff-select "$(RUFF_STRICT_PREVIEW_RULES)"

type-uplift-plan:
	$(PYTHON) -m ops.scripts.type_uplift_plan --vault "$(VAULT)" --out "$(TYPE_UPLIFT_PLAN_OUT)" --targets "$(STRICT_PREVIEW_AUDIT_TARGETS)"

wiki-lint-review-classification:
	$(PYTHON) -m ops.scripts.wiki_lint_review_classification --vault "$(VAULT)" --out "$(WIKI_LINT_REVIEW_CLASSIFICATION_OUT)"

function-budget-refactor-proposals: wiki-lint-review-classification
	$(PYTHON) -m ops.scripts.function_budget_refactor_proposals --vault "$(VAULT)" --classification "$(WIKI_LINT_REVIEW_CLASSIFICATION_OUT)" --out "$(FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT)" --out "$(FUNCTION_BUDGET_REFACTOR_PROPOSALS_OUT)" --schema ops/schemas/function-budget-refactor-proposals.schema.json --expected-artifact-kind function_budget_refactor_proposals --expected-producer ops.scripts.function_budget_refactor_proposals

eval:
	$(PYTHON) -m ops.scripts.wiki_eval --vault "$(VAULT)" $(EVAL_FLAGS)

stage2-eval:
	$(PYTHON) -m ops.scripts.wiki_stage2_eval --vault "$(VAULT)" $(EVAL_FLAGS)

planning-gate:
	$(PYTHON) -m ops.scripts.planning_gate_validate --vault "$(VAULT)" $(if $(ARTIFACT_DIR),--artifact-dir "$(ARTIFACT_DIR)",)

warning-budget:
	$(PYTHON) -m ops.scripts.warning_budget --vault "$(VAULT)"
complexity-budget:
	$(PYTHON) -m ops.scripts.structural_complexity_budget --vault "$(VAULT)" --out "$(STRUCTURAL_COMPLEXITY_BUDGET_OUT)"

complexity-budget-check:
	$(PYTHON) -m ops.scripts.structural_complexity_budget --vault "$(VAULT)" --out "$(STRUCTURAL_COMPLEXITY_BUDGET_OUT)" --fail-on-attention

complexity-budget-touched-check:
	@if [ -n "$(CHANGED_FILES_MANIFEST)$(STRUCTURAL_COMPLEXITY_BUDGET_TARGETS)" ]; then \
		$(PYTHON) -m ops.scripts.structural_complexity_budget --vault "$(VAULT)" --out "$(STRUCTURAL_COMPLEXITY_BUDGET_TOUCHED_OUT)" --fail-on-attention $(if $(CHANGED_FILES_MANIFEST),--changed-files-manifest "$(CHANGED_FILES_MANIFEST)",) $(foreach target,$(STRUCTURAL_COMPLEXITY_BUDGET_TARGETS),--target "$(target)"); \
	else \
		echo "complexity-budget-touched-check skipped: set CHANGED_FILES_MANIFEST or STRUCTURAL_COMPLEXITY_BUDGET_TARGETS"; \
	fi
