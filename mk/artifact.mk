SCRIPT_OUTPUT_SURFACES_OUT ?= ops/script-output-surfaces.json
SCRIPT_MODULE_SURFACES_OUT ?= ops/script-module-surfaces.json
CLEAN_FIXTURE_REGENERATION_GUARD_OUT ?= tmp/clean-fixture-regeneration-guard.json
CLOSURE_REGISTRY_ENVELOPE_REGISTRY ?= all
GENERATED_ARTIFACT_INDEX_OUT ?= ops/reports/generated-artifact-index.json
GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT ?= tmp/generated-artifact-index.candidate.json
GENERATED_ARTIFACT_INDEX_CHECK_OUT ?= tmp/generated-artifact-index-check.json
GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT ?= tmp/generated-artifact-converge-summary.json
GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT ?= tmp/generated-artifact-converge-summary.before.json
GENERATED_ARTIFACT_RETENTION_CLEAN_OUT ?= tmp/generated-artifact-retention-clean.json
GENERATED_ARTIFACT_RETENTION_COMPRESS_RUNS ?=
GENERATED_ARTIFACT_RETENTION_COMPRESS_TTL_DAYS ?= 30
GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY ?=
COMMAND_LOG_SUMMARY_BACKFILL_OUT ?= tmp/command-log-summary-backfill.json
COMMAND_LOG_SUMMARY_BACKFILL_APPLY ?=
COMMAND_LOG_SUMMARY_BACKFILL_ALL ?=
COMMAND_LOG_SUMMARY_BACKFILL_INCLUDE_RUN_COMMANDS ?=
COMMAND_LOG_SUMMARY_BACKFILL_CLOSE_PROMOTED_UNREFERENCED ?=
COMMAND_LOG_SUMMARY_BACKFILL_DELETE_RAW ?=
COMMAND_LOG_SUMMARY_BACKFILL_OPERATOR_CONFIRMATION ?=
COMMAND_LOG_SUMMARY_BACKFILL_RUN_ID ?=
ARCHIVE_EXECUTION_MANIFEST_OUT ?= tmp/archive-execution-manifest.json
ARCHIVE_EXECUTION_MANIFEST_SOURCE ?= tmp/archive-execution-manifest.json
ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION ?=
ARTIFACT_FRESHNESS_OUT ?= ops/reports/artifact-freshness-report.json
ARTIFACT_FRESHNESS_CANDIDATE_OUT ?= tmp/artifact-freshness-report.candidate.json
ARTIFACT_FRESHNESS_CHECK_OUT ?= tmp/artifact-freshness-report-check.json
ARTIFACT_FRESHNESS_MTIME_SOURCE ?= embedded_currentness
ARTIFACT_FRESHNESS_ZIP_METADATA ?=
ARTIFACT_FRESHNESS_PROGRESS ?= none
ARTIFACT_RELOCATION_AUDIT_OUT ?= ops/operator/artifact-relocation-audit.json
ARTIFACT_RELOCATION_AUDIT_CANDIDATE_OUT ?= tmp/artifact-relocation-audit.candidate.json
MANUAL_MUTATE_DEFECT_REGISTRY_OUT ?= ops/reports/manual-mutate-defect-registry.json
MAKE_TARGET_INVENTORY_OUT ?= tmp/make-target-inventory.json
WORKFLOW_DEPENDENCY_PLANNER_OUT ?= ops/reports/workflow-dependency-planner.json
WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT ?= tmp/workflow-dependency-planner.candidate.json
WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT ?= tmp/workflow-dependency-planner-check.json
WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST ?=
CHANGED_PATH_MINIMUM_PLAN_OUT ?= tmp/changed-path-minimum-plan.json
RELEASE_WORKFLOW_ORDER_GUARD_OUT ?= ops/reports/release-workflow-order-guard.json
RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT ?= tmp/release-workflow-order-guard.candidate.json
RELEASE_RISK_TAXONOMY_MATRIX_OUT ?= ops/reports/release-risk-taxonomy-matrix.json
RELEASE_RISK_TAXONOMY_MATRIX_CANDIDATE_OUT ?= tmp/release-risk-taxonomy-matrix.candidate.json
RELEASE_RISK_TAXONOMY_MATRIX_MD_OUT ?= ops/reports/release-risk-taxonomy-matrix.md

