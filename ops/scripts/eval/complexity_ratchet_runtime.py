from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RatchetCeiling:
    warn_targets: frozenset[str]
    resolved_targets: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RatchetJudgement:
    status: str
    new_warn_targets: tuple[str, ...]
    resurfaced_targets: tuple[str, ...]
    resolved_targets: tuple[str, ...]


def _normalized_path(value: object) -> str:
    return str(value).strip().replace("\\", "/").lstrip("./")


def _is_warn_target(target: dict[str, Any]) -> bool:
    over_budget_metrics = target.get("over_budget_metrics")
    no_headroom_metrics = target.get("no_headroom_metrics")
    low_headroom_metrics = target.get("low_headroom_metrics")
    function_budget_candidate_count = target.get("function_budget_candidate_count", 0)
    has_over_budget_metrics = isinstance(over_budget_metrics, list) and bool(over_budget_metrics)
    has_no_headroom_metrics = isinstance(no_headroom_metrics, list) and bool(no_headroom_metrics)
    has_low_headroom_metrics = isinstance(low_headroom_metrics, list) and bool(low_headroom_metrics)
    return (
        has_over_budget_metrics
        or has_no_headroom_metrics
        or has_low_headroom_metrics
        or int(function_budget_candidate_count) >= 1
    )


def current_warn_targets(report: dict[str, Any]) -> frozenset[str]:
    targets = report.get("targets")
    if not isinstance(targets, list):
        return frozenset()
    return frozenset(
        normalized
        for target in targets
        if isinstance(target, dict)
        and _is_warn_target(target)
        and (normalized := _normalized_path(target.get("path", "")))
    )


def judge_ratchet(ceiling: RatchetCeiling, report: dict[str, Any]) -> RatchetJudgement:
    current = current_warn_targets(report)
    baseline = frozenset(_normalized_path(path) for path in ceiling.warn_targets if _normalized_path(path))
    resolved_history = frozenset(
        _normalized_path(path) for path in ceiling.resolved_targets if _normalized_path(path)
    )
    resurfaced_targets = tuple(sorted(current & resolved_history))
    new_warn_targets = tuple(sorted(current - baseline - resolved_history))
    resolved_targets = tuple(sorted(baseline - current))
    status = "regression" if new_warn_targets or resurfaced_targets else "pass"
    return RatchetJudgement(
        status=status,
        new_warn_targets=new_warn_targets,
        resurfaced_targets=resurfaced_targets,
        resolved_targets=resolved_targets,
    )
