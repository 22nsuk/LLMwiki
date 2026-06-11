from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .auto_improve_error_runtime import AutoImproveUsageError
from .auto_improve_queue_runtime import (
    is_recent_log_overlap_queue_unblock,
    select_next_proposal,
)

DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES = 1
MAINTENANCE_ACTION_RESUME_TARGET = "auto-improve-goal-maintenance-action"
MAINTENANCE_ACTION_RUNNER_ACTION = "resume_session_with_additional_proposal_budget"
STABLE_MAINTENANCE_QUEUE_THRESHOLD = 2


@dataclass(frozen=True)
class MaintenanceRunEligibility:
    should_run: bool
    reason: str
    interval_seconds: int = 300
    max_cycles: int | None = None
    stop_reason: str | None = None
    post_promote_cycles: int = DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES


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


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _resolve_maintenance_interval(value: int | None) -> int:
    resolved = 300 if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 1:
        raise AutoImproveUsageError(
            "maintenance_interval_seconds must be an integer greater than or equal to 1"
        )
    return resolved


def _resolve_post_promote_maintenance_cycles(value: int | None) -> int:
    resolved = DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 0:
        raise AutoImproveUsageError(
            "post_promote_maintenance_cycles must be an integer greater than or equal to 0"
        )
    return resolved


def _last_iteration_outcome(session: Mapping[str, Any]) -> str:
    iterations = session.get("iterations", [])
    if not isinstance(iterations, list):
        return ""
    for iteration in reversed(iterations):
        if not isinstance(iteration, Mapping):
            continue
        return str(iteration.get("outcome", "")).strip()
    return ""


def _maintenance_cycle_count(session: Mapping[str, Any]) -> int:
    maintenance = _mapping_value(session, "maintenance")
    return _int_value(maintenance.get("cycle_count"))


def _maintenance_run_eligibility(
    *,
    maintain_until_budget: bool,
    post_promote_maintenance_cycles: int | None,
    maintenance_interval_seconds: int | None,
    new_iteration_count: int,
    stop_reason: str | None,
    last_iteration_outcome: str,
    elapsed_seconds: int,
    target_elapsed_seconds: int,
) -> MaintenanceRunEligibility:
    post_promote_cycles = _resolve_post_promote_maintenance_cycles(
        post_promote_maintenance_cycles
    )
    if not maintain_until_budget and post_promote_cycles == 0:
        return MaintenanceRunEligibility(
            should_run=False,
            reason="post_promote_maintenance_disabled",
            post_promote_cycles=post_promote_cycles,
        )
    if (
        not maintain_until_budget
        and post_promote_maintenance_cycles is None
        and new_iteration_count <= 0
    ):
        return MaintenanceRunEligibility(
            should_run=False,
            reason="default_post_promote_without_new_iteration",
            post_promote_cycles=post_promote_cycles,
        )
    if stop_reason != "proposal_budget_exhausted":
        return MaintenanceRunEligibility(
            should_run=False,
            reason="stop_reason_not_proposal_budget_exhausted",
            post_promote_cycles=post_promote_cycles,
        )
    if last_iteration_outcome != "promoted":
        return MaintenanceRunEligibility(
            should_run=False,
            reason="last_iteration_not_promoted",
            post_promote_cycles=post_promote_cycles,
        )
    if elapsed_seconds >= target_elapsed_seconds:
        return MaintenanceRunEligibility(
            should_run=False,
            reason="time_budget_already_exhausted",
            stop_reason="time_budget_exhausted",
            post_promote_cycles=post_promote_cycles,
        )
    return MaintenanceRunEligibility(
        should_run=True,
        reason="eligible",
        interval_seconds=_resolve_maintenance_interval(maintenance_interval_seconds),
        max_cycles=None if maintain_until_budget else post_promote_cycles,
        post_promote_cycles=post_promote_cycles,
    )


def _proposal_repairs_repeat_backlog(proposal: Mapping[str, Any] | None) -> bool:
    if not isinstance(proposal, Mapping):
        return False
    if _list_text(proposal.get("blocked_by")):
        return False
    proposal_id = str(proposal.get("proposal_id", "")).strip()
    family = str(proposal.get("family", "")).strip()
    failure_mode = str(proposal.get("failure_mode", "")).strip()
    return (
        family == "next_run_failure_repair"
        or failure_mode == "next_run_failure_repair"
        or proposal_id.startswith("next_run_failure_repair__")
    )


def _proposal_refreshes_stale_maintenance_queue(proposal: Mapping[str, Any] | None) -> bool:
    if not isinstance(proposal, Mapping):
        return False
    if _list_text(proposal.get("blocked_by")):
        return False
    return _proposal_repairs_repeat_backlog(proposal) or is_recent_log_overlap_queue_unblock(
        dict(proposal)
    )


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


