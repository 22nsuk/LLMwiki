from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.artifact_io_runtime import write_vault_schema_validated_json
from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.run_artifact_envelope_runtime import (
    maybe_embed_run_artifact_envelope,
)
from ops.scripts.core.runtime_context import RuntimeContext


class RunMechanismExperimentError(Exception):
    exit_code = 8


class RunMechanismExperimentUsageError(RunMechanismExperimentError):
    exit_code = 2


class RunMechanismExperimentPolicyError(RunMechanismExperimentError):
    exit_code = 3


class RunMechanismExperimentArtifactError(RunMechanismExperimentError):
    exit_code = 4


class RunMechanismExperimentMutationError(RunMechanismExperimentError):
    exit_code = 5


class RunMechanismExperimentWriteError(RunMechanismExperimentError):
    exit_code = 7


@dataclass(frozen=True)
class CommandSpec:
    command: str
    argv: list[str]
    timeout_seconds: int


@dataclass(frozen=True)
class ExperimentResolution:
    policy: dict
    resolved_policy_path: Path
    policy_path_text: str
    context: RuntimeContext
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]
    proposal: dict | None
    proposal_source_report: str | None
    log_summary: str
    mutation_command_spec: CommandSpec | None
    check_command_spec: CommandSpec | None
    scope_freeze_path: str
    routing_report_paths: list[str]
    executor_report_paths: list[str]


@dataclass(frozen=True)
class ScaffoldedRun:
    run_dir: Path
    proposal_snapshot: str


@dataclass(frozen=True)
class CommandStepResult:
    result: dict
    logs: list[str]


@dataclass(frozen=True)
class CommandExecutionDependencies:
    command_argv: Callable[..., list[str]]
    run_command: Callable[..., dict]
    write_command_logs: Callable[..., list[str]]
    write_timeout_failure_artifact: Callable[..., str]
    sanitize_path_text: Callable[..., str]


@dataclass(frozen=True)
class CommandExecutionRequest:
    vault: Path
    workspace_vault: Path
    run_id: str
    log_name: str
    command_spec: CommandSpec
    context: RuntimeContext


@dataclass(frozen=True)
class CommandExecutionResult:
    argv: list[str]
    result: dict
    logs: list[str]


@dataclass(frozen=True)
class RepoHealthStepResult:
    result: dict
    logs: list[str]
    changed_files_manifest: str
    structural_complexity_budget: str
    structural_complexity_budget_status: str
    behavior_delta: str
    passed: bool
    failure_taxonomy: str = ""


@dataclass(frozen=True)
class PromotionStepResult:
    report_path: Path
    report: dict


@dataclass(frozen=True)
class WorkspacePreparation:
    workspace_vault: Path
    baseline_file_digests: dict[str, str]
    telemetry: dict


@dataclass(frozen=True)
class FinalizeStepResult:
    finalized: bool
    finalize_result: dict


@dataclass(frozen=True)
class WorkspaceApplyResult:
    apply_mode: str
    apply_status: str
    live_applied: bool
    shadow_apply_report: str
    rollback_rehearsal_report: str


@dataclass(frozen=True)
class CompletedRunSteps:
    mutation_step: CommandStepResult
    generated_artifact_convergence: dict
    repo_health: RepoHealthStepResult
    promotion: PromotionStepResult
    finalize_step: FinalizeStepResult
    workspace_apply: WorkspaceApplyResult
    workspace_preparation: dict
    candidate_changed_files_snapshot: str


def timestamp(context: RuntimeContext | None = None) -> str:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    return runtime_context.isoformat_z()


def load_current_policy(vault: Path, policy_path: str | None) -> tuple[dict, Path]:
    try:
        return load_policy(vault, policy_path)
    except FileNotFoundError as exc:
        missing_path = policy_path or "ops/policies/wiki-maintainer-policy.yaml"
        raise RunMechanismExperimentPolicyError(f"missing policy: {missing_path}") from exc
    except ValueError as exc:
        raise RunMechanismExperimentPolicyError(str(exc)) from exc


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunMechanismExperimentArtifactError(f"missing artifact: {path.as_posix()}") from exc
    except json.JSONDecodeError as exc:
        raise RunMechanismExperimentArtifactError(
            f"invalid json in {path.as_posix()}: line {exc.lineno} column {exc.colno}"
        ) from exc


