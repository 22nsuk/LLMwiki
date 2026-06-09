from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.experiment_telemetry_runtime import run_rel
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext

from .auto_improve_outcome_runtime import ExecutionOutcome
from .run_mechanism_experiment_runtime import (
    RunMechanismExperimentError,
    RunMechanismExperimentMutationError,
)


@dataclass(frozen=True)
class ExecuteEvaluatePhaseResult:
    outcome: ExecutionOutcome
    phase_durations: dict[str, float]


@dataclass(frozen=True)
class ExecuteEvaluateDependencies:
    mutation_command: Callable[..., str]
    run_mechanism_experiment: Callable[..., dict[str, Any]]
    role_report_path: Callable[[str, str], str]
    evaluate_scope_blocked: Callable[[int], ExecutionOutcome]
    evaluate_experiment_result: Callable[[dict[str, Any], int], ExecutionOutcome]
    evaluate_mutation_error: Callable[..., ExecutionOutcome]
    evaluate_experiment_error: Callable[[int], ExecutionOutcome]


@dataclass(frozen=True)
class ExecuteEvaluateRequest:
    vault: Path
    resolved_policy_path: Path
    run_id: str
    proposal: dict[str, Any]
    scope_freeze: dict[str, Any]
    scope_freeze_rel: str
    roles: list[str]
    routing_report_rels: list[str]
    consecutive_failures: int
    pre_promotion_failure_outcomes: set[str]
    proposal_report_path: str
    context: RuntimeContext
    dependencies: ExecuteEvaluateDependencies


def _executor_report_paths(
    *,
    run_id: str,
    roles: list[str],
    dependencies: ExecuteEvaluateDependencies,
) -> list[str]:
    return [dependencies.role_report_path(run_id, role) for role in roles]


def _full_execution_mutation_command(request: ExecuteEvaluateRequest, *, policy_path_text: str) -> str:
    return request.dependencies.mutation_command(
        artifact_root=request.vault,
        run_id=request.run_id,
        scope_freeze_rel=request.scope_freeze_rel,
        proposal_snapshot_rel=run_rel(request.run_id, "proposal-snapshot.json"),
        roles=request.roles,
        routing_report_rels=request.routing_report_rels,
        policy_path=policy_path_text,
    )


def _scope_freeze_inputs(request: ExecuteEvaluateRequest) -> dict[str, Any]:
    inputs = request.scope_freeze.get("inputs")
    return inputs if isinstance(inputs, dict) else {}


def run_full_experiment(request: ExecuteEvaluateRequest) -> dict[str, Any]:
    policy_path_text = report_path(request.vault, request.resolved_policy_path)
    scope_inputs = _scope_freeze_inputs(request)
    return request.dependencies.run_mechanism_experiment(
        request.vault,
        run_id=request.run_id,
        policy_path=policy_path_text,
        primary_targets=list(scope_inputs.get("primary_targets", [])),
        supporting_targets=list(scope_inputs.get("supporting_targets", [])),
        test_files=request.scope_freeze["resolution"]["test_files"],
        log_summary=None,
        mutation_command=_full_execution_mutation_command(request, policy_path_text=policy_path_text),
        check_command=None,
        require_signoff=False,
        signoff_status="not_required",
        signoff_by="auto-improve",
        signoff_ts=request.context.isoformat_z(),
        finalize=True,
        proposal_id=request.proposal["proposal_id"],
        proposal_report_path=request.proposal_report_path,
        scaffold_only=False,
        scope_freeze_path=request.scope_freeze_rel,
        routing_report_paths=request.routing_report_rels,
        executor_report_paths=_executor_report_paths(
            run_id=request.run_id,
            roles=request.roles,
            dependencies=request.dependencies,
        ),
        context=request.context,
    )


def evaluate_execution_outcome(request: ExecuteEvaluateRequest) -> ExecutionOutcome:
    if request.scope_freeze["status"] == "blocked":
        return request.dependencies.evaluate_scope_blocked(request.consecutive_failures)

    try:
        result = run_full_experiment(request)
    except RunMechanismExperimentMutationError:
        return request.dependencies.evaluate_mutation_error(
            run_id=request.run_id,
            roles=request.roles,
            artifact_root=request.vault,
            pre_promotion_failure_outcomes=request.pre_promotion_failure_outcomes,
            consecutive_failures=request.consecutive_failures,
        )
    except RunMechanismExperimentError:
        return request.dependencies.evaluate_experiment_error(request.consecutive_failures)

    return request.dependencies.evaluate_experiment_result(result, request.consecutive_failures)


def execute_evaluate_phase(request: ExecuteEvaluateRequest) -> ExecuteEvaluatePhaseResult:
    experiment_start = time.monotonic()
    execution_outcome = evaluate_execution_outcome(request)
    return ExecuteEvaluatePhaseResult(
        outcome=execution_outcome,
        phase_durations={"experiment": round(time.monotonic() - experiment_start, 3)},
    )
