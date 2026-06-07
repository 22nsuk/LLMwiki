from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ops.scripts.core.release_authority_state_runtime import (
    RELEASE_AUTHORITY_VERIFIED_STATUSES,
    authoritative_live_rerun_fail_count,
    authoritative_live_rerun_not_run_count,
    current_release_manifest_pass,
    release_artifact_revision,
    release_authority_reports_verified,
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_PROMOTION,
    GATE_EFFECT_CLAIM_BLOCKER,
)
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_revision_runtime import resolve_source_revision
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
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
)
from .release_closeout_finality_attestation import verify_attestation
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
)


def _release_authority_reports_verified(vault: Path) -> bool:
    closeout = load_json_object(vault / "ops/reports/release-closeout-summary.json")
    dashboard = load_json_object(vault / "ops/reports/release-evidence-dashboard.json")
    return release_authority_reports_verified(closeout=closeout, dashboard=dashboard)


def _full_suite_evidence_verified(vault: Path) -> bool:
    full_summary = load_json_object(vault / "ops/reports/test-execution-summary-full.json")
    full_counts = as_dict(full_summary.get("counts"))
    return (
        full_summary.get("status") == "pass"
        and as_int(full_counts.get("failed")) == 0
        and as_int(full_counts.get("errors")) == 0
    )


def _dedupe_reason_ids(reason_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(reason_id for reason_id in reason_ids if reason_id))


def _reason_token(value: object) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return token or "unknown"


def _reason_detail(
    reason_id: str,
    *,
    owning_stage: str,
    recommended_targets: list[str],
    blocking_scope: str | None = None,
    gate_effect: str = GATE_EFFECT_BLOCKS_PROMOTION,
) -> dict[str, Any]:
    return {
        "reason_id": reason_id,
        "owning_stage": owning_stage,
        "blocking_scope": blocking_scope or owning_stage,
        "gate_effect": gate_effect,
        "recommended_targets": recommended_targets,
    }


def _evidence_reason_ids(evidence: list[dict[str, Any]]) -> list[str]:
    missing_count = sum(1 for item in evidence if not bool(item.get("exists")))
    if missing_count:
        return ["evidence_missing"]
    return []


def _release_authority_report_reason_ids(vault: Path) -> list[str]:
    closeout = load_json_object(vault / "ops/reports/release-closeout-summary.json")
    dashboard = load_json_object(vault / "ops/reports/release-evidence-dashboard.json")
    closeout_summary = as_dict(closeout.get("summary"))
    dashboard_summary = as_dict(dashboard.get("summary"))
    view = release_status_v2_view_with_readiness_fallback(closeout)
    reasons: list[str] = []
    if closeout.get("status") != "pass":
        reasons.append("release_closeout_summary_not_pass")
    if closeout_summary.get("live_make_check_status") != "pass":
        reasons.append("release_closeout_live_make_check_not_pass")
    if not bool(view.get("status_v2_available")):
        reasons.append("release_closeout_status_v2_missing")
    if str(view.get("release_authority_status", "")).strip() not in RELEASE_AUTHORITY_VERIFIED_STATUSES:
        reasons.append("release_authority_status_not_verified")
        reasons.extend(
            f"release_authority_blocker:{_reason_token(reason_id)}"
            for reason_id in as_list(view.get("blocker_reason_ids"))
        )
    if authoritative_live_rerun_fail_count(dashboard):
        reasons.append("release_dashboard_authoritative_live_rerun_fail")
    if authoritative_live_rerun_not_run_count(dashboard):
        reasons.append("release_dashboard_authoritative_live_rerun_not_run")
    if as_int(dashboard_summary.get("required_input_fail_count")):
        reasons.append("release_dashboard_required_input_fail")
    if reasons:
        return _dedupe_reason_ids(reasons)
    if not release_authority_reports_verified(closeout=closeout, dashboard=dashboard):
        return ["release_authority_reports_not_verified"]
    return []


def _current_release_manifest_reason_ids(
    vault: Path,
    rel_path: str,
    artifact_kind: str,
    reason_prefix: str,
) -> list[str]:
    payload = load_json_object(vault / rel_path)
    if not payload:
        return [f"{reason_prefix}_missing"]
    reasons: list[str] = []
    if payload.get("status") != "pass":
        reasons.append(f"{reason_prefix}_not_pass")
    if payload.get("artifact_kind") != artifact_kind:
        reasons.append(f"{reason_prefix}_artifact_kind_mismatch")
    current_fingerprint = release_source_tree_fingerprint(vault)
    if str(payload.get("source_tree_fingerprint", "")).strip() != current_fingerprint:
        reasons.append(f"{reason_prefix}_source_tree_fingerprint_mismatch")
    artifact_revision = release_artifact_revision(payload)
    current_revision = resolve_source_revision(vault).revision
    if not artifact_revision:
        reasons.append(f"{reason_prefix}_source_revision_missing")
    elif artifact_revision not in {current_revision, "source_package_without_git"}:
        reasons.append(f"{reason_prefix}_source_revision_mismatch")
    return reasons


