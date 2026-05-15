from __future__ import annotations

import copy
import datetime as dt
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

from ops.scripts.artifact_io_runtime import read_json_object
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_or_raise

from .auto_improve_runtime import run_auto_improve_session
from .goal_run_status import (
    DEFAULT_AUDIT_LOG_PATH,
    DEFAULT_CONTRACT_PATH,
    DEFAULT_STATUS_PATH,
    GOAL_CONTRACT_SCHEMA,
    GOAL_RUN_STATUS_SCHEMA,
    _build_status_from_contract,
    _heartbeat_status,
    _worktree_guard_summary,
    resolve_execution_profile,
    write_checkpoint,
    write_goal_status,
)


AutoImproveRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class GoalAutoImproveRequest:
    vault: Path
    policy_path: str | None
    goal_contract: str = DEFAULT_CONTRACT_PATH
    goal_profile: str = "5-day-sustained"
    status_out: str = DEFAULT_STATUS_PATH
    audit_jsonl: str = DEFAULT_AUDIT_LOG_PATH
    resume_from_checkpoint: str | None = None
    session_id: str | None = None
    resume_session: str | None = None
    executor_name: str = "codex_exec"
    artifact_class: str = "system_mechanism"
    allow_learning_uncertain: bool = False
    heartbeat_interval_minutes: int | None = None
    heartbeat_interval_seconds: float | None = None
    checkpoint_interval_minutes: int | None = None
    checkpoint_interval_seconds: float | None = None
    readiness_interval_seconds: float | None = None
    session_synopsis_interval_seconds: float | None = None
    sustain_until_budget: bool = False
    sustain_budget_seconds: float | None = None
    dry_run: bool = False
    context: RuntimeContext | None = None


def _context(request: GoalAutoImproveRequest) -> RuntimeContext:
    return request.context or RuntimeContext(display_timezone=dt.timezone.utc)


def _load_goal_contract(vault: Path, rel_path: str) -> dict[str, Any]:
    contract = read_json_object(vault / rel_path)
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


def _auto_improve_command(request: GoalAutoImproveRequest, profile: dict[str, int | str]) -> list[str]:
    command = [
        ".venv/bin/python",
        "-m",
        "ops.scripts.mechanism.auto_improve_loop",
        "--vault",
        ".",
        "--policy",
        request.policy_path or "ops/policies/wiki-maintainer-policy.yaml",
        "--goal-contract",
        request.goal_contract,
        "--goal-profile",
        str(profile["profile"]),
        "--status-out",
        request.status_out,
        "--audit-jsonl",
        request.audit_jsonl,
        "--max-proposals",
        str(profile["max_proposals"]),
        "--max-minutes",
        str(profile["max_minutes"]),
        "--max-consecutive-failures",
        str(profile["max_consecutive_failures"]),
        "--executor",
        request.executor_name,
    ]
    if request.resume_from_checkpoint:
        command.extend(["--resume-from-checkpoint", request.resume_from_checkpoint])
    if request.session_id:
        command.extend(["--session-id", request.session_id])
    if request.resume_session:
        command.extend(["--resume-session", request.resume_session])
    if request.allow_learning_uncertain:
        command.append("--allow-learning-uncertain")
    if request.sustain_until_budget:
        command.append("--sustain-until-budget")
    if request.sustain_budget_seconds is not None:
        command.extend(["--sustain-budget-seconds", str(request.sustain_budget_seconds)])
    return command


def _validate_goal_runtime_preflight(vault: Path, contract: dict[str, Any]) -> dict[str, str]:
    if contract["github"]["visibility"] != "PRIVATE":
        raise ValueError("goal auto-improve runs require PRIVATE GitHub visibility")
    guard = _worktree_guard_summary(vault, contract)
    if guard["status"] != "pass" or guard["mode"] != "git_worktree":
        raise ValueError(f"goal auto-improve runs require a Git worktree: {guard['reason']}")
    return guard


def _new_or_resumed_status(
    vault: Path,
    contract: dict[str, Any],
    *,
    profile_name: str,
    profile: dict[str, int | str],
    request: GoalAutoImproveRequest,
    context: RuntimeContext,
) -> dict[str, Any]:
    if request.resume_from_checkpoint:
        status = read_json_object(vault / request.resume_from_checkpoint)
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
        status = _build_status_from_contract(
            vault,
            contract,
            context=context,
            active_profile=profile_name,
            status="running",
            last_event="goal_run_start",
            reason="auto-improve goal profile started",
        )
    status["budget"] = {
        "max_minutes": int(profile["max_minutes"]),
        "max_proposals": int(profile["max_proposals"]),
        "max_consecutive_failures": int(profile["max_consecutive_failures"]),
    }
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


