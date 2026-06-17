from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .auto_improve_maintenance_decision_runtime import (
    _maintenance_completion_stop_reason,
    _mapping_value,
)


@dataclass(frozen=True)
class MaintenanceCompletion:
    maintenance: dict[str, Any]
    loop_stop_reason: str | None = None


def maintenance_already_reached_completion(
    session: Mapping[str, Any],
    *,
    completed_at: str,
) -> MaintenanceCompletion:
    maintenance = dict(_mapping_value(session, "maintenance"))
    maintenance["status"] = "complete"
    maintenance["completed_at"] = completed_at
    maintenance["stop_reason"] = "time_budget_already_reached"
    return MaintenanceCompletion(maintenance=maintenance)


def maintenance_completion(
    session: Mapping[str, Any],
    *,
    completion_condition: str,
    completed_at: str,
    last_cycle_elapsed_seconds: int,
) -> MaintenanceCompletion:
    maintenance = dict(_mapping_value(session, "maintenance"))
    maintenance["status"] = "complete"
    maintenance["completed_at"] = completed_at
    maintenance["completion_condition"] = completion_condition
    maintenance["stop_reason"] = _maintenance_completion_stop_reason(completion_condition)
    maintenance["last_cycle_elapsed_seconds"] = last_cycle_elapsed_seconds
    loop_stop_reason = (
        "time_budget_exhausted"
        if maintenance["stop_reason"] == "time_budget_reached"
        else None
    )
    return MaintenanceCompletion(
        maintenance=maintenance,
        loop_stop_reason=loop_stop_reason,
    )
