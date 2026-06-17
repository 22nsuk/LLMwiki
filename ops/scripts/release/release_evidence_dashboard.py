#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
    )
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.release.advisory_lifecycle_runtime import (
        ADVISORY_LIFECYCLE_NOT_APPLICABLE,
        advisory_lifecycle_assessment,
        advisory_lifecycle_summary,
    )
    from ops.scripts.release.release_evidence_dashboard_closeout_runtime import (
        closeout_decision_gate,
        closeout_input_status,
    )
    from ops.scripts.release.release_evidence_dashboard_finalizer_runtime import (
        finalizer_duration_signal,
    )
    from ops.scripts.release.release_evidence_dashboard_learning_delta_runtime import (
        learning_delta_guard_gate,
        learning_delta_guard_summary,
    )
    from ops.scripts.release.release_evidence_dashboard_render_runtime import (
        ARTIFACT_FRESHNESS_PATH,
        CLOSEOUT_PATH,
        FIXED_POINT_COST_TREND_PATH,
        FIXED_POINT_PATH,
        LEARNING_DELTA_SCOREBOARD_PATH,
        SIGNOFF_REVALIDATION_PATH,
        DashboardRenderInputs,
        _render_dashboard_report,
    )
    from ops.scripts.release.release_evidence_dashboard_status_runtime import (
        component_gate,
        dashboard_status_counts,
        signoff_revalidation_gate,
        test_failure_lane_gate,
    )
else:
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
    )
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.release.release_evidence_dashboard_closeout_runtime import (
        closeout_decision_gate,
        closeout_input_status,
    )
    from ops.scripts.release.release_evidence_dashboard_finalizer_runtime import (
        finalizer_duration_signal,
    )
    from ops.scripts.release.release_evidence_dashboard_learning_delta_runtime import (
        learning_delta_guard_gate,
        learning_delta_guard_summary,
    )
    from ops.scripts.release.release_evidence_dashboard_render_runtime import (
        ARTIFACT_FRESHNESS_PATH,
        CLOSEOUT_PATH,
        FIXED_POINT_COST_TREND_PATH,
        FIXED_POINT_PATH,
        LEARNING_DELTA_SCOREBOARD_PATH,
        SIGNOFF_REVALIDATION_PATH,
        DashboardRenderInputs,
        _render_dashboard_report,
    )
    from ops.scripts.release.release_evidence_dashboard_status_runtime import (
        component_gate,
        dashboard_status_counts,
        signoff_revalidation_gate,
        test_failure_lane_gate,
    )

    from .advisory_lifecycle_runtime import (
        ADVISORY_LIFECYCLE_NOT_APPLICABLE,
        advisory_lifecycle_assessment,
        advisory_lifecycle_summary,
    )

DEFAULT_OUT = "ops/reports/release-evidence-dashboard.json"


@dataclass(frozen=True)
class DashboardReports:
    closeout: dict[str, Any]
    closeout_load_status: str
    fixed_point: dict[str, Any]
    fixed_point_load_status: str
    cost_trend: dict[str, Any]
    cost_trend_load_status: str
    revalidation: dict[str, Any]
    revalidation_load_status: str
    freshness: dict[str, Any]
    freshness_load_status: str
    learning_scoreboard: dict[str, Any]
    learning_scoreboard_load_status: str


@dataclass(frozen=True)
class DashboardSignals:
    closeout_input: dict[str, Any]
    finalizer_duration: dict[str, Any]
    learning_guard: dict[str, Any]