def _initial_maintenance_payload(
    *,
    started_at: str,
    target_elapsed_seconds: int,
    start_elapsed_seconds: int,
    interval_seconds: int,
    max_cycles: int | None,
) -> dict[str, Any]:
    if max_cycles is None:
        expected_min_cycle_count = _expected_maintenance_cycle_count(
            start_elapsed_seconds=start_elapsed_seconds,
            target_elapsed_seconds=target_elapsed_seconds,
            interval_seconds=interval_seconds,
        )
        completion_condition = "time_budget"
    else:
        expected_min_cycle_count = max_cycles
        completion_condition = "post_promote_cycle_limit"
    return {
        "mode": "proposal_budget_runtime_maintenance",
        "status": "running",
        "started_at": started_at,
        "completed_at": "",
        "target_elapsed_seconds": target_elapsed_seconds,
        "target_cycle_count": expected_min_cycle_count,
        "completion_condition": completion_condition,
        "started_elapsed_seconds": start_elapsed_seconds,
        "interval_seconds": interval_seconds,
        "expected_min_cycle_count": expected_min_cycle_count,
        "cycle_count": 0,
        "meaningful_cycle_count": 0,
        "stable_queue_snapshot_count": 0,
        "stable_queue_snapshot": [],
        "queue_action": {
            "status": "none",
            "reason": "",
            "proposal_ids": [],
            "recommended_next_step": "",
        },
        "last_cycle_elapsed_seconds": 0,
        "stop_reason": "running",
        "cycles": [],
    }


def _maintenance_terminal_completion_condition(
    session: Mapping[str, Any],
    *,
    default_completion_condition: str,
    max_cycles: int | None,
    elapsed_seconds: int,
    target_elapsed_seconds: int,
) -> str | None:
    maintenance = _mapping_value(session, "maintenance")
    stable_count = _int_value(maintenance.get("stable_queue_snapshot_count"))
    stable_snapshot = _list_text(maintenance.get("stable_queue_snapshot"))
    if stable_snapshot and stable_count >= STABLE_MAINTENANCE_QUEUE_THRESHOLD:
        return "stable_queue_snapshot"
    if max_cycles is not None and _maintenance_cycle_count(session) >= max_cycles:
        return default_completion_condition
    if elapsed_seconds >= target_elapsed_seconds:
        return default_completion_condition
    return None


def _maintenance_completion_stop_reason(completion_condition: str) -> str:
    if completion_condition == "stable_queue_snapshot":
        return "stable_queue_snapshot"
    if completion_condition == "post_promote_cycle_limit":
        return "post_promote_cycle_limit_reached"
    return "time_budget_reached"


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


def _maintenance_action_queue_payload(maintenance: Mapping[str, Any]) -> dict[str, Any]:
    queue_action = _mapping_value(maintenance, "queue_action")
    queue_action_payload: dict[str, Any] = {
        "status": "none",
        "reason": "",
        "proposal_ids": [],
        "runner_action": "none",
        "proposal_budget_increment": 0,
        "resume_target": "",
        "recommended_next_step": "",
    }
    queue_action_payload.update(dict(queue_action))
    if not isinstance(queue_action_payload.get("proposal_ids"), list):
        queue_action_payload["proposal_ids"] = []
    return queue_action_payload


def _maintenance_action_base_plan(
    *,
    session_id: str,
    current_budget: int,
    current_iterations: int,
    queue_action_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_kind": "goal_runtime_maintenance_action_plan",
        "producer": "ops.scripts.auto_improve_runtime",
        "session_id": session_id,
        "status": "attention",
        "current_max_proposals": current_budget,
        "current_iteration_count": current_iterations,
        "next_max_proposals": current_budget,
        "queue_action": queue_action_payload,
        "selected_proposal": {
            "proposal_id": "",
            "family": "",
            "failure_mode": "",
        },
        "blockers": [],
        "recommended_next_action": "",
        "decisions": {
            "can_resume": False,
            "requires_budget_increment": False,
        },
    }


def _block_maintenance_action_plan(
    base_plan: dict[str, Any],
    *,
    blocker: str,
    recommended_next_action: str,
) -> dict[str, Any]:
    base_plan["blockers"] = [blocker]
    base_plan["recommended_next_action"] = recommended_next_action
    return base_plan