.PHONY: artifact-freshness artifact-freshness-check artifact-freshness-refresh-check artifact-freshness-stable-contract-debt-refresh artifact-relocation-audit tmp-json-clean tmp-clean sync-derived sync-derived-check refresh-generated-core refresh-generated-observability refresh-generated generated-artifact-converge generated-artifact-script-output generated-artifact-finality-suffix command-log-summary-backfill generated-artifact-retention-clean clean-fixture-regeneration-guard script-output-surfaces script-output-surfaces-check script-module-surfaces script-module-surfaces-check script-output-surfaces-clean-regenerate manual-mutate-defect-registry closure-registry-envelope make-target-inventory make-target-inventory-check workflow-dependency-planner workflow-dependency-planner-check changed-path-minimum-plan release-workflow-order-guard release-risk-taxonomy-matrix generated-artifact-index generated-artifact-index-check generated-artifact-index-body archive-execution-manifest archive-execution-manifest-report archive-execution-manifest-check archive-execution-manifest-apply archive-execution-manifest-defer archive-execution-manifest-rollback

artifact-freshness:
	$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" --progress "$(ARTIFACT_FRESHNESS_PROGRESS)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)" --out "$(ARTIFACT_FRESHNESS_OUT)" --schema ops/schemas/artifact-freshness-report.schema.json --expected-artifact-kind artifact_freshness_report --expected-producer ops.scripts.artifact_freshness_runtime

artifact-freshness-check:
	$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CHECK_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" --progress "$(ARTIFACT_FRESHNESS_PROGRESS)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",) --fail-on-fail

artifact-freshness-refresh-check:
	@status=0; $(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" --progress "$(ARTIFACT_FRESHNESS_PROGRESS)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",) --fail-on-fail || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(ARTIFACT_FRESHNESS_CANDIDATE_OUT)" --out "$(ARTIFACT_FRESHNESS_OUT)" --schema ops/schemas/artifact-freshness-report.schema.json --expected-artifact-kind artifact_freshness_report --expected-producer ops.scripts.artifact_freshness_runtime || status=$$?; exit $$status

artifact-freshness-stable-contract-debt-refresh:
	$(PYTHON) -m ops.scripts.backfill_archived_run_artifacts --vault "$(VAULT)"
	$(MAKE) artifact-freshness-refresh-check

artifact-relocation-audit:
	$(PYTHON) -m ops.scripts.artifact_relocation_audit --vault "$(VAULT)" --out "$(ARTIFACT_RELOCATION_AUDIT_CANDIDATE_OUT)" --fail-on-fail
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(ARTIFACT_RELOCATION_AUDIT_CANDIDATE_OUT)" --out "$(ARTIFACT_RELOCATION_AUDIT_OUT)" --schema ops/schemas/artifact-relocation-audit.schema.json --expected-artifact-kind artifact_relocation_audit --expected-producer ops.scripts.artifact_relocation_audit

tmp-json-clean:
	@if [ -d tmp ]; then find tmp -mindepth 1 -delete; fi

tmp-clean: tmp-json-clean

sync-derived:
	$(MAKE) pytest-markers-sync
	$(MAKE) test-selectors-sync
	$(MAKE) sync-public-policy
	$(MAKE) script-output-surfaces
	$(MAKE) script-module-surfaces
	$(MAKE) release-governance-sync
	$(MAKE) make-target-inventory
	$(MAKE) report-schema-samples-regenerate

sync-derived-check:
	$(MAKE) pytest-markers-sync-check
	$(MAKE) test-selectors-sync-check
	$(MAKE) sync-public-policy-check
	$(MAKE) script-output-surfaces-check
	$(MAKE) script-module-surfaces-check
	$(MAKE) release-governance-sync-check
	$(MAKE) make-target-inventory-check
	$(MAKE) report-schema-samples-check

# Keep the canonical freshness report current before queue/readiness consumers read it.
refresh-generated-core: registry-preflight raw-registry-export manifest script-output-surfaces routing-provenance-aggregate outcome-metrics promotion-decision-trends artifact-freshness mechanism-review mutation-proposal

refresh-generated-observability:
	$(MAKE) make-target-inventory
	$(MAKE) workflow-dependency-planner
	$(MAKE) release-workflow-order-guard
	$(MAKE) function-budget-refactor-proposals
	$(MAKE) outcome-provenance-gate-policy
	$(MAKE) generated-artifact-converge

refresh-generated: refresh-generated-core refresh-generated-observability
	@echo "refresh-generated is a compatibility aggregate; use refresh-generated-core for queue inputs and refresh-generated-observability for advisory reports."

generated-artifact-converge:
	$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase before --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)"
	$(MAKE) generated-artifact-finality-suffix
	$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase after --before "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)" --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT)"

