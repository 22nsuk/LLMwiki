from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from ops.scripts.auto_improve_session_runtime import (
    build_executor_rollup,
    build_routing_rollup,
    build_session_rollups,
    build_telemetry_rollup,
    normalize_session_report,
)

from .artifact_freshness_runtime import (
    build_canonical_report_envelope,
    embed_artifact_envelope_metadata,
)
from .observability_artifacts_shared_runtime import (
    dict_value,
    list_strings_any,
    load_optional_json,
    resolve_run_artifact_rel,
    run_artifact_glob_rels,
    write_schema_backed_json,
)
from .observability_decision_metrics_runtime import (
    build_session_decision_metrics_summary,
    collect_outcome_attempts,
)
from .policy_runtime import load_policy, report_path
from .runtime_context import RuntimeContext
from .runtime_event_logging_runtime import append_runtime_event
from .schema_constants_runtime import (
    AUTO_IMPROVE_SESSION_SCHEMA_PATH,
    ROUTING_PROVENANCE_AGGREGATE_SCHEMA_PATH,
)

ROUTING_PROVENANCE_AGGREGATE = ROUTING_PROVENANCE_AGGREGATE_SCHEMA_PATH
AUTO_IMPROVE_SESSION_SCHEMA = AUTO_IMPROVE_SESSION_SCHEMA_PATH
ROUTING_PROVENANCE_AGGREGATE_DIR = "ops/reports/routing-provenance-aggregates"
AUTO_IMPROVE_SESSION_DIR = "ops/reports/auto-improve-sessions"
STANDALONE_RECONSTRUCTED_SESSION_ID = "standalone-run-telemetry"
PRODUCER = "ops.scripts.observability_routing_provenance_runtime"
SOURCE_COMMAND = "python -m ops.scripts.observability_routing_provenance_runtime --vault ."


class RoutingAggregateRunArtifacts(TypedDict):
    proposal_snapshot: str
    scope_freeze: str
    routing_reports: list[str]
    executor_reports: list[str]
    run_telemetry: str
    promotion_report: str
    run_artifact_fingerprint: str


class RoutingAggregateRunEntry(TypedDict):
    run_id: str
    proposal_id: str
    source_candidate_id: str
    decision: str
    outcome: str
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]
    risk_flags: list[str]
    roles: list[str]
    artifacts: RoutingAggregateRunArtifacts


@dataclass(frozen=True)
class _RoutingAggregateInputs:
    session_id: str
    generated_at: str
    policy_block: dict
    resolved_policy_path: Path
    run_ids: list[str]
    by_run: dict[str, dict]
    routing_rollup: dict
    executor_rollup: dict
    telemetry_rollup: dict


@dataclass(frozen=True)
class _RoutingRunCollectionEntry:
    entry: RoutingAggregateRunEntry
    routing_report_count: int
    executor_report_count: int
    has_telemetry: bool
    has_promotion_report: bool
    has_artifact_fingerprint: bool


@dataclass(frozen=True)
class _RoutingRunCollection:
    runs: list[RoutingAggregateRunEntry]
    summary: dict
    coverage: dict


def _iteration_by_run(session: dict) -> dict[str, dict]:
    result = {}
    for iteration in session.get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        run_id = str(iteration.get("run_id", "")).strip()
        if run_id:
            result[run_id] = iteration
    return result


def _routing_reports(vault: Path, run_id: str) -> tuple[list[str], list[str], list[str]]:
    reports: list[str] = []
    roles: list[str] = []
    risk_flags: list[str] = []
    for rel_path in run_artifact_glob_rels(vault, run_id, "subagent-routing.*.json"):
        path = vault / rel_path
        reports.append(rel_path)
        payload = load_optional_json(path)
        if not isinstance(payload, dict):
            continue
        role = str(payload.get("role", "")).strip()
        if role and role not in roles:
            roles.append(role)
        complexity = payload.get("complexity_profile", {})
        if isinstance(complexity, dict):
            for flag in list_strings_any(complexity.get("risk_flags")):
                if flag not in risk_flags:
                    risk_flags.append(flag)
    return reports, roles, risk_flags


def _executor_reports(vault: Path, run_id: str) -> list[str]:
    return run_artifact_glob_rels(vault, run_id, "*-executor-report.json")


def _existing_or_resolved_run_artifact(vault: Path, run_id: str, rel_path: object, filename: str) -> str:
    candidate = str(rel_path or "").strip()
    if candidate and not Path(candidate).is_absolute() and (vault / candidate).is_file():
        return candidate
    return resolve_run_artifact_rel(vault, run_id, filename)


