from __future__ import annotations

import copy
import time
from pathlib import Path
from threading import Event
from typing import Any

from ops.scripts.artifact_io_runtime import read_json_object
from ops.scripts.codex_goal_client import GoalBackend, require_persistent_goal_backend
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_or_raise

from .auto_improve_runtime import run_auto_improve_session
from .goal_run_status import (
    GOAL_CONTRACT_SCHEMA,
    GOAL_RUN_STATUS_SCHEMA,
    _build_status_from_contract,
    _ensure_execution_identity,
    _heartbeat_status,
    _worktree_guard_summary,
    resolve_execution_profile,
    write_checkpoint,
    write_goal_status,
)
from .goal_runtime_backoff import (
    active_executor_backoff_from_status as _active_executor_backoff_from_status,
    executor_backoff_wait_seconds as _executor_backoff_wait_seconds,
    usage_limit_backoff_from_result as _usage_limit_backoff_from_result,
)
from .goal_runtime_ladder import (
    PENDING_CHECKPOINT,
    build_profile_verification,
    mark_profile_result,
    mark_profile_running,
    profile_prerequisite_blocker,
)
from .goal_runtime_maintenance import (
    run_periodic_refresh_command as _run_periodic_refresh_command,
    start_maintenance_thread as _start_maintenance_thread,
)
from .goal_runtime_request import (
    AutoImproveRunner,
    GoalAutoImproveRequest,
    auto_improve_command as _auto_improve_command,
    context_from_request as _context,
)


def _load_goal_contract(vault: Path, rel_path: str) -> dict[str, Any]:
    backend = require_persistent_goal_backend(
        vault=vault,
        goal_contract_path=rel_path,
    )
    return _load_goal_contract_from_backend(vault, backend)


def _load_goal_contract_from_backend(vault: Path, backend: GoalBackend) -> dict[str, Any]:
    persistent_backend = require_persistent_goal_backend(backend)
    contract = persistent_backend.get_goal()
    validate_or_raise(
        contract,
        load_schema(vault / GOAL_CONTRACT_SCHEMA),
        context="codex goal contract schema validation failed",
    )
    return contract


def _with_artifact_overrides(
    contract: dict[str, Any],
    *,
    status_out: str,
    audit_jsonl: str,
    heartbeat_interval_minutes: int,
    checkpoint_interval_minutes: int,
) -> dict[str, Any]:
    updated = copy.deepcopy(contract)
    updated["artifacts"]["status_json"] = status_out
    updated["artifacts"]["audit_log"] = audit_jsonl
    updated["budgets"]["heartbeat_interval_minutes"] = heartbeat_interval_minutes
    updated["budgets"]["checkpoint_interval_minutes"] = checkpoint_interval_minutes
    return updated


def _validate_goal_runtime_preflight(vault: Path, contract: dict[str, Any]) -> dict[str, Any]:
    if contract["github"]["visibility"] != "PRIVATE":
        raise ValueError("goal auto-improve runs require PRIVATE GitHub visibility")
    guard = _worktree_guard_summary(vault, contract)
    if (
        guard["status"] != "pass"
        or guard["mode"] != "git_worktree"
        or guard["long_run_allowed"] is not True
    ):
        reason = guard.get("blocked_operation_reason") or guard.get("reason")
        raise ValueError(f"goal auto-improve runs require a Git worktree: {reason}")
    return guard


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _apply_request_execution_identity(
    status: dict[str, Any],
    request: GoalAutoImproveRequest,
) -> dict[str, Any]:
    _ensure_execution_identity(status)
    execution = status["execution"]
    requested_session_id = str(request.session_id or "").strip()
    resume_session = str(request.resume_session or "").strip()
    execution["requested_session_id"] = requested_session_id
    execution["resume_session"] = resume_session
    if requested_session_id:
        execution["current_session_id"] = requested_session_id
    elif resume_session:
        execution["current_session_id"] = resume_session
    return status


