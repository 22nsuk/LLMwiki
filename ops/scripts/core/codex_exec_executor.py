from __future__ import annotations

import time
from pathlib import Path

from .codex_exec_dependency_preflight_decision_runtime import (
    non_worker_dependency_preflight as _non_worker_dependency_preflight,
    synthetic_preflight_completed as _synthetic_preflight_completed,
)
from .codex_exec_execution_outcome_runtime import (
    launch_execution,
    persist_execution_outcome,
)
from .codex_exec_execution_request_runtime import (
    build_execution_request,
    codex_exec_argv as _codex_exec_argv,
)
from .codex_exec_execution_result_runtime import (
    assess_execution_result,
    capture_execution_artifacts,
    persist_executor_streams,
)
from .codex_exec_execution_types_runtime import (
    CodexExecError,
    ExecutorContractError,
    ExecutorReportPayload,
    ExecutorReportRequest,
    _ExecutionSummary,
    _ExecutorArtifacts,
    _SyntheticCompleted,
)
from .codex_exec_integrity_runtime import (
    _apply_non_worker_integrity_guard,
    _workspace_integrity_digests,
)
from .codex_exec_prompt_runtime import load_agent_profile
from .codex_exec_report_runtime import build_executor_report as _build_executor_report
from .codex_exec_workspace_runtime import (
    expected_external_workspace_python_shim as _expected_external_workspace_python_shim,
)
from .runtime_context import RuntimeContext

DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS = 1800


def execute_codex_exec_role(
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
        repair_context_rel=repair_context_rel,
        context=context,
        timeout_seconds=timeout_seconds,
    )
    dependency_preflight, preflight_summary = _non_worker_dependency_preflight(request)
    if preflight_summary is not None:
        preflight_completed = _synthetic_preflight_completed(request)
        persist_executor_streams(
            artifact_root=request.artifact_root,
            run_id=request.run_id,
            role=request.role,
            artifacts=request.artifacts,
            completed=preflight_completed,
            sanitize_roots=[request.artifact_root, request.workspace_root],
            context=context,
            sanitized_argv=request.sanitized_argv,
        )
        return persist_execution_outcome(
            request=request,
            completed=preflight_completed,
            summary=preflight_summary,
            dependency_preflight=dependency_preflight,
            started_at=started_at,
            context=context,
        )
    integrity_before = (
        _workspace_integrity_digests(request.workspace_root, run_id=request.run_id)
        if role != "worker"
        else None
    )
    completed = launch_execution(request)
    model_output = capture_execution_artifacts(request, completed)
    summary = assess_execution_result(
        completed, model_output, timeout_seconds=timeout_seconds
    )
    integrity_after = (
        _workspace_integrity_digests(request.workspace_root, run_id=request.run_id)
        if role != "worker"
        else None
    )
    summary = _apply_non_worker_integrity_guard(
        summary, role=role, before=integrity_before, after=integrity_after
    )
    return persist_execution_outcome(
        request=request,
        completed=completed,
        summary=summary,
        dependency_preflight=dependency_preflight,
        started_at=started_at,
        context=context,
    )


_EXECUTOR_REEXPORTS = (
    CodexExecError,
    ExecutorContractError,
    ExecutorReportRequest,
    _ExecutionSummary,
    _ExecutorArtifacts,
    _SyntheticCompleted,
    _build_executor_report,
    _codex_exec_argv,
    _expected_external_workspace_python_shim,
    assess_execution_result,
    build_execution_request,
    capture_execution_artifacts,
    load_agent_profile,
    persist_execution_outcome,
)
