from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    read_json_object,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.release.release_status_v2 import release_status_v2_view

PRODUCER = "ops.scripts.release_post_seal_attestation"
SCHEMA_PATH = "ops/schemas/release-post-seal-attestation.schema.json"
DEFAULT_OUT = "build/release/release-post-seal-attestation.json"
DEFAULT_BATCH_MANIFEST = "build/release/release-closeout-batch-manifest.json"
DEFAULT_SELF_CHECK = "build/release/release-evidence-closeout-self-check.json"
DEFAULT_OPERATOR_SUMMARY = "build/release/operator-release-summary.json"
DEFAULT_LEARNING_CLAIM_EVIDENCE_BUNDLE = "ops/reports/learning-claim-evidence-bundle.json"
DEFAULT_LEARNING_CONFIRMED_EVIDENCE_COHORT = "ops/reports/learning-confirmed-evidence-cohort.json"
DEFAULT_LEARNING_DELTA_SCOREBOARD = "ops/reports/learning-delta-scoreboard.json"
DEFAULT_PUBLIC_CHECK_SUMMARY = "ops/reports/public-check-summary.json"
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"
_LINKED_REPORT_BINDINGS: dict[str, tuple[str, str, str]] = {
    "release_closeout_batch_manifest": (
        DEFAULT_BATCH_MANIFEST,
        "reports.release_closeout_batch_manifest.sha256",
        "release_closeout_batch_manifest_sha256",
    ),
    "release_evidence_closeout_self_check": (
        DEFAULT_SELF_CHECK,
        "reports.release_evidence_closeout_self_check.sha256",
        "release_evidence_closeout_self_check_sha256",
    ),
    "operator_release_summary": (
        DEFAULT_OPERATOR_SUMMARY,
        "reports.operator_release_summary.sha256",
        "operator_release_summary_sha256",
    ),
    "learning_claim_evidence_bundle": (
        DEFAULT_LEARNING_CLAIM_EVIDENCE_BUNDLE,
        "reports.learning_claim_evidence_bundle.sha256",
        "learning_claim_evidence_bundle_sha256",
    ),
    "learning_confirmed_evidence_cohort": (
        DEFAULT_LEARNING_CONFIRMED_EVIDENCE_COHORT,
        "reports.learning_confirmed_evidence_cohort.sha256",
        "learning_confirmed_evidence_cohort_sha256",
    ),
    "learning_delta_scoreboard": (
        DEFAULT_LEARNING_DELTA_SCOREBOARD,
        "reports.learning_delta_scoreboard.sha256",
        "learning_delta_scoreboard_sha256",
    ),
}


@dataclass(frozen=True)
class _AttestationInputs:
    batch_manifest: dict[str, Any]
    self_check: dict[str, Any]
    operator_summary: dict[str, Any]
    learning_claim_evidence_bundle: dict[str, Any]
    learning_confirmed_evidence_cohort: dict[str, Any]
    learning_delta_scoreboard: dict[str, Any]


@dataclass(frozen=True)
class _ReleaseAuthorityStatuses:
    batch_manifest_status: str
    release_authority_status: str
    semantic_release_status: str
    sealed_release_status: str
    machine_release_status: str
    operator_release_status: str
    status_v2_available: bool


@dataclass(frozen=True)
class _ReleaseAuthorityRiskSnapshot:
    accepted_risk_count: int
    release_accepted_risk_count: int
    accepted_learning_risk_count: int
    clean_lane_blocking_count: int
    advisory_lifecycle_count: int


@dataclass(frozen=True)
class _ReleaseAuthorityContext:
    statuses: _ReleaseAuthorityStatuses
    risks: _ReleaseAuthorityRiskSnapshot
    operator_summary_status: str
    self_check_status: str
    full_suite_status: str
    learning_revalidation_status: str
    operator_summary_text: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(vault: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (vault / path).resolve()


def _file_identity(vault: Path, value: str | Path, *, role: str) -> dict[str, Any]:
    path = _resolve(vault, value)
    exists = path.is_file()
    return {
        "role": role,
        "path": report_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
    }


def _report_identity(vault: Path, value: str | Path, *, role: str) -> dict[str, Any]:
    identity = _file_identity(vault, value, role=role)
    payload = read_json_object(_resolve(vault, value)) if identity["exists"] else {}
    identity.update(
        {
            "artifact_kind": str(payload.get("artifact_kind", "")),
            "producer": str(payload.get("producer", "")),
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
        }
    )
    return identity


def _source_zip_self_description(source_zip_path: Path) -> dict[str, Any]:
    if not source_zip_path.is_file():
        return {}
    with zipfile.ZipFile(source_zip_path) as archive:
        candidates = sorted(
            name
            for name in archive.namelist()
            if name.endswith(f"/{ARCHIVE_SELF_DESCRIPTION_PATH}") or name == ARCHIVE_SELF_DESCRIPTION_PATH
        )
        if not candidates:
            return {}
        return json.loads(archive.read(candidates[0]).decode("utf-8"))


def _status_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("result", "")).strip()
    return str(value).strip()


def _dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _int_value(payload: Any) -> int:
    if isinstance(payload, bool):
        return int(payload)
    if isinstance(payload, int):
        return payload
    if isinstance(payload, str) and payload.strip().isdigit():
        return int(payload.strip())
    return 0


def _source_zip_path(batch_manifest: dict[str, Any], operator_summary: dict[str, Any], explicit_path: str) -> str:
    if explicit_path.strip():
        return explicit_path.strip()
    operator_source_zip = _dict(operator_summary.get("source_zip"))
    operator_path = str(operator_source_zip.get("path", "")).strip()
    if operator_path:
        return operator_path
    distribution = _dict(batch_manifest.get("distribution_package"))
    return str(distribution.get("path", "")).strip()


