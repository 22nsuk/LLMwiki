from __future__ import annotations

import copy
import datetime as dt
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
    heartbeat_interval_seconds: int | None = None
    checkpoint_interval_minutes: int | None = None
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


def _heartbeat_loop(
    vault: Path,
    status_path: str,
    *,
    interval_seconds: int,
    stop_event: Event,
    errors: list[str],
) -> None:
    while not stop_event.wait(interval_seconds):
        try:
            context = RuntimeContext(display_timezone=dt.timezone.utc)
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
            status["last_event"] = {
                "at": context.isoformat_z(),
                "event": "heartbeat",
                "reason": "auto-improve goal profile heartbeat",
            }
            write_goal_status(
                vault,
                status,
                event="heartbeat",
                reason="auto-improve goal profile heartbeat",
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
            stop_event.set()


def _start_heartbeat_thread(
    vault: Path,
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
) -> tuple[Event, Thread | None, list[str]]:
    if request.heartbeat_interval_seconds is not None:
        interval_seconds = request.heartbeat_interval_seconds
    else:
        interval_seconds = int(request.heartbeat_interval_minutes or profile["heartbeat_interval_minutes"]) * 60
    errors: list[str] = []
    stop_event = Event()
    if interval_seconds <= 0:
        return stop_event, None, errors
    thread = Thread(
        target=_heartbeat_loop,
        kwargs={
            "vault": vault,
            "status_path": request.status_out,
            "interval_seconds": interval_seconds,
            "stop_event": stop_event,
            "errors": errors,
        },
        daemon=True,
    )
    thread.start()
    return stop_event, thread, errors


def _final_status_for_stop_reason(stop_reason: str) -> str:
    if stop_reason in {"failure_budget_exhausted", "learning_review_required"}:
        return "blocked"
    return "running"


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
    stop_event, heartbeat_thread, heartbeat_errors = _start_heartbeat_thread(vault, request, profile)
    started = time.monotonic()
    try:
        result = active_runner(
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
    finally:
        stop_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=5)

    progress = _read_session_progress(vault, result)
    progress["elapsed_minutes"] = round((time.monotonic() - started) / 60, 4)
    status["generated_at"] = context.isoformat_z()
    status["progress"] = progress
    stop_reason = str(result.get("stop_reason", "")).strip()
    if heartbeat_errors:
        status["status"] = "blocked"
        stop_reason = "heartbeat_write_failure"
        reason = f"heartbeat write failure: {heartbeat_errors[0]}"
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