def _ratio(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(count / denominator, 4)


def _session_rollup(session: dict, key: str) -> dict:
    rollups = session.get("rollups", {})
    if not isinstance(rollups, dict):
        return {}
    rollup = rollups.get(key)
    return rollup if isinstance(rollup, dict) else {}


def _routing_aggregate_inputs(
    vault: Path,
    session: dict,
    *,
    context: RuntimeContext,
) -> _RoutingAggregateInputs:
    session_id = str(session["session_id"])
    generated_at = context.isoformat_z()
    policy_block = dict(session["policy"])
    _policy, resolved_policy_path = load_policy(vault, str(policy_block.get("path") or ""))
    run_ids = list_strings_any(session.get("run_ids"))
    return _RoutingAggregateInputs(
        session_id=session_id,
        generated_at=generated_at,
        policy_block=policy_block,
        resolved_policy_path=resolved_policy_path,
        run_ids=run_ids,
        by_run=_iteration_by_run(session),
        routing_rollup=_session_rollup(session, "routing") or build_routing_rollup(vault, run_ids),
        executor_rollup=_session_rollup(session, "executor") or build_executor_rollup(vault, run_ids),
        telemetry_rollup=_session_rollup(session, "telemetry") or build_telemetry_rollup(vault, run_ids),
    )


def _empty_routing_aggregate_summary() -> dict:
    return {
        "run_count": 0,
        "routing_report_count": 0,
        "executor_report_count": 0,
        "telemetry_report_count": 0,
        "promotion_report_count": 0,
        "artifact_fingerprint_count": 0,
    }


def _empty_routing_aggregate_coverage() -> dict:
    return {
        "run_count": 0,
        "runs_with_routing": 0,
        "runs_with_executor": 0,
        "runs_with_telemetry": 0,
        "runs_with_promotion_report": 0,
        "runs_with_artifact_fingerprint": 0,
    }


def _build_loop_health_rollup(
    vault: Path,
    session: dict,
    *,
    summary: dict,
    coverage: dict,
    routing: dict,
    executor: dict,
) -> dict:
    metrics = build_session_decision_metrics_summary(vault, session)
    run_count = int(summary.get("run_count", 0) or 0)
    routing_report_parse_gap_count = max(
        int(summary.get("routing_report_count", 0) or 0) - int(routing.get("report_count", 0) or 0),
        0,
    )
    executor_report_parse_gap_count = max(
        int(summary.get("executor_report_count", 0) or 0)
        - int(executor.get("report_count", 0) or 0),
        0,
    )
    status_counts = dict_value(executor.get("status_counts"))
    executor_failure_count = sum(
        count
        for status, count in status_counts.items()
        if str(status).strip() != "pass" and isinstance(count, int)
    )
    coverage_ratios = {
        "routing": _ratio(int(coverage.get("runs_with_routing", 0) or 0), run_count),
        "executor": _ratio(int(coverage.get("runs_with_executor", 0) or 0), run_count),
        "telemetry": _ratio(int(coverage.get("runs_with_telemetry", 0) or 0), run_count),
        "promotion_report": _ratio(
            int(coverage.get("runs_with_promotion_report", 0) or 0),
            run_count,
        ),
        "artifact_fingerprint": _ratio(
            int(coverage.get("runs_with_artifact_fingerprint", 0) or 0),
            run_count,
        ),
    }
    health_flags: list[str] = []
    if coverage_ratios["telemetry"] <= 0.0:
        health_flags.append("missing_telemetry_coverage")
    elif coverage_ratios["telemetry"] < 1.0:
        health_flags.append("partial_telemetry_coverage")
    if routing_report_parse_gap_count:
        health_flags.append("routing_report_parse_gap")
    if executor_report_parse_gap_count:
        health_flags.append("executor_report_parse_gap")
    if executor_failure_count:
        health_flags.append("executor_failures_present")
    if metrics["rollback_signal_count"]:
        health_flags.append("rollback_signals_present")
    if metrics["rework_count"]:
        health_flags.append("rework_detected")
    if metrics["defect_escape_count"]:
        health_flags.append("defect_escape_signals_present")
    if metrics["finalized_run_count"] < run_count:
        health_flags.append("unfinalized_runs_present")
    if metrics["moving_averages"]["hold"] > 0.0:
        health_flags.append("recent_hold_present")
    if metrics["moving_averages"]["discard"] > 0.0:
        health_flags.append("recent_discard_present")
    return {
        "attempt_count": metrics["attempt_count"],
        "rework_count": metrics["rework_count"],
        "rollback_signal_count": metrics["rollback_signal_count"],
        "rollback_rehearsal_coverage_count": metrics["rollback_rehearsal_coverage_count"],
        "defect_escape_count": metrics["defect_escape_count"],
        "finalized_run_count": metrics["finalized_run_count"],
        "executor_failure_count": executor_failure_count,
        "routing_report_parse_gap_count": routing_report_parse_gap_count,
        "executor_report_parse_gap_count": executor_report_parse_gap_count,
        "moving_averages": metrics["moving_averages"],
        "coverage_ratios": coverage_ratios,
        "health_flags": health_flags,
    }


def _build_routing_run_entry(
    vault: Path,
    run_id: str,
    iteration: dict,
) -> _RoutingRunCollectionEntry:
    telemetry_rel = _existing_or_resolved_run_artifact(
        vault,
        run_id,
        iteration.get("run_telemetry"),
        "run-telemetry.json",
    )
    telemetry = load_optional_json(vault / telemetry_rel) if telemetry_rel else {}
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    scope_freeze_rel = _existing_or_resolved_run_artifact(
        vault,
        run_id,
        telemetry.get("scope_freeze"),
        "scope-freeze.json",
    )
    scope_freeze = load_optional_json(vault / scope_freeze_rel) if scope_freeze_rel else {}
    scope_freeze = scope_freeze if isinstance(scope_freeze, dict) else {}
    scope_inputs = dict_value(scope_freeze.get("inputs"))
    scope_resolution = dict_value(scope_freeze.get("resolution"))
    routing_reports, roles, risk_flags = _routing_reports(vault, run_id)
    executor_reports = _executor_reports(vault, run_id)
    proposal_snapshot = _existing_or_resolved_run_artifact(
        vault,
        run_id,
        telemetry.get("proposal_snapshot"),
        "proposal-snapshot.json",
    )
    promotion_report = resolve_run_artifact_rel(vault, run_id, "promotion-report.json")
    artifact_fingerprint = resolve_run_artifact_rel(vault, run_id, "run-artifact-fingerprint.json")
    return _RoutingRunCollectionEntry(
        entry={
            "run_id": run_id,
            "proposal_id": str(telemetry.get("proposal_id", "")).strip(),
            "source_candidate_id": str(
                telemetry.get("source_candidate_id")
                or iteration.get("source_candidate_id")
                or scope_freeze.get("source_candidate_id", "")
            ).strip(),
            "decision": str(telemetry.get("decision") or iteration.get("decision", "")).strip(),
            "outcome": str(iteration.get("outcome", "")).strip(),
            "primary_targets": list_strings_any(
                telemetry.get("primary_targets") or scope_inputs.get("primary_targets")
            ),
            "supporting_targets": list_strings_any(
                telemetry.get("supporting_targets") or scope_inputs.get("supporting_targets")
            ),
            "test_files": list_strings_any(
                telemetry.get("test_files") or scope_resolution.get("test_files")
            ),
            "risk_flags": risk_flags or list_strings_any(scope_resolution.get("risk_flags")),
            "roles": roles,
            "artifacts": {
                "proposal_snapshot": proposal_snapshot,
                "scope_freeze": scope_freeze_rel,
                "routing_reports": routing_reports,
                "executor_reports": executor_reports,
                "run_telemetry": telemetry_rel if telemetry else "",
                "promotion_report": promotion_report,
                "run_artifact_fingerprint": artifact_fingerprint,
            },
        },
        routing_report_count=len(routing_reports),
        executor_report_count=len(executor_reports),
        has_telemetry=bool(telemetry),
        has_promotion_report=bool(promotion_report),
        has_artifact_fingerprint=bool(artifact_fingerprint),
    )


def _collect_routing_runs(
    vault: Path,
    inputs: _RoutingAggregateInputs,
) -> _RoutingRunCollection:
    runs: list[RoutingAggregateRunEntry] = []
    summary = _empty_routing_aggregate_summary()
    coverage = _empty_routing_aggregate_coverage()
    for run_id in inputs.run_ids:
        item = _build_routing_run_entry(vault, run_id, inputs.by_run.get(run_id, {}))
        runs.append(item.entry)
        summary["run_count"] += 1
        summary["routing_report_count"] += item.routing_report_count
        summary["executor_report_count"] += item.executor_report_count
        summary["telemetry_report_count"] += 1 if item.has_telemetry else 0
        summary["promotion_report_count"] += 1 if item.has_promotion_report else 0
        summary["artifact_fingerprint_count"] += 1 if item.has_artifact_fingerprint else 0
        coverage["run_count"] += 1
        coverage["runs_with_routing"] += 1 if item.routing_report_count else 0
        coverage["runs_with_executor"] += 1 if item.executor_report_count else 0
        coverage["runs_with_telemetry"] += 1 if item.has_telemetry else 0
        coverage["runs_with_promotion_report"] += 1 if item.has_promotion_report else 0
        coverage["runs_with_artifact_fingerprint"] += 1 if item.has_artifact_fingerprint else 0
    return _RoutingRunCollection(runs=runs, summary=summary, coverage=coverage)


def _routing_provenance_payload(
    vault: Path,
    session: dict,
    inputs: _RoutingAggregateInputs,
    collection: _RoutingRunCollection,
) -> dict:
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=inputs.generated_at,
            artifact_kind="routing_provenance_aggregate",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=ROUTING_PROVENANCE_AGGREGATE,
            source_paths=[
                "ops/scripts/core/observability_routing_provenance_runtime.py",
                "ops/scripts/mechanism/auto_improve_session_runtime.py",
                "ops/scripts/core/observability_decision_metrics_runtime.py",
            ],
            file_inputs={"source_session_report": str(session["path"])},
            text_inputs={"run_ids": "\n".join(inputs.run_ids)},
        ),
        "$schema": ROUTING_PROVENANCE_AGGREGATE,
        "session_id": inputs.session_id,
        "generated_at": inputs.generated_at,
        "policy": inputs.policy_block,
        "source_session_report": str(session["path"]),
        "summary": collection.summary,
        "audit_rollup": {
            "routing": inputs.routing_rollup,
            "executor": inputs.executor_rollup,
            "telemetry": inputs.telemetry_rollup,
            "coverage": collection.coverage,
            "loop_health": _build_loop_health_rollup(
                vault,
                session,
                summary=collection.summary,
                coverage=collection.coverage,
                routing=inputs.routing_rollup,
                executor=inputs.executor_rollup,
            ),
        },
        "runs": collection.runs,
    }


