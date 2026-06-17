from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_json_object,
    write_schema_backed_report,
)
from ops.scripts.core.experiment_telemetry_runtime import append_ledger_event
from ops.scripts.core.observability_artifacts_runtime import (
    write_outcome_metrics_report,
    write_promotion_decision_trends,
    write_run_artifact_fingerprint,
)
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.proposal_scope_runtime import (
    build_scope_freeze,
    write_scope_freeze,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.runtime_event_logging_runtime import append_runtime_event
from ops.scripts.core.subagent_routing_runtime import run_selector

from . import (
    auto_improve_learning_preflight_runtime as _learning_preflight_runtime,
    auto_improve_session_report_runtime as _session_report_runtime,
    auto_improve_session_start_runtime as _session_start_runtime,
)
from ._auto_improve_maintenance_completion_runtime import (
    maintenance_already_reached_completion as _maintenance_already_reached_completion,
    maintenance_completion as _maintenance_completion,
)
from .auto_improve_error_runtime import (
    AutoImproveError as AutoImproveError,
    AutoImproveLearningReviewRequiredError,
    AutoImproveUsageError as AutoImproveUsageError,
)
from .auto_improve_execute_runtime import (
    ExecuteEvaluateDependencies,
    ExecuteEvaluatePhaseResult,
    ExecuteEvaluateRequest,
    execute_evaluate_phase,
)
from .auto_improve_execution_runtime import mutation_command
from .auto_improve_iteration_persistence_runtime import (
    PersistIterationDependencies,
    PersistIterationPhaseResult,
    persist_iteration_phase,
    write_iteration_telemetry,
)
from .auto_improve_iteration_runtime import (
    AutoImproveIterationDependencies,
    AutoImproveIterationRequest,
    run_auto_improve_iteration as run_auto_improve_iteration_helper,
)
from .auto_improve_learning_preflight_runtime import (
    apply_learning_preflight_session_fields,
    build_learning_preflight_decision,
)
from .auto_improve_loop_decision_runtime import (
    AutoImproveLoopState,
    _ensure_session_loop_state,
    _initial_auto_improve_loop_state,
    _record_pre_run_selected_proposal_metadata,
    _stop_reason_after_loop,
    _stop_reason_before_iteration,
)
from .auto_improve_maintenance_decision_runtime import (
    DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES as DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES,
    MAINTENANCE_ACTION_RESUME_TARGET as MAINTENANCE_ACTION_RESUME_TARGET,
    MAINTENANCE_ACTION_RUNNER_ACTION as MAINTENANCE_ACTION_RUNNER_ACTION,
    STABLE_MAINTENANCE_QUEUE_THRESHOLD as STABLE_MAINTENANCE_QUEUE_THRESHOLD,
    _initial_maintenance_payload,
    _maintenance_cycle_count,
    _maintenance_cycle_queue_metadata,
    _maintenance_terminal_completion_condition,
    _resolve_maintenance_interval as _resolve_maintenance_interval,
    _resolve_post_promote_maintenance_cycles as _resolve_post_promote_maintenance_cycles,
    build_maintenance_action_resume_plan,
)
from .auto_improve_outcome_runtime import (
    apply_execution_outcome,
    detect_executor_failure,
    evaluate_experiment_error,
    evaluate_experiment_result,
    evaluate_mutation_error,
    evaluate_scope_blocked,
    role_report_path,
)
from .auto_improve_promotion_stop_runtime import (
    promotion_maintenance_stop_decision as _promotion_maintenance_stop_decision,
)
from .auto_improve_queue_runtime import (
    build_proposal_queue,
    select_next_proposal,
)
from .auto_improve_readiness_runtime import (
    build_readiness_report,
    write_readiness_report,
)
from .auto_improve_route_scaffold_runtime import (
    RouteScaffoldDependencies,
    RouteScaffoldPhaseResult,
    route_scaffold_phase,
)
from .auto_improve_session_completion_runtime import (
    SessionCompletionDependencies,
    complete_auto_improve_session,
)
from .auto_improve_session_start_runtime import (
    AutoImproveSessionRequest,
    AutoImproveSessionStart,
)
from .auto_improve_value_runtime import _int_value, _list_text, _mapping_value
from .mechanism_review_runtime import build_report as build_mechanism_review_report
from .mutation_proposal_runtime import build_report as build_mutation_proposal_report
from .run_mechanism_experiment_runtime import run_mechanism_experiment

AUTO_IMPROVE_SESSION_SCHEMA = _session_start_runtime.AUTO_IMPROVE_SESSION_SCHEMA
DEFAULT_MECHANISM_REVIEW_REPORT = "ops/reports/mechanism-review-candidates.json"
DEFAULT_MUTATION_PROPOSAL_REPORT = "ops/reports/mutation-proposals.json"
DEFAULT_MAINTENANCE_ACTION_PLAN = "tmp/goal-runtime-maintenance-action.json"
MAINTENANCE_ACTION_PLAN_SCHEMA = "ops/schemas/goal-runtime-maintenance-action-plan.schema.json"
MAINTENANCE_ACTION_PLAN_SOURCE_COMMAND = (
    "python -m ops.scripts.auto_improve_loop "
    "--print-maintenance-action-next-max-proposals"
)
MAINTENANCE_ACTION_PLAN_ENVELOPE_FIELDS = frozenset(
    {
        "$schema",
        "generated_at",
        "source_command",
        "source_revision",
        "source_tree_fingerprint",
        "input_fingerprints",
        "schema_version",
        "artifact_status",
        "retention_policy",
        "encoding",
        "currentness",
        "vault",
    }
)


_build_proposal_queue = build_proposal_queue
_select_next_proposal = select_next_proposal
_role_report_path = role_report_path
_detect_executor_failure = detect_executor_failure
_mutation_command = mutation_command
_write_iteration_telemetry = write_iteration_telemetry
_load_session_report = _session_report_runtime._load_session_report
_write_session_report = _session_report_runtime._write_session_report
refresh_auto_improve_session_report = (
    _session_report_runtime.refresh_auto_improve_session_report
)
_coerce_auto_improve_session_request = (
    _session_start_runtime._coerce_auto_improve_session_request
)
_resolve_budget_value = _session_start_runtime._resolve_budget_value
_apply_resume_budget_overrides = _session_start_runtime._apply_resume_budget_overrides
_canonical_json_digest = _session_start_runtime._canonical_json_digest
_positive_contract_int = _session_start_runtime._positive_contract_int
_goal_contract_snapshot = _session_start_runtime._goal_contract_snapshot
_load_goal_contract_snapshot = _session_start_runtime._load_goal_contract_snapshot
_validate_goal_contract_budget = _session_start_runtime._validate_goal_contract_budget
_session_goal_contract_path = _session_start_runtime._session_goal_contract_path
_session_allows_maintenance_action_budget_increment = (
    _session_start_runtime._session_allows_maintenance_action_budget_increment
)
_compatible_goal_contract_refresh = _session_start_runtime._compatible_goal_contract_refresh
_attach_goal_contract_snapshot = _session_start_runtime._attach_goal_contract_snapshot
_new_session_id = _session_start_runtime._new_session_id
_validate_auto_improve_request = _session_start_runtime._validate_auto_improve_request
_validate_resume_executor = _session_start_runtime._validate_resume_executor
_new_auto_improve_session = _session_start_runtime._new_auto_improve_session
_start_auto_improve_session = _session_start_runtime._start_auto_improve_session
_learning_uncertain_contract_authorization = (
    _learning_preflight_runtime._learning_uncertain_contract_authorization
)


@dataclass(frozen=True)
class RefreshSelectPhaseResult:
    proposal: dict | None
    queue_snapshot: list[str]
    stop_reason: str | None = None


MAINTENANCE_WORK_ITEMS = (
    "mechanism_review_report",
    "mutation_proposal_report",
    "auto_improve_readiness_report",
    "auto_improve_session_report",
)


def _run_slug(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return normalized[:48] or "proposal"


def _build_run_id(session_id: str, iteration: int, proposal: dict) -> str:
    primary = proposal["primary_targets"][0]
    return f"{session_id}-run-{iteration:02d}-{_run_slug(Path(primary).stem)}"


def _pre_run_readiness_snapshot(
    vault: Path,
    readiness_report: dict,
    readiness_destination: Path,
) -> dict[str, object]:
    execution = readiness_report.get("execution_readiness")
    if not isinstance(execution, dict):
        execution = {}
    learning = readiness_report.get("learning_readiness")
    if not isinstance(learning, dict):
        learning = {}
    queue = readiness_report.get("queue")
    if not isinstance(queue, dict):
        queue = {}
    metrics = learning.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "report": report_path(vault, readiness_destination),
        "generated_at": str(readiness_report.get("generated_at", "")).strip(),
        "execution_status": str(execution.get("status", "")).strip(),
        "learning_status": str(learning.get("status", "")).strip(),
        "learning_gate_effect": str(learning.get("gate_effect", "")).strip(),
        "runnable_proposal_count": _int_value(queue.get("runnable_proposal_count")),
        "session_reports_considered": _int_value(metrics.get("session_reports_considered")),
    }


def _readiness_queue_snapshot(readiness_report: Mapping[str, Any]) -> list[str]:
    queue = readiness_report.get("queue")
    if not isinstance(queue, Mapping):
        return []
    return _list_text(queue.get("runnable_proposal_ids"))


def _readiness_runnable_proposal_count(readiness_report: Mapping[str, Any]) -> int:
    queue = readiness_report.get("queue")
    if not isinstance(queue, Mapping):
        return 0
    return _int_value(queue.get("runnable_proposal_count"))


def _preflight_learning_gate(
    vault: Path,
    start: AutoImproveSessionStart,
    *,
    allow_learning_uncertain: bool,
) -> bool:
    mechanism_review, proposals = _refresh_reports(
        vault,
        start.policy,
        start.resolved_policy_path,
        context=start.context,
    )
    readiness_report, readiness_destination = _refresh_readiness_report(
        vault,
        start.resolved_policy_path,
        context=start.context,
        mechanism_review=mechanism_review,
        proposals=proposals,
    )
    runnable_proposal_ids = _readiness_queue_snapshot(readiness_report)
    repeat_backlog_repair_active = _record_pre_run_selected_proposal_metadata(
        start.session,
        proposals,
    )
    decision = build_learning_preflight_decision(
        start.session,
        readiness_report,
        allow_learning_uncertain=allow_learning_uncertain,
    )
    pre_run_readiness = _pre_run_readiness_snapshot(
        vault,
        readiness_report,
        readiness_destination,
    )
    apply_learning_preflight_session_fields(
        start.session,
        decision,
        queue_snapshot=runnable_proposal_ids,
        pre_run_readiness=pre_run_readiness,
    )
    if decision.blocked:
        start.session["status"] = "blocked"
        _write_session_report(vault, start.session, context=start.context)
        append_runtime_event(
            vault,
            context=start.context,
            component="auto_improve_session",
            phase="preflight",
            decision="learning_review_required",
            artifact_path=report_path(vault, readiness_destination),
            session_id=start.session_id,
            policy_version=start.policy.get("version"),
        )
        raise AutoImproveLearningReviewRequiredError(decision.recommended_next_step)
    _write_session_report(vault, start.session, context=start.context)
    return repeat_backlog_repair_active


def _refresh_reports(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    context: RuntimeContext,
) -> tuple[dict, dict]:
    mechanism_review = build_mechanism_review_report(
        vault,
        policy,
        policy_path,
        context=context,
    )
    write_json_object(vault / DEFAULT_MECHANISM_REVIEW_REPORT, mechanism_review)
    proposals = build_mutation_proposal_report(
        vault,
        policy,
        policy_path,
        context=context,
    )
    write_json_object(vault / DEFAULT_MUTATION_PROPOSAL_REPORT, proposals)
    return mechanism_review, proposals


def _refresh_readiness_report(
    vault: Path,
    policy_path: Path,
    *,
    context: RuntimeContext,
    mechanism_review: dict,
    proposals: dict,
) -> tuple[dict, Path]:
    readiness_report = build_readiness_report(
        vault,
        policy_path=str(policy_path),
        context=context,
        mechanism_review_report=mechanism_review,
        mutation_proposal_report=proposals,
    )
    return readiness_report, write_readiness_report(vault, readiness_report)


def _refresh_select_phase(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    *,
    attempted: set[str],
    quarantined: set[str],
    context: RuntimeContext,
) -> RefreshSelectPhaseResult:
    _mechanism_review, proposals_report = _refresh_reports(
        vault,
        policy,
        resolved_policy_path,
        context=context,
    )
    _refresh_readiness_report(
        vault,
        resolved_policy_path,
        context=context,
        mechanism_review=_mechanism_review,
        proposals=proposals_report,
    )
    proposal, queue_snapshot = _select_next_proposal(
        proposals_report,
        attempted=attempted,
        quarantined=quarantined,
    )
    return RefreshSelectPhaseResult(
        proposal=proposal,
        queue_snapshot=queue_snapshot,
        stop_reason="queue_exhausted" if proposal is None else None,
    )


def _route_scaffold_phase(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    *,
    run_id: str,
    proposal: dict,
    context: RuntimeContext,
) -> RouteScaffoldPhaseResult:
    return route_scaffold_phase(
        vault,
        policy,
        resolved_policy_path,
        run_id=run_id,
        proposal=proposal,
        proposal_report_path=DEFAULT_MUTATION_PROPOSAL_REPORT,
        context=context,
        dependencies=RouteScaffoldDependencies(
            build_scope_freeze=build_scope_freeze,
            write_scope_freeze=write_scope_freeze,
            run_selector=run_selector,
            run_mechanism_experiment=run_mechanism_experiment,
            append_ledger_event=append_ledger_event,
            role_report_path=_role_report_path,
        ),
    )


def _execute_evaluate_phase(request: ExecuteEvaluateRequest) -> ExecuteEvaluatePhaseResult:
    return execute_evaluate_phase(request)


def _persist_iteration_phase(
    vault: Path,
    session: dict,
    *,
    session_id: str,
    iteration: int,
    proposal: dict,
    route_scaffold: RouteScaffoldPhaseResult,
    execution: ExecuteEvaluatePhaseResult,
    quarantined: set[str],
    context: RuntimeContext,
) -> PersistIterationPhaseResult:
    return persist_iteration_phase(
        vault,
        session,
        session_id=session_id,
        iteration=iteration,
        proposal=proposal,
        route_scaffold=route_scaffold,
        execution=execution,
        quarantined=quarantined,
        context=context,
        dependencies=PersistIterationDependencies(
            apply_execution_outcome=apply_execution_outcome,
            write_iteration_telemetry=_write_iteration_telemetry,
            write_run_artifact_fingerprint=write_run_artifact_fingerprint,
            write_session_report=_write_session_report,
        ),
    )


def _run_auto_improve_iteration(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    iteration: int,
) -> bool:
    iteration_context = start.context.with_iteration(iteration).with_executor(
        start.session["executor"]["name"]
    )
    iteration_result = run_auto_improve_iteration_helper(
        AutoImproveIterationRequest(
            vault=vault,
            policy=start.policy,
            resolved_policy_path=start.resolved_policy_path,
            session=start.session,
            session_id=start.session_id,
            proposal_report_path=DEFAULT_MUTATION_PROPOSAL_REPORT,
            iteration=iteration,
            attempted=state.attempted,
            quarantined=state.quarantined,
            consecutive_failures=state.consecutive_failures,
            pre_promotion_failure_outcomes=state.pre_promotion_failure_outcomes,
            context=iteration_context,
        ),
        dependencies=AutoImproveIterationDependencies(
            refresh_select_phase=_refresh_select_phase,
            route_scaffold_phase=_route_scaffold_phase,
            execute_evaluate_dependencies=ExecuteEvaluateDependencies(
                mutation_command=_mutation_command,
                run_mechanism_experiment=run_mechanism_experiment,
                role_report_path=_role_report_path,
                evaluate_scope_blocked=evaluate_scope_blocked,
                evaluate_experiment_result=evaluate_experiment_result,
                evaluate_mutation_error=evaluate_mutation_error,
                evaluate_experiment_error=evaluate_experiment_error,
            ),
            execute_evaluate_phase_fn=execute_evaluate_phase,
            persist_iteration_dependencies=PersistIterationDependencies(
                apply_execution_outcome=apply_execution_outcome,
                write_iteration_telemetry=_write_iteration_telemetry,
                write_run_artifact_fingerprint=write_run_artifact_fingerprint,
                write_session_report=_write_session_report,
            ),
            persist_iteration_phase_fn=persist_iteration_phase,
            append_runtime_event=append_runtime_event,
        ),
        build_run_id=_build_run_id,
    )
    state.consecutive_failures = iteration_result.consecutive_failures
    if iteration_result.stop_reason is not None:
        state.stop_reason = iteration_result.stop_reason
    return iteration_result.keep_running


def _complete_auto_improve_session(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
) -> dict:
    return complete_auto_improve_session(
        vault,
        session=start.session,
        session_id=start.session_id,
        stop_reason=state.stop_reason,
        policy=start.policy,
        resolved_policy_path=start.resolved_policy_path,
        context=start.context,
        dependencies=SessionCompletionDependencies(
            write_session_report=_write_session_report,
            write_promotion_decision_trends=write_promotion_decision_trends,
            write_outcome_metrics_report=write_outcome_metrics_report,
        ),
    )


def maintenance_action_resume_plan(
    vault: Path,
    *,
    session_id: str,
    mutation_proposals_report_path: str = DEFAULT_MUTATION_PROPOSAL_REPORT,
) -> dict[str, Any]:
    session = _load_session_report(vault, session_id)
    return build_maintenance_action_resume_plan(
        session,
        session_id=session_id,
        mutation_proposals_report_loader=lambda: load_optional_json_object(
            vault / mutation_proposals_report_path
        ),
    )


def write_maintenance_action_resume_plan(
    vault: Path,
    plan: Mapping[str, Any],
    *,
    out_path: str = DEFAULT_MAINTENANCE_ACTION_PLAN,
) -> Path:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = RuntimeContext.from_policy(policy)
    business_payload = {
        str(key): value
        for key, value in dict(plan).items()
        if str(key) not in MAINTENANCE_ACTION_PLAN_ENVELOPE_FIELDS
    }
    enriched_plan = {
        **business_payload,
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="goal_runtime_maintenance_action_plan",
            producer="ops.scripts.auto_improve_runtime",
            source_command=MAINTENANCE_ACTION_PLAN_SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=MAINTENANCE_ACTION_PLAN_SCHEMA,
            source_paths=[
                "ops/scripts/mechanism/auto_improve_runtime.py",
                "ops/scripts/mechanism/auto_improve_maintenance_decision_runtime.py",
                "ops/scripts/mechanism/auto_improve_loop.py",
                "ops/schemas/goal-runtime-maintenance-action-plan.schema.json",
                "mk/mechanism.mk",
            ],
            text_inputs={
                "maintenance_action_plan_payload": json.dumps(
                    business_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "maintenance_action_plan_out": str(out_path),
            },
        ),
        "retention_policy": "run_local_state",
        "vault": report_path(vault, vault),
    }
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=enriched_plan,
            schema_path=MAINTENANCE_ACTION_PLAN_SCHEMA,
            out_path=out_path,
            default_relative_path=DEFAULT_MAINTENANCE_ACTION_PLAN,
            context="goal runtime maintenance action plan schema validation failed",
            trailing_newline=True,
        )
    )


