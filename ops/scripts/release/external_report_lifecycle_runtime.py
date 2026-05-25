from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.workflow_dependency_planner import (
    build_report as build_workflow_dependency_report,
)

from .release_closeout_finality_attestation import verify_attestation
from .release_status_v2 import release_status_v2_view_with_readiness_fallback
from .release_workflow_order_guard import (
    build_report as build_release_workflow_order_guard_report,
)

REFERENCE_MANIFEST = "external-reports/report-reference-manifest.json"
REFERENCE_MANIFEST_EXTENSIONS = {".md", ".pdf", ".docx"}
REPORT_EXTENSIONS = REFERENCE_MANIFEST_EXTENSIONS
NARRATIVE_REPORT_EXTENSIONS = {".md"}
RELEASE_VERIFIED_ACTION_IDS = {
    "source_package_distribution_binding",
    "release_evidence_bundle_and_attestation",
    "full_suite_evidence_currentness",
    "promotion_truth_ladder",
}
ROADMAP_SOURCE_ONLY_ACTION_IDS = {
    "public_mirror_boundary_helper",
    "lint_uplift_plan_full_scope",
    "type_uplift_plan_full_scope",
    "mechanism_navigation_index",
    "cli_surface_inventory",
    "tools_migration_plan",
    "release_authority_inventory",
    "observation_closeout_lint",
    "subagent_profile_schema",
    "ci_tier_lane_bridge",
    "compatibility_alias_deprecation",
    "public_surface_snapshot",
    "doc_graph_integrity_lint",
}
SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS = {
    "ops/reports/learning-readiness-signoff.json",
    "ops/reports/release-closeout-batch-manifest.json",
    "ops/reports/release-closeout-finality-attestation.json",
    "ops/reports/release-closeout-fixed-point.json",
    "ops/reports/release-closeout-sealed-rehearsal-check.json",
    "ops/reports/release-evidence-closeout-self-check.json",
    "ops/reports/review-archive-report.json",
    "ops/reports/source-package-clean-extract.json",
    "ops/reports/test-execution-summary-full.json",
}

