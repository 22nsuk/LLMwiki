from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import report_path

from .external_report_inventory_runtime import (
    ARCHIVE_STATUS_RE,
    REFERENCE_MANIFEST,
    SUPERSEDED_BY_RE,
    active_report_paths,
    archived_report_paths,
    content_sha256,
    coverage_markers,
    matched_actions,
    priority_counts,
    report_text,
    report_type_for_path,
    unmatched_recommendation_count,
)


def report_coverage_item(vault: Path, path: Path) -> dict[str, Any]:
    rel_path = report_path(vault, path)
    text = report_text(path)
    report_type = report_type_for_path(path)
    operator_only_rationale = ""
    if report_type == "binary_report":
        action_ids = ["operator_only_external_report_binary"]
        operator_only_rationale = "binary_report_requires_operator_review"
    elif report_type == "reference_manifest":
        action_ids = ["external_report_lifecycle"]
        operator_only_rationale = "reference_manifest_lifecycle_evidence"
    elif not text:
        action_ids = ["external_report_lifecycle"]
        operator_only_rationale = "unreadable_narrative_report"
    else:
        action_ids = matched_actions(text)
    if path.name == Path(REFERENCE_MANIFEST).name:
        action_ids = sorted(set(action_ids) | {"active_report_manifest_freshness"})
    return {
        "path": rel_path,
        "report_type": report_type,
        "content_sha256": content_sha256(path),
        "coverage_markers": coverage_markers(path, text),
        "priority_mentions": priority_counts(text),
        "unmatched_recommendation_count": unmatched_recommendation_count(text),
        "matched_action_ids": action_ids,
        "matched_action_count": len(action_ids),
        "operator_only_rationale": operator_only_rationale,
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


def coverage_action_basis(profile: dict[str, Any], statuses: dict[str, str]) -> dict[str, Any]:
    unresolved = sorted(_unresolved_action_ids(profile, statuses))
    return {
        "report_type": str(profile.get("report_type", "")),
        "content_sha256": str(profile.get("content_sha256", "")),
        "matched_action_ids": sorted(str(action_id) for action_id in profile["matched_action_ids"]),
        "matched_action_count": int(profile.get("matched_action_count") or 0),
        "unresolved_action_ids": unresolved,
        "unresolved_action_count": len(unresolved),
        "unmatched_recommendation_count": int(
            profile.get("unmatched_recommendation_count") or 0
        ),
        "operator_only_rationale": str(profile.get("operator_only_rationale", "")).strip(),
    }


def coverage_archive_decision_code(
    action_basis: dict[str, Any],
    *,
    implemented_code: str = "all_structured_actions_implemented",
) -> str:
    if action_basis["operator_only_rationale"]:
        return str(action_basis["operator_only_rationale"])
    if int(action_basis["unmatched_recommendation_count"]) > 0:
        return "unmatched_recommendations_require_operator_review"
    if int(action_basis["unresolved_action_count"]) > 0:
        return "unresolved_actions_keep_report_active"
    return implemented_code


def coverage_with_action_basis(
    coverage: list[dict[str, Any]],
    statuses: dict[str, str],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in coverage:
        action_basis = coverage_action_basis(item, statuses)
        enriched.append(
            {
                **item,
                "unresolved_action_ids": action_basis["unresolved_action_ids"],
                "unresolved_action_count": action_basis["unresolved_action_count"],
                "archive_decision_code": coverage_archive_decision_code(action_basis),
            }
        )
    return enriched


def _archive_decision_code(
    *,
    profile: dict[str, Any],
    action_basis: dict[str, Any],
    archive_recommended: bool,
    reason_code: str,
) -> str:
    if archive_recommended:
        return reason_code
    action_decision_code = coverage_archive_decision_code(
        action_basis,
        implemented_code="implemented_action_basis_without_archive_marker",
    )
    if action_decision_code != "implemented_action_basis_without_archive_marker":
        return action_decision_code
    if profile.get("report_type") != "narrative_report":
        return reason_code
    return action_decision_code


def _decision_record(
    profile: dict[str, Any],
    statuses: dict[str, str],
    *,
    archive_recommended: bool,
    reason: str,
    reason_code: str,
    superseded_by: list[str],
) -> dict[str, Any]:
    action_basis = coverage_action_basis(profile, statuses)
    return {
        **action_basis,
        "archive_decision_code": _archive_decision_code(
            profile=profile,
            action_basis=action_basis,
            archive_recommended=archive_recommended,
            reason_code=reason_code,
        ),
        "archive_recommended": archive_recommended,
        "reason": reason,
        "superseded_by": superseded_by,
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
            return _decision_record(
                profile,
                statuses,
                archive_recommended=False,
                reason=(
                    "Binary active reports require operator-only review or an explicit "
                    "extracted mapping before lifecycle automation can archive them."
                ),
                reason_code="binary_report_requires_operator_review",
                superseded_by=[],
            )
        return _decision_record(
            profile,
            statuses,
            archive_recommended=False,
            reason="Reference manifest remains active lifecycle evidence.",
            reason_code="reference_manifest_lifecycle_evidence",
            superseded_by=[],
        )
    action_ids = {str(action_id) for action_id in profile["matched_action_ids"]}
    if not action_ids:
        if profile.get("lifecycle_namespace") == "archive":
            return _decision_record(
                profile,
                statuses,
                archive_recommended=True,
                reason="Archived external report has no structured action coverage; archive remains sticky.",
                reason_code="archive_sticky_without_structured_action_coverage",
                superseded_by=[],
            )
        return _decision_record(
            profile,
            statuses,
            archive_recommended=False,
            reason="No structured action coverage was detected; keep active for operator review.",
            reason_code="unmatched_recommendations_require_operator_review",
            superseded_by=[],
        )
    if bool(profile["explicit_archive_status"]):
        return _decision_record(
            profile,
            statuses,
            archive_recommended=True,
            reason="External report carries an explicit closed/superseded archive lifecycle marker.",
            reason_code="explicit_archive_status",
            superseded_by=list(profile["explicit_successor_paths"]),
        )

    unresolved = sorted(_unresolved_action_ids(profile, statuses))
    if not unresolved:
        return _decision_record(
            profile,
            statuses,
            archive_recommended=True,
            reason="All structured action themes from this external report are implemented in canonical evidence.",
            reason_code="all_structured_actions_implemented",
            superseded_by=[],
        )

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
        return _decision_record(
            profile,
            statuses,
            archive_recommended=True,
            reason=(
                "External report has no unique unresolved action themes; remaining open themes are covered by "
                "a broader active external report."
            ),
            reason_code="unresolved_actions_covered_by_broader_report",
            superseded_by=sorted(covering_reports),
        )
    return _decision_record(
        profile,
        statuses,
        archive_recommended=False,
        reason="External report still carries unique unresolved action themes not covered by another active report.",
        reason_code="unresolved_actions_keep_report_active",
        superseded_by=[],
    )


def archived_report_action_basis_records(
    vault: Path,
    statuses: dict[str, str],
) -> list[dict[str, Any]]:
    active_profiles = report_lifecycle_profiles(vault, active_report_paths(vault))
    archived_profiles = report_lifecycle_profiles(vault, archived_report_paths(vault))
    profiles = [*active_profiles, *archived_profiles]
    records: list[dict[str, Any]] = []
    for profile in archived_profiles:
        decision = lifecycle_decision(profile, profiles=profiles, statuses=statuses)
        records.append(
            {
                "path": str(profile["path"]),
                **coverage_action_basis(profile, statuses),
                "archive_decision_code": str(decision["archive_decision_code"]),
            }
        )
    return sorted(records, key=lambda item: str(item["path"]))
