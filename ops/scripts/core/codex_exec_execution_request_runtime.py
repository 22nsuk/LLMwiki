from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .codex_exec_execution_types_runtime import (
    ExecutorContractError,
    PromptMaterializationRequest,
    _ExecutionRequest,
    _ExecutorArtifacts,
)
from .codex_exec_prompt_runtime import load_agent_profile, materialize_prompt
from .codex_exec_sanitize_runtime import (
    _display_command_argv,
    _sanitize_argv,
)
from .codex_exec_workspace_runtime import (
    resolve_codex_executable,
    same_path,
)
from .command_log_summary_runtime import (
    command_log_summary_rel,
    command_log_trace_rel,
)
from .experiment_telemetry_runtime import run_rel
from .policy_runtime import report_path
from .runtime_context import RuntimeContext
from .schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH

EXECUTOR_REPORT_SCHEMA = EXECUTOR_REPORT_SCHEMA_PATH


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutorContractError(f"unable to load {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExecutorContractError(f"{label} root must be an object")
    return payload


def _load_optional_json_object(path: Path, *, label: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_object(path, label=label)


def load_executor_inputs(
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
        raise ExecutorContractError(
            f"missing proposal snapshot: {proposal_snapshot_rel}"
        )
    if not profile_path.exists():
        raise ExecutorContractError(
            f"missing agent profile: {report_path(artifact_root, profile_path)}"
        )
    profile = load_agent_profile(profile_path)
    return (routing_report, scope_freeze, profile)


def codex_exec_argv(
    *,
    workspace_root: Path,
    routing_report: dict[str, Any],
    output_last_message_rel: str,
) -> list[str]:
    sandbox_mode = routing_report["routing_decision"]["sandbox_mode"]
    argv = [
        resolve_codex_executable(workspace_root),
        "exec",
        "--cd",
        str(workspace_root),
        "-m",
        routing_report["routing_decision"]["model"],
        "-c",
        f'''model_reasoning_effort="{routing_report["routing_decision"]["reasoning_effort"]}"''',
        "--output-schema",
        str(workspace_root / EXECUTOR_REPORT_SCHEMA),
        "-o",
        str(workspace_root / output_last_message_rel),
        "-",
    ]
    if sandbox_mode == "workspace-write":
        argv.insert(2, "--full-auto")
        argv.insert(3, "--skip-git-repo-check")
    else:
        argv[2:2] = ["-s", sandbox_mode, "--skip-git-repo-check"]
    return argv


def executor_artifacts(run_id: str, role: str) -> _ExecutorArtifacts:
    return _ExecutorArtifacts(
        output_last_message_rel=run_rel(run_id, f"{role}-last-message.json"),
        stdout_rel=command_log_trace_rel(run_id, role, "stdout"),
        stderr_rel=command_log_trace_rel(run_id, role, "stderr"),
        raw_stdout_rel=run_rel(run_id, f"{role}.stdout.txt"),
        raw_stderr_rel=run_rel(run_id, f"{role}.stderr.txt"),
        command_log_summary_rel=command_log_summary_rel(run_id),
        prompt_rel=run_rel(run_id, f"{role}-prompt.md"),
    )


def _model_output_path(root: Path, artifacts: _ExecutorArtifacts) -> Path:
    return root / artifacts.output_last_message_rel


def _clear_stale_model_output(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() and (not path.is_symlink()):
        return
    if path.is_dir() and (not path.is_symlink()):
        raise ExecutorContractError(f"model output path is a directory: {path.name}")
    path.unlink()


def clear_stale_model_outputs(
    *, artifact_root: Path, workspace_root: Path, artifacts: _ExecutorArtifacts
) -> None:
    workspace_output = _model_output_path(workspace_root, artifacts)
    artifact_output = _model_output_path(artifact_root, artifacts)
    _clear_stale_model_output(workspace_output)
    if not same_path(workspace_output, artifact_output):
        _clear_stale_model_output(artifact_output)


def build_execution_request(
    *,
    artifact_root: Path,
    workspace_root: Path,
    run_id: str,
    role: str,
    routing_report_rel: str,
    scope_freeze_rel: str,
    proposal_snapshot_rel: str,
    repair_context_rel: str = "",
    context: RuntimeContext,
    timeout_seconds: int,
) -> _ExecutionRequest:
    artifacts = executor_artifacts(run_id, role)
    routing_report, scope_freeze, profile = load_executor_inputs(
        artifact_root=artifact_root,
        role=role,
        routing_report_rel=routing_report_rel,
        scope_freeze_rel=scope_freeze_rel,
        proposal_snapshot_rel=proposal_snapshot_rel,
    )
    repair_context = (
        _load_optional_json_object(
            artifact_root / repair_context_rel, label=repair_context_rel
        )
        if repair_context_rel
        else None
    )
    argv = codex_exec_argv(
        workspace_root=workspace_root,
        routing_report=routing_report,
        output_last_message_rel=artifacts.output_last_message_rel,
    )
    clear_stale_model_outputs(
        artifact_root=artifact_root, workspace_root=workspace_root, artifacts=artifacts
    )
    sanitized_argv = _sanitize_argv(
        _display_command_argv(argv), roots=[artifact_root, workspace_root]
    )
    prompt_path = materialize_prompt(
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
            repair_context_rel=repair_context_rel,
            repair_context=repair_context,
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
        repair_context_rel=repair_context_rel,
        repair_context=repair_context,
        artifacts=artifacts,
        argv=argv,
        sanitized_argv=sanitized_argv,
        prompt_path=prompt_path,
        timeout_seconds=timeout_seconds,
        context=context,
    )