ACTION_CATALOG: list[dict[str, Any]] = [
    {
        "action_id": "script_output_surfaces_currentness",
        "priority": "P0",
        "theme": "writer output surface currentness",
        "patterns": [r"script-output-surfaces", r"writer/output surface", r"writer output"],
        "evidence_paths": ["ops/script-output-surfaces.json"],
        "recommended_target": "script-output-surfaces",
    },
    {
        "action_id": "release_writer_dependency_single_source",
        "priority": "P0",
        "theme": "release writer ordering single source",
        "patterns": [r"workflow_dependency_planner", r"fixed-point", r"writer dependency", r"single source"],
        "evidence_paths": [
            "ops/reports/workflow-dependency-planner.json",
            "ops/reports/release-workflow-order-guard.json",
        ],
        "recommended_target": "release-workflow-order-guard",
    },
    {
        "action_id": "function_budget_proposal_adapter",
        "priority": "P1",
        "theme": "wiki_lint function-budget triage",
        "patterns": [r"function-budget", r"wiki_lint review", r"review candidate"],
        "evidence_paths": ["ops/reports/function-budget-refactor-proposals.json"],
        "recommended_target": "function-budget-refactor-proposals",
    },
    {
        "action_id": "windows_path_and_archive_alias_parity",
        "priority": "P1",
        "theme": "path portability and archive alias normalization",
        "patterns": [r"Windows", r"path alias", r"path portability", r"Info-ZIP", r"C locale", r"escaped path"],
        "evidence_paths": [
            "tests/test_writer_output_paths.py",
            "tests/test_planning_gate_validate_runtime.py",
            "tests/test_release_smoke.py",
        ],
        "recommended_target": "test-public",
    },
    {
        "action_id": "outcome_provenance_gate_policy",
        "priority": "P2",
        "theme": "outcome/provenance policy escalation",
        "patterns": [r"outcome", r"provenance", r"same-eval", r"rollback rehearsal", r"promotion gate"],
        "evidence_paths": ["ops/reports/outcome-provenance-gate-policy.json"],
        "recommended_target": "outcome-provenance-gate-policy",
    },
    {
        "action_id": "external_report_lifecycle",
        "priority": "P1",
        "theme": "active external report lifecycle",
        "patterns": [r"external report lifecycle", r"active external", r"report-reference-manifest", r"active report set"],
        "evidence_paths": [
            "external-reports/report-reference-manifest.json",
            "ops/reports/external-report-action-matrix.json",
        ],
        "recommended_target": "external-report-action-matrix",
    },
    {
        "action_id": "active_report_manifest_freshness",
        "priority": "P0",
        "theme": "active external report manifest freshness",
        "patterns": [
            r"active reference set",
            r"missing active report",
            r"report-reference-manifest",
            r"active report set",
            r"active external report",
        ],
        "evidence_paths": [
            "external-reports/report-reference-manifest.json",
            "ops/reports/external-report-action-matrix.json",
        ],
        "recommended_target": "external-report-reference-manifest-settle",
    },
    {
        "action_id": "source_revision_unknown_canonical_reports",
        "priority": "P0",
        "theme": "canonical report source revision provenance",
        "patterns": [
            r"source_revision\s*[:=]\s*unknown",
            r"source_revision",
            r"source revision",
            r"Git revision",
            r"source_package_without_git",
            r"canonical report.*unknown",
        ],
        "evidence_paths": [
            "ops/scripts/core/source_revision_runtime.py",
            "ops/scripts/core/artifact_freshness_runtime.py",
            "ops/scripts/core/bootstrap_preflight.py",
            "tests/test_source_revision_runtime.py",
            "ops/reports/artifact-freshness-report.json",
        ],
        "recommended_target": "artifact-freshness-refresh-check",
    },
    {
        "action_id": "ruff_strict_preview_import_order",
        "priority": "P0",
        "theme": "Ruff strict preview import-order currentness",
        "patterns": [
            r"Ruff strict",
            r"\bI001\b",
            r"import order",
            r"ruff-strict-preview",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py",
            "tools/ruff_strict_preview.py",
            "mk/static.mk",
        ],
        "recommended_target": "ruff-strict-preview",
    },
    {
        "action_id": "release_source_ready_deindex_hardening",
        "priority": "P0",
        "theme": "release source-ready local-only deindex hardening",
        "patterns": [
            r"release_source_ready_commit",
            r"release-source-ready",
            r"deindex",
            r"local-only private",
            r"git add -u",
        ],
        "evidence_paths": [
            "ops/scripts/release/release_source_ready_commit.py",
            "tests/test_release_source_ready_commit.py",
        ],
        "recommended_target": "release-source-ready-commit",
    },
    {
        "action_id": "uv_lock_canonical_policy",
        "priority": "P1",
        "theme": "uv lock canonical dependency policy",
        "patterns": [
            r"uv lock --check",
            r"uv\.lock",
            r"lockfile",
            r"canonical dependency",
        ],
        "evidence_paths": [
            "pyproject.toml",
            "uv.lock",
            "docs/development.md",
        ],
        "recommended_target": "uv-lock-check",
    },
    {
        "action_id": "operator_entrypoint_index",
        "priority": "P1",
        "theme": "operator Make entrypoint index",
        "patterns": [
            r"operator entrypoint",
            r"operator index",
            r"make help",
            r"release/public/mechanism/report-contract",
        ],
        "evidence_paths": [
            "Makefile",
            "mk/core.mk",
            "docs/development.md",
        ],
        "recommended_target": "help",
    },
    {
        "action_id": "strict_preview_all_target_audit",
        "priority": "P1",
        "theme": "strict-preview all-target audit after legacy allowlist removal",
        "patterns": [
            r"strict-preview",
            r"allowlist",
            r"all-target",
            r"all target",
            r"ops/scripts tests tools",
        ],
        "evidence_paths": [
            "tools/strict_preview_audit.py",
            "mk/static.mk",
            "tests/test_strict_preview_audit.py",
        ],
        "recommended_target": "strict-preview-audit",
    },
    {
        "action_id": "public_mirror_boundary_helper",
        "priority": "P1",
        "theme": "public mirror boundary helper",
        "patterns": [
            r"public_mirror_boundary_runtime",
            r"boundary helper",
            r"assert_within_public_mirror",
            r"경계",
        ],
        "evidence_paths": [
            "ops/scripts/core/public_mirror_boundary_runtime.py",
            "tests/test_public_mirror_boundary_runtime.py",
        ],
        "recommended_target": "test-public",
    },
    {
        "action_id": "lint_uplift_plan_full_scope",
        "priority": "P1",
        "theme": "full-scope lint uplift plan",
        "patterns": [
            r"Lint uplift plan",
            r"strict-lint-inventory",
            r"lint_uplift_plan",
            r"strict-preview family",
        ],
        "evidence_paths": [
            "ops/schemas/strict-lint-inventory.schema.json",
            "ops/scripts/eval/lint_uplift_plan.py",
            "tests/test_lint_uplift_plan.py",
            "mk/eval.mk",
        ],
        "recommended_target": "lint-uplift-plan",
    },
    {
        "action_id": "type_uplift_plan_full_scope",
        "priority": "P1",
        "theme": "full-scope type uplift plan",
        "patterns": [
            r"Type uplift plan",
            r"strict-type-inventory",
            r"type_uplift_plan",
            r"allowlist.*meaning",
            r"mypy target",
        ],
        "evidence_paths": [
            "ops/schemas/strict-type-inventory.schema.json",
            "ops/scripts/eval/type_uplift_plan.py",
            "tests/test_type_uplift_plan.py",
            "mk/eval.mk",
        ],
        "recommended_target": "type-uplift-plan",
    },
    {
        "action_id": "mechanism_navigation_index",
        "priority": "P1",
        "theme": "mechanism navigation index",
        "patterns": [r"Mechanism navigation index", r"mechanism_navigation_index"],
        "evidence_paths": [
            "ops/schemas/mechanism-navigation-index.schema.json",
            "ops/scripts/mechanism/mechanism_navigation_index.py",
            "tests/test_mechanism_navigation_index.py",
        ],
        "recommended_target": "mechanism-navigation-index",
    },
    {
        "action_id": "cli_surface_inventory",
        "priority": "P1",
        "theme": "CLI surface inventory",
        "patterns": [r"CLI surface inventory", r"cli_surface_inventory", r"alias debt"],
        "evidence_paths": [
            "ops/schemas/cli-surface-inventory.schema.json",
            "ops/scripts/core/cli_surface_inventory.py",
            "tests/test_cli_surface_inventory.py",
        ],
        "recommended_target": "cli-surface-inventory",
    },
    {
        "action_id": "tools_migration_plan",
        "priority": "P1",
        "theme": "tools migration plan",
        "patterns": [r"Tools migration plan", r"tools_migration_plan", r"migration debt"],
        "evidence_paths": [
            "ops/schemas/tools-migration-plan.schema.json",
            "ops/scripts/core/tools_migration_plan.py",
            "tests/test_tools_migration_plan.py",
        ],
        "recommended_target": "tools-migration-plan",
    },
    {
        "action_id": "release_authority_inventory",
        "priority": "P1",
        "theme": "release authority inventory",
        "patterns": [r"Release authority inventory", r"release_authority_inventory"],
        "evidence_paths": [
            "ops/schemas/release-authority-inventory.schema.json",
            "ops/scripts/release/release_authority_inventory.py",
            "tests/test_release_authority_inventory.py",
        ],
        "recommended_target": "release-authority-inventory",
    },
    {
        "action_id": "observation_closeout_lint",
        "priority": "P1",
        "theme": "observation closeout lint",
        "patterns": [r"Observation closeout lint", r"observation_closeout_lint"],
        "evidence_paths": [
            "ops/schemas/observation-closeout-registry.schema.json",
            "ops/observation-closeout-registry.json",
            "ops/scripts/mechanism/observation_closeout_lint.py",
            "tests/test_observation_closeout_lint.py",
        ],
        "recommended_target": "observation-closeout-lint",
    },
    {
        "action_id": "subagent_profile_schema",
        "priority": "P1",
        "theme": "subagent profile schema and rung ladder",
        "patterns": [r"Subagent profile schema", r"subagent_profile_schema", r"rung ladder"],
        "evidence_paths": [
            "ops/schemas/subagent-profile.schema.json",
            "ops/scripts/core/subagent_profile_schema.py",
            "tests/test_subagent_profile_schema.py",
            "tests/test_select_subagent_rung_ladder.py",
        ],
        "recommended_target": "subagent-profile-schema",
    },
    {
        "action_id": "ci_tier_lane_bridge",
        "priority": "P1",
        "theme": "CI tier lane bridge",
        "patterns": [r"CI tier lane bridge", r"ci_tier_lane_bridge", r"lane_ci_steps", r"pack_ci_steps"],
        "evidence_paths": [
            "ops/schemas/ci-tier-lane-bridge.schema.json",
            "ops/scripts/test/ci_tier_lane_bridge.py",
            "tests/test_ci_tier_lane_bridge.py",
        ],
        "recommended_target": "ci-tier-lane-bridge",
    },
    {
        "action_id": "compatibility_alias_deprecation",
        "priority": "P1",
        "theme": "compatibility alias deprecation inventory",
        "patterns": [r"Compatibility alias deprecation", r"compatibility_alias_deprecation", r"flat alias"],
        "evidence_paths": [
            "ops/schemas/compatibility-alias-deprecation.schema.json",
            "ops/scripts/core/compatibility_alias_deprecation.py",
            "tests/test_compatibility_alias_deprecation.py",
        ],
        "recommended_target": "compatibility-alias-deprecation",
    },
    {
        "action_id": "public_surface_snapshot",
        "priority": "P1",
        "theme": "public surface snapshot",
        "patterns": [r"Public surface snapshot", r"public_surface_snapshot", r"iter_public_files"],
        "evidence_paths": [
            "ops/schemas/public-surface-snapshot.schema.json",
            "ops/scripts/public/public_surface_snapshot.py",
            "tests/test_public_surface_snapshot.py",
        ],
        "recommended_target": "public-surface-snapshot",
    },
    {
        "action_id": "doc_graph_integrity_lint",
        "priority": "P1",
        "theme": "doc graph integrity lint",
        "patterns": [r"Doc graph integrity", r"doc_graph_integrity", r"doc-graph-orphan"],
        "evidence_paths": [
            "ops/schemas/doc-graph-integrity.schema.json",
            "ops/doc-graph-orphan-allowlist.json",
            "ops/scripts/eval/doc_graph_integrity.py",
            "tests/test_doc_graph_integrity.py",
        ],
        "recommended_target": "doc-graph-integrity",
    },
    {
        "action_id": "release_lane_mutability_split",
        "priority": "P0",
        "theme": "release lane mutability split",
        "patterns": [
            r"lane mutability",
            r"release-evidence-converge",
            r"release-verify-current",
            r"release-sealed-verify",
            r"Generate once in converge lane",
            r"Verify without writing in current lane",
        ],
        "evidence_paths": [
            "mk/release.mk",
            "ops/scripts/release/release_workflow_order_guard.py",
            "tests/test_makefile_static_gates.py",
        ],
        "recommended_target": "release-evidence-converge",
    },
    {
        "action_id": "sealed_summary_vocabulary_demotion",
        "priority": "P0",
        "theme": "sealed summary vocabulary demotion",
        "patterns": [
            r"pre_distribution_package_binding_status",
            r"source_closeout_distribution_binding_status",
            r"sealed_release_status.*pre[- ]distribution",
            r"source closeout.*sealed",
            r"field rename/demotion",
        ],
        "evidence_paths": [
            "ops/scripts/release/release_closeout_summary.py",
            "ops/schemas/release-closeout-summary.schema.json",
            "tests/test_release_closeout_summary.py",
            "tests/test_release_status_v2.py",
        ],
        "recommended_target": "release-closeout-summary-report",
    },
    {
        "action_id": "selector_marker_scope_parity",
        "priority": "P1",
        "theme": "explicit selector and marker-wide lane parity",
        "patterns": [
            r"marker-wide",
            r"marker expression",
            r"explicit selector",
            r"test-release-sealing-core",
            r"test-report-contract-core",
            r"RELEASE_SEALING_TESTS",
            r"REPORT_CONTRACT_CORE_TESTS",
        ],
        "evidence_paths": [
            "mk/test.mk",
            "ops/test-lane-registry.json",
            "tests/test_makefile_static_gates.py",
        ],
        "recommended_target": "test-release-sealing",
    },
    {
        "action_id": "source_package_distribution_binding",
        "priority": "P0",
        "theme": "source package and distribution ZIP binding",
        "patterns": [r"source package", r"source ZIP", r"distribution ZIP", r"archive profile", r"package mode"],
        "evidence_paths": [
            "ops/reports/source-package-clean-extract.json",
            "ops/reports/release-smoke-report.json",
            "external-reports/report-reference-manifest.json",
        ],
        "recommended_target": "release-source-package-check",
    },
    {
        "action_id": "release_evidence_bundle_and_attestation",
        "priority": "P1",
        "theme": "release evidence bundle and attestation",
        "patterns": [
            r"evidence bundle",
            r"attestation",
            r"post-seal",
            r"audit pack",
            r"release[- ]evidence",
            r"release-closeout-batch-manifest",
            r"batch-manifest",
            r"finality",
            r"closeout self-check",
        ],
        "evidence_paths": [
            "ops/reports/release-closeout-finality-attestation.json",
            "ops/reports/release-closeout-batch-manifest.json",
        ],
        "recommended_target": "release-evidence-closeout-sealed-dry-run",
    },
    {
        "action_id": "full_suite_evidence_currentness",
        "priority": "P1",
        "theme": "full-suite evidence currentness",
        "patterns": [r"full-suite", r"full suite", r"test-execution-summary-full", r"collect-only", r"nodeid"],
        "evidence_paths": ["ops/reports/test-execution-summary-full.json"],
        "recommended_target": "test-execution-summary-full-refresh",
    },
    {
        "action_id": "promotion_truth_ladder",
        "priority": "P0",
        "theme": "live gate and promotion truth ladder",
        "patterns": [r"truth ladder", r"live gate", r"promotion_blockers", r"can_promote_result", r"machine_release"],
        "evidence_paths": [
            "ops/reports/auto-improve-readiness.json",
            "ops/reports/release-closeout-summary.json",
            "ops/reports/release-evidence-dashboard.json",
        ],
        "recommended_target": "auto-improve-readiness-report",
    },
    {
        "action_id": "goal_contract_schema",
        "priority": "P0",
        "theme": "goal contract schema for long-running auto-improve",
        "patterns": [
            r"goal contract",
            r"codex-goal-contract",
            r"GoalSpec",
            r"required_evidence",
            r"stop_conditions",
        ],
        "evidence_paths": [
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/reports/codex-goal-contract.json",
            "tests/test_codex_goal_contract.py",
        ],
        "recommended_target": "codex-goal-contract",
    },
    {
        "action_id": "codex_goal_adapter",
        "priority": "P0",
        "theme": "local set_goal adapter and backend detection",
        "patterns": [
            r"set_goal",
            r"get_goal",
            r"update_goal",
            r"GoalBackend",
            r"feature detection",
            r"thread/goal",
            r"app-server",
        ],
        "evidence_paths": [
            "ops/scripts/core/codex_goal_client.py",
            "ops/reports/codex-goal-contract.json",
            "tests/test_codex_goal_client.py",
        ],
        "recommended_target": "codex-goal-client",
    },
    {
        "action_id": "codex_goal_prompt_generator",
        "priority": "P0",
        "theme": "goal prompt generator with promotion ban wording",
        "patterns": [
            r"goal prompt",
            r"codex_goal_prompt",
            r"can_promote_result=false",
            r"promotion forbidden",
            r"promotion ban",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/codex_goal_prompt.py",
            "ops/schemas/codex-goal-prompt.schema.json",
            "ops/reports/codex-goal-prompt.json",
            "tests/test_codex_goal_prompt.py",
        ],
        "recommended_target": "codex-goal-prompt",
    },
    {
        "action_id": "auto_improve_goal_contract_input",
        "priority": "P0",
        "theme": "auto-improve loop goal contract input and budget ceiling",
        "patterns": [
            r"--goal-contract",
            r"auto_improve_loop",
            r"policy/CLI.*larger budget",
            r"larger budget",
            r"contract digest",
            r"time_budget_exhausted",
            r"proposal_budget_exhausted",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/auto_improve_runtime.py",
            "ops/reports/codex-goal-contract.json",
            "tests/test_auto_improve_runtime.py",
        ],
        "recommended_target": "codex-goal-client",
    },
    {
        "action_id": "goal_run_status_audit_resume",
        "priority": "P0",
        "theme": "goal run status, audit log, checkpoint, and resume contract",
        "patterns": [
            r"goal-run-status",
            r"audit-log",
            r"checkpoint",
            r"resume",
            r"run id",
            r"run_ids",
            r"session_id",
            r"session identity",
            r"status\.md",
            r"resume_from_checkpoint",
            r"--goal-contract",
            r"--resume-from-checkpoint",
        ],
        "evidence_paths": [
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "ops/reports/goal-run-status.json",
            "tests/test_goal_auto_improve_runtime.py",
            "tests/test_goal_run_status.py",
            "tests/test_goal_runtime_runner.py",
        ],
        "recommended_target": "auto-improve-goal-run",
    },
    {
        "action_id": "goal_execution_runtime_certificate",
        "priority": "P0",
        "theme": "bounded goal execution runtime certificate",
        "patterns": [
            r"runtime certificate",
            r"self-improvement loop",
            r"자가개선 루프",
            r"full gate",
            r"source-package",
            r"public-check",
            r"bounded trial",
        ],
        "evidence_paths": [
            "mk/mechanism.mk",
            "ops/reports/goal-runtime-certificate.json",
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_certificate_report.py",
            "ops/scripts/mechanism/goal_runtime_certificate.py",
            "tests/test_goal_runtime_certificate.py",
            "tests/test_goal_run_status.py",
        ],
        "recommended_target": "goal-runtime-certificate",
    },
    {
        "action_id": "command_heartbeat_observability",
        "priority": "P1",
        "theme": "long command heartbeat and quiet-run observability",
        "patterns": [
            r"heartbeat",
            r"last_stdout_at",
            r"last_stderr_at",
            r"last_artifact_touch_at",
            r"quiet_seconds",
            r"time_budget_exhausted",
        ],
        "evidence_paths": [
            "ops/scripts/core/command_runtime.py",
            "ops/schemas/executor-report.schema.json",
            "ops/scripts/core/source_package_clean_extract.py",
            "ops/schemas/source-package-clean-extract.schema.json",
            "ops/reports/source-package-clean-extract.json",
            "tests/test_command_runtime_heartbeat.py",
            "tests/test_source_package_clean_extract.py",
        ],
        "recommended_target": "test-subprocess",
    },
    {
        "action_id": "goal_executor_backoff_observability",
        "priority": "P1",
        "theme": "goal executor retry-after backoff and status observability",
        "patterns": [
            r"executor backoff",
            r"retry-after",
            r"retry_after",
            r"usage limit",
            r"executor_usage_limited",
            r"backoff.*heartbeat",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/goal_runtime_backoff.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "ops/reports/goal-run-status.json",
            "ops/schemas/goal-run-status.schema.json",
            "tests/test_goal_runtime_runner.py",
            "tests/test_goal_run_status.py",
        ],
        "recommended_target": "auto-improve-goal-run",
    },
    {
        "action_id": "selected_contract_currentness_gate",
        "priority": "P0",
        "theme": "selected contract currentness gate distinct from artifact freshness",
        "patterns": [
            r"selected contract",
            r"selected_contract_currentness",
            r"test_execution_summary_contract_drift",
            r"artifact freshness pass",
            r"operational currentness drift",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
            "ops/reports/auto-improve-readiness.json",
            "ops/reports/test-execution-summary.json",
            "tests/test_auto_improve_readiness_release_authority_runtime.py",
        ],
        "recommended_target": "auto-improve-readiness-report",
    },
    {
        "action_id": "sealed_preflight_canonicalization",
        "priority": "P0",
        "theme": "sealed authority preflight clean-required canonical evidence",
        "patterns": [
            r"sealed preflight",
            r"release authority",
            r"expected blocked",
            r"clean-required",
            r"sealed authority clean",
            r"binding_pass_authority_blocked",
        ],
        "evidence_paths": [
            "mk/release.mk",
            "ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py",
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
            "ops/scripts/release/release_closeout_sealed_rehearsal_check.py",
            "ops/schemas/release-closeout-sealed-rehearsal-check.schema.json",
            "tests/test_release_closeout_sealed_rehearsal_check.py",
            "tests/test_auto_improve_readiness_runtime.py",
            "tests/test_makefile_static_gates.py",
        ],
        "recommended_target": "release-authority-sealed-preflight",
    },
    {
        "action_id": "negative_learning_ledger",
        "priority": "P2",
        "theme": "standalone negative learning ledger",
        "patterns": [
            r"negative learning",
            r"negative lessons",
            r"self-improvement-negative-lessons",
            r"same failure",
        ],
        "evidence_paths": [
            "ops/schemas/self-improvement-negative-lessons.schema.json",
            "ops/reports/self-improvement-negative-lessons.json",
            "tests/test_self_improvement_negative_lessons.py",
        ],
        "recommended_target": "self-improvement-negative-lessons",
    },
    {
        "action_id": "remediation_backlog",
        "priority": "P1",
        "theme": "remediation backlog for repeated blockers",
        "patterns": [
            r"remediation backlog",
            r"remediation-backlog",
            r"repeated blocker",
            r"blocked.*backlog",
        ],
        "evidence_paths": [
            "ops/schemas/remediation-backlog.schema.json",
            "ops/reports/remediation-backlog.json",
            "tests/test_remediation_backlog.py",
        ],
        "recommended_target": "remediation-backlog",
    },
    {
        "action_id": "git_worktree_goal_guard",
        "priority": "P1",
        "theme": "Git worktree and ZIP mode guard for long goal runs",
        "patterns": [
            r"Git worktree",
            r"ZIP extraction mode",
            r"trial only",
            r"report-only",
            r"long_run_allowed",
            r"git rev-parse",
            r"worktree path",
            r"private repo",
        ],
        "evidence_paths": [
            "mk/mechanism.mk",
            "ops/scripts/mechanism/goal_worktree_guard.py",
            "ops/schemas/goal-worktree-guard.schema.json",
            "tests/test_goal_worktree_guard.py",
        ],
        "recommended_target": "auto-improve-goal-preflight",
    },
    {
        "action_id": "goal_runtime_transient_cleanup_gate",
        "priority": "P1",
        "theme": "pre-run cleanup and admission gate for long goal runs",
        "patterns": [
            r"transient artifact cleanup",
            r"transient cleanup gate",
            r"goal-runtime-clean-transient",
            r"goal-runtime-run-admission",
            r"goal-runtime-run-admission-local-refresh",
            r"long-run-preflight-clean",
            r"runnable proposal",
            r"fixed-point",
            r"run-local evidence",
            r"obsolete tracked goal",
            r"stale legacy runtime",
        ],
        "evidence_paths": [
            "mk/mechanism.mk",
            "ops/scripts/mechanism/goal_runtime_clean_transient.py",
            "ops/schemas/goal-runtime-clean-transient.schema.json",
            "tests/test_goal_runtime_clean_transient.py",
            "ops/scripts/mechanism/goal_runtime_quarantine_preflight.py",
            "ops/schemas/goal-runtime-quarantine-preflight.schema.json",
            "tests/test_goal_runtime_quarantine_preflight.py",
            "ops/scripts/mechanism/goal_runtime_run_admission.py",
            "ops/schemas/goal-runtime-run-admission.schema.json",
            "tests/test_goal_runtime_run_admission.py",
        ],
        "recommended_target": "goal-runtime-run-admission",
    },
    {
        "action_id": "artifact_freshness_performance_observability",
        "priority": "P0",
        "theme": "artifact freshness performance and long-gate observability",
        "patterns": [
            r"artifact freshness",
            r"schema validator cache",
            r"validator cache",
            r"progress jsonl",
            r"per-phase timing",
            r"check-observed",
            r"incremental --changed-only",
            r"long-running gate",
        ],
        "evidence_paths": [
            "ops/scripts/core/artifact_freshness_runtime.py",
            "ops/reports/artifact-freshness-report.json",
            "tests/test_artifact_freshness_runtime.py",
            "mk/artifact.mk",
        ],
        "recommended_target": "artifact-freshness-check",
    },
    {
        "action_id": "repo_boundary_history_hygiene",
        "priority": "P0",
        "theme": "private vault and public/dev repo boundary hygiene",
        "patterns": [
            r"repo boundary",
            r"vault/code",
            r"public/dev repo",
            r"private vault",
            r"public mirror",
            r"raw/runs/archive",
            r"generated bulk",
        ],
        "evidence_paths": [
            ".gitignore",
            "ARCHITECTURE.md",
            "docs/public-mirror.md",
            "ops/scripts/public/public_surface_policy.py",
            "tests/test_public_surface_policy.py",
            "tests/test_export_public_repo.py",
            "ops/reports/public-check-summary.json",
        ],
        "recommended_target": "public-check",
    },
    {
        "action_id": "github_native_security_automation",
        "priority": "P0",
        "theme": "GitHub-native security and workflow governance",
        "patterns": [
            r"Dependabot",
            r"CodeQL",
            r"dependency review",
            r"required status",
            r"action pinning",
            r"concurrency",
            r"GitHub-native",
        ],
        "evidence_paths": [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            ".github/dependabot.yml",
            ".github/workflows/codeql.yml",
            ".github/workflows/dependency-review.yml",
        ],
        "recommended_target": "github-security-automation",
    },
    {
        "action_id": "maintainability_hotspot_refactor_backlog",
        "priority": "P1",
        "theme": "complexity hotspot and giant test decomposition",
        "patterns": [
            r"complexity hotspot",
            r"giant test",
            r"fixture cache",
            r"function budget",
            r"orchestrator",
            r"hotspot refactor",
        ],
        "evidence_paths": [
            "ops/reports/function-budget-refactor-proposals.json",
            "tests/test_function_budget_refactor_proposals.py",
            "ops/scripts/eval/function_budget_refactor_proposals.py",
        ],
        "recommended_target": "function-budget-refactor-proposals",
    },
    {
        "action_id": "generated_artifact_tracking_policy",
        "priority": "P1",
        "theme": "generated artifact tracking and churn policy",
        "patterns": [
            r"generated artifact",
            r"commit churn",
            r"decision-grade",
            r"ephemeral",
            r"tracked set",
            r"canonical refresh",
        ],
        "evidence_paths": [
            "ops/reports/generated-artifact-index.json",
            "ops/scripts/core/generated_artifact_index.py",
            "ops/schemas/generated-artifact-index.schema.json",
            "tests/test_generated_artifact_index.py",
        ],
        "recommended_target": "generated-artifact-index",
    },
    {
        "action_id": "public_export_negative_assertions",
        "priority": "P2",
        "theme": "public/private export negative assertions",
        "patterns": [
            r"negative assertion",
            r"excluded_prefix_absence",
            r"private_pattern_absence",
            r"local_path_absence",
            r"public export",
            r"public/private boundary",
        ],
        "evidence_paths": [
            "ops/scripts/public/export_public_repo.py",
            "ops/scripts/public/public_check_summary.py",
            "tests/test_export_public_repo.py",
            "tests/test_public_check_summary.py",
            "ops/reports/public-check-summary.json",
        ],
        "recommended_target": "public-check",
    },
    {
        "action_id": "supply_chain_external_verification",
        "priority": "P2",
        "theme": "external supply-chain verification",
        "patterns": [
            r"Scorecard",
            r"SBOM schema validation",
            r"SLSA",
            r"in-toto verification",
            r"supply-chain external verification",
            r"provenance verification",
        ],
        "evidence_paths": [
            "ops/reports/supply-chain-gate-report.json",
            "ops/reports/sbom-readiness-gate-report.json",
            "ops/reports/in-toto-statement.json",
            "ops/reports/sigstore-bundle-verification.json",
            "mk/supply_chain.mk",
        ],
        "recommended_target": "supply-chain-check",
    },
    {
        "action_id": "collaboration_governance_surface",
        "priority": "P2",
        "theme": "collaboration governance surface",
        "patterns": [
            r"CODEOWNERS",
            r"PR template",
            r"commit taxonomy",
            r"collaboration governance",
        ],
        "evidence_paths": [
            ".github/CODEOWNERS",
            ".github/pull_request_template.md",
            "CONTRIBUTING.md",
        ],
        "recommended_target": "collaboration-governance",
    },
]

