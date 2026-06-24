from __future__ import annotations

import re
from pathlib import Path

from .codex_exec_execution_types_runtime import (
    _ExecutionRequest,
    _ExecutionSummary,
    _ExecutorArtifacts,
)
from .codex_exec_model_output_runtime import (
    ModelOutputRead,
    read_model_output,
    validate_model_output_contract,
)
from .codex_exec_report_runtime import (
    completed_returncode,
    completed_termination_reason,
    completed_timed_out,
    completed_timeout_seconds,
)
from .codex_exec_sanitize_runtime import _sanitize_path_text
from .codex_exec_workspace_runtime import same_path
from .command_log_summary_runtime import write_command_log_summary
from .output_runtime import write_output_text
from .runtime_context import RuntimeContext

_CODEX_USAGE_LIMIT_RE = re.compile(
    "(usage limit|try again at|upgrade to pro)", flags=re.IGNORECASE
)
_CODEX_USAGE_LIMIT_RETRY_RE = re.compile(
    "try again at\\s+([^.\\n\\r]+)", flags=re.IGNORECASE
)


def _codex_usage_limit_note(stderr: str) -> str:
    if not _CODEX_USAGE_LIMIT_RE.search(stderr):
        return ""
    match = _CODEX_USAGE_LIMIT_RETRY_RE.search(stderr)
    if match:
        return (
            f"codex exec blocked by usage limit; retry_after={match.group(1).strip()}"
        )
    return "codex exec blocked by usage limit"


def _model_output_path(root: Path, artifacts: _ExecutorArtifacts) -> Path:
    return root / artifacts.output_last_message_rel


def persist_executor_streams(
    *,
    artifact_root: Path,
    run_id: str,
    role: str,
    artifacts: _ExecutorArtifacts,
    completed: object,
    sanitize_roots: list[Path],
    context: RuntimeContext,
    sanitized_argv: list[str],
) -> None:
    stdout = _sanitize_path_text(
        str(getattr(completed, "stdout", "")), roots=sanitize_roots
    )
    stderr = _sanitize_path_text(
        str(getattr(completed, "stderr", "")), roots=sanitize_roots
    )
    write_output_text(artifact_root / artifacts.raw_stdout_rel, stdout)
    write_output_text(artifact_root / artifacts.raw_stderr_rel, stderr)
    write_command_log_summary(
        artifact_root,
        run_id,
        role,
        {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": completed_returncode(completed),
            "timed_out": completed_timed_out(completed),
            "timeout_seconds": completed_timeout_seconds(completed, fallback=0),
            "termination_reason": completed_termination_reason(
                completed, timed_out=completed_timed_out(completed)
            ),
        },
        raw_paths={
            "stdout": artifacts.raw_stdout_rel,
            "stderr": artifacts.raw_stderr_rel,
        },
        context=context,
        command_argv=sanitized_argv,
    )


def capture_execution_artifacts(
    request: _ExecutionRequest, completed: object
) -> ModelOutputRead:
    persist_executor_streams(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        artifacts=request.artifacts,
        completed=completed,
        sanitize_roots=[request.artifact_root, request.workspace_root],
        context=request.context,
        sanitized_argv=request.sanitized_argv,
    )
    workspace_output = _model_output_path(request.workspace_root, request.artifacts)
    artifact_output = _model_output_path(request.artifact_root, request.artifacts)
    model_output = read_model_output(workspace_output)
    if model_output.raw_bytes is not None and (
        not same_path(workspace_output, artifact_output)
    ):
        artifact_output.parent.mkdir(parents=True, exist_ok=True)
        artifact_output.write_bytes(model_output.raw_bytes)
    return validate_model_output_contract(model_output, request=request)


def summarize_execution(
    completed: object, model_output: ModelOutputRead, *, fallback_timeout_seconds: int
) -> _ExecutionSummary:
    timed_out = completed_timed_out(completed)
    timeout_seconds = completed_timeout_seconds(
        completed, fallback=fallback_timeout_seconds
    )
    termination_reason = completed_termination_reason(completed, timed_out=timed_out)
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
        usage_limit_note = _codex_usage_limit_note(
            str(getattr(completed, "stderr", ""))
        )
        if usage_limit_note:
            notes.append(usage_limit_note)
    elif model_output.payload is None:
        status = "fail"
        decision = "blocked"
        notes.append(model_output.note)
    else:
        if "status" not in model_output.payload:
            status = "fail"
            decision = "blocked"
            notes.append("codex exec model output omitted required status field")
        returned_status = str(model_output.payload.get("status", "")).strip()
        if returned_status != "pass":
            status = "fail"
            decision = "blocked"
        diagnostics = model_output.payload.get("diagnostics", {})
        returned_notes = (
            diagnostics.get("notes", []) if isinstance(diagnostics, dict) else []
        )
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


def assess_execution_result(
    completed: object, model_output: ModelOutputRead, *, timeout_seconds: int
) -> _ExecutionSummary:
    return summarize_execution(
        completed, model_output, fallback_timeout_seconds=timeout_seconds
    )
