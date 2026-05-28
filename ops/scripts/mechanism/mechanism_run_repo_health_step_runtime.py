from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.schema_constants_runtime import STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH
from ops.scripts.structural_complexity_budget_runtime import (
    DEFAULT_TARGET_PROFILES,
    build_report as build_structural_complexity_budget_report,
    target_paths_from_changed_files_manifest,
    touched_target_profiles,
)

from .mechanism_run_common_runtime import (
    CommandExecutionDependencies,
    CommandExecutionRequest,
    ExperimentResolution,
    RepoHealthStepResult,
    execute_command_step,
    require_prepared_command,
    write_command_timeout_failure,
    write_json,
)

REPO_HEALTH_DIAGNOSTIC_ARTIFACTS = {
    "tmp/artifact-freshness-report-check.json": "repo-health-artifact-freshness-report-check.json",
}
STRUCTURAL_COMPLEXITY_BUDGET_RUN_ARTIFACT = "structural-complexity-budget.json"


@dataclass(frozen=True)
class StructuralComplexityBudgetStepResult:
    report_path: str
    status: str


@dataclass(frozen=True)
class RepoHealthStepDependencies:
    command_argv: Callable[..., list[str]]
    run_command: Callable[..., dict]
    write_command_logs: Callable[..., list[str]]
    write_timeout_failure_artifact: Callable[..., str]
    append_ledger_event: Callable[..., None]
    write_changed_files_manifest: Callable[..., str]
    write_structural_complexity_budget_artifact: Callable[..., StructuralComplexityBudgetStepResult]
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


def write_structural_complexity_budget_artifact(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    changed_files_manifest: str,
) -> StructuralComplexityBudgetStepResult:
    target_paths = target_paths_from_changed_files_manifest(vault, changed_files_manifest)
    report = build_structural_complexity_budget_report(
        workspace_vault,
        policy_path=resolution.policy_path_text,
        context=resolution.context,
        target_profiles=touched_target_profiles(DEFAULT_TARGET_PROFILES, target_paths),
    )
    rel_path = f"runs/{run_id}/{STRUCTURAL_COMPLEXITY_BUDGET_RUN_ARTIFACT}"
    write_json(vault, rel_path, report, STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH)
    return StructuralComplexityBudgetStepResult(
        report_path=rel_path,
        status=str(report.get("status", "")).strip(),
    )


def _repo_health_decision(
    *,
    repo_health_passed: bool,
    repo_health_timed_out: bool,
    structural_complexity_budget_status: str,
) -> str:
    if repo_health_timed_out:
        return "repo_health_timeout"
    if not repo_health_passed:
        return "repo_health_fail"
    if structural_complexity_budget_status != "pass":
        return "structural_complexity_non_regression"
    return "repo_health_pass"


def _repo_health_summary(
    *,
    repo_health_passed: bool,
    repo_health_timed_out: bool,
    structural_complexity_budget_status: str,
) -> str:
    if repo_health_timed_out:
        return "Repo health command timed out before promotion evaluation."
    if not repo_health_passed:
        return "Repo health command failed; promotion evaluation was skipped."
    if structural_complexity_budget_status != "pass":
        observed_status = structural_complexity_budget_status or "unknown"
        return (
            "Structural complexity budget reported "
            f"{observed_status} after repo health passed; promotion evaluation was skipped."
        )
    return "Repo health command and post-worker structural complexity budget passed before promotion evaluation."


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
    structural_complexity_budget = dependencies.write_structural_complexity_budget_artifact(
        vault,
        workspace_vault,
        run_id=run_id,
        resolution=resolution,
        changed_files_manifest=changed_files_manifest,
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
    structural_complexity_budget_status = structural_complexity_budget.status
    structural_complexity_budget_passed = structural_complexity_budget_status == "pass"
    passed = repo_health_passed and structural_complexity_budget_passed
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
                "structural_complexity_budget": structural_complexity_budget.report_path,
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
        summary=_repo_health_summary(
            repo_health_passed=repo_health_passed,
            repo_health_timed_out=repo_health_timed_out,
            structural_complexity_budget_status=structural_complexity_budget_status,
        ),
        artifacts=[
            *command_execution.logs,
            *diagnostic_artifacts,
            changed_files_manifest,
            structural_complexity_budget.report_path,
            behavior_delta,
            *([timeout_failure_rel] if timeout_failure_rel else []),
        ],
        decision=_repo_health_decision(
            repo_health_passed=repo_health_passed,
            repo_health_timed_out=repo_health_timed_out,
            structural_complexity_budget_status=structural_complexity_budget_status,
        ),
        context=resolution.context,
        status="running" if passed else "blocked",
    )
    return RepoHealthStepResult(
        result=command_execution.result,
        logs=command_execution.logs,
        changed_files_manifest=changed_files_manifest,
        structural_complexity_budget=structural_complexity_budget.report_path,
        structural_complexity_budget_status=structural_complexity_budget_status,
        behavior_delta=behavior_delta,
        passed=passed,
    )