ARCHIVE_STATUS_RE = re.compile(
    r"(?im)^\s*(?:archive_status|lifecycle_status|report_status)\s*[:=]\s*"
    r"`?(closed|superseded|archived)`?\s*$"
)
SUPERSEDED_BY_RE = re.compile(r"(?im)^\s*(?:superseded_by|replaced_by)\s*[:=]\s*`?([^`\n]+)`?")
COVERAGE_MARKER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("actual_file_crosscheck", r"actual[-_ ]file|실제\s*파일|파일\s*대조"),
    ("integrated_review", r"integrated|consolidated|통합\s*리뷰|통합\s*검토|종합\s*검토"),
    ("final_conclusion", r"final\s+conclusion|최종\s*결론|최종\s*권고|최종\s*판정"),
    ("live_reverification", r"live\s+truth|재검증|직접\s*재실행|실제\s*재검증"),
)


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def active_report_paths(vault: Path) -> list[Path]:
    root = vault / "external-reports"
    if not root.is_dir():
        return []
    manifest_path = (vault / REFERENCE_MANIFEST).resolve()
    paths: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in REPORT_EXTENSIONS:
            continue
        if path.resolve() == manifest_path:
            continue
        if path.parent.name in {"archive", "archived"}:
            continue
        paths.append(path)
    return paths


