from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.runtime_context import RuntimeContext

from .auto_improve_execute_runtime import (
    ExecuteEvaluateDependencies,
    ExecuteEvaluatePhaseResult,
    ExecuteEvaluateRequest,
    execute_evaluate_phase,
)
from .auto_improve_iteration_persistence_runtime import (
    PersistIterationDependencies,
    PersistIterationPhaseResult,
)


@dataclass(frozen=True)
class AutoImproveIterationRequest:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    session: dict[str, Any]
    session_id: str
    proposal_report_path: str
    iteration: int
    attempted: set[str]
    quarantined: set[str]
    consecutive_failures: int
    pre_promotion_failure_outcomes: set[str]
    context: RuntimeContext


@dataclass(frozen=True)
class AutoImproveIterationDependencies:
    refresh_select_phase: Callable[..., Any]
    route_scaffold_phase: Callable[..., Any]
    execute_evaluate_dependencies: ExecuteEvaluateDependencies
    execute_evaluate_phase_fn: Callable[[ExecuteEvaluateRequest], ExecuteEvaluatePhaseResult]
    persist_iteration_dependencies: PersistIterationDependencies
    persist_iteration_phase_fn: Callable[..., PersistIterationPhaseResult]
    append_runtime_event: Callable[..., Any]


@dataclass(frozen=True)
class AutoImproveIterationResult:
    consecutive_failures: int
    stop_reason: str | None
    keep_running: bool


@dataclass(frozen=True)
class ExecuteEvaluateIterationRequest:
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


def _record_selected_proposal(
    vault: Path,
    session: dict[str, Any],
    attempted: set[str],
    *,
    session_id: str,
    iteration: int,
    proposal: dict[str, Any],
    build_run_id: Callable[[str, int, dict[str, Any]], str],
) -> str:
    run_id = build_run_id(session_id, iteration, proposal)
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    attempted.add(proposal["proposal_id"])
    session["attempted_proposal_ids"] = sorted(attempted)
    session["run_ids"].append(run_id)
    return run_id


def _duration_ms(phase_durations: dict[str, float]) -> int:
    total = 0.0
    for value in phase_durations.values():
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return round(total * 1000)


def execute_evaluate_iteration_phase(
    *args: Any,
    request: ExecuteEvaluateIterationRequest | None = None,
    execute_evaluate_phase_fn: Callable[[ExecuteEvaluateRequest], ExecuteEvaluatePhaseResult] = execute_evaluate_phase,
    **kwargs: Any,
) -> ExecuteEvaluatePhaseResult:
    request = _coerce_execute_evaluate_iteration_request(request=request, args=args, kwargs=kwargs)
    return execute_evaluate_phase_fn(
        ExecuteEvaluateRequest(
            vault=request.vault,
            resolved_policy_path=request.resolved_policy_path,
            run_id=request.run_id,
            proposal=request.proposal,
            scope_freeze=request.scope_freeze,
            scope_freeze_rel=request.scope_freeze_rel,
            roles=request.roles,
            routing_report_rels=request.routing_report_rels,
            consecutive_failures=request.consecutive_failures,
            pre_promotion_failure_outcomes=request.pre_promotion_failure_outcomes,
            proposal_report_path=request.proposal_report_path,
            context=request.context,
            dependencies=request.dependencies,
        )
    )