generated-artifact-script-output:
	$(MAKE) script-output-surfaces

# These reports feed each other: freshness reads matrix/index, matrix reads freshness,
# and index reads matrix. Run one full index pass, then a body-only feedback pass.
generated-artifact-finality-suffix:
	$(MAKE) artifact-freshness
	$(MAKE) external-report-action-matrix
	$(MAKE) generated-artifact-index
	$(MAKE) artifact-freshness
	$(MAKE) external-report-action-matrix
	$(MAKE) generated-artifact-index-body
	$(MAKE) artifact-freshness

command-log-summary-backfill:
	$(PYTHON) -m ops.scripts.command_log_summary_backfill --vault "$(VAULT)" --out "$(COMMAND_LOG_SUMMARY_BACKFILL_OUT)" $(if $(COMMAND_LOG_SUMMARY_BACKFILL_APPLY),--apply,) $(if $(COMMAND_LOG_SUMMARY_BACKFILL_ALL),--all,) $(if $(COMMAND_LOG_SUMMARY_BACKFILL_INCLUDE_RUN_COMMANDS),--include-run-commands,) $(if $(COMMAND_LOG_SUMMARY_BACKFILL_CLOSE_PROMOTED_UNREFERENCED),--close-promoted-unreferenced,) $(if $(COMMAND_LOG_SUMMARY_BACKFILL_DELETE_RAW),--delete-raw,) $(if $(COMMAND_LOG_SUMMARY_BACKFILL_OPERATOR_CONFIRMATION),--operator-confirmation "$(COMMAND_LOG_SUMMARY_BACKFILL_OPERATOR_CONFIRMATION)",) $(if $(COMMAND_LOG_SUMMARY_BACKFILL_RUN_ID),--run-id "$(COMMAND_LOG_SUMMARY_BACKFILL_RUN_ID)",)

generated-artifact-retention-clean:
	$(PYTHON) -m ops.scripts.generated_artifact_retention_clean --vault "$(VAULT)" --out "$(GENERATED_ARTIFACT_RETENTION_CLEAN_OUT)" $(if $(GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY),--apply,) $(if $(GENERATED_ARTIFACT_RETENTION_COMPRESS_RUNS),--compress-runs,) $(if $(GENERATED_ARTIFACT_RETENTION_COMPRESS_TTL_DAYS),--compress-ttl-days $(GENERATED_ARTIFACT_RETENTION_COMPRESS_TTL_DAYS),)

generated-artifact-runs-compress:
	$(MAKE) generated-artifact-retention-clean GENERATED_ARTIFACT_RETENTION_COMPRESS_RUNS=1 GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY=$(GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY)

script-output-surfaces:
	$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" --out "$(SCRIPT_OUTPUT_SURFACES_OUT)"

script-output-surfaces-check:
	$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" --stored "$(SCRIPT_OUTPUT_SURFACES_OUT)" --check

script-module-surfaces:
	$(PYTHON) -m ops.scripts.script_module_surfaces --vault "$(VAULT)" --out "$(SCRIPT_MODULE_SURFACES_OUT)"

script-module-surfaces-check:
	$(PYTHON) -m ops.scripts.script_module_surfaces --vault "$(VAULT)" --stored "$(SCRIPT_MODULE_SURFACES_OUT)" --check

clean-fixture-regeneration-guard:
	$(PYTHON) -m ops.scripts.clean_fixture_regeneration_guard --vault "$(VAULT)" --out "$(CLEAN_FIXTURE_REGENERATION_GUARD_OUT)"

script-output-surfaces-clean-regenerate: clean-fixture-regeneration-guard script-output-surfaces

