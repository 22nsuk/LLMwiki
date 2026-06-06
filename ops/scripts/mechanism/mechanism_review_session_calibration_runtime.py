from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.observability_artifacts_shared_runtime import (
    resolve_auto_improve_session_report_rel,
    resolve_run_artifact_rel,
)

from .mechanism_review_history_runtime import load_optional_json

JsonLoader = Callable[[Path], dict | None]


@dataclass
class _SessionCalibrationCounters:
    runs_with_session_context: int = 0
    sessions_with_rollups: int = 0
    validation_blocked_sessions: int = 0
    review_blocked_sessions: int = 0
    mutation_failed_sessions: int = 0
    validator_dispatch_sessions: int = 0
    reviewer_dispatch_sessions: int = 0
    high_risk_routing_sessions: int = 0


__all__ = [
    "JsonLoader",
    "accumulate_session_calibration_diagnostics",
    "any_positive_counter_value",
    "apply_session_calibration",
    "build_session_calibration_diagnostics",
    "counter_has_positive_value",
    "empty_session_calibration_diagnostics_entry",
    "session_calibration_summary",
    "session_report_for_run",
]


def _clamp_priority(value: int) -> int:
    return max(0, min(100, value))


def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _session_report_containing_run(
    vault: Path,
    run_id: str,
    cache: dict[str, dict | None],
    *,
    load_optional_json_func: JsonLoader,
) -> tuple[str, dict | None]:
    reports_dir = vault / "ops" / "reports" / "auto-improve-sessions"
    if not reports_dir.exists():
        return "", None
    latest_key = ("", "")
    latest_session_id = ""
    latest_report: dict | None = None
    for path in sorted(reports_dir.glob("*.json")):
        payload = load_optional_json_func(path)
        if not isinstance(payload, dict):
            continue
        if run_id not in _list_strings(payload.get("run_ids")):
            continue
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            continue
        generated_at = str(payload.get("generated_at", "")).strip()
        candidate_key = (generated_at, str(path))
        if candidate_key >= latest_key:
            latest_key = candidate_key
            latest_session_id = session_id
            latest_report = payload
    if latest_session_id:
        cache[latest_session_id] = latest_report
    return latest_session_id, latest_report


def session_report_for_run(
    vault: Path,
    run_id: str,
    cache: dict[str, dict | None],
    run_cache: dict[str, tuple[str, dict | None]],
    *,
    load_optional_json_func: JsonLoader = load_optional_json,
) -> tuple[str, dict | None]:
    cached = run_cache.get(run_id)
    if cached is not None:
        return cached
    telemetry_rel = resolve_run_artifact_rel(vault, run_id, "run-telemetry.json") or f"runs/{run_id}/run-telemetry.json"
    telemetry = load_optional_json_func(vault / telemetry_rel)
    if not isinstance(telemetry, dict):
        run_cache[run_id] = ("", None)
        return run_cache[run_id]
    session_id = str(telemetry.get("session_id", "")).strip()
    if not session_id:
        run_cache[run_id] = _session_report_containing_run(
            vault,
            run_id,
            cache,
            load_optional_json_func=load_optional_json_func,
        )
        return run_cache[run_id]
    if session_id not in cache:
        session_rel = resolve_auto_improve_session_report_rel(vault, session_id) or (
            f"ops/reports/auto-improve-sessions/{session_id}.json"
        )
        cache[session_id] = load_optional_json_func(vault / session_rel)
    run_cache[run_id] = (session_id, cache[session_id])
    return run_cache[run_id]


def counter_has_positive_value(counter: object, key: str) -> bool:
    if not isinstance(counter, dict):
        return False
    try:
        return int(counter.get(key, 0)) > 0
    except (TypeError, ValueError):
        return False


