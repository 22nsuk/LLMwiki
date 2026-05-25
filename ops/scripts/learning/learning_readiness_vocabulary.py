from __future__ import annotations

from collections.abc import Iterable
from typing import Any

LEARNING_STATUS_LIKELY = "learning_likely"
LEARNING_STATUS_UNCERTAIN = "learning_uncertain"
LEARNING_STATUS_NOT_RUNNABLE = "not_runnable"
LEARNING_READINESS_STATUSES = (
    LEARNING_STATUS_LIKELY,
    LEARNING_STATUS_UNCERTAIN,
    LEARNING_STATUS_NOT_RUNNABLE,
)

LEARNING_REVIEW_REQUIRED_BLOCKER_ID = "learning_blocked_by_review_required"
LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID = "learning_blocked_by_execution_not_runnable"
EXECUTION_NO_RUNNABLE_PROPOSAL_BLOCKER_ID = "execution_blocked_by_no_runnable_proposal"
LEARNING_RELEASE_BLOCKER_IDS = (
    LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID,
    LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
)
RELEASE_BLOCKER_IDS = (
    *LEARNING_RELEASE_BLOCKER_IDS,
    EXECUTION_NO_RUNNABLE_PROPOSAL_BLOCKER_ID,
)
LEARNING_SIGNOFF_SUPPORTED_BLOCKER_IDS = (LEARNING_REVIEW_REQUIRED_BLOCKER_ID,)


def learning_blocker_id_for_status(status: str) -> str:
    normalized = status.strip()
    if normalized == LEARNING_STATUS_NOT_RUNNABLE:
        return LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID
    return LEARNING_REVIEW_REQUIRED_BLOCKER_ID


def is_learning_release_blocker_id(blocker_id: str) -> bool:
    return blocker_id.strip() in LEARNING_RELEASE_BLOCKER_IDS


def is_signoff_supported_learning_blocker_id(blocker_id: str) -> bool:
    return blocker_id.strip() in LEARNING_SIGNOFF_SUPPORTED_BLOCKER_IDS


def learning_release_blocker_ids_from_report(
    report: dict[str, Any],
    *,
    field_names: Iterable[str] = (
        "learning_claim_blockers",
        "learning_blockers",
        "release_blockers",
    ),
) -> list[str]:
    ids: list[str] = []
    for field_name in field_names:
        raw_items = report.get(field_name)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            blocker_id = str(item.get("id", "")).strip()
            if not blocker_id or not is_learning_release_blocker_id(blocker_id):
                continue
            if "release_blocker" in item and not bool(item.get("release_blocker")):
                continue
            if str(item.get("status", "")).strip() != "open":
                continue
            if blocker_id not in ids:
                ids.append(blocker_id)
    return ids
