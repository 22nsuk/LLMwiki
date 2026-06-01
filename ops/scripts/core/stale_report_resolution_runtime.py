from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.core.path_runtime import normalize_repo_path_text
from ops.scripts.core.report_bucket_runtime import (
    BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR,
    classify_report_bucket,
    move_report_delete_first,
)

STALE_REPORT_DECISION_REGENERATE = "regenerate"
STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET = "remove_from_canonical_set"
STALE_REPORT_DECISIONS = {
    STALE_REPORT_DECISION_REGENERATE,
    STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
}
STALE_REPORT_NON_CANONICAL_MARKER = "excluded_from_canonical_set"
STALE_REPORT_DELETED_MARKER = "deleted_from_canonical_set"
RESOLUTION_STATUS_PASS = "pass"
RESOLUTION_STATUS_FAIL = "fail"

STALE_CANONICAL_REPORT_PATHS = (
    "ops/reports/goal-runtime-certificate.json",
    "ops/reports/learning-readiness-signoff.json",
    "ops/reports/public-check-summary.json",
    "ops/reports/release-workflow-order-guard.json",
    "ops/reports/workflow-dependency-planner.json",
)
PRIORITY_STALE_CANONICAL_REPORT_PATHS = (
    "ops/reports/goal-runtime-certificate.json",
    "ops/reports/learning-readiness-signoff.json",
    "ops/reports/public-check-summary.json",
)

SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH = (
    "build/release/release-post-seal-attestation.json"
)
SEALED_SIDECAR_DECISION_REGENERATE = "regenerate"
SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET = "remove_from_active_set"
SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL = "preserve_non_canonical"
SEALED_SIDECAR_DECISIONS = {
    SEALED_SIDECAR_DECISION_REGENERATE,
    SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
    SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL,
}
SEALED_SIDECAR_NON_CANONICAL_MARKER = "archived_non_canonical_evidence"
SEALED_SIDECAR_REMOVED_MARKER = "removed_from_active_sealed_sidecar_set"
SEALED_SIDECAR_STATUS_PASS = "pass"
SEALED_SIDECAR_STATUS_INCOMPLETE = "incomplete"


def _normalized_repo_path(path: str | Path) -> str:
    normalized = normalize_repo_path_text(Path(path).as_posix())
    if (
        normalized is None
        or normalized in {".", ".."}
        or normalized.startswith("../")
        or normalized.startswith("/")
    ):
        raise ValueError(f"path must be vault-relative: {path}")
    return normalized


def _text(value: object) -> str:
    return str(value or "").strip()


def _record_error(report_path: str, code: str, message: str) -> dict[str, str]:
    return {
        "report_path": report_path,
        "code": code,
        "message": message,
    }


def stale_report_resolution_record(
    report_path: str | Path,
    *,
    decision: str,
    post_state_head_aligned: bool,
    preserved_non_canonical: bool = False,
    preservation_reason: str = "",
    non_canonical_marker: str = "",
    is_priority: bool | None = None,
) -> dict[str, Any]:
    rel_path = _normalized_repo_path(report_path)
    if decision not in STALE_REPORT_DECISIONS:
        raise ValueError(f"unsupported stale report decision: {decision}")
    canonical_retained = decision == STALE_REPORT_DECISION_REGENERATE
    excluded_from_canonical = not canonical_retained
    marker = _text(non_canonical_marker)
    if excluded_from_canonical and not marker:
        marker = (
            STALE_REPORT_NON_CANONICAL_MARKER
            if preserved_non_canonical
            else STALE_REPORT_DELETED_MARKER
        )
    return {
        "report_path": rel_path,
        "decision": decision,
        "is_priority": (
            rel_path in PRIORITY_STALE_CANONICAL_REPORT_PATHS
            if is_priority is None
            else bool(is_priority)
        ),
        "canonical_retained": canonical_retained,
        "excluded_from_canonical": excluded_from_canonical,
        "non_canonical_marker": "" if canonical_retained else marker,
        "preserved_non_canonical": bool(preserved_non_canonical)
        and excluded_from_canonical,
        "preservation_reason": _text(preservation_reason),
        "post_state_head_aligned": bool(post_state_head_aligned),
    }


