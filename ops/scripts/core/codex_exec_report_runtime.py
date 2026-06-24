from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .artifact_io_runtime import write_schema_validated_json
from .codex_exec_execution_types_runtime import (
    ExecutorObservabilityPayload,
    ExecutorReportPayload,
    ExecutorReportRequest,
    _ExecutionSummary,
    _ExecutorArtifacts,
)
from .codex_exec_model_output_runtime import scope_freeze_input_digest
from .experiment_telemetry_runtime import (
    append_ledger_event,
    run_rel,
    write_timeout_failure_artifact,
)
from .runtime_context import RuntimeContext
from .runtime_event_logging_runtime import append_runtime_event
from .schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH
from .schema_runtime import load_schema

EXECUTOR_REPORT_SCHEMA = EXECUTOR_REPORT_SCHEMA_PATH


def completed_timed_out(completed: object) -> bool:
    value = getattr(completed, "timed_out", False)
    if isinstance(value, bool):
        return value
    return False


def completed_returncode(completed: object) -> int:
    value = getattr(completed, "returncode", 0)
    if isinstance(value, int):
        return value
    return 0


def completed_timeout_seconds(completed: object, fallback: int) -> int:
    value = getattr(completed, "timeout_seconds", fallback)
    if isinstance(value, int):
        return value
    return fallback


def completed_termination_reason(completed: object, *, timed_out: bool) -> str:
    fallback = "timeout" if timed_out else "completed"
    value = getattr(completed, "termination_reason", fallback)
    if value in {"completed", "timeout"}:
        return str(value)
    return fallback


def completed_launch_succeeded(completed: object) -> bool:
    value = getattr(completed, "launch_succeeded", True)
    return bool(value)


def completed_signal_sent(completed: object) -> str:
    return str(getattr(completed, "signal_sent", "none")).strip()


def completed_final_state_observed(completed: object) -> str:
    return str(getattr(completed, "final_state_observed", "")).strip()


def completed_stdout_received(completed: object) -> bool:
    return bool(getattr(completed, "stdout_received", False))


def completed_stderr_received(completed: object) -> bool:
    return bool(getattr(completed, "stderr_received", False))


def completed_int_attr(completed: object, name: str) -> int:
    value = getattr(completed, name, 0)
    if isinstance(value, int):
        return value
    return 0


def completed_str_attr(completed: object, name: str, default: str = "") -> str:
    value = getattr(completed, name, default)
    if isinstance(value, str):
        return value.strip()
    return default


def completed_observability(completed: object) -> ExecutorObservabilityPayload:
    return {
        "heartbeat_count": completed_int_attr(completed, "heartbeat_count"),
        "heartbeat_interval_seconds": completed_int_attr(
            completed, "heartbeat_interval_seconds"
        ),
        "quiet_seconds": completed_int_attr(completed, "quiet_seconds"),
        "last_stdout_at": completed_str_attr(completed, "last_stdout_at"),
        "last_stderr_at": completed_str_attr(completed, "last_stderr_at"),
        "last_artifact_touch_at": completed_str_attr(
            completed, "last_artifact_touch_at"
        ),
        "observation_mode": completed_str_attr(
            completed, "observation_mode", "communicate"
        ),
    }


def build_executor_report(request: ExecutorReportRequest) -> ExecutorReportPayload:
    return {
        "$schema": EXECUTOR_REPORT_SCHEMA,
        "run_id": request.run_id,
        "role": request.role,
        "input_digest": scope_freeze_input_digest(request.scope_freeze),
        "generated_at": request.context.isoformat_z(),
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": request.routing_report["routing_decision"]["sandbox_mode"],
            "model": request.routing_report["routing_decision"]["model"],
            "reasoning_effort": request.routing_report["routing_decision"][
                "reasoning_effort"
            ],
        },
        "status": request.summary.status,
        "command": {"argv": request.sanitized_argv},
        "artifacts": {
            "prompt": request.artifacts.prompt_rel,
            "output_last_message": request.artifacts.output_last_message_rel,
            "stdout": request.artifacts.stdout_rel,
            "stderr": request.artifacts.stderr_rel,
            "command_log_summary": request.artifacts.command_log_summary_rel,
            "timeout_failure": None,
        },
        "result": {
            "returncode": completed_returncode(request.completed),
            "timed_out": request.summary.timed_out,
            "timeout_seconds": request.summary.timeout_seconds,
            "termination_reason": request.summary.termination_reason,
            "launch_succeeded": completed_launch_succeeded(request.completed),
            "signal_sent": completed_signal_sent(request.completed),
            "final_state_observed": completed_final_state_observed(request.completed),
            "stdout_received": completed_stdout_received(request.completed),
            "stderr_received": completed_stderr_received(request.completed),
            "observability": completed_observability(request.completed),
        },
        "diagnostics": {
            "routing_report": request.routing_report_rel,
            "scope_freeze": request.scope_freeze_rel,
            "dependency_preflight": request.dependency_preflight,
            "notes": request.summary.notes,
        },
    }


