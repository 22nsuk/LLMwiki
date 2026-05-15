from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict, cast

from ops.scripts.auto_improve_session_runtime import (
    AttemptRecord,
    build_attempt_records,
    build_outcome_metrics_from_attempts,
    list_strings,
)
from .artifact_freshness_runtime import build_canonical_report_envelope
from .observability_artifacts_shared_runtime import (
    increment,
    load_optional_json,
    resolve_run_artifact_rel,
    write_schema_backed_json,
)
from .policy_runtime import report_path
from .promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_is_terminal,
    decision_outcome,
    decision_record_from_report,
)
from .runtime_context import RuntimeContext
from .schema_constants_runtime import (
    OUTCOME_METRICS_SCHEMA_PATH,
    PROMOTION_DECISION_TRENDS_SCHEMA_PATH,
)


PROMOTION_DECISION_TRENDS = PROMOTION_DECISION_TRENDS_SCHEMA_PATH
PROMOTION_DECISION_TRENDS_REPORT = "ops/reports/promotion-decision-trends.json"
PROMOTION_DECISION_TRENDS_PRODUCER = "ops.scripts.observability_decision_metrics_runtime"
PROMOTION_DECISION_TRENDS_SOURCE_COMMAND = "python -m ops.scripts.run_mechanism_experiment --vault ."
OUTCOME_METRICS = OUTCOME_METRICS_SCHEMA_PATH
OUTCOME_METRICS_REPORT = "ops/reports/outcome-metrics.json"
DEFECT_ESCAPE_CLOSURES_REPORT = "ops/reports/defect-escape-closures.json"
REWORK_CLOSURES_REPORT = "ops/reports/rework-closures.json"
OUTCOME_METRICS_PRODUCER = "ops.scripts.observability_decision_metrics_runtime"
OUTCOME_METRICS_SOURCE_COMMAND = (
    "python -m ops.scripts.outcome_metrics "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)


class OutcomeMetricsAttemptEntry(TypedDict):
    run_id: str
    session_id: str
    proposal_id: str
    source_candidate_id: str
    observed_at: str
    decision: str
    outcome: str
    primary_targets: list[str]
    rework_key: str
    rollback_rehearsal_covered: bool
    rollback_signal: bool
    run_telemetry: str
    promotion_report: str


class SessionDecisionMetricsSummary(TypedDict):
    attempt_count: int
    rework_count: int
    rollback_signal_count: int
    rollback_rehearsal_coverage_count: int
    defect_escape_count: int
    finalized_run_count: int
    moving_averages: dict[str, float]


def _run_observed_at(vault: Path, run_id: str) -> str:
    ledger_rel = resolve_run_artifact_rel(vault, run_id, "run-ledger.json")
    ledger = load_optional_json(vault / ledger_rel) if ledger_rel else None
    if isinstance(ledger, dict):
        events = ledger.get("events", [])
        if isinstance(events, list):
            for event in reversed(events):
                if isinstance(event, dict) and isinstance(event.get("ts"), str):
                    return event["ts"]
    telemetry_rel = resolve_run_artifact_rel(vault, run_id, "run-telemetry.json")
    telemetry = load_optional_json(vault / telemetry_rel) if telemetry_rel else None
    if isinstance(telemetry, dict) and isinstance(telemetry.get("generated_at"), str):
        return telemetry["generated_at"]
    return ""


def _run_finalized(vault: Path, run_id: str) -> bool:
    telemetry_rel = resolve_run_artifact_rel(vault, run_id, "run-telemetry.json")
    telemetry = load_optional_json(vault / telemetry_rel) if telemetry_rel else None
    if isinstance(telemetry, dict) and isinstance(telemetry.get("finalized"), bool):
        return bool(telemetry["finalized"])
    ledger_rel = resolve_run_artifact_rel(vault, run_id, "run-ledger.json")
    ledger = load_optional_json(vault / ledger_rel) if ledger_rel else None
    return bool(isinstance(ledger, dict) and ledger.get("status") == "complete")