def active_reference_report_paths(vault: Path) -> list[Path]:
    root = vault / "external-reports"
    if not root.is_dir():
        return []
    manifest_path = (vault / REFERENCE_MANIFEST).resolve()
    paths: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in REFERENCE_MANIFEST_EXTENSIONS:
            continue
        if path.resolve() == manifest_path:
            continue
        paths.append(path)
    return paths


def reference_manifest_alignment(vault: Path) -> dict[str, Any]:
    manifest_path = vault / REFERENCE_MANIFEST
    expected_paths = sorted(report_path(vault, path) for path in active_reference_report_paths(vault))
    if not manifest_path.is_file():
        return {
            "status": "missing_manifest",
            "expected_reference_paths": expected_paths,
            "manifest_reference_paths": [],
            "missing_active_report_paths": expected_paths,
            "stale_reference_paths": [],
        }
    manifest = load_json_object(manifest_path)
    references = as_list(manifest.get("references"))
    manifest_paths = sorted(
        str(item.get("path"))
        for item in references
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    )
    if len(manifest_paths) != len(references):
        status = "unreadable_manifest"
    else:
        missing = sorted(set(expected_paths) - set(manifest_paths))
        stale = sorted(set(manifest_paths) - set(expected_paths))
        status = "current" if not missing and not stale else "drift"
    missing_paths = sorted(set(expected_paths) - set(manifest_paths))
    stale_paths = sorted(set(manifest_paths) - set(expected_paths))
    return {
        "status": status,
        "expected_reference_paths": expected_paths,
        "manifest_reference_paths": manifest_paths,
        "missing_active_report_paths": missing_paths,
        "stale_reference_paths": stale_paths,
    }


def archived_report_count(vault: Path) -> int:
    archive = vault / "external-reports" / "archive"
    if not archive.is_dir():
        return 0
    return sum(
        1
        for path in archive.iterdir()
        if path.is_file() and path.suffix.lower() in REPORT_EXTENSIONS
    )


def report_text(path: Path) -> str:
    if path.suffix.lower() not in NARRATIVE_REPORT_EXTENSIONS:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def content_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def priority_counts(text: str) -> dict[str, int]:
    return {
        priority: len(re.findall(rf"\b{priority}\b", text))
        for priority in ("P0", "P1", "P2")
    }


def matched_actions(text: str) -> list[str]:
    matches: list[str] = []
    for action in ACTION_CATALOG:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in action["patterns"]):
            matches.append(str(action["action_id"]))
    return matches


def coverage_markers(path: Path, text: str) -> list[str]:
    haystack = f"{path.name}\n{text}"
    return [
        marker
        for marker, pattern in COVERAGE_MARKER_PATTERNS
        if re.search(pattern, haystack, flags=re.IGNORECASE)
    ]


def release_run_verified(vault: Path) -> bool:
    closeout = load_json_object(vault / "ops/reports/release-closeout-summary.json")
    closeout_summary = as_dict(closeout.get("summary"))
    closeout_status_view = release_status_v2_view_with_readiness_fallback(closeout)
    release_authority_status = str(closeout_status_view["release_authority_status"])
    dashboard = load_json_object(vault / "ops/reports/release-evidence-dashboard.json")
    dashboard_summary = as_dict(dashboard.get("summary"))
    dashboard_status = str(dashboard.get("status", "")).strip()
    full_summary = load_json_object(vault / "ops/reports/test-execution-summary-full.json")
    full_counts = as_dict(full_summary.get("counts"))
    source_package = load_json_object(vault / "ops/reports/source-package-clean-extract.json")
    fixed_point = load_json_object(vault / "ops/reports/release-closeout-fixed-point.json")
    finality = load_json_object(vault / "ops/reports/release-closeout-finality-attestation.json")
    finality_fixed_point = as_dict(finality.get("fixed_point_report"))
    finality_verified, _finality_failures = verify_attestation(vault)
    return (
        closeout.get("status") == "pass"
        and closeout_summary.get("live_make_check_status") == "pass"
        and bool(closeout_status_view["status_v2_available"])
        and release_authority_status in {"clean_pass", "conditional_pass"}
        and dashboard_status in {"pass", "attention", "fail"}
        and authoritative_live_rerun_fail_count(dashboard) == 0
        and authoritative_live_rerun_not_run_count(dashboard) == 0
        and as_int(dashboard_summary.get("required_input_fail_count")) == 0
        and full_summary.get("status") == "pass"
        and as_int(full_counts.get("failed")) == 0
        and as_int(full_counts.get("errors")) == 0
        and source_package.get("status") == "pass"
        and fixed_point.get("status") == "pass"
        and bool(fixed_point.get("converged"))
        and finality_fixed_point.get("status") == "pass"
        and finality_verified
    )


