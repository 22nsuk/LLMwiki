from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object
from ops.scripts.runtime_context import RuntimeContext

from .auto_improve_queue_runtime import select_next_proposal

REPEATED_BLOCKER_THRESHOLD = 2
GENERIC_BLOCKING_REASONS = frozenset({"discarded"})
REMEDIATION_BACKLOG_REPORT = "ops/reports/remediation-backlog.json"
REPEAT_BACKLOG_ITEM_TYPES = frozenset(
    {
        "repeated_auto_improve_blocker",
        "repeated_negative_lesson",
    }
)
TERMINAL_SUCCESS_OUTCOMES = frozenset({"promoted"})


@dataclass
class AutoImproveLoopState:
    attempted: set[str]
    quarantined: set[str]
    consecutive_failures: int
    stop_reason: str
    start_monotonic: float
    pre_promotion_failure_outcomes: set[str]
    repeat_backlog_repair_active: bool = False


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


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _is_open_repeat_backlog_item(item: Mapping[str, Any]) -> bool:
    status = str(item.get("status", "")).strip().lower()
    if status != "open":
        return False
    severity = str(item.get("severity", "")).strip()
    item_type = str(item.get("item_type", "")).strip()
    return severity == "blocks_repeat" or item_type in REPEAT_BACKLOG_ITEM_TYPES


def _open_repeat_backlog_items(vault: Path) -> list[dict[str, Any]]:
    report = load_optional_json_object(vault / REMEDIATION_BACKLOG_REPORT)
    items = [
        item
        for item in _dict_items(report.get("items"))
        if _is_open_repeat_backlog_item(item)
    ]
    return sorted(
        items,
        key=lambda item: (
            str(item.get("item_id", "")).strip(),
            str(item.get("blocker_id", "")).strip(),
        ),
    )


def _open_repeat_backlog_blocker_reason(vault: Path) -> str:
    for item in _open_repeat_backlog_items(vault):
        for key in ("blocker_id", "item_id", "item_type"):
            reason = str(item.get(key, "")).strip()
            if reason:
                return reason
    return ""


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


def _record_pre_run_selected_proposal_metadata(
    session: dict,
    proposals_report: Mapping[str, Any],
) -> bool:
    proposal, _queue_snapshot = select_next_proposal(
        dict(proposals_report),
        attempted=set(_list_text(session.get("attempted_proposal_ids"))),
        quarantined=set(_list_text(session.get("quarantined_proposal_ids"))),
    )
    metadata = dict(_mapping_value(session, "metadata"))
    metadata["pre_run_selected_proposal"] = {
        "proposal_id": str(proposal.get("proposal_id", "")).strip() if proposal else "",
        "family": str(proposal.get("family", "")).strip() if proposal else "",
        "failure_mode": str(proposal.get("failure_mode", "")).strip() if proposal else "",
        "blocked_by": _list_text(proposal.get("blocked_by")) if proposal else [],
        "repeat_backlog_repair": _proposal_repairs_repeat_backlog(proposal),
    }
    session["metadata"] = metadata
    return bool(metadata["pre_run_selected_proposal"]["repeat_backlog_repair"])


def _empty_loop_state(context: RuntimeContext) -> dict:
    return {
        "consecutive_failures": 0,
        "last_outcome": "",
        "last_decision": "",
        "last_run_id": "",
        "last_blocking_reason": "",
        "blocking_reason_counts": {},
        "repeated_blocker_stop": False,
        "repeated_blocker_reason": "",
        "remediation_backlog_path": REMEDIATION_BACKLOG_REPORT,
        "updated_at": context.isoformat_z(),
    }


def _blocking_reason_counts_from_iterations(session: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, Mapping):
            continue
        outcome = str(iteration.get("outcome", "")).strip()
        if not outcome or outcome in TERMINAL_SUCCESS_OUTCOMES:
            continue
        reason = str(iteration.get("failure_taxonomy", "")).strip() or outcome
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _normalize_blocking_reason_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, int] = {}
    for key, count in value.items():
        reason = str(key).strip()
        if not reason:
            continue
        normalized[reason] = max(0, _int_value(count, 0))
    return normalized


