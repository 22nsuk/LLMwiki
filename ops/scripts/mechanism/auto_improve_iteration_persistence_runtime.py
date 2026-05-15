from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.experiment_telemetry_runtime import run_rel, write_run_telemetry
from ops.scripts.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_record_from_payload,
    decision_record_from_report,
)
from ops.scripts.runtime_context import RuntimeContext

from .auto_improve_execute_runtime import ExecuteEvaluatePhaseResult
from .auto_improve_iteration_telemetry_runtime import (
    iteration_behavior_delta_digest,
    iteration_same_eval_contract,
    iteration_same_eval_reason,
)
from .auto_improve_outcome_runtime import role_report_path
from .auto_improve_route_scaffold_runtime import RouteScaffoldPhaseResult
from .auto_improve_session_runtime import load_optional_json

ITERATION_TELEMETRY_WRITTEN_FIELDS = frozenset(
    {
        "session_id",
        "run_id",
        "generated_at",
        "observed_at",
        "proposal_id",
        "source_candidate_id",
        "proposal_snapshot",
        "scope_freeze",
        "routing_reports",
        "executor_reports",
        "phase_durations",
        "failure_taxonomy",
        "decision",
        "finalized",
        "finalize_result",
    }
)

ITERATION_TELEMETRY_MERGED_FIELDS = frozenset(
    {
        "decision_record",
        "command_timeouts",
        "timeout_failure_artifacts",
        "behavior_delta",
        "behavior_delta_digest",
        "same_eval_reason",
        "same_eval_reason_code",
        "strict_secondary_improvement_present",
        "secondary_improvement_axes",
    }
)

# Run-telemetry fields produced earlier in the run that later iteration writes
# should preserve unless an explicit overwrite or merge rule applies.
PRESERVED_RUN_TELEMETRY_FIELDS = frozenset(
    {
        "metadata",
        "primary_targets", "supporting_targets", "test_files",
        "workspace_preparation", "apply_mode", "apply_status",
        "live_applied", "shadow_apply_report", "rollback_rehearsal_report",
    }
)


@dataclass(frozen=True)
class PersistIterationPhaseResult:
    consecutive_failures: int
    telemetry_rel: str


@dataclass(frozen=True)
class PersistIterationDependencies:
    apply_execution_outcome: Callable[..., int]
    write_iteration_telemetry: Callable[..., str]
    write_run_artifact_fingerprint: Callable[..., str]
    write_session_report: Callable[..., Path]


@dataclass(frozen=True)
class IterationTelemetryRequest:
    vault: Path
    run_id: str
    session_id: str
    proposal: dict
    scope_freeze_rel: str
    routing_report_rels: list[str]
    roles: list[str]
    phase_durations: dict[str, float]
    outcome: str
    result: dict | None
    context: RuntimeContext