def json_report_status(path: Path) -> str:
    payload = load_json_object(path)
    if not payload:
        return "planned"
    if payload.get("status") in {"pass", "ready"}:
        return "implemented"
    if payload.get("status") in {"attention", "conditional_pass"}:
        return "partially_automated"
    return "requires_release_run_verification"


def _implemented_artifact_report(vault: Path, rel_path: str, artifact_kind: str) -> bool:
    payload = load_json_object(vault / rel_path)
    return payload.get("artifact_kind") == artifact_kind and bool(payload.get("producer"))


def _canonical_json_digest(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _current_contract_digest(vault: Path) -> str:
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    return _canonical_json_digest(contract) if contract else ""


def _all_evidence_status(existing_count: int, expected_count: int) -> str | None:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return None


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def active_report_manifest_freshness_status(vault: Path) -> str:
    alignment = reference_manifest_alignment(vault)
    if alignment["status"] == "current":
        return "implemented"
    if (vault / REFERENCE_MANIFEST).is_file():
        return "partially_automated"
    return "planned"


def source_revision_unknown_canonical_reports_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    unknown_paths = []
    for path in sorted((vault / "ops/reports").glob("*.json")):
        payload = load_json_object(path)
        if str(payload.get("source_revision", "")).strip() == "unknown":
            unknown_paths.append(report_path(vault, path))
    if not unknown_paths:
        return "implemented"
    unknown_path_set = set(unknown_paths)
    if unknown_path_set <= SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS:
        return "requires_release_run_verification"
    return "partially_automated"


def release_lane_mutability_split_status(vault: Path) -> str:
    makefile_text = _read_text_or_empty(vault / "mk/release.mk")
    required_targets = (
        "release-evidence-converge:",
        "release-verify-current:",
        "release-sealed-verify:",
    )
    present_count = sum(1 for target in required_targets if target in makefile_text)
    if present_count == len(required_targets):
        return "implemented"
    if present_count:
        return "partially_automated"
    return "planned"


def sealed_summary_vocabulary_demotion_status(vault: Path) -> str:
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/release/release_closeout_summary.py",
            "ops/schemas/release-closeout-summary.schema.json",
            "tests/test_release_closeout_summary.py",
            "tests/test_release_status_v2.py",
        )
    )
    has_pre_distribution = "pre_distribution_package_binding_status" in surface_text
    has_source_closeout_axis = "source_closeout_distribution_binding_status" in surface_text
    if has_pre_distribution and has_source_closeout_axis:
        return "implemented"
    if has_pre_distribution or has_source_closeout_axis:
        return "partially_automated"
    return "planned"


def selector_marker_scope_parity_status(vault: Path) -> str:
    makefile_text = _read_text_or_empty(vault / "mk/test.mk")
    registry_text = _read_text_or_empty(vault / "ops/test-lane-registry.json")
    required_make_targets = (
        "test-release-sealing-core:",
        "test-release-sealing-all:",
        "test-report-contract-core:",
        "test-report-contract-all:",
    )
    present_make_target_count = sum(1 for target in required_make_targets if target in makefile_text)
    registered_target_count = sum(
        1
        for target in (
            "test-release-sealing-core",
            "test-release-sealing-all",
            "test-report-contract-core",
            "test-report-contract-all",
        )
        if target in registry_text
    )
    if (
        present_make_target_count == len(required_make_targets)
        and registered_target_count == len(required_make_targets)
    ):
        return "implemented"
    if present_make_target_count or registered_target_count or "tests/test_release_status_v2.py" in makefile_text:
        return "partially_automated"
    return "planned"


def ruff_strict_preview_import_order_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py",
            "tools/ruff_strict_preview.py",
            "mk/static.mk",
        )
    )
    if (
        "from .set_mechanism_run_history import (\n" in surface_text
        and "RUFF_STRICT_PREVIEW_TARGETS" in surface_text
        and "--allowlist" not in surface_text
        and "tools/ruff_strict_preview.py" in surface_text
    ):
        return "implemented"
    return "requires_release_run_verification"


def roadmap_source_only_status(existing_count: int, expected_count: int) -> str:
    if existing_count == expected_count:
        return "implemented"
    if existing_count:
        return "partially_automated"
    return "planned"


def release_source_ready_deindex_hardening_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/release/release_source_ready_commit.py",
            "tests/test_release_source_ready_commit.py",
        )
    )
    if all(
        token in surface_text
        for token in (
            "local_only_deindex_paths",
            "LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY",
            "--ignore-unmatch",
            "test_commits_deindex_with_public_and_generated_updates",
        )
    ):
        return "implemented"
    return "requires_release_run_verification"


def uv_lock_canonical_policy_status(vault: Path, existing_count: int, expected_count: int) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    docs_text = _read_text_or_empty(vault / "docs/development.md")
    if "uv lock --check" in docs_text and "uv.lock" in docs_text:
        return "implemented"
    return "requires_release_run_verification"


def operator_entrypoint_index_status(vault: Path, existing_count: int, expected_count: int) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    make_surface = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in ("Makefile", "mk/core.mk")
    )
    docs_text = _read_text_or_empty(vault / "docs/development.md")
    if (
        re.search(r"(?m)^help:", make_surface)
        and "make help" in docs_text
        and all(token in make_surface for token in ("release", "public", "mechanism", "report-contract"))
    ):
        return "implemented"
    return "requires_release_run_verification"


def strict_preview_all_target_audit_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "tools/strict_preview_audit.py",
            "mk/static.mk",
            "tests/test_strict_preview_audit.py",
        )
    )
    if all(
        token in surface_text
        for token in (
            "strict-preview-audit:",
            "artifact_kind",
            "strict_preview_audit",
            "ops/scripts tests tools",
        )
    ):
        return "implemented"
    return "requires_release_run_verification"


def _goal_contract_is_bounded(contract: dict[str, Any]) -> bool:
    budgets = as_dict(contract.get("budgets"))
    runtime = as_dict(contract.get("runtime"))
    goal_backend = as_dict(contract.get("goal_backend"))
    promotion_guard = as_dict(contract.get("promotion_guard"))
    return bool(
        contract.get("$schema") == "ops/schemas/codex-goal-contract.schema.json"
        and contract.get("schema_version") == 1
        and contract.get("status") in {"active", "completed"}
        and as_int(budgets.get("max_wall_clock_seconds")) > 0
        and as_int(budgets.get("max_proposals")) > 0
        and as_int(budgets.get("max_consecutive_failures")) > 0
        and as_int(budgets.get("heartbeat_interval_seconds")) > 0
        and as_int(budgets.get("checkpoint_interval_seconds")) > 0
        and runtime.get("mode") == "self_improvement_loop"
        and as_int(runtime.get("duration_seconds")) > 0
        and runtime.get("certificate_status") in {"unverified", "verified"}
        and bool(goal_backend.get("process_persistent"))
        and goal_backend.get("backend_type") in {"file", "run_local_file"}
        and as_list(contract.get("stop_conditions"))
        and as_list(contract.get("required_evidence"))
        and bool(promotion_guard.get("no_sustained_claim_before_certificate_verified"))
        and not bool(promotion_guard.get("sustained_runtime_claimed"))
    )


def goal_contract_schema_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    if _goal_contract_is_bounded(contract):
        return "implemented"
    return "requires_release_run_verification"


def codex_goal_adapter_status(vault: Path, existing_count: int, expected_count: int) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    goal_backend = as_dict(contract.get("goal_backend"))
    storage_path = str(goal_backend.get("storage_path", "")).strip()
    if _goal_contract_is_bounded(contract) and (
        storage_path == "ops/reports/codex-goal-contract.json"
        or (
            storage_path.startswith("runs/goal-")
            and storage_path.endswith("/state/codex-goal-contract.json")
        )
    ):
        return "implemented"
    return "requires_release_run_verification"


def codex_goal_prompt_generator_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    report = load_json_object(vault / "ops/reports/codex-goal-prompt.json")
    goal_contract = as_dict(report.get("goal_contract"))
    prompt = as_dict(report.get("prompt"))
    promotion_guard = as_dict(report.get("promotion_guard"))
    contract_digest = _current_contract_digest(vault)
    prompt_guard_is_explicit = bool(prompt.get("includes_sustained_claim_ban"))
    prompt_guard_is_certified = bool(
        promotion_guard.get("promotion_ban_required") is False
        and promotion_guard.get("runtime_certificate_verified") is True
        and promotion_guard.get("can_promote_result") is True
        and not as_list(promotion_guard.get("promotion_blockers"))
    )
    if (
        report.get("artifact_kind") == "codex_goal_prompt"
        and report.get("producer") == "ops.scripts.codex_goal_prompt"
        and report.get("status") in {"pass", "attention"}
        and bool(goal_contract.get("process_persistent_backend"))
        and goal_contract.get("contract_sha256") == contract_digest
        and bool(prompt.get("includes_budget_limits"))
        and bool(prompt.get("includes_allowed_roots"))
        and (prompt_guard_is_explicit or prompt_guard_is_certified)
        and not bool(promotion_guard.get("sustained_runtime_claimed"))
    ):
        return "implemented"
    return "requires_release_run_verification"


