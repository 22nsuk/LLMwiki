from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.core.release_authority_state_runtime import (
    current_release_manifest_pass,
    release_authority_reports_verified,
    release_status_v2_view_with_readiness_fallback,
)

from .external_report_action_catalog import (
    ACTION_CATALOG,
    ALL_EVIDENCE_OR_PLANNED_ACTION_IDS,
    IMPLEMENTED_ARTIFACT_ACTIONS,
    ROADMAP_SOURCE_ONLY_ACTION_IDS,
    SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS,
    SPRINT_PRIORITIES,
)
from .external_report_action_lifecycle_runtime import (
    ACTION_LIFECYCLE_CURRENTLY_VALID,
    ACTION_LIFECYCLE_HISTORICALLY_TRUE,
    ACTION_LIFECYCLE_RESOLVED,
    ACTION_LIFECYCLE_SUPERSEDED,
    ACTION_LIFECYCLES,
    canonical_artifact_freshness_state,
    classify_external_report_action_lifecycle,
    external_report_action_lifecycle_record,
    external_report_action_lifecycle_summary,
)
from .external_report_inventory_runtime import (
    ARCHIVE_STATUS_RE,
    BINARY_REPORT_EXTENSIONS,
    COVERAGE_MARKER_PATTERNS,
    NARRATIVE_REPORT_EXTENSIONS,
    REFERENCE_MANIFEST,
    REFERENCE_MANIFEST_EXTENSIONS,
    REPORT_EXTENSIONS,
    SUPERSEDED_BY_RE,
    active_reference_report_paths,
    active_report_paths,
    archived_report_count,
    archived_report_paths,
    as_dict,
    as_int,
    as_list,
    content_sha256,
    coverage_markers,
    is_binary_report_path,
    load_json_object,
    matched_actions,
    priority_counts,
    reference_manifest_alignment,
    report_text,
    report_type_for_path,
    unmatched_recommendation_count,
)
from .external_report_lifecycle_maintainability_runtime import (
    maintainability_hotspot_refactor_backlog_reason_ids,
    maintainability_hotspot_refactor_backlog_status,
)
from .external_report_lifecycle_operator_runtime import operator_entrypoint_index_status
from .external_report_lifecycle_profile_runtime import (
    archived_report_action_basis_records,
    content_lifecycle_inventory,
    coverage_action_basis,
    coverage_archive_decision_code,
    coverage_with_action_basis,
    lifecycle_decision,
    report_coverage_item,
    report_lifecycle_profiles,
)
from .external_report_lifecycle_status_decision_runtime import (
    COUNT_STATUS_RESOLVERS,
    STATUS_RESOLVERS,
    active_report_manifest_freshness_status,
    artifact_freshness_performance_observability_reason_ids,
    artifact_freshness_performance_observability_status,
    auto_improve_goal_contract_input_status,
    codex_goal_adapter_status,
    codex_goal_prompt_generator_status,
    collaboration_governance_surface_reason_ids,
    collaboration_governance_surface_status,
    command_heartbeat_observability_status,
    external_report_lifecycle_status,
    generated_artifact_tracking_policy_status,
    git_worktree_goal_guard_status,
    github_governance_live_drift_verification_reason_ids,
    github_governance_live_drift_verification_status,
    github_native_security_automation_status,
    goal_contract_schema_status,
    goal_execution_runtime_certificate_status,
    goal_executor_backoff_observability_status,
    goal_run_status_audit_resume_status,
    goal_runtime_transient_cleanup_gate_status,
    operator_only_external_report_binary_status,
    public_export_negative_assertions_status,
    release_lane_mutability_split_status,
    release_mechanism_service_layer_extraction_status,
    release_source_ready_deindex_hardening_status,
    repo_boundary_history_hygiene_status,
    repository_surface_entrypoint_documentation_status,
    roadmap_source_only_status,
    ruff_strict_preview_import_order_status,
    sealed_preflight_canonicalization_status,
    sealed_summary_vocabulary_demotion_status,
    selected_contract_currentness_gate_status,
    selector_marker_scope_parity_status,
    single_source_status,
    source_revision_unknown_canonical_reports_status,
    strict_preview_all_target_audit_status,
    supply_chain_external_verification_reason_ids,
    supply_chain_external_verification_status,
    uv_lock_canonical_policy_status,
)
from .external_report_lifecycle_status_loader_runtime import (
    goal_runtime_certificate_noncertifiable_closed_failure as _goal_runtime_certificate_noncertifiable_closed_failure,
    goal_status_contract_digest as _goal_status_contract_digest,
    implemented_artifact_report as _implemented_artifact_report,
)
from .external_report_release_verification_runtime import (
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID,
    RELEASE_VERIFIED_ACTION_RESOLVERS,
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID,
    CountStatusResolver,
    _dedupe_reason_ids,
    _evidence_reason_ids,
    _reason_token,
    _status_with_archive_reconciliation_observations,
    archive_reconciliation_observation_inventory,
    archive_reconciliation_observation_paths,
    archive_reconciliation_observation_reason_ids,
    full_suite_evidence_currentness_verified,
    promotion_truth_ladder_verified,
    release_evidence_bundle_and_attestation_verified,
    release_run_verified,
    release_verified_action_reason_ids,
    release_verified_action_status,
    source_package_distribution_binding_verified,
)