def _verification(
    *,
    source_zip: dict[str, Any],
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    operator_summary: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    pre_seal_post_seal_linkage: dict[str, Any],
    learning_claim_authority: dict[str, Any],
) -> dict[str, Any]:
    source_sha256 = str(source_zip.get("sha256", "")).strip()
    distribution = _dict(batch_manifest.get("distribution_package"))
    operator_source_zip = _dict(operator_summary.get("source_zip"))
    batch_expected_sha256 = str(distribution.get("sha256", "")).strip()
    operator_expected_sha256 = str(operator_source_zip.get("sha256", "")).strip()
    operator_actual_sha256 = str(operator_source_zip.get("actual_sha256", "")).strip()
    batch_watch = _dict(self_check.get("batch_artifact_digest_watch"))
    operator_batch_verify = _dict(operator_summary.get("batch_verify"))
    claim_level = str(learning_claim_authority.get("claim_level", "")).strip()
    operator_bundle_sha = str(
        learning_claim_authority.get("operator_learning_claim_evidence_bundle_sha256", "")
    ).strip()
    operator_cohort_sha = str(
        learning_claim_authority.get("operator_learning_confirmed_evidence_cohort_sha256", "")
    ).strip()
    current_bundle_sha = str(learning_claim_authority.get("learning_claim_evidence_bundle_sha256", "")).strip()
    current_cohort_sha = str(learning_claim_authority.get("learning_confirmed_evidence_cohort_sha256", "")).strip()
    confirmed_status = str(
        learning_claim_authority.get("confirmed_learning_improvement_status", "")
    ).strip()
    distribution_materialized = str(distribution.get("status", "")).strip() == "materialized"
    checks = {
        "batch_manifest_present": bool(reports["release_closeout_batch_manifest"]["exists"]),
        "self_check_present": bool(reports["release_evidence_closeout_self_check"]["exists"]),
        "operator_summary_present": bool(reports["operator_release_summary"]["exists"]),
        "learning_claim_evidence_bundle_present": bool(reports["learning_claim_evidence_bundle"]["exists"]),
        "learning_confirmed_evidence_cohort_present": bool(
            reports["learning_confirmed_evidence_cohort"]["exists"]
        ),
        "learning_delta_scoreboard_present": bool(reports["learning_delta_scoreboard"]["exists"]),
        "source_zip_present_when_materialized": bool(source_zip["exists"]) if distribution_materialized else True,
        "source_zip_matches_batch_distribution": (
            not batch_expected_sha256 or (bool(source_sha256) and source_sha256 == batch_expected_sha256)
        ),
        "source_zip_matches_operator_summary": (
            not operator_expected_sha256
            or (bool(source_sha256) and source_sha256 in {operator_expected_sha256, operator_actual_sha256})
        ),
        "self_check_batch_digest_watch_match": str(batch_watch.get("status", "")).strip() == "match",
        "operator_batch_verify_pass": str(operator_batch_verify.get("status", "")).strip() == "pass",
        "operator_artifact_digest_policy_match": (
            str(operator_summary.get("artifact_digest_policy_status", "")).strip() == "match"
        ),
        "source_zip_self_description_present": (
            str(pre_seal_post_seal_linkage.get("self_description_status", "")).strip() == "present"
        ),
        "pre_seal_post_seal_authoritative_digests_present": (
            int(pre_seal_post_seal_linkage.get("current_missing_count", 0) or 0) == 0
        ),
        "pre_seal_post_seal_required_links_present": (
            int(pre_seal_post_seal_linkage.get("missing_required_link_count", 0) or 0) == 0
        ),
        "pre_seal_post_seal_bindings_match_current": (
            int(pre_seal_post_seal_linkage.get("binding_mismatch_count", 0) or 0) == 0
        ),
        "learning_claim_authority_operator_bundle_digest_match": (
            not operator_bundle_sha or (bool(current_bundle_sha) and operator_bundle_sha == current_bundle_sha)
        ),
        "learning_claim_authority_operator_cohort_digest_match": (
            not operator_cohort_sha or (bool(current_cohort_sha) and operator_cohort_sha == current_cohort_sha)
        ),
        "learning_claim_authority_scoreboard_operator_bundle_digest_match": bool(
            learning_claim_authority.get("scoreboard_operator_bundle_digest_match", False)
        ),
        "learning_claim_authority_scoreboard_operator_cohort_digest_match": bool(
            learning_claim_authority.get("scoreboard_operator_cohort_digest_match", False)
        ),
        "learning_claim_authority_confirmed_evidence_status_auto_confirmed_when_claimed": (
            claim_level != "confirmed_learning_improvement" or confirmed_status == "auto_confirmed"
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }


def _report_binding_sources(
    reports: dict[str, dict[str, Any]],
) -> dict[str, tuple[str, str]]:
    sources: dict[str, tuple[str, str]] = {}
    for report_key, (canonical_path, source_name, _binding_key) in _LINKED_REPORT_BINDINGS.items():
        report = reports[report_key]
        if str(report.get("path", "")).strip() == canonical_path:
            sources[canonical_path] = (source_name, str(report.get("sha256", "")))
        else:
            sources[canonical_path] = ("current_file", "")
    return sources


def _binding_digests(bindings: dict[str, Any], reports: dict[str, dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for report_key, (canonical_path, _source_name, binding_key) in _LINKED_REPORT_BINDINGS.items():
        report = reports[report_key]
        if str(report.get("path", "")).strip() == canonical_path:
            result[canonical_path] = str(bindings.get(binding_key, ""))
    return result


def _source_zip_linkage_payload(source_zip_path: Path) -> tuple[dict[str, Any], str, str]:
    try:
        self_description = _source_zip_self_description(source_zip_path)
    except (
        OSError,
        zipfile.BadZipFile,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        return {}, "unreadable", f"{type(exc).__name__}: {exc}"
    return self_description, "present" if self_description else "missing", ""


def _linkage_artifact_row(
    vault: Path,
    item: dict[str, Any],
    *,
    report_binding_by_path: dict[str, tuple[str, str]],
    binding_by_path: dict[str, str],
) -> tuple[dict[str, Any] | None, str]:
    rel_path = str(item.get("path", "")).strip()
    if not rel_path:
        return None, "skipped"
    pre_seal_sha = str(item.get("sha256", "")).strip()
    current_path = _resolve(vault, rel_path)
    current_sha = _sha256_file(current_path) if current_path.is_file() else ""
    authoritative_source, report_sha = report_binding_by_path.get(
        rel_path,
        ("current_file", ""),
    )
    binding_sha = binding_by_path.get(rel_path, report_sha)
    binding_matches_current = not binding_sha or binding_sha == current_sha
    if not current_sha:
        linkage_status = "current_missing"
    elif not binding_matches_current:
        linkage_status = "binding_mismatch"
    elif pre_seal_sha == current_sha:
        linkage_status = "match"
    else:
        linkage_status = "drift"
    return {
        "path": rel_path,
        "included_in_source_zip": bool(item.get("included_in_zip")),
        "pre_seal_observed_sha256": pre_seal_sha,
        "current_post_seal_sha256": current_sha,
        "authoritative_post_seal_digest_source": authoritative_source,
        "binding_sha256": binding_sha,
        "binding_matches_current": binding_matches_current,
        "linkage_status": linkage_status,
    }, linkage_status


def _pre_seal_post_seal_linkage(
    vault: Path,
    *,
    source_zip: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    bindings: dict[str, Any],
) -> dict[str, Any]:
    source_zip_path_text = str(source_zip.get("path", "")).strip()
    source_zip_path = _resolve(vault, source_zip_path_text) if source_zip_path_text else Path()
    report_binding_by_path = _report_binding_sources(reports)
    binding_by_path = _binding_digests(bindings, reports)
    required_linked_paths = sorted(report_binding_by_path)
    self_description, self_description_status, self_description_error = (
        _source_zip_linkage_payload(source_zip_path)
    )

    linkage = _dict(self_description.get("evidence_linkage"))
    linked_artifacts = linkage.get("linked_artifacts", [])
    linked_artifacts = linked_artifacts if isinstance(linked_artifacts, list) else []
    artifacts: list[dict[str, Any]] = []
    observed_paths: set[str] = set()
    current_missing_count = 0
    drift_count = 0
    binding_mismatch_count = 0
    for item in linked_artifacts:
        if not isinstance(item, dict):
            continue
        row, linkage_status = _linkage_artifact_row(
            vault,
            item,
            report_binding_by_path=report_binding_by_path,
            binding_by_path=binding_by_path,
        )
        if row is None:
            continue
        observed_paths.add(str(row["path"]))
        if linkage_status == "current_missing":
            current_missing_count += 1
        elif linkage_status == "binding_mismatch":
            binding_mismatch_count += 1
        elif linkage_status == "drift":
            drift_count += 1
        artifacts.append(row)

    missing_required_paths = [path for path in required_linked_paths if path not in observed_paths]
    status = (
        "pass"
        if self_description_status == "present"
        and current_missing_count == 0
        and binding_mismatch_count == 0
        and not missing_required_paths
        else "fail"
    )
    return {
        "status": status,
        "self_description_status": self_description_status,
        "self_description_error": self_description_error,
        "linkage_phase": str(linkage.get("linkage_phase", "")),
        "authoritative_post_seal_digest_source": "release_post_seal_attestation.reports_and_current_files",
        "artifact_count": len(artifacts),
        "required_linked_artifact_paths": required_linked_paths,
        "missing_required_linked_artifact_paths": missing_required_paths,
        "missing_required_link_count": len(missing_required_paths),
        "drift_count": drift_count,
        "current_missing_count": current_missing_count,
        "binding_mismatch_count": binding_mismatch_count,
        "artifacts": artifacts,
    }


def _blocking_reason(
    *,
    code: str,
    source: str,
    field_path: str,
    value: str | int | bool,
    release_effect: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "source": source,
        "field_path": field_path,
        "value": value,
        "release_effect": release_effect,
        "summary": summary,
    }


def _release_authority_statuses(
    batch_manifest: dict[str, Any],
) -> _ReleaseAuthorityStatuses:
    status_view = release_status_v2_view(batch_manifest)
    return _ReleaseAuthorityStatuses(
        batch_manifest_status=str(status_view["compatibility_status_value"]),
        release_authority_status=str(status_view["release_authority_status"]),
        semantic_release_status=str(status_view["semantic_release_status"]),
        sealed_release_status=str(status_view["sealed_release_status"]),
        machine_release_status=str(batch_manifest.get("machine_release_status", "")).strip(),
        operator_release_status=str(batch_manifest.get("operator_release_status", "")).strip(),
        status_v2_available=bool(status_view["status_v2_available"]),
    )


def _release_authority_risks(
    batch_manifest: dict[str, Any],
    operator_summary: dict[str, Any],
) -> _ReleaseAuthorityRiskSnapshot:
    accepted_risk = _dict(operator_summary.get("accepted_risk"))
    learning_readiness = _dict(operator_summary.get("learning_readiness"))
    decision = _dict(batch_manifest.get("release_decision_snapshot"))
    accepted_risk_count = _int_value(accepted_risk.get("accepted_risk_count", decision.get("accepted_risk_count", 0)))
    release_accepted_risk_count = _int_value(
        accepted_risk.get(
            "release_accepted_risk_count",
            decision.get("accepted_risk_count", accepted_risk_count),
        )
    )
    accepted_learning_risk_count = _int_value(
        accepted_risk.get(
            "accepted_learning_risk_count",
            1 if bool(learning_readiness.get("accepted_learning_risk")) else 0,
        )
    )
    clean_lane_blocking_count = _int_value(
        accepted_risk.get("clean_lane_blocking_accepted_risk_family_count")
    )
    advisory_lifecycle_count = _int_value(
        accepted_risk.get("advisory_lifecycle_family_count", decision.get("advisory_lifecycle_family_count", 0))
    )
    return _ReleaseAuthorityRiskSnapshot(
        accepted_risk_count=accepted_risk_count,
        release_accepted_risk_count=release_accepted_risk_count,
        accepted_learning_risk_count=accepted_learning_risk_count,
        clean_lane_blocking_count=clean_lane_blocking_count,
        advisory_lifecycle_count=advisory_lifecycle_count,
    )


def _release_authority_context(
    *,
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    operator_summary: dict[str, Any],
) -> _ReleaseAuthorityContext:
    test_evidence = _dict(operator_summary.get("test_evidence"))
    learning_readiness = _dict(operator_summary.get("learning_readiness"))
    return _ReleaseAuthorityContext(
        statuses=_release_authority_statuses(batch_manifest),
        risks=_release_authority_risks(batch_manifest, operator_summary),
        operator_summary_status=str(operator_summary.get("status", "")),
        self_check_status=_status_label(self_check.get("status")),
        full_suite_status=str(test_evidence.get("full_suite_status", "")).strip(),
        learning_revalidation_status=str(
            learning_readiness.get("revalidation_status", "")
        ).strip(),
        operator_summary_text=str(operator_summary.get("operator_summary", "")),
    )


def _legacy_status_blocking_reasons(
    statuses: _ReleaseAuthorityStatuses,
) -> list[dict[str, Any]]:
    blocking_reasons: list[dict[str, Any]] = []
    if (
        statuses.batch_manifest_status
        and statuses.batch_manifest_status != "pass"
        and not statuses.status_v2_available
    ):
        blocking_reasons.append(
            _blocking_reason(
                code="batch_manifest_not_pass",
                source="release_closeout_batch_manifest",
                field_path="$.status",
                value=statuses.batch_manifest_status,
                release_effect="blocks_release_authority",
                summary=f"batch manifest status is {statuses.batch_manifest_status}",
            )
        )
    return blocking_reasons


def _status_axis_blocking_reasons(
    statuses: _ReleaseAuthorityStatuses,
) -> list[dict[str, Any]]:
    blocking_reasons: list[dict[str, Any]] = []
    if statuses.release_authority_status and statuses.release_authority_status != "clean_pass":
        blocking_reasons.append(
            _blocking_reason(
                code="release_authority_not_clean",
                source="release_closeout_batch_manifest",
                field_path="$.release_authority_status",
                value=statuses.release_authority_status,
                release_effect="blocks_release_authority",
                summary=f"release authority status is {statuses.release_authority_status}",
            )
        )
    if statuses.semantic_release_status and statuses.semantic_release_status != "clean_pass":
        blocking_reasons.append(
            _blocking_reason(
                code="semantic_release_not_clean",
                source="release_closeout_batch_manifest",
                field_path="$.semantic_release_status",
                value=statuses.semantic_release_status,
                release_effect="blocks_semantic_release",
                summary=f"semantic release status is {statuses.semantic_release_status}",
            )
        )
    if statuses.sealed_release_status and statuses.sealed_release_status not in {
        "sealed_clean_pass",
        "sealed_conditional_pass",
    }:
        blocking_reasons.append(
            _blocking_reason(
                code="sealed_release_not_sealed",
                source="release_closeout_batch_manifest",
                field_path="$.sealed_release_status",
                value=statuses.sealed_release_status,
                release_effect="blocks_sealed_release",
                summary=f"sealed release status is {statuses.sealed_release_status}",
            )
        )
    if statuses.machine_release_status and statuses.machine_release_status not in {"clean_pass", "allowed"}:
        blocking_reasons.append(
            _blocking_reason(
                code="machine_release_not_allowed",
                source="release_closeout_batch_manifest",
                field_path="$.machine_release_status",
                value=statuses.machine_release_status,
                release_effect="blocks_machine_release",
                summary=f"machine release status is {statuses.machine_release_status}",
            )
        )
    if statuses.operator_release_status and statuses.operator_release_status not in {
        "clean_pass",
        "conditional_pass",
        "allowed",
    }:
        blocking_reasons.append(
            _blocking_reason(
                code="operator_release_not_allowed",
                source="release_closeout_batch_manifest",
                field_path="$.operator_release_status",
                value=statuses.operator_release_status,
                release_effect="blocks_operator_release",
                summary=f"operator release status is {statuses.operator_release_status}",
            )
        )
    return blocking_reasons


def _operator_evidence_blocking_reasons(
    context: _ReleaseAuthorityContext,
) -> list[dict[str, Any]]:
    blocking_reasons: list[dict[str, Any]] = []
    if context.full_suite_status and context.full_suite_status != "pass":
        blocking_reasons.append(
            _blocking_reason(
                code="full_suite_not_pass",
                source="operator_release_summary",
                field_path="$.test_evidence.full_suite_status",
                value=context.full_suite_status,
                release_effect="blocks_release_authority",
                summary=f"full-suite status is {context.full_suite_status}",
            )
        )
    if context.learning_revalidation_status and context.learning_revalidation_status not in {
        "current",
        "pass",
        "not_required",
        "metrics_close_candidate",
    }:
        blocking_reasons.append(
            _blocking_reason(
                code="learning_revalidation_not_current",
                source="operator_release_summary",
                field_path="$.learning_readiness.revalidation_status",
                value=context.learning_revalidation_status,
                release_effect="blocks_clean_release",
                summary=f"learning revalidation status is {context.learning_revalidation_status}",
            )
        )
    return blocking_reasons


def _risk_blocking_reasons(
    risks: _ReleaseAuthorityRiskSnapshot,
) -> list[dict[str, Any]]:
    blocking_reasons: list[dict[str, Any]] = []
    if risks.clean_lane_blocking_count > 0:
        blocking_reasons.append(
            _blocking_reason(
                code="clean_lane_blocking_accepted_risk",
                source="operator_release_summary",
                field_path="$.accepted_risk.clean_lane_blocking_accepted_risk_family_count",
                value=risks.clean_lane_blocking_count,
                release_effect="blocks_clean_release",
                summary=(
                    f"{risks.clean_lane_blocking_count} accepted-risk family count "
                    "still blocks the clean lane"
                ),
            )
        )
    if risks.advisory_lifecycle_count > 0:
        blocking_reasons.append(
            _blocking_reason(
                code="advisory_lifecycle_backlog",
                source="operator_release_summary",
                field_path="$.accepted_risk.advisory_lifecycle_family_count",
                value=risks.advisory_lifecycle_count,
                release_effect="advisory",
                summary=(
                    f"{risks.advisory_lifecycle_count} accepted-risk family count "
                    "remains in advisory lifecycle backlog"
                ),
            )
        )
    return blocking_reasons


def _release_authority_blocking_reasons(
    context: _ReleaseAuthorityContext,
) -> list[dict[str, Any]]:
    return [
        *_legacy_status_blocking_reasons(context.statuses),
        *_status_axis_blocking_reasons(context.statuses),
        *_operator_evidence_blocking_reasons(context),
        *_risk_blocking_reasons(context.risks),
    ]


def _typed_release_authority(
    *,
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
    operator_summary: dict[str, Any],
) -> dict[str, Any]:
    context = _release_authority_context(
        batch_manifest=batch_manifest,
        self_check=self_check,
        operator_summary=operator_summary,
    )
    statuses = context.statuses
    risks = context.risks

    return {
        "batch_manifest_status": statuses.batch_manifest_status,
        "release_authority_status": statuses.release_authority_status,
        "semantic_release_status": statuses.semantic_release_status,
        "sealed_release_status": statuses.sealed_release_status,
        "machine_release_status": statuses.machine_release_status,
        "operator_release_status": statuses.operator_release_status,
        "operator_summary_status": context.operator_summary_status,
        "self_check_status": context.self_check_status,
        "full_suite_status": context.full_suite_status,
        "learning_revalidation_status": context.learning_revalidation_status,
        "accepted_risk_count": risks.accepted_risk_count,
        "release_accepted_risk_count": risks.release_accepted_risk_count,
        "accepted_learning_risk_count": risks.accepted_learning_risk_count,
        "clean_lane_blocking_accepted_risk_family_count": risks.clean_lane_blocking_count,
        "advisory_lifecycle_family_count": risks.advisory_lifecycle_count,
        "blocking_reasons": _release_authority_blocking_reasons(context),
        "operator_summary": context.operator_summary_text,
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _learning_claim_digest_context(
    *,
    learning_claim: dict[str, Any],
    learning_claim_evidence_bundle: dict[str, Any],
    learning_confirmed_evidence_cohort: dict[str, Any],
    learning_delta_scoreboard: dict[str, Any],
) -> dict[str, str]:
    bundle_identity = _dict(learning_claim_evidence_bundle.get("bundle_identity"))
    bundle_summary = _dict(learning_claim_evidence_bundle.get("summary"))
    cohort_identity = _dict(learning_confirmed_evidence_cohort.get("cohort_identity"))
    cohort_summary = _dict(learning_confirmed_evidence_cohort.get("summary"))
    scoreboard_summary = _dict(learning_delta_scoreboard.get("summary"))
    scoreboard_unlock = _dict(learning_delta_scoreboard.get("learning_claim_unlock_review"))
    return {
        "bundle_sha": (
            str(bundle_identity.get("evidence_bundle_digest", "")).strip()
            or str(bundle_summary.get("bundle_sha256", "")).strip()
        ),
        "cohort_sha": (
            str(cohort_identity.get("cohort_digest", "")).strip()
            or str(cohort_summary.get("cohort_sha256", "")).strip()
        ),
        "scoreboard_bundle_sha": str(
            scoreboard_summary.get(
                "learning_claim_evidence_bundle_sha256",
                scoreboard_unlock.get("bundle_sha256", ""),
            )
        ).strip(),
        "scoreboard_cohort_sha": str(
            scoreboard_summary.get(
                "learning_confirmed_evidence_cohort_sha256",
                scoreboard_unlock.get("confirmed_evidence_cohort_sha256", ""),
            )
        ).strip(),
        "operator_bundle_sha": str(
            learning_claim.get("learning_claim_evidence_bundle_sha256", "")
        ).strip(),
        "operator_cohort_sha": str(
            learning_claim.get("learning_confirmed_evidence_cohort_sha256", "")
        ).strip(),
    }


def _learning_required_conditions(
    *,
    confirmed_status: str,
    confirmed_evidence_status: str,
    bundle_status: str,
    cohort_status: str,
    full_suite_status: str,
    public_check_status: str,
    revalidation_status: str,
    accepted_learning_risk: bool,
    digests: dict[str, str],
) -> dict[str, bool]:
    bundle_sha = digests["bundle_sha"]
    cohort_sha = digests["cohort_sha"]
    operator_bundle_sha = digests["operator_bundle_sha"]
    operator_cohort_sha = digests["operator_cohort_sha"]
    scoreboard_bundle_sha = digests["scoreboard_bundle_sha"]
    scoreboard_cohort_sha = digests["scoreboard_cohort_sha"]
    return {
        "confirmed_learning_improvement_status_auto_confirmed": confirmed_status == "auto_confirmed",
        "confirmed_evidence_status_auto_confirmed": confirmed_evidence_status == "auto_confirmed",
        "evidence_bundle_active": bundle_status == "active" and bool(bundle_sha) and operator_bundle_sha == bundle_sha,
        "confirmed_cohort_active": cohort_status == "active" and bool(cohort_sha) and operator_cohort_sha == cohort_sha,
        "full_suite_pass": full_suite_status == "pass",
        "public_check_pass": public_check_status == "pass",
        "rollback_revalidation_clean": revalidation_status
        in {"current", "pass", "not_required", "metrics_close_candidate"},
        "no_accepted_learning_risk": not accepted_learning_risk,
        "operator_bundle_digest_matches_current": bool(bundle_sha) and operator_bundle_sha == bundle_sha,
        "operator_cohort_digest_matches_current": bool(cohort_sha) and operator_cohort_sha == cohort_sha,
        "scoreboard_operator_bundle_digest_match": (
            not scoreboard_bundle_sha and not operator_bundle_sha
        )
        or (bool(scoreboard_bundle_sha) and scoreboard_bundle_sha == operator_bundle_sha),
        "scoreboard_operator_cohort_digest_match": (
            not scoreboard_cohort_sha and not operator_cohort_sha
        )
        or (bool(scoreboard_cohort_sha) and scoreboard_cohort_sha == operator_cohort_sha),
    }


def _learning_claim_run_context(claim_summary: dict[str, Any], cohort_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid_run_count": _int_value(
            claim_summary.get("valid_run_count", cohort_summary.get("valid_run_count", 0))
        ),
        "min_required_run_count": _int_value(
            claim_summary.get("min_required_run_count", cohort_summary.get("min_required_run_count", 0))
        ),
        "eligible_family_count": _int_value(
            claim_summary.get("eligible_family_count", cohort_summary.get("eligible_family_count", 0))
        ),
        "selected_valid_run_ids": _string_list(
            claim_summary.get("selected_valid_run_ids", cohort_summary.get("selected_valid_run_ids", []))
        ),
    }


def _learning_claim_authority_summary(
    *,
    claim_level: str,
    confirmed_status: str,
    bundle_status: str,
    cohort_status: str,
    run_context: dict[str, Any],
    pre_seal_ready: bool,
) -> str:
    return (
        f"claim_level={claim_level}; confirmed_status={confirmed_status}; "
        f"bundle={bundle_status}; cohort={cohort_status}; "
        f"valid_runs={run_context['valid_run_count']}/{run_context['min_required_run_count']}; "
        f"eligible_families={run_context['eligible_family_count']}; "
        f"pre_seal_wording_ready={pre_seal_ready}"
    )


def _learning_claim_authority(
    vault: Path,
    *,
    operator_summary: dict[str, Any],
    learning_claim_evidence_bundle: dict[str, Any],
    learning_confirmed_evidence_cohort: dict[str, Any],
    learning_delta_scoreboard: dict[str, Any],
    reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    learning_claim = _dict(operator_summary.get("learning_claim"))
    claim_summary = _dict(learning_claim.get("confirmed_evidence_summary"))
    cohort_summary = _dict(learning_confirmed_evidence_cohort.get("summary"))
    scoreboard_summary = _dict(learning_delta_scoreboard.get("summary"))
    test_evidence = _dict(operator_summary.get("test_evidence"))
    learning_readiness = _dict(operator_summary.get("learning_readiness"))
    public_check, public_check_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, DEFAULT_PUBLIC_CHECK_SUMMARY)
    )
    digests = _learning_claim_digest_context(
        learning_claim=learning_claim,
        learning_claim_evidence_bundle=learning_claim_evidence_bundle,
        learning_confirmed_evidence_cohort=learning_confirmed_evidence_cohort,
        learning_delta_scoreboard=learning_delta_scoreboard,
    )
    claim_level = str(learning_claim.get("claim_level", "none")).strip() or "none"
    confirmed_status = str(
        learning_claim.get(
            "improvement_claim_status",
            learning_claim.get("confirmed_learning_improvement_status", "not_ready"),
        )
    ).strip() or "not_ready"
    confirmed_evidence_status = str(
        learning_claim.get(
            "evidence_cohort_status",
            claim_summary.get(
                "evidence_cohort_status",
                claim_summary.get(
                    "confirmed_evidence_status",
                    cohort_summary.get("confirmed_evidence_status", "not_ready"),
                ),
            ),
        )
    ).strip() or "not_ready"
    bundle_status = str(
        learning_claim.get(
            "learning_claim_evidence_bundle_status",
            scoreboard_summary.get("learning_claim_evidence_bundle_status", "not_evaluated"),
        )
    ).strip() or "not_evaluated"
    cohort_status = str(
        learning_claim.get(
            "learning_confirmed_evidence_cohort_status",
            scoreboard_summary.get("learning_confirmed_evidence_cohort_status", "not_evaluated"),
        )
    ).strip() or "not_evaluated"
    full_suite_status = str(test_evidence.get("full_suite_status", "")).strip()
    revalidation_status = str(learning_readiness.get("revalidation_status", "")).strip()
    accepted_learning_risk = bool(learning_readiness.get("accepted_learning_risk"))
    public_check_status = str(public_check.get("status", "")).strip()
    run_context = _learning_claim_run_context(claim_summary, cohort_summary)
    required_conditions = _learning_required_conditions(
        confirmed_status=confirmed_status,
        confirmed_evidence_status=confirmed_evidence_status,
        bundle_status=bundle_status,
        cohort_status=cohort_status,
        full_suite_status=full_suite_status,
        public_check_status=public_check_status,
        revalidation_status=revalidation_status,
        accepted_learning_risk=accepted_learning_risk,
        digests=digests,
    )
    pre_seal_ready = all(required_conditions.values())

    return {
        "claim_level": claim_level,
        "improvement_claim_status": confirmed_status,
        "confirmed_learning_improvement_status": confirmed_status,
        "evidence_cohort_status": confirmed_evidence_status,
        "confirmed_evidence_status": confirmed_evidence_status,
        "learning_claim_evidence_bundle_sha256": digests["bundle_sha"],
        "learning_confirmed_evidence_cohort_sha256": digests["cohort_sha"],
        "learning_delta_scoreboard_sha256": str(reports["learning_delta_scoreboard"].get("sha256", "")).strip(),
        "operator_learning_claim_evidence_bundle_sha256": digests["operator_bundle_sha"],
        "operator_learning_confirmed_evidence_cohort_sha256": digests["operator_cohort_sha"],
        "scoreboard_learning_claim_evidence_bundle_sha256": digests["scoreboard_bundle_sha"],
        "scoreboard_learning_confirmed_evidence_cohort_sha256": digests["scoreboard_cohort_sha"],
        **run_context,
        "evidence_bundle_status": bundle_status,
        "confirmed_cohort_status": cohort_status,
        "full_suite_status": full_suite_status,
        "public_check_status": public_check_status,
        "public_check_load_status": str(public_check_diagnostics.get("status", "unknown")),
        "rollback_revalidation_status": revalidation_status,
        "accepted_learning_risk": accepted_learning_risk,
        "operator_confirmed_wording_policy_status": str(
            learning_claim.get("confirmed_wording_policy_status", "")
        ).strip(),
        "operator_confirmed_wording_allowed": bool(learning_claim.get("confirmed_wording_allowed")),
        "required_conditions": required_conditions,
        "pre_seal_confirmed_wording_ready": pre_seal_ready,
        "post_seal_attestation_status": "pending",
        "no_human_confirmed_wording_allowed": False,
        "scoreboard_operator_bundle_digest_match": required_conditions[
            "scoreboard_operator_bundle_digest_match"
        ],
        "scoreboard_operator_cohort_digest_match": required_conditions[
            "scoreboard_operator_cohort_digest_match"
        ],
        "summary": _learning_claim_authority_summary(
            claim_level=claim_level,
            confirmed_status=confirmed_status,
            bundle_status=bundle_status,
            cohort_status=cohort_status,
            run_context=run_context,
            pre_seal_ready=pre_seal_ready,
        ),
    }


def _finalize_learning_claim_authority(
    authority: dict[str, Any],
    *,
    verification_status: str,
) -> dict[str, Any]:
    finalized = dict(authority)
    finalized["post_seal_attestation_status"] = verification_status
    finalized["required_conditions"] = {
        **_dict(authority.get("required_conditions")),
        "post_seal_attestation_pass": verification_status == "pass",
    }
    finalized["no_human_confirmed_wording_allowed"] = bool(
        authority.get("pre_seal_confirmed_wording_ready")
    ) and verification_status == "pass"
    finalized["summary"] = (
        f"{authority.get('summary', '')}; post_seal_attestation={verification_status}; "
        f"no_human_confirmed_wording_allowed={finalized['no_human_confirmed_wording_allowed']}"
    )
    return finalized


def _load_attestation_inputs(
    vault: Path,
    *,
    batch_manifest_path: str,
    self_check_path: str,
    operator_summary_path: str,
) -> _AttestationInputs:
    batch_manifest, _batch_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, batch_manifest_path)
    )
    self_check, _self_check_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, self_check_path)
    )
    operator_summary, _operator_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, operator_summary_path)
    )
    bundle, _bundle_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, DEFAULT_LEARNING_CLAIM_EVIDENCE_BUNDLE)
    )
    cohort, _cohort_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, DEFAULT_LEARNING_CONFIRMED_EVIDENCE_COHORT)
    )
    scoreboard, _scoreboard_diagnostics = load_optional_json_object_with_diagnostics(
        _resolve(vault, DEFAULT_LEARNING_DELTA_SCOREBOARD)
    )
    return _AttestationInputs(
        batch_manifest=batch_manifest,
        self_check=self_check,
        operator_summary=operator_summary,
        learning_claim_evidence_bundle=bundle,
        learning_confirmed_evidence_cohort=cohort,
        learning_delta_scoreboard=scoreboard,
    )