def auto_improve_goal_contract_input_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    budgets = as_dict(contract.get("budgets"))
    required_evidence = as_list(contract.get("required_evidence"))
    required_paths = {
        str(item.get("path", "")).strip()
        for item in required_evidence
        if isinstance(item, dict)
    }
    has_goal_status_path = "ops/reports/goal-run-status.json" in required_paths or any(
        path.startswith("runs/goal-") and path.endswith("/state/goal-run-status.json")
        for path in required_paths
    )
    if (
        _goal_contract_is_bounded(contract)
        and as_int(budgets.get("max_wall_clock_seconds")) >= 21600
        and as_int(budgets.get("max_proposals")) >= 1
        and as_int(budgets.get("max_consecutive_failures")) >= 1
        and has_goal_status_path
    ):
        return "implemented"
    return "requires_release_run_verification"


def goal_run_status_audit_resume_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    report = load_json_object(vault / "ops/reports/goal-run-status.json")
    goal = as_dict(report.get("goal"))
    backend = as_dict(goal.get("backend"))
    artifacts = as_dict(report.get("artifacts"))
    health = as_dict(report.get("health"))
    runtime_certificate = as_dict(report.get("runtime_certificate"))
    contract_digest = _current_contract_digest(vault)
    status_report_path = str(artifacts.get("status_report_path", "")).strip()
    status_report_path_valid = status_report_path == "ops/reports/goal-run-status.json" or (
        status_report_path.startswith("runs/goal-")
        and status_report_path.endswith("/state/goal-run-status.json")
    )
    artifact_paths = {
        "status_markdown_path": "runs/goal-",
        "audit_log_path": "runs/goal-",
        "resume_metadata_path": "runs/goal-",
        "checkpoint_command_log_path": "runs/goal-",
    }
    paths_valid = all(
        str(artifacts.get(key, "")).startswith(prefix)
        if prefix.endswith("-")
        else artifacts.get(key) == prefix
        for key, prefix in artifact_paths.items()
    )
    blocked_pending_state = bool(
        health.get("promotion_status") == "blocked"
        and health.get("can_promote_result") is False
        and runtime_certificate.get("status") in {"pending", "complete"}
    )
    verified_completed_state = bool(
        report.get("status") == "pass"
        and health.get("promotion_status") == "allowed"
        and health.get("can_promote_result") is True
        and runtime_certificate.get("status") == "complete"
        and runtime_certificate.get("certificate_status") == "verified"
        and runtime_certificate.get("full_gate_clean") is True
        and not as_list(runtime_certificate.get("promotion_blockers"))
    )
    if (
        report.get("artifact_kind") == "goal_run_status"
        and report.get("producer") == "ops.scripts.goal_run_status"
        and report.get("status") in {"pass", "attention", "fail"}
        and bool(backend.get("process_persistent"))
        and goal.get("contract_sha256") == contract_digest
        and status_report_path_valid
        and paths_valid
        and health.get("heartbeat_status") in {"current", "stale"}
        and health.get("checkpoint_status") in {"current", "stale"}
        and health.get("command_heartbeat_status") in {"current", "stale", "not_recorded"}
        and health.get("backoff_status") in {"inactive", "active", "expired"}
        and health.get("resume_status") in {"not_requested", "ready"}
        and (blocked_pending_state or verified_completed_state)
        and runtime_certificate.get("mode") == "self_improvement_loop"
    ):
        return "implemented"
    return "requires_release_run_verification"


def goal_execution_runtime_certificate_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    report = load_json_object(vault / "ops/reports/goal-runtime-certificate.json")
    certificate = as_dict(report.get("certificate"))
    run = as_dict(report.get("run"))
    run_artifacts = as_dict(report.get("run_artifacts"))
    session_evidence = as_dict(report.get("session_evidence"))
    command_observability = as_dict(report.get("command_observability"))
    contract_update = as_dict(report.get("contract_update"))
    if (
        report.get("artifact_kind") == "goal_runtime_certificate"
        and report.get("producer") == "ops.scripts.goal_runtime_certificate_report"
        and report.get("status") == "pass"
        and certificate.get("target_runtime_mode") == "self_improvement_loop"
        and certificate.get("verification_status") in {"eligible", "already_verified"}
        and certificate.get("eligible") is True
        and run.get("run_status") == "completed"
        and run.get("run_runtime_mode") == "self_improvement_loop"
        and run_artifacts.get("status") == "clean"
        and session_evidence.get("status") == "clean"
        and command_observability.get("status") == "clean"
        and contract_update.get("runtime_certificate_verified_after") is True
        and not as_list(report.get("blockers"))
    ):
        return "implemented"
    return "requires_release_run_verification"


def goal_executor_backoff_observability_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    report = load_json_object(vault / "ops/reports/goal-run-status.json")
    health = as_dict(report.get("health"))
    observability = as_dict(report.get("observability"))
    command_mode = str(observability.get("command_observation_mode", "")).strip()
    backoff_until = observability.get("last_backoff_until")
    backoff_reason = observability.get("backoff_reason")
    if (
        report.get("artifact_kind") == "goal_run_status"
        and report.get("producer") == "ops.scripts.goal_run_status"
        and report.get("status") in {"pass", "attention"}
        and health.get("backoff_status") in {"inactive", "active", "expired"}
        and command_mode in {"", "communicate", "process_poll", "process_heartbeat"}
        and isinstance(backoff_until, str)
        and isinstance(backoff_reason, str)
        and "last_backoff_until" in observability
        and "backoff_reason" in observability
    ):
        return "implemented"
    return "requires_release_run_verification"


def selected_contract_currentness_gate_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    readiness = load_json_object(vault / "ops/reports/auto-improve-readiness.json")
    selected_contract = as_dict(as_dict(readiness.get("diagnostics")).get("selected_contract_summary"))
    artifact_freshness = as_dict(as_dict(readiness.get("diagnostics")).get("artifact_freshness_summary"))
    test_summary = load_json_object(vault / "ops/reports/test-execution-summary.json")
    blockers = as_list(readiness.get("promotion_blockers"))
    blocker_ids = {
        str(item.get("id", "")).strip()
        for item in blockers
        if isinstance(item, dict)
    }
    selected_status = str(selected_contract.get("status", "")).strip()
    selected_gate_active = selected_status == "pass" or (
        selected_status == "fail"
        and "promotion_blocked_by_selected_contract_failure" in blocker_ids
    )
    if (
        readiness.get("artifact_kind") == "auto_improve_readiness_report"
        and test_summary.get("artifact_kind") == "test_execution_summary"
        and selected_contract.get("path") == "ops/reports/test-execution-summary.json"
        and selected_gate_active
        and artifact_freshness.get("status") in {"pass", "fail"}
    ):
        return "implemented"
    return "requires_release_run_verification"


def git_worktree_goal_guard_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    try:
        makefile_text = (vault / "mk/mechanism.mk").read_text(encoding="utf-8")
    except OSError:
        makefile_text = ""
    if (
        "auto-improve-goal-preflight: goal-runtime-lock-check goal-runtime-python-preflight" in makefile_text
        and "ops.scripts.goal_worktree_guard" in makefile_text
        and "--requested-mode \"$(GOAL_WORKTREE_MODE)\"" in makefile_text
        and "--out \"$(GOAL_WORKTREE_GUARD_OUT)\"" in makefile_text
        and "goal-worktree-guard: auto-improve-goal-preflight" in makefile_text
    ):
        return "implemented"
    return "requires_release_run_verification"


def goal_runtime_transient_cleanup_gate_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    try:
        makefile_text = (vault / "mk/mechanism.mk").read_text(encoding="utf-8")
    except OSError:
        makefile_text = ""
    if (
        "goal-runtime-clean-transient:" in makefile_text
        and "goal-runtime-run-admission-local-refresh:" in makefile_text
        and "goal-runtime-run-admission: goal-runtime-run-admission-local-refresh" in makefile_text
        and "goal-runtime-run-admission-converge:" in makefile_text
        and "$(MAKE) goal-runtime-clean-transient" in makefile_text
        and "$(MAKE) goal-runtime-quarantine-preflight" in makefile_text
        and "--readiness-report \"$(GOAL_LOCAL_READINESS_OUT)\"" in makefile_text
        and "--remediation-backlog-report \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\"" in makefile_text
        and "long-run-preflight-clean:" in makefile_text
        and "long-run-preflight-clean: goal-runtime-run-admission-converge" in makefile_text
    ):
        return "implemented"
    return "requires_release_run_verification"


def artifact_freshness_performance_observability_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/core/artifact_freshness_runtime.py",
            "tests/test_artifact_freshness_runtime.py",
            "mk/artifact.mk",
        )
    )
    has_run_context = "ArtifactFreshnessContext" in surface_text
    has_schema_cache = any(
        token in surface_text
        for token in (
            "schema_cache",
            "validator_cache",
            "compiled_validator_cache",
        )
    )
    has_progress = "--progress" in surface_text and "jsonl" in surface_text
    has_timing = any(
        token in surface_text
        for token in (
            "phase_timing",
            "phase_timings",
            "elapsed_seconds",
            "per_phase_timing",
        )
    )
    report = load_json_object(vault / "ops/reports/artifact-freshness-report.json")
    if (
        existing_count == expected_count
        and report.get("status") == "pass"
        and has_run_context
        and has_schema_cache
        and has_progress
        and has_timing
    ):
        return "implemented"
    return "partially_automated"


