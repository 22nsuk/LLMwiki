#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.advisory_lifecycle_runtime import (
        ADVISORY_LIFECYCLE_NOT_APPLICABLE,
        advisory_lifecycle_assessment,
        advisory_lifecycle_summary,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.release_currentness_state_runtime import (
        live_rerun_state,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
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
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
    )
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.release_currentness_state_runtime import live_rerun_state
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
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
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
    )
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
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


@dataclass(frozen=True)
class DashboardStatusCounts:
    required_input_fail_count: int
    fail_count: int
    not_run_count: int
    accepted_risk_count: int
    gate_attention_count: int
    budget_attention_count: int
    status: str


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


def _risk_owner_and_expiry(risks: list[dict[str, Any]]) -> tuple[str, str]:
    owners: set[str] = set()
    expiries: list[str] = []
    for risk in risks:
        acceptance = risk.get("risk_acceptance")
        if not isinstance(acceptance, dict):
            continue
        owner = str(acceptance.get("risk_owner", "")).strip()
        expiry = str(acceptance.get("expires_at", "")).strip()
        if owner:
            owners.add(owner)
        if expiry:
            expiries.append(expiry)
    expiries.sort()
    return ", ".join(sorted(owners)), (expiries[0] if expiries else "")


def _next_action(blockers: list[dict[str, Any]], risks: list[dict[str, Any]]) -> str:
    for blocker in blockers:
        required = blocker.get("required_evidence")
        if isinstance(required, list):
            for item in required:
                text = str(item).strip()
                if text:
                    return text
        message = str(blocker.get("message", "")).strip()
        if message:
            return message
    for risk in risks:
        acceptance = risk.get("risk_acceptance")
        if isinstance(acceptance, dict):
            text = str(acceptance.get("revalidation_condition", "")).strip()
            if text:
                return text
    return "none"


def _component_evidence_label(live: dict[str, str]) -> str:
    reason = str(live.get("reason", "")).strip()
    if "matches current source tree" in reason:
        return "fingerprint_equivalent_to_checked_in"
    return "diagnostic_workspace_only"


def _component_gate(
    component: dict[str, Any],
    *,
    blockers: list[dict[str, Any]],
    accepted_risks: list[dict[str, Any]],
    current_fingerprint: str,
) -> dict[str, Any]:
    ready = bool(component.get("ready"))
    live = live_rerun_state(component, current_fingerprint=current_fingerprint)
    owner, expiry = _risk_owner_and_expiry(accepted_risks)
    checked_state = "pass" if ready else ("attention" if accepted_risks else "fail")
    if ready and blockers:
        checked_state = "attention"
    if live["status"] == "fail" and accepted_risks:
        live = {
            "status": "attention",
            "reason": "checked-in component matches current source tree and is covered by accepted risk",
        }
    if live["status"] == "pass" and blockers:
        live = {
            "status": "attention",
            "reason": "checked-in component is source-clean but has non-source lane blockers",
        }
    claim_label = _component_evidence_label(live)
    return {
        "gate_id": str(component.get("name", "")).strip(),
        "source_path": str(component.get("path", "")).strip(),
        "checked_in_state": checked_state,
        "live_rerun_state": live,
        "authoritative_for_release": checked_state == "pass"
        and live["status"] == "pass",
        "accepted_risk": {
            "count": len(accepted_risks),
            "codes": [str(item.get("code", "")).strip() for item in accepted_risks],
        },
        "owner": owner or "runtime-maintainer",
        "expiry": expiry,
        "next_action": _next_action(blockers, accepted_risks),
        "required_evidence": [
            str(evidence)
            for blocker in blockers
            for evidence in blocker.get("required_evidence", [])
            if str(evidence).strip()
        ],
        "claims": [
            {
                "claim": f"{component.get('name', 'gate')} checked-in release evidence state is {checked_state}",
                "provenance_label": "checked_in_json_confirmed",
            },
            {
                "claim": (
                    f"{component.get('name', 'gate')} fingerprint/currentness diagnostic state "
                    f"is {live['status']}"
                ),
                "provenance_label": claim_label,
            },
        ],
    }


