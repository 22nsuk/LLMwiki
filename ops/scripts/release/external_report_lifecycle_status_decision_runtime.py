from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from ops.scripts.core.policy_runtime import report_path

from .external_report_action_catalog import SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS
from .external_report_inventory_runtime import (
    REFERENCE_MANIFEST,
    active_report_paths,
    as_dict,
    as_int,
    as_list,
    is_binary_report_path,
    load_json_object,
    reference_manifest_alignment,
)
from .external_report_lifecycle_maintainability_runtime import (
    maintainability_hotspot_refactor_backlog_status,
)
from .external_report_lifecycle_operator_runtime import operator_entrypoint_index_status
from .external_report_lifecycle_status_loader_runtime import (
    all_evidence_status,
    current_contract_digest,
    goal_contract_is_bounded,
    goal_runtime_certificate_noncertifiable_closed_failure,
    goal_status_contract_digest,
    has_codeowners_review_owner,
    has_contributing_commit_governance_policy,
    has_pr_review_section,
    json_report_status,
    learning_claim_service_complete,
    make_target_exists,
    read_text_or_empty,
    release_authority_service_complete,
    release_currentness_service_complete,
    release_risk_service_complete,
    workflow_uses_entries,
)
from .external_report_release_verification_runtime import (
    CountStatusResolver,
    _dedupe_reason_ids,
    _reason_token,
    _release_verified_count_status,
)
from .release_closeout_fixed_point import POLICY_PATH as FIXED_POINT_POLICY_PATH
from .release_workflow_order_guard import (
    SPEC_PATH as WORKFLOW_ORDER_SPEC_PATH,
    release_writer_single_source_contract,
)


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


def codex_exec_dependency_preflight_trust_boundary_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/core/codex_exec_dependency_preflight_runtime.py",
            "ops/scripts/core/codex_exec_dependency_preflight_decision_runtime.py",
            "ops/scripts/core/codex_exec_workspace_runtime.py",
            "ops/scripts/core/trusted_candidate_runner.py",
            "tests/test_executor_runtime.py",
            "tests/test_trusted_candidate_runner.py",
        )
    )
    if all(
        token in surface_text
        for token in (
            "trusted_dependency_preflight_python(",
            "DependencyPreflightTrustError",
            "path_is_inside_workspace",
            "resolve(strict=True)",
            "run_trusted_candidate_command(",
            "trusted_python_realpath",
            "same-root workspace python identity manifest is self-signed",
            "trusted python symlink target changed before launch",
            "test_same_root_dependency_preflight_blocks_self_signed_workspace_python_without_execution",
            "test_same_root_dependency_preflight_blocks_untrusted_sys_executable_path",
            "test_same_root_dependency_preflight_captures_workspace_symlink_realpath",
            "test_external_workspace_dependency_preflight_executes_artifact_python",
            "test_run_trusted_candidate_command_blocks_trusted_python_symlink_swap",
        )
    ):
        return "implemented"
    return "requires_release_run_verification"


def bootstrap_dev_install_hardening_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/core/bootstrap_preflight.py",
            "mk/core.mk",
            "docs/development.md",
            "tests/test_bootstrap_preflight.py",
            "tests/test_makefile_static_gates.py",
        )
    )
    if all(
        token in surface_text
        for token in (
            "DEV_DEPENDENCIES",
            "importlib.metadata.version",
            "DEV_INSTALL_ROLLBACK_DIR",
            "DEV_INSTALL_READY_MARKER",
            ".venv.previous",
            "test_dev_report_checks_full_dev_lane_dependency_surface",
            "test_dev_install_creates_editable_environment",
        )
    ):
        return "implemented"
    return "requires_release_run_verification"