def _normalise_resolution_input(record: dict[str, Any]) -> dict[str, Any]:
    rel_path = _normalized_repo_path(_text(record.get("report_path")))
    decision = _text(record.get("decision"))
    canonical_retained = decision == STALE_REPORT_DECISION_REGENERATE
    excluded = bool(record.get("excluded_from_canonical"))
    if "canonical_retained" in record:
        canonical_retained = bool(record.get("canonical_retained"))
    return {
        "report_path": rel_path,
        "decision": decision,
        "is_priority": rel_path in PRIORITY_STALE_CANONICAL_REPORT_PATHS,
        "canonical_retained": canonical_retained,
        "excluded_from_canonical": excluded,
        "non_canonical_marker": _text(record.get("non_canonical_marker")),
        "preserved_non_canonical": bool(record.get("preserved_non_canonical")),
        "preservation_reason": _text(record.get("preservation_reason")),
        "post_state_head_aligned": bool(record.get("post_state_head_aligned")),
    }


def validate_stale_report_resolutions(
    records: list[dict[str, Any]],
    *,
    required_report_paths: tuple[str, ...] = STALE_CANONICAL_REPORT_PATHS,
) -> dict[str, Any]:
    required = tuple(_normalized_repo_path(path) for path in required_report_paths)
    required_set = set(required)
    normalised_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    by_path: dict[str, list[dict[str, Any]]] = {}
    for raw_record in records:
        try:
            record = _normalise_resolution_input(raw_record)
        except ValueError as exc:
            errors.append(_record_error("<unknown>", "invalid_report_path", str(exc)))
            continue
        normalised_records.append(record)
        by_path.setdefault(record["report_path"], []).append(record)

    missing_reports = [path for path in required if path not in by_path]
    duplicate_reports = sorted(path for path, items in by_path.items() if len(items) > 1)
    unexpected_reports = sorted(path for path in by_path if path not in required_set)
    for path in missing_reports:
        errors.append(_record_error(path, "missing_decision", "stale report has no decision"))
    for path in duplicate_reports:
        errors.append(_record_error(path, "duplicate_decision", "stale report has multiple decisions"))
    for path in unexpected_reports:
        errors.append(_record_error(path, "unexpected_report", "report is outside the stale canonical set"))

    retained_not_head_aligned_reports: list[str] = []
    excluded_without_marker_reports: list[str] = []
    preserved_without_reason_reports: list[str] = []
    priority_unresolved_reports: list[str] = []
    canonical_retained_reports: list[str] = []
    excluded_reports: list[str] = []

    for record in normalised_records:
        report_path = str(record["report_path"])
        decision = str(record["decision"])
        if decision not in STALE_REPORT_DECISIONS:
            errors.append(
                _record_error(
                    report_path,
                    "invalid_decision",
                    f"unsupported stale report decision: {decision}",
                )
            )
            continue

        if decision == STALE_REPORT_DECISION_REGENERATE:
            canonical_retained_reports.append(report_path)
            if record["excluded_from_canonical"]:
                errors.append(
                    _record_error(
                        report_path,
                        "regenerated_report_marked_excluded",
                        "regenerated reports remain in the canonical set",
                    )
                )
            if record["preserved_non_canonical"]:
                errors.append(
                    _record_error(
                        report_path,
                        "regenerated_report_marked_preserved",
                        "regenerated reports must not also be preserved as stale",
                    )
                )
            if not record["post_state_head_aligned"]:
                retained_not_head_aligned_reports.append(report_path)
                errors.append(
                    _record_error(
                        report_path,
                        "canonical_retained_not_head_aligned",
                        "canonical-retained reports must be HEAD_Aligned_Current",
                    )
                )
        else:
            excluded_reports.append(report_path)
            if not record["excluded_from_canonical"]:
                errors.append(
                    _record_error(
                        report_path,
                        "removed_report_not_excluded",
                        "removed reports must be explicitly excluded from canonical",
                    )
                )
            if not record["non_canonical_marker"]:
                excluded_without_marker_reports.append(report_path)
                errors.append(
                    _record_error(
                        report_path,
                        "excluded_report_missing_marker",
                        "excluded reports require an explicit non-canonical marker",
                    )
                )
            if record["preserved_non_canonical"] and not record["preservation_reason"]:
                preserved_without_reason_reports.append(report_path)
                errors.append(
                    _record_error(
                        report_path,
                        "preserved_report_missing_reason",
                        "preserved stale reports require a preservation reason",
                    )
                )

        if record["is_priority"]:
            resolved = (
                decision == STALE_REPORT_DECISION_REGENERATE
                and record["post_state_head_aligned"]
            ) or (
                decision == STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET
                and record["excluded_from_canonical"]
                and bool(record["non_canonical_marker"])
            )
            if not resolved:
                priority_unresolved_reports.append(report_path)

    all_retained_head_aligned = not retained_not_head_aligned_reports
    priority_reports_resolved = not priority_unresolved_reports
    status = RESOLUTION_STATUS_PASS if not errors else RESOLUTION_STATUS_FAIL
    return {
        "status": status,
        "complete": status == RESOLUTION_STATUS_PASS,
        "records": normalised_records,
        "required_reports": list(required),
        "missing_reports": missing_reports,
        "duplicate_reports": duplicate_reports,
        "unexpected_reports": unexpected_reports,
        "canonical_retained_reports": sorted(set(canonical_retained_reports)),
        "excluded_reports": sorted(set(excluded_reports)),
        "retained_not_head_aligned_reports": sorted(set(retained_not_head_aligned_reports)),
        "excluded_without_marker_reports": sorted(set(excluded_without_marker_reports)),
        "preserved_without_reason_reports": sorted(set(preserved_without_reason_reports)),
        "priority_unresolved_reports": sorted(set(priority_unresolved_reports)),
        "all_retained_reports_head_aligned": all_retained_head_aligned,
        "priority_reports_resolved": priority_reports_resolved,
        "errors": errors,
    }


