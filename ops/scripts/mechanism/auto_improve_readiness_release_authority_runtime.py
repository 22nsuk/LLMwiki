from __future__ import annotations

from typing import Any

from ops.scripts.core.release_authority_state_runtime import (
    clean_required_preflight_passes,
    machine_release_allowed_from_status_view,
    release_status_v2_view,
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.gate_effect_vocabulary import GATE_EFFECT_BLOCKS_PROMOTION
from ops.scripts.release_authority_vocabulary import (
    REASON_MACHINE_RELEASE_NOT_ALLOWED,
    REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS,
    REASON_SEALED_RELEASE_NOT_CLEAN_PASS,
)

from .auto_improve_readiness_constants_runtime import (
    ARTIFACT_FRESHNESS_REPORT_REL_PATH,
    RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH,
    RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH,
    SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH,
    SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH,
)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _release_gate_summaries(reports: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    release_finality = _release_finality_gate(reports["release_finality"])
    artifact_finalization = _artifact_finalization_gate(
        reports["artifact_finalization"],
        release_finality_summary=release_finality,
    )
    release_closeout = _release_closeout_summary_gate(reports["release_closeout"])
    release_evidence_cohort = _release_evidence_cohort_summary(
        reports["release_evidence_cohort"]
    )

    artifact_freshness = reports["artifact_freshness"]
    selected_contract_attention = [
        item
        for item in _artifact_operational_attention_items(artifact_freshness)
        if item["path"] == SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH
    ]
    return {
        "artifact_freshness": _artifact_freshness_summary(artifact_freshness),
        "selected_contract": _selected_contract_summary(
            reports["selected_contract"],
            operational_attention_items=selected_contract_attention,
        ),
        "source_package": _release_gate_summary(
            reports["source_package"],
            path=SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH,
            expected_artifact_kind="source_package_clean_extract",
            gate_label="source package clean extract",
        ),
        "release_closeout": release_closeout,
        "release_batch_manifest": _release_batch_manifest_gate(reports["release_batch_manifest"]),
        "release_finality": release_finality,
        "release_evidence_cohort": release_evidence_cohort,
        "artifact_finalization": artifact_finalization,
        "release_authority_preflight": _release_authority_preflight_summary(
            reports["release_authority_preflight"]
        ),
    }


def _artifact_freshness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    schema_invalid_artifacts = [
        {
            "path": str(record.get("path", "")).strip(),
            "errors": [
                str(error)
                for error in record.get("schema_validation_errors", [])
                if str(error).strip()
            ][:5],
        }
        for record in payload.get("artifact_records", [])
        if isinstance(record, dict) and str(record.get("schema_validation_status", "")).strip() == "fail"
    ]
    status = str(payload.get("status", "")).strip() if payload else "missing"
    return {
        "path": ARTIFACT_FRESHNESS_REPORT_REL_PATH,
        "status": status or "unknown",
        "schema_invalid_artifact_count": _int_value(summary.get("schema_invalid_artifact_count")),
        "stable_contract_debt_issue_count": _int_value(summary.get("stable_contract_debt_issue_count")),
        "schema_invalid_artifacts": schema_invalid_artifacts,
    }


def _artifact_operational_attention_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in payload.get("artifact_records", []):
        if not isinstance(record, dict):
            continue
        issues = [
            str(issue).strip()
            for issue in record.get("issues", [])
            if str(issue).startswith(("test_target_fingerprint_mismatch", "test_target_missing"))
        ]
        path = str(record.get("path", "")).strip()
        if path and issues:
            items.append({"path": path, "issues": issues})
    return items


def _artifact_mtime_attention_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in payload.get("artifact_records", []):
        if not isinstance(record, dict):
            continue
        issues = [
            str(issue).strip()
            for issue in record.get("issues", [])
            if str(issue).strip() == "generated_at_older_than_file_mtime"
        ]
        path = str(record.get("path", "")).strip()
        if path and issues:
            items.append({"path": path, "issues": issues})
    return items


def _release_gate_summary(
    payload: dict[str, Any],
    *,
    path: str,
    expected_artifact_kind: str,
    gate_label: str,
    nonblocking_source_statuses: set[str] | None = None,
) -> dict[str, Any]:
    if not payload:
        return {
            "path": path,
            "expected_artifact_kind": expected_artifact_kind,
            "artifact_kind": "",
            "status": "not_run",
            "source_status": "missing",
            "release_blocking": True,
            "summary": f"{gate_label} report is missing or unusable",
        }
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    source_status = str(payload.get("status", "")).strip() or "unknown"
    if artifact_kind != expected_artifact_kind:
        return {
            "path": path,
            "expected_artifact_kind": expected_artifact_kind,
            "artifact_kind": artifact_kind,
            "status": "fail",
            "source_status": "kind_mismatch",
            "release_blocking": True,
            "summary": (
                f"{gate_label} artifact_kind={artifact_kind or '<missing>'}; "
                f"expected {expected_artifact_kind}"
            ),
        }
    nonblocking_statuses = {"pass"}
    if nonblocking_source_statuses:
        nonblocking_statuses.update(nonblocking_source_statuses)
    status = "pass" if source_status in nonblocking_statuses else "fail"
    return {
        "path": path,
        "expected_artifact_kind": expected_artifact_kind,
        "artifact_kind": artifact_kind,
        "status": status,
        "source_status": source_status,
        "release_blocking": status != "pass",
        "summary": f"{gate_label} status={source_status}",
    }


def _selected_contract_summary(
    payload: dict[str, Any],
    *,
    operational_attention_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary = _release_gate_summary(
        payload,
        path=SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH,
        expected_artifact_kind="test_execution_summary",
        gate_label="selected contract summary",
        nonblocking_source_statuses={"partial-pass"},
    )
    if summary["status"] == "not_run" or summary["source_status"] == "kind_mismatch":
        return summary
    currentness = payload.get("currentness")
    currentness = currentness if isinstance(currentness, dict) else {}
    currentness_status = str(currentness.get("status", "")).strip() or "missing"
    if summary["status"] != "pass":
        return {**summary, "currentness_status": currentness_status}
    if operational_attention_items:
        issues = [
            issue
            for item in operational_attention_items
            for issue in _string_list(item.get("issues"))
        ]
        issue_summary = ", ".join(issues[:4]) if issues else "operational attention"
        return {
            **summary,
            "status": "fail",
            "source_status": "currentness_operational_attention",
            "currentness_status": currentness_status,
            "release_blocking": True,
            "signal_ids": ["selected_contract_currentness_not_current"],
            "summary": (
                f"{summary['summary']}; selected_contract_currentness_status={currentness_status}; "
                f"operational_attention={issue_summary}"
            ),
        }
    if currentness_status == "current":
        return {**summary, "currentness_status": currentness_status}
    return {
        **summary,
        "status": "fail",
        "source_status": f"currentness_{currentness_status}",
        "currentness_status": currentness_status,
        "release_blocking": True,
        "signal_ids": ["selected_contract_currentness_not_current"],
        "summary": (
            f"{summary['summary']}; selected_contract_currentness_status={currentness_status}"
        ),
    }


def _release_closeout_summary_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _release_gate_summary(
        payload,
        path=RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH,
        expected_artifact_kind="release_closeout_summary",
        gate_label="release closeout summary",
    )
    if summary["status"] == "not_run" or summary["source_status"] == "kind_mismatch":
        return summary
    status_view = release_status_v2_view_with_readiness_fallback(payload)
    source_status = str(status_view["compatibility_status_value"])
    authority_status = str(status_view["release_authority_status"])
    sealed_status = str(status_view["sealed_release_status"])
    machine_release_allowed = machine_release_allowed_from_status_view(
        status_view,
        machine_release_not_allowed_reason_id=REASON_MACHINE_RELEASE_NOT_ALLOWED,
    )
    clean_release_ready = bool(payload.get("clean_release_ready", False))
    status = "pass" if machine_release_allowed else "fail"
    signal_ids = [str(reason) for reason in status_view["blocker_reason_ids"]] if status != "pass" else []
    if status != "pass" and not signal_ids:
        signal_ids = [REASON_MACHINE_RELEASE_NOT_ALLOWED]
    return {
        **summary,
        "status": status,
        "source_status": source_status,
        "release_blocking": status != "pass",
        "signal_ids": signal_ids,
        "summary": (
            "release closeout summary "
            f"status={source_status}; machine_release_allowed={str(machine_release_allowed).lower()}; "
            f"clean_release_ready={str(clean_release_ready).lower()}; "
            f"release_authority_status={authority_status}; "
            f"sealed_release_status={sealed_status}"
        ),
    }


def _release_batch_manifest_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _release_gate_summary(
        payload,
        path=RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH,
        expected_artifact_kind="release_closeout_batch_manifest",
        gate_label="release closeout batch manifest",
    )
    if summary["status"] == "not_run" or summary["source_status"] == "kind_mismatch":
        return summary
    status_view = release_status_v2_view(payload)
    source_status = str(status_view["compatibility_status_value"])
    authority_status = str(status_view["release_authority_status"])
    sealed_status = str(status_view["sealed_release_status"])
    batch_integrity_status = str(payload.get("batch_integrity_status", "")).strip() or "unknown"
    auto_improve_lane_status = str(payload.get("auto_improve_lane_status", "")).strip() or "unknown"
    machine_release_status = str(payload.get("machine_release_status", "")).strip() or "unknown"
    distribution = payload.get("distribution_package", {})
    distribution_status = (
        str(distribution.get("status", "")).strip()
        if isinstance(distribution, dict)
        else "unknown"
    ) or "unknown"
    if batch_integrity_status == "unknown":
        batch_integrity_status = "pass" if source_status == "pass" else "fail"
    if auto_improve_lane_status == "unknown":
        auto_improve_lane_status = "pass" if authority_status == "clean_pass" else "blocked"
    if machine_release_status == "unknown":
        machine_release_status = "allowed" if authority_status == "clean_pass" else "blocked"

    # This gate owns the batch manifest authority only.  The manifest records
    # lane status for operator context, but treating auto_improve_lane_status as
    # an input here creates a self-dependency:
    # readiness -> closeout summary -> lane summary -> batch manifest -> readiness.
    gate_pass = (
        authority_status == "clean_pass"
        and batch_integrity_status == "pass"
        and machine_release_status == "allowed"
    )
    signal_ids = list(status_view["blocker_reason_ids"])
    if not signal_ids and not gate_pass:
        if authority_status != "clean_pass":
            signal_ids.append(REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS)
        if sealed_status != "sealed_clean_pass":
            signal_ids.append(REASON_SEALED_RELEASE_NOT_CLEAN_PASS)
    return {
        **summary,
        "status": "pass" if gate_pass else "fail",
        "source_status": source_status,
        "release_blocking": not gate_pass,
        "signal_ids": signal_ids if not gate_pass else [],
        "summary": (
            "release closeout batch manifest "
            f"status={source_status}; release_authority_status={authority_status}; "
            f"sealed_release_status={sealed_status}; distribution_package.status={distribution_status}; "
            f"batch_integrity_status={batch_integrity_status}; auto_improve_lane_status={auto_improve_lane_status}; "
            f"machine_release_status={machine_release_status}"
        ),
    }


def _release_evidence_cohort_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _release_gate_summary(
        payload,
        path=RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH,
        expected_artifact_kind="release_evidence_cohort",
        gate_label="release evidence cohort",
        nonblocking_source_statuses={"attention"},
    )
    if summary["status"] == "not_run" or summary["source_status"] == "kind_mismatch":
        return summary
    source_status = str(payload.get("status", "")).strip() or "unknown"
    cohort = _dict_field(payload, "cohort")
    release_summary = _dict_field(payload, "summary")
    strict_same_fingerprint = bool(cohort.get("strict_same_fingerprint", False))
    component_fingerprint_count = _int_value(cohort.get("component_fingerprint_count"))
    clean_lane_contract_status = (
        str(release_summary.get("clean_lane_contract_status", "")).strip() or "unknown"
    )
    source_status_pass = summary["status"] == "pass"
    gate_pass = (
        source_status_pass
        and strict_same_fingerprint
        and clean_lane_contract_status == "pass"
    )
    signal_ids: list[str] = []
    if not source_status_pass:
        signal_ids.append("release_evidence_cohort_status_not_pass")
    if not strict_same_fingerprint:
        signal_ids.append("release_lineage_not_strict_same_fingerprint")
    if clean_lane_contract_status != "pass":
        signal_ids.append("release_evidence_clean_lane_contract_not_pass")
    return {
        **summary,
        "status": "pass" if gate_pass else "fail",
        "source_status": source_status,
        "release_blocking": not gate_pass,
        "signal_ids": signal_ids,
        "summary": (
            "release evidence cohort "
            f"status={source_status}; strict_same_fingerprint={str(strict_same_fingerprint).lower()}; "
            f"component_fingerprint_count={component_fingerprint_count}; "
            f"clean_lane_contract_status={clean_lane_contract_status}"
        ),
    }


def _release_authority_preflight_summary(payload: dict[str, Any]) -> dict[str, Any]:
    path = str(payload.get("_source_rel_path", RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH)).strip()
    if not path:
        path = RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH
    if not payload:
        return {
            "path": path,
            "artifact_kind": "",
            "status": "not_run",
            "preflight_status": "not_run",
            "preflight_mode": "clean_required",
            "distribution_binding_status": "unknown",
            "authority_preflight_status": "unknown",
            "expected_blocked_preflight": False,
            "clean_required_preflight": True,
            "failure_ids": [],
            "unexpected_failure_ids": [],
            "failure_details": [],
            "blocker_reason_ids": [],
            "linked_promotion_blocker_ids": [],
            "summary": "release authority sealed preflight report is missing or unusable",
        }
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    status = str(payload.get("status", "")).strip() or "unknown"
    preflight_status = str(payload.get("preflight_status", "")).strip() or "unknown"
    preflight_mode = str(payload.get("preflight_mode", "")).strip() or "clean_required"
    distribution_binding_status = (
        str(payload.get("distribution_binding_status", "")).strip() or "unknown"
    )
    authority_preflight_status = (
        str(payload.get("authority_preflight_status", "")).strip() or "unknown"
    )
    expected_blocked_preflight = bool(payload.get("expected_blocked_preflight", False))
    clean_required_preflight = bool(payload.get("clean_required_preflight", True))
    clean_required_gate = clean_required_preflight_passes(
        status=status,
        preflight_status=preflight_status,
        preflight_mode=preflight_mode,
        distribution_binding_status=distribution_binding_status,
        authority_preflight_status=authority_preflight_status,
        expected_blocked_preflight=expected_blocked_preflight,
        clean_required_preflight=clean_required_preflight,
    )
    blocker_reason_ids = _string_list(payload.get("blocking_reason_ids"))
    linked_blockers: list[str] = []
    if REASON_MACHINE_RELEASE_NOT_ALLOWED in blocker_reason_ids:
        linked_blockers.append("promotion_blocked_by_release_closeout_summary_failure")
    if blocker_reason_ids:
        linked_blockers.append("promotion_blocked_by_release_batch_manifest_failure")
    failure_details = payload.get("failure_details")
    if not isinstance(failure_details, list):
        failure_details = []
    failure_details = [item for item in failure_details if isinstance(item, dict)]
    unexpected_failure_ids = _string_list(payload.get("unexpected_failure_ids"))
    return {
        "path": path,
        "artifact_kind": artifact_kind,
        "status": (
            "fail"
            if artifact_kind != "release_closeout_sealed_rehearsal_check"
            else "pass" if clean_required_gate else "fail"
        ),
        "preflight_status": preflight_status,
        "preflight_mode": preflight_mode,
        "distribution_binding_status": distribution_binding_status,
        "authority_preflight_status": authority_preflight_status,
        "expected_blocked_preflight": expected_blocked_preflight,
        "clean_required_preflight": clean_required_preflight,
        "failure_ids": _string_list(payload.get("failures")),
        "unexpected_failure_ids": unexpected_failure_ids,
        "failure_details": failure_details,
        "blocker_reason_ids": blocker_reason_ids,
        "linked_promotion_blocker_ids": linked_blockers,
        "summary": str(payload.get("summary", "")).strip()
        or (
            "release authority sealed preflight "
            f"{preflight_status}; distribution_binding_status={distribution_binding_status}; "
            f"authority_preflight_status={authority_preflight_status}"
        ),
    }


SELF_REFERENTIAL_PREFLIGHT_FAILURE_IDS = frozenset(
    {
        "batch_release_authority_not_clean_pass",
        "batch_sealed_release_not_clean_pass",
    }
)
SELF_REFERENTIAL_PREFLIGHT_BLOCKER_REASON_IDS = frozenset(
    {
        "release_authority_not_clean_pass",
        "machine_release_not_allowed",
        "sealed_release_not_clean_pass",
    }
)


def _expected_blocked_preflight_is_self_referential(summary: dict[str, Any]) -> bool:
    if not bool(summary.get("expected_blocked_preflight", False)):
        return False
    if str(summary.get("preflight_status", "")).strip() != "binding_pass_authority_blocked":
        return False
    if str(summary.get("preflight_mode", "")).strip() != "expected_blocked":
        return False
    if str(summary.get("distribution_binding_status", "")).strip() != "pass":
        return False
    if str(summary.get("authority_preflight_status", "")).strip() != "blocked":
        return False
    if _string_list(summary.get("unexpected_failure_ids")):
        return False
    failure_ids = set(_string_list(summary.get("failure_ids")))
    blocker_reason_ids = set(_string_list(summary.get("blocker_reason_ids")))
    return failure_ids <= SELF_REFERENTIAL_PREFLIGHT_FAILURE_IDS and (
        blocker_reason_ids <= SELF_REFERENTIAL_PREFLIGHT_BLOCKER_REASON_IDS
    )


def _release_finality_gate(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _release_gate_summary(
        payload,
        path=RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH,
        expected_artifact_kind="release_closeout_finality_attestation",
        gate_label="release closeout finality attestation",
        nonblocking_source_statuses={"pass", "unknown"},
    )
    if summary["status"] == "not_run" or summary["source_status"] == "kind_mismatch":
        return summary
    finality_status = str(payload.get("finality_status", "")).strip() or "unknown"
    failures = payload.get("finality_failures", [])
    failure_count = len(failures) if isinstance(failures, list) else 0
    gate_pass = finality_status == "pass" and failure_count == 0
    return {
        **summary,
        "status": "pass" if gate_pass else "fail",
        "source_status": finality_status,
        "release_blocking": not gate_pass,
        "summary": (
            "release closeout finality attestation "
            f"finality_status={finality_status}; finality_failure_count={failure_count}"
        ),
    }


def _artifact_finalization_gate(
    payload: dict[str, Any],
    *,
    release_finality_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = _release_gate_summary(
        payload,
        path=RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH,
        expected_artifact_kind="release_closeout_post_check_finalizer",
        gate_label="artifact finalization post-check finalizer",
    )
    if summary["source_status"] == "kind_mismatch":
        return summary
    if summary["status"] == "not_run":
        finality_status = (
            str(release_finality_summary.get("status", "")).strip()
            if isinstance(release_finality_summary, dict)
            else ""
        )
        finality_source_status = (
            str(release_finality_summary.get("source_status", "")).strip()
            if isinstance(release_finality_summary, dict)
            else ""
        )
        if finality_status == "pass" and finality_source_status == "pass":
            return {
                **summary,
                "artifact_kind": "release_closeout_post_check_finalizer",
                "status": "pass",
                "source_status": "finality_attested_pass",
                "release_blocking": False,
                "summary": (
                    "artifact finalization post-check finalizer report was cleaned from tmp, "
                    "but release closeout finality attestation passed so the final artifact set is treated as finalized"
                ),
            }
        return summary
    source_status = str(payload.get("status", "")).strip() or "unknown"
    refresh_required = bool(payload.get("refresh_required", True))
    affected_path_count = _int_value(payload.get("affected_path_count"))
    gate_pass = source_status == "pass" and not refresh_required and affected_path_count == 0
    return {
        **summary,
        "status": "pass" if gate_pass else "fail",
        "source_status": source_status,
        "release_blocking": not gate_pass,
        "summary": (
            "artifact finalization post-check finalizer "
            f"status={source_status}; refresh_required={str(refresh_required).lower()}; "
            f"affected_path_count={affected_path_count}"
        ),
    }


def _release_gate_promotion_blockers(
    selected_contract_summary: dict[str, Any],
    source_package_summary: dict[str, Any],
    release_closeout_summary: dict[str, Any],
    release_batch_manifest_summary: dict[str, Any],
    release_finality_summary: dict[str, Any],
    release_evidence_cohort_summary: dict[str, Any],
    artifact_finalization_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    gate_definitions = [
        (
            selected_contract_summary,
            "promotion_blocked_by_selected_contract_failure",
            "selected_contract",
            "selected_contract_status_not_pass",
            "Run make test-execution-summary-report-contract-refresh and confirm selected contract status=pass.",
            "Refresh selected contract evidence, then rerun make auto-improve-readiness.",
        ),
        (
            source_package_summary,
            "promotion_blocked_by_source_package_failure",
            "source_package",
            "source_package_status_not_pass",
            "Run make release-source-package-check and confirm source package status=pass.",
            "Refresh source package clean-extract evidence, then rerun make auto-improve-readiness.",
        ),
        (
            release_closeout_summary,
            "promotion_blocked_by_release_closeout_summary_failure",
            "release_closeout_summary",
            "release_closeout_summary_not_machine_allowed",
            "Run make release-closeout-summary and confirm machine_release_allowed=true.",
            "Refresh release closeout summary, then rerun make auto-improve-readiness.",
        ),
        (
            release_batch_manifest_summary,
            "promotion_blocked_by_release_batch_manifest_failure",
            "release_closeout_batch_manifest",
            "release_batch_manifest_not_sealed_clean",
            "Run make release-closeout-batch-manifest-promote with a bound distribution ZIP.",
            "Seal the release batch manifest, then rerun make auto-improve-readiness.",
        ),
        (
            release_finality_summary,
            "promotion_blocked_by_release_finality_failure",
            "release_closeout_finality",
            "release_finality_status_not_pass",
            "Run make release-closeout-finality-verify and confirm finality_status=pass.",
            "Refresh finality attestation, then rerun make auto-improve-readiness.",
        ),
        (
            release_evidence_cohort_summary,
            "promotion_blocked_by_release_lineage_mismatch",
            "release_evidence_cohort",
            "release_lineage_not_strict_same_fingerprint",
            "Run make release-evidence-cohort RELEASE_EVIDENCE_COHORT_POLICY=strict_same_fingerprint and confirm strict_same_fingerprint=true.",
            "Refresh release evidence cohort until the release lineage is a single strict fingerprint, then rerun make auto-improve-readiness.",
        ),
        (
            artifact_finalization_summary,
            "promotion_blocked_by_artifact_finalization_failure",
            "artifact_finalization",
            "artifact_finalization_status_not_pass",
            "Run make release-run-ready, make release-sealed-run-ready, and make release-closeout-post-check-finalizer-dry-run.",
            "Refresh staged release authority evidence, then rerun make auto-improve-readiness.",
        ),
    ]
    for summary, blocker_id, scope, signal_id, required_evidence, next_step in gate_definitions:
        status = str(summary.get("status", "not_run")).strip() or "not_run"
        if status == "pass":
            continue
        summary_signal_ids = [
            str(item)
            for item in summary.get("signal_ids", [])
            if str(item).strip()
        ]
        blockers.append(
            {
                "id": blocker_id,
                "scope": "release_gate",
                "status": "open",
                "severity": "blocker",
                "accepted_risk": False,
                "gate_effect": GATE_EFFECT_BLOCKS_PROMOTION,
                "source_status": status,
                "reason": (
                    f"{scope} release gate is not pass: "
                    f"{str(summary.get('summary', '')).strip() or 'summary unavailable'}"
                ),
                "signal_ids": summary_signal_ids or [signal_id],
                "required_evidence": [
                    required_evidence,
                    "can_promote_result must stay false until this release gate is pass.",
                ],
                "recommended_next_step": next_step,
            }
        )
    return blockers


def _release_authority_preflight_promotion_blockers(
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    status = str(summary.get("status", "not_run")).strip() or "not_run"
    preflight_status = str(summary.get("preflight_status", "not_run")).strip() or "not_run"
    distribution_binding_status = (
        str(summary.get("distribution_binding_status", "unknown")).strip() or "unknown"
    )
    authority_preflight_status = (
        str(summary.get("authority_preflight_status", "unknown")).strip() or "unknown"
    )
    preflight_mode = str(summary.get("preflight_mode", "clean_required")).strip() or "clean_required"
    expected_blocked_preflight = bool(summary.get("expected_blocked_preflight", False))
    clean_required_preflight = bool(summary.get("clean_required_preflight", True))
    gate_pass = clean_required_preflight_passes(
        status=status,
        preflight_status=preflight_status,
        preflight_mode=preflight_mode,
        distribution_binding_status=distribution_binding_status,
        authority_preflight_status=authority_preflight_status,
        expected_blocked_preflight=expected_blocked_preflight,
        clean_required_preflight=clean_required_preflight,
    )
    if gate_pass:
        return []
    if _expected_blocked_preflight_is_self_referential(summary):
        return []

    signal_ids = _unique_strings(
        str(item).strip()
        for item in [
            *_string_list(summary.get("blocker_reason_ids")),
            *_string_list(summary.get("failure_ids")),
        ]
        if str(item).strip()
    )
    clean_shape_without_mode_flags = (
        preflight_status == "sealed_clean_pass"
        and distribution_binding_status == "pass"
        and authority_preflight_status == "clean"
    )
    if clean_shape_without_mode_flags:
        if preflight_mode != "clean_required":
            signal_ids.append("release_authority_preflight_not_clean_required")
        if expected_blocked_preflight:
            signal_ids.append("release_authority_preflight_expected_blocked")
        if not clean_required_preflight:
            signal_ids.append("release_authority_preflight_clean_required_missing")
    signal_ids = _unique_strings(signal_ids)
    if not signal_ids:
        signal_ids = ["release_authority_preflight_not_clean"]
    source_status = status if status in {"warn", "fail", "not_run", "missing", "unknown"} else "fail"
    return [
        {
            "id": "promotion_blocked_by_release_authority_preflight_failure",
            "scope": "release_gate",
            "status": "open",
            "severity": "blocker",
            "accepted_risk": False,
            "gate_effect": GATE_EFFECT_BLOCKS_PROMOTION,
            "source_status": source_status,
            "reason": (
                "release authority sealed preflight is not clean: "
                f"{str(summary.get('summary', '')).strip() or 'summary unavailable'}"
            ),
            "signal_ids": signal_ids,
            "required_evidence": [
                "Run make release-authority-sealed-preflight for operator handoff.",
                "Run make release-evidence-closeout-sealed-dry-run-check or the sealed release lane before promoting.",
                "can_promote_result must stay false until sealed authority preflight is clean.",
            ],
            "recommended_next_step": (
                "Refresh sealed authority preflight evidence, then rerun make auto-improve-readiness."
            ),
        }
    ]


def _artifact_contract_promotion_blockers(
    summary: dict[str, Any],
    artifact_freshness_report: dict[str, Any],
) -> list[dict[str, Any]]:
    status = str(summary.get("status", "missing")).strip() or "missing"
    schema_invalid_count = _int_value(summary.get("schema_invalid_artifact_count"))
    report_summary = artifact_freshness_report.get("summary")
    report_summary = report_summary if isinstance(report_summary, dict) else {}
    root_ephemeral_count = _int_value(report_summary.get("root_ephemeral_artifact_count"))
    non_utf8_count = _int_value(report_summary.get("non_utf8_text_artifact_count"))
    hard_failure_count = root_ephemeral_count + non_utf8_count
    mtime_attention_items = [
        item
        for item in _artifact_mtime_attention_items(artifact_freshness_report)
        if item["path"] == SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH
    ]
    status_allows_contract_debt = status in {"pass", "attention"}
    if (
        status_allows_contract_debt
        and schema_invalid_count == 0
        and hard_failure_count == 0
        and not mtime_attention_items
    ):
        return []
    invalid_artifacts = [
        str(item.get("path", "")).strip()
        for item in summary.get("schema_invalid_artifacts", [])
        if isinstance(item, dict) and str(item.get("path", "")).strip()
    ]
    if schema_invalid_count:
        reason = (
            "artifact freshness schema validation failed for "
            f"{schema_invalid_count} canonical artifact(s)"
        )
        if invalid_artifacts:
            reason = f"{reason}: {', '.join(invalid_artifacts[:6])}"
        signal_ids = ["artifact_freshness_schema_invalid"]
        required_evidence = [
            "Run make artifact-freshness-check and confirm status=pass.",
            "Regenerate schema-invalid canonical artifacts before promoting an auto-improve result.",
        ]
        recommended_next_step = (
            "Regenerate schema-invalid artifacts, then rerun make artifact-freshness and "
            "make auto-improve-readiness."
        )
    elif hard_failure_count:
        reason = (
            "artifact freshness found hard artifact failures: "
            f"root_ephemeral_artifact_count={root_ephemeral_count}; "
            f"non_utf8_text_artifact_count={non_utf8_count}"
        )
        signal_ids = ["artifact_freshness_hard_failure"]
        required_evidence = [
            "Remove root-ephemeral artifacts and repair non-UTF8 text artifacts.",
            "Run make artifact-freshness-check and confirm hard failure counts are zero.",
        ]
        recommended_next_step = (
            "Resolve hard artifact freshness failures, then rerun make artifact-freshness and "
            "make auto-improve-readiness."
        )
    elif mtime_attention_items:
        paths = ", ".join(item["path"] for item in mtime_attention_items[:6])
        reason = (
            "artifact freshness found mtime-sensitive artifact drift: "
            f"{paths}"
        )
        signal_ids = ["artifact_freshness_mtime_attention"]
        required_evidence = [
            "Regenerate mtime-sensitive artifacts with current metadata.",
            "Run make artifact-freshness-check and confirm mtime_sensitive_attention_issue_count=0.",
        ]
        recommended_next_step = (
            "Regenerate mtime-sensitive artifacts, then rerun make artifact-freshness and "
            "make auto-improve-readiness."
        )
    else:
        reason = f"artifact freshness status={status}; schema_invalid_artifact_count={schema_invalid_count}"
        signal_ids = ["artifact_freshness_status_not_pass"]
        required_evidence = [
            "Run make artifact-freshness-check and confirm status=pass.",
            "Resolve artifact freshness blockers before promoting an auto-improve result.",
        ]
        recommended_next_step = "Resolve artifact freshness blockers, then rerun make auto-improve-readiness."
    return [
        {
            "id": "promotion_blocked_by_artifact_contract_failure",
            "scope": "artifact_contract",
            "status": "open",
            "severity": "blocker",
            "accepted_risk": False,
            "gate_effect": GATE_EFFECT_BLOCKS_PROMOTION,
            "source_status": "fail",
            "reason": reason,
            "signal_ids": signal_ids,
            "required_evidence": required_evidence,
            "recommended_next_step": recommended_next_step,
        }
    ]