def _coerce_execute_evaluate_iteration_request(
    *,
    request: ExecuteEvaluateIterationRequest | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> ExecuteEvaluateIterationRequest:
    if request is not None:
        if args or kwargs:
            raise TypeError("request cannot be combined with positional or keyword iteration fields")
        return request

    field_names = [
        "vault",
        "resolved_policy_path",
        "run_id",
        "proposal",
        "scope_freeze",
        "scope_freeze_rel",
        "roles",
        "routing_report_rels",
        "consecutive_failures",
        "pre_promotion_failure_outcomes",
        "proposal_report_path",
        "context",
        "dependencies",
    ]
    if len(args) > len(field_names):
        raise TypeError(f"expected at most {len(field_names)} positional arguments")
    values = dict(zip(field_names, args, strict=False))
    values.update(kwargs)
    missing = [name for name in field_names if name not in values]
    if missing:
        raise TypeError(f"missing execute/evaluate iteration fields: {', '.join(missing)}")
    return ExecuteEvaluateIterationRequest(**values)


def run_auto_improve_iteration(
    request: AutoImproveIterationRequest,
    *,
    dependencies: AutoImproveIterationDependencies,
    build_run_id: Callable[[str, int, dict[str, Any]], str],
) -> AutoImproveIterationResult:
    selection = dependencies.refresh_select_phase(
        request.vault,
        request.policy,
        request.resolved_policy_path,
        attempted=request.attempted,
        quarantined=request.quarantined,
        context=request.context,
    )
    request.session["queue_snapshot"] = selection.queue_snapshot
    if selection.proposal is None:
        return AutoImproveIterationResult(
            consecutive_failures=request.consecutive_failures,
            stop_reason=selection.stop_reason or "queue_exhausted",
            keep_running=False,
        )

    proposal = selection.proposal
    run_id = _record_selected_proposal(
        request.vault,
        request.session,
        request.attempted,
        session_id=request.session_id,
        iteration=request.iteration,
        proposal=proposal,
        build_run_id=build_run_id,
    )
    route_scaffold = dependencies.route_scaffold_phase(
        request.vault,
        request.policy,
        request.resolved_policy_path,
        run_id=run_id,
        proposal=proposal,
        context=request.context,
    )
    dependencies.append_runtime_event(
        request.vault,
        context=request.context,
        component="auto_improve_session",
        phase="route_scaffold",
        decision=str(route_scaffold.scope_freeze.get("status", "")).strip(),
        artifact_path=route_scaffold.scope_freeze_rel,
        duration_ms=_duration_ms(route_scaffold.phase_durations),
        run_id=run_id,
        session_id=request.session_id,
        policy_version=request.policy.get("version"),
        proposal_id=str(proposal.get("proposal_id", "")).strip(),
        candidate_id=str(proposal.get("source_candidate_id", "")).strip(),
        decision_reason="scope_freeze_status",
    )
    execution = execute_evaluate_iteration_phase(
        request=ExecuteEvaluateIterationRequest(
            vault=request.vault,
            resolved_policy_path=request.resolved_policy_path,
            run_id=run_id,
            proposal=proposal,
            scope_freeze=route_scaffold.scope_freeze,
            scope_freeze_rel=route_scaffold.scope_freeze_rel,
            roles=route_scaffold.roles,
            routing_report_rels=route_scaffold.routing_report_rels,
            consecutive_failures=request.consecutive_failures,
            pre_promotion_failure_outcomes=request.pre_promotion_failure_outcomes,
            proposal_report_path=request.proposal_report_path,
            context=request.context,
            dependencies=dependencies.execute_evaluate_dependencies,
        ),
        execute_evaluate_phase_fn=dependencies.execute_evaluate_phase_fn,
    )
    persisted = dependencies.persist_iteration_phase_fn(
        request.vault,
        request.session,
        session_id=request.session_id,
        iteration=request.iteration,
        proposal=proposal,
        route_scaffold=route_scaffold,
        execution=execution,
        quarantined=request.quarantined,
        context=request.context,
        dependencies=dependencies.persist_iteration_dependencies,
    )
    next_consecutive_failures = persisted.consecutive_failures
    if execution.outcome.outcome == "executor_usage_limited":
        return AutoImproveIterationResult(
            consecutive_failures=next_consecutive_failures,
            stop_reason="executor_usage_limited",
            keep_running=False,
        )
    if (
        not execution.outcome.is_terminal_success
        and next_consecutive_failures >= request.session["budget"]["max_consecutive_failures"]
    ):
        return AutoImproveIterationResult(
            consecutive_failures=next_consecutive_failures,
            stop_reason="failure_budget_exhausted",
            keep_running=False,
        )
    return AutoImproveIterationResult(
        consecutive_failures=next_consecutive_failures,
        stop_reason=None,
        keep_running=True,
    )