def _apply_result_execution_identity(
    status: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    _ensure_execution_identity(status)
    execution = status["execution"]
    session_id = str(result.get("session_id", "")).strip()
    if session_id:
        execution["current_session_id"] = session_id
    execution["session_report"] = str(result.get("session_report", "")).strip()
    execution["run_ids"] = _string_list(result.get("run_ids"))
    return status


def _new_or_resumed_status(
    vault: Path,
    contract: dict[str, Any],
    *,
    profile_name: str,
    profile: dict[str, int | str],
    request: GoalAutoImproveRequest,
    context: RuntimeContext,
) -> dict[str, Any]:
    existing_status: dict[str, Any] | None = None
    if request.resume_from_checkpoint:
        status = read_json_object(vault / request.resume_from_checkpoint)
        existing_status = status
        _ensure_execution_identity(status)
        validate_or_raise(
            status,
            load_schema(vault / GOAL_RUN_STATUS_SCHEMA),
            context="goal run checkpoint schema validation failed",
        )
        if status["goal_id"] != contract["goal_id"]:
            raise ValueError("resume checkpoint goal_id does not match goal contract")
        status["generated_at"] = context.isoformat_z()
        status["status"] = "running"
        status["active_profile"] = profile_name
        status["repo"] = {
            **contract["github"],
            "worktree_guard": _worktree_guard_summary(vault, contract),
        }
        status["heartbeat"] = _heartbeat_status(contract, context)
        status["artifacts"] = contract["artifacts"]
        status["stop_conditions"] = list(contract["stop_conditions"])
        status["last_event"] = {
            "at": context.isoformat_z(),
            "event": "goal_run_resume",
            "reason": request.resume_from_checkpoint,
        }
    else:
        existing_status = _existing_goal_status(vault, request.status_out, contract["goal_id"])
        status = _build_status_from_contract(
            vault,
            contract,
            context=context,
            active_profile=profile_name,
            status="running",
            last_event="goal_run_start",
            reason="auto-improve goal profile started",
        )
    status["profile_verification"] = build_profile_verification(
        contract,
        active_profile=profile_name,
        existing_status=existing_status,
    )
    mark_profile_running(
        status["profile_verification"],
        active_profile=profile_name,
        started_at=context.isoformat_z(),
    )
    _apply_request_execution_identity(status, request)
    status["budget"] = {
        "max_minutes": int(profile["max_minutes"]),
        "max_proposals": int(profile["max_proposals"]),
        "max_consecutive_failures": int(profile["max_consecutive_failures"]),
    }
    active_backoff = _active_executor_backoff_from_status(vault, request.status_out, context)
    if active_backoff is not None:
        status["executor_backoff"] = active_backoff
    return status


def _existing_goal_status(vault: Path, status_path: str, goal_id: str) -> dict[str, Any] | None:
    path = vault / status_path
    if not path.is_file():
        return None
    try:
        status = read_json_object(path)
    except (OSError, ValueError, TypeError):
        return None
    if status.get("goal_id") != goal_id:
        return None
    return status


def _read_session_progress(vault: Path, result: dict[str, Any]) -> dict[str, Any]:
    progress = {
        "iterations_completed": int(result.get("iterations", 0) or 0),
        "proposals_attempted": int(result.get("iterations", 0) or 0),
        "consecutive_failures": 0,
    }
    session_report = str(result.get("session_report", "")).strip()
    if not session_report:
        return progress
    session_path = vault / session_report
    if not session_path.is_file():
        return progress
    session = read_json_object(session_path)
    iterations = session.get("iterations")
    if isinstance(iterations, list):
        progress["iterations_completed"] = len(iterations)
    attempted = session.get("attempted_proposal_ids")
    if isinstance(attempted, list):
        progress["proposals_attempted"] = len(attempted)
    loop_state = session.get("loop_state")
    if isinstance(loop_state, dict):
        progress["consecutive_failures"] = int(loop_state.get("consecutive_failures", 0) or 0)
    return progress


def _final_status_for_stop_reason(stop_reason: str) -> str:
    if stop_reason in {
        "failure_budget_exhausted",
        "learning_review_required",
        "executor_usage_limited",
    }:
        return "blocked"
    return "running"


def _blocking_stop_reason(stop_reason: str) -> bool:
    return stop_reason in {"failure_budget_exhausted", "learning_review_required"}


def _profile_result_evidence_status(
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
    *,
    stop_reason: str,
) -> tuple[str, str]:
    if stop_reason in {
        "failure_budget_exhausted",
        "learning_review_required",
        "executor_usage_limited",
        "periodic_maintenance_failure",
    }:
        return "blocked", f"profile stopped on blocker: {stop_reason}"
    if stop_reason != "sustained_budget_elapsed":
        return (
            "incomplete",
            f"profile stopped before full-duration sustain evidence: {stop_reason}",
        )
    required_seconds = int(profile["max_minutes"]) * 60
    if request.sustain_budget_seconds is None:
        return (
            "verified",
            "profile sustained until the configured max_minutes budget elapsed",
        )
    observed_seconds = float(request.sustain_budget_seconds)
    if observed_seconds >= required_seconds:
        return (
            "verified",
            "profile sustained until an override budget at least as long as max_minutes elapsed",
        )
    return (
        "sampled",
        (
            f"profile used sustain_budget_seconds={observed_seconds:g}; "
            f"full verification requires {required_seconds} seconds"
        ),
    )


def _sustain_budget_seconds(
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
) -> float:
    if request.sustain_budget_seconds is not None:
        resolved = float(request.sustain_budget_seconds)
        if resolved < 0:
            raise ValueError("sustain_budget_seconds must be >= 0")
        return resolved
    return float(int(profile["max_minutes"]) * 60)


def _write_sustain_wait_status(
    vault: Path,
    status: dict[str, Any],
    *,
    result: dict[str, Any],
    started: float,
    profile_name: str,
    context: RuntimeContext,
) -> None:
    status["generated_at"] = context.isoformat_z()
    _apply_result_execution_identity(status, result)
    progress = _read_session_progress(vault, result)
    progress["elapsed_minutes"] = round((time.monotonic() - started) / 60, 4)
    status["progress"] = progress
    status["last_event"] = {
        "at": context.isoformat_z(),
        "event": "goal_run_sustain_wait",
        "reason": f"profile={profile_name}; auto-improve loop ended before time budget; sustaining heartbeat/checkpoint until budget elapses",
    }
    write_goal_status(
        vault,
        status,
        event="goal_run_sustain_wait",
        reason=f"profile={profile_name}; sustaining heartbeat/checkpoint until budget elapses",
    )


def _write_executor_backoff_status(
    vault: Path,
    status: dict[str, Any],
    *,
    result: dict[str, Any],
    started: float,
    profile_name: str,
    context: RuntimeContext,
    backoff: dict[str, Any],
) -> None:
    status["generated_at"] = context.isoformat_z()
    _apply_result_execution_identity(status, result)
    progress = _read_session_progress(vault, result)
    progress["elapsed_minutes"] = round((time.monotonic() - started) / 60, 4)
    status["progress"] = progress
    status["executor_backoff"] = backoff
    retry_after = str(backoff.get("retry_after", "")).strip() or "unknown"
    retry_after_utc = str(backoff.get("retry_after_utc", "")).strip() or "unknown"
    reason = (
        f"profile={profile_name}; executor_usage_limited_backoff; "
        f"retry_after={retry_after}; retry_after_utc={retry_after_utc}"
    )
    status["last_event"] = {
        "at": context.isoformat_z(),
        "event": "goal_run_executor_backoff",
        "reason": reason,
    }
    write_goal_status(vault, status, event="goal_run_executor_backoff", reason=reason)


def _clear_executor_backoff_status(
    vault: Path,
    status: dict[str, Any],
    *,
    profile_name: str,
    context: RuntimeContext,
) -> None:
    status.pop("executor_backoff", None)
    status["generated_at"] = context.isoformat_z()
    reason = f"profile={profile_name}; executor_usage_limited_backoff retry_after reached"
    status["last_event"] = {
        "at": context.isoformat_z(),
        "event": "goal_run_executor_backoff_retry_due",
        "reason": reason,
    }
    write_goal_status(vault, status, event="goal_run_executor_backoff_retry_due", reason=reason)


def _empty_executor_backoff_result() -> dict[str, Any]:
    return {
        "session_id": "",
        "session_report": "",
        "iterations": 0,
        "stop_reason": "executor_usage_limited",
        "run_ids": [],
    }


def _wait_for_executor_backoff(
    *,
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
    started: float,
    stop_event: Event,
    maintenance_errors: list[str],
    backoff: dict[str, Any],
    context: RuntimeContext,
) -> str:
    wait_seconds = _executor_backoff_wait_seconds(backoff, context)
    if wait_seconds is None:
        return _sustain_until_budget_elapsed(
            request=request,
            profile=profile,
            started=started,
            stop_event=stop_event,
            maintenance_errors=maintenance_errors,
        )
    if wait_seconds <= 0:
        return "executor_backoff_retry_due"
    budget_seconds = _sustain_budget_seconds(request, profile)
    retry_due_at = time.monotonic() + wait_seconds
    budget_due_at = started + budget_seconds
    while True:
        if maintenance_errors:
            return "periodic_maintenance_failure"
        now = time.monotonic()
        if now >= retry_due_at:
            return "executor_backoff_retry_due"
        if now >= budget_due_at:
            return "sustained_budget_elapsed"
        remaining = min(60.0, retry_due_at - now, budget_due_at - now)
        if stop_event.wait(max(0.0, remaining)):
            if maintenance_errors:
                return "periodic_maintenance_failure"
            return "sustain_wait_interrupted"


def _sustain_until_budget_elapsed(
    *,
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
    started: float,
    stop_event: Event,
    maintenance_errors: list[str],
) -> str:
    budget_seconds = _sustain_budget_seconds(request, profile)
    while True:
        if maintenance_errors:
            return "periodic_maintenance_failure"
        elapsed = time.monotonic() - started
        remaining = budget_seconds - elapsed
        if remaining <= 0:
            return "sustained_budget_elapsed"
        if stop_event.wait(min(60.0, remaining)):
            if maintenance_errors:
                return "periodic_maintenance_failure"
            return "sustain_wait_interrupted"


def _merge_periodic_status_updates(
    vault: Path,
    status: dict[str, Any],
    *,
    status_path: str,
) -> dict[str, Any]:
    persisted_path = vault / status_path
    if not persisted_path.is_file():
        return status
    persisted = read_json_object(persisted_path)
    if persisted.get("goal_id") != status.get("goal_id"):
        return status
    if persisted.get("active_profile") != status.get("active_profile"):
        return status
    merged = dict(status)
    merged["checkpoints"] = persisted.get("checkpoints", status.get("checkpoints", []))
    merged["resume"] = persisted.get("resume", status.get("resume", {}))
    merged["heartbeat"] = persisted.get("heartbeat", status.get("heartbeat", {}))
    if isinstance(persisted.get("executor_backoff"), dict):
        merged["executor_backoff"] = persisted["executor_backoff"]
    return merged


def _run_auto_improve_with_optional_sustain(
    *,
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
    runner: AutoImproveRunner,
    started: float,
    status: dict[str, Any],
    profile_name: str,
    stop_event: Event,
    maintenance_errors: list[str],
    context: RuntimeContext,
) -> tuple[dict[str, Any], str]:
    vault = request.vault.resolve()
    result = _empty_executor_backoff_result()
    while True:
        status.update(_merge_periodic_status_updates(vault, status, status_path=request.status_out))
        active_backoff = status.get("executor_backoff")
        if request.sustain_until_budget and isinstance(active_backoff, dict):
            _write_executor_backoff_status(
                vault,
                status,
                result=result,
                started=started,
                profile_name=profile_name,
                context=context,
                backoff=active_backoff,
            )
            backoff_stop = _wait_for_executor_backoff(
                request=request,
                profile=profile,
                started=started,
                stop_event=stop_event,
                maintenance_errors=maintenance_errors,
                backoff=active_backoff,
                context=context,
            )
            if backoff_stop != "executor_backoff_retry_due":
                return result, backoff_stop
            _clear_executor_backoff_status(
                vault,
                status,
                profile_name=profile_name,
                context=context,
            )

        result = runner(
            vault,
            policy_path=request.policy_path,
            session_id=request.session_id,
            resume_session=request.resume_session,
            max_proposals=int(profile["max_proposals"]),
            max_minutes=int(profile["max_minutes"]),
            max_consecutive_failures=int(profile["max_consecutive_failures"]),
            executor_name=request.executor_name,
            artifact_class=request.artifact_class,
            allow_learning_uncertain=request.allow_learning_uncertain,
        )
        stop_reason = str(result.get("stop_reason", "")).strip()
        if not request.sustain_until_budget or _blocking_stop_reason(stop_reason):
            return result, stop_reason

        backoff = _usage_limit_backoff_from_result(vault, result, context)
        if backoff is not None:
            status.update(_merge_periodic_status_updates(vault, status, status_path=request.status_out))
            _write_executor_backoff_status(
                vault,
                status,
                result=result,
                started=started,
                profile_name=profile_name,
                context=context,
                backoff=backoff,
            )
            backoff_stop = _wait_for_executor_backoff(
                request=request,
                profile=profile,
                started=started,
                stop_event=stop_event,
                maintenance_errors=maintenance_errors,
                backoff=backoff,
                context=context,
            )
            if backoff_stop == "executor_backoff_retry_due":
                _clear_executor_backoff_status(
                    vault,
                    status,
                    profile_name=profile_name,
                    context=context,
                )
                continue
            return result, backoff_stop

        status.update(_merge_periodic_status_updates(vault, status, status_path=request.status_out))
        _write_sustain_wait_status(
            vault,
            status,
            result=result,
            started=started,
            profile_name=profile_name,
            context=context,
        )
        return result, _sustain_until_budget_elapsed(
            request=request,
            profile=profile,
            started=started,
            stop_event=stop_event,
            maintenance_errors=maintenance_errors,
        )


def run_goal_bound_auto_improve(
    request: GoalAutoImproveRequest,
    *,
    runner: AutoImproveRunner | None = None,
) -> dict[str, Any]:
    vault = request.vault.resolve()
    context = _context(request)
    goal_backend = require_persistent_goal_backend(
        request.goal_backend,
        vault=vault,
        goal_contract_path=request.goal_contract,
    )
    contract = _load_goal_contract_from_backend(vault, goal_backend)
    profile = resolve_execution_profile(contract, request.goal_profile)
    if request.heartbeat_interval_minutes is not None:
        profile["heartbeat_interval_minutes"] = request.heartbeat_interval_minutes
    if request.checkpoint_interval_minutes is not None:
        profile["checkpoint_interval_minutes"] = request.checkpoint_interval_minutes
    contract = _with_artifact_overrides(
        contract,
        status_out=request.status_out,
        audit_jsonl=request.audit_jsonl,
        heartbeat_interval_minutes=int(profile["heartbeat_interval_minutes"]),
        checkpoint_interval_minutes=int(profile["checkpoint_interval_minutes"]),
    )
    guard = _validate_goal_runtime_preflight(vault, contract)
    profile_name = str(profile["profile"])
    status = _new_or_resumed_status(
        vault,
        contract,
        profile_name=profile_name,
        profile=profile,
        request=request,
        context=context,
    )
    status["repo"]["worktree_guard"] = guard
    prerequisite_blocker = profile_prerequisite_blocker(status["profile_verification"])
    if prerequisite_blocker is not None:
        status["status"] = "blocked"
        status["last_event"] = {
            "at": context.isoformat_z(),
            "event": "goal_run_profile_prerequisite_blocked",
            "reason": prerequisite_blocker,
        }
        mark_profile_result(
            status["profile_verification"],
            active_profile=profile_name,
            status="blocked",
            observed_at=context.isoformat_z(),
            checkpoint=PENDING_CHECKPOINT,
            session_report="",
            stop_reason="profile_prerequisite_blocked",
            detail=prerequisite_blocker,
        )
        status = write_checkpoint(vault, status, reason=prerequisite_blocker)
        write_goal_status(
            vault,
            status,
            event="goal_run_profile_prerequisite_blocked",
            reason=prerequisite_blocker,
        )
        raise ValueError(prerequisite_blocker)
    write_goal_status(
        vault,
        status,
        event="goal_run_start",
        reason=f"auto-improve goal profile started: {profile_name}",
    )
    command = _auto_improve_command(request, profile)
    if request.dry_run:
        status["last_event"] = {
            "at": context.isoformat_z(),
            "event": "goal_run_dry_run",
            "reason": f"profile verification without execution: {profile_name}",
        }
        mark_profile_result(
            status["profile_verification"],
            active_profile=profile_name,
            status="incomplete",
            observed_at=context.isoformat_z(),
            checkpoint=PENDING_CHECKPOINT,
            session_report="",
            stop_reason="dry_run",
            detail="dry-run checks command shape only; it is not full-duration profile evidence",
        )
        status = write_checkpoint(
            vault,
            status,
            reason=f"dry-run profile verification: {profile_name}",
        )
        write_goal_status(
            vault,
            status,
            event="goal_run_dry_run",
            reason=f"profile verification without execution: {profile_name}",
        )
        return {
            "status": "dry_run",
            "goal_profile": profile_name,
            "budget": status["budget"],
            "goal_status": request.status_out,
            "checkpoint": status["resume"]["last_checkpoint"],
            "auto_improve_command": command,
        }

    active_runner = runner or run_auto_improve_session
    stop_event, maintenance_thread, maintenance_errors = _start_maintenance_thread(
        vault,
        request,
        profile,
        refresh_command=_run_periodic_refresh_command,
    )
    started = time.monotonic()
    try:
        result, stop_reason = _run_auto_improve_with_optional_sustain(
            request=request,
            profile=profile,
            runner=active_runner,
            started=started,
            status=status,
            profile_name=profile_name,
            stop_event=stop_event,
            maintenance_errors=maintenance_errors,
            context=context,
        )
    finally:
        stop_event.set()
        if maintenance_thread is not None:
            maintenance_thread.join(timeout=5)

    status = _merge_periodic_status_updates(vault, status, status_path=request.status_out)
    _apply_result_execution_identity(status, result)
    progress = _read_session_progress(vault, result)
    progress["elapsed_minutes"] = round((time.monotonic() - started) / 60, 4)
    status["generated_at"] = context.isoformat_z()
    status["progress"] = progress
    if not request.sustain_until_budget or _blocking_stop_reason(stop_reason):
        stop_reason = str(result.get("stop_reason", "")).strip()
    if maintenance_errors:
        status["status"] = "blocked"
        stop_reason = "periodic_maintenance_failure"
        reason = f"periodic maintenance failure: {maintenance_errors[0]}"
    else:
        status["status"] = _final_status_for_stop_reason(stop_reason)
        reason = (
            f"profile={profile_name}; stop_reason={stop_reason}; "
            f"session_report={result.get('session_report', '')}"
        )
    evidence_status, evidence_detail = _profile_result_evidence_status(
        request,
        profile,
        stop_reason=stop_reason,
    )
    mark_profile_result(
        status["profile_verification"],
        active_profile=profile_name,
        status=evidence_status,
        observed_at=context.isoformat_z(),
        checkpoint=PENDING_CHECKPOINT,
        session_report=str(result.get("session_report", "")).strip(),
        stop_reason=stop_reason,
        detail=evidence_detail,
    )
    status["last_event"] = {
        "at": context.isoformat_z(),
        "event": "goal_run_complete",
        "reason": reason,
    }
    status = write_checkpoint(vault, status, reason=reason)
    write_goal_status(vault, status, event="goal_run_complete", reason=reason)
    return {
        "status": status["status"],
        "goal_profile": profile_name,
        "budget": status["budget"],
        "goal_status": request.status_out,
        "checkpoint": status["resume"]["last_checkpoint"],
        "auto_improve": result,
        "auto_improve_command": command,
    }