_ACTION_LIFECYCLE_COMPAT_EXPORTS = (
    ACTION_LIFECYCLE_CURRENTLY_VALID,
    ACTION_LIFECYCLE_HISTORICALLY_TRUE,
    ACTION_LIFECYCLE_RESOLVED,
    ACTION_LIFECYCLE_SUPERSEDED,
    ACTION_LIFECYCLES,
    canonical_artifact_freshness_state,
    classify_external_report_action_lifecycle,
    external_report_action_lifecycle_record,
    external_report_action_lifecycle_summary,
)
_ACTION_CATALOG_COMPAT_EXPORTS = (
    ACTION_CATALOG,
    ALL_EVIDENCE_OR_PLANNED_ACTION_IDS,
    IMPLEMENTED_ARTIFACT_ACTIONS,
    ROADMAP_SOURCE_ONLY_ACTION_IDS,
    SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS,
    SPRINT_PRIORITIES,
)
_INVENTORY_COMPAT_EXPORTS = (
    ARCHIVE_STATUS_RE,
    BINARY_REPORT_EXTENSIONS,
    COVERAGE_MARKER_PATTERNS,
    NARRATIVE_REPORT_EXTENSIONS,
    REFERENCE_MANIFEST,
    REFERENCE_MANIFEST_EXTENSIONS,
    REPORT_EXTENSIONS,
    SUPERSEDED_BY_RE,
    active_reference_report_paths,
    active_report_paths,
    archived_report_count,
    archived_report_paths,
    as_dict,
    as_int,
    as_list,
    content_sha256,
    coverage_markers,
    is_binary_report_path,
    load_json_object,
    matched_actions,
    priority_counts,
    reference_manifest_alignment,
    report_type_for_path,
    report_text,
    unmatched_recommendation_count,
)
_PROFILE_COMPAT_EXPORTS = (
    archived_report_action_basis_records,
    content_lifecycle_inventory,
    coverage_action_basis,
    coverage_archive_decision_code,
    coverage_with_action_basis,
    lifecycle_decision,
    report_coverage_item,
    report_lifecycle_profiles,
)
_RELEASE_VERIFICATION_COMPAT_EXPORTS = (
    release_status_v2_view_with_readiness_fallback,
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID,
    RELEASE_VERIFIED_ACTION_RESOLVERS,
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID,
    CountStatusResolver,
    archive_reconciliation_observation_inventory,
    archive_reconciliation_observation_paths,
    archive_reconciliation_observation_reason_ids,
    full_suite_evidence_currentness_verified,
    promotion_truth_ladder_verified,
    release_evidence_bundle_and_attestation_verified,
    release_run_verified,
    release_verified_action_reason_ids,
    release_verified_action_status,
    source_package_distribution_binding_verified,
)
_STATUS_DECISION_COMPAT_EXPORTS = (
    COUNT_STATUS_RESOLVERS,
    STATUS_RESOLVERS,
    active_report_manifest_freshness_status,
    artifact_freshness_performance_observability_reason_ids,
    artifact_freshness_performance_observability_status,
    auto_improve_goal_contract_input_status,
    codex_goal_adapter_status,
    codex_goal_prompt_generator_status,
    collaboration_governance_surface_reason_ids,
    collaboration_governance_surface_status,
    command_heartbeat_observability_status,
    external_report_lifecycle_status,
    generated_artifact_tracking_policy_status,
    git_worktree_goal_guard_status,
    github_governance_live_drift_verification_reason_ids,
    github_governance_live_drift_verification_status,
    github_native_security_automation_status,
    goal_contract_schema_status,
    goal_execution_runtime_certificate_status,
    goal_executor_backoff_observability_status,
    goal_run_status_audit_resume_status,
    goal_runtime_transient_cleanup_gate_status,
    maintainability_hotspot_refactor_backlog_status,
    operator_entrypoint_index_status,
    operator_only_external_report_binary_status,
    public_export_negative_assertions_status,
    release_lane_mutability_split_status,
    release_mechanism_service_layer_extraction_status,
    release_source_ready_deindex_hardening_status,
    repo_boundary_history_hygiene_status,
    repository_surface_entrypoint_documentation_status,
    roadmap_source_only_status,
    ruff_strict_preview_import_order_status,
    sealed_preflight_canonicalization_status,
    sealed_summary_vocabulary_demotion_status,
    selector_marker_scope_parity_status,
    selected_contract_currentness_gate_status,
    single_source_status,
    source_revision_unknown_canonical_reports_status,
    strict_preview_all_target_audit_status,
    supply_chain_external_verification_reason_ids,
    supply_chain_external_verification_status,
    uv_lock_canonical_policy_status,
)


