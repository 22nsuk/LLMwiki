from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .mechanism_run_common_runtime import (
    CommandExecutionDependencies,
    CommandExecutionRequest,
    CommandStepResult,
    ExperimentResolution,
    RunMechanismExperimentMutationError,
    execute_command_step,
    require_prepared_command,
    write_command_timeout_failure,
)


@dataclass(frozen=True)
class MutationStepDependencies:
    command_argv: Callable[..., list[str]]
    run_command: Callable[..., dict]
    write_command_logs: Callable[..., list[str]]
    write_timeout_failure_artifact: Callable[..., str]
    append_ledger_event: Callable[..., None]
    write_experiment_telemetry: Callable[..., str]
    sanitize_path_text: Callable[..., str]


def _command_execution_dependencies(
    dependencies: MutationStepDependencies,
) -> CommandExecutionDependencies:
    return CommandExecutionDependencies(
        command_argv=dependencies.command_argv,
        run_command=dependencies.run_command,
        write_command_logs=dependencies.write_command_logs,
        write_timeout_failure_artifact=dependencies.write_timeout_failure_artifact,
        sanitize_path_text=dependencies.sanitize_path_text,
    )


def execute_mutation_step(
    vault: Path,
    workspace_vault: Path,
    *,
    run_id: str,
    resolution: ExperimentResolution,
    dependencies: MutationStepDependencies,
) -> CommandStepResult:
    command_spec = require_prepared_command(resolution.mutation_command_spec)
    command_request = CommandExecutionRequest(
        vault=vault,
        workspace_vault=workspace_vault,
        run_id=run_id,
        log_name="mutation-command",
        command_spec=command_spec,
        context=resolution.context,
    )
    command_execution = execute_command_step(
        command_request,
        dependencies=_command_execution_dependencies(dependencies),
    )
    if command_execution.result.get("timed_out"):
        timeout_failure_rel = write_command_timeout_failure(
            command_request,
            execution=command_execution,
            phase="mutation_command",
            scope_freeze_path=resolution.scope_freeze_path,
            context=resolution.context,
            artifacts={},
            note=(
                "mutation command timed out after "
                f"{command_execution.result['timeout_seconds']} seconds"
            ),
            dependencies=_command_execution_dependencies(dependencies),
        )
        dependencies.append_ledger_event(
            vault,
            run_id,
            event_type="mutation_failed",
            summary=(
                "Mutation command timed out before candidate capture completed "
                f"after {command_execution.result['timeout_seconds']} seconds."
            ),
            artifacts=[*command_execution.logs, timeout_failure_rel],
            decision="mutation_timeout",
            context=resolution.context,
            status="blocked",
        )
        dependencies.write_experiment_telemetry(
            vault,
            run_id=run_id,
            resolution=resolution,
            result={"mutation_command": command_execution.result},
        )
        raise RunMechanismExperimentMutationError(
            f"mutation command timed out after {command_execution.result['timeout_seconds']} seconds"
        )
    if command_execution.result["returncode"] != 0:
        dependencies.append_ledger_event(
            vault,
            run_id,
            event_type="mutation_failed",
            summary="Mutation command failed before candidate capture completed.",
            artifacts=command_execution.logs,
            decision="blocked_on_mutation_failure",
            context=resolution.context,
            status="blocked",
        )
        dependencies.write_experiment_telemetry(
            vault,
            run_id=run_id,
            resolution=resolution,
            result={"mutation_command": command_execution.result},
        )
        raise RunMechanismExperimentMutationError(
            f"mutation command failed with exit code {command_execution.result['returncode']}"
        )

    dependencies.append_ledger_event(
        vault,
        run_id,
        event_type="mutation_applied",
        summary="Applied the wrapper-provided mutation command inside a disposable workspace.",
        artifacts=[
            *resolution.primary_targets,
            *resolution.supporting_targets,
            *resolution.test_files,
            *command_execution.logs,
        ],
        decision="candidate_ready_for_capture",
        context=resolution.context,
        status="running",
    )
    return CommandStepResult(result=command_execution.result, logs=command_execution.logs)
