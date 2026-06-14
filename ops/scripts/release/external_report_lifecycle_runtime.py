from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_CLAIM_BLOCKER,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
)
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.workflow_dependency_planner import (
    build_report as build_workflow_dependency_report,
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
from .external_report_release_verification_runtime import (
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID,
    RELEASE_VERIFIED_ACTION_RESOLVERS,
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID,
    CountStatusResolver,
    _dedupe_reason_ids,
    _evidence_reason_ids,
    _reason_detail,
    _reason_token,
    _release_verified_count_status,
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
from .release_workflow_order_guard import (
    build_report as build_release_workflow_order_guard_report,
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

ARCHIVE_RECONCILIATION_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID: (
        "external_report_reconciliation",
        "external_report_lifecycle",
        ["external-report-lifecycle-refresh", "external-report-action-matrix"],
    ),
    "status_surface_currentness_visibility_gap": (
        "operator_status_currentness",
        "status_surface",
        ["status", "artifact-freshness-refresh-check"],
    ),
    "dev_install_index_portability_gap": (
        "dependency_install_policy",
        "dependency_setup",
        ["dev-install", "uv-lock-check"],
    ),
    "github_governance_live_drift_gap": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID: (
        "review_bundle_hygiene",
        "review_archive",
        ["review-archive", "external-report-action-matrix"],
    ),
    "full_vault_archive_mtime_normalization_gap": (
        "archive_portability",
        "source_package",
        ["release-source-package-check", "release-smoke-fast"],
    ),
}
MAINTAINABILITY_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    "maintainability_hotspot_report_missing": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_report_kind_mismatch": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_report_producer_mismatch": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_report_not_pass": (
        "function_budget_refactor_proposals",
        "maintainability_report_evidence",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_candidates_remain": (
        "function_budget_candidate_closeout",
        "maintainability_candidate_backlog",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_proposals_not_absorbed": (
        "function_budget_proposal_absorption",
        "maintainability_proposal_absorption",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_owner_backlog_not_absorbed": (
        "function_budget_owner_backlog_absorption",
        "maintainability_owner_backlog",
        ["function-budget-refactor-proposals"],
    ),
    "maintainability_hotspot_large_main_remains": (
        "function_budget_large_main_closeout",
        "maintainability_large_main",
        ["function-budget-refactor-proposals"],
    ),
}
SUPPLY_CHAIN_EXTERNAL_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    "supply_chain_gate_not_pass": (
        "supply_chain_external_gate",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_sbom_readiness_not_pass": (
        "supply_chain_external_gate",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_slsa_predicate_missing": (
        "supply_chain_external_gate",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_sigstore_local_integrity_only": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_sigstore_external_bundle_not_verified": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_sigstore_checks_missing": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_sigstore_check_failed": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_sigstore_bundle_ref_missing": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_external_bundle_rule_missing": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_external_bundle_not_observed": (
        "supply_chain_external_bundle_verification",
        "supply_chain_external_verification",
        ["sigstore-bundle SIGSTORE_BUNDLE_REF=<bundle>"],
    ),
    "supply_chain_release_attestation_missing": (
        "supply_chain_external_workflow_verification",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_dependency_review_missing": (
        "supply_chain_external_workflow_verification",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
    "supply_chain_sigstore_bundle_target_missing": (
        "supply_chain_external_workflow_verification",
        "supply_chain_external_verification",
        ["supply-chain-check"],
    ),
}
REASON_PREFIX_TARGETS: tuple[tuple[tuple[str, ...], str, str, str, tuple[str, ...]], ...] = (
    (
        ("release_run_manifest_",),
        "release_run_ready",
        "release_run",
        "",
        ("release-run-ready-plan-check", "release-run-ready"),
    ),
    (
        ("release_sealed_run_manifest_",),
        "release_sealed_run_ready",
        "sealed_release",
        "",
        ("release-sealed-run-ready-plan", "release-sealed-run-ready"),
    ),
    (
        ("release_auto_promotion_ready_manifest_",),
        "release_auto_promotion_ready",
        "unattended_promotion",
        "",
        ("release-auto-promotion-ready-plan", "release-auto-promotion-ready"),
    ),
    (
        ("release_finality_", "release_closeout_fixed_point_"),
        "release_auto_promotion_preseal",
        "release_preseal",
        "",
        (
            "release-auto-promotion-preseal",
            "release-closeout-fixed-point",
            "release-closeout-finality-verify",
        ),
    ),
    (
        ("release_dashboard_", "release_authority_", "release_closeout_"),
        "release_auto_promotion_preseal",
        "release_preseal",
        "",
        ("release-auto-promotion-preseal", "release-evidence-dashboard"),
    ),
    (
        ("source_package_",),
        "release_source_package",
        "source_package",
        "",
        ("release-source-package-check",),
    ),
    (
        ("external_report_",),
        "external_report_reference_manifest",
        "external_report_lifecycle",
        "",
        ("external-report-reference-manifest-settle",),
    ),
    (
        ("collaboration_governance_",),
        "collaboration_governance",
        "github_governance",
        GATE_EFFECT_ADVISORY,
        ("collaboration-governance",),
    ),
    (
        ("full_suite_",),
        "release_run_ready",
        "release_run",
        "",
        ("test-execution-summary-full-current-or-refresh",),
    ),
    (
        ("goal_runtime_",),
        "goal_runtime_certificate",
        "unattended_promotion",
        GATE_EFFECT_CLAIM_BLOCKER,
        (
            "goal-runtime-certificate",
            "release-auto-promotion-goal-run-id-guard",
            "release-auto-promotion-ready-plan",
        ),
    ),
    (
        ("goal_run_status_",),
        "goal_runtime_status",
        "goal_runtime_status",
        GATE_EFFECT_CLAIM_BLOCKER,
        (
            "goal-run-status",
            "goal-runtime-reconcile",
        ),
    ),
)
REASON_EXACT_TARGETS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "release_auto_promotion_not_allowed": (
        "release_auto_promotion_ready",
        "unattended_promotion",
        "",
        ("release-auto-promotion-ready-plan", "release-auto-promotion-ready"),
    ),
    "release_unattended_promotion_not_allowed": (
        "release_auto_promotion_ready",
        "unattended_promotion",
        "",
        ("release-auto-promotion-ready-plan", "release-auto-promotion-ready"),
    ),
}
GITHUB_LIVE_GOVERNANCE_REASON_TARGETS: dict[str, tuple[str, str, list[str]]] = {
    "github_live_governance_checklist_missing": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
    "github_live_governance_operator_evidence_missing": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
    "github_live_governance_operator_evidence_not_pass": (
        "github_live_governance_verification",
        "github_live_governance",
        ["collaboration-governance"],
    ),
}



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