def build_promotion_decision_trends(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    context: RuntimeContext,
    recent_window: int = 20,
) -> dict:
    generated_at = context.isoformat_z()
    runs_dir = vault / "runs"
    run_dirs = sorted(item for item in runs_dir.glob("*") if item.is_dir()) if runs_dir.exists() else []
    promotion_report_paths: list[str] = []
    decision_counts: dict[str, int] = {}
    artifact_class_counts: dict[str, int] = {}
    finalized_count = 0
    recent_runs = []
    for run_dir in run_dirs:
        promotion_path = run_dir / "promotion-report.json"
        promotion = load_optional_json(promotion_path)
        if not isinstance(promotion, dict):
            continue
        promotion_report_paths.append(report_path(vault, promotion_path))
        run_id = str(promotion.get("run_id") or run_dir.name)
        decision_record = decision_record_from_report(promotion, require_record=False)
        decision = str(decision_record["decision"]).strip()
        artifact_class = str(promotion.get("artifact_class", "")).strip()
        primary_targets = promotion.get("primary_targets", [])
        if not isinstance(primary_targets, list):
            primary_targets = []
        increment(decision_counts, decision)
        increment(artifact_class_counts, artifact_class)
        finalized = _run_finalized(vault, run_id)
        if finalized:
            finalized_count += 1
        recent_runs.append(
            {
                "run_id": run_id,
                "observed_at": _run_observed_at(vault, run_id),
                "decision": decision,
                "decision_record": decision_record,
                "artifact_class": artifact_class,
                "primary_targets": [str(item) for item in primary_targets],
                "finalized": finalized,
                "promotion_report": report_path(vault, promotion_path),
            }
        )
    recent_runs.sort(key=lambda item: (item["observed_at"], item["run_id"]), reverse=True)
    recent_runs = recent_runs[:recent_window]
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="promotion_decision_trends",
            producer=PROMOTION_DECISION_TRENDS_PRODUCER,
            source_command=PROMOTION_DECISION_TRENDS_SOURCE_COMMAND,
            resolved_policy_path=policy_path,
            schema_path=PROMOTION_DECISION_TRENDS,
            source_paths=[
                "ops/scripts/observability_decision_metrics_runtime.py",
                "ops/scripts/promotion_decision_registry_runtime.py",
            ],
            path_group_inputs={
                "promotion_reports": promotion_report_paths,
            },
            text_inputs={
                "recent_window": str(recent_window),
            },
        ),
        "$schema": PROMOTION_DECISION_TRENDS,
        "vault": report_path(vault, vault),
        "generated_at": generated_at,
        "policy": {
            "path": report_path(vault, policy_path),
            "version": policy.get("version"),
        },
        "summary": {
            "runs_discovered": len(run_dirs),
            "promotion_reports_considered": sum(decision_counts.values()),
            "finalized_count": finalized_count,
            "recent_window": recent_window,
        },
        "decision_counts": decision_counts,
        "artifact_class_counts": artifact_class_counts,
        "recent_runs": recent_runs,
    }


def write_promotion_decision_trends(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    context: RuntimeContext,
    recent_window: int = 20,
) -> str:
    payload = build_promotion_decision_trends(
        vault,
        policy,
        policy_path,
        context=context,
        recent_window=recent_window,
    )
    return write_schema_backed_json(
        vault,
        PROMOTION_DECISION_TRENDS_REPORT,
        payload,
        PROMOTION_DECISION_TRENDS,
        context=f"schema validation failed for {PROMOTION_DECISION_TRENDS_REPORT}",
    )


def _load_session_reports(vault: Path) -> list[dict]:
    reports_dir = vault / "ops" / "reports" / "auto-improve-sessions"
    if not reports_dir.exists():
        return []
    reports = []
    for path in sorted(reports_dir.glob("*.json")):
        report = load_optional_json(path)
        if isinstance(report, dict):
            reports.append(report)
    return reports


def _promotion_primary_targets(vault: Path, run_id: str) -> list[str]:
    promotion_rel = resolve_run_artifact_rel(vault, run_id, "promotion-report.json")
    promotion = load_optional_json(vault / promotion_rel) if promotion_rel else None
    if not isinstance(promotion, dict):
        return []
    return list_strings(promotion.get("primary_targets"))


def _promotion_decision(vault: Path, run_id: str) -> str:
    promotion_rel = resolve_run_artifact_rel(vault, run_id, "promotion-report.json")
    promotion = load_optional_json(vault / promotion_rel) if promotion_rel else None
    if not isinstance(promotion, dict):
        return ""
    try:
        return str(decision_record_from_report(promotion, require_record=False)["decision"])
    except PromotionDecisionRegistryError:
        return str(promotion.get("decision", "")).strip()


def _outcome_from_decision(decision: str) -> str:
    try:
        return decision_outcome(decision)
    except PromotionDecisionRegistryError:
        return ""