def build_routing_provenance_aggregate(
    vault: Path,
    session: dict,
    *,
    context: RuntimeContext,
) -> dict:
    inputs = _routing_aggregate_inputs(vault, session, context=context)
    collection = _collect_routing_runs(vault, inputs)
    return _routing_provenance_payload(vault, session, inputs, collection)


def write_routing_provenance_aggregate(
    vault: Path,
    session: dict,
    *,
    context: RuntimeContext,
) -> str:
    started_at = context.utcnow()
    session_id = str(session["session_id"])
    rel_path = f"{ROUTING_PROVENANCE_AGGREGATE_DIR}/{session_id}.json"
    payload = build_routing_provenance_aggregate(vault, session, context=context)
    written_rel_path = write_schema_backed_json(
        vault,
        rel_path,
        payload,
        ROUTING_PROVENANCE_AGGREGATE,
        context=f"schema validation failed for {rel_path}",
    )
    append_runtime_event(
        vault,
        context=context,
        component="observability_artifacts",
        phase="routing_provenance_aggregate",
        decision="written",
        artifact_path=written_rel_path,
        duration_ms=int(round((context.utcnow() - started_at).total_seconds() * 1000)),
        session_id=session_id,
        policy_version=dict(session.get("policy", {})).get("version", ""),
    )
    return written_rel_path