def external_report_release_authority_reports_verified(vault: Path) -> bool:
    closeout = load_json_object(vault / "ops/reports/release-closeout-summary.json")
    dashboard = load_json_object(vault / "ops/reports/release-evidence-dashboard.json")
    return release_authority_reports_verified(closeout=closeout, dashboard=dashboard)


def external_report_current_release_manifest_pass(
    vault: Path,
    rel_path: str,
    artifact_kind: str,
) -> bool:
    return current_release_manifest_pass(vault, rel_path, artifact_kind)


def _collect_action_evidence(
    vault: Path, action: dict[str, Any]
) -> tuple[list[dict[str, Any]], int, int]:
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
    return evidence, existing_count, len(action["evidence_paths"])


def _implemented_artifact_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
    *,
    rel_path: str,
    artifact_kind: str,
) -> str:
    if existing_count == expected_count and _implemented_artifact_report(
        vault, rel_path, artifact_kind
    ):
        return "implemented"
    if existing_count:
        return "partially_automated"
    return "planned"


def _default_evidence_status(existing_count: int, expected_count: int) -> str:
    if existing_count == expected_count:
        return "requires_release_run_verification"
    if existing_count:
        return "partially_automated"
    return "planned"


def _resolve_action_status(
    vault: Path,
    action_id: str,
    *,
    existing_count: int,
    expected_count: int,
) -> str:
    if action_id in STATUS_RESOLVERS:
        return STATUS_RESOLVERS[action_id](vault)
    if action_id in COUNT_STATUS_RESOLVERS:
        return COUNT_STATUS_RESOLVERS[action_id](vault, existing_count, expected_count)
    if action_id in ROADMAP_SOURCE_ONLY_ACTION_IDS:
        return roadmap_source_only_status(existing_count, expected_count)
    if action_id in ALL_EVIDENCE_OR_PLANNED_ACTION_IDS:
        return "implemented" if existing_count == expected_count else "planned"
    if action_id in IMPLEMENTED_ARTIFACT_ACTIONS:
        rel_path, artifact_kind = IMPLEMENTED_ARTIFACT_ACTIONS[action_id]
        return _implemented_artifact_status(
            vault,
            existing_count,
            expected_count,
            rel_path=rel_path,
            artifact_kind=artifact_kind,
        )
    return _default_evidence_status(existing_count, expected_count)


