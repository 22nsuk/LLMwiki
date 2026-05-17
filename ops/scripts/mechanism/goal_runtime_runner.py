from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import datetime as dt
from pathlib import Path
import shlex
import sys
import time
from typing import Any

from ops.scripts.command_runtime import (
    CommandHeartbeat,
    ProcessBackend,
    TimedProcessResult,
    run_with_timeout,
)
from ops.scripts.output_runtime import display_path, resolve_repo_output_path, write_output_text
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext

from .goal_run_status import (
    DEFAULT_STATUS_PATH,
    GoalRunStatusRequest,
    build_report as build_goal_run_status_report,
    goal_run_artifact_paths,
    write_report as write_goal_run_status_report,
    write_run_artifacts,
)
from .goal_runtime_maintenance import (
    PERIODIC_CHECKPOINT_COMMAND_EVENT,
    append_checkpoint_command_event,
    build_periodic_evidence,
    checkpoint_command_retry_due,
)
from .goal_runtime_profile import PROFILE_REQUIREMENTS


DEFAULT_RESULT_OUT = "tmp/auto-improve-goal-session-result.json"
PRODUCER = "ops.scripts.goal_runtime_runner"


@dataclass(frozen=True)
class CheckpointCommandExecution:
    command: str
    status: str
    returncode: int
    timed_out: bool
    timeout_seconds: int
    termination_reason: str = ""
    stdout_bytes: int = 0
    stderr_bytes: int = 0


CheckpointCommandExecutor = Callable[[str, dt.datetime], CheckpointCommandExecution]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class GoalRuntimeRunnerRequest:
    vault: Path
    command_argv: Sequence[str]
    run_id: str
    goal_contract_path: str
    profile: str = "30m_trial"
    status_report_path: str = DEFAULT_STATUS_PATH
    result_out: str = DEFAULT_RESULT_OUT
    heartbeat_interval_seconds: int = 300
    checkpoint_interval_seconds: int = 1800
    checkpoint_command_timeout_seconds: int = 900
    timeout_seconds: int = 1800
    resume_from_checkpoint: bool = False
    resume_command: str = ""
    policy_path: str | None = None
    context: RuntimeContext | None = None
    backend: ProcessBackend | None = None
    monotonic_clock: Callable[[], float] | None = None
    checkpoint_backend: ProcessBackend | None = None
    checkpoint_command_executor: CheckpointCommandExecutor | None = None
    profile_minimum_elapsed_seconds: int | None = None
    sleeper: Sleeper | None = None


def _iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _context_at(base_context: RuntimeContext, value: dt.datetime) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=base_context.display_timezone,
        clock=lambda: value,
        session_id=base_context.session_id,
        iteration=base_context.iteration,
        executor_id=base_context.executor_id,
    )


def _status_report(
    request: GoalRuntimeRunnerRequest,
    *,
    generated_at: dt.datetime,
    started_at: str,
    run_status: str,
    completed_at: str = "",
    last_heartbeat_at: str = "",
    last_checkpoint_at: str = "",
    last_command_heartbeat_at: str = "",
    quiet_seconds: int = 0,
    command_observation_mode: str = "",
    command_heartbeat_count: int = 0,
    command_timeout_seconds: int = 0,
    last_stdout_at: str = "",
    last_stderr_at: str = "",
    last_artifact_touch_at: str = "",
    last_command_returncode: int = -1,
    last_command_timed_out: bool = False,
    last_command_termination_reason: str = "",
    runtime_context: RuntimeContext,
) -> dict[str, Any]:
    observed_at = _iso_z(generated_at)
    resume_command = request.resume_command or " ".join(request.command_argv)
    return build_goal_run_status_report(
        GoalRunStatusRequest(
            vault=request.vault,
            run_id=request.run_id,
            goal_contract_path=request.goal_contract_path,
            status=run_status,
            profile=request.profile,
            started_at=started_at,
            completed_at=completed_at,
            heartbeat_interval_seconds=request.heartbeat_interval_seconds,
            checkpoint_interval_seconds=request.checkpoint_interval_seconds,
            last_heartbeat_at=last_heartbeat_at or observed_at,
            last_checkpoint_at=last_checkpoint_at or observed_at,
            last_command_heartbeat_at=last_command_heartbeat_at or observed_at,
            quiet_seconds=quiet_seconds,
            command_observation_mode=command_observation_mode,
            command_heartbeat_count=command_heartbeat_count,
            command_timeout_seconds=command_timeout_seconds,
            last_stdout_at=last_stdout_at,
            last_stderr_at=last_stderr_at,
            last_artifact_touch_at=last_artifact_touch_at,
            last_command_returncode=last_command_returncode,
            last_command_timed_out=last_command_timed_out,
            last_command_termination_reason=last_command_termination_reason,
            resume_from_checkpoint=request.resume_from_checkpoint,
            resume_command=resume_command,
            status_report_path=request.status_report_path,
            context=_context_at(runtime_context, generated_at),
        )
    )