def _should_prefer_reconstructed_blocking_counts(
    existing_counts: Mapping[str, int],
    reconstructed_counts: Mapping[str, int],
) -> bool:
    return bool(reconstructed_counts) and any(
        reason in GENERIC_BLOCKING_REASONS for reason in existing_counts
    ) and any(reason not in GENERIC_BLOCKING_REASONS for reason in reconstructed_counts)


def _reconstructed_loop_state(session: dict, *, context: RuntimeContext) -> dict:
    state = _empty_loop_state(context)
    consecutive_failures = 0
    blocking_reason_counts: dict[str, int] = {}
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        outcome = str(iteration.get("outcome", "")).strip()
        if outcome in TERMINAL_SUCCESS_OUTCOMES:
            consecutive_failures = 0
        elif outcome:
            consecutive_failures += 1
            reason = str(iteration.get("failure_taxonomy", "")).strip() or outcome
            blocking_reason_counts[reason] = blocking_reason_counts.get(reason, 0) + 1
        else:
            reason = ""
        state = {
            "consecutive_failures": consecutive_failures,
            "last_outcome": outcome,
            "last_decision": str(iteration.get("decision", "")).strip(),
            "last_run_id": str(iteration.get("run_id", "")).strip(),
            "last_blocking_reason": "" if outcome in TERMINAL_SUCCESS_OUTCOMES else reason,
            "blocking_reason_counts": dict(blocking_reason_counts),
            "repeated_blocker_stop": False,
            "repeated_blocker_reason": "",
            "remediation_backlog_path": REMEDIATION_BACKLOG_REPORT,
            "updated_at": context.isoformat_z(),
        }
    return state


def _normalize_loop_state(session: dict, *, context: RuntimeContext) -> dict:
    existing = session.get("loop_state")
    if not isinstance(existing, dict):
        return _reconstructed_loop_state(session, context=context)
    reconstructed_state = _reconstructed_loop_state(session, context=context)
    reconstructed_counts = _normalize_blocking_reason_counts(
        reconstructed_state.get("blocking_reason_counts")
    )
    existing_counts = _normalize_blocking_reason_counts(existing.get("blocking_reason_counts"))
    if _should_prefer_reconstructed_blocking_counts(existing_counts, reconstructed_counts):
        blocking_reason_counts = reconstructed_counts
        last_blocking_reason = str(reconstructed_state.get("last_blocking_reason", "")).strip()
    else:
        blocking_reason_counts = existing_counts or reconstructed_counts
        last_blocking_reason = str(existing.get("last_blocking_reason", "")).strip()
    repeated_blocker_reason = str(existing.get("repeated_blocker_reason", "")).strip()
    if (
        repeated_blocker_reason in GENERIC_BLOCKING_REASONS
        and last_blocking_reason
        and last_blocking_reason not in GENERIC_BLOCKING_REASONS
    ):
        repeated_blocker_reason = last_blocking_reason
    normalized = _empty_loop_state(context)
    normalized.update(
        {
            "consecutive_failures": max(
                0,
                _int_value(existing.get("consecutive_failures"), 0),
            ),
            "last_outcome": str(existing.get("last_outcome", "")).strip(),
            "last_decision": str(existing.get("last_decision", "")).strip(),
            "last_run_id": str(existing.get("last_run_id", "")).strip(),
            "last_blocking_reason": last_blocking_reason,
            "blocking_reason_counts": blocking_reason_counts,
            "repeated_blocker_stop": bool(existing.get("repeated_blocker_stop", False)),
            "repeated_blocker_reason": repeated_blocker_reason,
            "remediation_backlog_path": str(
                existing.get("remediation_backlog_path", REMEDIATION_BACKLOG_REPORT)
            ).strip()
            or REMEDIATION_BACKLOG_REPORT,
            "updated_at": str(existing.get("updated_at", "")).strip() or context.isoformat_z(),
        }
    )
    return normalized


def _ensure_session_loop_state(session: dict, *, context: RuntimeContext) -> dict:
    session["loop_state"] = _normalize_loop_state(session, context=context)
    return session["loop_state"]