def _terminal_status(decision: str) -> str:
    return "complete" if decision in {"PROMOTE", "DISCARD", "SKIPPED"} else "blocked"


def _reconstructed_standalone_session(
    vault: Path,
    *,
    policy_path: str | None,
    context: RuntimeContext,
) -> dict:
    attempts = collect_outcome_attempts(vault)
    run_ids: list[str] = []
    iterations: list[dict] = []
    for attempt in attempts:
        run_id = str(attempt.get("run_id", "")).strip()
        if not run_id or run_id in run_ids:
            continue
        run_ids.append(run_id)
        iterations.append(
            {
                "index": len(iterations) + 1,
                "proposal_id": str(attempt.get("proposal_id", "")).strip(),
                "source_candidate_id": str(attempt.get("source_candidate_id", "")).strip(),
                "run_id": run_id,
                "status": str(attempt.get("status", "")).strip()
                or _terminal_status(str(attempt.get("decision", "")).strip()),
                "decision": str(attempt.get("decision", "")).strip(),
                "outcome": str(attempt.get("outcome", "")).strip(),
            }
        )
    if not run_ids:
        return {}

    policy, resolved_policy_path = load_policy(vault, policy_path)
    generated_at = context.isoformat_z()
    session = {
        "$schema": AUTO_IMPROVE_SESSION_SCHEMA,
        "session_id": STANDALONE_RECONSTRUCTED_SESSION_ID,
        "generated_at": generated_at,
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": int(policy["version"]),
        },
        "status": "complete",
        "budget": {
            "max_proposals": max(1, len(run_ids)),
            "max_minutes": 1,
            "max_consecutive_failures": max(1, len(run_ids)),
        },
        "executor": {"name": "standalone_run_reconstruction"},
        "attempted_proposal_ids": [],
        "quarantined_proposal_ids": [],
        "run_ids": run_ids,
        "iterations": iterations,
        "learning_summary": {
            "attempt_count": 0,
            "rework_count": 0,
            "rollback_signal_count": 0,
            "defect_escape_pair_count": 0,
            "session_context_status": "no_attempt_context",
            "evidence_gaps": [],
        },
        "loop_state": {
            "consecutive_failures": 0,
            "last_outcome": str(iterations[-1].get("outcome", "")).strip(),
            "last_decision": str(iterations[-1].get("decision", "")).strip(),
            "last_run_id": run_ids[-1],
            "last_blocking_reason": "",
            "blocking_reason_counts": {},
            "repeated_blocker_stop": False,
            "repeated_blocker_reason": "",
            "remediation_backlog_path": "ops/reports/remediation-backlog.json",
            "updated_at": generated_at,
        },
        "queue_snapshot": [],
        "stop_reason": "reconstructed_from_standalone_run_artifacts",
        "path": f"{AUTO_IMPROVE_SESSION_DIR}/{STANDALONE_RECONSTRUCTED_SESSION_ID}.json",
        "metadata": {
            "source": "standalone_run_artifact_reconstruction",
            "reason": "surface run telemetry that predates auto-improve session_id persistence",
        },
    }
    session = normalize_session_report(vault, session)
    session["rollups"] = build_session_rollups(vault, session)
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="auto_improve_session",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=AUTO_IMPROVE_SESSION_SCHEMA,
        source_paths=[
            "ops/scripts/core/observability_routing_provenance_runtime.py",
            "ops/scripts/core/observability_decision_metrics_runtime.py",
            "ops/scripts/mechanism/auto_improve_session_runtime.py",
        ],
        text_inputs={
            "session_id": STANDALONE_RECONSTRUCTED_SESSION_ID,
            "run_ids": "\n".join(run_ids),
        },
    )
    session = embed_artifact_envelope_metadata(session, envelope)
    write_schema_backed_json(
        vault,
        str(session["path"]),
        session,
        AUTO_IMPROVE_SESSION_SCHEMA,
        context=f"schema validation failed for {session['path']}",
    )
    return session


