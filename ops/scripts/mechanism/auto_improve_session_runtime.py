from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any, TypedDict

from ops.scripts.core.observability_artifacts_shared_runtime import (
    resolve_run_artifact_rel,
    run_artifact_glob_rels,
)
from ops.scripts.core.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_outcome,
    decision_record_from_report,
)

from .auto_improve_next_run_decision_runtime import normalize_next_run_decisions
from .auto_improve_session_completion_runtime import completion_class_for_session

TERMINAL_NON_BLOCKING_OUTCOMES = frozenset({"promoted"})
TERMINAL_SUCCESS_OUTCOMES = frozenset({"promoted"})
SESSION_CONTEXT_AVAILABLE = "session_context_available"
SESSION_CONTEXT_PARTIAL = "partial_context"
SESSION_CONTEXT_MISSING = "no_attempt_context"
SESSION_CONTEXT_EMPTY = "no_iterations"
SESSION_CONTEXT_NO_RUNS = "no_run_ids"
DEFAULT_RECENT_WINDOW = 20
ROLLBACK_LEDGER_EVENT_TYPES = frozenset(
    {
        "rollback",
        "rollback_applied",
        "rollback_required",
        "live_apply_rollback",
    }
)


class AttemptRecord(TypedDict):
    position: int
    session_id: str
    run_id: str
    proposal_id: str
    source_candidate_id: str
    observed_at: str
    status: str
    outcome: str
    decision: str
    primary_targets: list[str]
    rework_key: str
    phase_durations: dict[str, float]
    executor_roles: list[str]
    executor_report_count: int
    rollback_rehearsal_report: str
    rollback_rehearsal_covered: bool
    rollback_signal: bool
    run_telemetry: str


class ReworkKeyRollup(TypedDict):
    key: str
    attempt_count: int
    rework_count: int
    run_ids: list[str]


class DefectEscapePair(TypedDict):
    target: str
    promoted_run_id: str
    escaped_run_id: str
    escaped_decision: str
    escaped_outcome: str


class OutcomeOperatorEffortProxy(TypedDict):
    phase_totals_seconds: dict[str, float]
    executor_report_count: int
    reviewer_dispatch_count: int
    validator_dispatch_count: int
    auditor_dispatch_count: int
    hold_count: int


class OutcomeMetricsRollup(TypedDict):
    attempt_count: int
    recent_window: int
    recent_attempt_count: int
    rework_count: int
    rollback_signal_count: int
    rollback_rehearsal_coverage_count: int
    moving_averages: dict[str, float]
    operator_effort_proxy: OutcomeOperatorEffortProxy
    rework_keys: list[ReworkKeyRollup]
    defect_escape_proxy: dict[str, int | list[DefectEscapePair]]


def increment_counter(counter: dict[str, int], key: object) -> None:
    normalized = str(key).strip()
    if not normalized:
        return
    counter[normalized] = counter.get(normalized, 0) + 1