def release_manifest_path_classification_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/eval/wiki_manifest.py",
            "ops/scripts/core/source_trace_profile_runtime.py",
            "tests/test_manifest_export_symlink_safety.py",
            "tests/test_source_trace_runtime.py",
        )
    )
    if all(
        token in surface_text
        for token in (
            "classify_release_manifest_path",
            "RELEASE_MANIFEST_PATH_INVALID",
            "release_manifest_includes_path",
            "MISSING_INVALID_PATH",
            "test_release_manifest_excludes_path_is_valid_path_compatibility_facade",
        )
    ):
        return "implemented"
    return "requires_release_run_verification"


RELEASE_LANE_MUTABILITY_SPLIT_SURFACES = (
    "mk/release.mk",
    "mk/release-authority.mk",
    "mk/release-evidence.mk",
    "mk/release-learning.mk",
)


def release_lane_mutability_split_status(vault: Path) -> str:
    makefile_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in RELEASE_LANE_MUTABILITY_SPLIT_SURFACES
    )
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
        read_text_or_empty(vault / rel_path)
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
    makefile_text = read_text_or_empty(vault / "mk/test.mk")
    registry_text = read_text_or_empty(vault / "ops/test-lane-registry.json")
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
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            "tools/ruff_strict_preview.py",
            "mk/static.mk",
        )
    )
    if (
        "RUFF_STRICT_PREVIEW_TARGETS" in surface_text
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
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
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
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    docs_text = read_text_or_empty(vault / "docs/development.md")
    if "uv lock --check" in docs_text and "uv.lock" in docs_text:
        return "implemented"
    return "requires_release_run_verification"


def strict_preview_all_target_audit_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
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


def goal_contract_schema_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    if goal_contract_is_bounded(contract):
        return "implemented"
    return "requires_release_run_verification"


def codex_goal_adapter_status(vault: Path, existing_count: int, expected_count: int) -> str:
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    goal_backend = as_dict(contract.get("goal_backend"))
    storage_path = str(goal_backend.get("storage_path", "")).strip()
    if goal_contract_is_bounded(contract) and (
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
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    report = load_json_object(vault / "ops/reports/codex-goal-prompt.json")
    goal_contract = as_dict(report.get("goal_contract"))
    prompt = as_dict(report.get("prompt"))
    promotion_guard = as_dict(report.get("promotion_guard"))
    contract_digest = current_contract_digest(vault)
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
    status = all_evidence_status(existing_count, expected_count)
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
        goal_contract_is_bounded(contract)
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
    status = all_evidence_status(existing_count, expected_count)
    if status:
        return status
    report = load_json_object(vault / "ops/reports/goal-run-status.json")
    goal = as_dict(report.get("goal"))
    backend = as_dict(goal.get("backend"))
    artifacts = as_dict(report.get("artifacts"))
    health = as_dict(report.get("health"))
    runtime_certificate = as_dict(report.get("runtime_certificate"))
    contract_digest = goal_status_contract_digest(vault, goal)
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
    noncertifiable_closed_failure_state = bool(
        report.get("status") == "attention"
        and health.get("promotion_status") == "allowed"
        and health.get("can_promote_result") is True
        and runtime_certificate.get("status") == "pending"
        and runtime_certificate.get("certificate_status") == "unverified"
        and runtime_certificate.get("mode") == "self_improvement_loop"
        and goal_runtime_certificate_noncertifiable_closed_failure(vault, report)
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
        and (
            blocked_pending_state
            or noncertifiable_closed_failure_state
            or verified_completed_state
        )
        and runtime_certificate.get("mode") == "self_improvement_loop"
    ):
        return "implemented"
    return "requires_release_run_verification"


def goal_execution_runtime_certificate_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
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
    status = all_evidence_status(existing_count, expected_count)
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
    status = all_evidence_status(existing_count, expected_count)
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
    artifact_freshness_status = str(artifact_freshness.get("status", "")).strip()
    selected_gate_active = selected_status == "pass" or (
        selected_status == "fail"
        and "promotion_blocked_by_selected_contract_failure" in blocker_ids
    )
    if (
        readiness.get("artifact_kind") == "auto_improve_readiness_report"
        and test_summary.get("artifact_kind") == "test_execution_summary"
        and selected_contract.get("path") == "ops/reports/test-execution-summary.json"
        and selected_gate_active
        and artifact_freshness_status in {"pass", "attention", "fail"}
    ):
        return "implemented"
    return "requires_release_run_verification"


def git_worktree_goal_guard_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    status = all_evidence_status(existing_count, expected_count)
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
    status = all_evidence_status(existing_count, expected_count)
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
        read_text_or_empty(vault / rel_path)
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


def artifact_freshness_performance_observability_reason_ids(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> list[str]:
    reasons: list[str] = []
    if existing_count < expected_count:
        reasons.append("artifact_freshness_observability_evidence_incomplete")
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            "ops/scripts/core/artifact_freshness_runtime.py",
            "tests/test_artifact_freshness_runtime.py",
            "mk/artifact.mk",
        )
    )
    checks = {
        "artifact_freshness_context_missing": "ArtifactFreshnessContext" not in surface_text,
        "artifact_freshness_schema_cache_missing": not any(
            token in surface_text
            for token in (
                "schema_cache",
                "validator_cache",
                "compiled_validator_cache",
            )
        ),
        "artifact_freshness_jsonl_progress_missing": not ("--progress" in surface_text and "jsonl" in surface_text),
        "artifact_freshness_phase_timing_missing": not any(
            token in surface_text
            for token in (
                "phase_timing",
                "phase_timings",
                "elapsed_seconds",
                "per_phase_timing",
            )
        ),
    }
    reasons.extend(reason_id for reason_id, failed in checks.items() if failed)
    report = load_json_object(vault / "ops/reports/artifact-freshness-report.json")
    if not report:
        reasons.append("artifact_freshness_report_missing")
    elif report.get("status") != "pass":
        summary = as_dict(report.get("summary"))
        stale_artifact_count = as_int(summary.get("stale_artifact_count"))
        operational_attention_count = as_int(
            summary.get("operational_attention_artifact_count")
        )
        stale_routing = as_dict(report.get("stale_routing"))
        is_source_identity_resettle = (
            stale_artifact_count
            and stale_routing.get("classification") == "source_identity_only"
        )
        if is_source_identity_resettle:
            reasons.append("artifact_freshness_source_identity_resettle")
        elif max(0, stale_artifact_count - operational_attention_count):
            reasons.append("artifact_freshness_stale_canonical_reports")
        if operational_attention_count and not is_source_identity_resettle:
            reasons.append("artifact_freshness_operational_attention")
        if as_int(summary.get("stable_contract_debt_artifact_count")):
            reasons.append("artifact_freshness_stable_contract_debt")
        if not any(reason_id.startswith("artifact_freshness_") for reason_id in reasons):
            reasons.append(f"artifact_freshness_report_status_{_reason_token(report.get('status'))}")
    return _dedupe_reason_ids(reasons)


def repo_boundary_history_hygiene_status(vault: Path, existing_count: int, expected_count: int) -> str:
    if existing_count == 0:
        return "planned"
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
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


def repository_surface_entrypoint_documentation_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> str:
    if existing_count == 0:
        return "planned"
    text = read_text_or_empty(vault / "docs/repository-surfaces.md")
    linked_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            "docs/README.md",
            "README.md",
            "ARCHITECTURE.md",
            "docs/public-mirror.md",
            "docs/release.md",
        )
    )
    required_tokens = (
        "Full local vault",
        "Public mirror",
        "Release source ZIP",
        "ops/scripts/public/public_surface_policy.py",
        "make public-export",
        "make release-run-ready",
        "build/release/",
        "AGENTS.local.md",
    )
    if (
        existing_count == expected_count
        and all(token in text for token in required_tokens)
        and "repository-surfaces.md" in linked_text
    ):
        return "implemented"
    return "partially_automated"