def any_positive_counter_value(counter: object) -> bool:
    if not isinstance(counter, dict):
        return False
    for value in counter.values():
        try:
            if int(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _session_report_has_attempt_context(session_report: dict) -> bool:
    learning_summary = session_report.get("learning_summary", {})
    if not isinstance(learning_summary, dict):
        return True
    session_context_status = str(learning_summary.get("session_context_status", "")).strip()
    return session_context_status not in {
        "no_attempt_context",
        "no_iterations",
        "no_run_ids",
    }


def _accumulate_rollup_counters(
    counters: _SessionCalibrationCounters,
    session_report: dict,
) -> None:
    if not _session_report_has_attempt_context(session_report):
        return
    rollups = session_report.get("rollups", {})
    if not isinstance(rollups, dict):
        return
    counters.sessions_with_rollups += 1

    telemetry = rollups.get("telemetry", {})
    if isinstance(telemetry, dict):
        failure_counts = telemetry.get("failure_taxonomy_counts", {})
        if counter_has_positive_value(failure_counts, "validation_blocked"):
            counters.validation_blocked_sessions += 1
        if counter_has_positive_value(failure_counts, "review_blocked"):
            counters.review_blocked_sessions += 1
        if counter_has_positive_value(failure_counts, "mutation_failed"):
            counters.mutation_failed_sessions += 1

    executor = rollups.get("executor", {})
    if isinstance(executor, dict):
        role_counts = executor.get("role_counts", {})
        if counter_has_positive_value(role_counts, "validator"):
            counters.validator_dispatch_sessions += 1
        if counter_has_positive_value(role_counts, "reviewer"):
            counters.reviewer_dispatch_sessions += 1

    routing = rollups.get("routing", {})
    if isinstance(routing, dict) and any_positive_counter_value(
        routing.get("risk_flag_counts", {})
    ):
        counters.high_risk_routing_sessions += 1


def _accumulate_session_calibration_counters(
    vault: Path,
    candidate: dict,
    session_report_cache: dict[str, dict | None],
    run_session_cache: dict[str, tuple[str, dict | None]],
    *,
    load_optional_json_func: JsonLoader,
) -> tuple[_SessionCalibrationCounters, list[str]]:
    counters = _SessionCalibrationCounters()
    session_ids: list[str] = []
    seen_session_ids: set[str] = set()

    for run_id in candidate["run_ids"]:
        session_id, session_report = session_report_for_run(
            vault,
            run_id,
            session_report_cache,
            run_session_cache,
            load_optional_json_func=load_optional_json_func,
        )
        if not session_id:
            continue
        counters.runs_with_session_context += 1
        if session_id in seen_session_ids:
            continue
        seen_session_ids.add(session_id)
        session_ids.append(session_id)

        if isinstance(session_report, dict):
            _accumulate_rollup_counters(counters, session_report)

    return counters, session_ids


def _session_calibration_weighted_deltas(
    policy: dict,
    candidate: dict,
    counters: _SessionCalibrationCounters,
) -> dict[str, int]:
    family_adjustments = policy["mechanism_review"]["calibration"]["session_priority_adjustments"][
        "by_family"
    ][candidate["family"]]
    return {
        "validation_blocked_sessions": (
            int(family_adjustments["validation_blocked"]) * counters.validation_blocked_sessions
        ),
        "review_blocked_sessions": (
            int(family_adjustments["review_blocked"]) * counters.review_blocked_sessions
        ),
        "mutation_failed_sessions": (
            int(family_adjustments["mutation_failed"]) * counters.mutation_failed_sessions
        ),
        "validator_dispatch_sessions": (
            int(family_adjustments["validator_dispatch"]) * counters.validator_dispatch_sessions
        ),
        "reviewer_dispatch_sessions": (
            int(family_adjustments["reviewer_dispatch"]) * counters.reviewer_dispatch_sessions
        ),
        "high_risk_routing_sessions": (
            int(family_adjustments["high_risk_routing"]) * counters.high_risk_routing_sessions
        ),
    }


def _session_calibration_priority_delta(
    policy: dict,
    candidate: dict,
    counters: _SessionCalibrationCounters,
) -> tuple[int, int, int]:
    adjustments = policy["mechanism_review"]["calibration"]["session_priority_adjustments"]
    weighted_deltas = _session_calibration_weighted_deltas(policy, candidate, counters)
    positive_delta = min(
        sum(value for value in weighted_deltas.values() if value > 0),
        int(adjustments["positive_cap"]),
    )
    negative_delta = max(
        sum(value for value in weighted_deltas.values() if value < 0),
        -int(adjustments["negative_cap"]),
    )
    priority_before = int(candidate["priority"])
    priority_after = _clamp_priority(priority_before + positive_delta + negative_delta)
    return priority_before, priority_after - priority_before, priority_after


def session_calibration_summary(
    vault: Path,
    policy: dict,
    candidate: dict,
    session_report_cache: dict[str, dict | None],
    run_session_cache: dict[str, tuple[str, dict | None]],
    *,
    load_optional_json_func: JsonLoader = load_optional_json,
) -> dict:
    counters, session_ids = _accumulate_session_calibration_counters(
        vault,
        candidate,
        session_report_cache,
        run_session_cache,
        load_optional_json_func=load_optional_json_func,
    )
    priority_before, priority_delta, priority_after = _session_calibration_priority_delta(
        policy,
        candidate,
        counters,
    )
    return {
        "runs_with_session_context": counters.runs_with_session_context,
        "sessions_considered": len(session_ids),
        "sessions_with_rollups": counters.sessions_with_rollups,
        "validation_blocked_sessions": counters.validation_blocked_sessions,
        "review_blocked_sessions": counters.review_blocked_sessions,
        "mutation_failed_sessions": counters.mutation_failed_sessions,
        "validator_dispatch_sessions": counters.validator_dispatch_sessions,
        "reviewer_dispatch_sessions": counters.reviewer_dispatch_sessions,
        "high_risk_routing_sessions": counters.high_risk_routing_sessions,
        "priority_before_calibration": priority_before,
        "priority_delta": priority_delta,
        "priority_after_calibration": priority_after,
    }


def apply_session_calibration(
    vault: Path,
    policy: dict,
    candidate: dict,
    session_report_cache: dict[str, dict | None],
    run_session_cache: dict[str, tuple[str, dict | None]],
    *,
    load_optional_json_func: JsonLoader = load_optional_json,
) -> dict:
    calibration_policy = policy["mechanism_review"]["calibration"]
    if not calibration_policy["enabled"]:
        return candidate

    calibrated = dict(candidate)
    summary = session_calibration_summary(
        vault,
        policy,
        candidate,
        session_report_cache,
        run_session_cache,
        load_optional_json_func=load_optional_json_func,
    )
    calibrated["priority"] = summary["priority_after_calibration"]
    calibrated["session_calibration"] = summary
    return calibrated


def empty_session_calibration_diagnostics_entry(*, family: str | None = None) -> dict:
    payload: dict[str, object] = {
        "candidates_with_session_context": 0,
        "candidates_with_rollups": 0,
        "candidates_without_session_context": 0,
        "runs_with_session_context": 0,
        "sessions_considered": 0,
        "sessions_with_rollups": 0,
        "validation_blocked_sessions": 0,
        "review_blocked_sessions": 0,
        "mutation_failed_sessions": 0,
        "validator_dispatch_sessions": 0,
        "reviewer_dispatch_sessions": 0,
        "high_risk_routing_sessions": 0,
        "total_priority_delta": 0,
        "boosted_candidates": 0,
        "lowered_candidates": 0,
        "unchanged_candidates": 0,
    }
    if family is not None:
        payload["family"] = family
    return payload


def accumulate_session_calibration_diagnostics(target: dict, summary: dict) -> None:
    has_session_context = int(summary.get("runs_with_session_context", 0)) > 0
    has_rollups = int(summary.get("sessions_with_rollups", 0)) > 0
    target["candidates_with_session_context"] += 1 if has_session_context else 0
    target["candidates_with_rollups"] += 1 if has_rollups else 0
    target["candidates_without_session_context"] += 0 if has_session_context else 1
    for key in (
        "runs_with_session_context",
        "sessions_considered",
        "sessions_with_rollups",
        "validation_blocked_sessions",
        "review_blocked_sessions",
        "mutation_failed_sessions",
        "validator_dispatch_sessions",
        "reviewer_dispatch_sessions",
        "high_risk_routing_sessions",
    ):
        target[key] += int(summary.get(key, 0))
    priority_delta = int(summary.get("priority_delta", 0))
    target["total_priority_delta"] += priority_delta
    if priority_delta > 0:
        target["boosted_candidates"] += 1
    elif priority_delta < 0:
        target["lowered_candidates"] += 1
    else:
        target["unchanged_candidates"] += 1


def build_session_calibration_diagnostics(candidates: list[dict], *, enabled: bool) -> dict:
    if not enabled:
        aggregate = empty_session_calibration_diagnostics_entry()
        aggregate["enabled"] = False
        aggregate["status"] = "disabled"
        aggregate["candidate_count"] = 0
        aggregate["by_family"] = []
        return aggregate

    aggregate = empty_session_calibration_diagnostics_entry()
    by_family: dict[str, dict] = {}
    for candidate in candidates:
        summary = candidate.get("session_calibration")
        if not isinstance(summary, dict):
            continue
        accumulate_session_calibration_diagnostics(aggregate, summary)
        family = str(candidate.get("family", "")).strip() or "<unknown>"
        family_entry = by_family.setdefault(
            family,
            empty_session_calibration_diagnostics_entry(family=family),
        )
        accumulate_session_calibration_diagnostics(family_entry, summary)

    if not candidates:
        status = "no_candidates"
    elif aggregate["candidates_with_session_context"] == 0:
        status = "no_session_context"
    else:
        status = "active"
    aggregate["enabled"] = True
    aggregate["status"] = status
    aggregate["candidate_count"] = len(candidates)
    aggregate["by_family"] = [by_family[key] for key in sorted(by_family)]
    return aggregate