def remove_stale_report_from_canonical_set(
    vault: Path,
    *,
    report_path: str | Path,
    destination_path: str | Path | None = None,
    preservation_reason: str = "",
) -> dict[str, Any]:
    source_rel = _normalized_repo_path(report_path)
    if destination_path is not None:
        if not _text(preservation_reason):
            raise ValueError("preserving a stale report requires a preservation_reason")
        destination_rel = _normalized_repo_path(destination_path)
        move_result = move_report_delete_first(
            vault,
            source_path=source_rel,
            destination_path=destination_rel,
        )
        return {
            "resolution": stale_report_resolution_record(
                source_rel,
                decision=STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
                post_state_head_aligned=False,
                preserved_non_canonical=True,
                preservation_reason=preservation_reason,
            ),
            "move": move_result,
        }

    source = vault / source_rel
    if not source.exists():
        raise FileNotFoundError(source_rel)
    source.unlink()
    return {
        "resolution": stale_report_resolution_record(
            source_rel,
            decision=STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
            post_state_head_aligned=False,
            preserved_non_canonical=False,
        ),
        "deleted": True,
        "source_exists_after_delete": source.exists(),
    }


def sealed_sidecar_cleanup_record(
    *,
    decision: str,
    sidecar_path: str | Path = SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
    post_state_head_aligned: bool = False,
    preservation_reason: str = "",
    non_canonical_marker: str = "",
) -> dict[str, Any]:
    rel_path = _normalized_repo_path(sidecar_path)
    if decision not in SEALED_SIDECAR_DECISIONS:
        raise ValueError(f"unsupported sealed sidecar decision: {decision}")
    active_after_cleanup = decision == SEALED_SIDECAR_DECISION_REGENERATE
    preserved_non_canonical = decision == SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL
    marker = _text(non_canonical_marker)
    if preserved_non_canonical and not marker:
        marker = SEALED_SIDECAR_NON_CANONICAL_MARKER
    elif decision == SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET and not marker:
        marker = SEALED_SIDECAR_REMOVED_MARKER
    return {
        "sidecar_path": rel_path,
        "decision": decision,
        "active_after_cleanup": active_after_cleanup,
        "post_state_head_aligned": bool(post_state_head_aligned),
        "preserved_non_canonical": preserved_non_canonical,
        "preservation_reason": _text(preservation_reason),
        "non_canonical_marker": "" if active_after_cleanup else marker,
    }


def sealed_sidecar_entry_record(
    path: str | Path,
    *,
    head_aligned_current: bool,
    active: bool = True,
) -> dict[str, Any]:
    rel_path = _normalized_repo_path(path)
    bucket = classify_report_bucket(rel_path)
    return {
        "sidecar_path": rel_path,
        "bucket": bucket,
        "active": bool(active),
        "authoritative": bucket == BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR,
        "head_aligned_current": bool(head_aligned_current),
    }