def _signoff_revalidation_gate(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    status = (
        str(payload.get("status", "")).strip() if load_status == "ok" else "not_run"
    )
    required_actions = payload.get("required_actions", [])
    required_evidence = [
        str(item.get("action", "") or item.get("summary", "")).strip()
        for item in required_actions
        if isinstance(item, dict)
        and str(item.get("action", "") or item.get("summary", "")).strip()
    ]
    signoff_payload = payload.get("signoff")
    signoff: dict[str, Any] = (
        signoff_payload if isinstance(signoff_payload, dict) else {}
    )
    return {
        "gate_id": "learning_readiness_signoff_revalidation",
        "source_path": SIGNOFF_REVALIDATION_PATH,
        "checked_in_state": status or "not_run",
        "live_rerun_state": {
            "status": "not_run" if load_status != "ok" else status,
            "reason": "loaded checked-in revalidation report"
            if load_status == "ok"
            else f"load_status={load_status}",
        },
        "authoritative_for_release": status == "pass",
        "accepted_risk": {
            "count": 0,
            "codes": [],
        },
        "owner": str(signoff.get("risk_owner", "")).strip() or "runtime-maintainer",
        "expiry": str(signoff.get("expires_at", "")).strip(),
        "next_action": required_evidence[0] if required_evidence else "none",
        "required_evidence": required_evidence,
        "claims": [
            {
                "claim": f"learning readiness signoff revalidation state is {status or 'not_run'}",
                "provenance_label": "checked_in_json_confirmed"
                if load_status == "ok"
                else "diagnostic_workspace_only",
            }
        ],
    }


def _test_failure_lane_gate(lane: dict[str, Any]) -> dict[str, Any]:
    lane_id = str(lane.get("lane_id", "")).strip()
    status = str(lane.get("status", "")).strip() or "not_run"
    failed_nodeids = [
        str(item).strip()
        for item in lane.get("failed_nodeids", [])
        if str(item).strip()
    ]
    next_action = str(lane.get("next_action", "")).strip() or "none"
    return {
        "gate_id": f"test_failure_lane_{lane_id}",
        "source_path": str(lane.get("source_path", "")).strip()
        or "ops/reports/test-execution-summary.json",
        "checked_in_state": status,
        "live_rerun_state": {
            "status": status,
            "reason": str(lane.get("summary", "")).strip()
            or f"{lane_id} status={status}",
        },
        "authoritative_for_release": status == "pass",
        "accepted_risk": {
            "count": 0,
            "codes": [],
        },
        "owner": "runtime-maintainer",
        "expiry": "",
        "next_action": next_action,
        "required_evidence": [next_action] if next_action != "none" else [],
        "claims": [
            {
                "claim": f"{lane_id} release test lane state is {status}",
                "provenance_label": "checked_in_json_confirmed",
            },
            *[
                {
                    "claim": f"{lane_id} failing test: {nodeid}",
                    "provenance_label": "checked_in_json_confirmed",
                }
                for nodeid in failed_nodeids
            ],
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
        _component_gate(
            component,
            blockers=blockers.get(str(component.get("name", "")), []),
            accepted_risks=risks.get(str(component.get("name", "")), []),
            current_fingerprint=current_fingerprint,
        )
        for component in reports.closeout.get("components", [])
        if isinstance(component, dict)
    )
    gates.extend(
        _test_failure_lane_gate(lane)
        for lane in reports.closeout.get("test_failure_lanes", [])
        if isinstance(lane, dict)
    )
    gates.append(
        _signoff_revalidation_gate(
            reports.revalidation, reports.revalidation_load_status
        )
    )
    advisory_gate = _advisory_lifecycle_gate(reports.closeout, generated_at=generated_at)
    if advisory_gate is not None:
        gates.append(advisory_gate)
    gates.append(learning_delta_guard_gate(signals.learning_guard))
    return gates


def _required_input_fail_count(reports: DashboardReports) -> int:
    return sum(
        1
        for load_status in (
            reports.closeout_load_status,
            reports.freshness_load_status,
            reports.learning_scoreboard_load_status,
        )
        if load_status != "ok"
    )


def _accepted_risk_count(closeout: dict[str, Any]) -> int:
    summary = closeout.get("summary")
    count = int(
        summary.get("accepted_risk_instance_count", 0)
        if isinstance(summary, dict)
        else 0
    )
    if count == 0 and isinstance(closeout.get("accepted_risks"), list):
        return len(closeout.get("accepted_risks", []))
    return count


def _gate_fail_count(gates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for gate in gates
        if gate["checked_in_state"] == "fail"
        or gate["live_rerun_state"]["status"] == "fail"
    )


def _gate_not_run_count(gates: list[dict[str, Any]]) -> int:
    return sum(1 for gate in gates if gate["live_rerun_state"]["status"] == "not_run")


def _gate_attention_count(gates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for gate in gates
        if gate["checked_in_state"] == "attention"
        or gate["live_rerun_state"]["status"] == "attention"
    )


def _dashboard_status(
    *,
    fail_count: int,
    required_input_fail_count: int,
    not_run_count: int,
    gate_attention_count: int,
    budget_attention_count: int,
) -> str:
    if fail_count or required_input_fail_count:
        return "fail"
    if not_run_count or gate_attention_count or budget_attention_count:
        return "attention"
    return "pass"


def _dashboard_status_counts(
    reports: DashboardReports,
    signals: DashboardSignals,
    gates: list[dict[str, Any]],
) -> DashboardStatusCounts:
    required_input_fail_count = _required_input_fail_count(reports)
    fail_count = _gate_fail_count(gates)
    not_run_count = _gate_not_run_count(gates)
    gate_attention_count = _gate_attention_count(gates)
    budget_attention_count = (
        1 if signals.finalizer_duration["status"] == "attention" else 0
    )
    status = _dashboard_status(
        fail_count=fail_count,
        required_input_fail_count=required_input_fail_count,
        not_run_count=not_run_count,
        gate_attention_count=gate_attention_count,
        budget_attention_count=budget_attention_count,
    )
    return DashboardStatusCounts(
        required_input_fail_count=required_input_fail_count,
        fail_count=fail_count,
        not_run_count=not_run_count,
        accepted_risk_count=_accepted_risk_count(reports.closeout),
        gate_attention_count=gate_attention_count,
        budget_attention_count=budget_attention_count,
        status=status,
    )


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
    status_counts = _dashboard_status_counts(reports, signals, gates)
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
