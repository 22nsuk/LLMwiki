from __future__ import annotations

from ops.scripts.release.release_closeout_gate_decision_runtime import (
    RELEASE_STATE_BLOCKED,
    RELEASE_STATE_CLEAN_PASS,
    RELEASE_STATE_CONDITIONAL_PASS,
    RELEASE_STATE_UNKNOWN,
    CloseoutComponentCollection,
    CloseoutGates,
    CloseoutRiskState,
    build_closeout_test_failure_lanes,
    closeout_readiness_state,
    failed_test_nodeids,
    live_make_check_gate,
    release_readiness_state,
    release_smoke_boundedness_gate,
)


def test_release_readiness_state_clean_pass() -> None:
    assert (
        release_readiness_state(
            checked_in_release_ready=True,
            clean_release_ready=True,
            accepted_risks=[],
        )
        == RELEASE_STATE_CLEAN_PASS
    )


def test_release_readiness_state_conditional_pass() -> None:
    assert (
        release_readiness_state(
            checked_in_release_ready=True,
            clean_release_ready=False,
            accepted_risks=[{"code": "accepted"}],
        )
        == RELEASE_STATE_CONDITIONAL_PASS
    )


def test_release_readiness_state_unknown_when_checked_without_risks() -> None:
    assert (
        release_readiness_state(
            checked_in_release_ready=True,
            clean_release_ready=False,
            accepted_risks=[],
        )
        == RELEASE_STATE_UNKNOWN
    )


def test_release_readiness_state_blocked_when_not_checked_in() -> None:
    assert (
        release_readiness_state(
            checked_in_release_ready=False,
            clean_release_ready=False,
            accepted_risks=[],
        )
        == RELEASE_STATE_BLOCKED
    )


def test_failed_test_nodeids_parses_pytest_stdout_tail() -> None:
    payload = {
        "stdout_tail": (
            "FAILED tests/test_report_schemas.py::test_schema_samples_match - AssertionError\n"
            "1 failed in 1.2s"
        )
    }
    assert failed_test_nodeids(payload) == [
        "tests/test_report_schemas.py::test_schema_samples_match"
    ]


def test_test_failure_lanes_marks_schema_contract_failures() -> None:
    payload = {
        "command": ".venv/bin/python -m pytest tests/test_report_schemas.py",
        "stdout_tail": "FAILED tests/test_report_schemas.py::test_schema_samples_match",
    }
    lanes = {lane["lane_id"]: lane for lane in build_closeout_test_failure_lanes(payload, "ok")}
    assert lanes["report_schema_contract"]["status"] == "fail"
    assert lanes["report_schema_contract"]["failed_count"] == 1


def test_release_smoke_boundedness_gate_missing_budget() -> None:
    gate = release_smoke_boundedness_gate({"release_smoke": {}})
    assert gate["load_status"] == "missing_budget"
    assert gate["status"] == "unknown"


def test_live_make_check_gate_not_run_when_component_missing() -> None:
    gate = live_make_check_gate([], {})
    assert gate["load_status"] == "missing"
    assert gate["status"] == "not_run"


def test_closeout_readiness_state_blocks_without_source_clean_lane() -> None:
    collection = CloseoutComponentCollection(
        components=[],
        source_payloads={},
        blockers=[],
        accepted_risks=[],
        test_summary_payload={},
        test_summary_load_status="missing",
    )
    gates = CloseoutGates(
        test_failure_lanes=[],
        source_tree_coherence={"status": "pass"},
        coherence_blockers=[],
        coherence_risks=[],
        artifact_freshness_gate={},
        release_smoke_boundedness_gate={},
        live_make_check={"status": "pass"},
    )
    risk_state = CloseoutRiskState(
        blockers=[{"code": "source_clean_blocker"}],
        accepted_risks=[],
        accepted_risk_delta={},
        source_clean_blockers=[{"code": "source_clean_blocker"}],
        accepted_risk_scope_counts={"clean_lane_blocking_family_count": 0},
        clean_lane_blocking_risk_count=0,
    )
    readiness = closeout_readiness_state(
        collection,
        gates,
        risk_state,
        current_source_tree_fingerprint="abc",
    )
    assert readiness.release_readiness_state == RELEASE_STATE_BLOCKED
    assert readiness.machine_release_allowed is False