def _selected_maintenance_proposal(
    session: Mapping[str, Any],
    proposals: list[Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    return select_next_proposal(
        {"proposals": proposals},
        attempted=set(_list_text(session.get("attempted_proposal_ids"))),
        quarantined=set(_list_text(session.get("quarantined_proposal_ids"))),
    )


def _refresh_stale_queue_action(
    *,
    selected: Mapping[str, Any],
    selected_proposal_id: str,
    actionable_queue: list[str],
    increment: int,
) -> dict[str, Any] | None:
    if (
        selected_proposal_id in actionable_queue
        and _proposal_refreshes_stale_maintenance_queue(selected)
    ):
        queue_action_payload = _maintenance_queue_action(actionable_queue)
        queue_action_payload["proposal_budget_increment"] = increment
        return queue_action_payload
    return None


def _complete_maintenance_action_plan(
    base_plan: dict[str, Any],
    *,
    selected: Mapping[str, Any],
    selected_proposal_id: str,
    current_budget: int,
    current_iterations: int,
    increment: int,
    actionable_queue: list[str],
) -> dict[str, Any]:
    next_budget = max(current_budget + increment, current_iterations + 1)
    base_plan.update(
        {
            "status": "pass",
            "next_max_proposals": next_budget,
            "selected_proposal": {
                "proposal_id": selected_proposal_id,
                "family": str(selected.get("family", "")).strip(),
                "failure_mode": str(selected.get("failure_mode", "")).strip(),
            },
            "recommended_next_action": (
                f"Run make {MAINTENANCE_ACTION_RESUME_TARGET} with "
                f"GOAL_MAX_PROPOSALS={next_budget}."
            ),
            "decisions": {
                "can_resume": True,
                "requires_budget_increment": next_budget > current_budget,
            },
            "actionable_queue_snapshot": actionable_queue,
        }
    )
    return base_plan


def build_maintenance_action_resume_plan(
    session: Mapping[str, Any],
    *,
    session_id: str,
    mutation_proposals_report_loader: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    maintenance = _mapping_value(session, "maintenance")
    queue_action_payload = _maintenance_action_queue_payload(maintenance)
    current_budget = _int_value(_mapping_value(session, "budget").get("max_proposals"))
    current_iterations = len(session.get("iterations", [])) if isinstance(session.get("iterations"), list) else 0
    base_plan = _maintenance_action_base_plan(
        session_id=session_id,
        current_budget=current_budget,
        current_iterations=current_iterations,
        queue_action_payload=queue_action_payload,
    )
    if str(queue_action_payload.get("status", "")).strip() != "action_required":
        base_plan["status"] = "pass"
        base_plan["recommended_next_action"] = "No maintenance queue action requires a resume."
        return base_plan
    if str(queue_action_payload.get("runner_action", "")).strip() != MAINTENANCE_ACTION_RUNNER_ACTION:
        return _block_maintenance_action_plan(
            base_plan,
            blocker="maintenance queue action has no executable runner action",
            recommended_next_action=(
                "Refresh maintenance evidence, then rerun maintenance action planning."
            ),
        )
    increment = _int_value(queue_action_payload.get("proposal_budget_increment"))
    if increment < 1:
        return _block_maintenance_action_plan(
            base_plan,
            blocker="maintenance queue action has invalid proposal budget increment",
            recommended_next_action=(
                "Refresh maintenance evidence so queue_action.proposal_budget_increment "
                "declares the explicit resume budget increase."
            ),
        )
    proposals = mutation_proposals_report_loader().get("proposals")
    if not isinstance(proposals, list):
        return _block_maintenance_action_plan(
            base_plan,
            blocker="mutation proposal report is missing or invalid",
            recommended_next_action=(
                "Run make mutation-proposal or make goal-runtime-between-run-settle, "
                "then rerun the maintenance action."
            ),
        )
    selected, actionable_queue = _selected_maintenance_proposal(session, proposals)
    action_proposal_ids = set(_list_text(queue_action_payload.get("proposal_ids")))
    if not selected:
        return _block_maintenance_action_plan(
            base_plan,
            blocker="no unattempted runnable proposal is available",
            recommended_next_action=(
                "Refresh mutation proposals and readiness. If the queue remains blocked, "
                "the maintenance action cannot complete by adding proposal budget alone."
            ),
        )
    selected_proposal_id = str(selected.get("proposal_id", "")).strip()
    if action_proposal_ids and selected_proposal_id not in action_proposal_ids:
        refreshed_queue_action = _refresh_stale_queue_action(
            selected=selected,
            selected_proposal_id=selected_proposal_id,
            actionable_queue=actionable_queue,
            increment=increment,
        )
        if refreshed_queue_action is None:
            return _block_maintenance_action_plan(
                base_plan,
                blocker="selected proposal is not in the maintenance action queue",
                recommended_next_action=(
                    "Run make goal-runtime-between-run-settle so readiness and mutation proposal "
                    "queue evidence converge, then rerun the maintenance action."
                ),
            )
        queue_action_payload = refreshed_queue_action
        base_plan["queue_action"] = queue_action_payload
    return _complete_maintenance_action_plan(
        base_plan,
        selected=selected,
        selected_proposal_id=selected_proposal_id,
        current_budget=current_budget,
        current_iterations=current_iterations,
        increment=increment,
        actionable_queue=actionable_queue,
    )