@dataclass(frozen=True)
class GoalMaintenanceSchedule:
    heartbeat_interval_seconds: float | None
    checkpoint_interval_seconds: float | None
    readiness_interval_seconds: float | None
    session_synopsis_interval_seconds: float | None


def _positive_interval_seconds(value: float | int | None) -> float | None:
    if value is None:
        return None
    resolved = float(value)
    if resolved <= 0:
        return None
    return resolved


def _build_maintenance_schedule(
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
) -> GoalMaintenanceSchedule:
    if request.heartbeat_interval_seconds is not None:
        heartbeat_interval = _positive_interval_seconds(request.heartbeat_interval_seconds)
    else:
        heartbeat_interval = _positive_interval_seconds(
            int(request.heartbeat_interval_minutes or profile["heartbeat_interval_minutes"]) * 60
        )
    if request.checkpoint_interval_seconds is not None:
        checkpoint_interval = _positive_interval_seconds(request.checkpoint_interval_seconds)
    else:
        checkpoint_interval = _positive_interval_seconds(
            int(request.checkpoint_interval_minutes or profile["checkpoint_interval_minutes"]) * 60
        )
    readiness_interval = request.readiness_interval_seconds
    if readiness_interval is None:
        readiness_interval = int(profile["readiness_interval_hours"]) * 3600
    session_synopsis_interval = request.session_synopsis_interval_seconds
    if session_synopsis_interval is None:
        session_synopsis_interval = int(profile["session_synopsis_interval_hours"]) * 3600
    return GoalMaintenanceSchedule(
        heartbeat_interval_seconds=heartbeat_interval,
        checkpoint_interval_seconds=checkpoint_interval,
        readiness_interval_seconds=_positive_interval_seconds(readiness_interval),
        session_synopsis_interval_seconds=_positive_interval_seconds(session_synopsis_interval),
    )


def _next_due(now: float, interval: float | None) -> float | None:
    if interval is None:
        return None
    return now + interval


def _wait_seconds(now: float, due_times: list[float | None]) -> float:
    active_due_times = [due for due in due_times if due is not None]
    if not active_due_times:
        return 0
    return max(0.0, min(active_due_times) - now)