def _release_artifact_revision_current(vault: Path, payload: dict[str, Any]) -> bool:
    artifact_revision = release_artifact_revision(payload)
    return bool(artifact_revision) and artifact_revision in {
        resolve_source_revision(vault).revision,
        "source_package_without_git",
    }


def _source_package_reason_ids(vault: Path) -> list[str]:
    source_package = load_json_object(vault / "ops/reports/source-package-clean-extract.json")
    if not source_package:
        return ["source_package_clean_extract_missing"]
    reasons: list[str] = []
    if source_package.get("status") != "pass":
        reasons.append("source_package_clean_extract_not_pass")
    return reasons


def _full_suite_reason_ids(vault: Path) -> list[str]:
    full_summary = load_json_object(vault / "ops/reports/test-execution-summary-full.json")
    if not full_summary:
        return ["full_suite_summary_missing"]
    full_counts = as_dict(full_summary.get("counts"))
    reasons: list[str] = []
    if full_summary.get("status") != "pass":
        reasons.append("full_suite_summary_not_pass")
    if as_int(full_counts.get("failed")):
        reasons.append("full_suite_failed_tests")
    if as_int(full_counts.get("errors")):
        reasons.append("full_suite_error_tests")
    return reasons


def release_verified_action_reason_ids(vault: Path, action_id: str) -> list[str]:
    reasons: list[str] = []
    if action_id in {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
        "full_suite_evidence_currentness",
        "promotion_truth_ladder",
    }:
        reasons.extend(_release_authority_report_reason_ids(vault))
    if action_id in {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
    }:
        reasons.extend(_source_package_reason_ids(vault))
    if action_id in {
        "release_evidence_bundle_and_attestation",
        "full_suite_evidence_currentness",
    }:
        reasons.extend(_full_suite_reason_ids(vault))
    if action_id in {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
        "full_suite_evidence_currentness",
    }:
        reasons.extend(
            _current_release_manifest_reason_ids(
                vault,
                "build/release/release-run-manifest.json",
                "release_run_manifest",
                "release_run_manifest",
            )
        )
    if action_id == "source_package_distribution_binding":
        reasons.extend(
            _current_release_manifest_reason_ids(
                vault,
                "build/release/release-sealed-run-manifest.json",
                "release_sealed_run_manifest",
                "release_sealed_run_manifest",
            )
        )
    if action_id == "release_evidence_bundle_and_attestation":
        reasons.extend(
            _current_release_manifest_reason_ids(
                vault,
                "build/release/release-sealed-run-manifest.json",
                "release_sealed_run_manifest",
                "release_sealed_run_manifest",
            )
        )
    if action_id == "release_evidence_bundle_and_attestation":
        fixed_point = load_json_object(vault / "ops/reports/release-closeout-fixed-point.json")
        finality = load_json_object(vault / "ops/reports/release-closeout-finality-attestation.json")
        finality_fixed_point = as_dict(finality.get("fixed_point_report"))
        finality_verified, _finality_failures = verify_attestation(vault)
        if fixed_point.get("status") != "pass":
            reasons.append("release_closeout_fixed_point_not_pass")
        if not bool(fixed_point.get("converged")):
            reasons.append("release_closeout_fixed_point_not_converged")
        if finality_fixed_point.get("status") != "pass":
            reasons.append("release_finality_fixed_point_report_not_pass")
        if not finality_verified:
            reasons.append("release_finality_attestation_verification_failed")
    if action_id == "promotion_truth_ladder":
        ready = load_json_object(vault / "build/release/release-auto-promotion-ready-manifest.json")
        if not ready:
            reasons.append("release_auto_promotion_ready_manifest_missing")
        else:
            if ready.get("status") != "pass":
                reasons.append("release_auto_promotion_ready_manifest_not_pass")
            if ready.get("artifact_kind") != "release_auto_promotion_ready_manifest":
                reasons.append("release_auto_promotion_ready_manifest_kind_mismatch")
            if ready.get("auto_promotion_status") != "allowed":
                reasons.append("release_auto_promotion_not_allowed")
            if ready.get("unattended_promotion_allowed") is not True:
                reasons.append("release_unattended_promotion_not_allowed")
            if (
                str(ready.get("source_tree_fingerprint", "")).strip()
                != release_source_tree_fingerprint(vault)
            ):
                reasons.append("release_auto_promotion_ready_manifest_source_tree_fingerprint_mismatch")
            artifact_revision = release_artifact_revision(ready)
            if not artifact_revision:
                reasons.append("release_auto_promotion_ready_manifest_source_revision_missing")
            elif not _release_artifact_revision_current(vault, ready):
                reasons.append("release_auto_promotion_ready_manifest_source_revision_mismatch")
    return _dedupe_reason_ids(reasons)


