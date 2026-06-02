from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
CURRENT_EXTERNAL_REPORT_STALE_TOTAL = 47
CURRENT_EXTERNAL_REPORT_STALE_COUNT = 5
CURRENT_EXTERNAL_REPORT_PRIORITY_STALE_COUNT = 3
ARTIFACT_FRESHNESS_REPORT_PATH = "ops/reports/artifact-freshness-report.json"
STALE_46_OF_46_RE = re.compile(r"\b46\s*/\s*46\b.*\bstale\b|\bstale\b.*\b46\s*/\s*46\b", re.I)
STALE_5_OF_47_RE = re.compile(r"\b5\b.*\bstale\b.*\b47\b|\b47\b.*\b5\b.*\bstale\b", re.I)
SUPERSEDED_CLAIM_RE = re.compile(r"\b(superseded|no longer current|historical(?:ly)? true)\b", re.I)


def _integer_summary_value(summary: dict[str, Any], key: str, fallback: int) -> int:
    value = summary.get(key)
    if isinstance(value, int):
        return value
    return fallback


def _current_canonical_state_from_artifact_freshness(payload: dict[str, Any]) -> dict[str, Any] | None:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return None
    stale_count = _integer_summary_value(summary, "stale_artifact_count", CURRENT_EXTERNAL_REPORT_STALE_COUNT)
    total_count = _integer_summary_value(summary, "artifact_count", CURRENT_EXTERNAL_REPORT_STALE_TOTAL)
    priority_stale_count = _integer_summary_value(
        summary,
        "operational_attention_artifact_count",
        stale_count,
    )
    return {
        "stale_report_count": stale_count,
        "total_report_count": total_count,
        "priority_stale_report_count": priority_stale_count,
        "summary": f"{stale_count} stale / {total_count} total; {priority_stale_count} priority stale",
    }


def _read_artifact_freshness_report(vault: Path) -> dict[str, Any] | None:
    path = vault / ARTIFACT_FRESHNESS_REPORT_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def external_report_current_canonical_state(
    vault: Path | None = None,
    *,
    artifact_freshness_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if artifact_freshness_report is None and vault is not None:
        artifact_freshness_report = _read_artifact_freshness_report(vault)
    if artifact_freshness_report is not None:
        state = _current_canonical_state_from_artifact_freshness(artifact_freshness_report)
        if state is not None:
            return state
    return {
        "stale_report_count": CURRENT_EXTERNAL_REPORT_STALE_COUNT,
        "total_report_count": CURRENT_EXTERNAL_REPORT_STALE_TOTAL,
        "priority_stale_report_count": CURRENT_EXTERNAL_REPORT_PRIORITY_STALE_COUNT,
        "summary": (
            f"{CURRENT_EXTERNAL_REPORT_STALE_COUNT} stale / "
            f"{CURRENT_EXTERNAL_REPORT_STALE_TOTAL} total; "
            f"{CURRENT_EXTERNAL_REPORT_PRIORITY_STALE_COUNT} priority stale"
        ),
    }


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
    if STALE_5_OF_47_RE.search(claim_text):
        return ACTION_LIFECYCLE_CURRENTLY_VALID
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
    current_canonical_report_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts = {lifecycle: 0 for lifecycle in sorted(ACTION_LIFECYCLES)}
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
        "current_canonical_report_state": current_canonical_report_state
        or external_report_current_canonical_state(),
    }
