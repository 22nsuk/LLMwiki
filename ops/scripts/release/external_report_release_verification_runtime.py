from __future__ import annotations

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
from ops.scripts.core.schema_constants_runtime import (
    GENERATED_ARTIFACT_INDEX_SCHEMA_PATH,
    REVIEW_ARCHIVE_REPORT_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)
from ops.scripts.gate_effect_vocabulary import GATE_EFFECT_BLOCKS_PROMOTION
from ops.scripts.policy_runtime import report_path
from ops.scripts.source_revision_runtime import resolve_source_revision
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from .external_report_inventory_runtime import (
    REFERENCE_MANIFEST,
    archived_report_paths,
    as_dict,
    as_int,
    as_list,
    load_json_object,
)
from .release_closeout_finality_attestation import verify_attestation
from .review_archive import (
    CLEAN_SOURCE_COMMAND as REVIEW_ARCHIVE_CLEAN_SOURCE_COMMAND,
    PRODUCER as REVIEW_ARCHIVE_PRODUCER,
)

TASK_IMPROVEMENT_OBSERVATIONS_ROOT = "ops/reports/task-improvement-observations"
REVIEW_ARCHIVE_REPORT_PATH = "ops/reports/review-archive-report.json"
GENERATED_ARTIFACT_INDEX_PATH = "ops/reports/generated-artifact-index.json"
ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID = "archived_report_action_trace_gap"
REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID = "review_bundle_full_vault_hygiene_gap"
SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")
ARCHIVED_REPORT_ACTION_BASIS_REQUIRED_FIELDS = (
    "path",
    "report_type",
    "content_sha256",
    "matched_action_ids",
    "matched_action_count",
    "unresolved_action_ids",
    "unresolved_action_count",
    "unmatched_recommendation_count",
    "operator_only_rationale",
    "archive_decision_code",
)
OPEN_IMPROVEMENT_OBSERVATION_STATUSES = {"open", "planned"}
RESOLUTION_EVIDENCE_REQUIRED_STATUSES = {"automated"}
RESOLUTION_EVIDENCE_PREFIXES = ("source:", "test:", "artifact:", "digest:", "make:")
ARCHIVE_RECONCILIATION_OBSERVATION_ACTIONS: dict[str, set[str]] = {
    ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID: {
        "external_report_lifecycle",
        "active_report_manifest_freshness",
    },
    "status_surface_currentness_visibility_gap": {
        "artifact_freshness_performance_observability",
        "operator_entrypoint_index",
        "selected_contract_currentness_gate",
    },
    "dev_install_index_portability_gap": {
        "operator_entrypoint_index",
        "uv_lock_canonical_policy",
    },
    "github_governance_live_drift_gap": {
        "github_governance_live_drift_verification",
    },
    REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID: {
        "repo_boundary_history_hygiene",
        "source_package_distribution_binding",
        "windows_path_and_archive_alias_parity",
    },
    "full_vault_archive_mtime_normalization_gap": {
        "source_package_distribution_binding",
        "windows_path_and_archive_alias_parity",
    },
}

def _resolution_evidence_items(observation: dict[str, Any]) -> list[str]:
    value = observation.get("resolution_evidence")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _has_verified_resolution_evidence(observation: dict[str, Any]) -> bool:
    return any(
        item.startswith(RESOLUTION_EVIDENCE_PREFIXES)
        for item in _resolution_evidence_items(observation)
    )