def _normalize_timeout_result(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    if not any(key in value for key in ("timed_out", "timeout_seconds", "termination_reason")):
        return None
    timeout_seconds = value.get("timeout_seconds", 0)
    if not isinstance(timeout_seconds, int):
        timeout_seconds = 0
    return {
        "timed_out": bool(value.get("timed_out", False)),
        "timeout_seconds": timeout_seconds,
        "termination_reason": str(value.get("termination_reason", "")),
        "launch_succeeded": bool(value.get("launch_succeeded", True)),
        "signal_sent": str(value.get("signal_sent", "none")),
        "final_state_observed": str(value.get("final_state_observed", "")),
        "stdout_received": bool(value.get("stdout_received", False)),
        "stderr_received": bool(value.get("stderr_received", False)),
    }


def _iteration_command_timeouts(vault: Path, run_id: str, result: dict | None) -> dict | None:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    merged: dict[str, dict] = {}
    timeout_sources = []
    if isinstance(existing_report, dict):
        timeout_sources.append(existing_report.get("command_timeouts", {}))
    if isinstance(result, dict):
        timeout_sources.extend((result.get("command_timeouts", {}), result))
    for source in timeout_sources:
        if not isinstance(source, dict):
            continue
        for key in ("mutation_command", "repo_health"):
            normalized = _normalize_timeout_result(source.get(key))
            if normalized is not None:
                merged[key] = normalized
    return merged or None


def _iteration_timeout_failure_artifacts(vault: Path, run_id: str, result: dict | None) -> list[str]:
    artifacts: set[str] = set()
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    artifact_sources = (
        existing_report.get("timeout_failure_artifacts", []) if isinstance(existing_report, dict) else [],
        result.get("timeout_failure_artifacts", []) if isinstance(result, dict) else [],
    )
    artifacts.update(
        str(item)
        for source in artifact_sources
        if isinstance(source, list)
        for item in source
        if str(item).strip()
    )
    run_dir = vault / run_rel(run_id, "")
    if run_dir.exists():
        artifacts.update(
            run_rel(run_id, path.name)
            for path in run_dir.glob("*-timeout-failure.json")
            if path.is_file()
        )
    return sorted(artifacts)


def _iteration_behavior_delta(vault: Path, run_id: str, result: dict | None) -> str:
    if isinstance(result, dict):
        behavior_delta = result.get("behavior_delta")
        if isinstance(behavior_delta, str) and behavior_delta.strip():
            return behavior_delta
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    if isinstance(existing_report, dict):
        behavior_delta = existing_report.get("behavior_delta")
        if isinstance(behavior_delta, str) and behavior_delta.strip():
            return behavior_delta
    rel_path = run_rel(run_id, "behavior-delta.json")
    if (vault / rel_path).is_file():
        return rel_path
    return ""


def _load_repo_relative_json(vault: Path, rel_path: object) -> dict | None:
    if not isinstance(rel_path, str) or not rel_path.strip():
        return None
    path = Path(rel_path)
    if path.is_absolute():
        return None
    vault_root = vault.resolve()
    resolved_path = (vault_root / path).resolve()
    if not resolved_path.is_relative_to(vault_root):
        return None
    payload = load_optional_json(resolved_path)
    return payload if isinstance(payload, dict) else None


def _decision_record_from_source(vault: Path, source: object) -> dict | None:
    if not isinstance(source, dict):
        return None
    decision_record = source.get("decision_record")
    if isinstance(decision_record, dict):
        try:
            return decision_record_from_payload(
                {"decision_record": decision_record},
                require_record=True,
            )
        except PromotionDecisionRegistryError:
            pass
    promotion_report = source.get("promotion_report")
    if isinstance(promotion_report, dict):
        try:
            return decision_record_from_report(promotion_report, require_record=False)
        except PromotionDecisionRegistryError:
            pass
    promotion_payload = _load_repo_relative_json(vault, promotion_report)
    if promotion_payload is not None:
        try:
            return decision_record_from_report(promotion_payload, require_record=False)
        except PromotionDecisionRegistryError:
            pass
    return None


def _iteration_decision_record(
    vault: Path,
    run_id: str,
    result: dict | None,
    existing_report: dict,
) -> dict | None:
    for source in (result, existing_report):
        decision_record = _decision_record_from_source(vault, source)
        if decision_record is not None:
            return decision_record
    promotion_payload = _load_repo_relative_json(vault, run_rel(run_id, "promotion-report.json"))
    if promotion_payload is None:
        return None
    try:
        return decision_record_from_report(promotion_payload, require_record=False)
    except PromotionDecisionRegistryError:
        return None


def _preserve_existing_telemetry_fields(payload: dict[str, Any], existing_report: dict) -> None:
    for field in PRESERVED_RUN_TELEMETRY_FIELDS:
        if field in existing_report:
            payload[field] = existing_report[field]


def _update_session_loop_state(
    session: dict[str, Any],
    *,
    run_id: str,
    outcome: object,
    consecutive_failures: int,
    context: RuntimeContext,
) -> None:
    outcome_text = str(getattr(outcome, "outcome", "")).strip()
    decision_text = str(getattr(outcome, "decision", "")).strip()
    terminal_success = bool(getattr(outcome, "is_terminal_success", False))
    session["loop_state"] = {
        "consecutive_failures": max(0, consecutive_failures),
        "last_outcome": outcome_text,
        "last_decision": decision_text,
        "last_run_id": run_id,
        "last_blocking_reason": "" if terminal_success else outcome_text,
        "updated_at": context.isoformat_z(),
    }


def write_iteration_telemetry(
    *args: Any,
    request: IterationTelemetryRequest | None = None,
    **kwargs: Any,
) -> str:
    request = _coerce_iteration_telemetry_request(request=request, args=args, kwargs=kwargs)
    loaded_existing_report = load_optional_json(
        request.vault / run_rel(request.run_id, "run-telemetry.json")
    )
    existing_report = loaded_existing_report if isinstance(loaded_existing_report, dict) else {}
    observed_at = request.context.isoformat_z()
    payload = {
        "session_id": request.session_id,
        "run_id": request.run_id,
        "generated_at": observed_at,
        "observed_at": observed_at,
        "proposal_id": request.proposal["proposal_id"],
        "source_candidate_id": str(request.proposal.get("source_candidate_id", "")).strip(),
        "proposal_snapshot": run_rel(request.run_id, "proposal-snapshot.json"),
        "scope_freeze": request.scope_freeze_rel,
        "routing_reports": request.routing_report_rels,
        "executor_reports": [role_report_path(request.run_id, role) for role in request.roles],
        "phase_durations": request.phase_durations,
        "failure_taxonomy": request.outcome if request.outcome not in {"promoted", "discarded"} else "",
        "decision": (request.result or {}).get("decision", ""),
        "finalized": bool((request.result or {}).get("finalized")),
        "finalize_result": (request.result or {}).get("finalize_result", {}),
    }
    _preserve_existing_telemetry_fields(payload, existing_report)
    decision_record = _iteration_decision_record(
        request.vault,
        request.run_id,
        request.result,
        existing_report,
    )
    if isinstance(decision_record, dict):
        payload["decision_record"] = decision_record
    command_timeouts = _iteration_command_timeouts(request.vault, request.run_id, request.result)
    if command_timeouts is not None:
        payload["command_timeouts"] = command_timeouts
    timeout_failure_artifacts = _iteration_timeout_failure_artifacts(
        request.vault, request.run_id, request.result
    )
    if timeout_failure_artifacts:
        payload["timeout_failure_artifacts"] = timeout_failure_artifacts
    behavior_delta = _iteration_behavior_delta(request.vault, request.run_id, request.result)
    behavior_delta_digest = ""
    if behavior_delta:
        payload["behavior_delta"] = behavior_delta
        behavior_delta_digest = iteration_behavior_delta_digest(
            request.vault,
            behavior_delta,
            existing_report,
        )
        if behavior_delta_digest:
            payload["behavior_delta_digest"] = behavior_delta_digest
    same_eval_reason = iteration_same_eval_reason(request.result, existing_report)
    if same_eval_reason:
        payload["same_eval_reason"] = same_eval_reason
    same_eval_contract = iteration_same_eval_contract(
        request.result,
        existing_report,
        same_eval_reason=same_eval_reason,
        behavior_delta_digest=behavior_delta_digest,
    )
    if same_eval_reason or same_eval_contract["same_eval_reason_code"] != "unknown":
        payload["same_eval_reason_code"] = same_eval_contract["same_eval_reason_code"]
        payload["strict_secondary_improvement_present"] = same_eval_contract[
            "strict_secondary_improvement_present"
        ]
        payload["secondary_improvement_axes"] = same_eval_contract["secondary_improvement_axes"]
    return write_run_telemetry(request.vault, request.run_id, payload)


def _coerce_iteration_telemetry_request(
    *,
    request: IterationTelemetryRequest | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> IterationTelemetryRequest:
    if request is not None:
        if args or kwargs:
            raise TypeError("request cannot be combined with positional or keyword telemetry fields")
        return request

    field_names = [
        "vault",
        "run_id",
        "session_id",
        "proposal",
        "scope_freeze_rel",
        "routing_report_rels",
        "roles",
        "phase_durations",
        "outcome",
        "result",
        "context",
    ]
    if len(args) > len(field_names):
        raise TypeError(f"expected at most {len(field_names)} positional arguments")
    values = dict(zip(field_names, args, strict=False))
    values.update(kwargs)
    missing = [name for name in field_names if name not in values]
    if missing:
        raise TypeError(f"missing iteration telemetry fields: {', '.join(missing)}")
    return IterationTelemetryRequest(**values)


def persist_iteration_phase(
    vault: Path,
    session: dict[str, Any],
    *,
    session_id: str,
    iteration: int,
    proposal: dict[str, Any],
    route_scaffold: RouteScaffoldPhaseResult,
    execution: ExecuteEvaluatePhaseResult,
    quarantined: set[str],
    context: RuntimeContext,
    dependencies: PersistIterationDependencies,
) -> PersistIterationPhaseResult:
    run_id = route_scaffold.run_id
    consecutive_failures = dependencies.apply_execution_outcome(
        session,
        proposal_id=proposal["proposal_id"],
        quarantined=quarantined,
        outcome=execution.outcome,
    )
    phase_durations = dict(route_scaffold.phase_durations)
    phase_durations.update(execution.phase_durations)
    telemetry_rel = dependencies.write_iteration_telemetry(
        request=IterationTelemetryRequest(
            vault=vault,
            run_id=run_id,
            session_id=session_id,
            proposal=proposal,
            scope_freeze_rel=route_scaffold.scope_freeze_rel,
            routing_report_rels=route_scaffold.routing_report_rels,
            roles=route_scaffold.roles,
            phase_durations=phase_durations,
            outcome=execution.outcome.outcome,
            result=execution.outcome.result,
            context=context,
        ),
    )
    dependencies.write_run_artifact_fingerprint(vault, run_id, context=context)
    session["iterations"].append(
        execution.outcome.iteration_record(
            index=iteration,
            proposal_id=proposal["proposal_id"],
            run_id=run_id,
        )
    )
    _update_session_loop_state(
        session,
        run_id=run_id,
        outcome=execution.outcome,
        consecutive_failures=consecutive_failures,
        context=context,
    )
    dependencies.write_session_report(vault, session, context=context)
    return PersistIterationPhaseResult(
        consecutive_failures=consecutive_failures,
        telemetry_rel=telemetry_rel,
    )