def _write_status(
    request: GoalRuntimeRunnerRequest,
    report: dict[str, Any],
) -> None:
    write_goal_run_status_report(request.vault, report, request.status_report_path)
    write_run_artifacts(request.vault, report, writer=PRODUCER)


def _exit_code(returncode: int, *, timed_out: bool) -> int:
    if timed_out:
        return 124
    return returncode


def _execution_from_timed_process(
    *,
    command: str,
    timeout_seconds: int,
    result: TimedProcessResult,
) -> CheckpointCommandExecution:
    return CheckpointCommandExecution(
        command=command,
        status="pass" if result.returncode == 0 and not result.timed_out else "fail",
        returncode=result.returncode,
        timed_out=result.timed_out,
        timeout_seconds=timeout_seconds,
        termination_reason=result.termination_reason,
        stdout_bytes=len(result.stdout.encode("utf-8")),
        stderr_bytes=len(result.stderr.encode("utf-8")),
    )


def _run_checkpoint_command(
    request: GoalRuntimeRunnerRequest,
    command: str,
    observed_at: dt.datetime,
) -> CheckpointCommandExecution:
    if request.checkpoint_command_executor is not None:
        return request.checkpoint_command_executor(command, observed_at)
    argv = shlex.split(command)
    if not argv:
        return CheckpointCommandExecution(
            command=command,
            status="fail",
            returncode=2,
            timed_out=False,
            timeout_seconds=request.checkpoint_command_timeout_seconds,
            termination_reason="empty_command",
        )
    result = run_with_timeout(
        argv,
        cwd=request.vault.resolve(),
        timeout_seconds=request.checkpoint_command_timeout_seconds,
        backend=request.checkpoint_backend,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return _execution_from_timed_process(
        command=command,
        timeout_seconds=request.checkpoint_command_timeout_seconds,
        result=result,
    )


def _checkpoint_execution_payload(execution: CheckpointCommandExecution) -> dict[str, Any]:
    return {
        "command": execution.command,
        "status": execution.status,
        "returncode": execution.returncode,
        "timed_out": execution.timed_out,
        "timeout_seconds": execution.timeout_seconds,
        "termination_reason": execution.termination_reason,
        "stdout_bytes": execution.stdout_bytes,
        "stderr_bytes": execution.stderr_bytes,
    }


def _run_due_checkpoint_commands(
    request: GoalRuntimeRunnerRequest,
    *,
    generated_at: dt.datetime,
    started_at: str,
) -> None:
    paths = goal_run_artifact_paths(
        request.run_id,
        status_report_path=request.status_report_path,
    )
    generated_at_text = _iso_z(generated_at)
    periodic = build_periodic_evidence(
        request.vault.resolve(),
        generated_at=generated_at_text,
        started_at=started_at,
        last_checkpoint_at=generated_at_text,
        checkpoint_command_log_path=paths.checkpoint_command_log_path,
    )
    for checkpoint in periodic["checkpoints"]:
        command_run = checkpoint["command_run"]
        if not checkpoint_command_retry_due(
            generated_at=generated_at_text,
            command_run=command_run,
            retry_after_seconds=request.checkpoint_interval_seconds,
        ):
            continue
        executions: list[CheckpointCommandExecution] = []
        for command in checkpoint["commands"]:
            execution = _run_checkpoint_command(request, str(command), generated_at)
            executions.append(execution)
            if execution.status != "pass":
                break
        failed_count = sum(1 for execution in executions if execution.status != "pass")
        append_checkpoint_command_event(
            request.vault.resolve(),
            paths.checkpoint_command_log_path,
            {
                "event": PERIODIC_CHECKPOINT_COMMAND_EVENT,
                "generated_at": generated_at_text,
                "run_id": request.run_id,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "status": "pass" if failed_count == 0 else "fail",
                "command_count": len(executions),
                "failed_command_count": failed_count,
                "commands": [_checkpoint_execution_payload(execution) for execution in executions],
            },
        )


def _profile_minimum_elapsed_seconds(request: GoalRuntimeRunnerRequest) -> int:
    if request.profile_minimum_elapsed_seconds is not None:
        return max(0, int(request.profile_minimum_elapsed_seconds))
    requirements = PROFILE_REQUIREMENTS.get(request.profile, {})
    value = requirements.get("minimum_elapsed_seconds", 0)
    return max(0, int(value)) if isinstance(value, int) else 0


def _elapsed_since_start(started_at: dt.datetime, observed_at: dt.datetime) -> int:
    return max(0, int((observed_at - started_at).total_seconds()))


def run_goal_runtime_command(request: GoalRuntimeRunnerRequest) -> int:
    if not request.command_argv:
        raise ValueError("goal runtime runner requires a command after --")
    if request.timeout_seconds < 1:
        raise ValueError("timeout_seconds must be >= 1")
    if request.heartbeat_interval_seconds < 1:
        raise ValueError("heartbeat_interval_seconds must be >= 1")
    if request.checkpoint_interval_seconds < 1:
        raise ValueError("checkpoint_interval_seconds must be >= 1")
    if request.checkpoint_command_timeout_seconds < 1:
        raise ValueError("checkpoint_command_timeout_seconds must be >= 1")

    vault = request.vault.resolve()
    policy, _resolved_policy_path = load_policy(vault, request.policy_path)
    runtime_context = request.context or RuntimeContext.from_policy(policy)
    started_at_dt = runtime_context.utcnow().replace(microsecond=0)
    started_at = _iso_z(started_at_dt)
    _write_status(
        request,
        _status_report(
            request,
            generated_at=started_at_dt,
            started_at=started_at,
            run_status="running",
            quiet_seconds=0,
            command_observation_mode="process_heartbeat",
            command_timeout_seconds=request.timeout_seconds,
            runtime_context=runtime_context,
        ),
    )

    last_observed_at = started_at_dt

    def heartbeat_callback(event: CommandHeartbeat) -> None:
        nonlocal last_observed_at
        observed_at = started_at_dt + dt.timedelta(seconds=int(event.elapsed_seconds))
        last_observed_at = max(last_observed_at, observed_at)
        observed_at_text = _iso_z(observed_at)
        _run_due_checkpoint_commands(
            request,
            generated_at=observed_at,
            started_at=started_at,
        )
        _write_status(
            request,
            _status_report(
                request,
                generated_at=observed_at,
                started_at=started_at,
                run_status="running",
                last_heartbeat_at=observed_at_text,
                last_checkpoint_at=observed_at_text,
                last_command_heartbeat_at=observed_at_text,
                quiet_seconds=event.quiet_seconds,
                command_observation_mode=event.observation_mode,
                command_heartbeat_count=event.heartbeat_index,
                command_timeout_seconds=event.timeout_seconds,
                last_stdout_at=event.last_stdout_at,
                last_stderr_at=event.last_stderr_at,
                last_artifact_touch_at=event.last_artifact_touch_at,
                runtime_context=runtime_context,
            ),
        )

    result = run_with_timeout(
        list(request.command_argv),
        cwd=vault,
        timeout_seconds=request.timeout_seconds,
        backend=request.backend,
        heartbeat_interval_seconds=request.heartbeat_interval_seconds,
        heartbeat_callback=heartbeat_callback,
        monotonic_clock=request.monotonic_clock,
    )
    result_path = resolve_repo_output_path(vault, request.result_out, default_relative_path=DEFAULT_RESULT_OUT)
    write_output_text(result_path, result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")

    minimum_elapsed_seconds = _profile_minimum_elapsed_seconds(request)
    final_command_heartbeat_count = result.heartbeat_count
    if (
        result.returncode == 0
        and not result.timed_out
        and minimum_elapsed_seconds > 0
        and request.timeout_seconds >= minimum_elapsed_seconds
    ):
        sleeper = request.sleeper or time.sleep
        observed_elapsed_seconds = _elapsed_since_start(started_at_dt, last_observed_at)
        while observed_elapsed_seconds < minimum_elapsed_seconds:
            next_heartbeat_index = final_command_heartbeat_count + 1
            next_elapsed_seconds = next_heartbeat_index * request.heartbeat_interval_seconds
            if next_elapsed_seconds <= observed_elapsed_seconds:
                next_elapsed_seconds = observed_elapsed_seconds + request.heartbeat_interval_seconds
            next_elapsed_seconds = min(minimum_elapsed_seconds, next_elapsed_seconds)
            sleeper(max(0.0, float(next_elapsed_seconds - observed_elapsed_seconds)))
            final_command_heartbeat_count = next_heartbeat_index
            heartbeat_callback(
                CommandHeartbeat(
                    args=list(request.command_argv),
                    heartbeat_index=final_command_heartbeat_count,
                    elapsed_seconds=float(next_elapsed_seconds),
                    timeout_seconds=request.timeout_seconds,
                    quiet_seconds=next_elapsed_seconds,
                    observation_mode="process_heartbeat",
                )
            )
            observed_elapsed_seconds = next_elapsed_seconds

    completed_now = runtime_context.utcnow().replace(microsecond=0)
    completed_at_dt = max(completed_now, last_observed_at)
    completed_at = _iso_z(completed_at_dt)
    _run_due_checkpoint_commands(
        request,
        generated_at=completed_at_dt,
        started_at=started_at,
    )
    final_status = "completed" if result.returncode == 0 and not result.timed_out else "failed"
    _write_status(
        request,
        _status_report(
            request,
            generated_at=completed_at_dt,
            started_at=started_at,
            run_status=final_status,
            completed_at=completed_at,
            last_heartbeat_at=completed_at,
            last_checkpoint_at=completed_at,
            last_command_heartbeat_at=completed_at,
            quiet_seconds=result.quiet_seconds,
            command_observation_mode=result.observation_mode,
            command_heartbeat_count=final_command_heartbeat_count,
            command_timeout_seconds=result.timeout_seconds,
            last_stdout_at=result.last_stdout_at,
            last_stderr_at=result.last_stderr_at,
            last_artifact_touch_at=result.last_artifact_touch_at,
            last_command_returncode=result.returncode,
            last_command_timed_out=result.timed_out,
            last_command_termination_reason=result.termination_reason,
            runtime_context=runtime_context,
        ),
    )
    print(display_path(vault, result_path))
    return _exit_code(result.returncode, timed_out=result.timed_out)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--goal-contract", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile", default="30m_trial")
    parser.add_argument("--status-report-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--result-out", default=DEFAULT_RESULT_OUT)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=300)
    parser.add_argument("--checkpoint-interval-seconds", type=int, default=1800)
    parser.add_argument("--checkpoint-command-timeout-seconds", type=int, default=900)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--resume-from-checkpoint", action="store_true")
    parser.add_argument("--resume-command", default="")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    return run_goal_runtime_command(
        GoalRuntimeRunnerRequest(
            vault=Path(args.vault).resolve(),
            command_argv=command,
            run_id=args.run_id,
            goal_contract_path=args.goal_contract,
            profile=args.profile,
            status_report_path=args.status_report_path,
            result_out=args.result_out,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
            checkpoint_interval_seconds=args.checkpoint_interval_seconds,
            checkpoint_command_timeout_seconds=args.checkpoint_command_timeout_seconds,
            timeout_seconds=args.timeout_seconds,
            resume_from_checkpoint=args.resume_from_checkpoint,
            resume_command=args.resume_command,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