def source_package_distribution_binding_verified(vault: Path) -> bool:
    source_package = load_json_object(vault / "ops/reports/source-package-clean-extract.json")
    return (
        _release_authority_reports_verified(vault)
        and source_package.get("status") == "pass"
        and current_release_manifest_pass(
            vault,
            "build/release/release-run-manifest.json",
            "release_run_manifest",
        )
        and current_release_manifest_pass(
            vault,
            "build/release/release-sealed-run-manifest.json",
            "release_sealed_run_manifest",
        )
    )


def full_suite_evidence_currentness_verified(vault: Path) -> bool:
    return (
        _release_authority_reports_verified(vault)
        and _full_suite_evidence_verified(vault)
        and current_release_manifest_pass(
            vault,
            "build/release/release-run-manifest.json",
            "release_run_manifest",
        )
    )


def promotion_truth_ladder_verified(vault: Path) -> bool:
    ready = load_json_object(vault / "build/release/release-auto-promotion-ready-manifest.json")
    return (
        _release_authority_reports_verified(vault)
        and ready.get("status") == "pass"
        and ready.get("artifact_kind") == "release_auto_promotion_ready_manifest"
        and ready.get("auto_promotion_status") == "allowed"
        and ready.get("unattended_promotion_allowed") is True
        and str(ready.get("source_tree_fingerprint", "")).strip()
        == release_source_tree_fingerprint(vault)
        and _release_artifact_revision_current(vault, ready)
    )


def release_evidence_bundle_and_attestation_verified(vault: Path) -> bool:
    fixed_point = load_json_object(vault / "ops/reports/release-closeout-fixed-point.json")
    finality = load_json_object(vault / "ops/reports/release-closeout-finality-attestation.json")
    finality_fixed_point = as_dict(finality.get("fixed_point_report"))
    finality_verified, _finality_failures = verify_attestation(vault)
    return (
        _release_authority_reports_verified(vault)
        and _full_suite_evidence_verified(vault)
        and source_package_distribution_binding_verified(vault)
        and fixed_point.get("status") == "pass"
        and bool(fixed_point.get("converged"))
        and finality_fixed_point.get("status") == "pass"
        and finality_verified
    )


RELEASE_VERIFIED_ACTION_RESOLVERS: dict[str, Callable[[Path], bool]] = {
    "source_package_distribution_binding": source_package_distribution_binding_verified,
    "release_evidence_bundle_and_attestation": release_evidence_bundle_and_attestation_verified,
    "full_suite_evidence_currentness": full_suite_evidence_currentness_verified,
    "promotion_truth_ladder": promotion_truth_ladder_verified,
}


def release_run_verified(vault: Path) -> bool:
    return all(verifier(vault) for verifier in RELEASE_VERIFIED_ACTION_RESOLVERS.values())


def release_verified_action_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
    *,
    action_id: str,
) -> str:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    verifier = RELEASE_VERIFIED_ACTION_RESOLVERS[action_id]
    return "implemented" if verifier(vault) else "requires_release_run_verification"


def _release_verified_count_status(action_id: str) -> CountStatusResolver:
    def resolver(vault: Path, existing_count: int, expected_count: int) -> str:
        return release_verified_action_status(
            vault,
            existing_count,
            expected_count,
            action_id=action_id,
        )

    return resolver


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
        if as_int(summary.get("stale_artifact_count")):
            reasons.append("artifact_freshness_stale_canonical_reports")
        if as_int(summary.get("operational_attention_artifact_count")):
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