def _record_maintenance_cycle(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    *,
    index: int,
    cycle_started_elapsed_seconds: int,
) -> None:
    cycle_started_monotonic = time.monotonic()
    mechanism_review, proposals = _refresh_reports(
        vault,
        start.policy,
        start.resolved_policy_path,
        context=start.context,
    )
    readiness_report = build_readiness_report(
        vault,
        policy_path=str(start.resolved_policy_path),
        context=start.context,
        mechanism_review_report=mechanism_review,
        mutation_proposal_report=proposals,
    )
    readiness_destination = write_readiness_report(vault, readiness_report)
    queue_snapshot = _readiness_queue_snapshot(readiness_report)
    start.session["queue_snapshot"] = queue_snapshot
    loop_state = _ensure_session_loop_state(start.session, context=start.context)
    loop_state["updated_at"] = start.context.isoformat_z()
    maintenance = _mapping_value(start.session, "maintenance")
    cycles = maintenance.get("cycles")
    if not isinstance(cycles, list):
        cycles = []
    session_report = start.session.get("path", "")
    cycle_completed_elapsed_seconds = int(time.monotonic() - state.start_monotonic)
    runnable_proposal_count = _readiness_runnable_proposal_count(readiness_report)
    queue_metadata = _maintenance_cycle_queue_metadata(
        cycles,
        queue_snapshot,
        runnable_proposal_count,
    )
    cycles.append(
        {
            "index": index,
            "observed_at": start.context.isoformat_z(),
            "cycle_started_elapsed_seconds": cycle_started_elapsed_seconds,
            "elapsed_seconds": cycle_completed_elapsed_seconds,
            "duration_ms": round((time.monotonic() - cycle_started_monotonic) * 1000),
            "status": "pass",
            "work_items": list(MAINTENANCE_WORK_ITEMS),
            "mechanism_review_report": DEFAULT_MECHANISM_REVIEW_REPORT,
            "mutation_proposal_report": DEFAULT_MUTATION_PROPOSAL_REPORT,
            "readiness_report": report_path(vault, readiness_destination),
            "session_report": str(session_report),
            "runnable_proposal_count": runnable_proposal_count,
            "queue_snapshot": queue_snapshot,
            **queue_metadata,
        }
    )
    latest_cycle = cycles[-1]
    start.session["maintenance"] = {
        **dict(maintenance),
        "status": "running",
        "cycles": cycles,
        "cycle_count": len(cycles),
        "meaningful_cycle_count": len(
            [
                cycle
                for cycle in cycles
                if isinstance(cycle, Mapping)
                and bool(cycle.get("meaningful", False))
            ]
        ),
        "stable_queue_snapshot_count": _int_value(
            latest_cycle.get("stable_queue_snapshot_count")
        ),
        "stable_queue_snapshot": _list_text(latest_cycle.get("queue_snapshot")),
        "queue_action": dict(_mapping_value(latest_cycle, "queue_action")),
        "completed_at": start.context.isoformat_z(),
        "last_cycle_elapsed_seconds": cycle_completed_elapsed_seconds,
    }
    _write_session_report(vault, start.session, context=start.context)
    append_runtime_event(
        vault,
        context=start.context,
        component="auto_improve_session",
        phase="proposal_budget_maintenance",
        decision="cycle_pass",
        artifact_path=str(session_report),
        duration_ms=round((time.monotonic() - cycle_started_monotonic) * 1000),
        session_id=start.session_id,
        policy_version=start.policy.get("version"),
    )