def repo_boundary_history_hygiene_status(vault: Path, existing_count: int, expected_count: int) -> str:
    if existing_count == 0:
        return "planned"
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            ".gitignore",
            "ARCHITECTURE.md",
            "docs/public-mirror.md",
            "ops/scripts/public/public_surface_policy.py",
            "tests/test_public_surface_policy.py",
            "tests/test_export_public_repo.py",
        )
    )
    report = load_json_object(vault / "ops/reports/public-check-summary.json")
    physical_split_status = str(
        as_dict(report.get("summary")).get("physical_repo_split_status", "")
    ).strip()
    history_absence_status = str(
        as_dict(report.get("summary")).get("private_surface_history_absence_status", "")
    ).strip()
    negative_assertion_fail_count = as_int(
        as_dict(report.get("summary")).get("negative_assertion_fail_count")
    )
    if (
        report.get("status") == "pass"
        and physical_split_status == "pass"
        and history_absence_status == "pass"
        and negative_assertion_fail_count == 0
    ):
        return "implemented"
    has_public_policy = all(
        token in surface_text
        for token in (
            "raw/",
            "wiki/",
            "system/",
            "runs/",
            "external-reports/",
        )
    )
    if has_public_policy or existing_count:
        return "partially_automated"
    return "planned"


def github_native_security_automation_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    workflow_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            ".github/workflows/codeql.yml",
            ".github/workflows/dependency-review.yml",
        )
    )
    has_dependabot = (vault / ".github/dependabot.yml").is_file()
    has_codeql = "github/codeql-action" in workflow_text or "codeql" in _read_text_or_empty(
        vault / ".github/workflows/codeql.yml"
    ).lower()
    has_dependency_review = "actions/dependency-review-action" in workflow_text
    has_concurrency = "concurrency:" in workflow_text
    external_uses = re.findall(r"uses:\s+([^\s#]+)", workflow_text)
    pinned_uses = [
        use
        for use in external_uses
        if re.search(r"@[0-9a-f]{40}\b", use)
        or use.startswith("./")
        or use.startswith("docker://sha256:")
    ]
    all_external_uses_pinned = bool(external_uses) and len(pinned_uses) == len(external_uses)
    if (
        existing_count == expected_count
        and has_dependabot
        and has_codeql
        and has_dependency_review
        and has_concurrency
        and all_external_uses_pinned
    ):
        return "implemented"
    return "partially_automated"


def maintainability_hotspot_refactor_backlog_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    report = load_json_object(vault / "ops/reports/function-budget-refactor-proposals.json")
    summary = as_dict(report.get("summary"))
    proposal_count = as_int(summary.get("proposal_count"))
    candidate_count = as_int(summary.get("function_budget_candidate_count"))
    owner_backlog_count = as_int(summary.get("owner_backlog_count"))
    large_main_count = as_int(summary.get("large_main_without_tests_or_docs_count"))
    if (
        existing_count == expected_count
        and report.get("artifact_kind") == "function_budget_refactor_proposals"
        and report.get("producer") == "ops.scripts.function_budget_refactor_proposals"
        and report.get("status") == "pass"
        and candidate_count > 0
        and proposal_count > 0
        and owner_backlog_count > 0
        and large_main_count == 0
    ):
        return "implemented"
    if report or candidate_count or existing_count:
        return "partially_automated"
    return "planned"


def generated_artifact_tracking_policy_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/core/generated_artifact_index.py",
            "ops/schemas/generated-artifact-index.schema.json",
            "tests/test_generated_artifact_index.py",
        )
    )
    report = load_json_object(vault / "ops/reports/generated-artifact-index.json")
    explicit_policy = any(
        token in surface_text
        for token in (
            "decision_grade",
            "decision-grade",
            "tracking_policy",
            "commit_policy",
        )
    )
    has_ephemeral_class = "ephemeral" in surface_text
    if (
        existing_count == expected_count
        and report.get("artifact_kind") == "generated_artifact_index_report"
        and report.get("producer") == "ops.scripts.generated_artifact_index"
        and explicit_policy
        and has_ephemeral_class
    ):
        return "implemented"
    return "partially_automated"


def public_export_negative_assertions_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    report = load_json_object(vault / "ops/reports/public-check-summary.json")
    report_text_value = json.dumps(report, ensure_ascii=False, sort_keys=True)
    required_assertions = (
        "excluded_prefix_absence",
        "local_path_absence",
        "private_pattern_absence",
    )
    if (
        existing_count == expected_count
        and report.get("status") == "pass"
        and all(token in report_text_value for token in required_assertions)
        and not re.search(r'"(?:status|result)"\s*:\s*"(?:fail|attention)"', report_text_value)
    ):
        return "implemented"
    return "partially_automated"


def supply_chain_external_verification_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    gate = load_json_object(vault / "ops/reports/supply-chain-gate-report.json")
    sbom = load_json_object(vault / "ops/reports/sbom-readiness-gate-report.json")
    in_toto = load_json_object(vault / "ops/reports/in-toto-statement.json")
    sigstore = load_json_object(vault / "ops/reports/sigstore-bundle-verification.json")
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in (
            "mk/supply_chain.mk",
            "ops/reports/supply-chain-gate-report.json",
            ".github/workflows/release.yml",
            ".github/workflows/dependency-review.yml",
        )
    )
    has_slsa_predicate = in_toto.get("predicateType") == "https://slsa.dev/provenance/v1"
    sigstore_checks = as_list(sigstore.get("verification_checks"))
    has_release_attestation = "attest-build-provenance@" in surface_text
    has_dependency_review = "dependency-review-action@" in surface_text
    has_sigstore_bundle_target = "sigstore-bundle:" in surface_text
    external_bundle_rule_present = any(
        as_dict(check).get("rule") == "external_bundle_observed" for check in sigstore_checks
    )
    if (
        existing_count == expected_count
        and gate.get("status") == "pass"
        and sbom.get("status") == "pass"
        and has_slsa_predicate
        and sigstore.get("status") in {"local-integrity-only", "verified-external-bundle"}
        and sigstore_checks
        and has_release_attestation
        and has_dependency_review
        and has_sigstore_bundle_target
        and external_bundle_rule_present
    ):
        return "implemented"
    return "partially_automated"


def collaboration_governance_surface_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count == expected_count:
        return "implemented"
    return "partially_automated"


def single_source_status(vault: Path) -> str:
    planner_path = vault / "ops" / "reports" / "workflow-dependency-planner.json"
    guard_path = vault / "ops" / "reports" / "release-workflow-order-guard.json"
    planner = load_json_object(planner_path)
    guard = load_json_object(guard_path)
    if not planner or not guard:
        makefile_path = vault / "Makefile"
        if not makefile_path.is_file():
            if guard.get("status") == "pass":
                return "partially_automated"
            return "planned"
    runtime_context = RuntimeContext(display_timezone=dt.UTC)
    if not guard:
        guard = build_release_workflow_order_guard_report(vault, context=runtime_context)
    if not planner:
        planner = build_workflow_dependency_report(vault, context=runtime_context)
    rules = as_list(planner.get("workflow_rules"))
    planner_targets: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("workflow_id") != "workflow_dependency_planner_closeout":
            continue
        targets = rule.get("targets")
        if not isinstance(targets, list):
            continue
        planner_targets.extend(str(target) for target in targets)
    has_policy_targets = "generated-artifact-index-body" in planner_targets
    if guard.get("status") == "pass" and has_policy_targets:
        return "implemented"
    if guard:
        return "partially_automated"
    return "planned"


def authoritative_live_rerun_not_run_count(dashboard: dict[str, Any]) -> int:
    count = 0
    for gate in as_list(dashboard.get("gates")):
        gate_payload = as_dict(gate)
        live_rerun_state = as_dict(gate_payload.get("live_rerun_state"))
        if (
            bool(gate_payload.get("authoritative_for_release"))
            and str(live_rerun_state.get("status", "")).strip() == "not_run"
        ):
            count += 1
    return count


def authoritative_live_rerun_fail_count(dashboard: dict[str, Any]) -> int:
    count = 0
    for gate in as_list(dashboard.get("gates")):
        gate_payload = as_dict(gate)
        live_rerun_state = as_dict(gate_payload.get("live_rerun_state"))
        if (
            bool(gate_payload.get("authoritative_for_release"))
            and str(live_rerun_state.get("status", "")).strip() == "fail"
        ):
            count += 1
    return count


def command_heartbeat_observability_status(vault: Path, existing_count: int, expected_count: int) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    source_package = load_json_object(vault / "ops/reports/source-package-clean-extract.json")
    heartbeat = as_dict(source_package.get("heartbeat_observability"))
    if (
        source_package.get("status") == "pass"
        and heartbeat.get("status") == "pass"
        and as_int(heartbeat.get("heartbeat_enabled_command_count"))
        == as_int(heartbeat.get("command_count"))
    ):
        return "implemented"
    return "requires_release_run_verification"


def sealed_preflight_canonicalization_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    report = load_json_object(vault / "ops/reports/release-closeout-sealed-rehearsal-check.json")
    if (
        report.get("artifact_kind") == "release_closeout_sealed_rehearsal_check"
        and str(report.get("preflight_status", "")).strip()
        in {"sealed_clean_pass", "binding_pass_authority_blocked"}
        and str(report.get("distribution_binding_status", "")).strip() == "pass"
        and str(report.get("authority_preflight_status", "")).strip()
        in {"clean", "blocked"}
    ):
        return "implemented"
    if existing_count < expected_count:
        return "partially_automated"
    return "requires_release_run_verification"