def attach_timeout_failure(
    *,
    artifact_root: Path,
    report: ExecutorReportPayload,
    artifacts: _ExecutorArtifacts,
    routing_report_rel: str,
    scope_freeze_rel: str,
    sanitized_argv: list[str],
    completed: object,
    summary: _ExecutionSummary,
    context: RuntimeContext,
) -> str | None:
    if not summary.timed_out:
        return None
    run_id = str(report["run_id"])
    role = str(report["role"])
    timeout_failure_rel = write_timeout_failure_artifact(
        artifact_root,
        run_id,
        phase="executor",
        role=role,
        command={"argv": sanitized_argv},
        result={
            "returncode": completed_returncode(completed),
            "timed_out": summary.timed_out,
            "timeout_seconds": summary.timeout_seconds,
            "termination_reason": summary.termination_reason,
            "launch_succeeded": completed_launch_succeeded(completed),
            "signal_sent": completed_signal_sent(completed),
            "final_state_observed": completed_final_state_observed(completed),
            "stdout_received": completed_stdout_received(completed),
            "stderr_received": completed_stderr_received(completed),
        },
        artifacts={
            "prompt": artifacts.prompt_rel,
            "output_last_message": artifacts.output_last_message_rel,
            "stdout": artifacts.stdout_rel,
            "stderr": artifacts.stderr_rel,
            "command_log_summary": artifacts.command_log_summary_rel,
            "routing_report": routing_report_rel,
            "scope_freeze": scope_freeze_rel,
        },
        context=context,
        diagnostics={"notes": summary.notes},
    )
    report["artifacts"]["timeout_failure"] = timeout_failure_rel
    return timeout_failure_rel


def executor_ledger_event_type(role: str, status: str) -> tuple[str, str | None]:
    if status == "pass":
        return ("executor_completed", None)
    if role == "reviewer":
        return ("review_blocked", "blocked")
    if role == "validator" or role.endswith("auditor"):
        return ("validation_blocked", "blocked")
    return ("executor_completed", "blocked")


def write_executor_report_and_ledger(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    report: ExecutorReportPayload,
    routing_report_rel: str,
    scope_freeze_rel: str,
    prompt_rel: str,
    timeout_failure_rel: str | None,
    summary: _ExecutionSummary,
    context: RuntimeContext,
) -> None:
    schema = load_schema(artifact_root / EXECUTOR_REPORT_SCHEMA)
    report_rel = run_rel(run_id, f"{role}-executor-report.json")
    write_schema_validated_json(
        artifact_root / report_rel,
        report,
        schema,
        context=f"executor report schema validation failed for {role}",
    )
    event_type, status_value = executor_ledger_event_type(role, summary.status)
    append_ledger_event(
        artifact_root,
        run_id,
        event_type=event_type,
        summary=f"Executed {role} via codex exec.",
        artifacts=[
            routing_report_rel,
            scope_freeze_rel,
            prompt_rel,
            report_rel,
            *([timeout_failure_rel] if timeout_failure_rel else []),
        ],
        decision=summary.decision if summary.status != "pass" else "ready",
        context=context,
        status=status_value,
    )


def append_executor_runtime_event(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    summary: _ExecutionSummary,
    started_at: float,
    scope_freeze: dict[str, Any],
    context: RuntimeContext,
) -> None:
    append_runtime_event(
        artifact_root,
        context=context,
        component="codex_exec_executor",
        phase="executor",
        decision=summary.decision,
        artifact_path=run_rel(run_id, f"{role}-executor-report.json"),
        duration_ms=round((time.monotonic() - started_at) * 1000),
        run_id=run_id,
        policy_version=read_policy_version(scope_freeze),
        proposal_id=str(scope_freeze.get("proposal_id", "")).strip(),
        decision_reason="executor_summary_decision",
    )


def read_policy_version(scope_freeze: dict[str, Any]) -> Any:
    policy = scope_freeze.get("policy")
    if isinstance(policy, dict):
        return policy.get("version", "")
    return ""
