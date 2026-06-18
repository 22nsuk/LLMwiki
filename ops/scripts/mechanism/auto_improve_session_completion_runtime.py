from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.runtime_context import RuntimeContext

from .failure_taxonomy_runtime import GENERATED_EVIDENCE_SETTLE_REQUIRED


@dataclass(frozen=True)
class SessionCompletionDependencies:
    write_session_report: Callable[..., Path]
    write_promotion_decision_trends: Callable[..., str]
    write_outcome_metrics_report: Callable[..., str]


def _last_iteration_was_promoted(session: Mapping[str, Any]) -> bool:
    iterations = session.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        return False
    last_iteration = iterations[-1]
    if not isinstance(last_iteration, Mapping):
        return False
    return (
        str(last_iteration.get("decision", "")).strip() == "PROMOTE"
        or str(last_iteration.get("outcome", "")).strip() == "promoted"
        or str(last_iteration.get("status", "")).strip() == "promoted"
    )


def completion_class_for_session(session: Mapping[str, Any], *, stop_reason: str) -> str:
    if stop_reason == "proposal_budget_exhausted" and _last_iteration_was_promoted(session):
        return "bounded_success_after_promotion"
    if stop_reason == "proposal_budget_exhausted":
        return "proposal_budget_exhausted"
    if stop_reason == "queue_exhausted":
        return "queue_exhausted"
    if stop_reason == "time_budget_exhausted":
        return "time_budget_exhausted"
    if stop_reason == "failure_budget_exhausted":
        return "failure_budget_exhausted"
    if stop_reason == GENERATED_EVIDENCE_SETTLE_REQUIRED:
        return GENERATED_EVIDENCE_SETTLE_REQUIRED
    if stop_reason == "repeated_blocker_backlog_required":
        return "blocked_repair_required"
    return "stopped"


def complete_auto_improve_session(
    vault: Path,
    *,
    session: dict[str, Any],
    session_id: str,
    stop_reason: str,
    policy: dict[str, Any],
    resolved_policy_path: Path,
    context: RuntimeContext,
    dependencies: SessionCompletionDependencies,
) -> dict[str, Any]:
    session["status"] = "complete"
    session["stop_reason"] = stop_reason
    completion_class = completion_class_for_session(session, stop_reason=stop_reason)
    session["completion_class"] = completion_class
    dependencies.write_session_report(vault, session, context=context)
    promotion_decision_trends = dependencies.write_promotion_decision_trends(
        vault,
        policy,
        resolved_policy_path,
        context=context,
    )
    outcome_metrics = dependencies.write_outcome_metrics_report(
        vault,
        policy,
        resolved_policy_path,
        context=context,
    )
    return {
        "session_id": session_id,
        "session_report": session["path"],
        "routing_provenance_aggregate": (
            f"ops/reports/routing-provenance-aggregates/{session_id}.json"
        ),
        "promotion_decision_trends": promotion_decision_trends,
        "outcome_metrics": outcome_metrics,
        "iterations": len(session["iterations"]),
        "stop_reason": stop_reason,
        "completion_class": completion_class,
        "run_ids": session["run_ids"],
    }
