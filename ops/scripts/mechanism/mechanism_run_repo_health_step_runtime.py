from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .mechanism_run_common_runtime import (
    CommandExecutionDependencies,
    CommandExecutionRequest,
    ExperimentResolution,
    RepoHealthStepResult,
    execute_command_step,
    require_prepared_command,
    write_command_timeout_failure,
)


REPO_HEALTH_DIAGNOSTIC_ARTIFACTS = {
    "tmp/artifact-freshness-report-check.json": "repo-health-artifact-freshness-report-check.json",
}


@dataclass(frozen=True)
class RepoHealthStepDependencies:
    command_argv: Callable[..., list[str]]
    run_command: Callable[..., dict]
    write_command_logs: Callable[..., list[str]]
    write_timeout_failure_artifact: Callable[..., str]
    append_ledger_event: Callable[..., None]
    write_changed_files_manifest: Callable[..., str]
    write_behavior_delta_artifact: Callable[..., str]
    sanitize_path_text: Callable[..., str]


def _command_execution_dependencies(
    dependencies: RepoHealthStepDependencies,
) -> CommandExecutionDependencies:
    return CommandExecutionDependencies(
        command_argv=dependencies.command_argv,
        run_command=dependencies.run_command,
        write_command_logs=dependencies.write_command_logs,
        write_timeout_failure_artifact=dependencies.write_timeout_failure_artifact,
        sanitize_path_text=dependencies.sanitize_path_text,
    )


def _copy_repo_health_diagnostic_artifacts(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
) -> list[str]:
    copied: list[str] = []
    run_dir = vault / "runs" / run_id
    for source_rel, destination_name in REPO_HEALTH_DIAGNOSTIC_ARTIFACTS.items():
        source = workspace_vault / source_rel
        if not source.is_file():
            continue
        destination = run_dir / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.append(f"runs/{run_id}/{destination_name}")
    return copied


def repo_health_step(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    baseline_file_digests: dict[str, str],
    dependencies: RepoHealthStepDependencies,
    diff_model: str = "full_workspace",
) -> RepoHealthStepResult:
    command_spec = require_prepared_command(resolution.check_command_spec)
    command_request = CommandExecutionRequest(
        vault=vault,
        workspace_vault=workspace_vault,
        run_id=run_id,
        log_name="repo-health",
        command_spec=command_spec,
    )
    command_execution = execute_command_step(
        command_request,
        dependencies=_command_execution_dependencies(dependencies),
    )
    diagnostic_artifacts = _copy_repo_health_diagnostic_artifacts(
        vault,
        workspace_vault,
        run_id=run_id,
    )
    changed_files_manifest = dependencies.write_changed_files_manifest(
        vault,
        workspace_vault,
        run_id=run_id,
        primary_targets=resolution.primary_targets,
        supporting_targets=resolution.supporting_targets,
        test_files=resolution.test_files,
        baseline_file_digests=baseline_file_digests,
        diff_model=diff_model,
        context=resolution.context,
    )
    behavior_delta = dependencies.write_behavior_delta_artifact(
        vault,
        workspace_vault,
        run_id=run_id,
        resolution=resolution,
        changed_files_manifest=changed_files_manifest,
    )
    repo_health_passed = command_execution.result["returncode"] == 0
    repo_health_timed_out = bool(command_execution.result.get("timed_out"))
    timeout_failure_rel = ""
    if repo_health_timed_out:
        timeout_failure_rel = write_command_timeout_failure(
            command_request,
            execution=command_execution,
            phase="repo_health",
            scope_freeze_path=resolution.scope_freeze_path,
            context=resolution.context,
            artifacts={
                "changed_files_manifest": changed_files_manifest,
                "behavior_delta": behavior_delta,
            },
            note=(
                "repo health command timed out after "
                f"{command_execution.result['timeout_seconds']} seconds"
            ),
            dependencies=_command_execution_dependencies(dependencies),
        )
    dependencies.append_ledger_event(
        vault,
        run_id,
        event_type="repo_health_checked",
        summary=(
            "Repo health command timed out before promotion evaluation."
            if repo_health_timed_out
            else (
                "Repo health command passed before promotion evaluation."
                if repo_health_passed
                else "Repo health command failed; promotion evaluation was skipped."
            )
        ),
        artifacts=[
            *command_execution.logs,
            *diagnostic_artifacts,
            changed_files_manifest,
            behavior_delta,
            *([timeout_failure_rel] if timeout_failure_rel else []),
        ],
        decision=(
            "repo_health_timeout"
            if repo_health_timed_out
            else ("repo_health_pass" if repo_health_passed else "repo_health_fail")
        ),
        context=resolution.context,
        status="running" if repo_health_passed else "blocked",
    )
    return RepoHealthStepResult(
        result=command_execution.result,
        logs=command_execution.logs,
        changed_files_manifest=changed_files_manifest,
        behavior_delta=behavior_delta,
        passed=repo_health_passed,
    )