def _goal_status_contract_digest(vault: Path, goal: dict[str, Any]) -> str:
    contract_path = str(goal.get("contract_path", "")).strip()
    if contract_path == "ops/reports/codex-goal-contract.json" or (
        contract_path.startswith("runs/goal-")
        and contract_path.endswith("/state/codex-goal-contract.json")
    ):
        contract = load_json_object(vault / contract_path)
        return _canonical_json_digest(contract) if contract else ""
    return _current_contract_digest(vault)


def _goal_runtime_certificate_noncertifiable_closed_failure(
    vault: Path,
    goal_status_report: dict[str, Any],
) -> bool:
    certificate = load_json_object(vault / "ops/reports/goal-runtime-certificate.json")
    if (
        certificate.get("artifact_kind") != "goal_runtime_certificate"
        or certificate.get("producer") != "ops.scripts.goal_runtime_certificate_report"
    ):
        return False
    diagnosis = as_dict(certificate.get("diagnosis"))
    if diagnosis.get("certificate_failure_class") != "noncertifiable_closed_failure":
        return False
    run = as_dict(goal_status_report.get("run"))
    current_scope = as_dict(diagnosis.get("current_scope"))
    return bool(
        current_scope.get("run_id") == run.get("run_id")
        and current_scope.get("run_status") == run.get("status")
        and current_scope.get("runtime_mode") == run.get("runtime_mode")
    )


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