def _load(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _issues_by_source(items: object) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(items, list):
        return grouped
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip() or "unknown"
        grouped.setdefault(source, []).append(item)
    return grouped


def _advisory_lifecycle_entries(
    closeout: dict[str, Any],
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    risks = closeout.get("accepted_risks", [])
    if not isinstance(risks, list):
        return []
    entries: list[dict[str, Any]] = []
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        assessment = advisory_lifecycle_assessment(risk, generated_at=generated_at)
        if assessment["lifecycle_status"] == ADVISORY_LIFECYCLE_NOT_APPLICABLE:
            continue
        acceptance = risk.get("risk_acceptance")
        acceptance = acceptance if isinstance(acceptance, dict) else {}
        required_evidence = [
            str(item).strip()
            for item in risk.get("required_evidence", [])
            if str(item).strip()
        ]
        closure_action = str(acceptance.get("revalidation_condition", "")).strip()
        if closure_action:
            required_evidence.append(closure_action)
        entries.append(
            {
                "code": str(risk.get("code", "")).strip(),
                "source": str(risk.get("source", "")).strip(),
                "source_path": str(risk.get("source_path", CLOSEOUT_PATH)).strip()
                or CLOSEOUT_PATH,
                "risk_owner": str(acceptance.get("risk_owner", "")).strip(),
                "expires_at": str(acceptance.get("expires_at", "")).strip(),
                "closure_action": closure_action,
                "rollback_trigger": str(acceptance.get("rollback_trigger", "")).strip(),
                "required_evidence": required_evidence,
                **assessment,
            }
        )
    return entries


def _advisory_lifecycle_gate(
    closeout: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any] | None:
    entries = _advisory_lifecycle_entries(closeout, generated_at=generated_at)
    if not entries:
        return None
    summary = advisory_lifecycle_summary(entries)
    status = str(summary["advisory_backlog_status"])
    owner = next(
        (
            str(entry.get("risk_owner", "")).strip()
            for entry in entries
            if str(entry.get("risk_owner", "")).strip()
        ),
        "runtime-maintainer",
    )
    expiry = min(
        (
            str(entry.get("expires_at", "")).strip()
            for entry in entries
            if str(entry.get("expires_at", "")).strip()
        ),
        default="",
    )
    required_evidence = sorted(
        {
            str(item).strip()
            for entry in entries
            for item in entry.get("required_evidence", [])
            if str(item).strip()
        }
    )
    codes = [str(entry.get("code", "")).strip() for entry in entries]
    issue_count = int(summary["advisory_backlog_expired_count"]) + int(
        summary["advisory_backlog_missing_lifecycle_count"]
    )
    if issue_count:
        next_action = "Resolve expired or incomplete advisory accepted-risk lifecycle metadata before operator signoff."
    else:
        next_action = "Review advisory accepted-risk lifecycle before operator signoff."
    reason = (
        f"advisory_backlog_status={status}; "
        f"active={summary['advisory_backlog_active_count']}; "
        f"expired={summary['advisory_backlog_expired_count']}; "
        f"metadata_missing={summary['advisory_backlog_missing_lifecycle_count']}"
    )
    return {
        "gate_id": "advisory_lifecycle_review",
        "source_path": CLOSEOUT_PATH,
        "checked_in_state": "attention",
        "live_rerun_state": {
            "status": "attention",
            "reason": reason,
        },
        "authoritative_for_release": False,
        "accepted_risk": {
            "count": len(entries),
            "codes": codes,
        },
        "owner": owner,
        "expiry": expiry,
        "next_action": next_action,
        "required_evidence": required_evidence or [next_action],
        "claims": [
            {
                "claim": f"advisory accepted-risk lifecycle status is {status}",
                "provenance_label": "checked_in_json_confirmed",
            },
            {
                "claim": f"advisory accepted-risk codes requiring operator review: {', '.join(codes)}",
                "provenance_label": "checked_in_json_confirmed",
            },
        ],
    }


def _load_dashboard_reports(vault: Path) -> DashboardReports:
    closeout, closeout_load_status = _load(vault, CLOSEOUT_PATH)
    fixed_point, fixed_point_load_status = _load(vault, FIXED_POINT_PATH)
    cost_trend, cost_trend_load_status = _load(vault, FIXED_POINT_COST_TREND_PATH)
    revalidation, revalidation_load_status = _load(vault, SIGNOFF_REVALIDATION_PATH)
    freshness, freshness_load_status = _load(vault, ARTIFACT_FRESHNESS_PATH)
    learning_scoreboard, learning_scoreboard_load_status = _load(
        vault, LEARNING_DELTA_SCOREBOARD_PATH
    )
    return DashboardReports(
        closeout=closeout,
        closeout_load_status=closeout_load_status,
        fixed_point=fixed_point,
        fixed_point_load_status=fixed_point_load_status,
        cost_trend=cost_trend,
        cost_trend_load_status=cost_trend_load_status,
        revalidation=revalidation,
        revalidation_load_status=revalidation_load_status,
        freshness=freshness,
        freshness_load_status=freshness_load_status,
        learning_scoreboard=learning_scoreboard,
        learning_scoreboard_load_status=learning_scoreboard_load_status,
    )


def _dashboard_signals(vault: Path, reports: DashboardReports) -> DashboardSignals:
    return DashboardSignals(
        closeout_input=closeout_input_status(
            reports.closeout, reports.closeout_load_status
        ),
        finalizer_duration=finalizer_duration_signal(
            vault,
            reports.fixed_point,
            reports.fixed_point_load_status,
            reports.cost_trend,
            reports.cost_trend_load_status,
        ),
        learning_guard=learning_delta_guard_summary(
            reports.learning_scoreboard,
            reports.learning_scoreboard_load_status,
        ),
    )


def _dashboard_gates(
    reports: DashboardReports,
    signals: DashboardSignals,
    *,
    current_fingerprint: str,
    generated_at: str,
) -> list[dict[str, Any]]:
    blockers = _issues_by_source(reports.closeout.get("blockers", []))
    risks = _issues_by_source(reports.closeout.get("accepted_risks", []))
    gates = [closeout_decision_gate(signals.closeout_input)]
    gates.extend(
        component_gate(
            component,
            blockers=blockers.get(str(component.get("name", "")), []),
            accepted_risks=risks.get(str(component.get("name", "")), []),
            current_fingerprint=current_fingerprint,
        )
        for component in reports.closeout.get("components", [])
        if isinstance(component, dict)
    )
    gates.extend(
        test_failure_lane_gate(lane)
        for lane in reports.closeout.get("test_failure_lanes", [])
        if isinstance(lane, dict)
    )
    gates.append(
        signoff_revalidation_gate(
            reports.revalidation, reports.revalidation_load_status
        )
    )
    advisory_gate = _advisory_lifecycle_gate(reports.closeout, generated_at=generated_at)
    if advisory_gate is not None:
        gates.append(advisory_gate)
    gates.append(learning_delta_guard_gate(signals.learning_guard))
    return gates


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    current_fingerprint = release_source_tree_fingerprint(vault)
    reports = _load_dashboard_reports(vault)
    signals = _dashboard_signals(vault, reports)
    gates = _dashboard_gates(
        reports,
        signals,
        current_fingerprint=current_fingerprint,
        generated_at=generated_at,
    )
    status_counts = dashboard_status_counts(reports, signals, gates)
    return _render_dashboard_report(
        DashboardRenderInputs(
            vault=vault,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            generated_at=generated_at,
            current_fingerprint=current_fingerprint,
            reports=reports,
            signals=signals,
            gates=gates,
            status_counts=status_counts,
        )
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release evidence dashboard schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a release evidence dashboard from closeout reports"
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Write dashboard output and exit zero even when dashboard status is fail.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.no_fail:
        return 0
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
