from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_binding_runtime import (
    BINDING_MODES,
    binding_file_digest,
    is_sha256_digest,
)
from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    OPERATOR_RELEASE_SUMMARY_SCHEMA_PATH,
)
from ops.scripts.learning.learning_claim_model import learning_claim_blocker_status
from ops.scripts.release.release_authority_vocabulary import (
    REASON_MACHINE_RELEASE_NOT_ALLOWED,
)
from ops.scripts.release.release_status_v2 import (
    release_status_v2_view,
    release_status_v2_view_with_readiness_fallback,
)

PRODUCER = "ops.scripts.operator_release_summary"
DEFAULT_OUT = "ops/operator/operator-release-summary.json"
DEFAULT_CLOSEOUT = "ops/reports/release-closeout-summary.json"
DEFAULT_BATCH_MANIFEST = "ops/reports/release-closeout-batch-manifest.json"
DEFAULT_SELF_CHECK = "ops/reports/release-evidence-closeout-self-check.json"
DEFAULT_TEST_SUMMARY = "ops/reports/test-execution-summary.json"
DEFAULT_FULL_TEST_SUMMARY = "ops/reports/test-execution-summary-full.json"
DEFAULT_LEARNING_REVALIDATION = "ops/reports/learning-readiness-signoff-revalidation.json"
DEFAULT_LEARNING_DELTA_SCOREBOARD = "ops/reports/learning-delta-scoreboard.json"
SOURCE_COMMAND = "python -m ops.scripts.operator_release_summary --vault . --out ops/operator/operator-release-summary.json"


@dataclass(frozen=True)
class OperatorReleaseSummaryRequest:
    closeout_path: str = DEFAULT_CLOSEOUT
    batch_manifest_path: str = DEFAULT_BATCH_MANIFEST
    self_check_path: str = DEFAULT_SELF_CHECK
    test_summary_path: str = DEFAULT_TEST_SUMMARY
    full_test_summary_path: str = DEFAULT_FULL_TEST_SUMMARY
    learning_revalidation_path: str = DEFAULT_LEARNING_REVALIDATION
    learning_delta_scoreboard_path: str = DEFAULT_LEARNING_DELTA_SCOREBOARD
    context: RuntimeContext | None = None
    policy_path: str | None = None
    source_command: str = SOURCE_COMMAND


@dataclass(frozen=True)
class OperatorSourceReports:
    closeout: dict[str, Any]
    closeout_load_status: str
    batch_manifest: dict[str, Any]
    batch_manifest_load_status: str
    self_check: dict[str, Any]
    self_check_load_status: str
    test_summary: dict[str, Any]
    test_summary_load_status: str
    full_test_summary: dict[str, Any]
    full_test_summary_load_status: str
    learning_revalidation: dict[str, Any]
    learning_revalidation_load_status: str
    learning_scoreboard: dict[str, Any]
    learning_scoreboard_load_status: str


@dataclass(frozen=True)
class OperatorReleaseSignals:
    batch_verify: dict[str, Any]
    artifact_digest_policy_status: str
    semantic_release_status: str
    sealed_release_status: str
    source_zip: dict[str, Any]
    self_check_status: str
    test_evidence: dict[str, Any]
    learning_readiness: dict[str, Any]
    learning_claim: dict[str, Any]
    accepted_risk: dict[str, Any]
    auto_improve_lane_status: str
    status: str


