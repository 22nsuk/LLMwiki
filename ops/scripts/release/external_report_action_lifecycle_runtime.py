from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)

ACTION_LIFECYCLE_RESOLVED = "resolved"
ACTION_LIFECYCLE_HISTORICALLY_TRUE = "historically_true"
ACTION_LIFECYCLE_SUPERSEDED = "superseded"
ACTION_LIFECYCLE_CURRENTLY_VALID = "currently_valid"
ACTION_LIFECYCLES = {
    ACTION_LIFECYCLE_RESOLVED,
    ACTION_LIFECYCLE_HISTORICALLY_TRUE,
    ACTION_LIFECYCLE_SUPERSEDED,
    ACTION_LIFECYCLE_CURRENTLY_VALID,
}
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
ARTIFACT_FRESHNESS_ARTIFACT_KIND = "artifact_freshness_report"
ARTIFACT_FRESHNESS_OWNER_TARGET = "artifact-freshness"
EVIDENCE_STATUS_CURRENT = "current"
EVIDENCE_STATUS_MISSING = "missing"
EVIDENCE_STATUS_UNREADABLE = "unreadable"
EVIDENCE_STATUS_INVALID = "invalid"
EVIDENCE_STATUS_STALE = "stale"
EVIDENCE_STATUS_SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
STALE_46_OF_46_RE = re.compile(r"\b46\s*/\s*46\b.*\bstale\b|\bstale\b.*\b46\s*/\s*46\b", re.I)
SUPERSEDED_CLAIM_RE = re.compile(r"\b(superseded|no longer current|historical(?:ly)? true)\b", re.I)


def _integer_summary_value(summary: dict[str, Any], key: str) -> int | None:
    value = summary.get(key)
    if isinstance(value, int):
        return value
    return None


