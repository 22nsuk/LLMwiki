from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ops.scripts.core.release_currentness_state_runtime import live_rerun_state

from .release_evidence_dashboard_render_runtime import SIGNOFF_REVALIDATION_PATH


@dataclass(frozen=True)
class DashboardStatusCounts:
    required_input_fail_count: int
    fail_count: int
    not_run_count: int
    accepted_risk_count: int
    gate_attention_count: int
    budget_attention_count: int
    status: str


def risk_owner_and_expiry(risks: list[dict[str, Any]]) -> tuple[str, str]:
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


def next_action(blockers: list[dict[str, Any]], risks: list[dict[str, Any]]) -> str:
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


def component_evidence_label(live: dict[str, str]) -> str:
    reason = str(live.get("reason", "")).strip()
    if "matches current source tree" in reason:
        return "fingerprint_equivalent_to_checked_in"
    return "diagnostic_workspace_only"


def component_gate(
    component: dict[str, Any],
    *,
    blockers: list[dict[str, Any]],
    accepted_risks: list[dict[str, Any]],
    current_fingerprint: str,
) -> dict[str, Any]:
    ready = bool(component.get("ready"))
    live = live_rerun_state(component, current_fingerprint=current_fingerprint)
    owner, expiry = risk_owner_and_expiry(accepted_risks)
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
    claim_label = component_evidence_label(live)
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
        "next_action": next_action(blockers, accepted_risks),
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


def signoff_revalidation_gate(
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


def test_failure_lane_gate(lane: dict[str, Any]) -> dict[str, Any]:
    lane_id = str(lane.get("lane_id", "")).strip()
    status = str(lane.get("status", "")).strip() or "not_run"
    failed_nodeids = [
        str(item).strip()
        for item in lane.get("failed_nodeids", [])
        if str(item).strip()
    ]
    next_lane_action = str(lane.get("next_action", "")).strip() or "none"
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
        "next_action": next_lane_action,
        "required_evidence": [next_lane_action] if next_lane_action != "none" else [],
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


def required_input_fail_count(reports: Any) -> int:
    return sum(
        1
        for load_status in (
            reports.closeout_load_status,
            reports.freshness_load_status,
            reports.learning_scoreboard_load_status,
        )
        if load_status != "ok"
    )


def accepted_risk_count(closeout: dict[str, Any]) -> int:
    summary = closeout.get("summary")
    count = int(
        summary.get("accepted_risk_instance_count", 0)
        if isinstance(summary, dict)
        else 0
    )
    if count == 0 and isinstance(closeout.get("accepted_risks"), list):
        return len(closeout.get("accepted_risks", []))
    return count


def gate_fail_count(gates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for gate in gates
        if gate["checked_in_state"] == "fail"
        or gate["live_rerun_state"]["status"] == "fail"
    )


def gate_not_run_count(gates: list[dict[str, Any]]) -> int:
    return sum(1 for gate in gates if gate["live_rerun_state"]["status"] == "not_run")


def gate_attention_count(gates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for gate in gates
        if gate["checked_in_state"] == "attention"
        or gate["live_rerun_state"]["status"] == "attention"
    )


def dashboard_status(
    *,
    fail_count: int,
    required_input_fail_count: int,
    not_run_count: int,
    gate_attention_count_value: int,
    budget_attention_count: int,
) -> str:
    if fail_count or required_input_fail_count:
        return "fail"
    if not_run_count or gate_attention_count_value or budget_attention_count:
        return "attention"
    return "pass"


def dashboard_status_counts(
    reports: Any,
    signals: Any,
    gates: list[dict[str, Any]],
) -> DashboardStatusCounts:
    required_fail_count = required_input_fail_count(reports)
    fail_count = gate_fail_count(gates)
    not_run_count = gate_not_run_count(gates)
    attention_count = gate_attention_count(gates)
    budget_attention_count = (
        1 if signals.finalizer_duration["status"] == "attention" else 0
    )
    status = dashboard_status(
        fail_count=fail_count,
        required_input_fail_count=required_fail_count,
        not_run_count=not_run_count,
        gate_attention_count_value=attention_count,
        budget_attention_count=budget_attention_count,
    )
    return DashboardStatusCounts(
        required_input_fail_count=required_fail_count,
        fail_count=fail_count,
        not_run_count=not_run_count,
        accepted_risk_count=accepted_risk_count(reports.closeout),
        gate_attention_count=attention_count,
        budget_attention_count=budget_attention_count,
        status=status,
    )