def _status_from_decision(decision: str) -> str:
    try:
        return "complete" if decision_is_terminal(decision) else "blocked"
    except PromotionDecisionRegistryError:
        return "blocked"


def _standalone_attempt(vault: Path, run_id: str) -> AttemptRecord | None:
    telemetry_rel = resolve_run_artifact_rel(vault, run_id, "run-telemetry.json")
    promotion_rel = resolve_run_artifact_rel(vault, run_id, "promotion-report.json")
    telemetry = load_optional_json(vault / telemetry_rel) if telemetry_rel else None
    promotion = load_optional_json(vault / promotion_rel) if promotion_rel else None
    if not isinstance(telemetry, dict) and not isinstance(promotion, dict):
        return None
    decision = (
        str(telemetry.get("decision", "")).strip()
        if isinstance(telemetry, dict)
        else ""
    ) or _promotion_decision(vault, run_id)
    proposal_id = (
        str(telemetry.get("proposal_id", "")).strip()
        if isinstance(telemetry, dict)
        else str(promotion.get("proposal_id", "")).strip()
        if isinstance(promotion, dict)
        else ""
    )
    source_candidate_id = (
        str(telemetry.get("source_candidate_id", "")).strip()
        if isinstance(telemetry, dict)
        else str(promotion.get("source_candidate_id", "")).strip()
        if isinstance(promotion, dict)
        else ""
    )
    iteration = {
        "index": 1,
        "proposal_id": proposal_id,
        "source_candidate_id": source_candidate_id,
        "run_id": run_id,
        "status": _status_from_decision(decision),
        "outcome": str(telemetry.get("failure_taxonomy", "")).strip()
        if isinstance(telemetry, dict)
        else "",
        "decision": decision,
    }
    if not iteration["outcome"]:
        iteration["outcome"] = _outcome_from_decision(decision)
    session = {
        "session_id": str(telemetry.get("session_id", "")).strip()
        if isinstance(telemetry, dict)
        else "",
        "iterations": [iteration],
    }
    attempts = build_attempt_records(vault, session)
    if not attempts:
        return None
    attempt = attempts[0]
    if not attempt.get("primary_targets"):
        attempt["primary_targets"] = _promotion_primary_targets(vault, run_id)
        attempt["rework_key"] = (
            f"targets:{'|'.join(sorted(list_strings(attempt['primary_targets'])))}"
            if attempt["primary_targets"]
            else ""
        )
    if not attempt.get("observed_at"):
        attempt["observed_at"] = _run_observed_at(vault, run_id)
    return attempt


def _collect_outcome_attempts(vault: Path) -> list[AttemptRecord]:
    attempts: list[AttemptRecord] = []
    seen_run_ids: set[str] = set()
    for session in _load_session_reports(vault):
        for attempt in build_attempt_records(vault, session):
            run_id = str(attempt.get("run_id", "")).strip()
            if run_id:
                seen_run_ids.add(run_id)
            attempts.append(attempt)
    runs_dir = vault / "runs"
    if not runs_dir.exists():
        return attempts
    run_dirs = sorted(
        path
        for path in runs_dir.glob("*")
        if path.is_dir() and path.name != "archive"
    )
    archive_dir = runs_dir / "archive"
    if archive_dir.is_dir():
        run_dirs.extend(sorted(path for path in archive_dir.glob("*") if path.is_dir()))
    for run_dir in run_dirs:
        run_id = run_dir.name
        if run_id in seen_run_ids:
            continue
        standalone_attempt = _standalone_attempt(vault, run_id)
        if standalone_attempt is not None:
            attempts.append(standalone_attempt)
    return attempts


def collect_outcome_attempts(vault: Path) -> list[AttemptRecord]:
    return _collect_outcome_attempts(vault)


def _session_outcome_metrics_rollup(vault: Path, session: dict) -> dict[str, Any]:
    rollups = session.get("rollups", {})
    if isinstance(rollups, dict):
        outcome_metrics = rollups.get("outcome_metrics")
        if isinstance(outcome_metrics, dict):
            return outcome_metrics
    return cast(
        dict[str, Any],
        build_outcome_metrics_from_attempts(build_attempt_records(vault, session)),
    )