def _review_archive_clean_report_verified(vault: Path) -> bool:
    report = load_json_object(vault / REVIEW_ARCHIVE_REPORT_PATH)
    schema_errors = validate_with_schema(
        report,
        load_schema_with_vault_override(vault, REVIEW_ARCHIVE_REPORT_SCHEMA_PATH),
    )
    if schema_errors:
        return False
    hygiene = as_dict(report.get("snapshot_hygiene"))
    representativeness = as_dict(report.get("current_snapshot_representativeness"))
    archive_file = as_dict(report.get("archive_file"))
    manifest_digest = str(report.get("manifest_digest", "")).strip()
    archive_manifest_digest = str(report.get("archive_manifest_digest", "")).strip()
    return (
        report.get("artifact_kind") == "review_archive_report"
        and report.get("producer") == REVIEW_ARCHIVE_PRODUCER
        and report.get("source_command") == REVIEW_ARCHIVE_CLEAN_SOURCE_COMMAND
        and report.get("artifact_status") == "current"
        and as_dict(report.get("currentness")).get("status") == "current"
        and report.get("status") == "pass"
        and report.get("profile") == "clean"
        and report.get("exclusion_policy") == "public_surface_policy"
        and archive_file.get("exists") is True
        and bool(str(archive_file.get("sha256", "")).strip())
        and hygiene.get("profile") == "clean"
        and hygiene.get("status") == "pass"
        and hygiene.get("enforced") is True
        and as_int(hygiene.get("forbidden_count")) == 0
        and as_list(hygiene.get("forbidden_paths")) == []
        and representativeness.get("status") == "representative"
        and representativeness.get("representative_of_current_tree") is True
        and representativeness.get("representative_of_current_zip") is True
        and representativeness.get("next_action") == "none"
        and bool(manifest_digest)
        and manifest_digest == archive_manifest_digest
    )