def _run_periodic_refresh_command(vault: Path, target: str) -> None:
    completed = subprocess.run(
        ["make", target, f"PYTHON={sys.executable}"],
        cwd=vault,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise RuntimeError(f"{target} failed with exit code {completed.returncode}{suffix}")


def _readiness_continuation_blocker(vault: Path) -> str | None:
    readiness_path = vault / "ops/reports/auto-improve-readiness.json"
    if not readiness_path.is_file():
        return "auto-improve readiness report is missing"
    readiness = read_json_object(readiness_path)
    for blocker_field in (
        "blockers",
        "release_blockers",
        "promotion_blockers",
        "learning_blockers",
    ):
        blockers = readiness.get(blocker_field)
        if blockers:
            return f"auto-improve readiness blockers are present: {blocker_field}"
    if not bool(readiness.get("can_execute_trial", False)):
        return "auto-improve readiness regression: can_execute_trial=false"
    if not bool(readiness.get("can_promote_result", False)):
        return "sealed authority/readiness regression: can_promote_result=false"
    diagnostics = readiness.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return "sealed authority/readiness regression: missing diagnostics"
    preflight = diagnostics.get("release_authority_preflight_summary")
    if not isinstance(preflight, dict):
        return "sealed authority/readiness regression: missing release authority preflight summary"
    if (
        preflight.get("status") != "pass"
        or preflight.get("preflight_status") != "sealed_clean_pass"
        or bool(preflight.get("clean_required_preflight")) is not True
        or bool(preflight.get("expected_blocked_preflight")) is not False
    ):
        return "sealed authority/readiness regression: clean-required sealed pass is not current"
    return None


def _assert_readiness_allows_continuation(vault: Path) -> None:
    blocker = _readiness_continuation_blocker(vault)
    if blocker is not None:
        raise RuntimeError(blocker)


def _read_status_for_periodic_update(
    vault: Path,
    status_path: str,
    context: RuntimeContext,
) -> dict[str, Any]:
    status = read_json_object(vault / status_path)
    status["generated_at"] = context.isoformat_z()
    status["heartbeat"] = _heartbeat_status(
        {
            "budgets": {
                "heartbeat_interval_minutes": status["heartbeat"]["interval_minutes"],
            }
        },
        context,
    )
    return status


def _maintenance_loop(
    vault: Path,
    status_path: str,
    *,
    profile_name: str,
    schedule: GoalMaintenanceSchedule,
    stop_event: Event,
    errors: list[str],
) -> None:
    now = time.monotonic()
    next_heartbeat = _next_due(now, schedule.heartbeat_interval_seconds)
    next_checkpoint = _next_due(now, schedule.checkpoint_interval_seconds)
    next_readiness = _next_due(now, schedule.readiness_interval_seconds)
    next_session_synopsis = _next_due(now, schedule.session_synopsis_interval_seconds)
    if not any(
        due is not None
        for due in (next_heartbeat, next_checkpoint, next_readiness, next_session_synopsis)
    ):
        return
    while True:
        now = time.monotonic()
        wait_seconds = _wait_seconds(
            now,
            [next_heartbeat, next_checkpoint, next_readiness, next_session_synopsis],
        )
        if stop_event.wait(wait_seconds):
            return
        try:
            context = RuntimeContext(display_timezone=dt.timezone.utc)
            now = time.monotonic()
            if next_readiness is not None and now >= next_readiness:
                _run_periodic_refresh_command(vault, "auto-improve-readiness-report-body")
                _assert_readiness_allows_continuation(vault)
                status = _read_status_for_periodic_update(vault, status_path, context)
                status["last_event"] = {
                    "at": context.isoformat_z(),
                    "event": "periodic_readiness_refresh",
                    "reason": f"profile={profile_name}; target=auto-improve-readiness-report-body",
                }
                write_goal_status(
                    vault,
                    status,
                    event="periodic_readiness_refresh",
                    reason=f"profile={profile_name}; target=auto-improve-readiness-report-body",
                )
                next_readiness = _next_due(now, schedule.readiness_interval_seconds)
            if next_session_synopsis is not None and now >= next_session_synopsis:
                _run_periodic_refresh_command(vault, "session-synopsis")
                status = _read_status_for_periodic_update(vault, status_path, context)
                status["last_event"] = {
                    "at": context.isoformat_z(),
                    "event": "periodic_session_synopsis",
                    "reason": f"profile={profile_name}; target=session-synopsis",
                }
                write_goal_status(
                    vault,
                    status,
                    event="periodic_session_synopsis",
                    reason=f"profile={profile_name}; target=session-synopsis",
                )
                next_session_synopsis = _next_due(now, schedule.session_synopsis_interval_seconds)
            if next_checkpoint is not None and now >= next_checkpoint:
                status = _read_status_for_periodic_update(vault, status_path, context)
                status["last_event"] = {
                    "at": context.isoformat_z(),
                    "event": "checkpoint",
                    "reason": f"periodic checkpoint for goal profile: {profile_name}",
                }
                status = write_checkpoint(
                    vault,
                    status,
                    reason=f"periodic checkpoint for goal profile: {profile_name}",
                )
                write_goal_status(
                    vault,
                    status,
                    event="checkpoint",
                    reason=f"periodic checkpoint for goal profile: {profile_name}",
                )
                next_checkpoint = _next_due(now, schedule.checkpoint_interval_seconds)
                next_heartbeat = _next_due(now, schedule.heartbeat_interval_seconds)
                continue
            if next_heartbeat is not None and now >= next_heartbeat:
                status = _read_status_for_periodic_update(vault, status_path, context)
                status["last_event"] = {
                    "at": context.isoformat_z(),
                    "event": "heartbeat",
                    "reason": f"auto-improve goal profile heartbeat: {profile_name}",
                }
                write_goal_status(
                    vault,
                    status,
                    event="heartbeat",
                    reason=f"auto-improve goal profile heartbeat: {profile_name}",
                )
                next_heartbeat = _next_due(now, schedule.heartbeat_interval_seconds)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
            stop_event.set()
            return


def _start_maintenance_thread(
    vault: Path,
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
) -> tuple[Event, Thread | None, list[str]]:
    schedule = _build_maintenance_schedule(request, profile)
    errors: list[str] = []
    stop_event = Event()
    if not any(
        interval is not None
        for interval in (
            schedule.heartbeat_interval_seconds,
            schedule.checkpoint_interval_seconds,
            schedule.readiness_interval_seconds,
            schedule.session_synopsis_interval_seconds,
        )
    ):
        return stop_event, None, errors
    thread = Thread(
        target=_maintenance_loop,
        kwargs={
            "vault": vault,
            "status_path": request.status_out,
            "profile_name": str(profile["profile"]),
            "schedule": schedule,
            "stop_event": stop_event,
            "errors": errors,
        },
        daemon=True,
    )
    thread.start()
    return stop_event, thread, errors


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
    status = _merge_periodic_status_updates(vault, status, status_path=request.status_out)
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
    contract = _load_goal_contract(vault, request.goal_contract)
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