def validate_sealed_sidecar_cleanup(
    cleanup_record: dict[str, Any],
    *,
    active_sidecars: list[dict[str, Any]],
) -> dict[str, Any]:
    sidecar_path = _normalized_repo_path(_text(cleanup_record.get("sidecar_path")))
    decision = _text(cleanup_record.get("decision"))
    active_after_cleanup = bool(cleanup_record.get("active_after_cleanup"))
    post_state_head_aligned = bool(cleanup_record.get("post_state_head_aligned"))
    preserved_non_canonical = bool(cleanup_record.get("preserved_non_canonical"))
    preservation_reason = _text(cleanup_record.get("preservation_reason"))
    non_canonical_marker = _text(cleanup_record.get("non_canonical_marker"))

    errors: list[dict[str, str]] = []
    if decision not in SEALED_SIDECAR_DECISIONS:
        errors.append(
            _record_error(
                sidecar_path,
                "invalid_decision",
                f"unsupported sealed sidecar decision: {decision}",
            )
        )
    if decision == SEALED_SIDECAR_DECISION_REGENERATE:
        if not active_after_cleanup:
            errors.append(
                _record_error(
                    sidecar_path,
                    "regenerated_sidecar_not_active",
                    "regenerated sealed sidecar must remain active",
                )
            )
        if not post_state_head_aligned:
            errors.append(
                _record_error(
                    sidecar_path,
                    "regenerated_sidecar_not_head_aligned",
                    "regenerated sealed sidecar must be HEAD_Aligned_Current",
                )
            )
    elif decision == SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET:
        if active_after_cleanup:
            errors.append(
                _record_error(
                    sidecar_path,
                    "removed_sidecar_still_active",
                    "removed sealed sidecar must leave the active set",
                )
            )
    elif decision == SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL:
        if active_after_cleanup:
            errors.append(
                _record_error(
                    sidecar_path,
                    "preserved_sidecar_still_active",
                    "preserved stale sidecar must leave the active set",
                )
            )
        if not preserved_non_canonical:
            errors.append(
                _record_error(
                    sidecar_path,
                    "preserved_sidecar_missing_preserved_flag",
                    "preserved stale sidecar must be marked non-canonical",
                )
            )
        if not non_canonical_marker:
            errors.append(
                _record_error(
                    sidecar_path,
                    "preserved_sidecar_missing_marker",
                    "preserved stale sidecar requires a non-canonical marker",
                )
            )
        if not preservation_reason:
            errors.append(
                _record_error(
                    sidecar_path,
                    "preserved_sidecar_missing_reason",
                    "preserved stale sidecar requires a preservation reason",
                )
            )

    authoritative_active: list[str] = []
    stale_active: list[str] = []
    for raw_entry in active_sidecars:
        entry_path = _normalized_repo_path(_text(raw_entry.get("sidecar_path")))
        bucket = _text(raw_entry.get("bucket")) or classify_report_bucket(entry_path)
        active = bool(raw_entry.get("active", True))
        authoritative = bool(raw_entry.get("authoritative", bucket == BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR))
        if not active or not authoritative:
            continue
        authoritative_active.append(entry_path)
        if not bool(raw_entry.get("head_aligned_current")):
            stale_active.append(entry_path)
            errors.append(
                _record_error(
                    entry_path,
                    "active_sidecar_not_head_aligned",
                    "active authoritative sealed sidecars must be HEAD_Aligned_Current",
                )
            )
        if (
            entry_path == sidecar_path
            and decision
            in {
                SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
                SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL,
            }
        ):
            errors.append(
                _record_error(
                    entry_path,
                    "target_sidecar_still_active",
                    "removed or preserved target sidecar is still active",
                )
            )

    status = SEALED_SIDECAR_STATUS_PASS if not errors else SEALED_SIDECAR_STATUS_INCOMPLETE
    return {
        "status": status,
        "complete": status == SEALED_SIDECAR_STATUS_PASS,
        "retry_required": status != SEALED_SIDECAR_STATUS_PASS,
        "sidecar_path": sidecar_path,
        "decision": decision,
        "active_authoritative_sidecar_paths": sorted(set(authoritative_active)),
        "stale_active_sidecar_paths": sorted(set(stale_active)),
        "errors": errors,
    }


def sealed_sidecar_cleanup_retry_summary(
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    validations: list[dict[str, Any]] = []
    for index, attempt in enumerate(attempts, start=1):
        validation = validate_sealed_sidecar_cleanup(
            attempt["cleanup_record"],
            active_sidecars=attempt.get("active_sidecars", []),
        )
        validation = {"attempt": index, **validation}
        validations.append(validation)
        if validation["status"] == SEALED_SIDECAR_STATUS_PASS:
            return {
                "status": SEALED_SIDECAR_STATUS_PASS,
                "complete": True,
                "retry_required": False,
                "attempt_count": index,
                "validations": validations,
            }
    return {
        "status": SEALED_SIDECAR_STATUS_INCOMPLETE,
        "complete": False,
        "retry_required": True,
        "attempt_count": len(attempts),
        "validations": validations,
    }
