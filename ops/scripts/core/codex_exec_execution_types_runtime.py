from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from ops.scripts.core.runtime_context import RuntimeContext


class CodexExecError(Exception):
    pass


class ExecutorContractError(CodexExecError):
    pass


class ExecutorInfoPayload(TypedDict):
    name: str
    sandbox_mode: str
    model: str
    reasoning_effort: str


class ExecutorCommandPayload(TypedDict):
    argv: list[str]


class ExecutorArtifactsPayload(TypedDict):
    prompt: str
    output_last_message: str
    stdout: str
    stderr: str
    command_log_summary: str
    timeout_failure: str | None


class ExecutorObservabilityPayload(TypedDict):
    heartbeat_count: int
    heartbeat_interval_seconds: int
    quiet_seconds: int
    last_stdout_at: str
    last_stderr_at: str
    last_artifact_touch_at: str
    observation_mode: str


class ExecutorResultPayload(TypedDict):
    returncode: int
    timed_out: bool
    timeout_seconds: int
    termination_reason: str
    launch_succeeded: bool
    signal_sent: str
    final_state_observed: str
    stdout_received: bool
    stderr_received: bool
    observability: ExecutorObservabilityPayload


class ExecutorDiagnosticsPayload(TypedDict):
    routing_report: str
    scope_freeze: str
    dependency_preflight: ExecutorDependencyPreflightPayload
    notes: list[str]


class ExecutorDependencyCommandPayload(TypedDict):
    argv: list[str]
    project_check_lane: str


class ExecutorDependencyPythonPayload(TypedDict):
    path: str
    executable: str
    version: str
    exists: bool


class ExecutorDependencyModulePayload(TypedDict):
    import_name: str
    package: str
    status: str
    version: str
    detail: str


class ExecutorDependencyPreflightPayload(TypedDict):
    role_requires_project_check: bool
    status: str
    command: ExecutorDependencyCommandPayload
    python: ExecutorDependencyPythonPayload
    required_modules: list[ExecutorDependencyModulePayload]
    returncode: int


ExecutorReportPayload = TypedDict(
    "ExecutorReportPayload",
    {
        "$schema": str,
        "run_id": str,
        "role": str,
        "input_digest": str,
        "generated_at": str,
        "executor": ExecutorInfoPayload,
        "status": str,
        "command": ExecutorCommandPayload,
        "artifacts": ExecutorArtifactsPayload,
        "result": ExecutorResultPayload,
        "diagnostics": ExecutorDiagnosticsPayload,
    },
)


@dataclass(frozen=True)
class _ExecutorArtifacts:
    output_last_message_rel: str
    stdout_rel: str
    stderr_rel: str
    raw_stdout_rel: str
    raw_stderr_rel: str
    command_log_summary_rel: str
    prompt_rel: str


@dataclass(frozen=True)
class _ExecutionSummary:
    status: str
    decision: str
    notes: list[str]
    timed_out: bool
    timeout_seconds: int
    termination_reason: str


@dataclass(frozen=True)
class _SyntheticCompleted:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    timeout_seconds: int
    termination_reason: str
    launch_succeeded: bool
    signal_sent: str
    final_state_observed: str
    stdout_received: bool
    stderr_received: bool
    heartbeat_count: int
    heartbeat_interval_seconds: int
    quiet_seconds: int
    last_stdout_at: str
    last_stderr_at: str
    last_artifact_touch_at: str
    observation_mode: str


@dataclass(frozen=True)
class _ExecutionRequest:
    artifact_root: Path
    workspace_root: Path
    run_id: str
    role: str
    routing_report: dict[str, Any]
    scope_freeze: dict[str, Any]
    profile: dict[str, Any]
    routing_report_rel: str
    scope_freeze_rel: str
    proposal_snapshot_rel: str
    repair_context_rel: str
    repair_context: dict[str, Any] | None
    artifacts: _ExecutorArtifacts
    argv: list[str]
    sanitized_argv: list[str]
    prompt_path: Path
    timeout_seconds: int
    context: RuntimeContext


@dataclass(frozen=True)
class PromptMaterializationRequest:
    artifact_root: Path
    workspace_root: Path
    run_id: str
    role: str
    profile: dict[str, Any]
    routing_report: dict[str, Any]
    scope_freeze: dict[str, Any]
    proposal_snapshot_rel: str
    scope_freeze_rel: str
    routing_report_rel: str
    repair_context_rel: str
    repair_context: dict[str, Any] | None
    artifacts: _ExecutorArtifacts
    command_argv: list[str]
    timeout_seconds: int
    context: RuntimeContext


@dataclass(frozen=True)
class ExecutorReportRequest:
    run_id: str
    role: str
    scope_freeze: dict[str, Any]
    routing_report: dict[str, Any]
    routing_report_rel: str
    scope_freeze_rel: str
    artifacts: _ExecutorArtifacts
    sanitized_argv: list[str]
    completed: object
    summary: _ExecutionSummary
    dependency_preflight: ExecutorDependencyPreflightPayload
    context: RuntimeContext


ExecutionSummary = _ExecutionSummary
ExecutionRequest = _ExecutionRequest
SyntheticCompleted = _SyntheticCompleted