def _run_proposal_budget_maintenance(
    vault: Path,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    *,
    interval_seconds: int,
    max_cycles: int | None,
) -> None:
    target_elapsed_seconds = start.session["budget"]["max_minutes"] * 60
    start_elapsed_seconds = int(time.monotonic() - state.start_monotonic)
    start.session["maintenance"] = _initial_maintenance_payload(
        started_at=start.context.isoformat_z(),
        target_elapsed_seconds=target_elapsed_seconds,
        start_elapsed_seconds=start_elapsed_seconds,
        interval_seconds=interval_seconds,
        max_cycles=max_cycles,
    )
    expected_min_cycle_count = _int_value(
        start.session["maintenance"].get("expected_min_cycle_count")
    )
    completion_condition = str(
        start.session["maintenance"].get("completion_condition", "")
    ).strip()
    _write_session_report(vault, start.session, context=start.context)
    if expected_min_cycle_count == 0:
        completion = _maintenance_already_reached_completion(
            start.session,
            completed_at=start.context.isoformat_z(),
        )
        start.session["maintenance"] = completion.maintenance
        _write_session_report(vault, start.session, context=start.context)
        return

    while True:
        cycle_started_elapsed_seconds = int(time.monotonic() - state.start_monotonic)
        _record_maintenance_cycle(
            vault,
            start,
            state,
            index=_maintenance_cycle_count(start.session) + 1,
            cycle_started_elapsed_seconds=cycle_started_elapsed_seconds,
        )
        elapsed_seconds = int(time.monotonic() - state.start_monotonic)
        terminal_condition = _maintenance_terminal_completion_condition(
            start.session,
            default_completion_condition=completion_condition,
            max_cycles=max_cycles,
            elapsed_seconds=elapsed_seconds,
            target_elapsed_seconds=target_elapsed_seconds,
        )
        if terminal_condition is not None:
            completion_condition = terminal_condition
            break
        time.sleep(min(interval_seconds, target_elapsed_seconds - elapsed_seconds))

    completion = _maintenance_completion(
        start.session,
        completion_condition=completion_condition,
        completed_at=start.context.isoformat_z(),
        last_cycle_elapsed_seconds=int(time.monotonic() - state.start_monotonic),
    )
    start.session["maintenance"] = completion.maintenance
    if completion.loop_stop_reason is not None:
        state.stop_reason = completion.loop_stop_reason
    _write_session_report(vault, start.session, context=start.context)


