from __future__ import annotations

import json
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from .artifact_io_runtime import write_schema_validated_json
from .command_runtime import run_with_timeout
from .experiment_telemetry_runtime import (
    append_ledger_event,
    run_rel,
    write_timeout_failure_artifact,
)
from .output_runtime import write_output_text
from .policy_runtime import report_path
from .runtime_context import RuntimeContext
from .runtime_event_logging_runtime import append_runtime_event
from .schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH
from .schema_runtime import load_schema


EXECUTOR_REPORT_SCHEMA = EXECUTOR_REPORT_SCHEMA_PATH
DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS = 1800
_CODEX_USAGE_LIMIT_RE = re.compile(
    r"(usage limit|try again at|upgrade to pro)",
    flags=re.IGNORECASE,
)
_CODEX_USAGE_LIMIT_RETRY_RE = re.compile(
    r"try again at\s+([^.\n\r]+)",
    flags=re.IGNORECASE,
)


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


class ExecutorArtifactsPayload(TypedDict, total=False):
    prompt: str
    output_last_message: str
    stdout: str
    stderr: str
    timeout_failure: str


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
    heartbeat: dict[str, Any]


class ExecutorDiagnosticsPayload(TypedDict, total=False):
    routing_report: str
    scope_freeze: str
    notes: list[str]