def _archived_report_basis_record_verified(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    if any(field not in record for field in ARCHIVED_REPORT_ACTION_BASIS_REQUIRED_FIELDS):
        return False
    matched_action_ids = as_list(record.get("matched_action_ids"))
    unresolved_action_ids = as_list(record.get("unresolved_action_ids"))
    return (
        bool(str(record.get("path", "")).strip())
        and str(record.get("report_type", "")).strip()
        in {"narrative_report", "reference_manifest", "binary_report"}
        and bool(SHA256_HEX_RE.match(str(record.get("content_sha256", "")).strip()))
        and all(isinstance(action_id, str) and action_id for action_id in matched_action_ids)
        and as_int(record.get("matched_action_count")) == len(matched_action_ids)
        and all(
            isinstance(action_id, str) and action_id for action_id in unresolved_action_ids
        )
        and as_int(record.get("unresolved_action_count")) == len(unresolved_action_ids)
        and as_int(record.get("unmatched_recommendation_count")) >= 0
        and isinstance(record.get("operator_only_rationale", ""), str)
        and bool(str(record.get("archive_decision_code", "")).strip())
    )


def _generated_index_archived_report_basis_verified(vault: Path) -> bool:
    report = load_json_object(vault / GENERATED_ARTIFACT_INDEX_PATH)
    schema_errors = validate_with_schema(
        report,
        load_schema_with_vault_override(vault, GENERATED_ARTIFACT_INDEX_SCHEMA_PATH),
    )
    if schema_errors:
        return False
    records = as_list(report.get("archived_external_report_basis"))
    expected_paths = sorted(report_path(vault, path) for path in archived_report_paths(vault))
    record_paths = sorted(
        str(record.get("path", "")).strip()
        for record in records
        if isinstance(record, dict)
    )
    return (
        report.get("artifact_kind") == "generated_artifact_index_report"
        and report.get("artifact_status") == "current"
        and as_dict(report.get("currentness")).get("status") == "current"
        and record_paths == expected_paths
        and all(_archived_report_basis_record_verified(record) for record in records)
    )


def _has_verified_observation_resolution(vault: Path, observation: dict[str, Any]) -> bool:
    if not _has_verified_resolution_evidence(observation):
        return False
    observation_id = str(observation.get("observation_id", "")).strip()
    if observation_id == ARCHIVED_REPORT_ACTION_TRACE_OBSERVATION_ID:
        return _generated_index_archived_report_basis_verified(vault)
    if observation_id == REVIEW_BUNDLE_FULL_VAULT_HYGIENE_OBSERVATION_ID:
        return _review_archive_clean_report_verified(vault)
    return True


def _observation_keeps_archive_action_active(vault: Path, observation: dict[str, Any]) -> bool:
    status = str(observation.get("status", "")).strip()
    if status in OPEN_IMPROVEMENT_OBSERVATION_STATUSES:
        return True
    return status in RESOLUTION_EVIDENCE_REQUIRED_STATUSES and not (
        _has_verified_observation_resolution(vault, observation)
    )


def _observation_runtime_status(vault: Path, observation: dict[str, Any]) -> str:
    status = str(observation.get("status", "")).strip()
    if status in RESOLUTION_EVIDENCE_REQUIRED_STATUSES and not (
        _has_verified_observation_resolution(vault, observation)
    ):
        return f"{status}_missing_resolution_evidence"
    return status


def _archive_reconciliation_observation_records(vault: Path) -> list[dict[str, Any]]:
    root = vault / TASK_IMPROVEMENT_OBSERVATIONS_ROOT
    if not root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/improvement-observations.json")):
        payload = load_json_object(path)
        observations = as_list(payload.get("observations"))
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            observation_id = str(observation.get("observation_id", "")).strip()
            action_ids = ARCHIVE_RECONCILIATION_OBSERVATION_ACTIONS.get(observation_id)
            if action_ids is None or not _observation_keeps_archive_action_active(
                vault, observation
            ):
                continue
            records.append(
                {
                    "observation_id": observation_id,
                    "path": report_path(vault, path),
                    "status": _observation_runtime_status(vault, observation),
                    "resolution_evidence_status": (
                        "verified"
                        if _has_verified_observation_resolution(vault, observation)
                        else "missing"
                    ),
                    "action_ids": sorted(action_ids),
                }
            )
    return records


def archive_reconciliation_observation_inventory(vault: Path) -> list[dict[str, Any]]:
    return _archive_reconciliation_observation_records(vault)


def archive_reconciliation_observation_paths(vault: Path) -> list[str]:
    return sorted({str(record["path"]) for record in _archive_reconciliation_observation_records(vault)})


def archive_reconciliation_observation_reason_ids(vault: Path, action_id: str) -> list[str]:
    return sorted(
        {
            str(record["observation_id"])
            for record in _archive_reconciliation_observation_records(vault)
            if action_id in set(record["action_ids"])
        }
    )


def _status_with_archive_reconciliation_observations(vault: Path, action_id: str, status: str) -> str:
    if status != "implemented":
        return status
    if archive_reconciliation_observation_reason_ids(vault, action_id):
        return "partially_automated"
    return status


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


def _reference_manifest_distribution_reason_ids(vault: Path) -> list[str]:
    manifest = load_json_object(vault / REFERENCE_MANIFEST)
    if not manifest:
        return ["external_report_reference_manifest_missing"]
    summary = as_dict(manifest.get("summary"))
    reasons: list[str] = []
    if summary.get("current_distribution_zip_known") is not True:
        reasons.append("external_report_current_distribution_zip_missing")
    if summary.get("basis_zip_matches_current_distribution") is not True:
        reasons.append("external_report_basis_zip_not_bound")
    if str(summary.get("zip_provenance_status", "")).strip() != "basis_current_match":
        reasons.append("external_report_zip_provenance_not_bound")
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


RELEASE_AUTHORITY_REASON_ACTIONS = frozenset(
    {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
        "full_suite_evidence_currentness",
        "promotion_truth_ladder",
    }
)
SOURCE_PACKAGE_REASON_ACTIONS = frozenset(
    {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
    }
)
FULL_SUITE_REASON_ACTIONS = frozenset(
    {
        "release_evidence_bundle_and_attestation",
        "full_suite_evidence_currentness",
    }
)
RELEASE_RUN_MANIFEST_REASON_ACTIONS = frozenset(
    {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
        "full_suite_evidence_currentness",
    }
)
SEALED_RUN_MANIFEST_REASON_ACTIONS = frozenset(
    {
        "source_package_distribution_binding",
        "release_evidence_bundle_and_attestation",
    }
)


def _release_run_manifest_reason_ids(vault: Path) -> list[str]:
    return _current_release_manifest_reason_ids(
        vault,
        "build/release/release-run-manifest.json",
        "release_run_manifest",
        "release_run_manifest",
    )


def _sealed_run_manifest_reason_ids(vault: Path) -> list[str]:
    return _current_release_manifest_reason_ids(
        vault,
        "build/release/release-sealed-run-manifest.json",
        "release_sealed_run_manifest",
        "release_sealed_run_manifest",
    )


def _release_evidence_finality_reason_ids(vault: Path) -> list[str]:
    reasons: list[str] = []
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
    return reasons


def _promotion_truth_ladder_reason_ids(vault: Path) -> list[str]:
    ready = load_json_object(vault / "build/release/release-auto-promotion-ready-manifest.json")
    if not ready:
        return ["release_auto_promotion_ready_manifest_missing"]
    reasons: list[str] = []
    if ready.get("status") != "pass":
        reasons.append("release_auto_promotion_ready_manifest_not_pass")
    if ready.get("artifact_kind") != "release_auto_promotion_ready_manifest":
        reasons.append("release_auto_promotion_ready_manifest_kind_mismatch")
    if ready.get("auto_promotion_status") != "allowed":
        reasons.append("release_auto_promotion_not_allowed")
    if ready.get("unattended_promotion_allowed") is not True:
        reasons.append("release_unattended_promotion_not_allowed")
    if str(ready.get("source_tree_fingerprint", "")).strip() != release_source_tree_fingerprint(
        vault
    ):
        reasons.append("release_auto_promotion_ready_manifest_source_tree_fingerprint_mismatch")
    artifact_revision = release_artifact_revision(ready)
    if not artifact_revision:
        reasons.append("release_auto_promotion_ready_manifest_source_revision_missing")
    elif not _release_artifact_revision_current(vault, ready):
        reasons.append("release_auto_promotion_ready_manifest_source_revision_mismatch")
    return reasons


def _common_release_verified_reason_ids(vault: Path, action_id: str) -> list[str]:
    reasons: list[str] = []
    if action_id in RELEASE_AUTHORITY_REASON_ACTIONS:
        reasons.extend(_release_authority_report_reason_ids(vault))
    if action_id in SOURCE_PACKAGE_REASON_ACTIONS:
        reasons.extend(_source_package_reason_ids(vault))
    if action_id in FULL_SUITE_REASON_ACTIONS:
        reasons.extend(_full_suite_reason_ids(vault))
    if action_id in RELEASE_RUN_MANIFEST_REASON_ACTIONS:
        reasons.extend(_release_run_manifest_reason_ids(vault))
    if action_id in SEALED_RUN_MANIFEST_REASON_ACTIONS:
        reasons.extend(_sealed_run_manifest_reason_ids(vault))
    return reasons


def release_verified_action_reason_ids(vault: Path, action_id: str) -> list[str]:
    reasons: list[str] = []
    reasons.extend(_common_release_verified_reason_ids(vault, action_id))
    if action_id == "source_package_distribution_binding":
        reasons.extend(_reference_manifest_distribution_reason_ids(vault))
    if action_id == "release_evidence_bundle_and_attestation":
        reasons.extend(_release_evidence_finality_reason_ids(vault))
    if action_id == "promotion_truth_ladder":
        reasons.extend(_promotion_truth_ladder_reason_ids(vault))
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
        and not _reference_manifest_distribution_reason_ids(vault)
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


CountStatusResolver = Callable[[Path, int, int], str]


def _release_verified_count_status(action_id: str) -> CountStatusResolver:
    def resolver(vault: Path, existing_count: int, expected_count: int) -> str:
        return release_verified_action_status(
            vault,
            existing_count,
            expected_count,
            action_id=action_id,
        )

    return resolver