RELEASE_LANE_MUTABILITY_SPLIT_SURFACES = (
    "mk/release.mk",
    "mk/release-authority.mk",
    "mk/release-evidence.mk",
    "mk/release-learning.mk",
)


def release_lane_mutability_split_status(vault: Path) -> str:
    makefile_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
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
    contract_digest = _goal_status_contract_digest(vault, goal)
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


def artifact_freshness_performance_observability_reason_ids(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> list[str]:
    reasons: list[str] = []
    if existing_count < expected_count:
        reasons.append("artifact_freshness_observability_evidence_incomplete")
    surface_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
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
        if max(0, stale_artifact_count - operational_attention_count):
            reasons.append("artifact_freshness_stale_canonical_reports")
        if operational_attention_count:
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


def repository_surface_entrypoint_documentation_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> str:
    if existing_count == 0:
        return "planned"
    text = _read_text_or_empty(vault / "docs/repository-surfaces.md")
    linked_text = "\n".join(
        _read_text_or_empty(vault / rel_path)
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


def _contains_all(text: str, tokens: tuple[str, ...]) -> bool:
    return all(token in text for token in tokens)


def _release_authority_service_complete(vault: Path) -> bool:
    core_text = _read_text_or_empty(vault / "ops/scripts/core/release_authority_state_runtime.py")
    facade_text = _read_text_or_empty(vault / "ops/scripts/release/release_status_v2.py")
    mechanism_text = _read_text_or_empty(
        vault / "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py"
    )
    lifecycle_text = _read_text_or_empty(
        vault / "ops/scripts/release/external_report_lifecycle_runtime.py"
    )
    inventory_text = _read_text_or_empty(vault / "ops/scripts/release/release_authority_inventory.py")
    facade_uses_service = (
        "from ops.scripts.core.release_authority_state_runtime import" in facade_text
        or "from ops.scripts.core import release_authority_state_runtime" in facade_text
    )
    return _contains_all(
        core_text,
        (
            "release_status_v2_view",
            "machine_release_allowed_from_status_view",
            "clean_required_preflight_passes",
            "release_authority_reports_verified",
            "current_release_manifest_pass",
            "release_artifact_revision",
        ),
    ) and all(
        (
            facade_uses_service,
            "machine_release_allowed_from_status_view" in mechanism_text,
            "clean_required_preflight_passes" in mechanism_text,
            "release_authority_reports_verified" in lifecycle_text,
            "current_release_manifest_pass" in lifecycle_text,
            "release_artifact_revision" in inventory_text,
        )
    )


def _release_currentness_service_complete(vault: Path) -> bool:
    currentness_text = _read_text_or_empty(
        vault / "ops/scripts/core/release_currentness_state_runtime.py"
    )
    cohort_text = _read_text_or_empty(vault / "ops/scripts/release/release_evidence_cohort.py")
    dashboard_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard.py"
    )
    dashboard_status_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard_status_runtime.py"
    )
    closeout_gate_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_closeout_gate_runtime.py"
    )
    dashboard_uses_currentness_service = (
        "from ops.scripts.core.release_currentness_state_runtime import" in dashboard_text
        or "from ops.scripts.core.release_currentness_state_runtime import" in dashboard_status_text
    )
    dashboard_uses_live_rerun_state = (
        "live_rerun_state(" in dashboard_text
        or "live_rerun_state(" in dashboard_status_text
    )
    return _contains_all(
        currentness_text,
        ("def currentness_field", "def live_rerun_state", "def components_match_current_source_tree"),
    ) and all(
        (
            "from ops.scripts.core.release_currentness_state_runtime import" in cohort_text,
            "from ops.scripts.core.release_currentness_state_runtime import" in closeout_gate_text,
            dashboard_uses_currentness_service,
            dashboard_uses_live_rerun_state,
            "components_match_current_source_tree(" in closeout_gate_text,
        )
    )


