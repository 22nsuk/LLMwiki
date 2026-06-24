from __future__ import annotations

import subprocess

from ops.scripts.core.codex_exec_execution_types_runtime import (
    ExecutionRequest,
    ExecutionSummary,
    ExecutorDependencyPreflightPayload,
    SyntheticCompleted,
)
from ops.scripts.core.codex_exec_sanitize_runtime import _sanitize_path_text
from ops.scripts.core.codex_exec_workspace_runtime import (
    external_workspace_python_issue,
    workspace_virtualenv_python,
)
from ops.scripts.core.trusted_candidate_runner import (
    TrustedCandidateRunRequest,
    run_trusted_candidate_command,
)

from .codex_exec_dependency_preflight_runtime import (
    DEPENDENCY_PREFLIGHT_PYTHON_FLAGS,
    dependency_module_payloads,
    dependency_preflight_failure_summary,
    dependency_preflight_from_probe,
    dependency_preflight_payload,
    dependency_preflight_template,
    project_dependency_check_script,
    trusted_dependency_preflight_python,
    workspace_python_failure,
)


def non_worker_dependency_preflight(
    request: ExecutionRequest,
) -> tuple[ExecutorDependencyPreflightPayload, ExecutionSummary | None]:
    roots = [request.artifact_root, request.workspace_root]
    if request.role == "worker":
        return (
            dependency_preflight_template(request.role, request.workspace_root, roots),
            None,
        )
    workspace_python = workspace_virtualenv_python(request.workspace_root)
    if workspace_python is None:
        missing_python = request.workspace_root / ".venv" / "bin" / "python"
        python_display = _sanitize_path_text(str(missing_python), roots=roots)
        preflight = dependency_preflight_payload(
            role_requires_project_check=True,
            status="fail",
            python_path=python_display,
            python_executable="",
            python_version="",
            python_exists=False,
            required_modules=dependency_module_payloads(
                "not_checked",
                detail="missing workspace virtualenv python",
            ),
            returncode=127,
        )
        return (
            preflight,
            ExecutionSummary(
                status="fail",
                decision="blocked",
                notes=[
                    (
                        f"executor dependency preflight blocked {request.role}: "
                        "missing workspace virtualenv python at .venv/bin/python; "
                        "prepare an isolated workspace Python shim before "
                        "reviewer/validator/auditor execution"
                    )
                ],
                timed_out=False,
                timeout_seconds=request.timeout_seconds,
                termination_reason="completed",
            ),
        )

    workspace_python_issue = external_workspace_python_issue(
        request,
        workspace_python=workspace_python,
    )
    if workspace_python_issue:
        return workspace_python_failure(
            request=request,
            workspace_python=workspace_python,
            detail=workspace_python_issue,
        )

    trusted_python = trusted_dependency_preflight_python(request.artifact_root)
    command = [
        str(trusted_python),
        *DEPENDENCY_PREFLIGHT_PYTHON_FLAGS,
        "-c",
        project_dependency_check_script(),
    ]
    outcome = run_trusted_candidate_command(
        TrustedCandidateRunRequest(
            purpose="dependency_preflight",
            argv=command,
            workspace_root=request.workspace_root,
            trusted_vault_root=request.artifact_root,
            trusted_python=trusted_python,
            timeout_seconds=30,
            cwd=request.workspace_root,
            audit_rel_path=f"runs/{request.run_id}/{request.role}-dependency-preflight.audit.json",
        )
    )
    completed = subprocess.CompletedProcess(
        outcome.argv,
        outcome.returncode,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
    )
    if outcome.timed_out or outcome.returncode == 126:
        detail = (
            "dependency preflight timed out" if outcome.timed_out else completed.stderr
        )
        python_display = _sanitize_path_text(str(trusted_python), roots=roots)
        preflight = dependency_preflight_payload(
            role_requires_project_check=True,
            status="fail",
            python_path=python_display,
            python_executable="",
            python_version="",
            python_exists=True,
            required_modules=dependency_module_payloads("unknown", detail=detail),
            returncode=1,
        )
        return (
            preflight,
            ExecutionSummary(
                status="fail",
                decision="blocked",
                notes=[
                    (
                        f"executor dependency preflight blocked {request.role}: "
                        f"{python_display} could not execute required project dependency check; "
                        f"{detail}"
                    )
                ],
                timed_out=outcome.timed_out,
                timeout_seconds=request.timeout_seconds,
                termination_reason="completed",
            ),
        )
    preflight = dependency_preflight_from_probe(
        request,
        python_path=workspace_python,
        completed=completed,
    )
    return preflight, dependency_preflight_failure_summary(request, preflight)


def synthetic_preflight_completed(request: ExecutionRequest) -> SyntheticCompleted:
    return SyntheticCompleted(
        returncode=1,
        stdout="",
        stderr="",
        timed_out=False,
        timeout_seconds=request.timeout_seconds,
        termination_reason="completed",
        launch_succeeded=False,
        signal_sent="none",
        final_state_observed="preflight_blocked",
        stdout_received=False,
        stderr_received=False,
        heartbeat_count=0,
        heartbeat_interval_seconds=0,
        quiet_seconds=0,
        last_stdout_at="",
        last_stderr_at="",
        last_artifact_touch_at="",
        observation_mode="communicate",
    )
