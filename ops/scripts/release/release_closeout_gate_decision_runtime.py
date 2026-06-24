"""Pure closeout gate classification and readiness decision helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ops.scripts.core.release_currentness_state_runtime import (
    components_match_current_source_tree,
)

RELEASE_STATE_CLEAN_PASS = "clean_pass"
RELEASE_STATE_CONDITIONAL_PASS = "conditional_pass"
RELEASE_STATE_BLOCKED = "blocked"
RELEASE_STATE_UNKNOWN = "unknown"
RELEASE_READINESS_STATES = (
    RELEASE_STATE_CLEAN_PASS,
    RELEASE_STATE_CONDITIONAL_PASS,
    RELEASE_STATE_BLOCKED,
    RELEASE_STATE_UNKNOWN,
)

TEST_FAILURE_LANES = (
    {
        "lane_id": "report_schema_contract",
        "summary": "Schema and source-owned report contract tests must pass before release evidence is authoritative.",
        "command_markers": (
            "tests/test_report_schema_sample_regeneration.py",
            "tests/test_report_schemas.py",
        ),
        "failure_markers": (
            "tests/test_report_schema_sample_regeneration.py::",
            "tests/test_report_schemas.py::",
        ),
        "next_action": "Fix the failing schema or source-owned report contract, then rerun report-contract summary.",
    },
    {
        "lane_id": "runtime_telemetry_schema_contract",
        "summary": "Runtime telemetry schema-contract preservation tests must pass before release evidence is authoritative.",
        "command_markers": (
            "tests/test_auto_improve_iteration_runtime.py",
        ),
        "failure_markers": (
            "tests/test_auto_improve_iteration_runtime.py::",
        ),
        "next_action": "Fix the run-telemetry preservation/schema contract and rerun report-contract summary.",
    },
)
FAILED_NODEID_RE = re.compile(r"(?P<nodeid>tests/[A-Za-z0-9_./-]+\.py::[^\s]+)")


@dataclass(frozen=True)
class CloseoutGates:
    test_failure_lanes: list[dict[str, Any]]
    source_tree_coherence: dict[str, Any]
    coherence_blockers: list[dict[str, Any]]
    coherence_risks: list[dict[str, Any]]
    artifact_freshness_gate: dict[str, Any]
    release_smoke_boundedness_gate: dict[str, Any]
    live_make_check: dict[str, Any]


@dataclass(frozen=True)
class CloseoutRiskState:
    blockers: list[dict[str, Any]]
    accepted_risks: list[dict[str, Any]]
    accepted_risk_delta: dict[str, Any]
    source_clean_blockers: list[dict[str, Any]]
    accepted_risk_scope_counts: dict[str, int]
    clean_lane_blocking_risk_count: int


@dataclass(frozen=True)
class CloseoutReadinessState:
    checked_in_release_ready: bool
    live_rerun_release_ready: bool
    conditional_release_ready: bool
    clean_release_ready: bool
    release_readiness_state: str
    machine_release_allowed: bool
    operator_release_allowed: bool
    requires_accepted_risk_review: bool


@dataclass(frozen=True)
class CloseoutComponentCollection:
    components: list[dict[str, Any]]
    source_payloads: dict[str, dict[str, Any]]
    blockers: list[dict[str, Any]]
    accepted_risks: list[dict[str, Any]]
    test_summary_payload: dict[str, Any]
    test_summary_load_status: str


def release_readiness_state(
    *,
    checked_in_release_ready: bool,
    clean_release_ready: bool,
    accepted_risks: list[dict[str, Any]],
) -> str:
    if clean_release_ready:
        return RELEASE_STATE_CLEAN_PASS
    if checked_in_release_ready and accepted_risks:
        return RELEASE_STATE_CONDITIONAL_PASS
    if checked_in_release_ready:
        return RELEASE_STATE_UNKNOWN
    return RELEASE_STATE_BLOCKED


def release_smoke_boundedness_gate(
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = source_payloads.get("release_smoke", {})
    archive_budget = payload.get("archive_budget")
    if not isinstance(archive_budget, dict):
        return {
            "path": "ops/reports/release-smoke-report.json",
            "load_status": "missing_budget",
            "status": "unknown",
            "archive_budget_pass": False,
            "failing_budget_count": 0,
            "top_offender_count": 0,
            "summary": "release smoke archive_budget is unavailable",
        }
    if "blocking_budget_fail_count" in archive_budget:
        failing_budget_count = int(archive_budget.get("blocking_budget_fail_count", 0) or 0)
    else:
        budget_fields = [
            archive_budget.get("zip_path_byte_budget"),
            archive_budget.get("zip_component_byte_budget"),
        ]
        failing_budget_count = sum(
            1
            for item in budget_fields
            if isinstance(item, dict) and str(item.get("status", "")).strip() == "fail"
        )
    top_offenders = archive_budget.get("top_offenders")
    top_offender_count = len(top_offenders) if isinstance(top_offenders, list) else 0
    archive_budget_pass = bool(archive_budget.get("pass", False))
    status = "pass" if archive_budget_pass else "fail"
    return {
        "path": "ops/reports/release-smoke-report.json",
        "load_status": "ok",
        "status": status,
        "archive_budget_pass": archive_budget_pass,
        "failing_budget_count": failing_budget_count,
        "top_offender_count": top_offender_count,
        "summary": (
            f"release_smoke_boundedness status={status}; "
            f"failing_budget_count={failing_budget_count}; "
            f"top_offender_count={top_offender_count}"
        ),
    }


def live_make_check_gate(
    components: list[dict[str, Any]],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    component_row = next((item for item in components if item["name"] == "live_make_check"), {})
    payload = source_payloads.get("live_make_check", {})
    consistency = payload.get("nodeid_outcome_consistency")
    consistency = consistency if isinstance(consistency, dict) else {}
    execution_environment = payload.get("execution_environment")
    execution_environment = execution_environment if isinstance(execution_environment, dict) else {}
    toolchain = execution_environment.get("toolchain_contract")
    toolchain = toolchain if isinstance(toolchain, dict) else {}
    load_status = str(component_row.get("load_status", "missing")).strip() or "missing"
    source_status = str(payload.get("status", component_row.get("source_status", "unknown"))).strip() or "unknown"
    represents_full_suite = bool(payload.get("represents_full_suite", False))
    suite_scope = str(payload.get("suite_scope", "")).strip() or "unknown"
    nodeid_count = int(consistency.get("nodeid_count", 0) or 0)
    outcome_count = int(consistency.get("outcome_count", 0) or 0)
    consistency_status = str(consistency.get("status", "unknown")).strip() or "unknown"
    toolchain_status = str(toolchain.get("status", "unknown")).strip() or "unknown"
    toolchain_effect = str(toolchain.get("release_evidence_effect", "unknown")).strip() or "unknown"
    ready = (
        bool(component_row.get("ready"))
        and load_status == "ok"
        and source_status == "pass"
        and represents_full_suite
        and suite_scope == "full_suite"
        and consistency_status == "pass"
        and toolchain_status == "pass"
        and toolchain_effect == "eligible"
    )
    if ready:
        status = "pass"
    elif load_status != "ok":
        status = "not_run"
    else:
        status = "fail"
    return {
        "path": "ops/reports/test-execution-summary-full.json",
        "load_status": load_status,
        "status": status,
        "source_status": source_status,
        "ready": ready,
        "represents_full_suite": represents_full_suite,
        "suite_scope": suite_scope,
        "nodeid_count": nodeid_count,
        "outcome_count": outcome_count,
        "nodeid_outcome_consistency_status": consistency_status,
        "toolchain_contract_status": toolchain_status,
        "toolchain_release_evidence_effect": toolchain_effect,
        "blocking": not ready,
        "summary": (
            f"live_make_check status={status}; source_status={source_status}; "
            f"suite_scope={suite_scope}; represents_full_suite={represents_full_suite}; "
            f"nodeid_outcome_consistency={consistency_status}; toolchain={toolchain_status}/{toolchain_effect}"
        ),
    }


def failed_test_nodeids(payload: dict[str, Any]) -> list[str]:
    stdout_tail = str(payload.get("stdout_tail", ""))
    failed: set[str] = set()
    for line in stdout_tail.splitlines():
        if line.startswith("FAILED "):
            match = FAILED_NODEID_RE.search(line)
            if match:
                failed.add(match.group("nodeid"))
    if not failed:
        for match in FAILED_NODEID_RE.finditer(stdout_tail):
            failed.add(match.group("nodeid"))
    return sorted(failed)


def build_closeout_test_failure_lanes(payload: dict[str, Any], load_status: str) -> list[dict[str, Any]]:
    command = str(payload.get("command", "")).strip()
    failed_nodeids = failed_test_nodeids(payload) if load_status == "ok" else []
    lanes: list[dict[str, Any]] = []
    for definition in TEST_FAILURE_LANES:
        lane_id = str(definition["lane_id"])
        command_markers = tuple(str(item) for item in definition["command_markers"])
        failure_markers = tuple(str(item) for item in definition["failure_markers"])
        lane_failures = [
            nodeid
            for nodeid in failed_nodeids
            if any(marker in nodeid for marker in failure_markers)
        ]
        represented = load_status == "ok" and any(marker in command for marker in command_markers)
        if lane_failures:
            status = "fail"
            next_action = str(definition["next_action"])
        elif represented:
            status = "pass"
            next_action = "none"
        else:
            status = "not_run"
            next_action = f"Add {lane_id} to the release test execution summary evidence."
        lanes.append(
            {
                "lane_id": lane_id,
                "source_path": "ops/reports/test-execution-summary.json",
                "status": status,
                "represented_in_summary": represented,
                "failed_count": len(lane_failures),
                "failed_nodeids": lane_failures,
                "summary": str(definition["summary"]),
                "next_action": next_action,
            }
        )
    return lanes


def closeout_readiness_state(
    collection: CloseoutComponentCollection,
    gates: CloseoutGates,
    risk_state: CloseoutRiskState,
    *,
    current_source_tree_fingerprint: str,
) -> CloseoutReadinessState:
    checked_in_release_ready = not risk_state.source_clean_blockers
    live_rerun_release_ready = (
        checked_in_release_ready
        and all(lane["status"] == "pass" for lane in gates.test_failure_lanes)
        and gates.live_make_check["status"] == "pass"
        and components_match_current_source_tree(
            collection.components,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
        )
    )
    clean_release_ready = (
        live_rerun_release_ready
        and risk_state.clean_lane_blocking_risk_count == 0
        and gates.source_tree_coherence["status"] == "pass"
        and gates.live_make_check["status"] == "pass"
    )
    conditional_release_ready = (
        checked_in_release_ready
        and bool(risk_state.accepted_risks)
        and not clean_release_ready
    )
    release_state = release_readiness_state(
        checked_in_release_ready=checked_in_release_ready,
        clean_release_ready=clean_release_ready,
        accepted_risks=risk_state.accepted_risks,
    )
    return CloseoutReadinessState(
        checked_in_release_ready=checked_in_release_ready,
        live_rerun_release_ready=live_rerun_release_ready,
        conditional_release_ready=conditional_release_ready,
        clean_release_ready=clean_release_ready,
        release_readiness_state=release_state,
        machine_release_allowed=release_state == RELEASE_STATE_CLEAN_PASS,
        operator_release_allowed=release_state
        in {RELEASE_STATE_CLEAN_PASS, RELEASE_STATE_CONDITIONAL_PASS},
        requires_accepted_risk_review=release_state == RELEASE_STATE_CONDITIONAL_PASS,
    )