def status_from_evidence(vault: Path, action: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    evidence = []
    existing_count = 0
    for rel_path in action["evidence_paths"]:
        path = vault / str(rel_path)
        payload = load_json_object(path) if path.suffix == ".json" else {}
        exists = path.exists()
        existing_count += 1 if exists else 0
        evidence.append(
            {
                "path": str(rel_path),
                "exists": exists,
                "status": str(payload.get("status", "")) if payload else "",
                "producer": str(payload.get("producer", "")) if payload else "",
            }
        )
    action_id = str(action["action_id"])
    if action_id == "release_writer_dependency_single_source":
        status = single_source_status(vault)
    elif action_id == "outcome_provenance_gate_policy":
        status = json_report_status(vault / "ops/reports/outcome-provenance-gate-policy.json")
    elif action_id == "external_report_lifecycle":
        alignment = reference_manifest_alignment(vault)
        if alignment["status"] == "current":
            status = "implemented"
        elif (vault / REFERENCE_MANIFEST).exists():
            status = "partially_automated"
        else:
            status = "planned"
    elif action_id == "active_report_manifest_freshness":
        status = active_report_manifest_freshness_status(vault)
    elif action_id == "source_revision_unknown_canonical_reports":
        status = source_revision_unknown_canonical_reports_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "release_lane_mutability_split":
        status = release_lane_mutability_split_status(vault)
    elif action_id == "sealed_summary_vocabulary_demotion":
        status = sealed_summary_vocabulary_demotion_status(vault)
    elif action_id == "selector_marker_scope_parity":
        status = selector_marker_scope_parity_status(vault)
    elif action_id == "ruff_strict_preview_import_order":
        status = ruff_strict_preview_import_order_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "release_source_ready_deindex_hardening":
        status = release_source_ready_deindex_hardening_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "uv_lock_canonical_policy":
        status = uv_lock_canonical_policy_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "operator_entrypoint_index":
        status = operator_entrypoint_index_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "strict_preview_all_target_audit":
        status = strict_preview_all_target_audit_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id in ROADMAP_SOURCE_ONLY_ACTION_IDS:
        status = roadmap_source_only_status(existing_count, len(action["evidence_paths"]))
    elif action_id in {
        "script_output_surfaces_currentness",
        "function_budget_proposal_adapter",
        "windows_path_and_archive_alias_parity",
    }:
        status = "implemented" if existing_count == len(action["evidence_paths"]) else "planned"
    elif action_id == "negative_learning_ledger":
        status = (
            "implemented"
            if existing_count == len(action["evidence_paths"])
            and _implemented_artifact_report(
                vault,
                "ops/reports/self-improvement-negative-lessons.json",
                "self_improvement_negative_lessons",
            )
            else "partially_automated"
            if existing_count
            else "planned"
        )
    elif action_id == "remediation_backlog":
        status = (
            "implemented"
            if existing_count == len(action["evidence_paths"])
            and _implemented_artifact_report(
                vault,
                "ops/reports/remediation-backlog.json",
                "remediation_backlog",
            )
            else "partially_automated"
            if existing_count
            else "planned"
        )
    elif action_id == "command_heartbeat_observability":
        status = command_heartbeat_observability_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "sealed_preflight_canonicalization":
        status = sealed_preflight_canonicalization_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "goal_contract_schema":
        status = goal_contract_schema_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "codex_goal_adapter":
        status = codex_goal_adapter_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "codex_goal_prompt_generator":
        status = codex_goal_prompt_generator_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "auto_improve_goal_contract_input":
        status = auto_improve_goal_contract_input_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "goal_run_status_audit_resume":
        status = goal_run_status_audit_resume_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "goal_execution_runtime_certificate":
        status = goal_execution_runtime_certificate_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "goal_executor_backoff_observability":
        status = goal_executor_backoff_observability_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "selected_contract_currentness_gate":
        status = selected_contract_currentness_gate_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "git_worktree_goal_guard":
        status = git_worktree_goal_guard_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "goal_runtime_transient_cleanup_gate":
        status = goal_runtime_transient_cleanup_gate_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "artifact_freshness_performance_observability":
        status = artifact_freshness_performance_observability_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "repo_boundary_history_hygiene":
        status = repo_boundary_history_hygiene_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "github_native_security_automation":
        status = github_native_security_automation_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "maintainability_hotspot_refactor_backlog":
        status = maintainability_hotspot_refactor_backlog_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "generated_artifact_tracking_policy":
        status = generated_artifact_tracking_policy_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "public_export_negative_assertions":
        status = public_export_negative_assertions_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "supply_chain_external_verification":
        status = supply_chain_external_verification_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id == "collaboration_governance_surface":
        status = collaboration_governance_surface_status(
            vault,
            existing_count,
            len(action["evidence_paths"]),
        )
    elif action_id in RELEASE_VERIFIED_ACTION_IDS and existing_count == len(action["evidence_paths"]):
        status = "implemented" if release_run_verified(vault) else "requires_release_run_verification"
    elif existing_count == len(action["evidence_paths"]):
        status = "requires_release_run_verification"
    elif existing_count:
        status = "partially_automated"
    else:
        status = "planned"
    return status, evidence


def action_statuses(vault: Path) -> dict[str, str]:
    return {
        str(action["action_id"]): status_from_evidence(vault, action)[0]
        for action in ACTION_CATALOG
    }


def report_coverage_item(vault: Path, path: Path) -> dict[str, Any]:
    rel_path = report_path(vault, path)
    text = report_text(path)
    action_ids = matched_actions(text) if text else ["external_report_lifecycle"]
    if path.name == Path(REFERENCE_MANIFEST).name:
        action_ids = sorted(set(action_ids) | {"active_report_manifest_freshness"})
    return {
        "path": rel_path,
        "report_type": "reference_manifest" if path.name == "report-reference-manifest.json" else "narrative_report",
        "priority_mentions": priority_counts(text),
        "matched_action_ids": action_ids,
        "matched_action_count": len(action_ids),
    }


def report_lifecycle_profiles(vault: Path, paths: list[Path]) -> list[dict[str, Any]]:
    profiles = []
    for path in paths:
        text = report_text(path)
        coverage = report_coverage_item(vault, path)
        rel_parts = Path(str(coverage["path"])).parts
        profiles.append(
            {
                **coverage,
                "lifecycle_namespace": "archive" if "archive" in rel_parts else "active_root",
                "line_count": len(text.splitlines()) if text else None,
                "content_sha256": content_sha256(path),
                "coverage_markers": coverage_markers(path, text),
                "explicit_archive_status": bool(ARCHIVE_STATUS_RE.search(text)),
                "explicit_successor_paths": sorted(
                    item.strip()
                    for item in SUPERSEDED_BY_RE.findall(text)
                    if item.strip()
                ),
            }
        )
    return profiles


def content_lifecycle_inventory(vault: Path) -> list[dict[str, Any]]:
    return report_lifecycle_profiles(vault, active_report_paths(vault))


def _unresolved_action_ids(profile: dict[str, Any], statuses: dict[str, str]) -> set[str]:
    return {
        str(action_id)
        for action_id in profile["matched_action_ids"]
        if statuses.get(str(action_id)) != "implemented"
    }


def _coverage_authority(profile: dict[str, Any], statuses: dict[str, str]) -> tuple[int, int, int, int]:
    unresolved = _unresolved_action_ids(profile, statuses)
    namespace_rank = 1 if profile.get("lifecycle_namespace") == "active_root" else 0
    return (
        namespace_rank,
        len(profile.get("coverage_markers", [])),
        len(unresolved),
        int(profile.get("matched_action_count") or 0),
    )


def lifecycle_decision(
    profile: dict[str, Any],
    *,
    profiles: list[dict[str, Any]],
    statuses: dict[str, str],
) -> dict[str, Any]:
    path = str(profile["path"])
    if profile["report_type"] != "narrative_report":
        return {
            "archive_recommended": False,
            "reason": "Reference manifest remains active lifecycle evidence.",
            "superseded_by": [],
        }
    action_ids = {str(action_id) for action_id in profile["matched_action_ids"]}
    if not action_ids:
        if profile.get("lifecycle_namespace") == "archive":
            return {
                "archive_recommended": True,
                "reason": "Archived external report has no structured action coverage; archive remains sticky.",
                "superseded_by": [],
            }
        return {
            "archive_recommended": False,
            "reason": "No structured action coverage was detected; keep active for operator review.",
            "superseded_by": [],
        }
    if bool(profile["explicit_archive_status"]):
        return {
            "archive_recommended": True,
            "reason": "External report carries an explicit closed/superseded archive lifecycle marker.",
            "superseded_by": list(profile["explicit_successor_paths"]),
        }

    unresolved = sorted(_unresolved_action_ids(profile, statuses))
    if not unresolved:
        return {
            "archive_recommended": True,
            "reason": "All structured action themes from this external report are implemented in canonical evidence.",
            "superseded_by": [],
        }

    unresolved_set = set(unresolved)
    covering_reports = []
    own_authority = _coverage_authority(profile, statuses)
    for other in profiles:
        other_path = str(other["path"])
        if other_path == path or other["report_type"] != "narrative_report":
            continue
        other_actions = {str(action_id) for action_id in other["matched_action_ids"]}
        other_authority = _coverage_authority(other, statuses)
        if unresolved_set.issubset(other_actions) and other_authority > own_authority:
            covering_reports.append(other_path)

    if covering_reports:
        return {
            "archive_recommended": True,
            "reason": (
                "External report has no unique unresolved action themes; remaining open themes are covered by "
                "a broader active external report."
            ),
            "superseded_by": sorted(covering_reports),
        }
    return {
        "archive_recommended": False,
        "reason": "External report still carries unique unresolved action themes not covered by another active report.",
        "superseded_by": [],
    }
