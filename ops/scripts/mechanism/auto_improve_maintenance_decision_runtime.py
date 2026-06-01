from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAINTENANCE_ACTION_RESUME_TARGET = "auto-improve-goal-maintenance-action"
MAINTENANCE_ACTION_RUNNER_ACTION = "resume_session_with_additional_proposal_budget"


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _expected_maintenance_cycle_count(
    *,
    start_elapsed_seconds: int,
    target_elapsed_seconds: int,
    interval_seconds: int,
) -> int:
    if start_elapsed_seconds >= target_elapsed_seconds:
        return 0
    remaining = target_elapsed_seconds - start_elapsed_seconds
    return (remaining + interval_seconds - 1) // interval_seconds + 1


def _maintenance_queue_action(queue_snapshot: list[str]) -> dict[str, Any]:
    if not queue_snapshot:
        return {
            "status": "none",
            "reason": "queue_empty",
            "proposal_ids": [],
            "runner_action": "none",
            "proposal_budget_increment": 0,
            "resume_target": "",
            "recommended_next_step": "Refresh auto-improve readiness and inspect queue remediations.",
        }
    if all(item.startswith("recent_log_overlap_queue_blocked__") for item in queue_snapshot):
        return {
            "status": "action_required",
            "reason": "recent_log_overlap_queue_blocked",
            "proposal_ids": queue_snapshot,
            "runner_action": MAINTENANCE_ACTION_RUNNER_ACTION,
            "proposal_budget_increment": 1,
            "resume_target": MAINTENANCE_ACTION_RESUME_TARGET,
            "recommended_next_step": (
                f"Run make {MAINTENANCE_ACTION_RESUME_TARGET} so the generated "
                "recent-log-overlap queue-unblock proposal can run instead of "
                "repeating maintenance refreshes."
            ),
        }
    return {
        "status": "action_required",
        "reason": "stable_runnable_queue",
        "proposal_ids": queue_snapshot,
        "runner_action": MAINTENANCE_ACTION_RUNNER_ACTION,
        "proposal_budget_increment": 1,
        "resume_target": MAINTENANCE_ACTION_RESUME_TARGET,
        "recommended_next_step": (
            f"Run make {MAINTENANCE_ACTION_RESUME_TARGET} so the stable queued "
            "proposal can run with one additional proposal budget slot."
        ),
    }


def _maintenance_cycle_queue_metadata(
    cycles: list[Any],
    queue_snapshot: list[str],
    runnable_proposal_count: int,
) -> dict[str, Any]:
    previous = cycles[-1] if cycles and isinstance(cycles[-1], Mapping) else {}
    previous_snapshot = _list_text(previous.get("queue_snapshot")) if previous else []
    previous_runnable_count = _int_value(previous.get("runnable_proposal_count"), -1)
    queue_changed = not previous or queue_snapshot != previous_snapshot
    runnable_count_changed = previous_runnable_count != runnable_proposal_count
    stable_count = 1
    if previous and not queue_changed:
        stable_count = _int_value(previous.get("stable_queue_snapshot_count"), 1) + 1
    meaningful_reasons: list[str] = []
    if not previous:
        meaningful_reasons.append("post_promote_observation")
    if queue_changed and previous:
        meaningful_reasons.append("queue_snapshot_changed")
    if runnable_count_changed and previous:
        meaningful_reasons.append("runnable_proposal_count_changed")
    meaningful = bool(meaningful_reasons)
    return {
        "queue_snapshot_changed": queue_changed,
        "stable_queue_snapshot_count": stable_count,
        "meaningful": meaningful,
        "meaningful_reasons": meaningful_reasons,
        "queue_action": _maintenance_queue_action(queue_snapshot),
    }