def _release_risk_service_complete(vault: Path) -> bool:
    risk_text = _read_text_or_empty(vault / "ops/scripts/core/release_risk_state_runtime.py")
    closeout_risk_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_closeout_risk_runtime.py"
    )
    clean_blocker_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_clean_blocker_ledger.py"
    )
    return _contains_all(
        risk_text,
        (
            "def release_risk_identity",
            "def release_risk_blocks_clean_lane",
            "def release_risk_list",
            "def release_blocker_entry",
        ),
    ) and all(
        (
            "from ops.scripts.core.release_risk_state_runtime import" in closeout_risk_text,
            "from ops.scripts.core.release_risk_state_runtime import" in clean_blocker_text,
            "release_risk_identity(" in closeout_risk_text,
            "release_risk_blocks_clean_lane(" in clean_blocker_text,
        )
    )


def _learning_claim_service_complete(vault: Path) -> bool:
    learning_text = _read_text_or_empty(vault / "ops/scripts/core/learning_claim_state_runtime.py")
    dashboard_learning_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard_learning_delta_runtime.py"
    )
    unlock_text = _read_text_or_empty(
        vault / "ops/scripts/learning/learning_delta_scoreboard_unlock_runtime.py"
    )
    return _contains_all(
        learning_text,
        (
            "def confirmed_evidence_summary",
            "def confirmed_predicate_results",
            "def confirmed_blocking_predicate_ids",
            "def confirmed_wording_allowed",
        ),
    ) and all(
        (
            "from ops.scripts.core.learning_claim_state_runtime import" in dashboard_learning_text,
            "from ops.scripts.core.learning_claim_state_runtime import" in unlock_text,
            "confirmed_evidence_summary(" in dashboard_learning_text,
            "confirmed_evidence_summary(" in unlock_text,
        )
    )


def release_mechanism_service_layer_extraction_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count != expected_count or not _release_authority_service_complete(vault):
        return "partially_automated"
    complete_service_family = all(
        (
            _release_currentness_service_complete(vault),
            _release_risk_service_complete(vault),
            _learning_claim_service_complete(vault),
        )
    )
    return "implemented" if complete_service_family else "partially_automated"


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