def _initial_auto_improve_loop_state(
    auto_policy: dict,
    session: dict,
    *,
    monotonic: Callable[[], float] | None = None,
) -> AutoImproveLoopState:
    monotonic_clock = monotonic or time.monotonic
    return AutoImproveLoopState(
        attempted=set(session["attempted_proposal_ids"]),
        quarantined=set(session["quarantined_proposal_ids"]),
        consecutive_failures=max(
            0,
            _int_value(session.get("loop_state", {}).get("consecutive_failures"), 0),
        ),
        stop_reason="queue_exhausted",
        start_monotonic=monotonic_clock(),
        pre_promotion_failure_outcomes=set(
            auto_policy["quarantine"]["pre_promotion_failure_outcomes"]
        ),
    )


def _repeated_blocker_reason(session: Mapping[str, Any]) -> str:
    loop_state = _mapping_value(session, "loop_state")
    counts = _normalize_blocking_reason_counts(loop_state.get("blocking_reason_counts"))
    if not counts:
        counts = _blocking_reason_counts_from_iterations(session)
    for reason, count in sorted(counts.items()):
        if count >= REPEATED_BLOCKER_THRESHOLD:
            return reason
    return ""


def _mark_repeated_blocker_stop(
    session: dict,
    reason: str,
    *,
    context: RuntimeContext,
) -> None:
    loop_state = _ensure_session_loop_state(session, context=context)
    counts = _normalize_blocking_reason_counts(loop_state.get("blocking_reason_counts"))
    counts[reason] = max(counts.get(reason, 0), REPEATED_BLOCKER_THRESHOLD)
    loop_state["blocking_reason_counts"] = counts
    loop_state["repeated_blocker_stop"] = True
    loop_state["repeated_blocker_reason"] = reason
    loop_state["remediation_backlog_path"] = REMEDIATION_BACKLOG_REPORT


def _stop_reason_before_iteration(
    vault: Path,
    session: dict,
    state: AutoImproveLoopState,
    *,
    context: RuntimeContext,
    check_open_repeat_backlog: bool = True,
    monotonic: Callable[[], float] | None = None,
) -> str | None:
    repeated_blocker_reason = _repeated_blocker_reason(session)
    if repeated_blocker_reason:
        _mark_repeated_blocker_stop(session, repeated_blocker_reason, context=context)
        return "repeated_blocker_backlog_required"
    open_backlog_reason = (
        _open_repeat_backlog_blocker_reason(vault)
        if check_open_repeat_backlog and not state.repeat_backlog_repair_active
        else ""
    )
    if open_backlog_reason:
        _mark_repeated_blocker_stop(session, open_backlog_reason, context=context)
        return "repeated_blocker_backlog_required"
    if len(session.get("iterations", [])) >= session["budget"]["max_proposals"]:
        return "proposal_budget_exhausted"
    monotonic_clock = monotonic or time.monotonic
    if monotonic_clock() - state.start_monotonic > session["budget"]["max_minutes"] * 60:
        return "time_budget_exhausted"
    if state.consecutive_failures >= session["budget"]["max_consecutive_failures"]:
        return "failure_budget_exhausted"
    return None


def _stop_reason_after_loop(
    vault: Path,
    session: dict,
    state: AutoImproveLoopState,
    *,
    context: RuntimeContext,
) -> str:
    repeated_blocker_reason = _repeated_blocker_reason(session)
    if repeated_blocker_reason:
        _mark_repeated_blocker_stop(session, repeated_blocker_reason, context=context)
        return "repeated_blocker_backlog_required"
    open_backlog_reason = (
        ""
        if state.repeat_backlog_repair_active
        else _open_repeat_backlog_blocker_reason(vault)
    )
    if open_backlog_reason:
        _mark_repeated_blocker_stop(session, open_backlog_reason, context=context)
        return "repeated_blocker_backlog_required"
    if (
        state.stop_reason == "queue_exhausted"
        and len(session.get("iterations", [])) >= session["budget"]["max_proposals"]
    ):
        return "proposal_budget_exhausted"
    return state.stop_reason