def _attestation_report_identities(
    vault: Path,
    *,
    batch_manifest_path: str,
    self_check_path: str,
    operator_summary_path: str,
) -> dict[str, dict[str, Any]]:
    return {
        "release_closeout_batch_manifest": _report_identity(
            vault,
            batch_manifest_path,
            role="batch_manifest",
        ),
        "release_evidence_closeout_self_check": _report_identity(
            vault,
            self_check_path,
            role="self_check",
        ),
        "operator_release_summary": _report_identity(
            vault,
            operator_summary_path,
            role="operator_summary",
        ),
        "learning_claim_evidence_bundle": _report_identity(
            vault,
            DEFAULT_LEARNING_CLAIM_EVIDENCE_BUNDLE,
            role="learning_claim_evidence_bundle",
        ),
        "learning_confirmed_evidence_cohort": _report_identity(
            vault,
            DEFAULT_LEARNING_CONFIRMED_EVIDENCE_COHORT,
            role="learning_confirmed_evidence_cohort",
        ),
        "learning_delta_scoreboard": _report_identity(
            vault,
            DEFAULT_LEARNING_DELTA_SCOREBOARD,
            role="learning_delta_scoreboard",
        ),
    }


def _attestation_source_zip(
    vault: Path,
    *,
    inputs: _AttestationInputs,
    explicit_source_zip_path: str,
) -> tuple[str, dict[str, Any]]:
    resolved_source_zip_path = _source_zip_path(
        inputs.batch_manifest,
        inputs.operator_summary,
        explicit_source_zip_path,
    )
    if not resolved_source_zip_path:
        return "", {
            "role": "source_zip",
            "path": "",
            "exists": False,
            "size_bytes": 0,
            "sha256": "",
        }
    return resolved_source_zip_path, _file_identity(
        vault,
        resolved_source_zip_path,
        role="source_zip",
    )