def maintainability_hotspot_refactor_backlog_status(
    vault: Path, existing_count: int, expected_count: int
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return (
        "implemented"
        if not maintainability_hotspot_refactor_backlog_reason_ids(vault)
        else "partially_automated"
    )


def maintainability_hotspot_refactor_backlog_reason_ids(vault: Path) -> list[str]:
    report = load_json_object(vault / "ops/reports/function-budget-refactor-proposals.json")
    if not report:
        return ["maintainability_hotspot_report_missing"]
    summary = as_dict(report.get("summary"))
    proposal_count = as_int(summary.get("proposal_count"))
    candidate_count = as_int(summary.get("function_budget_candidate_count"))
    owner_backlog_count = as_int(summary.get("owner_backlog_count"))
    large_main_count = as_int(summary.get("large_main_without_tests_or_docs_count"))
    reasons: list[str] = []
    if report.get("artifact_kind") != "function_budget_refactor_proposals":
        reasons.append("maintainability_hotspot_report_kind_mismatch")
    if report.get("producer") != "ops.scripts.function_budget_refactor_proposals":
        reasons.append("maintainability_hotspot_report_producer_mismatch")
    if report.get("status") != "pass":
        reasons.append("maintainability_hotspot_report_not_pass")
    if candidate_count > 0:
        reasons.append("maintainability_hotspot_candidates_remain")
    if proposal_count > 0:
        reasons.append("maintainability_hotspot_proposals_not_absorbed")
    if owner_backlog_count > 0:
        reasons.append("maintainability_hotspot_owner_backlog_not_absorbed")
    if large_main_count > 0:
        reasons.append("maintainability_hotspot_large_main_remains")
    return _dedupe_reason_ids(reasons)


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
        and report.get("status") == "pass"
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


def _workflow_uses_entries(vault: Path, rel_path: str) -> list[str]:
    entries: list[str] = []
    for line in _read_text_or_empty(vault / rel_path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"-?\s*uses:\s+([^#\s]+)", stripped)
        if match:
            entries.append(match.group(1))
    return entries


def _make_target_exists(vault: Path, rel_path: str, target: str) -> bool:
    text = _read_text_or_empty(vault / rel_path)
    return bool(re.search(rf"(?m)^{re.escape(target)}\s*:", text))


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
    release_uses = _workflow_uses_entries(vault, ".github/workflows/release.yml")
    dependency_review_uses = _workflow_uses_entries(
        vault, ".github/workflows/dependency-review.yml"
    )
    has_release_attestation = any(
        use.startswith("actions/attest-build-provenance@") for use in release_uses
    )
    has_dependency_review = any(
        use.startswith("actions/dependency-review-action@")
        for use in dependency_review_uses
    )
    has_sigstore_bundle_target = _make_target_exists(
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
    elif sigstore_check_failed:
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


CODEOWNERS_OWNER_RE = re.compile(
    r"^@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?$"
)
MARKDOWN_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
PLACEHOLDER_TEXT_RE = re.compile(r"\b(?:placeholder|todo|tbd|example only)\b", re.IGNORECASE)
REVIEW_HEADING_RE = re.compile(r"\breviews?\b", re.IGNORECASE)
POLICY_LANGUAGE_RE = re.compile(
    r"\b(?:must|should|required|requires|policy|taxonomy|governance)\b",
    re.IGNORECASE,
)


def _has_codeowners_review_owner(text: str) -> bool:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or PLACEHOLDER_TEXT_RE.search(line):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if any(CODEOWNERS_OWNER_RE.fullmatch(owner) for owner in parts[1:]):
            return True
    return False


def _markdown_without_comments(text: str) -> str:
    return MARKDOWN_COMMENT_RE.sub("", text)


def _meaningful_markdown_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or PLACEHOLDER_TEXT_RE.search(stripped):
        return ""
    return stripped


def _has_pr_review_section(text: str) -> bool:
    in_review_section = False
    for raw_line in _markdown_without_comments(text).splitlines():
        line = _meaningful_markdown_line(raw_line)
        if not line:
            continue
        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            in_review_section = bool(REVIEW_HEADING_RE.search(heading.group(1)))
            continue
        if in_review_section:
            return True
    return False


def _has_contributing_commit_governance_policy(text: str) -> bool:
    in_commit_governance_section = False
    for raw_line in _markdown_without_comments(text).splitlines():
        line = _meaningful_markdown_line(raw_line)
        if not line:
            continue
        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            heading_text = heading.group(1).casefold()
            in_commit_governance_section = "commit" in heading_text and (
                "governance" in heading_text
                or "policy" in heading_text
                or "taxonomy" in heading_text
            )
            continue
        if in_commit_governance_section and POLICY_LANGUAGE_RE.search(line):
            return True
    return False


def collaboration_governance_surface_reason_ids(vault: Path) -> list[str]:
    codeowners = _read_text_or_empty(vault / ".github/CODEOWNERS")
    pr_template = _read_text_or_empty(vault / ".github/pull_request_template.md")
    contributing = _read_text_or_empty(vault / "CONTRIBUTING.md")
    reasons: list[str] = []
    if not _has_codeowners_review_owner(codeowners):
        reasons.append("collaboration_governance_codeowners_review_owner_missing")
    if not _has_pr_review_section(pr_template):
        reasons.append("collaboration_governance_pr_template_review_missing")
    if not _has_contributing_commit_governance_policy(contributing):
        reasons.append("collaboration_governance_contributing_policy_missing")
    return reasons


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
    if existing_count == expected_count and _implemented_artifact_report(vault, rel_path, artifact_kind):
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


def status_from_evidence(vault: Path, action: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
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
    if health.get("command_heartbeat_status") not in {"current", "stale", "not_recorded"}:
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
                existing_count if existing_count is not None else sum(1 for item in evidence if item.get("exists")),
                expected_count if expected_count is not None else len(evidence),
            )
        )
    reasons.extend(archive_reconciliation_observation_reason_ids(vault, action_id))
    if not reasons:
        reasons.append(status)
    return _dedupe_reason_ids(reasons)


def _target_reason_detail(
    reason_id: str,
    *,
    owning_stage: str,
    blocking_scope: str,
    recommended_targets: tuple[str, ...] | list[str],
    gate_effect: str = "",
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "owning_stage": owning_stage,
        "blocking_scope": blocking_scope,
        "recommended_targets": list(recommended_targets),
    }
    if gate_effect:
        kwargs["gate_effect"] = gate_effect
    return _reason_detail(reason_id, **kwargs)


def _prefix_reason_detail(reason_id: str) -> dict[str, Any] | None:
    if reason_id in REASON_EXACT_TARGETS:
        owning_stage, blocking_scope, gate_effect, recommended_targets = REASON_EXACT_TARGETS[
            reason_id
        ]
        return _target_reason_detail(
            reason_id,
            owning_stage=owning_stage,
            blocking_scope=blocking_scope,
            gate_effect=gate_effect,
            recommended_targets=recommended_targets,
        )
    for prefixes, owning_stage, blocking_scope, gate_effect, recommended_targets in (
        REASON_PREFIX_TARGETS
    ):
        if reason_id.startswith(prefixes):
            return _target_reason_detail(
                reason_id,
                owning_stage=owning_stage,
                blocking_scope=blocking_scope,
                gate_effect=gate_effect,
                recommended_targets=recommended_targets,
            )
    if reason_id.startswith("artifact_freshness_"):
        recommended_targets = ("artifact-freshness-refresh-check",)
        if reason_id == "artifact_freshness_stable_contract_debt":
            recommended_targets = (
                "artifact-freshness-stable-contract-debt-refresh",
                "artifact-freshness-refresh-check",
            )
        return _target_reason_detail(
            reason_id,
            owning_stage="artifact_freshness",
            blocking_scope="artifact_freshness",
            gate_effect=GATE_EFFECT_ADVISORY,
            recommended_targets=recommended_targets,
        )
    return None


def _mapped_reason_detail(
    reason_id: str,
    mapping: dict[str, tuple[str, str, list[str]]],
    *,
    gate_effect: str = GATE_EFFECT_ADVISORY,
) -> dict[str, Any] | None:
    if reason_id not in mapping:
        return None
    owning_stage, blocking_scope, recommended_targets = mapping[reason_id]
    return _target_reason_detail(
        reason_id,
        owning_stage=owning_stage,
        blocking_scope=blocking_scope,
        gate_effect=gate_effect,
        recommended_targets=recommended_targets,
    )


def _action_status_reason_detail(reason_id: str, *, fallback_target: str) -> dict[str, Any]:
    prefix_detail = _prefix_reason_detail(reason_id)
    if prefix_detail is not None:
        return prefix_detail
    for mapping in (
        MAINTAINABILITY_REASON_TARGETS,
        SUPPLY_CHAIN_EXTERNAL_REASON_TARGETS,
    ):
        mapped_detail = _mapped_reason_detail(reason_id, mapping)
        if mapped_detail is not None:
            return mapped_detail
    mapped_detail = _mapped_reason_detail(
        reason_id,
        GITHUB_LIVE_GOVERNANCE_REASON_TARGETS,
        gate_effect=GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
    )
    if mapped_detail is not None:
        return mapped_detail
    if reason_id == "github_governance_live_drift_gap":
        archive_live_detail = _mapped_reason_detail(
            reason_id,
            ARCHIVE_RECONCILIATION_REASON_TARGETS,
            gate_effect=GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
        )
        if archive_live_detail is not None:
            return archive_live_detail
    archive_detail = _mapped_reason_detail(reason_id, ARCHIVE_RECONCILIATION_REASON_TARGETS)
    if archive_detail is not None:
        return archive_detail
    return _target_reason_detail(
        reason_id,
        owning_stage="action_recommended_target",
        blocking_scope="action_matrix",
        gate_effect=GATE_EFFECT_ADVISORY,
        recommended_targets=(fallback_target,),
    )


def action_status_reason_details(
    reason_ids: list[str],
    *,
    fallback_target: str,
) -> list[dict[str, Any]]:
    return [
        _action_status_reason_detail(reason_id, fallback_target=fallback_target)
        for reason_id in reason_ids
    ]


def action_statuses(vault: Path) -> dict[str, str]:
    return {
        str(action["action_id"]): status_from_evidence(vault, action)[0]
        for action in ACTION_CATALOG
    }