def build_session_decision_metrics_summary(
    vault: Path,
    session: dict,
) -> SessionDecisionMetricsSummary:
    outcome_metrics = _session_outcome_metrics_rollup(vault, session)
    learning_summary = session.get("learning_summary", {})
    if not isinstance(learning_summary, dict):
        learning_summary = {}
    moving_averages = outcome_metrics.get("moving_averages", {})
    if not isinstance(moving_averages, dict):
        moving_averages = {}
    defect_escape_proxy = outcome_metrics.get("defect_escape_proxy", {})
    if not isinstance(defect_escape_proxy, dict):
        defect_escape_proxy = {}
    run_ids = list_strings(session.get("run_ids"))
    return {
        "attempt_count": int(
            outcome_metrics.get("attempt_count", learning_summary.get("attempt_count", 0)) or 0
        ),
        "rework_count": int(
            outcome_metrics.get("rework_count", learning_summary.get("rework_count", 0)) or 0
        ),
        "rollback_signal_count": int(
            outcome_metrics.get(
                "rollback_signal_count",
                learning_summary.get("rollback_signal_count", 0),
            )
            or 0
        ),
        "rollback_rehearsal_coverage_count": int(
            outcome_metrics.get("rollback_rehearsal_coverage_count", 0) or 0
        ),
        "defect_escape_count": int(
            defect_escape_proxy.get(
                "count",
                learning_summary.get("defect_escape_pair_count", 0),
            )
            or 0
        ),
        "finalized_run_count": sum(1 for run_id in run_ids if _run_finalized(vault, run_id)),
        "moving_averages": {
            "hold": round(float(moving_averages.get("hold", 0.0) or 0.0), 4),
            "discard": round(float(moving_averages.get("discard", 0.0) or 0.0), 4),
            "rollback_signal": round(
                float(moving_averages.get("rollback_signal", 0.0) or 0.0), 4
            ),
        },
    }


def _attempt_report_entry(vault: Path, attempt: AttemptRecord) -> OutcomeMetricsAttemptEntry:
    run_id = str(attempt.get("run_id", "")).strip()
    promotion_report = resolve_run_artifact_rel(vault, run_id, "promotion-report.json")
    return {
        "run_id": run_id,
        "session_id": str(attempt.get("session_id", "")).strip(),
        "proposal_id": str(attempt.get("proposal_id", "")).strip(),
        "source_candidate_id": str(attempt.get("source_candidate_id", "")).strip(),
        "observed_at": str(attempt.get("observed_at", "")).strip(),
        "decision": str(attempt.get("decision", "")).strip(),
        "outcome": str(attempt.get("outcome", "")).strip(),
        "primary_targets": list_strings(attempt.get("primary_targets")),
        "rework_key": str(attempt.get("rework_key", "")).strip(),
        "rollback_rehearsal_covered": bool(attempt.get("rollback_rehearsal_covered")),
        "rollback_signal": bool(attempt.get("rollback_signal")),
        "run_telemetry": str(attempt.get("run_telemetry", "")).strip(),
        "promotion_report": promotion_report,
    }


def _defect_escape_pair_key(pair: dict) -> tuple[str, str, str]:
    return (
        str(pair.get("target", "")).strip(),
        str(pair.get("promoted_run_id", "")).strip(),
        str(pair.get("escaped_run_id", "")).strip(),
    )


def _load_defect_escape_closures(vault: Path) -> list[dict]:
    payload = load_optional_json(vault / DEFECT_ESCAPE_CLOSURES_REPORT)
    if not isinstance(payload, dict):
        return []
    closures = payload.get("closures", [])
    if not isinstance(closures, list):
        return []
    return [item for item in closures if isinstance(item, dict)]


def _load_rework_closures(vault: Path) -> list[dict]:
    payload = load_optional_json(vault / REWORK_CLOSURES_REPORT)
    if not isinstance(payload, dict):
        return []
    closures = payload.get("closures", [])
    if not isinstance(closures, list):
        return []
    return [item for item in closures if isinstance(item, dict)]


def _closure_status_closed(closure: dict) -> bool:
    return str(closure.get("closure_status", "")).strip() in {"closed", "superseded"}


def _closure_evidence_refs(closure: dict) -> list[str]:
    refs = closure.get("evidence_refs", [])
    if not isinstance(refs, list):
        return []
    return [str(item).strip() for item in refs if str(item).strip()]


def _closure_run_ids(closure: dict) -> list[str]:
    run_ids = closure.get("closed_run_ids", [])
    if not isinstance(run_ids, list):
        return []
    return [str(item).strip() for item in run_ids if str(item).strip()]