def sanitize_root_strings(*roots: Path) -> list[str]:
    normalized: list[str] = []
    for root in roots:
        try:
            root_text = root.resolve().as_posix().rstrip("/")
        except OSError:
            root_text = root.as_posix().rstrip("/")
        if not root_text or root_text in normalized:
            continue
        normalized.append(root_text)
    normalized.sort(key=len, reverse=True)
    return normalized


def sanitize_path_text(text: str, *, roots: list[Path]) -> str:
    sanitized = text.replace("\\", "/")
    for root_text in sanitize_root_strings(*roots):
        sanitized = sanitized.replace(f"{root_text}/", "")
        sanitized = sanitized.replace(root_text, ".")
    return sanitized


def sanitize_payload(value: object, *, roots: list[Path]) -> object:
    if isinstance(value, str):
        return sanitize_path_text(value, roots=roots)
    if isinstance(value, list):
        return [sanitize_payload(item, roots=roots) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_payload(item, roots=roots) for key, item in value.items()}
    return value


def write_json(vault: Path, rel_path: str, payload: dict, schema_rel_path: str) -> None:
    try:
        payload = maybe_embed_run_artifact_envelope(
            vault,
            rel_path,
            payload,
            schema_path=schema_rel_path,
        )
        write_vault_schema_validated_json(
            vault,
            rel_path,
            payload,
            schema_rel_path,
            context=f"schema validation failed for {rel_path}",
        )
    except FileNotFoundError as exc:
        raise RunMechanismExperimentArtifactError(f"missing schema: {schema_rel_path}") from exc
    except ValueError as exc:
        raise RunMechanismExperimentArtifactError(str(exc)) from exc
    except OSError as exc:
        raise RunMechanismExperimentWriteError(str(exc)) from exc


def require_prepared_command(command_spec: CommandSpec | None) -> CommandSpec:
    if command_spec is None:
        raise RunMechanismExperimentUsageError(
            "execution commands were not prepared for a full mechanism run"
        )
    return command_spec


def execute_command_step(
    request: CommandExecutionRequest,
    *,
    dependencies: CommandExecutionDependencies,
) -> CommandExecutionResult:
    argv = dependencies.command_argv(request.command_spec.command, cwd=request.workspace_vault)
    command_result = dependencies.run_command(
        request.command_spec.command,
        cwd=request.workspace_vault,
        argv=argv,
        timeout_seconds=request.command_spec.timeout_seconds,
    )
    sanitized_result = dict(command_result)
    sanitized_result["stdout"] = dependencies.sanitize_path_text(
        command_result["stdout"],
        roots=[request.workspace_vault, request.vault],
    )
    sanitized_result["stderr"] = dependencies.sanitize_path_text(
        command_result["stderr"],
        roots=[request.workspace_vault, request.vault],
    )
    logs = dependencies.write_command_logs(
        request.vault,
        request.run_id,
        request.log_name,
        sanitized_result,
        context=request.context,
    )
    return CommandExecutionResult(argv=argv, result=sanitized_result, logs=logs)


def write_command_timeout_failure(
    request: CommandExecutionRequest,
    *,
    execution: CommandExecutionResult,
    phase: str,
    scope_freeze_path: str,
    context: RuntimeContext,
    artifacts: dict[str, str],
    note: str,
    dependencies: CommandExecutionDependencies,
) -> str:
    return dependencies.write_timeout_failure_artifact(
        request.vault,
        request.run_id,
        phase=phase,
        command={
            "command": dependencies.sanitize_path_text(
                request.command_spec.command,
                roots=[request.workspace_vault, request.vault],
            ),
            "argv": [
                dependencies.sanitize_path_text(item, roots=[request.workspace_vault, request.vault])
                for item in execution.argv
            ],
        },
        result=execution.result,
        artifacts={
            "stdout": execution.logs[0],
            "stderr": execution.logs[1],
            "scope_freeze": scope_freeze_path,
            **artifacts,
        },
        context=context,
        diagnostics={"notes": [note]},
    )