def latest_auto_improve_session(vault: Path) -> dict:
    reports_dir = vault / AUTO_IMPROVE_SESSION_DIR
    if not reports_dir.exists():
        return {}
    latest_key = ("", "")
    latest_payload: dict = {}
    for path in sorted(reports_dir.glob("*.json")):
        payload = load_optional_json(path)
        if not isinstance(payload, dict):
            continue
        generated_at = str(payload.get("generated_at", "")).strip()
        rel_path = report_path(vault, path)
        candidate_key = (generated_at, rel_path)
        if candidate_key >= latest_key:
            latest_key = candidate_key
            latest_payload = payload
    return latest_payload


def write_latest_routing_provenance_aggregate(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> str:
    session = latest_auto_improve_session(vault)
    policy, _resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    if not session or not list_strings_any(session.get("run_ids")) or (
        str(session.get("session_id", "")).strip() == STANDALONE_RECONSTRUCTED_SESSION_ID
    ):
        reconstructed = _reconstructed_standalone_session(
            vault,
            policy_path=policy_path,
            context=runtime_context,
        )
        if reconstructed:
            session = reconstructed
    if not session:
        return ""
    return write_routing_provenance_aggregate(vault, session, context=runtime_context)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a routing provenance aggregate for the latest auto-improve session report."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    rel_path = write_latest_routing_provenance_aggregate(vault, policy_path=args.policy_path)
    print(
        json.dumps(
            {
                "status": "written" if rel_path else "skipped",
                "path": rel_path,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