def _closed_rework_key(
    entry: dict,
    closure: dict,
    *,
    active_run_ids: list[str],
    closed_run_ids: list[str],
    active_rework_count: int,
) -> dict:
    raw_rework_count = int(entry.get("rework_count", 0) or 0)
    return {
        "key": str(entry.get("key", "")).strip(),
        "raw_attempt_count": int(entry.get("attempt_count", 0) or 0),
        "raw_rework_count": raw_rework_count,
        "run_ids": list_strings(entry.get("run_ids")),
        "active_attempt_count": len(active_run_ids),
        "active_run_ids": active_run_ids,
        "active_rework_count": active_rework_count,
        "closed_run_ids": closed_run_ids,
        "closed_rework_count": max(raw_rework_count - active_rework_count, 0),
        "closure_status": str(closure.get("closure_status", "")).strip(),
        "closure_reason": str(closure.get("closure_reason", "")).strip(),
        "superseding_run_id": str(closure.get("superseding_run_id", "")).strip(),
        "closed_at": str(closure.get("closed_at", "")).strip(),
        "evidence_refs": _closure_evidence_refs(closure),
    }


def _apply_rework_closures(metrics: dict, closures: list[dict]) -> dict:
    rework_keys = metrics.get("rework_keys", [])
    if not isinstance(rework_keys, list):
        return metrics
    closure_by_key = {
        str(closure.get("rework_key", "")).strip(): closure
        for closure in closures
        if _closure_status_closed(closure)
        and str(closure.get("rework_key", "")).strip()
        and _closure_run_ids(closure)
    }
    active_rework_keys: list[dict] = []
    closed_rework_keys: list[dict] = []
    raw_rework_count = int(metrics.get("rework_count", 0) or 0)
    active_rework_count_total = 0
    closed_rework_count_total = 0
    for entry in rework_keys:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key", "")).strip()
        run_ids = list_strings(entry.get("run_ids"))
        raw_entry_rework_count = int(entry.get("rework_count", 0) or 0)
        closure = closure_by_key.get(key)
        if closure is None:
            active_rework_count_total += raw_entry_rework_count
            active_rework_keys.append(entry)
            continue
        closed_run_id_set = set(_closure_run_ids(closure))
        matched_closed_run_ids = [run_id for run_id in run_ids if run_id in closed_run_id_set]
        if not matched_closed_run_ids:
            active_rework_count_total += raw_entry_rework_count
            active_rework_keys.append(entry)
            continue
        active_run_ids = [run_id for run_id in run_ids if run_id not in closed_run_id_set]
        active_entry_rework_count = max(len(active_run_ids) - 1, 0)
        if active_entry_rework_count:
            active_rework_keys.append(
                {
                    **entry,
                    "attempt_count": len(active_run_ids),
                    "rework_count": active_entry_rework_count,
                    "run_ids": active_run_ids,
                }
            )
        active_rework_count_total += active_entry_rework_count
        closed_entry = _closed_rework_key(
            entry,
            closure,
            active_run_ids=active_run_ids,
            closed_run_ids=matched_closed_run_ids,
            active_rework_count=active_entry_rework_count,
        )
        closed_rework_keys.append(closed_entry)
        closed_rework_count_total += int(closed_entry["closed_rework_count"])
    metrics.update(
        {
            "raw_rework_count": raw_rework_count,
            "rework_count": active_rework_count_total,
            "closed_rework_count": closed_rework_count_total,
            "rework_keys": active_rework_keys,
            "closed_rework_keys": closed_rework_keys,
        }
    )
    return metrics


def _closed_defect_escape_pair(pair: dict, closure: dict) -> dict:
    return {
        **pair,
        "closure_status": str(closure.get("closure_status", "")).strip(),
        "closure_reason": str(closure.get("closure_reason", "")).strip(),
        "superseding_run_id": str(closure.get("superseding_run_id", "")).strip(),
        "closed_at": str(closure.get("closed_at", "")).strip(),
        "evidence_refs": _closure_evidence_refs(closure),
    }