def status_from_evidence(
    vault: Path, action: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    evidence, existing_count, expected_count = _collect_action_evidence(vault, action)
    action_id = str(action["action_id"])
    status = _resolve_action_status(
        vault,
        action_id,
        existing_count=existing_count,
        expected_count=expected_count,
    )
    status = _status_with_archive_reconciliation_observations(vault, action_id, status)
    return status, evidence


def goal_execution_runtime_certificate_reason_ids(vault: Path) -> list[str]:
    report = load_json_object(vault / "ops/reports/goal-runtime-certificate.json")
    if not report:
        return ["goal_runtime_certificate_missing"]
    certificate = as_dict(report.get("certificate"))
    run = as_dict(report.get("run"))
    run_artifacts = as_dict(report.get("run_artifacts"))
    session_evidence = as_dict(report.get("session_evidence"))
    command_observability = as_dict(report.get("command_observability"))
    contract_update = as_dict(report.get("contract_update"))
    reasons: list[str] = []
    if report.get("status") != "pass":
        reasons.append("goal_runtime_certificate_not_pass")
    if certificate.get("target_runtime_mode") != "self_improvement_loop":
        reasons.append("goal_runtime_certificate_wrong_runtime_mode")
    if certificate.get("verification_status") not in {"eligible", "already_verified"}:
        reasons.append("goal_runtime_certificate_not_eligible")
    if certificate.get("eligible") is not True:
        reasons.append("goal_runtime_certificate_eligible_false")
    if run.get("run_status") != "completed":
        reasons.append("goal_runtime_run_not_completed")
    if run.get("run_runtime_mode") != "self_improvement_loop":
        reasons.append("goal_runtime_run_wrong_runtime_mode")
    if run_artifacts.get("status") != "clean":
        reasons.append("goal_runtime_run_artifacts_not_clean")
    if session_evidence.get("status") != "clean":
        reasons.append("goal_runtime_session_evidence_not_clean")
    if command_observability.get("status") != "clean":
        reasons.append("goal_runtime_command_observability_not_clean")
    if contract_update.get("runtime_certificate_verified_after") is not True:
        reasons.append("goal_runtime_contract_not_marked_verified")
    reasons.extend(
        f"goal_runtime_certificate_blocker:{_reason_token(blocker)}"
        for blocker in as_list(report.get("blockers"))
    )
    return _dedupe_reason_ids(reasons)


def goal_run_status_audit_resume_reason_ids(vault: Path) -> list[str]:
    report = load_json_object(vault / "ops/reports/goal-run-status.json")
    if not report:
        return ["goal_run_status_missing"]
    goal = as_dict(report.get("goal"))
    backend = as_dict(goal.get("backend"))
    artifacts = as_dict(report.get("artifacts"))
    health = as_dict(report.get("health"))
    runtime_certificate = as_dict(report.get("runtime_certificate"))
    contract_digest = _goal_status_contract_digest(vault, goal)
    status_report_path = str(artifacts.get("status_report_path", "")).strip()
    status_report_path_valid = (
        status_report_path == "ops/reports/goal-run-status.json"
        or (
            status_report_path.startswith("runs/goal-")
            and status_report_path.endswith("/state/goal-run-status.json")
        )
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
        and _goal_runtime_certificate_noncertifiable_closed_failure(vault, report)
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
    reasons: list[str] = []
    if report.get("artifact_kind") != "goal_run_status":
        reasons.append("goal_run_status_wrong_artifact_kind")
    if report.get("producer") != "ops.scripts.goal_run_status":
        reasons.append("goal_run_status_wrong_producer")
    if report.get("status") not in {"pass", "attention", "fail"}:
        reasons.append("goal_run_status_unrecognized_status")
    if not bool(backend.get("process_persistent")):
        reasons.append("goal_run_status_backend_not_process_persistent")
    if goal.get("contract_sha256") != contract_digest:
        reasons.append("goal_run_status_contract_digest_mismatch")
    if not status_report_path_valid:
        reasons.append("goal_run_status_report_path_invalid")
    if not paths_valid:
        reasons.append("goal_run_status_artifact_paths_invalid")
    if health.get("heartbeat_status") not in {"current", "stale"}:
        reasons.append("goal_run_status_heartbeat_invalid")
    if health.get("checkpoint_status") not in {"current", "stale"}:
        reasons.append("goal_run_status_checkpoint_invalid")
    if health.get("command_heartbeat_status") not in {
        "current",
        "stale",
        "not_recorded",
    }:
        reasons.append("goal_run_status_command_heartbeat_invalid")
    if health.get("backoff_status") not in {"inactive", "active", "expired"}:
        reasons.append("goal_run_status_backoff_invalid")
    if health.get("resume_status") not in {"not_requested", "ready"}:
        reasons.append("goal_run_status_resume_invalid")
    if not (
        blocked_pending_state
        or noncertifiable_closed_failure_state
        or verified_completed_state
    ):
        reasons.append("goal_run_status_promotion_state_invalid")
    if runtime_certificate.get("mode") != "self_improvement_loop":
        reasons.append("goal_run_status_wrong_runtime_mode")
    return _dedupe_reason_ids(reasons)


def action_status_reason_ids(
    vault: Path,
    action_id: str,
    status: str,
    evidence: list[dict[str, Any]],
    *,
    existing_count: int | None = None,
    expected_count: int | None = None,
) -> list[str]:
    if status == "implemented":
        return []
    reasons = _evidence_reason_ids(evidence)
    if action_id in RELEASE_VERIFIED_ACTION_RESOLVERS:
        reasons.extend(release_verified_action_reason_ids(vault, action_id))
    elif action_id == "maintainability_hotspot_refactor_backlog":
        reasons.extend(maintainability_hotspot_refactor_backlog_reason_ids(vault))
    elif action_id == "supply_chain_external_verification":
        reasons.extend(supply_chain_external_verification_reason_ids(vault))
    elif action_id == "github_governance_live_drift_verification":
        reasons.extend(github_governance_live_drift_verification_reason_ids(vault))
    elif action_id == "collaboration_governance_surface":
        reasons.extend(collaboration_governance_surface_reason_ids(vault))
    elif action_id == "goal_execution_runtime_certificate":
        reasons.extend(goal_execution_runtime_certificate_reason_ids(vault))
    elif action_id == "goal_run_status_audit_resume":
        reasons.extend(goal_run_status_audit_resume_reason_ids(vault))
    elif action_id == "artifact_freshness_performance_observability":
        reasons.extend(
            artifact_freshness_performance_observability_reason_ids(
                vault,
                existing_count
                if existing_count is not None
                else sum(1 for item in evidence if item.get("exists")),
                expected_count if expected_count is not None else len(evidence),
            )
        )
    reasons.extend(archive_reconciliation_observation_reason_ids(vault, action_id))
    if not reasons:
        reasons.append(status)
    return _dedupe_reason_ids(reasons)


def action_status_reason_details(
    reason_ids: list[str],
    *,
    fallback_target: str,
) -> list[dict[str, Any]]:
    from .external_report_lifecycle_reason_decision_runtime import (
        action_status_reason_details as resolve_action_status_reason_details,
    )

    return resolve_action_status_reason_details(
        reason_ids,
        fallback_target=fallback_target,
    )


def action_statuses(vault: Path) -> dict[str, str]:
    return {
        str(action["action_id"]): status_from_evidence(vault, action)[0]
        for action in ACTION_CATALOG
    }