def load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def dict_value(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _existing_rel_path(vault: Path, value: object) -> str:
    rel_path = str(value).strip()
    if not rel_path:
        return ""
    path = Path(rel_path)
    if path.is_absolute():
        return ""
    candidate = vault / path
    return rel_path if candidate.exists() else ""


def _list_existing_rel_paths(vault: Path, value: object) -> list[str]:
    seen: set[str] = set()
    rel_paths: list[str] = []
    for item in list_strings(value):
        rel_path = _existing_rel_path(vault, item)
        if not rel_path or rel_path in seen:
            continue
        seen.add(rel_path)
        rel_paths.append(rel_path)
    return rel_paths


def _decision_from_promotion_report(vault: Path, rel_path: str) -> str:
    if not rel_path:
        return ""
    promotion = load_optional_json(vault / rel_path)
    if not isinstance(promotion, dict):
        return ""
    try:
        return str(decision_record_from_report(promotion, require_record=False)["decision"]).strip()
    except PromotionDecisionRegistryError:
        return str(promotion.get("decision", "")).strip()


def _decision_outcome(decision: str) -> str:
    try:
        return str(decision_outcome(decision)).strip()
    except PromotionDecisionRegistryError:
        return ""


def _role_from_executor_report_path(rel_path: str) -> str:
    name = Path(rel_path).name
    if name.endswith("-executor-report.json"):
        return name.removesuffix("-executor-report.json")
    return ""


def _routing_report_paths(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> list[str]:
    rel_paths = [
        rel_path
        for rel_path in _list_existing_rel_paths(vault, iteration.get("routing_reports"))
        if isinstance(load_optional_json(vault / rel_path), dict)
    ]
    if rel_paths:
        return rel_paths
    rel_paths = [
        rel_path
        for rel_path in _list_existing_rel_paths(vault, telemetry.get("routing_reports"))
        if isinstance(load_optional_json(vault / rel_path), dict)
    ]
    if rel_paths:
        return rel_paths
    return [
        rel_path
        for rel_path in run_artifact_glob_rels(vault, run_id, "subagent-routing.*.json")
        if isinstance(load_optional_json(vault / rel_path), dict)
    ]


def _executor_report_paths(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> list[str]:
    rel_paths = [
        rel_path
        for rel_path in _list_existing_rel_paths(vault, iteration.get("executor_reports"))
        if isinstance(load_optional_json(vault / rel_path), dict)
    ]
    if rel_paths:
        return rel_paths
    rel_paths = [
        rel_path
        for rel_path in _list_existing_rel_paths(vault, telemetry.get("executor_reports"))
        if isinstance(load_optional_json(vault / rel_path), dict)
    ]
    if rel_paths:
        return rel_paths
    return [
        rel_path
        for rel_path in run_artifact_glob_rels(vault, run_id, "*-executor-report.json")
        if isinstance(load_optional_json(vault / rel_path), dict)
    ]


def _executor_roles(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> list[str]:
    roles: list[str] = []
    for rel_path in _executor_report_paths(vault, run_id, telemetry, iteration):
        role = ""
        report = load_optional_json(vault / rel_path)
        if isinstance(report, dict):
            role = str(report.get("role", "")).strip()
        if not role:
            role = _role_from_executor_report_path(rel_path)
        if role:
            roles.append(role)
    return roles


def _scope_freeze_inputs(vault: Path, scope_freeze_rel: str) -> dict:
    scope_freeze = load_optional_json(vault / scope_freeze_rel)
    if not isinstance(scope_freeze, dict):
        return {}
    return dict_value(scope_freeze.get("inputs"))


def _primary_targets(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> list[str]:
    targets = list_strings(iteration.get("primary_targets"))
    if targets:
        return targets
    targets = list_strings(telemetry.get("primary_targets"))
    if targets:
        return targets
    scope_freeze_rel = _scope_freeze_rel(vault, run_id, telemetry, iteration)
    if not scope_freeze_rel:
        return []
    return list_strings(_scope_freeze_inputs(vault, scope_freeze_rel).get("primary_targets"))


def _rollback_rehearsal_rel(vault: Path, run_id: str, telemetry: dict) -> str:
    rel_path = str(telemetry.get("rollback_rehearsal_report", "")).strip()
    if rel_path and not Path(rel_path).is_absolute() and (vault / rel_path).is_file():
        return rel_path
    return resolve_run_artifact_rel(vault, run_id, "rollback-rehearsal-report.json")


def _rollback_signal_from_rehearsal(vault: Path, rel_path: str) -> bool:
    if not rel_path:
        return False
    report = load_optional_json(vault / rel_path)
    if not isinstance(report, dict):
        return False
    status = str(report.get("status", "")).strip()
    return bool(status and status != "pass")


def _rollback_signal_from_ledger(vault: Path, run_id: str) -> bool:
    ledger_rel = resolve_run_artifact_rel(vault, run_id, "run-ledger.json")
    ledger = load_optional_json(vault / ledger_rel) if ledger_rel else None
    if not isinstance(ledger, dict):
        return False
    events = ledger.get("events", [])
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type", "")).strip()
        decision = str(event.get("decision", "")).strip()
        if event_type in ROLLBACK_LEDGER_EVENT_TYPES or decision == "rollback":
            return True
    return False


def _rework_key(proposal_id: str, primary_targets: list[str]) -> str:
    if proposal_id:
        return f"proposal:{proposal_id}"
    if primary_targets:
        return "targets:" + "|".join(sorted(primary_targets))
    return ""


def _phase_durations(telemetry: dict) -> dict[str, float]:
    durations: dict[str, float] = {}
    for phase, value in dict_value(telemetry.get("phase_durations")).items():
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        durations[str(phase)] = round(duration, 3)
    return durations


def _run_telemetry_rel(vault: Path, run_id: str, iteration: dict) -> str:
    iteration_rel = _existing_rel_path(vault, iteration.get("run_telemetry"))
    if iteration_rel:
        return iteration_rel
    return resolve_run_artifact_rel(vault, run_id, "run-telemetry.json")


def _proposal_snapshot_rel(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> str:
    return (
        _existing_rel_path(vault, iteration.get("proposal_snapshot"))
        or _existing_rel_path(vault, telemetry.get("proposal_snapshot"))
        or resolve_run_artifact_rel(vault, run_id, "proposal-snapshot.json")
    )


def _source_candidate_id(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> str:
    candidate_id = str(iteration.get("source_candidate_id") or telemetry.get("source_candidate_id", "")).strip()
    if candidate_id:
        return candidate_id
    proposal_snapshot_rel = _proposal_snapshot_rel(vault, run_id, telemetry, iteration)
    proposal_snapshot = load_optional_json(vault / proposal_snapshot_rel) if proposal_snapshot_rel else None
    proposal = proposal_snapshot.get("proposal") if isinstance(proposal_snapshot, dict) else None
    if isinstance(proposal, dict):
        return str(proposal.get("source_candidate_id", "")).strip()
    return ""


def _scope_freeze_rel(vault: Path, run_id: str, telemetry: dict, iteration: dict) -> str:
    return (
        _existing_rel_path(vault, iteration.get("scope_freeze"))
        or _existing_rel_path(vault, telemetry.get("scope_freeze"))
        or resolve_run_artifact_rel(vault, run_id, "scope-freeze.json")
    )


def _promotion_report_rel(vault: Path, run_id: str, iteration: dict) -> str:
    return (
        _existing_rel_path(vault, iteration.get("promotion_report"))
        or resolve_run_artifact_rel(vault, run_id, "promotion-report.json")
    )


def _run_telemetry(vault: Path, run_id: str, iteration: dict) -> tuple[str, dict]:
    rel_path = _run_telemetry_rel(vault, run_id, iteration)
    payload = load_optional_json(vault / rel_path) if rel_path else None
    return rel_path, payload if isinstance(payload, dict) else {}


def _normalized_decision(vault: Path, run_id: str, iteration: dict, telemetry: dict) -> str:
    decision = str(iteration.get("decision", "")).strip()
    if decision:
        return decision
    decision = str(telemetry.get("decision", "")).strip()
    if decision:
        return decision
    return _decision_from_promotion_report(vault, _promotion_report_rel(vault, run_id, iteration))


def _failure_taxonomy(iteration: dict, telemetry: dict, outcome: str) -> str:
    failure_taxonomy = str(iteration.get("failure_taxonomy", "")).strip()
    if failure_taxonomy:
        return failure_taxonomy
    failure_taxonomy = str(telemetry.get("failure_taxonomy", "")).strip()
    if failure_taxonomy:
        return failure_taxonomy
    return outcome if outcome and outcome not in TERMINAL_SUCCESS_OUTCOMES else ""


def _normalized_outcome(vault: Path, run_id: str, iteration: dict, telemetry: dict) -> str:
    outcome = str(iteration.get("outcome", "")).strip()
    if outcome:
        return outcome
    failure_taxonomy = str(telemetry.get("failure_taxonomy", "")).strip()
    if failure_taxonomy:
        return failure_taxonomy
    return _decision_outcome(_normalized_decision(vault, run_id, iteration, telemetry))


def _normalized_status(iteration: dict, outcome: str) -> str:
    status = str(iteration.get("status", "")).strip()
    if status:
        return status
    return "complete" if outcome in TERMINAL_SUCCESS_OUTCOMES else "blocked"


def _normalized_iteration(
    vault: Path,
    *,
    session: dict,
    iteration: dict,
    position: int,
    run_ids: list[str],
    quarantined_proposal_ids: set[str],
) -> dict[str, Any]:
    run_id = str(iteration.get("run_id", "")).strip()
    if not run_id and position <= len(run_ids):
        run_id = run_ids[position - 1]
    telemetry_rel, telemetry = _run_telemetry(vault, run_id, iteration)
    proposal_id = str(iteration.get("proposal_id") or telemetry.get("proposal_id", "")).strip()
    source_candidate_id = _source_candidate_id(vault, run_id, telemetry, iteration)
    decision = _normalized_decision(vault, run_id, iteration, telemetry)
    outcome = _normalized_outcome(vault, run_id, iteration, telemetry)
    return {
        "index": int(iteration.get("index", position) or position),
        "proposal_id": proposal_id,
        "source_candidate_id": source_candidate_id,
        "run_id": run_id,
        "status": _normalized_status(iteration, outcome),
        "decision": decision,
        "outcome": outcome,
        "failure_taxonomy": _failure_taxonomy(iteration, telemetry, outcome),
        "proposal_snapshot": _proposal_snapshot_rel(vault, run_id, telemetry, iteration),
        "scope_freeze": _scope_freeze_rel(vault, run_id, telemetry, iteration),
        "routing_reports": _routing_report_paths(vault, run_id, telemetry, iteration),
        "executor_reports": _executor_report_paths(vault, run_id, telemetry, iteration),
        "run_telemetry": telemetry_rel,
        "promotion_report": _promotion_report_rel(vault, run_id, iteration),
        "quarantined": bool(iteration.get("quarantined")) or proposal_id in quarantined_proposal_ids,
        "primary_targets": _primary_targets(vault, run_id, telemetry, iteration),
    }


def normalize_session_iterations(vault: Path, session: dict) -> list[dict[str, Any]]:
    iterations: list[dict[str, Any]] = []
    run_ids = list_strings(session.get("run_ids"))
    quarantined_proposal_ids = set(list_strings(session.get("quarantined_proposal_ids")))
    for position, iteration in enumerate(session.get("iterations", []), start=1):
        if not isinstance(iteration, dict):
            continue
        iterations.append(
            _normalized_iteration(
                vault,
                session=session,
                iteration=iteration,
                position=position,
                run_ids=run_ids,
                quarantined_proposal_ids=quarantined_proposal_ids,
            )
        )
    return iterations


def build_learning_summary(
    vault: Path,
    session: dict,
    *,
    recent_window: int = DEFAULT_RECENT_WINDOW,
) -> dict[str, Any]:
    normalized_iterations = normalize_session_iterations(vault, session)
    normalized_session = dict(session)
    normalized_session["iterations"] = normalized_iterations
    normalized_session["run_ids"] = list_strings(session.get("run_ids"))
    metrics = build_outcome_metrics_from_attempts(
        build_attempt_records(vault, normalized_session),
        recent_window=recent_window,
    )
    defect_escape_proxy = metrics.get("defect_escape_proxy", {})
    defect_escape_pair_count = 0
    if isinstance(defect_escape_proxy, dict):
        count_value = defect_escape_proxy.get("count", 0)
        if isinstance(count_value, int):
            defect_escape_pair_count = count_value
    evidence_gaps: list[str] = []
    if not normalized_iterations:
        evidence_gaps.append("session.iterations is empty")
    if not normalized_session["run_ids"]:
        evidence_gaps.append("session.run_ids is empty")
    if int(metrics.get("attempt_count", 0) or 0) == 0:
        evidence_gaps.append("no attempt records could be reconstructed from session iterations")
    missing_run_telemetry = sum(1 for item in normalized_iterations if not item.get("run_telemetry"))
    if missing_run_telemetry:
        evidence_gaps.append(f"{missing_run_telemetry} iteration(s) are missing run_telemetry")
    if not normalized_iterations:
        session_context_status = SESSION_CONTEXT_EMPTY
    elif not normalized_session["run_ids"]:
        session_context_status = SESSION_CONTEXT_NO_RUNS
    elif int(metrics.get("attempt_count", 0) or 0) == 0:
        session_context_status = SESSION_CONTEXT_MISSING
    elif evidence_gaps:
        session_context_status = SESSION_CONTEXT_PARTIAL
    else:
        session_context_status = SESSION_CONTEXT_AVAILABLE
    return {
        "attempt_count": int(metrics.get("attempt_count", 0) or 0),
        "rework_count": int(metrics.get("rework_count", 0) or 0),
        "rollback_signal_count": int(metrics.get("rollback_signal_count", 0) or 0),
        "defect_escape_pair_count": defect_escape_pair_count,
        "session_context_status": session_context_status,
        "evidence_gaps": evidence_gaps,
    }


def normalize_session_report(vault: Path, session: dict) -> dict[str, Any]:
    normalized = dict(session)
    normalized["attempted_proposal_ids"] = list_strings(session.get("attempted_proposal_ids"))
    normalized["quarantined_proposal_ids"] = list_strings(session.get("quarantined_proposal_ids"))
    normalized["run_ids"] = list_strings(session.get("run_ids"))
    normalized["queue_snapshot"] = list_strings(session.get("queue_snapshot"))
    normalized["iterations"] = normalize_session_iterations(vault, session)
    normalized["next_run_decisions"] = normalize_next_run_decisions(
        session.get("next_run_decisions")
    )
    normalized["learning_summary"] = build_learning_summary(vault, normalized)
    if str(normalized.get("status", "")).strip() == "complete":
        normalized["completion_class"] = completion_class_for_session(
            normalized,
            stop_reason=str(normalized.get("stop_reason", "")).strip(),
        )
    return normalized


def build_attempt_records(vault: Path, session: dict) -> list[AttemptRecord]:
    attempts: list[AttemptRecord] = []
    run_ids = list_strings(session.get("run_ids"))
    for position, iteration in enumerate(session.get("iterations", []), start=1):
        if not isinstance(iteration, dict):
            continue
        run_id = str(iteration.get("run_id", "")).strip()
        if not run_id and position <= len(run_ids):
            run_id = run_ids[position - 1]
        if not run_id:
            continue
        telemetry_rel, telemetry = _run_telemetry(vault, run_id, iteration)
        proposal_id = str(
            iteration.get("proposal_id") or telemetry.get("proposal_id", "")
        ).strip()
        source_candidate_id = _source_candidate_id(vault, run_id, telemetry, iteration)
        decision = _normalized_decision(vault, run_id, iteration, telemetry)
        outcome = _normalized_outcome(vault, run_id, iteration, telemetry)
        primary_targets = _primary_targets(vault, run_id, telemetry, iteration)
        rollback_rehearsal = _rollback_rehearsal_rel(vault, run_id, telemetry)
        rollback_signal = _rollback_signal_from_rehearsal(vault, rollback_rehearsal)
        rollback_signal = rollback_signal or _rollback_signal_from_ledger(vault, run_id)
        attempts.append(
            {
                "position": int(iteration.get("index", position) or position),
                "session_id": str(session.get("session_id", "")).strip(),
                "run_id": run_id,
                "proposal_id": proposal_id,
                "source_candidate_id": source_candidate_id,
                "observed_at": str(telemetry.get("generated_at", "")).strip(),
                "status": _normalized_status(iteration, outcome),
                "outcome": outcome,
                "decision": decision,
                "primary_targets": primary_targets,
                "rework_key": _rework_key(proposal_id, primary_targets),
                "phase_durations": _phase_durations(telemetry),
                "executor_roles": _executor_roles(vault, run_id, telemetry, iteration),
                "executor_report_count": len(_executor_report_paths(vault, run_id, telemetry, iteration)),
                "rollback_rehearsal_report": rollback_rehearsal,
                "rollback_rehearsal_covered": bool(rollback_rehearsal),
                "rollback_signal": rollback_signal,
                "run_telemetry": telemetry_rel,
            }
        )
    return attempts


def _rework_key_rollups(attempts: list[AttemptRecord]) -> tuple[int, list[ReworkKeyRollup]]:
    grouped: dict[str, list[AttemptRecord]] = {}
    for attempt in attempts:
        key = str(attempt.get("rework_key", "")).strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(attempt)
    rework_keys: list[ReworkKeyRollup] = []
    rework_count = 0
    for key in sorted(grouped):
        group = grouped[key]
        if len(group) <= 1:
            continue
        current_rework = len(group) - 1
        rework_count += current_rework
        rework_keys.append(
            {
                "key": key,
                "attempt_count": len(group),
                "rework_count": current_rework,
                "run_ids": [str(item["run_id"]) for item in group],
            }
        )
    return rework_count, rework_keys


def _blocking_attempt(attempt: AttemptRecord) -> bool:
    decision = str(attempt.get("decision", "")).strip()
    outcome = str(attempt.get("outcome", "")).strip()
    if decision in {"HOLD", "DISCARD"}:
        return True
    return bool(outcome and outcome not in TERMINAL_NON_BLOCKING_OUTCOMES)


def _defect_escape_pairs(attempts: list[AttemptRecord]) -> list[DefectEscapePair]:
    pairs: list[DefectEscapePair] = []
    promoted_by_target: dict[str, AttemptRecord] = {}
    ordered = sorted(
        attempts,
        key=lambda item: (
            str(item.get("observed_at", "")),
            str(item.get("session_id", "")),
            int(item.get("position", 0)),
            str(item.get("run_id", "")),
        ),
    )
    for attempt in ordered:
        decision = str(attempt.get("decision", "")).strip()
        outcome = str(attempt.get("outcome", "")).strip()
        targets = list_strings(attempt.get("primary_targets"))
        if decision == "PROMOTE" or outcome == "promoted":
            for target in targets:
                promoted_by_target[target] = attempt
            continue
        if not _blocking_attempt(attempt):
            continue
        for target in targets:
            promoted = promoted_by_target.get(target)
            if promoted is None:
                continue
            pairs.append(
                {
                    "target": target,
                    "promoted_run_id": str(promoted.get("run_id", "")),
                    "escaped_run_id": str(attempt.get("run_id", "")),
                    "escaped_decision": decision,
                    "escaped_outcome": outcome,
                }
            )
    return pairs


def _operator_effort_proxy(attempts: list[AttemptRecord]) -> OutcomeOperatorEffortProxy:
    phase_totals: dict[str, float] = {}
    executor_report_count = 0
    reviewer_dispatch_count = 0
    validator_dispatch_count = 0
    auditor_dispatch_count = 0
    hold_count = 0
    for attempt in attempts:
        for phase, value in dict_value(attempt.get("phase_durations")).items():
            try:
                duration = float(value)
            except (TypeError, ValueError):
                continue
            phase_totals[str(phase)] = round(phase_totals.get(str(phase), 0.0) + duration, 3)
        with suppress(TypeError, ValueError):
            executor_report_count += int(attempt.get("executor_report_count", 0))
        for role in list_strings(attempt.get("executor_roles")):
            if role == "reviewer":
                reviewer_dispatch_count += 1
            elif role == "validator":
                validator_dispatch_count += 1
            elif role.endswith("auditor"):
                auditor_dispatch_count += 1
        if str(attempt.get("decision", "")).strip() == "HOLD":
            hold_count += 1
    return {
        "phase_totals_seconds": phase_totals,
        "executor_report_count": executor_report_count,
        "reviewer_dispatch_count": reviewer_dispatch_count,
        "validator_dispatch_count": validator_dispatch_count,
        "auditor_dispatch_count": auditor_dispatch_count,
        "hold_count": hold_count,
    }


def _ratio(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(count / denominator, 4)


def build_outcome_metrics_from_attempts(
    attempts: list[AttemptRecord],
    *,
    recent_window: int = DEFAULT_RECENT_WINDOW,
) -> OutcomeMetricsRollup:
    ordered = sorted(
        attempts,
        key=lambda item: (
            str(item.get("observed_at", "")),
            str(item.get("session_id", "")),
            int(item.get("position", 0)),
            str(item.get("run_id", "")),
        ),
    )
    recent = ordered[-recent_window:]
    recent_count = len(recent)
    rework_count, rework_keys = _rework_key_rollups(ordered)
    rollback_signal_count = sum(1 for item in ordered if bool(item.get("rollback_signal")))
    rollback_rehearsal_coverage_count = sum(
        1 for item in ordered if bool(item.get("rollback_rehearsal_covered"))
    )
    defect_pairs = _defect_escape_pairs(ordered)
    return {
        "attempt_count": len(ordered),
        "recent_window": recent_window,
        "recent_attempt_count": recent_count,
        "rework_count": rework_count,
        "rollback_signal_count": rollback_signal_count,
        "rollback_rehearsal_coverage_count": rollback_rehearsal_coverage_count,
        "moving_averages": {
            "hold": _ratio(
                sum(1 for item in recent if str(item.get("decision", "")).strip() == "HOLD"),
                recent_count,
            ),
            "discard": _ratio(
                sum(1 for item in recent if str(item.get("decision", "")).strip() == "DISCARD"),
                recent_count,
            ),
            "rollback_signal": _ratio(
                sum(1 for item in recent if bool(item.get("rollback_signal"))),
                recent_count,
            ),
        },
        "operator_effort_proxy": _operator_effort_proxy(ordered),
        "rework_keys": rework_keys,
        "defect_escape_proxy": {
            "count": len(defect_pairs),
            "pairs": defect_pairs,
        },
    }


def build_outcome_metrics_rollup(vault: Path, session: dict) -> OutcomeMetricsRollup:
    return build_outcome_metrics_from_attempts(build_attempt_records(vault, session))


def build_iteration_rollup(session: dict) -> dict:
    outcome_counts: dict[str, int] = {}
    decision_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    valid_iterations = []
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        valid_iterations.append(iteration)
        increment_counter(outcome_counts, iteration.get("outcome", ""))
        increment_counter(decision_counts, iteration.get("decision", ""))
        increment_counter(status_counts, iteration.get("status", ""))
    return {
        "count": len(valid_iterations),
        "outcome_counts": outcome_counts,
        "decision_counts": decision_counts,
        "status_counts": status_counts,
        "quarantined_proposal_count": len(session.get("quarantined_proposal_ids", [])),
    }


def build_routing_rollup(vault: Path, run_ids: list[str]) -> dict:
    role_counts: dict[str, int] = {}
    selected_rung_counts: dict[str, int] = {}
    score_band_counts: dict[str, int] = {}
    sandbox_mode_counts: dict[str, int] = {}
    model_counts: dict[str, int] = {}
    reasoning_effort_counts: dict[str, int] = {}
    risk_flag_counts: dict[str, int] = {}
    report_count = 0

    for run_id in run_ids:
        for rel_path in run_artifact_glob_rels(vault, run_id, "subagent-routing.*.json"):
            report = load_optional_json(vault / rel_path)
            if not isinstance(report, dict):
                continue
            report_count += 1
            increment_counter(role_counts, report.get("role", ""))
            routing_decision = report.get("routing_decision", {})
            if isinstance(routing_decision, dict):
                increment_counter(selected_rung_counts, routing_decision.get("selected_rung", ""))
                increment_counter(score_band_counts, routing_decision.get("score_band", ""))
                increment_counter(sandbox_mode_counts, routing_decision.get("sandbox_mode", ""))
                increment_counter(model_counts, routing_decision.get("model", ""))
                increment_counter(reasoning_effort_counts, routing_decision.get("reasoning_effort", ""))
            complexity_profile = report.get("complexity_profile", {})
            if isinstance(complexity_profile, dict):
                for flag in report.get("complexity_profile", {}).get("risk_flags", []):
                    increment_counter(risk_flag_counts, flag)

    return {
        "report_count": report_count,
        "role_counts": role_counts,
        "selected_rung_counts": selected_rung_counts,
        "score_band_counts": score_band_counts,
        "sandbox_mode_counts": sandbox_mode_counts,
        "model_counts": model_counts,
        "reasoning_effort_counts": reasoning_effort_counts,
        "risk_flag_counts": risk_flag_counts,
    }


def build_executor_rollup(vault: Path, run_ids: list[str]) -> dict:
    role_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    blocking_role_counts: dict[str, int] = {}
    returncode_counts: dict[str, int] = {}
    report_count = 0

    for run_id in run_ids:
        for rel_path in run_artifact_glob_rels(vault, run_id, "*-executor-report.json"):
            report = load_optional_json(vault / rel_path)
            if not isinstance(report, dict):
                continue
            report_count += 1
            role = str(report.get("role", "")).strip()
            status = str(report.get("status", "")).strip()
            returncode = ""
            result = report.get("result", {})
            if isinstance(result, dict):
                returncode = str(result.get("returncode", "")).strip()
            increment_counter(role_counts, role)
            increment_counter(status_counts, status)
            increment_counter(returncode_counts, returncode)
            if status and status != "pass":
                increment_counter(blocking_role_counts, role)

    return {
        "report_count": report_count,
        "role_counts": role_counts,
        "status_counts": status_counts,
        "blocking_role_counts": blocking_role_counts,
        "returncode_counts": returncode_counts,
    }


def build_telemetry_rollup(vault: Path, run_ids: list[str]) -> dict:
    failure_taxonomy_counts: dict[str, int] = {}
    phase_totals_seconds: dict[str, float] = {}
    phase_max_seconds: dict[str, float] = {}
    report_count = 0

    for run_id in run_ids:
        telemetry_rel = resolve_run_artifact_rel(vault, run_id, "run-telemetry.json")
        report = load_optional_json(vault / telemetry_rel) if telemetry_rel else None
        if not isinstance(report, dict):
            continue
        report_count += 1
        increment_counter(failure_taxonomy_counts, report.get("failure_taxonomy", ""))
        phase_durations = report.get("phase_durations", {})
        if not isinstance(phase_durations, dict):
            continue
        for phase, value in phase_durations.items():
            try:
                duration = float(value)
            except (TypeError, ValueError):
                continue
            phase_totals_seconds[phase] = round(phase_totals_seconds.get(phase, 0.0) + duration, 3)
            phase_max_seconds[phase] = round(max(phase_max_seconds.get(phase, 0.0), duration), 3)

    return {
        "report_count": report_count,
        "failure_taxonomy_counts": failure_taxonomy_counts,
        "phase_totals_seconds": phase_totals_seconds,
        "phase_max_seconds": phase_max_seconds,
    }


def build_session_rollups(vault: Path, session: dict) -> dict:
    run_ids = list_strings(session.get("run_ids", []))
    return {
        "iterations": build_iteration_rollup(session),
        "routing": build_routing_rollup(vault, run_ids),
        "executor": build_executor_rollup(vault, run_ids),
        "telemetry": build_telemetry_rollup(vault, run_ids),
        "outcome_metrics": build_outcome_metrics_rollup(vault, session),
    }