def _artifact_freshness_state(
    *,
    evidence_status: str,
    reason_id: str,
    stale_artifact_count: int | None = None,
    total_artifact_count: int | None = None,
    operational_attention_artifact_count: int | None = None,
    summary: str | None = None,
    stale_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if summary is None:
        summary = (
            f"{stale_artifact_count} stale / {total_artifact_count} total; "
            f"{operational_attention_artifact_count} operational attention"
        )
    state: dict[str, Any] = {
        "evidence_status": evidence_status,
        "evidence_path": ARTIFACT_FRESHNESS_REPORT_PATH,
        "stale_artifact_count": stale_artifact_count,
        "total_artifact_count": total_artifact_count,
        "operational_attention_artifact_count": operational_attention_artifact_count,
        "summary": summary,
        "reason_id": reason_id,
        "owner_target": ARTIFACT_FRESHNESS_OWNER_TARGET,
    }
    if stale_routing is not None:
        state["stale_routing"] = stale_routing
    return state


def _artifact_freshness_stale_routing(payload: dict[str, Any]) -> dict[str, Any] | None:
    routing = payload.get("stale_routing")
    if not isinstance(routing, dict):
        return None
    classification = str(routing.get("classification", "")).strip()
    recommended_lane = str(routing.get("recommended_lane", "")).strip()
    summary = str(routing.get("summary", "")).strip()
    recommended_targets = _clean_string_list(routing.get("recommended_targets"))
    reason_ids = _clean_string_list(routing.get("reason_ids"))
    if not classification or not recommended_lane or not summary:
        return None
    return {
        "classification": classification,
        "recommended_lane": recommended_lane,
        "recommended_targets": recommended_targets,
        "reason_ids": reason_ids,
        "summary": summary,
    }


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def _artifact_freshness_unavailable_state(*, evidence_status: str, reason_id: str) -> dict[str, Any]:
    return _artifact_freshness_state(
        evidence_status=evidence_status,
        reason_id=reason_id,
        summary=(
            f"artifact freshness evidence {evidence_status}; "
            "current canonical artifact freshness state unavailable"
        ),
    )


def _artifact_freshness_rejection_reason(
    payload: dict[str, Any],
    *,
    current_source_revision: str | None,
    current_source_tree_fingerprint: str | None,
) -> tuple[str, str] | None:
    currentness = payload.get("currentness")
    if payload.get("artifact_kind") != ARTIFACT_FRESHNESS_ARTIFACT_KIND:
        return EVIDENCE_STATUS_INVALID, "artifact_freshness_kind_mismatch"
    if payload.get("artifact_status") != "current":
        return EVIDENCE_STATUS_STALE, "artifact_freshness_artifact_status_not_current"
    if not isinstance(currentness, dict) or currentness.get("status") != "current":
        return EVIDENCE_STATUS_STALE, "artifact_freshness_currentness_not_current"
    observed_source_revision = str(payload.get("source_revision", "")).strip()
    observed_source_tree_fingerprint = str(payload.get("source_tree_fingerprint", "")).strip()
    if not observed_source_revision or not current_source_revision:
        return EVIDENCE_STATUS_SOURCE_IDENTITY_MISMATCH, "artifact_freshness_source_revision_missing"
    if not observed_source_tree_fingerprint or not current_source_tree_fingerprint:
        return (
            EVIDENCE_STATUS_SOURCE_IDENTITY_MISMATCH,
            "artifact_freshness_source_tree_fingerprint_missing",
        )
    if observed_source_tree_fingerprint != current_source_tree_fingerprint:
        return (
            EVIDENCE_STATUS_SOURCE_IDENTITY_MISMATCH,
            "artifact_freshness_source_tree_fingerprint_mismatch",
        )
    return None


def _artifact_freshness_summary_rejection_reason(payload: dict[str, Any]) -> tuple[str, str] | None:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return EVIDENCE_STATUS_INVALID, "artifact_freshness_summary_missing"
    for field in (
        "artifact_count",
        "stale_artifact_count",
        "operational_attention_artifact_count",
    ):
        value = summary.get(field)
        if not isinstance(value, int) or value < 0:
            return EVIDENCE_STATUS_INVALID, f"artifact_freshness_summary_{field}_invalid"
    return None


def _canonical_artifact_freshness_state_from_report(
    payload: dict[str, Any],
    *,
    current_source_revision: str | None,
    current_source_tree_fingerprint: str | None,
) -> dict[str, Any] | None:
    rejection_reason = _artifact_freshness_rejection_reason(
        payload,
        current_source_revision=current_source_revision,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
    )
    if rejection_reason is not None:
        return None
    if _artifact_freshness_summary_rejection_reason(payload) is not None:
        return None
    summary = payload.get("summary")
    assert isinstance(summary, dict)
    stale_artifact_count = _integer_summary_value(summary, "stale_artifact_count")
    total_artifact_count = _integer_summary_value(summary, "artifact_count")
    operational_attention_artifact_count = _integer_summary_value(summary, "operational_attention_artifact_count")
    assert stale_artifact_count is not None
    assert total_artifact_count is not None
    assert operational_attention_artifact_count is not None
    return _artifact_freshness_state(
        evidence_status=EVIDENCE_STATUS_CURRENT,
        reason_id="artifact_freshness_report_current",
        stale_artifact_count=stale_artifact_count,
        total_artifact_count=total_artifact_count,
        operational_attention_artifact_count=operational_attention_artifact_count,
        stale_routing=_artifact_freshness_stale_routing(payload),
    )


def _read_artifact_freshness_report(vault: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = vault / ARTIFACT_FRESHNESS_REPORT_PATH
    if not path.is_file():
        return None, EVIDENCE_STATUS_MISSING
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, EVIDENCE_STATUS_UNREADABLE
    except json.JSONDecodeError:
        return None, EVIDENCE_STATUS_INVALID
    if not isinstance(payload, dict):
        return None, EVIDENCE_STATUS_INVALID
    return payload, None


def canonical_artifact_freshness_state(
    vault: Path | None = None,
    *,
    artifact_freshness_report: dict[str, Any] | None = None,
    current_source_revision: str | None = None,
    current_source_tree_fingerprint: str | None = None,
) -> dict[str, Any]:
    read_issue: str | None = None
    if artifact_freshness_report is None and vault is not None:
        artifact_freshness_report, read_issue = _read_artifact_freshness_report(vault)
    fallback_evidence_status = read_issue or EVIDENCE_STATUS_MISSING
    fallback_reason_id = (
        f"artifact_freshness_report_{fallback_evidence_status}"
        if read_issue is not None
        else "artifact_freshness_report_not_provided"
    )
    if artifact_freshness_report is not None:
        if vault is not None:
            current_source_revision = current_source_revision or resolve_source_revision(vault).revision
            current_source_tree_fingerprint = (
                current_source_tree_fingerprint or release_source_tree_fingerprint(vault)
            )
        rejection = _artifact_freshness_rejection_reason(
            artifact_freshness_report,
            current_source_revision=current_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
        )
        if rejection is None:
            rejection = _artifact_freshness_summary_rejection_reason(artifact_freshness_report)
        if rejection is not None:
            fallback_evidence_status, fallback_reason_id = rejection
        state = _canonical_artifact_freshness_state_from_report(
            artifact_freshness_report,
            current_source_revision=current_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
        )
        if state is not None:
            return state
    return _artifact_freshness_unavailable_state(
        evidence_status=fallback_evidence_status,
        reason_id=fallback_reason_id,
    )


def classify_external_report_action_lifecycle(action_item: dict[str, Any]) -> str:
    claim_text = str(action_item.get("claim_text", "")).strip()
    if not claim_text:
        claim_text = " ".join(
            str(action_item.get(field, "")).strip()
            for field in ("theme", "current_status", "recommended_target")
            if str(action_item.get(field, "")).strip()
        )
    if STALE_46_OF_46_RE.search(claim_text):
        return ACTION_LIFECYCLE_HISTORICALLY_TRUE
    if SUPERSEDED_CLAIM_RE.search(claim_text):
        return ACTION_LIFECYCLE_SUPERSEDED
    if str(action_item.get("current_status", "")).strip() == "implemented":
        return ACTION_LIFECYCLE_RESOLVED
    return ACTION_LIFECYCLE_CURRENTLY_VALID


def external_report_action_lifecycle_record(action_item: dict[str, Any]) -> dict[str, Any]:
    claim_text = str(action_item.get("claim_text", "")).strip()
    if not claim_text:
        claim_text = str(action_item.get("theme", "")).strip()
    lifecycle = classify_external_report_action_lifecycle({**action_item, "claim_text": claim_text})
    return {
        "claim_text": claim_text,
        "lifecycle": lifecycle,
        "is_active": lifecycle == ACTION_LIFECYCLE_CURRENTLY_VALID,
    }


def external_report_action_lifecycle_summary(
    items: list[dict[str, Any]],
    *,
    canonical_artifact_freshness_state_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts = dict.fromkeys(sorted(ACTION_LIFECYCLES), 0)
    for item in items:
        lifecycle = str(item.get("lifecycle", "")).strip()
        if lifecycle in counts:
            counts[lifecycle] += 1
    return {
        "lifecycle_counts": counts,
        "currently_valid_action_count": counts[ACTION_LIFECYCLE_CURRENTLY_VALID],
        "resolved_action_count": counts[ACTION_LIFECYCLE_RESOLVED],
        "historical_or_superseded_action_count": (
            counts[ACTION_LIFECYCLE_HISTORICALLY_TRUE]
            + counts[ACTION_LIFECYCLE_SUPERSEDED]
        ),
        "active_action_ids": [
            str(item.get("action_id", "")).strip()
            for item in items
            if str(item.get("lifecycle", "")).strip() == ACTION_LIFECYCLE_CURRENTLY_VALID
        ],
        "archived_action_ids": [
            str(item.get("action_id", "")).strip()
            for item in items
            if str(item.get("lifecycle", "")).strip() != ACTION_LIFECYCLE_CURRENTLY_VALID
        ],
        "canonical_artifact_freshness_state": canonical_artifact_freshness_state_record
        or canonical_artifact_freshness_state(),
    }
