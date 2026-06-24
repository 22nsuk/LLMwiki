from __future__ import annotations

from .codex_exec_execution_types_runtime import (
    ExecutorDependencyPreflightPayload,
    ExecutorReportPayload,
    ExecutorReportRequest,
    _ExecutionRequest,
    _ExecutionSummary,
)
from .codex_exec_report_runtime import (
    append_executor_runtime_event,
    attach_timeout_failure,
    build_executor_report,
    write_executor_report_and_ledger,
)
from .codex_exec_workspace_runtime import execution_env
from .command_runtime import run_with_timeout
from .runtime_context import RuntimeContext


def launch_execution(request: _ExecutionRequest) -> object:
    return run_with_timeout(
        request.argv,
        cwd=request.workspace_root,
        input_text=request.prompt_path.read_text(encoding="utf-8"),
        timeout_seconds=request.timeout_seconds,
        env=execution_env(request.workspace_root),
    )


def persist_execution_outcome(
    *,
    request: _ExecutionRequest,
    completed: object,
    summary: _ExecutionSummary,
    dependency_preflight: ExecutorDependencyPreflightPayload,
    started_at: float,
    context: RuntimeContext,
) -> ExecutorReportPayload:
    report = build_executor_report(
        ExecutorReportRequest(
            run_id=request.run_id,
            role=request.role,
            scope_freeze=request.scope_freeze,
            routing_report=request.routing_report,
            routing_report_rel=request.routing_report_rel,
            scope_freeze_rel=request.scope_freeze_rel,
            artifacts=request.artifacts,
            sanitized_argv=request.sanitized_argv,
            completed=completed,
            summary=summary,
            dependency_preflight=dependency_preflight,
            context=context,
        )
    )
    timeout_failure_rel = attach_timeout_failure(
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
    write_executor_report_and_ledger(
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
    append_executor_runtime_event(
        artifact_root=request.artifact_root,
        run_id=request.run_id,
        role=request.role,
        summary=summary,
        started_at=started_at,
        scope_freeze=request.scope_freeze,
        context=context,
    )
    return report