def _maybe_run_proposal_budget_maintenance(
    vault: Path,
    request: AutoImproveSessionRequest,
    start: AutoImproveSessionStart,
    state: AutoImproveLoopState,
    *,
    new_iteration_count: int,
) -> None:
    elapsed_seconds = int(time.monotonic() - state.start_monotonic)
    target_elapsed_seconds = start.session["budget"]["max_minutes"] * 60
    decision = _promotion_maintenance_stop_decision(
        start.session,
        maintain_until_budget=request.maintain_until_budget,
        post_promote_maintenance_cycles=request.post_promote_maintenance_cycles,
        maintenance_interval_seconds=request.maintenance_interval_seconds,
        new_iteration_count=new_iteration_count,
        stop_reason=state.stop_reason,
        elapsed_seconds=elapsed_seconds,
        target_elapsed_seconds=target_elapsed_seconds,
    )
    if decision.stop_reason is not None:
        state.stop_reason = decision.stop_reason
        return
    if not decision.should_run_maintenance:
        return
    _run_proposal_budget_maintenance(
        vault,
        start,
        state,
        interval_seconds=decision.interval_seconds,
        max_cycles=decision.max_cycles,
    )


def run_auto_improve_session(
    vault: AutoImproveSessionRequest | Path | None = None,
    **legacy_kwargs: Any,
) -> dict:
    request = _coerce_auto_improve_session_request(vault, legacy_kwargs)
    start = _start_auto_improve_session(request)
    loop_state = _initial_auto_improve_loop_state(
        start.auto_policy,
        start.session,
        monotonic=time.monotonic,
    )
    initial_stop_reason = _stop_reason_before_iteration(
        request.vault,
        start.session,
        loop_state,
        context=start.context,
        check_open_repeat_backlog=False,
        monotonic=time.monotonic,
    )
    if initial_stop_reason is None:
        loop_state.repeat_backlog_repair_active = (
            _preflight_learning_gate(
                request.vault,
                start,
                allow_learning_uncertain=request.allow_learning_uncertain,
            )
            is True
        )
    else:
        loop_state.stop_reason = initial_stop_reason

    initial_iteration_count = len(start.session["iterations"])
    first_iteration = initial_iteration_count + 1
    for iteration in range(first_iteration, start.session["budget"]["max_proposals"] + 1):
        stop_reason = _stop_reason_before_iteration(
            request.vault,
            start.session,
            loop_state,
            context=start.context,
            monotonic=time.monotonic,
        )
        if stop_reason is not None:
            loop_state.stop_reason = stop_reason
            break
        if not _run_auto_improve_iteration(request.vault, start, loop_state, iteration):
            break

    loop_state.stop_reason = _stop_reason_after_loop(
        request.vault,
        start.session,
        loop_state,
        context=start.context,
    )
    _maybe_run_proposal_budget_maintenance(
        request.vault,
        request,
        start,
        loop_state,
        new_iteration_count=len(start.session["iterations"]) - initial_iteration_count,
    )
    result = _complete_auto_improve_session(request.vault, start, loop_state)
    append_runtime_event(
        request.vault,
        context=start.context,
        component="auto_improve_session",
        phase="complete",
        decision=str(result.get("stop_reason", "")).strip(),
        artifact_path=str(result.get("session_report", "")).strip(),
        duration_ms=round((time.monotonic() - loop_state.start_monotonic) * 1000),
        session_id=start.session_id,
        policy_version=start.policy.get("version"),
    )
    return result
