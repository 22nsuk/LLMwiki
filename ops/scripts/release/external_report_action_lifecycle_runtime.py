from __future__ import annotations

import re
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
STALE_46_OF_46_RE = re.compile(r"\b46\s*/\s*46\b.*\bstale\b|\bstale\b.*\b46\s*/\s*46\b", re.I)
STALE_5_OF_47_RE = re.compile(r"\b5\b.*\bstale\b.*\b47\b|\b47\b.*\b5\b.*\bstale\b", re.I)
SUPERSEDED_CLAIM_RE = re.compile(r"\b(superseded|no longer current|historical(?:ly)? true)\b", re.I)


def external_report_current_canonical_state() -> dict[str, Any]:
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


def external_report_action_lifecycle_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
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
        "current_canonical_report_state": external_report_current_canonical_state(),
    }