def _attestation_bindings(
    *,
    source_zip: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    batch_manifest: dict[str, Any],
    self_check: dict[str, Any],
) -> dict[str, str]:
    distribution = _dict(batch_manifest.get("distribution_package"))
    audit_materialization = _dict(batch_manifest.get("audit_materialization"))
    batch_watch = _dict(self_check.get("batch_artifact_digest_watch"))
    return {
        "source_zip_sha256": source_zip["sha256"],
        "release_closeout_batch_manifest_sha256": reports["release_closeout_batch_manifest"]["sha256"],
        "release_evidence_closeout_self_check_sha256": reports["release_evidence_closeout_self_check"]["sha256"],
        "operator_release_summary_sha256": reports["operator_release_summary"]["sha256"],
        "learning_claim_evidence_bundle_sha256": reports["learning_claim_evidence_bundle"]["sha256"],
        "learning_confirmed_evidence_cohort_sha256": reports["learning_confirmed_evidence_cohort"]["sha256"],
        "learning_delta_scoreboard_sha256": reports["learning_delta_scoreboard"]["sha256"],
        "batch_distribution_zip_sha256": str(distribution.get("sha256", "")),
        "evidence_set_digest": str(audit_materialization.get("evidence_set_digest", "")),
        "batch_artifact_digest_watch_status": str(batch_watch.get("status", "")),
        "source_tree_fingerprint": reports["release_closeout_batch_manifest"]["source_tree_fingerprint"],
    }


