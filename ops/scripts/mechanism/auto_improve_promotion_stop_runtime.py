from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .auto_improve_maintenance_decision_runtime import (
    DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES,
    _last_iteration_outcome,
    _maintenance_run_eligibility,
)


@dataclass(frozen=True)
class PromotionMaintenanceStopDecision:
    should_run_maintenance: bool
    reason: str
    interval_seconds: int = 300
    max_cycles: int | None = None
    stop_reason: str | None = None
    post_promote_cycles: int = DEFAULT_POST_PROMOTE_MAINTENANCE_CYCLES


def promotion_maintenance_stop_decision(
    session: Mapping[str, Any],
    *,
    maintain_until_budget: bool,
    post_promote_maintenance_cycles: int | None,
    maintenance_interval_seconds: int | None,
    new_iteration_count: int,
    stop_reason: str | None,
    elapsed_seconds: int,
    target_elapsed_seconds: int,
) -> PromotionMaintenanceStopDecision:
    eligibility = _maintenance_run_eligibility(
        maintain_until_budget=maintain_until_budget,
        post_promote_maintenance_cycles=post_promote_maintenance_cycles,
        maintenance_interval_seconds=maintenance_interval_seconds,
        new_iteration_count=new_iteration_count,
        stop_reason=stop_reason,
        last_iteration_outcome=_last_iteration_outcome(session),
        elapsed_seconds=elapsed_seconds,
        target_elapsed_seconds=target_elapsed_seconds,
    )
    return PromotionMaintenanceStopDecision(
        should_run_maintenance=eligibility.should_run,
        reason=eligibility.reason,
        interval_seconds=eligibility.interval_seconds,
        max_cycles=eligibility.max_cycles,
        stop_reason=eligibility.stop_reason,
        post_promote_cycles=eligibility.post_promote_cycles,
    )