manual-mutate-defect-registry:
	$(PYTHON) -m ops.scripts.manual_mutate_defect_registry --vault "$(VAULT)" --out "$(MANUAL_MUTATE_DEFECT_REGISTRY_OUT)"

closure-registry-envelope:
	$(PYTHON) -m ops.scripts.closure_registry_envelope --vault "$(VAULT)" --registry "$(CLOSURE_REGISTRY_ENVELOPE_REGISTRY)"

make-target-inventory:
	$(PYTHON) -m ops.scripts.make_target_inventory --vault "$(VAULT)" --out "$(MAKE_TARGET_INVENTORY_OUT)"

make-target-inventory-check:
	$(PYTHON) -m ops.scripts.make_target_inventory --vault "$(VAULT)" --check

workflow-dependency-planner:
	$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT)" $(if $(WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST),--changed-files-manifest "$(WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_OUT)" --schema ops/schemas/workflow-dependency-planner.schema.json --expected-artifact-kind workflow_dependency_planner --expected-producer ops.scripts.workflow_dependency_planner

workflow-dependency-planner-check:
	$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT)" $(if $(WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST),--changed-files-manifest "$(WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST)",)

changed-path-minimum-plan:
	$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(CHANGED_PATH_MINIMUM_PLAN_OUT)" $(if $(WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST),--changed-files-manifest "$(WORKFLOW_DEPENDENCY_PLANNER_CHANGED_FILES_MANIFEST)",)

release-workflow-order-guard:
	$(PYTHON) -m ops.scripts.release_workflow_order_guard --vault "$(VAULT)" --out "$(RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT)" --out "$(RELEASE_WORKFLOW_ORDER_GUARD_OUT)" --schema ops/schemas/release-workflow-order-guard.schema.json --expected-artifact-kind release_workflow_order_guard --expected-producer ops.scripts.release_workflow_order_guard

release-risk-taxonomy-matrix:
	$(PYTHON) -m ops.scripts.release_risk_taxonomy_matrix --vault "$(VAULT)" --out "$(RELEASE_RISK_TAXONOMY_MATRIX_CANDIDATE_OUT)" --markdown-out "$(RELEASE_RISK_TAXONOMY_MATRIX_MD_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RELEASE_RISK_TAXONOMY_MATRIX_CANDIDATE_OUT)" --out "$(RELEASE_RISK_TAXONOMY_MATRIX_OUT)" --schema ops/schemas/release-risk-taxonomy-matrix.schema.json --expected-artifact-kind release_risk_taxonomy_matrix --expected-producer ops.scripts.release_risk_taxonomy_matrix

generated-artifact-index: artifact-relocation-audit closure-registry-envelope manual-mutate-defect-registry release-risk-taxonomy-matrix generated-artifact-index-body

generated-artifact-index-check:
	$(PYTHON) -m ops.scripts.generated_artifact_index --vault "$(VAULT)" --out "$(GENERATED_ARTIFACT_INDEX_CHECK_OUT)"

generated-artifact-index-body:
	$(PYTHON) -m ops.scripts.generated_artifact_index --vault "$(VAULT)" --out "$(GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GENERATED_ARTIFACT_INDEX_CANDIDATE_OUT)" --out "$(GENERATED_ARTIFACT_INDEX_OUT)" --schema ops/schemas/generated-artifact-index.schema.json --expected-artifact-kind generated_artifact_index_report --expected-producer ops.scripts.generated_artifact_index

archive-execution-manifest: generated-artifact-index archive-execution-manifest-report

archive-execution-manifest-report:
	$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode dry_run

archive-execution-manifest-check:
	$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode dry_run --fail-on-attention

archive-execution-manifest-apply:
	$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode applied --operator-confirmation "$(ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION)"

archive-execution-manifest-defer:
	$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --index-path "$(GENERATED_ARTIFACT_INDEX_OUT)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode deferred

archive-execution-manifest-rollback:
	$(PYTHON) -m ops.scripts.archive_execution_manifest --vault "$(VAULT)" --manifest-path "$(ARCHIVE_EXECUTION_MANIFEST_SOURCE)" --out "$(ARCHIVE_EXECUTION_MANIFEST_OUT)" --mode rollback --operator-confirmation "$(ARCHIVE_EXECUTION_OPERATOR_CONFIRMATION)"