def _attestation_envelope(
    vault: Path,
    *,
    generated_at: str,
    resolved_policy_path: Path,
    resolved_source_zip_path: str,
    batch_manifest_path: str,
    self_check_path: str,
    operator_summary_path: str,
) -> dict[str, Any]:
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="release_post_seal_attestation",
        producer=PRODUCER,
        source_command=(
            "python -m ops.scripts.release_post_seal_attestation "
            "--vault . --out build/release/release-post-seal-attestation.json"
        ),
        resolved_policy_path=resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=["ops/scripts/release/release_post_seal_attestation.py"],
        file_inputs={
            "source_zip": resolved_source_zip_path,
            "release_closeout_batch_manifest": batch_manifest_path,
            "release_evidence_closeout_self_check": self_check_path,
            "operator_release_summary": operator_summary_path,
            "learning_claim_evidence_bundle": DEFAULT_LEARNING_CLAIM_EVIDENCE_BUNDLE,
            "learning_confirmed_evidence_cohort": DEFAULT_LEARNING_CONFIRMED_EVIDENCE_COHORT,
            "learning_delta_scoreboard": DEFAULT_LEARNING_DELTA_SCOREBOARD,
        },
    )


def build_attestation(
    vault: Path,
    *,
    out_path: str = DEFAULT_OUT,
    source_zip_path: str = "",
    batch_manifest_path: str = DEFAULT_BATCH_MANIFEST,
    self_check_path: str = DEFAULT_SELF_CHECK,
    operator_summary_path: str = DEFAULT_OPERATOR_SUMMARY,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    inputs = _load_attestation_inputs(
        vault,
        batch_manifest_path=batch_manifest_path,
        self_check_path=self_check_path,
        operator_summary_path=operator_summary_path,
    )
    resolved_source_zip_path, source_zip = _attestation_source_zip(
        vault,
        inputs=inputs,
        explicit_source_zip_path=source_zip_path,
    )
    reports = _attestation_report_identities(
        vault,
        batch_manifest_path=batch_manifest_path,
        self_check_path=self_check_path,
        operator_summary_path=operator_summary_path,
    )
    bindings = _attestation_bindings(
        source_zip=source_zip,
        reports=reports,
        batch_manifest=inputs.batch_manifest,
        self_check=inputs.self_check,
    )
    linkage = _pre_seal_post_seal_linkage(
        vault,
        source_zip=source_zip,
        reports=reports,
        bindings=bindings,
    )
    learning_claim_authority = _learning_claim_authority(
        vault,
        operator_summary=inputs.operator_summary,
        learning_claim_evidence_bundle=inputs.learning_claim_evidence_bundle,
        learning_confirmed_evidence_cohort=inputs.learning_confirmed_evidence_cohort,
        learning_delta_scoreboard=inputs.learning_delta_scoreboard,
        reports=reports,
    )
    verification = _verification(
        source_zip=source_zip,
        batch_manifest=inputs.batch_manifest,
        self_check=inputs.self_check,
        operator_summary=inputs.operator_summary,
        reports=reports,
        pre_seal_post_seal_linkage=linkage,
        learning_claim_authority=learning_claim_authority,
    )
    learning_claim_authority = _finalize_learning_claim_authority(
        learning_claim_authority,
        verification_status=verification["status"],
    )
    return {
        **_attestation_envelope(
            vault,
            generated_at=generated_at,
            resolved_policy_path=resolved_policy_path,
            resolved_source_zip_path=resolved_source_zip_path,
            batch_manifest_path=batch_manifest_path,
            self_check_path=self_check_path,
            operator_summary_path=operator_summary_path,
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": verification["status"],
        "sidecar": {
            "path": report_path(vault, _resolve(vault, out_path)),
            "storage_role": "post_seal_non_cyclic_sidecar",
            "included_in_source_zip": False,
            "reason": "Generated after source ZIP, batch manifest, self-check, and operator summary are materialized.",
        },
        "source_zip": source_zip,
        "reports": reports,
        "bindings": bindings,
        "pre_seal_post_seal_linkage": linkage,
        "release_authority": _typed_release_authority(
            batch_manifest=inputs.batch_manifest,
            self_check=inputs.self_check,
            operator_summary=inputs.operator_summary,
        ),
        "learning_claim_authority": learning_claim_authority,
        "verification": verification,
    }


def write_attestation(vault: Path, payload: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=payload,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release post-seal attestation schema validation failed",
        )
    )


def verify_attestation(vault: Path, *, attestation_path: str) -> dict[str, Any]:
    attestation = read_json_object(_resolve(vault, attestation_path))
    schema = load_schema_with_vault_override(vault, SCHEMA_PATH)
    validate_or_raise(attestation, schema, context="release post-seal attestation validation failed")
    return {
        "status": attestation["verification"]["status"],
        "attestation_path": attestation_path,
        "failed_checks": attestation["verification"]["failed_checks"],
        "bindings": attestation["bindings"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify a post-seal release sidecar attestation.")
    subparsers = parser.add_subparsers(dest="command_name", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--vault", default=".")
    build.add_argument("--out", default=DEFAULT_OUT)
    build.add_argument("--source-zip-path", default="")
    build.add_argument("--batch-manifest-path", default=DEFAULT_BATCH_MANIFEST)
    build.add_argument("--self-check-path", default=DEFAULT_SELF_CHECK)
    build.add_argument("--operator-summary-path", default=DEFAULT_OPERATOR_SUMMARY)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--vault", default=".")
    verify.add_argument("--attestation", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.command_name == "verify":
        result = verify_attestation(vault, attestation_path=args.attestation)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "pass" else 1
    payload = build_attestation(
        vault,
        out_path=args.out,
        source_zip_path=args.source_zip_path,
        batch_manifest_path=args.batch_manifest_path,
        self_check_path=args.self_check_path,
        operator_summary_path=args.operator_summary_path,
    )
    destination = write_attestation(vault, payload, args.out)
    print(display_path(vault, destination))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
