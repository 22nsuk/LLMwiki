from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.experiment_telemetry_runtime import run_rel
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext


@dataclass(frozen=True)
class FrozenScopeResult:
    scope_freeze: dict[str, Any]
    scope_freeze_rel: str


@dataclass(frozen=True)
class RoutingPlan:
    roles: list[str]
    routing_report_rels: list[str]


@dataclass(frozen=True)
class RouteScaffoldPhaseResult:
    run_id: str
    scope_freeze: dict[str, Any]
    scope_freeze_rel: str
    roles: list[str]
    routing_report_rels: list[str]
    phase_durations: dict[str, float]


@dataclass(frozen=True)
class RouteScaffoldDependencies:
    build_scope_freeze: Callable[..., dict[str, Any]]
    write_scope_freeze: Callable[..., Path]
    run_selector: Callable[..., tuple[dict[str, Any], Path]]
    run_mechanism_experiment: Callable[..., dict[str, Any]]
    append_ledger_event: Callable[..., Any]
    role_report_path: Callable[[str, str], str]


def freeze_proposal_scope(
    vault: Path,
    policy: dict[str, Any],
    resolved_policy_path: Path,
    *,
    run_id: str,
    proposal: dict[str, Any],
    context: RuntimeContext,
    dependencies: RouteScaffoldDependencies,
) -> FrozenScopeResult:
    scope_freeze = dependencies.build_scope_freeze(
        vault,
        policy,
        resolved_policy_path,
        run_id=run_id,
        proposal=proposal,
        context=context,
    )
    scope_freeze_path = dependencies.write_scope_freeze(vault, scope_freeze, run_id=run_id)
    return FrozenScopeResult(
        scope_freeze=scope_freeze,
        scope_freeze_rel=report_path(vault, scope_freeze_path),
    )


def _routing_selector_inputs(scope_freeze: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_targets": scope_freeze["inputs"]["primary_targets"],
        "supporting_targets": scope_freeze["inputs"]["supporting_targets"],
        "test_files": scope_freeze["resolution"]["test_files"],
        "manual_risk_flags": scope_freeze["resolution"]["risk_flags"],
    }


def _route_role(
    vault: Path,
    *,
    policy_path_text: str,
    run_id: str,
    role: str,
    selector_inputs: dict[str, Any],
    context: RuntimeContext,
    dependencies: RouteScaffoldDependencies,
) -> tuple[dict[str, Any], str]:
    report, report_path_abs = dependencies.run_selector(
        vault=vault,
        policy_path=policy_path_text,
        role=role,
        out_path=run_rel(run_id, f"subagent-routing.{role}.json"),
        context=context,
        **selector_inputs,
    )
    return report, report_path(vault, report_path_abs)


def route_scope_roles(
    vault: Path,
    policy: dict[str, Any],
    *,
    policy_path_text: str,
    run_id: str,
    scope_freeze: dict[str, Any],
    context: RuntimeContext,
    dependencies: RouteScaffoldDependencies,
) -> RoutingPlan:
    selector_inputs = _routing_selector_inputs(scope_freeze)
    worker_report, worker_report_rel = _route_role(
        vault,
        policy_path_text=policy_path_text,
        run_id=run_id,
        role="worker",
        selector_inputs=selector_inputs,
        context=context,
        dependencies=dependencies,
    )
    roles = ["worker"]
    routing_report_rels = [worker_report_rel]

    reviewer_needed = scope_freeze["dispatch"]["reviewer"] or (
        worker_report["routing_decision"]["score_band"]
        in policy["auto_improve_policy"]["scope_resolution"]["reviewer_score_bands"]
    )
    if reviewer_needed:
        _reviewer_report, reviewer_report_rel = _route_role(
            vault,
            policy_path_text=policy_path_text,
            run_id=run_id,
            role="reviewer",
            selector_inputs=selector_inputs,
            context=context,
            dependencies=dependencies,
        )
        roles.append("reviewer")
        routing_report_rels.append(reviewer_report_rel)

    if scope_freeze["dispatch"]["validator"]:
        _validator_report, validator_report_rel = _route_role(
            vault,
            policy_path_text=policy_path_text,
            run_id=run_id,
            role="validator",
            selector_inputs=selector_inputs,
            context=context,
            dependencies=dependencies,
        )
        roles.append("validator")
        routing_report_rels.append(validator_report_rel)

    for auditor in scope_freeze["dispatch"]["auditors"]:
        _auditor_report, auditor_report_rel = _route_role(
            vault,
            policy_path_text=policy_path_text,
            run_id=run_id,
            role=auditor,
            selector_inputs=selector_inputs,
            context=context,
            dependencies=dependencies,
        )
        roles.append(auditor)
        routing_report_rels.append(auditor_report_rel)

    return RoutingPlan(roles=roles, routing_report_rels=routing_report_rels)