def release_mechanism_service_layer_extraction_status(
    vault: Path,
    existing_count: int,
    expected_count: int,
) -> str:
    if existing_count == 0:
        return "planned"
    core_text = _read_text_or_empty(vault / "ops/scripts/core/release_authority_state_runtime.py")
    facade_text = _read_text_or_empty(vault / "ops/scripts/release/release_status_v2.py")
    mechanism_text = _read_text_or_empty(
        vault / "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py"
    )
    lifecycle_text = _read_text_or_empty(
        vault / "ops/scripts/release/external_report_lifecycle_runtime.py"
    )
    inventory_text = _read_text_or_empty(vault / "ops/scripts/release/release_authority_inventory.py")
    currentness_text = _read_text_or_empty(
        vault / "ops/scripts/core/release_currentness_state_runtime.py"
    )
    risk_text = _read_text_or_empty(vault / "ops/scripts/core/release_risk_state_runtime.py")
    learning_text = _read_text_or_empty(
        vault / "ops/scripts/core/learning_claim_state_runtime.py"
    )
    cohort_text = _read_text_or_empty(vault / "ops/scripts/release/release_evidence_cohort.py")
    dashboard_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard.py"
    )
    closeout_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_closeout_summary.py"
    )
    clean_blocker_text = _read_text_or_empty(
        vault / "ops/scripts/release/release_clean_blocker_ledger.py"
    )
    unlock_text = _read_text_or_empty(
        vault / "ops/scripts/learning/learning_delta_scoreboard_unlock_runtime.py"
    )
    authority_extracted = all(
        token in core_text
        for token in (
            "release_status_v2_view",
            "machine_release_allowed_from_status_view",
            "clean_required_preflight_passes",
            "release_authority_reports_verified",
            "current_release_manifest_pass",
            "release_artifact_revision",
        )
    )
    facade_uses_authority_service = (
        "from ops.scripts.core.release_authority_state_runtime import" in facade_text
        or "from ops.scripts.core import release_authority_state_runtime" in facade_text
    )
    consumers_use_service = (
        facade_uses_authority_service
        and "machine_release_allowed_from_status_view" in mechanism_text
        and "clean_required_preflight_passes" in mechanism_text
        and "release_authority_reports_verified" in lifecycle_text
        and "current_release_manifest_pass" in lifecycle_text
        and "release_artifact_revision" in inventory_text
    )
    currentness_extracted = all(
        token in currentness_text
        for token in (
            "def currentness_field",
            "def live_rerun_state",
            "def components_match_current_source_tree",
        )
    )
    currentness_consumers_use_service = (
        "from ops.scripts.core.release_currentness_state_runtime import" in cohort_text
        and "from ops.scripts.core.release_currentness_state_runtime import" in closeout_text
        and "from ops.scripts.core.release_currentness_state_runtime import" in dashboard_text
        and "live_rerun_state(" in dashboard_text
        and "components_match_current_source_tree(" in closeout_text
    )
    risk_extracted = all(
        token in risk_text
        for token in (
            "def release_risk_identity",
            "def release_risk_blocks_clean_lane",
            "def release_risk_list",
            "def release_blocker_entry",
        )
    )
    risk_consumers_use_service = (
        "from ops.scripts.core.release_risk_state_runtime import" in closeout_text
        and "from ops.scripts.core.release_risk_state_runtime import" in clean_blocker_text
        and "release_risk_identity(" in closeout_text
        and "release_risk_blocks_clean_lane(" in clean_blocker_text
    )
    learning_extracted = all(
        token in learning_text
        for token in (
            "def confirmed_evidence_summary",
            "def confirmed_predicate_results",
            "def confirmed_blocking_predicate_ids",
            "def confirmed_wording_allowed",
        )
    )
    learning_consumers_use_service = (
        "from ops.scripts.core.learning_claim_state_runtime import" in dashboard_text
        and "from ops.scripts.core.learning_claim_state_runtime import" in unlock_text
        and "confirmed_evidence_summary(" in dashboard_text
        and "confirmed_evidence_summary(" in unlock_text
    )
    complete_service_family = all(
        (
            currentness_extracted,
            currentness_consumers_use_service,
            risk_extracted,
            risk_consumers_use_service,
            learning_extracted,
            learning_consumers_use_service,
        )
    )
    if existing_count == expected_count and authority_extracted and consumers_use_service:
        return "implemented" if complete_service_family else "partially_automated"
    return "partially_automated"


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
CountStatusResolver = Callable[[Path, int, int], str]


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
    elif action_id == "goal_execution_runtime_certificate":
        reasons.extend(goal_execution_runtime_certificate_reason_ids(vault))
    elif action_id == "artifact_freshness_performance_observability":
        reasons.extend(
            artifact_freshness_performance_observability_reason_ids(
                vault,
                existing_count if existing_count is not None else sum(1 for item in evidence if item.get("exists")),
                expected_count if expected_count is not None else len(evidence),
            )
        )
    if not reasons:
        reasons.append(status)
    return _dedupe_reason_ids(reasons)