def release_mechanism_service_layer_extraction_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count != expected_count or not release_authority_service_complete(vault):
        return "partially_automated"
    complete_service_family = all(
        (
            release_currentness_service_complete(vault),
            release_risk_service_complete(vault),
            learning_claim_service_complete(vault),
        )
    )
    return "implemented" if complete_service_family else "partially_automated"


def github_native_security_automation_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    workflow_text = "\n".join(
        read_text_or_empty(vault / rel_path)
        for rel_path in (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            ".github/workflows/codeql.yml",
            ".github/workflows/dependency-review.yml",
        )
    )
    has_dependabot = (vault / ".github/dependabot.yml").is_file()
    has_codeql = "github/codeql-action" in workflow_text or "codeql" in read_text_or_empty(
        vault / ".github/workflows/codeql.yml"
    ).lower()
    has_dependency_review = "actions/dependency-review-action" in workflow_text
    has_concurrency = "concurrency:" in workflow_text
    external_uses = re.findall(r"uses:\s+([^\s#]+)", workflow_text)
    pinned_uses = [
        use
        for use in external_uses
        if re.search(r"@[0-9a-f]{40}\b", use) or use.startswith(("./", "docker://sha256:"))
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


def generated_artifact_tracking_policy_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    surface_text = "\n".join(
        read_text_or_empty(vault / rel_path)
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
    tracking_policy = report.get("tracking_policy")
    tracking_policy_ok = (
        isinstance(tracking_policy, dict)
        and str(tracking_policy.get("policy_id", "")).strip() == "generated_artifact_tracking_policy"
    )
    currentness = report.get("currentness")
    currentness_ok = (
        isinstance(currentness, dict) and str(currentness.get("status", "")).strip() == "current"
    )
    if (
        existing_count == expected_count
        and report.get("artifact_kind") == "generated_artifact_index_report"
        and report.get("producer") == "ops.scripts.generated_artifact_index"
        and tracking_policy_ok
        and currentness_ok
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
    if existing_count < expected_count:
        return "partially_automated"
    return (
        "implemented"
        if not supply_chain_external_verification_reason_ids(vault)
        else "partially_automated"
    )


def supply_chain_external_verification_reason_ids(vault: Path) -> list[str]:
    gate = load_json_object(vault / "ops/reports/supply-chain-gate-report.json")
    sbom = load_json_object(vault / "ops/reports/sbom-readiness-gate-report.json")
    in_toto = load_json_object(vault / "ops/reports/in-toto-statement.json")
    sigstore = load_json_object(vault / "ops/reports/sigstore-bundle-verification.json")
    has_slsa_predicate = in_toto.get("predicateType") == "https://slsa.dev/provenance/v1"
    sigstore_checks = [
        as_dict(check) for check in as_list(sigstore.get("verification_checks"))
    ]
    sigstore_bundle_ref = str(sigstore.get("bundle_ref") or "").strip()
    release_uses = workflow_uses_entries(vault, ".github/workflows/release.yml")
    dependency_review_uses = workflow_uses_entries(
        vault, ".github/workflows/dependency-review.yml"
    )
    has_release_attestation = any(
        use.startswith("actions/attest-build-provenance@") for use in release_uses
    )
    has_dependency_review = any(
        use.startswith("actions/dependency-review-action@")
        for use in dependency_review_uses
    )
    has_sigstore_bundle_target = make_target_exists(
        vault, "mk/supply_chain.mk", "sigstore-bundle"
    )
    external_bundle_checks = [
        check
        for check in sigstore_checks
        if check.get("rule") == "external_bundle_observed"
    ]
    external_bundle_rule_present = bool(external_bundle_checks)
    external_bundle_observed = any(
        check.get("pass") is True for check in external_bundle_checks
    )
    sigstore_check_failed = any(check.get("pass") is not True for check in sigstore_checks)
    local_sigstore_check_failed = any(
        check.get("pass") is not True
        for check in sigstore_checks
        if not str(check.get("rule", "")).startswith("external_bundle_")
    )
    reasons: list[str] = []
    if gate.get("status") != "pass":
        reasons.append("supply_chain_gate_not_pass")
    if sbom.get("status") != "pass":
        reasons.append("supply_chain_sbom_readiness_not_pass")
    if not has_slsa_predicate:
        reasons.append("supply_chain_slsa_predicate_missing")
    if sigstore.get("status") == "local-integrity-only":
        reasons.append("supply_chain_sigstore_local_integrity_only")
    elif sigstore.get("status") != "verified-external-bundle":
        reasons.append("supply_chain_sigstore_external_bundle_not_verified")
    if not sigstore_checks:
        reasons.append("supply_chain_sigstore_checks_missing")
    elif local_sigstore_check_failed or (sigstore_bundle_ref and sigstore_check_failed):
        reasons.append("supply_chain_sigstore_check_failed")
    if not sigstore_bundle_ref:
        reasons.append("supply_chain_sigstore_bundle_ref_missing")
    if not external_bundle_rule_present:
        reasons.append("supply_chain_external_bundle_rule_missing")
    elif not external_bundle_observed:
        reasons.append("supply_chain_external_bundle_not_observed")
    if not has_release_attestation:
        reasons.append("supply_chain_release_attestation_missing")
    if not has_dependency_review:
        reasons.append("supply_chain_dependency_review_missing")
    if not has_sigstore_bundle_target:
        reasons.append("supply_chain_sigstore_bundle_target_missing")
    return _dedupe_reason_ids(reasons)


def github_governance_live_drift_verification_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return (
        "implemented"
        if not github_governance_live_drift_verification_reason_ids(vault)
        else "partially_automated"
    )


def github_governance_live_drift_verification_reason_ids(vault: Path) -> list[str]:
    reasons: list[str] = []
    if not (vault / ".github/release-governance.yml").is_file():
        reasons.append("github_live_governance_checklist_missing")
    report = load_json_object(vault / "ops/reports/github-governance-live-drift.json")
    if not report:
        reasons.append("github_live_governance_operator_evidence_missing")
    elif report.get("status") != "pass":
        reasons.append("github_live_governance_operator_evidence_not_pass")
    return _dedupe_reason_ids(reasons)


def collaboration_governance_surface_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return (
        "implemented"
        if not collaboration_governance_surface_reason_ids(vault)
        else "partially_automated"
    )


def collaboration_governance_surface_reason_ids(vault: Path) -> list[str]:
    codeowners = read_text_or_empty(vault / ".github/CODEOWNERS")
    pr_template = read_text_or_empty(vault / ".github/pull_request_template.md")
    contributing = read_text_or_empty(vault / "CONTRIBUTING.md")
    reasons: list[str] = []
    if not has_codeowners_review_owner(codeowners):
        reasons.append("collaboration_governance_codeowners_review_owner_missing")
    if not has_pr_review_section(pr_template):
        reasons.append("collaboration_governance_pr_template_review_missing")
    if not has_contributing_commit_governance_policy(contributing):
        reasons.append("collaboration_governance_contributing_policy_missing")
    return reasons


def single_source_status(vault: Path) -> str:
    source_paths = (
        vault / "Makefile",
        vault / FIXED_POINT_POLICY_PATH,
        vault / WORKFLOW_ORDER_SPEC_PATH,
    )
    existing_count = sum(path.is_file() for path in source_paths)
    if existing_count == 0:
        return "planned"
    if existing_count != len(source_paths):
        return "partially_automated"
    try:
        contract = release_writer_single_source_contract(vault)
    except (OSError, ValueError, json.JSONDecodeError):
        return "partially_automated"
    if contract.get("status") == "pass":
        return "implemented"
    return "partially_automated"


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


StatusResolver = Callable[[Path], str]


def external_report_lifecycle_status(vault: Path) -> str:
    alignment = reference_manifest_alignment(vault)
    if alignment["status"] == "current":
        return "implemented"
    if (vault / REFERENCE_MANIFEST).exists():
        return "partially_automated"
    return "planned"


def operator_only_external_report_binary_status(vault: Path) -> str:
    if any(is_binary_report_path(path) for path in active_report_paths(vault)):
        return "planned"
    return "implemented"


STATUS_RESOLVERS: dict[str, StatusResolver] = {
    "release_writer_dependency_single_source": single_source_status,
    "outcome_provenance_gate_policy": lambda vault: json_report_status(
        vault / "ops/reports/outcome-provenance-gate-policy.json"
    ),
    "external_report_lifecycle": external_report_lifecycle_status,
    "operator_only_external_report_binary": operator_only_external_report_binary_status,
    "active_report_manifest_freshness": active_report_manifest_freshness_status,
    "release_lane_mutability_split": release_lane_mutability_split_status,
    "sealed_summary_vocabulary_demotion": sealed_summary_vocabulary_demotion_status,
    "selector_marker_scope_parity": selector_marker_scope_parity_status,
}

COUNT_STATUS_RESOLVERS: dict[str, CountStatusResolver] = {
    "source_package_distribution_binding": _release_verified_count_status(
        "source_package_distribution_binding"
    ),
    "release_evidence_bundle_and_attestation": _release_verified_count_status(
        "release_evidence_bundle_and_attestation"
    ),
    "full_suite_evidence_currentness": _release_verified_count_status(
        "full_suite_evidence_currentness"
    ),
    "promotion_truth_ladder": _release_verified_count_status("promotion_truth_ladder"),
    "source_revision_unknown_canonical_reports": source_revision_unknown_canonical_reports_status,
    "codex_exec_dependency_preflight_trust_boundary": (
        codex_exec_dependency_preflight_trust_boundary_status
    ),
    "bootstrap_dev_install_hardening": bootstrap_dev_install_hardening_status,
    "release_manifest_path_classification": release_manifest_path_classification_status,
    "ruff_strict_preview_import_order": ruff_strict_preview_import_order_status,
    "release_source_ready_deindex_hardening": release_source_ready_deindex_hardening_status,
    "uv_lock_canonical_policy": uv_lock_canonical_policy_status,
    "operator_entrypoint_index": operator_entrypoint_index_status,
    "strict_preview_all_target_audit": strict_preview_all_target_audit_status,
    "command_heartbeat_observability": command_heartbeat_observability_status,
    "sealed_preflight_canonicalization": sealed_preflight_canonicalization_status,
    "goal_contract_schema": goal_contract_schema_status,
    "codex_goal_adapter": codex_goal_adapter_status,
    "codex_goal_prompt_generator": codex_goal_prompt_generator_status,
    "auto_improve_goal_contract_input": auto_improve_goal_contract_input_status,
    "goal_run_status_audit_resume": goal_run_status_audit_resume_status,
    "goal_execution_runtime_certificate": goal_execution_runtime_certificate_status,
    "goal_executor_backoff_observability": goal_executor_backoff_observability_status,
    "repository_surface_entrypoint_documentation": repository_surface_entrypoint_documentation_status,
    "release_mechanism_service_layer_extraction": release_mechanism_service_layer_extraction_status,
    "selected_contract_currentness_gate": selected_contract_currentness_gate_status,
    "git_worktree_goal_guard": git_worktree_goal_guard_status,
    "goal_runtime_transient_cleanup_gate": goal_runtime_transient_cleanup_gate_status,
    "artifact_freshness_performance_observability": artifact_freshness_performance_observability_status,
    "repo_boundary_history_hygiene": repo_boundary_history_hygiene_status,
    "github_native_security_automation": github_native_security_automation_status,
    "maintainability_hotspot_refactor_backlog": maintainability_hotspot_refactor_backlog_status,
    "generated_artifact_tracking_policy": generated_artifact_tracking_policy_status,
    "public_export_negative_assertions": public_export_negative_assertions_status,
    "supply_chain_external_verification": supply_chain_external_verification_status,
    "github_governance_live_drift_verification": (
        github_governance_live_drift_verification_status
    ),
    "collaboration_governance_surface": collaboration_governance_surface_status,
}