ExecutorReportPayload = TypedDict(
    "ExecutorReportPayload",
    {
        "$schema": str,
        "run_id": str,
        "role": str,
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
    prompt_rel: str


@dataclass(frozen=True)
class _ExecutionSummary:
    status: str
    decision: str
    notes: list[str]
    timed_out: bool
    timeout_seconds: int
    termination_reason: str


def _codex_usage_limit_note(stderr: str) -> str:
    if not _CODEX_USAGE_LIMIT_RE.search(stderr):
        return ""
    match = _CODEX_USAGE_LIMIT_RETRY_RE.search(stderr)
    if match:
        return f"codex exec blocked by usage limit; retry_after={match.group(1).strip()}"
    return "codex exec blocked by usage limit"


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
    artifacts: _ExecutorArtifacts
    argv: list[str]
    sanitized_argv: list[str]
    prompt_path: Path
    timeout_seconds: int


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
    artifacts: _ExecutorArtifacts
    command_argv: list[str]
    timeout_seconds: int
    context: RuntimeContext


def _completed_timed_out(completed: object) -> bool:
    value = getattr(completed, "timed_out", False)
    if isinstance(value, bool):
        return value
    return False


def _completed_returncode(completed: object) -> int:
    value = getattr(completed, "returncode", 0)
    if isinstance(value, int):
        return value
    return 0


def _completed_timeout_seconds(completed: object, fallback: int) -> int:
    value = getattr(completed, "timeout_seconds", fallback)
    if isinstance(value, int):
        return value
    return fallback


def _completed_termination_reason(completed: object, *, timed_out: bool) -> str:
    fallback = "timeout" if timed_out else "completed"
    value = getattr(completed, "termination_reason", fallback)
    if value in {"completed", "timeout"}:
        return str(value)
    return fallback


def _completed_launch_succeeded(completed: object) -> bool:
    value = getattr(completed, "launch_succeeded", True)
    return bool(value)


def _completed_signal_sent(completed: object) -> str:
    return str(getattr(completed, "signal_sent", "none")).strip()


def _completed_final_state_observed(completed: object) -> str:
    return str(getattr(completed, "final_state_observed", "")).strip()


def _completed_stdout_received(completed: object) -> bool:
    return bool(getattr(completed, "stdout_received", False))


def _completed_stderr_received(completed: object) -> bool:
    return bool(getattr(completed, "stderr_received", False))


def _completed_int_attr(completed: object, name: str, default: int = 0) -> int:
    value = getattr(completed, name, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _completed_float_attr(completed: object, name: str, default: float = 0.0) -> float:
    value = getattr(completed, name, default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _completed_heartbeat(completed: object) -> dict[str, Any]:
    interval = _completed_int_attr(completed, "heartbeat_interval_seconds")
    count = _completed_int_attr(completed, "heartbeat_emitted_count")
    elapsed = _completed_float_attr(completed, "last_heartbeat_elapsed_seconds")
    raw_status = getattr(completed, "heartbeat_status", "disabled")
    status = raw_status if isinstance(raw_status, str) and raw_status else "disabled"
    return {
        "interval_seconds": interval,
        "emitted_count": count,
        "last_elapsed_seconds": round(elapsed, 3),
        "status": status,
    }


def load_agent_profile(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ExecutorContractError(f"unable to read agent profile {path.name}: {exc}") from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ExecutorContractError(f"unable to parse agent profile {path.name}: {exc}") from exc


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutorContractError(f"unable to load {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExecutorContractError(f"{label} root must be an object")
    return payload


def _sanitize_root_strings(*roots: Path) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for root in roots:
        variants: list[str] = []
        for candidate in (root, root.absolute()):
            candidate_text = candidate.as_posix().rstrip("/")
            if candidate_text:
                variants.append(candidate_text)
        try:
            resolved_text = root.resolve().as_posix().rstrip("/")
        except OSError:
            resolved_text = ""
        if resolved_text:
            variants.append(resolved_text)
        for root_text in variants:
            key = root_text.lower()
            if not root_text or key in seen:
                continue
            seen.add(key)
            normalized.append(root_text)
    normalized.sort(key=len, reverse=True)
    return normalized


def _sanitize_path_text(text: str, *, roots: list[Path]) -> str:
    sanitized = text.replace("\\", "/")
    for root_text in _sanitize_root_strings(*roots):
        sanitized = re.sub(re.escape(f"{root_text}/"), "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(re.escape(root_text), ".", sanitized, flags=re.IGNORECASE)
    return sanitized


def _sanitize_argv(argv: list[str], *, roots: list[Path]) -> list[str]:
    return [_sanitize_path_text(item, roots=roots) for item in argv]


def _materialize_prompt(request: PromptMaterializationRequest) -> Path:
    prompt_path = request.artifact_root / request.artifacts.prompt_rel
    sandbox_mode = request.routing_report["routing_decision"]["sandbox_mode"]
    sanitize_roots = [request.artifact_root, request.workspace_root]
    sanitized_command_argv = _sanitize_argv(request.command_argv, roots=sanitize_roots)
    template = {
        "$schema": EXECUTOR_REPORT_SCHEMA,
        "run_id": request.run_id,
        "role": request.role,
        "generated_at": request.context.isoformat_z(),
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": sandbox_mode,
            "model": request.routing_report["routing_decision"]["model"],
            "reasoning_effort": request.routing_report["routing_decision"]["reasoning_effort"],
        },
        "status": "pass",
        "command": {
            "argv": sanitized_command_argv
        },
        "artifacts": {
            "prompt": request.artifacts.prompt_rel,
            "output_last_message": request.artifacts.output_last_message_rel,
            "stdout": request.artifacts.stdout_rel,
            "stderr": request.artifacts.stderr_rel,
        },
        "result": {
            "returncode": 0,
            "timed_out": False,
            "timeout_seconds": request.timeout_seconds,
            "termination_reason": "completed",
            "launch_succeeded": True,
            "signal_sent": "none",
            "final_state_observed": "communicate",
            "stdout_received": True,
            "stderr_received": True,
            "heartbeat": {
                "interval_seconds": 300,
                "emitted_count": 0,
                "last_elapsed_seconds": 0.0,
                "status": "completed"
            }
        },
        "diagnostics": {
            "routing_report": request.routing_report_rel,
            "scope_freeze": request.scope_freeze_rel,
            "notes": []
        }
    }
    prompt_text = f"""You are executing the `{request.role}` role for LLM Wiki vNext.

Role profile:
- name: `{request.profile.get("name", request.role)}`
- description: {request.profile.get("description", "")}
- sandbox_mode: `{sandbox_mode}`

Developer instructions:
{request.profile.get("developer_instructions", "").strip()}

Run context:
- run_id: `{request.run_id}`
- workspace_root: `{_sanitize_path_text(str(request.workspace_root), roots=sanitize_roots)}`
- proposal_snapshot: `{request.proposal_snapshot_rel}`
- scope_freeze: `{request.scope_freeze_rel}`
- routing_report: `{request.routing_report_rel}`

Repository write boundary:
- worker may only mutate `ops/**`, `tests/**`, and bounded files required by the selected proposal.
- reviewer, validator, and auditor roles are read-only.
- never edit `raw/`, `wiki/`, or non-log `system/` pages.
- do not rewrite unrelated files or expand scope.

Scope freeze summary:
```json
{json.dumps(request.scope_freeze, ensure_ascii=False, indent=2)}
```

Routing summary:
```json
{json.dumps(request.routing_report, ensure_ascii=False, indent=2)}
```

Final response requirements:
- Return JSON only.
- Match this schema-compatible shape exactly.
- Set `status` to `fail` if you are blocked, timed out, or if reviewer/validator/auditor found a material issue.
- Keep `executor`, `artifacts`, and `result` aligned with the template below.
- Put concise evidence in `diagnostics.notes`.

JSON template:
```json
{json.dumps(template, ensure_ascii=False, indent=2)}
```
"""
    prompt_text = _sanitize_path_text(prompt_text, roots=sanitize_roots)
    write_output_text(prompt_path, prompt_text)
    return prompt_path


def _load_executor_inputs(
    *,
    artifact_root: Path,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    routing_path = artifact_root / routing_report_rel
    scope_path = artifact_root / scope_freeze_rel
    proposal_snapshot_path = artifact_root / proposal_snapshot_rel
    profile_path = artifact_root / ".codex" / "agents" / f"{role}.toml"

    routing_report = _load_json_object(routing_path, label=routing_report_rel)
    scope_freeze = _load_json_object(scope_path, label=scope_freeze_rel)
    if not proposal_snapshot_path.exists():
        raise ExecutorContractError(f"missing proposal snapshot: {proposal_snapshot_rel}")
    if not profile_path.exists():
        raise ExecutorContractError(
            f"missing agent profile: {report_path(artifact_root, profile_path)}"
        )
    profile = load_agent_profile(profile_path)
    return routing_report, scope_freeze, profile


def _codex_exec_argv(
    *,
    workspace_root: Path,
    artifact_root: Path,
    routing_report: dict[str, Any],
    output_last_message_rel: str,
) -> list[str]:
    sandbox_mode = routing_report["routing_decision"]["sandbox_mode"]
    argv = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--cd",
        str(workspace_root),
        "-m",
        routing_report["routing_decision"]["model"],
        "-c",
        f'model_reasoning_effort="{routing_report["routing_decision"]["reasoning_effort"]}"',
        "--output-schema",
        str(workspace_root / EXECUTOR_REPORT_SCHEMA),
        "-o",
        str(artifact_root / output_last_message_rel),
        "-",
    ]
    if sandbox_mode == "workspace-write":
        argv.insert(2, "--full-auto")
    else:
        argv[2:2] = ["-s", sandbox_mode]
    return argv


def _executor_artifacts(run_id: str, role: str) -> _ExecutorArtifacts:
    return _ExecutorArtifacts(
        output_last_message_rel=run_rel(run_id, f"{role}-last-message.json"),
        stdout_rel=run_rel(run_id, f"{role}.stdout.txt"),
        stderr_rel=run_rel(run_id, f"{role}.stderr.txt"),
        prompt_rel=run_rel(run_id, f"{role}-prompt.md"),
    )


def _persist_executor_streams(
    *,
    artifact_root: Path,
    artifacts: _ExecutorArtifacts,
    completed: object,
    sanitize_roots: list[Path],
) -> None:
    write_output_text(
        artifact_root / artifacts.stdout_rel,
        _sanitize_path_text(str(getattr(completed, "stdout", "")), roots=sanitize_roots),
    )
    write_output_text(
        artifact_root / artifacts.stderr_rel,
        _sanitize_path_text(str(getattr(completed, "stderr", "")), roots=sanitize_roots),
    )


def _read_model_output(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _summarize_execution(
    completed: object,
    model_output: dict[str, Any] | None,
    *,
    fallback_timeout_seconds: int,
) -> _ExecutionSummary:
    timed_out = _completed_timed_out(completed)
    timeout_seconds = _completed_timeout_seconds(completed, fallback=fallback_timeout_seconds)
    termination_reason = _completed_termination_reason(completed, timed_out=timed_out)
    decision = "ready"
    status = "pass"
    notes: list[str] = []
    returncode = int(getattr(completed, "returncode", 0))
    if returncode != 0:
        status = "fail"
        decision = "blocked"
        if timed_out:
            notes.append(f"codex exec timed out after {timeout_seconds} seconds")
        else:
            notes.append(f"codex exec exited with {returncode}")
            usage_limit_note = _codex_usage_limit_note(str(getattr(completed, "stderr", "")))
            if usage_limit_note:
                notes.append(usage_limit_note)
    elif isinstance(model_output, dict):
        returned_status = str(model_output.get("status", "pass"))
        if returned_status != "pass":
            status = "fail"
            decision = "blocked"
        diagnostics = model_output.get("diagnostics", {})
        returned_notes = diagnostics.get("notes", []) if isinstance(diagnostics, dict) else []
        if isinstance(returned_notes, list):
            notes.extend(str(item) for item in returned_notes if str(item).strip())
    return _ExecutionSummary(
        status=status,
        decision=decision,
        notes=notes,
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
        termination_reason=termination_reason,
    )


def _build_executor_report(
    *,
    run_id: str,
    role: str,
    routing_report: dict[str, Any],
    routing_report_rel: str,
    scope_freeze_rel: str,
    artifacts: _ExecutorArtifacts,
    sanitized_argv: list[str],
    completed: object,
    summary: _ExecutionSummary,
    context: RuntimeContext,
) -> ExecutorReportPayload:
    return {
        "$schema": EXECUTOR_REPORT_SCHEMA,
        "run_id": run_id,
        "role": role,
        "generated_at": context.isoformat_z(),
        "executor": {
            "name": "codex_exec",
            "sandbox_mode": routing_report["routing_decision"]["sandbox_mode"],
            "model": routing_report["routing_decision"]["model"],
            "reasoning_effort": routing_report["routing_decision"]["reasoning_effort"],
        },
        "status": summary.status,
        "command": {"argv": sanitized_argv},
        "artifacts": {
            "prompt": artifacts.prompt_rel,
            "output_last_message": artifacts.output_last_message_rel,
            "stdout": artifacts.stdout_rel,
            "stderr": artifacts.stderr_rel,
        },
        "result": {
            "returncode": _completed_returncode(completed),
            "timed_out": summary.timed_out,
            "timeout_seconds": summary.timeout_seconds,
            "termination_reason": summary.termination_reason,
            "launch_succeeded": _completed_launch_succeeded(completed),
            "signal_sent": _completed_signal_sent(completed),
            "final_state_observed": _completed_final_state_observed(completed),
            "stdout_received": _completed_stdout_received(completed),
            "stderr_received": _completed_stderr_received(completed),
            "heartbeat": _completed_heartbeat(completed),
        },
        "diagnostics": {
            "routing_report": routing_report_rel,
            "scope_freeze": scope_freeze_rel,
            "notes": summary.notes,
        },
    }


def _attach_timeout_failure(
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
) -> str:
    if not summary.timed_out:
        return ""
    run_id = str(report["run_id"])
    role = str(report["role"])
    timeout_failure_rel = write_timeout_failure_artifact(
        artifact_root,
        run_id,
        phase="executor",
        role=role,
        command={"argv": sanitized_argv},
        result={
            "returncode": _completed_returncode(completed),
            "timed_out": summary.timed_out,
            "timeout_seconds": summary.timeout_seconds,
            "termination_reason": summary.termination_reason,
            "launch_succeeded": _completed_launch_succeeded(completed),
            "signal_sent": _completed_signal_sent(completed),
            "final_state_observed": _completed_final_state_observed(completed),
            "stdout_received": _completed_stdout_received(completed),
            "stderr_received": _completed_stderr_received(completed),
        },
        artifacts={
            "prompt": artifacts.prompt_rel,
            "output_last_message": artifacts.output_last_message_rel,
            "stdout": artifacts.stdout_rel,
            "stderr": artifacts.stderr_rel,
            "routing_report": routing_report_rel,
            "scope_freeze": scope_freeze_rel,
        },
        context=context,
        diagnostics={"notes": summary.notes},
    )
    report["artifacts"]["timeout_failure"] = timeout_failure_rel
    return timeout_failure_rel


def _executor_ledger_event_type(role: str, status: str) -> tuple[str, str | None]:
    if status == "pass":
        return "executor_completed", None
    if role == "reviewer":
        return "review_blocked", "blocked"
    if role == "validator" or role.endswith("auditor"):
        return "validation_blocked", "blocked"
    return "executor_completed", "blocked"


def _write_executor_report_and_ledger(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    report: ExecutorReportPayload,
    routing_report_rel: str,
    scope_freeze_rel: str,
    prompt_rel: str,
    timeout_failure_rel: str,
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
    event_type, status_value = _executor_ledger_event_type(role, summary.status)
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


def _append_executor_runtime_event(
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
        duration_ms=int(round((time.monotonic() - started_at) * 1000)),
        run_id=run_id,
        policy_version=_read_policy_version(scope_freeze),
        proposal_id=str(scope_freeze.get("proposal_id", "")).strip(),
        decision_reason="executor_summary_decision",
    )


def build_execution_request(
    *,
    artifact_root: Path,
    workspace_root: Path,
    run_id: str,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    context: RuntimeContext,
    timeout_seconds: int,
) -> _ExecutionRequest:
    artifacts = _executor_artifacts(run_id, role)
    routing_report, scope_freeze, profile = _load_executor_inputs(
        artifact_root=artifact_root,
        role=role,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
    )
    argv = _codex_exec_argv(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
        routing_report=routing_report,
        output_last_message_rel=artifacts.output_last_message_rel,
    )
    sanitized_argv = _sanitize_argv(argv, roots=[artifact_root, workspace_root])
    prompt_path = _materialize_prompt(
        PromptMaterializationRequest(
            artifact_root=artifact_root,
            workspace_root=workspace_root,
            run_id=run_id,
            role=role,
            profile=profile,
            routing_report=routing_report,
            scope_freeze=scope_freeze,
            proposal_snapshot_rel=proposal_snapshot_rel,
            scope_freeze_rel=scope_freeze_rel,
            routing_report_rel=routing_report_rel,
            artifacts=artifacts,
            command_argv=argv,
            timeout_seconds=timeout_seconds,
            context=context,
        )
    )
    return _ExecutionRequest(
        artifact_root=artifact_root,
        workspace_root=workspace_root,
        run_id=run_id,
        role=role,
        routing_report=routing_report,
        scope_freeze=scope_freeze,
        profile=profile,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
        artifacts=artifacts,
        argv=argv,
        sanitized_argv=sanitized_argv,
        prompt_path=prompt_path,
        timeout_seconds=timeout_seconds,
    )


def launch_execution(request: _ExecutionRequest) -> object:
    return run_with_timeout(
        request.argv,
        cwd=request.workspace_root,
        input_text=request.prompt_path.read_text(encoding="utf-8"),
        timeout_seconds=request.timeout_seconds,
        heartbeat_interval_seconds=300,
    )


def capture_execution_artifacts(request: _ExecutionRequest, completed: object) -> dict[str, Any] | None:
    _persist_executor_streams(
        artifact_root=request.artifact_root,
        artifacts=request.artifacts,
        completed=completed,
        sanitize_roots=[request.artifact_root, request.workspace_root],
    )
    return _read_model_output(request.artifact_root / request.artifacts.output_last_message_rel)


def assess_execution_result(
    completed: object,
    model_output: dict[str, Any] | None,
    *,
    timeout_seconds: int,
) -> _ExecutionSummary:
    return _summarize_execution(
        completed,
        model_output,
        fallback_timeout_seconds=timeout_seconds,
    )


def persist_execution_outcome(
    *,
    request: _ExecutionRequest,
    completed: object,
    summary: _ExecutionSummary,
    started_at: float,
    context: RuntimeContext,
) -> ExecutorReportPayload:
    report = _build_executor_report(
        run_id=request.run_id,
        role=request.role,
        routing_report=request.routing_report,
        routing_report_rel=request.routing_report_rel,
        scope_freeze_rel=request.scope_freeze_rel,
        artifacts=request.artifacts,
        sanitized_argv=request.sanitized_argv,
        completed=completed,
        summary=summary,
        context=context,
    )
    timeout_failure_rel = _attach_timeout_failure(
        artifact_root=request.artifact_root,
        report=report,
        artifacts=request.artifacts,
        routing_report_rel=request.routing_report_rel,
        scope_freeze_rel=request.scope_freeze_rel,
        sanitized_argv=request.sanitized_argv,
        completed=completed,
        summary=summary,
        context=context,
    )
    _write_executor_report_and_ledger(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        report=report,
        routing_report_rel=request.routing_report_rel,
        scope_freeze_rel=request.scope_freeze_rel,
        prompt_rel=request.artifacts.prompt_rel,
        timeout_failure_rel=timeout_failure_rel,
        summary=summary,
        context=context,
    )
    _append_executor_runtime_event(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        summary=summary,
        started_at=started_at,
        scope_freeze=request.scope_freeze,
        context=context,
    )
    return report


def execute_codex_exec_role(
    *,
    artifact_root: Path,
    workspace_root: Path,
    run_id: str,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    context: RuntimeContext,
    timeout_seconds: int = DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS,
) -> ExecutorReportPayload:
    started_at = time.monotonic()
    request = build_execution_request(
        artifact_root=artifact_root,
        workspace_root=workspace_root,
        run_id=run_id,
        role=role,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
        context=context,
        timeout_seconds=timeout_seconds,
    )
    completed = launch_execution(request)
    model_output = capture_execution_artifacts(request, completed)
    summary = assess_execution_result(
        completed,
        model_output,
        timeout_seconds=timeout_seconds,
    )
    return persist_execution_outcome(
        request=request,
        completed=completed,
        summary=summary,
        started_at=started_at,
        context=context,
    )


def _read_policy_version(scope_freeze: dict[str, Any]) -> Any:
    policy = scope_freeze.get("policy")
    if isinstance(policy, dict):
        return policy.get("version", "")
    return ""
