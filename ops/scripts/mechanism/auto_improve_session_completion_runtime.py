from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.runtime_context import RuntimeContext


@dataclass(frozen=True)
class SessionCompletionDependencies:
    write_session_report: Callable[..., Path]
    write_promotion_decision_trends: Callable[..., str]
    write_outcome_metrics_report: Callable[..., str]


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
        "run_ids": session["run_ids"],
    }
