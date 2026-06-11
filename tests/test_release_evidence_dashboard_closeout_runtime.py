from __future__ import annotations

from ops.scripts.release.release_evidence_dashboard_closeout_runtime import (
    closeout_decision_gate,
    closeout_input_status,
)
from ops.scripts.release.release_evidence_dashboard_render_runtime import CLOSEOUT_PATH


def _closeout_payload(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "status": "pass",
        "checked_in_release_ready": True,
        "conditional_release_ready": False,
        "clean_release_ready": True,
        "live_make_check": {
            "status": "pass",
            "ready": True,
            "blocking": False,
        },
    }
    payload.update(overrides)
    return payload


def test_closeout_input_status_blocks_missing_closeout_report() -> None:
    status = closeout_input_status({}, "missing")
    gate = closeout_decision_gate(status)

    assert status["path"] == CLOSEOUT_PATH
    assert status["load_status"] == "missing"
    assert status["release_authority_status"] == "blocked"
    assert status["machine_release_allowed"] is False
    assert gate["checked_in_state"] == "fail"
    assert gate["live_rerun_state"]["reason"] == "release closeout load_status=missing"
    assert gate["claims"][0]["provenance_label"] == "diagnostic_workspace_only"


def test_closeout_decision_gate_passes_clean_machine_release() -> None:
    status = closeout_input_status(_closeout_payload(), "ok")
    gate = closeout_decision_gate(status)

    assert status["release_authority_status"] == "clean_pass"
    assert status["machine_release_allowed"] is True
    assert status["operator_release_allowed"] is True
    assert status["requires_accepted_risk_review"] is False
    assert gate["checked_in_state"] == "pass"
    assert gate["authoritative_for_release"] is True
    assert gate["required_evidence"] == []


def test_closeout_decision_gate_marks_conditional_release_as_attention() -> None:
    status = closeout_input_status(
        _closeout_payload(
            checked_in_release_ready=True,
            conditional_release_ready=True,
            clean_release_ready=False,
        ),
        "ok",
    )
    gate = closeout_decision_gate(status)

    assert status["release_authority_status"] == "conditional_pass"
    assert status["machine_release_allowed"] is False
    assert status["operator_release_allowed"] is True
    assert status["requires_accepted_risk_review"] is True
    assert gate["checked_in_state"] == "attention"
    assert "accepted-risk operator review" in gate["live_rerun_state"]["reason"]
    assert "Review accepted_risks" in gate["next_action"]


def test_closeout_decision_gate_fails_blocked_release_state() -> None:
    status = closeout_input_status(
        _closeout_payload(
            status="fail",
            checked_in_release_ready=False,
            conditional_release_ready=False,
            clean_release_ready=False,
            live_make_check={"status": "fail", "ready": False, "blocking": True},
        ),
        "ok",
    )
    gate = closeout_decision_gate(status)

    assert status["release_authority_status"] == "blocked"
    assert status["machine_release_allowed"] is False
    assert status["operator_release_allowed"] is False
    assert gate["checked_in_state"] == "fail"
    assert "release_authority_status=blocked" in gate["live_rerun_state"]["reason"]