def scaffold_route_run(
    vault: Path,
    *,
    policy_path_text: str,
    run_id: str,
    proposal: dict[str, Any],
    scope_freeze: dict[str, Any],
    scope_freeze_rel: str,
    routing_plan: RoutingPlan,
    proposal_report_path: str,
    context: RuntimeContext,
    dependencies: RouteScaffoldDependencies,
) -> None:
    dependencies.run_mechanism_experiment(
        vault,
        run_id=run_id,
        policy_path=policy_path_text,
        primary_targets=[],
        supporting_targets=[],
        test_files=scope_freeze["resolution"]["test_files"],
        log_summary=None,
        mutation_command=None,
        check_command=None,
        require_signoff=False,
        signoff_status="not_required",
        signoff_by="",
        signoff_ts="",
        finalize=False,
        proposal_id=proposal["proposal_id"],
        proposal_report_path=proposal_report_path,
        scaffold_only=True,
        scope_freeze_path=scope_freeze_rel,
        routing_report_paths=routing_plan.routing_report_rels,
        executor_report_paths=[
            dependencies.role_report_path(run_id, role) for role in routing_plan.roles
        ],
        context=context,
    )


def append_route_scaffold_events(
    vault: Path,
    *,
    run_id: str,
    scope_freeze: dict[str, Any],
    scope_freeze_rel: str,
    routing_plan: RoutingPlan,
    context: RuntimeContext,
    dependencies: RouteScaffoldDependencies,
) -> None:
    dependencies.append_ledger_event(
        vault,
        run_id,
        event_type="scope_frozen",
        summary="Frozen proposal scope for automated execution.",
        artifacts=[scope_freeze_rel],
        decision=scope_freeze["status"],
        context=context,
        status=None,
    )
    dependencies.append_ledger_event(
        vault,
        run_id,
        event_type="subagent_routed",
        summary="Selected bounded subagent roles and ladder rungs for this run.",
        artifacts=routing_plan.routing_report_rels,
        decision="ready",
        context=context,
        status=None,
    )


def route_scaffold_phase(
    vault: Path,
    policy: dict[str, Any],
    resolved_policy_path: Path,
    *,
    run_id: str,
    proposal: dict[str, Any],
    proposal_report_path: str,
    context: RuntimeContext,
    dependencies: RouteScaffoldDependencies,
) -> RouteScaffoldPhaseResult:
    phase_durations: dict[str, float] = {}
    policy_path_text = report_path(vault, resolved_policy_path)

    scope_start = time.monotonic()
    frozen_scope = freeze_proposal_scope(
        vault,
        policy,
        resolved_policy_path,
        run_id=run_id,
        proposal=proposal,
        context=context,
        dependencies=dependencies,
    )
    phase_durations["scope_freeze"] = round(time.monotonic() - scope_start, 3)

    routing_start = time.monotonic()
    routing_plan = route_scope_roles(
        vault,
        policy,
        policy_path_text=policy_path_text,
        run_id=run_id,
        scope_freeze=frozen_scope.scope_freeze,
        context=context,
        dependencies=dependencies,
    )
    phase_durations["routing"] = round(time.monotonic() - routing_start, 3)

    scaffold_start = time.monotonic()
    scaffold_route_run(
        vault,
        policy_path_text=policy_path_text,
        run_id=run_id,
        proposal=proposal,
        scope_freeze=frozen_scope.scope_freeze,
        scope_freeze_rel=frozen_scope.scope_freeze_rel,
        routing_plan=routing_plan,
        proposal_report_path=proposal_report_path,
        context=context,
        dependencies=dependencies,
    )
    append_route_scaffold_events(
        vault,
        run_id=run_id,
        scope_freeze=frozen_scope.scope_freeze,
        scope_freeze_rel=frozen_scope.scope_freeze_rel,
        routing_plan=routing_plan,
        context=context,
        dependencies=dependencies,
    )
    phase_durations["scaffold"] = round(time.monotonic() - scaffold_start, 3)

    return RouteScaffoldPhaseResult(
        run_id=run_id,
        scope_freeze=frozen_scope.scope_freeze,
        scope_freeze_rel=frozen_scope.scope_freeze_rel,
        roles=routing_plan.roles,
        routing_report_rels=routing_plan.routing_report_rels,
        phase_durations=phase_durations,
    )
