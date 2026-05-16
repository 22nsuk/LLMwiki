from __future__ import annotations

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

from .goal_run_status import _heartbeat_status, write_checkpoint, write_goal_status
from .goal_runtime_request import GoalAutoImproveRequest


RefreshCommand = Callable[[Path, str], None]


@dataclass(frozen=True)
class GoalMaintenanceSchedule:
    heartbeat_interval_seconds: float | None
    checkpoint_interval_seconds: float | None
    readiness_interval_seconds: float | None
    session_synopsis_interval_seconds: float | None


def positive_interval_seconds(value: float | int | None) -> float | None:
    if value is None:
        return None
    resolved = float(value)
    if resolved <= 0:
        return None
    return resolved


def build_maintenance_schedule(
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
) -> GoalMaintenanceSchedule:
    if request.heartbeat_interval_seconds is not None:
        heartbeat_interval = positive_interval_seconds(request.heartbeat_interval_seconds)
    else:
        heartbeat_interval = positive_interval_seconds(
            int(request.heartbeat_interval_minutes or profile["heartbeat_interval_minutes"]) * 60
        )
    if request.checkpoint_interval_seconds is not None:
        checkpoint_interval = positive_interval_seconds(request.checkpoint_interval_seconds)
    else:
        checkpoint_interval = positive_interval_seconds(
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
        readiness_interval_seconds=positive_interval_seconds(readiness_interval),
        session_synopsis_interval_seconds=positive_interval_seconds(session_synopsis_interval),
    )


def next_due(now: float, interval: float | None) -> float | None:
    if interval is None:
        return None
    return now + interval


def wait_seconds(now: float, due_times: list[float | None]) -> float:
    active_due_times = [due for due in due_times if due is not None]
    if not active_due_times:
        return 0
    return max(0.0, min(active_due_times) - now)


def run_periodic_refresh_command(vault: Path, target: str) -> None:
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


def readiness_continuation_blocker(vault: Path) -> str | None:
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


def assert_readiness_allows_continuation(vault: Path) -> None:
    blocker = readiness_continuation_blocker(vault)
    if blocker is not None:
        raise RuntimeError(blocker)


def read_status_for_periodic_update(
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


def maintenance_loop(
    vault: Path,
    status_path: str,
    *,
    profile_name: str,
    schedule: GoalMaintenanceSchedule,
    stop_event: Event,
    errors: list[str],
    refresh_command: RefreshCommand,
) -> None:
    now = time.monotonic()
    next_heartbeat = next_due(now, schedule.heartbeat_interval_seconds)
    next_checkpoint = next_due(now, schedule.checkpoint_interval_seconds)
    next_readiness = next_due(now, schedule.readiness_interval_seconds)
    next_session_synopsis = next_due(now, schedule.session_synopsis_interval_seconds)
    if not any(
        due is not None
        for due in (next_heartbeat, next_checkpoint, next_readiness, next_session_synopsis)
    ):
        return
    while True:
        now = time.monotonic()
        interval_wait = wait_seconds(
            now,
            [next_heartbeat, next_checkpoint, next_readiness, next_session_synopsis],
        )
        if stop_event.wait(interval_wait):
            return
        try:
            context = RuntimeContext(display_timezone=dt.timezone.utc)
            now = time.monotonic()
            if next_readiness is not None and now >= next_readiness:
                refresh_command(vault, "auto-improve-readiness-report-body")
                assert_readiness_allows_continuation(vault)
                status = read_status_for_periodic_update(vault, status_path, context)
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
                next_readiness = next_due(now, schedule.readiness_interval_seconds)
            if next_session_synopsis is not None and now >= next_session_synopsis:
                refresh_command(vault, "session-synopsis")
                status = read_status_for_periodic_update(vault, status_path, context)
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
                next_session_synopsis = next_due(now, schedule.session_synopsis_interval_seconds)
            if next_checkpoint is not None and now >= next_checkpoint:
                status = read_status_for_periodic_update(vault, status_path, context)
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
                next_checkpoint = next_due(now, schedule.checkpoint_interval_seconds)
                next_heartbeat = next_due(now, schedule.heartbeat_interval_seconds)
                continue
            if next_heartbeat is not None and now >= next_heartbeat:
                status = read_status_for_periodic_update(vault, status_path, context)
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
                next_heartbeat = next_due(now, schedule.heartbeat_interval_seconds)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
            stop_event.set()
            return


def start_maintenance_thread(
    vault: Path,
    request: GoalAutoImproveRequest,
    profile: dict[str, int | str],
    *,
    refresh_command: RefreshCommand = run_periodic_refresh_command,
) -> tuple[Event, Thread | None, list[str]]:
    schedule = build_maintenance_schedule(request, profile)
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
        target=maintenance_loop,
        kwargs={
            "vault": vault,
            "status_path": request.status_out,
            "profile_name": str(profile["profile"]),
            "schedule": schedule,
            "stop_event": stop_event,
            "errors": errors,
            "refresh_command": refresh_command,
        },
        daemon=True,
    )
    thread.start()
    return stop_event, thread, errors