@dataclass(frozen=True)
class OperatorReleaseRenderInputs:
    vault: Path
    request: OperatorReleaseSummaryRequest
    policy: dict[str, Any]
    resolved_policy_path: Path
    generated_at: str
    sources: OperatorSourceReports
    signals: OperatorReleaseSignals


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_optional(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    return payload, status


def _tmp_json_paths(vault: Path) -> list[str]:
    tmp_dir = vault / "tmp"
    if not tmp_dir.is_dir():
        return []
    return sorted(report_path(vault, path) for path in tmp_dir.rglob("*") if path.is_file())


def _batch_verify_snapshot(vault: Path, batch_manifest: dict[str, Any], load_status: str) -> dict[str, Any]:
    tmp_paths = _tmp_json_paths(vault)
    if not batch_manifest:
        return {
            "status": "fail",
            "manifest_load_status": load_status,
            "authority_schema_status": "missing",
            "manifest_schema_version": 0,
            "artifact_count": 0,
            "mismatch_count": 0,
            "missing_artifact_count": 0,
            "tmp_json_count": len(tmp_paths),
            "tmp_json_paths": tmp_paths,
            "mismatches": [],
            "summary": "release batch manifest is missing or unreadable",
        }
    declared_schema_version = batch_manifest.get("schema_version")
    schema_version = declared_schema_version if type(declared_schema_version) is int else 0
    if schema_version != 2:
        return {
            "status": "fail",
            "manifest_load_status": load_status,
            "authority_schema_status": "unsupported",
            "manifest_schema_version": schema_version,
            "artifact_count": 0,
            "mismatch_count": 0,
            "missing_artifact_count": 0,
            "tmp_json_count": len(tmp_paths),
            "tmp_json_paths": tmp_paths,
            "mismatches": [],
            "summary": (
                "release batch manifest is not current authority; "
                f"expected exact integer schema_version=2; actual={declared_schema_version!r}"
            ),
        }

    mismatches: list[dict[str, str]] = []
    missing_count = 0
    artifacts = batch_manifest.get("artifacts", [])
    artifacts = artifacts if isinstance(artifacts, list) else []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            mismatches.append(
                {
                    "path": f"<invalid-artifact-{index}>",
                    "binding_mode": "missing",
                    "expected_binding_digest": "missing",
                    "actual_binding_digest": "not_checked",
                    "declared_raw_digest": "missing",
                    "actual_raw_digest": "not_checked",
                    "reason": "binding_metadata_invalid",
                }
            )
            continue
        rel_path = str(artifact.get("path", "")).strip()
        display_rel_path = rel_path or f"<missing-path-{index}>"
        binding_mode = str(artifact.get("binding_mode", "")).strip()
        expected_binding_digest = str(artifact.get("binding_digest", "")).strip() or "missing"
        declared_raw = str(artifact.get("raw_digest", "")).strip() or "missing"
        artifact_path = vault / rel_path if rel_path else None
        actual_raw = _sha256_file(artifact_path) if artifact_path is not None else "not_checked"
        actual_binding_digest = "not_checked"
        binding_metadata_valid = bool(
            rel_path
            and is_sha256_digest(expected_binding_digest)
            and binding_mode in BINDING_MODES
        )
        if binding_metadata_valid and artifact_path is not None:
            actual_binding_digest = binding_file_digest(
                artifact_path,
                binding_mode=binding_mode,
            )[1]
        if actual_raw == "missing":
            missing_count += 1
        if not binding_metadata_valid or expected_binding_digest != actual_binding_digest:
            mismatches.append(
                {
                    "path": display_rel_path,
                    "binding_mode": binding_mode or "missing",
                    "expected_binding_digest": expected_binding_digest,
                    "actual_binding_digest": actual_binding_digest,
                    "declared_raw_digest": declared_raw,
                    "actual_raw_digest": actual_raw,
                    "reason": (
                        "binding_digest_mismatch"
                        if binding_metadata_valid
                        else "binding_metadata_invalid"
                    ),
                }
            )

    status = "pass" if not mismatches and not tmp_paths else "fail"
    return {
        "status": status,
        "manifest_load_status": load_status,
        "authority_schema_status": "current",
        "manifest_schema_version": schema_version,
        "artifact_count": len(artifacts),
        "mismatch_count": len(mismatches),
        "missing_artifact_count": missing_count,
        "tmp_json_count": len(tmp_paths),
        "tmp_json_paths": tmp_paths,
        "mismatches": mismatches,
        "summary": (
            f"batch verify status={status}; artifact_count={len(artifacts)}; "
            f"mismatch_count={len(mismatches)}; tmp_json_count={len(tmp_paths)}"
        ),
    }


def _artifact_digest_policy_status(batch_verify: dict[str, Any]) -> str:
    if str(batch_verify.get("manifest_load_status", "")).strip() != "ok":
        return "unknown"
    if str(batch_verify.get("authority_schema_status", "")).strip() != "current":
        return "unknown"
    if int(batch_verify.get("missing_artifact_count", 0) or 0):
        return "missing"
    if int(batch_verify.get("mismatch_count", 0) or 0):
        return "mismatch"
    return "match"


def _semantic_release_status(closeout: dict[str, Any], batch_manifest: dict[str, Any]) -> str:
    value = str(release_status_v2_view(batch_manifest)["semantic_release_status"])
    if value != "unknown":
        return value
    return str(_closeout_status_view(closeout)["semantic_release_status"])


def _closeout_status_view(closeout: dict[str, Any]) -> dict[str, Any]:
    return release_status_v2_view_with_readiness_fallback(closeout)


def _closeout_machine_release_allowed(closeout: dict[str, Any]) -> bool:
    view = _closeout_status_view(closeout)
    blocker_reason_ids = {str(reason) for reason in view["blocker_reason_ids"]}
    return (
        str(view["release_authority_status"]) == "clean_pass"
        and REASON_MACHINE_RELEASE_NOT_ALLOWED not in blocker_reason_ids
    )


def _closeout_operator_release_allowed(closeout: dict[str, Any]) -> bool:
    return str(_closeout_status_view(closeout)["release_authority_status"]) in {
        "clean_pass",
        "conditional_pass",
    }


def _accepted_risk_count_source(
    *,
    source_artifact: str,
    source_path: str,
    field_path: str,
    aggregation_rule: str,
    included_scopes: list[str],
    excluded_scopes: list[str],
) -> dict[str, Any]:
    return {
        "source_artifact": source_artifact,
        "source_path": source_path,
        "field_path": field_path,
        "aggregation_rule": aggregation_rule,
        "included_scopes": included_scopes,
        "excluded_scopes": excluded_scopes,
    }


def _accepted_risk_count_sources() -> dict[str, Any]:
    return {
        "operator_accepted_risk_family_count": _accepted_risk_count_source(
            source_artifact="release_closeout_summary",
            source_path=DEFAULT_CLOSEOUT,
            field_path="$.summary.accepted_risk_family_count",
            aggregation_rule="distinct accepted risk families across all accepted-risk scopes",
            included_scopes=[
                "policy",
                "test_deselection_policy",
                "operator_signoff",
                "upstream_report",
            ],
            excluded_scopes=[],
        ),
        "clean_lane_blocking_accepted_risk_family_count": _accepted_risk_count_source(
            source_artifact="release_closeout_summary",
            source_path=DEFAULT_CLOSEOUT,
            field_path="$.clean_lane_blocking_risk_family_count",
            aggregation_rule="accepted risk families that still block the clean release lane",
            included_scopes=["policy", "test_deselection_policy"],
            excluded_scopes=["operator_signoff", "upstream_report"],
        ),
        "accepted_risk_count": _accepted_risk_count_source(
            source_artifact="release_closeout_batch_manifest",
            source_path=DEFAULT_BATCH_MANIFEST,
            field_path="$.release_decision_snapshot.accepted_risk_count",
            aggregation_rule="accepted risk instances copied from release closeout; excludes non-risk gate attention",
            included_scopes=["accepted_risks"],
            excluded_scopes=["release_dashboard_gate_attention"],
        ),
        "release_accepted_risk_count": _accepted_risk_count_source(
            source_artifact="release_closeout_batch_manifest",
            source_path=DEFAULT_BATCH_MANIFEST,
            field_path="$.release_decision_snapshot.accepted_risk_count",
            aggregation_rule="release accepted risk instances only; excludes learning-readiness accepted risk state",
            included_scopes=["release_accepted_risks"],
            excluded_scopes=["learning_readiness_accepted_risk"],
        ),
        "accepted_learning_risk_count": _accepted_risk_count_source(
            source_artifact="learning_readiness_signoff_revalidation",
            source_path=DEFAULT_LEARNING_REVALIDATION,
            field_path="$.closeout.accepted_learning_risk",
            aggregation_rule="boolean learning-readiness accepted risk converted to a 0/1 learning-only count",
            included_scopes=["learning_readiness_accepted_risk"],
            excluded_scopes=["release_accepted_risks"],
        ),
        "gate_attention_count": _accepted_risk_count_source(
            source_artifact="release_closeout_batch_manifest",
            source_path=DEFAULT_BATCH_MANIFEST,
            field_path="$.release_decision_snapshot.gate_attention_count",
            aggregation_rule="dashboard gates in attention state; not an accepted-risk count",
            included_scopes=["release_dashboard_gate_attention"],
            excluded_scopes=["accepted_risks"],
        ),
        "learning_claim_blocking_family_count": _accepted_risk_count_source(
            source_artifact="release_closeout_batch_manifest",
            source_path=DEFAULT_BATCH_MANIFEST,
            field_path="$.release_decision_snapshot.learning_claim_blocking_family_count",
            aggregation_rule="accepted risk families that block learning-improvement claims",
            included_scopes=["learning_lane_effect=blocks_learning_claim"],
            excluded_scopes=["clean_lane_effect=blocks_clean_lane"],
        ),
        "advisory_lifecycle_family_count": _accepted_risk_count_source(
            source_artifact="release_closeout_batch_manifest",
            source_path=DEFAULT_BATCH_MANIFEST,
            field_path="$.release_decision_snapshot.advisory_lifecycle_family_count",
            aggregation_rule="accepted risk families that represent advisory review backlog",
            included_scopes=["advisory_lifecycle_effect=review_backlog"],
            excluded_scopes=["clean_lane_effect=blocks_clean_lane"],
        ),
    }


def _scope_count(closeout: dict[str, Any], key: str) -> int:
    counts = closeout.get("accepted_risk_count_by_scope", {})
    if not isinstance(counts, dict):
        return 0
    return int(counts.get(key, 0) or 0)


def _sealed_release_status(batch_manifest: dict[str, Any], batch_verify: dict[str, Any]) -> str:
    if batch_verify["tmp_json_count"]:
        return "blocked_tmp_json"
    if batch_verify["mismatch_count"] or batch_verify["missing_artifact_count"]:
        return "unsealed_mismatch"
    value = str(release_status_v2_view(batch_manifest)["sealed_release_status"])
    if value in {"sealed_clean_pass", "sealed_conditional_pass"}:
        distribution = batch_manifest.get("distribution_package", {})
        if not isinstance(distribution, dict):
            return "unsealed_distribution_not_provided"
        distribution_status = str(distribution.get("status", "not_provided")).strip() or "not_provided"
        if distribution_status == "not_provided":
            return "unsealed_distribution_not_provided"
        if distribution_status == "invalid":
            return "unsealed_distribution_invalid"
        if distribution_status != "materialized":
            return "unsealed_distribution_drift"
        if not bool(distribution.get("path_set_matches_release_manifest")):
            return "unsealed_distribution_drift"
        if not bool(distribution.get("content_digest_matches_release_manifest")):
            return "unsealed_distribution_drift"
    if value:
        return value
    if not batch_manifest:
        return "unsealed_missing_manifest"
    return "sealed_clean_pass" if batch_verify["status"] == "pass" else "unsealed_mismatch"


def _release_package_mode(batch_manifest: dict[str, Any]) -> str:
    distribution = batch_manifest.get("distribution_package", {})
    if isinstance(distribution, dict):
        value = str(distribution.get("archive_profile", "")).strip()
        if value:
            return value
    return "local_workspace"


def _source_zip(vault: Path, batch_manifest: dict[str, Any], load_status: str) -> dict[str, Any]:
    distribution = batch_manifest.get("distribution_package", {})
    empty_file_identity = {
        "actual_sha256": "",
        "file_exists": False,
        "file_digest_matches_batch": False,
    }
    if load_status != "ok":
        return {
            "status": "unknown",
            "distribution_status": "unknown",
            "archive_profile": "unknown",
            "path": "",
            "sha256": "",
            **empty_file_identity,
            "entry_count": 0,
            "path_set_matches_release_manifest": False,
            "content_digest_matches_release_manifest": False,
            "summary": "release batch manifest is missing or unreadable",
        }
    if not isinstance(distribution, dict):
        return {
            "status": "not_provided",
            "distribution_status": "not_provided",
            "archive_profile": "local_workspace",
            "path": "",
            "sha256": "",
            **empty_file_identity,
            "entry_count": 0,
            "path_set_matches_release_manifest": False,
            "content_digest_matches_release_manifest": False,
            "summary": "distribution_package is missing from release batch manifest",
        }

    distribution_status = str(distribution.get("status", "not_provided")).strip() or "not_provided"
    path_matches = bool(distribution.get("path_set_matches_release_manifest"))
    content_matches = bool(distribution.get("content_digest_matches_release_manifest"))
    rel_path = str(distribution.get("path", "")).strip()
    expected_sha256 = str(distribution.get("sha256", "")).strip()
    zip_path = vault / rel_path if rel_path else Path()
    file_exists = bool(rel_path) and zip_path.is_file()
    actual_sha256 = _sha256_file(zip_path) if file_exists else ""
    file_digest_matches_batch = bool(expected_sha256) and actual_sha256 == expected_sha256
    if distribution_status == "materialized" and path_matches and content_matches and file_digest_matches_batch:
        status = "match"
    elif distribution_status == "not_provided":
        status = "not_provided"
    elif distribution_status == "invalid":
        status = "invalid"
    else:
        status = "drift"

    return {
        "status": status,
        "distribution_status": distribution_status,
        "archive_profile": str(distribution.get("archive_profile", "unknown")).strip() or "unknown",
        "path": rel_path,
        "sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "file_exists": file_exists,
        "file_digest_matches_batch": file_digest_matches_batch,
        "entry_count": int(distribution.get("entry_count", 0) or 0),
        "path_set_matches_release_manifest": path_matches,
        "content_digest_matches_release_manifest": content_matches,
        "summary": (
            f"source_zip={status}; distribution_status={distribution_status}; "
            f"path_matches={path_matches}; content_matches={content_matches}; "
            f"file_digest_matches_batch={file_digest_matches_batch}"
        ),
    }


def _test_scope(test_summary: dict[str, Any], full_test_summary: dict[str, Any], full_load_status: str) -> dict[str, Any]:
    primary_scope = str(test_summary.get("suite_scope", "unknown")).strip() or "unknown"
    primary_represents_full = bool(test_summary.get("represents_full_suite"))
    full_represents = bool(full_test_summary.get("represents_full_suite"))
    full_status = str(full_test_summary.get("status", "")).strip()
    full_evidence = full_test_summary.get("full_suite_evidence", {})
    full_evidence = full_evidence if isinstance(full_evidence, dict) else {}
    full_reason = str(full_evidence.get("reason", "")).strip()
    if full_load_status != "ok":
        full_suite_status = "not_run"
        full_reason = f"full-suite summary artifact is missing or unreadable: {full_load_status}"
    elif full_represents and full_status == "pass":
        full_suite_status = "pass"
        full_reason = full_reason or "full-suite summary loaded and represents the full pytest suite"
    elif full_represents:
        full_suite_status = full_status or "unknown"
        full_reason = full_reason or f"full-suite summary represents the full suite with status={full_suite_status}"
    else:
        full_suite_status = "not_represented"
        full_reason = full_reason or "loaded full-suite summary does not represent the full pytest suite"
    return {
        "primary_suite": str(test_summary.get("suite", "unknown")).strip() or "unknown",
        "primary_suite_scope": primary_scope,
        "primary_represents_full_suite": primary_represents_full,
        "primary_status": str(test_summary.get("status", "unknown")).strip() or "unknown",
        "primary_passed_count": int(test_summary.get("counts", {}).get("passed", 0))
        if isinstance(test_summary.get("counts"), dict)
        else 0,
        "full_suite_status": full_suite_status,
        "full_suite_summary_load_status": full_load_status,
        "full_suite_reason": full_reason,
    }


def _learning_revalidation(revalidation: dict[str, Any], load_status: str) -> dict[str, Any]:
    release_effect = revalidation.get("release_effect")
    release_effect = release_effect if isinstance(release_effect, dict) else {}
    nested_revalidation = revalidation.get("revalidation")
    nested_revalidation = nested_revalidation if isinstance(nested_revalidation, dict) else {}
    closeout = revalidation.get("closeout")
    closeout = closeout if isinstance(closeout, dict) else {}
    revalidation_status = str(nested_revalidation.get("status", "unknown")).strip() or "unknown"
    closeout_status_view = _closeout_status_view(closeout)
    closeout_state = str(closeout_status_view["release_authority_status"])
    machine_release_allowed = _closeout_machine_release_allowed(closeout)
    operator_release_allowed = _closeout_operator_release_allowed(closeout)
    operator_summary = str(release_effect.get("operator_summary", "")).strip()
    if not operator_summary:
        operator_summary = (
            f"learning revalidation={revalidation_status}; release_authority_status={closeout_state}; "
            f"machine_release_allowed={machine_release_allowed}; "
            f"operator_release_allowed={operator_release_allowed}"
        )
    return {
        "load_status": load_status,
        "status": str(revalidation.get("status", "unknown")).strip() or "unknown",
        "revalidation_status": revalidation_status,
        "accepted_learning_risk": bool(closeout.get("accepted_learning_risk")),
        "release_effect": {
            "clean_release_effect": str(release_effect.get("clean_release_effect", "conditional_operator_accepted")).strip()
            or "conditional_operator_accepted",
            "operator_summary": operator_summary,
        },
    }


def _confirmed_evidence_summary(value: object, blocking_ids: list[str]) -> dict[str, Any]:
    summary = value if isinstance(value, dict) else {}
    evidence_status = (
        str(
            summary.get(
                "evidence_cohort_status",
                summary.get("confirmed_evidence_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )
    legacy_summary = summary.get("legacy_reconstruction_summary")
    return {
        "evidence_cohort_status": evidence_status,
        "confirmed_evidence_status": evidence_status,
        "valid_run_count": int(summary.get("valid_run_count", 0) or 0),
        "min_required_run_count": int(summary.get("min_required_run_count", 0) or 0),
        "eligible_family_count": int(summary.get("eligible_family_count", 0) or 0),
        "selected_valid_run_ids": [
            str(item).strip()
            for item in summary.get("selected_valid_run_ids", [])
            if str(item).strip()
        ],
        "blocking_predicate_ids": [
            str(item).strip()
            for item in summary.get("blocking_predicate_ids", blocking_ids)
            if str(item).strip()
        ],
        "rejected_run_count": int(summary.get("rejected_run_count", 0) or 0),
        "rejected_run_diagnostics": [
            item for item in summary.get("rejected_run_diagnostics", []) if isinstance(item, dict)
        ],
        "legacy_reconstruction_summary": legacy_summary
        if isinstance(legacy_summary, dict)
        else {
            "status": "not_used",
            "reconstruction_needed_count": 0,
            "reconstructed_run_count": 0,
            "blocked_run_count": 0,
            "run_diagnostics": [],
        },
    }


def _confirmed_predicate_results(unlock: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": str(item.get("id", "")).strip(),
            "status": str(item.get("status", "")).strip(),
            "source_path": str(item.get("source_path", "")).strip(),
            "observed_value": str(item.get("observed_value", "")).strip(),
        }
        for item in unlock.get("confirmed_predicate_results", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    ]


def _confirmed_blocking_predicate_ids(
    summary: dict[str, Any],
    predicates: list[dict[str, str]],
) -> list[str]:
    blocking_ids = [
        str(item).strip()
        for item in summary.get("confirmed_blocking_predicate_ids", [])
        if str(item).strip()
    ]
    return blocking_ids or [
        str(item["id"])
        for item in predicates
        if str(item.get("status", "")).strip() != "pass"
    ]


def _learning_claim_artifact_statuses(
    summary: dict[str, Any],
    unlock: dict[str, Any],
) -> dict[str, str]:
    return {
        "bundle_status": str(
            summary.get(
                "learning_claim_evidence_bundle_status",
                unlock.get("bundle_status", "not_evaluated"),
            )
        ).strip()
        or "not_evaluated",
        "bundle_sha256": str(
            summary.get("learning_claim_evidence_bundle_sha256", unlock.get("bundle_sha256", ""))
        ).strip(),
        "cohort_status": str(
            summary.get(
                "learning_confirmed_evidence_cohort_status",
                unlock.get("confirmed_evidence_cohort_status", "not_evaluated"),
            )
        ).strip()
        or "not_evaluated",
        "cohort_sha256": str(
            summary.get(
                "learning_confirmed_evidence_cohort_sha256",
                unlock.get("confirmed_evidence_cohort_sha256", ""),
            )
        ).strip(),
    }


def _confirmed_wording_policy(
    *,
    claim_level: str,
    summary: dict[str, Any],
    confirmed_status: str,
    confirmed_summary: dict[str, Any],
    artifact_statuses: dict[str, str],
    blocking_ids: list[str],
) -> tuple[bool, str, str]:
    allowed = (
        claim_level == "confirmed_learning_improvement"
        and bool(summary.get("confirmed_learning_improvement_allowed"))
        and confirmed_status == "auto_confirmed"
        and confirmed_summary["confirmed_evidence_status"] == "auto_confirmed"
        and artifact_statuses["bundle_status"] == "active"
        and artifact_statuses["cohort_status"] == "active"
        and not blocking_ids
    )
    if allowed:
        return (
            True,
            "pre_seal_ready",
            "confirmed wording is pre-seal ready; release sidecar must still bind post-seal attestation",
        )
    return (
        False,
        "blocked",
        (
            f"confirmed wording blocked: claim_level={claim_level}; "
            f"confirmed_status={confirmed_status}; bundle={artifact_statuses['bundle_status']}; "
            f"cohort={artifact_statuses['cohort_status']}; "
            f"blockers={','.join(blocking_ids) or 'none'}"
        ),
    )


def _learning_claim_operator_summary(
    *,
    claim_level: str,
    summary: dict[str, Any],
    confirmed_summary: dict[str, Any],
    blocking_ids: list[str],
) -> str:
    legacy_summary = confirmed_summary["legacy_reconstruction_summary"]
    return (
        f"claim_level={claim_level}; "
        f"bounded={bool(summary.get('bounded_learning_claim_allowed'))}; "
        f"confirmed_learning={confirmed_summary['confirmed_evidence_status']}; "
        f"valid_runs={confirmed_summary['valid_run_count']}/{confirmed_summary['min_required_run_count']}; "
        f"eligible_families={confirmed_summary['eligible_family_count']}; "
        f"rejected_runs={confirmed_summary['rejected_run_count']}; "
        f"legacy_reconstruction={legacy_summary['status']}; "
        f"legacy_reconstructed_runs={legacy_summary['reconstructed_run_count']}/"
        f"{legacy_summary['reconstruction_needed_count']}; "
        f"confirmed_blockers={','.join(blocking_ids) or 'none'}"
    )


def _learning_claim_summary(scoreboard: dict[str, Any], load_status: str) -> dict[str, Any]:
    if load_status != "ok":
        confirmed_summary = _confirmed_evidence_summary({}, [])
        return {
            "load_status": load_status,
            "claim_level": "none",
            "bounded_learning_claim_allowed": False,
            "confirmed_learning_improvement_allowed": False,
            "improvement_claim_status": "not_ready",
            "confirmed_learning_improvement_status": "not_ready",
            "evidence_cohort_status": "not_ready",
            "learning_claim_blocker_status": "not_evaluated",
            "confirmed_blocking_predicate_ids": [],
            "confirmed_evidence_summary": confirmed_summary,
            "confirmed_predicate_results": [],
            "learning_claim_evidence_bundle_status": "not_evaluated",
            "learning_claim_evidence_bundle_sha256": "",
            "learning_confirmed_evidence_cohort_status": "not_evaluated",
            "learning_confirmed_evidence_cohort_sha256": "",
            "claim_wording_allowed": False,
            "claim_wording_policy_status": "blocked",
            "confirmed_wording_allowed": False,
            "confirmed_wording_policy_status": "blocked",
            "confirmed_wording_policy_reason": "learning delta scoreboard is unavailable",
            "summary": f"learning delta scoreboard load_status={load_status}",
        }
    summary_payload = scoreboard.get("summary")
    summary: dict[str, Any] = summary_payload if isinstance(summary_payload, dict) else {}
    unlock_payload = scoreboard.get("learning_claim_unlock_review")
    unlock: dict[str, Any] = unlock_payload if isinstance(unlock_payload, dict) else {}
    predicates = _confirmed_predicate_results(unlock)
    blocking_ids = _confirmed_blocking_predicate_ids(summary, predicates)
    confirmed_status = (
        str(
            summary.get(
                "improvement_claim_status",
                summary.get("confirmed_learning_improvement_status", "not_ready"),
            )
        ).strip()
        or "not_ready"
    )
    claim_level = str(summary.get("claim_level", "none")).strip() or "none"
    confirmed_summary_payload = scoreboard.get("confirmed_evidence_summary")
    if not isinstance(confirmed_summary_payload, dict):
        confirmed_summary_payload = unlock.get("confirmed_evidence_summary")
    confirmed_summary = _confirmed_evidence_summary(confirmed_summary_payload, blocking_ids)
    evidence_cohort_status = str(
        summary.get(
            "evidence_cohort_status",
            confirmed_summary.get("evidence_cohort_status", "not_ready"),
        )
    ).strip() or "not_ready"
    has_confirmed_predicates = bool(predicates)
    blocker_status = (
        str(
            summary.get(
                "learning_claim_blocker_status",
                learning_claim_blocker_status(blocking_ids)
                if has_confirmed_predicates
                else "not_evaluated",
            )
        ).strip()
        or ("clear" if has_confirmed_predicates else "not_evaluated")
    )
    artifact_statuses = _learning_claim_artifact_statuses(summary, unlock)
    confirmed_wording_allowed, policy_status, policy_reason = _confirmed_wording_policy(
        claim_level=claim_level,
        summary=summary,
        confirmed_status=confirmed_status,
        confirmed_summary=confirmed_summary,
        artifact_statuses=artifact_statuses,
        blocking_ids=blocking_ids,
    )
    return {
        "load_status": load_status,
        "claim_level": claim_level,
        "bounded_learning_claim_allowed": bool(summary.get("bounded_learning_claim_allowed")),
        "confirmed_learning_improvement_allowed": bool(
            summary.get("confirmed_learning_improvement_allowed")
        ),
        "improvement_claim_status": confirmed_status,
        "confirmed_learning_improvement_status": confirmed_status,
        "evidence_cohort_status": evidence_cohort_status,
        "learning_claim_blocker_status": blocker_status,
        "confirmed_blocking_predicate_ids": blocking_ids,
        "confirmed_evidence_summary": confirmed_summary,
        "confirmed_predicate_results": predicates,
        "learning_claim_evidence_bundle_status": artifact_statuses["bundle_status"],
        "learning_claim_evidence_bundle_sha256": artifact_statuses["bundle_sha256"],
        "learning_confirmed_evidence_cohort_status": artifact_statuses["cohort_status"],
        "learning_confirmed_evidence_cohort_sha256": artifact_statuses["cohort_sha256"],
        "claim_wording_allowed": bool(
            summary.get("claim_wording_allowed", confirmed_wording_allowed)
        ),
        "claim_wording_policy_status": str(
            summary.get("claim_wording_policy_status", policy_status)
        ).strip()
        or policy_status,
        "confirmed_wording_allowed": confirmed_wording_allowed,
        "confirmed_wording_policy_status": policy_status,
        "confirmed_wording_policy_reason": policy_reason,
        "summary": _learning_claim_operator_summary(
            claim_level=claim_level,
            summary=summary,
            confirmed_summary=confirmed_summary,
            blocking_ids=blocking_ids,
        ),
    }


_BUILD_REPORT_KWARGS = {
    "closeout_path",
    "batch_manifest_path",
    "self_check_path",
    "test_summary_path",
    "full_test_summary_path",
    "learning_revalidation_path",
    "learning_delta_scoreboard_path",
    "context",
    "policy_path",
    "source_command",
}


def _text_kw(legacy_kwargs: dict[str, Any], name: str, default: str) -> str:
    value = legacy_kwargs.get(name, default)
    return default if value is None else str(value)


def _operator_release_summary_request(
    request: OperatorReleaseSummaryRequest | None,
    legacy_kwargs: dict[str, Any],
) -> OperatorReleaseSummaryRequest:
    if request is not None:
        if legacy_kwargs:
            names = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"build_report request cannot be combined with legacy keyword arguments: {names}")
        if not isinstance(request, OperatorReleaseSummaryRequest):
            raise TypeError("build_report request must be an OperatorReleaseSummaryRequest")
        return request

    extra = set(legacy_kwargs) - _BUILD_REPORT_KWARGS
    if extra:
        raise TypeError(f"unexpected keyword arguments: {', '.join(sorted(extra))}")
    context = legacy_kwargs.get("context")
    if context is not None and not isinstance(context, RuntimeContext):
        raise TypeError("build_report context must be a RuntimeContext")
    return OperatorReleaseSummaryRequest(
        closeout_path=_text_kw(legacy_kwargs, "closeout_path", DEFAULT_CLOSEOUT),
        batch_manifest_path=_text_kw(legacy_kwargs, "batch_manifest_path", DEFAULT_BATCH_MANIFEST),
        self_check_path=_text_kw(legacy_kwargs, "self_check_path", DEFAULT_SELF_CHECK),
        test_summary_path=_text_kw(legacy_kwargs, "test_summary_path", DEFAULT_TEST_SUMMARY),
        full_test_summary_path=_text_kw(legacy_kwargs, "full_test_summary_path", DEFAULT_FULL_TEST_SUMMARY),
        learning_revalidation_path=_text_kw(
            legacy_kwargs,
            "learning_revalidation_path",
            DEFAULT_LEARNING_REVALIDATION,
        ),
        learning_delta_scoreboard_path=_text_kw(
            legacy_kwargs,
            "learning_delta_scoreboard_path",
            DEFAULT_LEARNING_DELTA_SCOREBOARD,
        ),
        context=context,
        policy_path=None
        if legacy_kwargs.get("policy_path") is None
        else str(legacy_kwargs["policy_path"]),
        source_command=_text_kw(legacy_kwargs, "source_command", SOURCE_COMMAND),
    )


def _load_operator_source_reports(
    vault: Path,
    request: OperatorReleaseSummaryRequest,
) -> OperatorSourceReports:
    closeout, closeout_load_status = _load_optional(vault, request.closeout_path)
    batch_manifest, batch_manifest_load_status = _load_optional(vault, request.batch_manifest_path)
    self_check, self_check_load_status = _load_optional(vault, request.self_check_path)
    test_summary, test_summary_load_status = _load_optional(vault, request.test_summary_path)
    full_test_summary, full_test_summary_load_status = _load_optional(
        vault,
        request.full_test_summary_path,
    )
    learning_revalidation, learning_revalidation_load_status = _load_optional(
        vault,
        request.learning_revalidation_path,
    )
    learning_scoreboard, learning_scoreboard_load_status = _load_optional(
        vault,
        request.learning_delta_scoreboard_path,
    )
    return OperatorSourceReports(
        closeout=closeout,
        closeout_load_status=closeout_load_status,
        batch_manifest=batch_manifest,
        batch_manifest_load_status=batch_manifest_load_status,
        self_check=self_check,
        self_check_load_status=self_check_load_status,
        test_summary=test_summary,
        test_summary_load_status=test_summary_load_status,
        full_test_summary=full_test_summary,
        full_test_summary_load_status=full_test_summary_load_status,
        learning_revalidation=learning_revalidation,
        learning_revalidation_load_status=learning_revalidation_load_status,
        learning_scoreboard=learning_scoreboard,
        learning_scoreboard_load_status=learning_scoreboard_load_status,
    )


def _release_decision_snapshot(batch_manifest: dict[str, Any]) -> dict[str, Any]:
    snapshot = batch_manifest.get("release_decision_snapshot", {})
    return snapshot if isinstance(snapshot, dict) else {}


def _accepted_risk_summary(
    closeout: dict[str, Any],
    release_decision_snapshot: dict[str, Any],
    learning_readiness: dict[str, Any],
) -> dict[str, Any]:
    closeout_summary = closeout.get("summary", {})
    closeout_summary = closeout_summary if isinstance(closeout_summary, dict) else {}
    operator_count = int(closeout_summary.get("accepted_risk_family_count", 0) or 0)
    v2_machine_release_allowed = _closeout_machine_release_allowed(closeout)
    clean_lane_blocking_count = int(
        closeout.get(
            "clean_lane_blocking_risk_family_count",
            0 if v2_machine_release_allowed else operator_count,
        )
        or 0
    )
    accepted_risk_count = int(
        release_decision_snapshot.get(
            "accepted_risk_count",
            closeout_summary.get("accepted_risk_instance_count", 0),
        )
        or 0
    )
    release_blocking_count = int(_scope_count(closeout, "release_blocking_family_count") or 0)
    release_accepted_risk_count = max(clean_lane_blocking_count, release_blocking_count)
    return {
        "operator_accepted_risk_family_count": operator_count,
        "clean_lane_blocking_accepted_risk_family_count": clean_lane_blocking_count,
        "accepted_risk_count": accepted_risk_count,
        "release_accepted_risk_count": release_accepted_risk_count,
        "accepted_learning_risk_count": 1 if learning_readiness["accepted_learning_risk"] else 0,
        "gate_attention_count": int(release_decision_snapshot.get("gate_attention_count", 0) or 0),
        "learning_claim_blocking_family_count": int(
            release_decision_snapshot.get(
                "learning_claim_blocking_family_count",
                _scope_count(closeout, "learning_claim_blocking_family_count"),
            )
            or 0
        ),
        "advisory_lifecycle_family_count": int(
            release_decision_snapshot.get(
                "advisory_lifecycle_family_count",
                _scope_count(closeout, "advisory_lifecycle_family_count"),
            )
            or 0
        ),
        "count_sources": _accepted_risk_count_sources(),
    }


def _operator_report_status(
    *,
    semantic_release_status: str,
    sealed_release_status: str,
    source_zip: dict[str, Any],
    batch_verify: dict[str, Any],
    self_check_status: str,
    test_evidence: dict[str, Any],
) -> str:
    if (
        semantic_release_status == "clean_pass"
        and sealed_release_status == "sealed_clean_pass"
        and source_zip["status"] in {"match", "not_provided"}
        and batch_verify["status"] == "pass"
        and self_check_status in {"pass", "unknown"}
        and test_evidence["full_suite_status"] == "pass"
    ):
        return "pass"
    return "attention"


def _operator_release_signals(
    vault: Path,
    sources: OperatorSourceReports,
) -> OperatorReleaseSignals:
    batch_verify = _batch_verify_snapshot(
        vault,
        sources.batch_manifest,
        sources.batch_manifest_load_status,
    )
    semantic_release_status = _semantic_release_status(sources.closeout, sources.batch_manifest)
    sealed_release_status = _sealed_release_status(sources.batch_manifest, batch_verify)
    source_zip = _source_zip(vault, sources.batch_manifest, sources.batch_manifest_load_status)
    test_evidence = _test_scope(
        sources.test_summary,
        sources.full_test_summary,
        sources.full_test_summary_load_status,
    )
    learning_readiness = _learning_revalidation(
        sources.learning_revalidation,
        sources.learning_revalidation_load_status,
    )
    learning_claim = _learning_claim_summary(
        sources.learning_scoreboard,
        sources.learning_scoreboard_load_status,
    )
    release_snapshot = _release_decision_snapshot(sources.batch_manifest)
    accepted_risk = _accepted_risk_summary(sources.closeout, release_snapshot, learning_readiness)
    self_check_status = str(sources.self_check.get("status", {}).get("result", "unknown")).strip()
    return OperatorReleaseSignals(
        batch_verify=batch_verify,
        artifact_digest_policy_status=_artifact_digest_policy_status(batch_verify),
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        source_zip=source_zip,
        self_check_status=self_check_status,
        test_evidence=test_evidence,
        learning_readiness=learning_readiness,
        learning_claim=learning_claim,
        accepted_risk=accepted_risk,
        auto_improve_lane_status=str(
            release_snapshot.get("auto_improve_lane_status", "unknown")
        ).strip()
        or "unknown",
        status=_operator_report_status(
            semantic_release_status=semantic_release_status,
            sealed_release_status=sealed_release_status,
            source_zip=source_zip,
            batch_verify=batch_verify,
            self_check_status=self_check_status,
            test_evidence=test_evidence,
        ),
    )


def _operator_source_load_status(sources: OperatorSourceReports) -> dict[str, str]:
    return {
        "closeout": sources.closeout_load_status,
        "batch_manifest": sources.batch_manifest_load_status,
        "self_check": sources.self_check_load_status,
        "test_summary": sources.test_summary_load_status,
        "full_test_summary": sources.full_test_summary_load_status,
        "learning_revalidation": sources.learning_revalidation_load_status,
        "learning_delta_scoreboard": sources.learning_scoreboard_load_status,
    }


def _operator_summary_text(signals: OperatorReleaseSignals) -> str:
    claim_summary = signals.learning_claim["confirmed_evidence_summary"]
    legacy_summary = claim_summary["legacy_reconstruction_summary"]
    accepted_risk = signals.accepted_risk
    return (
        f"semantic={signals.semantic_release_status}; sealed={signals.sealed_release_status}; "
        f"source_zip={signals.source_zip['status']}; "
        f"artifact_digest={signals.artifact_digest_policy_status}; "
        f"artifact_mismatches={signals.batch_verify['mismatch_count']}; "
        f"tmp_json={signals.batch_verify['tmp_json_count']}; "
        f"full_suite={signals.test_evidence['full_suite_status']}; "
        f"auto_improve_lane={signals.auto_improve_lane_status}; "
        f"learning_revalidation={signals.learning_readiness['revalidation_status']}; "
        f"confirmed_learning={claim_summary['confirmed_evidence_status']}; "
        f"valid_runs={claim_summary['valid_run_count']}/{claim_summary['min_required_run_count']}; "
        f"eligible_families={claim_summary['eligible_family_count']}; "
        f"rejected_runs={claim_summary['rejected_run_count']}; "
        f"legacy_reconstruction={legacy_summary['status']}; "
        f"legacy_reconstructed_runs={legacy_summary['reconstructed_run_count']}/"
        f"{legacy_summary['reconstruction_needed_count']}; "
        f"confirmed_blockers={','.join(signals.learning_claim['confirmed_blocking_predicate_ids']) or 'none'}; "
        f"release_risk_acceptances={accepted_risk['release_accepted_risk_count']}; "
        f"learning_risk_acceptances={accepted_risk['accepted_learning_risk_count']}; "
        f"gate_attention={accepted_risk['gate_attention_count']}; "
        f"learning_claim_blocking={accepted_risk['learning_claim_blocking_family_count']}; "
        f"advisory_lifecycle={accepted_risk['advisory_lifecycle_family_count']}"
    )


def _render_operator_release_summary(inputs: OperatorReleaseRenderInputs) -> dict[str, Any]:
    request = inputs.request
    signals = inputs.signals
    batch_verify = signals.batch_verify
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.generated_at,
            artifact_kind="operator_release_summary",
            producer=PRODUCER,
            source_command=request.source_command,
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=OPERATOR_RELEASE_SUMMARY_SCHEMA_PATH,
            source_paths=["ops/scripts/release/operator_release_summary.py"],
            file_inputs={
                "closeout": request.closeout_path,
                "batch_manifest": request.batch_manifest_path,
                "self_check": request.self_check_path,
                "test_summary": request.test_summary_path,
                "full_test_summary": request.full_test_summary_path,
                "learning_revalidation": request.learning_revalidation_path,
                "learning_delta_scoreboard": request.learning_delta_scoreboard_path,
            },
        ),
        "vault": report_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "status": signals.status,
        "semantic_release_status": signals.semantic_release_status,
        "sealed_release_status": signals.sealed_release_status,
        "release_package_mode": _release_package_mode(inputs.sources.batch_manifest),
        "source_zip_policy_status": signals.source_zip["status"],
        "source_zip": signals.source_zip,
        "tmp_json_policy_status": "clean" if batch_verify["tmp_json_count"] == 0 else "dirty",
        "tmp_json_count": batch_verify["tmp_json_count"],
        "artifact_digest_policy_status": signals.artifact_digest_policy_status,
        "artifact_digest_mismatch_count": batch_verify["mismatch_count"],
        "artifact_digest_missing_count": batch_verify["missing_artifact_count"],
        "check_mode_write_policy": "check targets must write only tmp diagnostics; canonical writes are promote/build targets",
        "source_load_status": _operator_source_load_status(inputs.sources),
        "batch_verify": batch_verify,
        "test_evidence": signals.test_evidence,
        "learning_readiness": signals.learning_readiness,
        "learning_claim": signals.learning_claim,
        "accepted_risk": signals.accepted_risk,
        "operator_summary": _operator_summary_text(signals),
    }


def build_report(
    vault: Path,
    request: OperatorReleaseSummaryRequest | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    request = _operator_release_summary_request(request, legacy_kwargs)
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    sources = _load_operator_source_reports(vault, request)
    signals = _operator_release_signals(vault, sources)
    return _render_operator_release_summary(
        OperatorReleaseRenderInputs(
            vault=vault,
            request=request,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            generated_at=generated_at,
            sources=sources,
            signals=signals,
        )
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=OPERATOR_RELEASE_SUMMARY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="operator release summary schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build operator release summary")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--closeout", default=DEFAULT_CLOSEOUT)
    parser.add_argument("--batch-manifest", default=DEFAULT_BATCH_MANIFEST)
    parser.add_argument("--self-check", default=DEFAULT_SELF_CHECK)
    parser.add_argument("--test-summary", default=DEFAULT_TEST_SUMMARY)
    parser.add_argument("--full-test-summary", default=DEFAULT_FULL_TEST_SUMMARY)
    parser.add_argument("--learning-revalidation", default=DEFAULT_LEARNING_REVALIDATION)
    parser.add_argument("--learning-delta-scoreboard", default=DEFAULT_LEARNING_DELTA_SCOREBOARD)
    parser.add_argument(
        "--fail-on-attention",
        action="store_true",
        help="Exit nonzero when the summary status is attention.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    source_command = (
        "python -m ops.scripts.operator_release_summary "
        f"--vault {args.vault} --out {args.out} "
        f"--closeout {args.closeout} "
        f"--batch-manifest {args.batch_manifest} "
        f"--self-check {args.self_check} "
        f"--test-summary {args.test_summary} "
        f"--full-test-summary {args.full_test_summary} "
        f"--learning-revalidation {args.learning_revalidation} "
        f"--learning-delta-scoreboard {args.learning_delta_scoreboard}"
    )
    report = build_report(
        vault,
        OperatorReleaseSummaryRequest(
            closeout_path=args.closeout,
            batch_manifest_path=args.batch_manifest,
            self_check_path=args.self_check,
            test_summary_path=args.test_summary,
            full_test_summary_path=args.full_test_summary,
            learning_revalidation_path=args.learning_revalidation,
            learning_delta_scoreboard_path=args.learning_delta_scoreboard,
            source_command=source_command,
        ),
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.fail_on_attention and report["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