def action_status_reason_details(
    reason_ids: list[str],
    *,
    fallback_target: str,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for reason_id in reason_ids:
        if reason_id.startswith("release_run_manifest_"):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_run_ready",
                    blocking_scope="release_run",
                    recommended_targets=[
                        "release-run-ready-plan-check",
                        "release-run-ready",
                    ],
                )
            )
        elif reason_id.startswith("release_sealed_run_manifest_"):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_sealed_run_ready",
                    blocking_scope="sealed_release",
                    recommended_targets=[
                        "release-sealed-run-ready-plan",
                        "release-sealed-run-ready",
                    ],
                )
            )
        elif reason_id.startswith("release_auto_promotion_ready_manifest_") or reason_id in {
            "release_auto_promotion_not_allowed",
            "release_unattended_promotion_not_allowed",
        }:
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_auto_promotion_ready",
                    blocking_scope="unattended_promotion",
                    recommended_targets=[
                        "release-auto-promotion-ready-plan",
                        "release-auto-promotion-ready",
                    ],
                )
            )
        elif reason_id.startswith(("release_finality_", "release_closeout_fixed_point_")):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_auto_promotion_preseal",
                    blocking_scope="release_preseal",
                    recommended_targets=[
                        "release-auto-promotion-preseal",
                        "release-closeout-fixed-point",
                        "release-closeout-finality-verify",
                    ],
                )
            )
        elif reason_id.startswith(("release_dashboard_", "release_authority_", "release_closeout_")):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_auto_promotion_preseal",
                    blocking_scope="release_preseal",
                    recommended_targets=[
                        "release-auto-promotion-preseal",
                        "release-evidence-dashboard",
                    ],
                )
            )
        elif reason_id.startswith("source_package_"):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_source_package",
                    blocking_scope="source_package",
                    recommended_targets=["release-source-package-check"],
                )
            )
        elif reason_id.startswith("full_suite_"):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="release_run_ready",
                    blocking_scope="release_run",
                    recommended_targets=["test-execution-summary-full-current-or-refresh"],
                )
            )
        elif reason_id.startswith("goal_runtime_"):
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="goal_runtime_certificate",
                    blocking_scope="unattended_promotion",
                    gate_effect=GATE_EFFECT_CLAIM_BLOCKER,
                    recommended_targets=[
                        "goal-runtime-certificate",
                        "release-auto-promotion-goal-run-id-guard",
                        "release-auto-promotion-ready-plan",
                    ],
                )
            )
        elif reason_id.startswith("artifact_freshness_"):
            recommended_targets = ["artifact-freshness-refresh-check"]
            if reason_id == "artifact_freshness_stable_contract_debt":
                recommended_targets = [
                    "artifact-freshness-stable-contract-debt-refresh",
                    "artifact-freshness-refresh-check",
                ]
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="artifact_freshness",
                    blocking_scope="artifact_freshness",
                    gate_effect=GATE_EFFECT_ADVISORY,
                    recommended_targets=recommended_targets,
                )
            )
        else:
            details.append(
                _reason_detail(
                    reason_id,
                    owning_stage="action_recommended_target",
                    blocking_scope="action_matrix",
                    gate_effect=GATE_EFFECT_ADVISORY,
                    recommended_targets=[fallback_target],
                )
            )
    return details


def action_statuses(vault: Path) -> dict[str, str]:
    return {
        str(action["action_id"]): status_from_evidence(vault, action)[0]
        for action in ACTION_CATALOG
    }


def report_coverage_item(vault: Path, path: Path) -> dict[str, Any]:
    rel_path = report_path(vault, path)
    text = report_text(path)
    report_type = report_type_for_path(path)
    if report_type == "binary_report":
        action_ids = ["operator_only_external_report_binary"]
    else:
        action_ids = matched_actions(text) if text else ["external_report_lifecycle"]
    if path.name == Path(REFERENCE_MANIFEST).name:
        action_ids = sorted(set(action_ids) | {"active_report_manifest_freshness"})
    return {
        "path": rel_path,
        "report_type": report_type,
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
        if profile["report_type"] == "binary_report":
            return {
                "archive_recommended": False,
                "reason": "Binary active reports require operator-only review or an explicit extracted mapping before lifecycle automation can archive them.",
                "superseded_by": [],
            }
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
