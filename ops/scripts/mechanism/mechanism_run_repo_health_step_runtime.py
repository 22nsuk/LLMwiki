from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.schema_constants_runtime import (
    STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
)
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
COMPACT_ARTIFACT_FRESHNESS_OMITTED_SECTIONS = [
    "artifact_records",
    "owner_surface",
    "root_ephemeral_patterns",
    "root_ephemeral_artifacts",
    "run_log_placeholders",
    "non_utf8_text_artifacts",
]


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


def _json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _dict_child(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_child(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _artifact_freshness_report_blocks_repo_health(
    payload: dict[str, Any],
    *,
    repo_health_failed: bool,
) -> bool:
    if str(payload.get("status", "")).strip() == "fail":
        return True
    gate_effect = str(payload.get("gate_effect", "")).strip()
    return repo_health_failed and gate_effect in {"blocks_execution", "blocks_promotion"}


def _compact_artifact_freshness_report(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_kind": "repo_health_artifact_freshness_report_check_summary",
        "schema_version": 1,
        "preservation_mode": "compact_summary",
        "full_scan_preserved": False,
        "source_path": "tmp/artifact-freshness-report-check.json",
        "source_artifact_kind": str(payload.get("artifact_kind", "")).strip(),
        "generated_at": str(payload.get("generated_at", "")).strip(),
        "producer": str(payload.get("producer", "")).strip(),
        "source_command": str(payload.get("source_command", "")).strip(),
        "source_revision": str(payload.get("source_revision", "")).strip(),
        "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")).strip(),
        "status": str(payload.get("status", "")).strip(),
        "gate_effect": str(payload.get("gate_effect", "")).strip(),
        "recommended_next_action": str(payload.get("recommended_next_action", "")).strip(),
        "currentness": _dict_child(payload, "currentness"),
        "summary": _dict_child(payload, "summary"),
        "top_debt": _list_child(payload, "top_debt"),
        "top_debt_files": _list_child(payload, "top_debt_files"),
        "debt_queues": _list_child(payload, "debt_queues"),
        "omitted_sections": COMPACT_ARTIFACT_FRESHNESS_OMITTED_SECTIONS,
    }


def _write_artifact_freshness_diagnostic(
    source: Path,
    destination: Path,
    *,
    repo_health_failed: bool,
) -> None:
    payload = _json_object(source)
    if payload is None or _artifact_freshness_report_blocks_repo_health(
        payload,
        repo_health_failed=repo_health_failed,
    ):
        destination.write_bytes(source.read_bytes())
        return
    destination.write_text(
        json.dumps(_compact_artifact_freshness_report(payload), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _copy_repo_health_diagnostic_artifacts(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    repo_health_failed: bool,
) -> list[str]:
    copied: list[str] = []
    run_dir = vault / "runs" / run_id
    for source_rel, destination_name in REPO_HEALTH_DIAGNOSTIC_ARTIFACTS.items():
        source = workspace_vault / source_rel
        if not source.is_file():
            continue
        destination = run_dir / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination_name == "repo-health-artifact-freshness-report-check.json":
            _write_artifact_freshness_diagnostic(
                source,
                destination,
                repo_health_failed=repo_health_failed,
            )
        else:
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
        context=resolution.context,
    )
    command_execution = execute_command_step(
        command_request,
        dependencies=_command_execution_dependencies(dependencies),
    )
    repo_health_passed = command_execution.result["returncode"] == 0
    repo_health_timed_out = bool(command_execution.result.get("timed_out"))
    diagnostic_artifacts = _copy_repo_health_diagnostic_artifacts(
        vault,
        workspace_vault,
        run_id=run_id,
        repo_health_failed=not repo_health_passed,
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