def _apply_defect_escape_closures(metrics: dict, closures: list[dict]) -> dict:
    proxy = metrics.get("defect_escape_proxy", {})
    if not isinstance(proxy, dict):
        return metrics
    pairs = proxy.get("pairs", [])
    if not isinstance(pairs, list):
        return metrics
    closure_by_key = {
        _defect_escape_pair_key(closure): closure
        for closure in closures
        if _closure_status_closed(closure) and all(_defect_escape_pair_key(closure))
    }
    active_pairs: list[dict] = []
    closed_pairs: list[dict] = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        closure = closure_by_key.get(_defect_escape_pair_key(pair))
        if closure is None:
            active_pairs.append(pair)
            continue
        closed_pairs.append(_closed_defect_escape_pair(pair, closure))
    metrics["defect_escape_proxy"] = {
        **proxy,
        "count": len(active_pairs),
        "pairs": active_pairs,
        "closed_count": len(closed_pairs),
        "closed_pairs": closed_pairs,
    }
    return metrics


def build_outcome_metrics_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    context: RuntimeContext,
    recent_window: int = 20,
) -> dict:
    attempts = _collect_outcome_attempts(vault)
    ordered = sorted(
        attempts,
        key=lambda item: (
            str(item.get("observed_at", "")),
            str(item.get("session_id", "")),
            int(item.get("position", 0)),
            str(item.get("run_id", "")),
        ),
    )
    metrics = cast(dict[str, Any], build_outcome_metrics_from_attempts(ordered, recent_window=recent_window))
    metrics = _apply_rework_closures(metrics, _load_rework_closures(vault))
    metrics = _apply_defect_escape_closures(metrics, _load_defect_escape_closures(vault))
    recent_attempts = [_attempt_report_entry(vault, item) for item in reversed(ordered[-recent_window:])]
    generated_at = context.isoformat_z()
    session_report_paths = []
    reports_dir = vault / "ops" / "reports" / "auto-improve-sessions"
    if reports_dir.exists():
        session_report_paths = [
            path.relative_to(vault).as_posix()
            for path in sorted(reports_dir.glob("*.json"))
        ]
    run_input_paths: list[str] = []
    runs_dir = vault / "runs"
    if runs_dir.exists():
        run_input_paths.extend(
            path.relative_to(vault).as_posix()
            for path in sorted(runs_dir.glob("*/run-telemetry.json"))
        )
        run_input_paths.extend(
            path.relative_to(vault).as_posix()
            for path in sorted(runs_dir.glob("*/promotion-report.json"))
        )
        run_input_paths.extend(
            path.relative_to(vault).as_posix()
            for path in sorted((runs_dir / "archive").glob("*/run-telemetry.json"))
        )
        run_input_paths.extend(
            path.relative_to(vault).as_posix()
            for path in sorted((runs_dir / "archive").glob("*/promotion-report.json"))
        )
    closure_report_paths = [
        DEFECT_ESCAPE_CLOSURES_REPORT
        if (vault / DEFECT_ESCAPE_CLOSURES_REPORT).is_file()
        else ""
    ]
    closure_report_paths = [path for path in closure_report_paths if path]
    rework_closure_report_paths = [
        REWORK_CLOSURES_REPORT
        if (vault / REWORK_CLOSURES_REPORT).is_file()
        else ""
    ]
    rework_closure_report_paths = [path for path in rework_closure_report_paths if path]
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="outcome_metrics_report",
            producer=OUTCOME_METRICS_PRODUCER,
            source_command=OUTCOME_METRICS_SOURCE_COMMAND,
            resolved_policy_path=policy_path,
            schema_path=OUTCOME_METRICS,
            source_paths=[
                "ops/scripts/observability_decision_metrics_runtime.py",
                "ops/scripts/auto_improve_session_runtime.py",
            ],
            path_group_inputs={
                "session_reports": session_report_paths,
                "run_inputs": run_input_paths,
                "defect_escape_closures": closure_report_paths,
                "rework_closures": rework_closure_report_paths,
            },
            text_inputs={
                "recent_window": str(recent_window),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, policy_path),
            "version": policy.get("version"),
        },
        "summary": {
            "attempts_considered": len(ordered),
            "recent_window": recent_window,
            "recent_attempt_count": len(recent_attempts),
            "session_reports_considered": len(_load_session_reports(vault)),
        },
        "metrics": metrics,
        "recent_attempts": recent_attempts,
    }


def write_outcome_metrics_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    context: RuntimeContext,
    recent_window: int = 20,
) -> str:
    payload = build_outcome_metrics_report(
        vault,
        policy,
        policy_path,
        context=context,
        recent_window=recent_window,
    )
    return write_schema_backed_json(
        vault,
        OUTCOME_METRICS_REPORT,
        payload,
        OUTCOME_METRICS,
        context=f"schema validation failed for {OUTCOME_METRICS_REPORT}",
    )
