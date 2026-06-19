from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_mtime_runtime import parse_generated_at
from ops.scripts.core.gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_BLOCKS_PROMOTION,
    canonical_gate_effect,
)
from ops.scripts.core.release_currentness_state_runtime import (
    components_match_current_source_tree,
    currentness_field,
)
from ops.scripts.core.source_tree_fingerprint_runtime import (
    producer_input_fingerprint,
    release_source_tree_divergence_diagnostics,
)
from ops.scripts.learning.learning_readiness_vocabulary import (
    LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
    LEARNING_STATUS_LIKELY,
)

from .release_closeout_envelope_runtime import FIXED_POINT_POLICY_PATH
from .release_closeout_risk_runtime import (
    COHERENCE_SOURCE,
    accepted_risk_count_by_scope,
    annotated_blocks_source_clean_lane,
    blocks_source_clean_lane,
    finalize_accepted_risks,
    release_closeout_issue,
    risk_delta,
    taxonomy_coverage_blockers,
)
from .release_closeout_source_runtime import SourceSpec, load_closeout_source
from .release_freshness_gate_runtime import artifact_freshness_gate_record
from .release_risk_taxonomy_runtime import annotate_release_risk

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

COHERENCE_POLICY = "allowed_divergence_with_fingerprints"

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
class ComponentInput:
    spec: SourceSpec
    load_status: str
    source_status: str
    ready: bool
    blockers: list[dict[str, Any]]
    accepted_risks: list[dict[str, Any]]
    generated_at: str = ""
    source_tree_fingerprint: str = ""
    producer_input_fingerprint: str = ""
    artifact_status: str = "unknown"
    currentness_status: str = "unknown"
    currentness_checked_at: str = ""
    report_mtime: str = ""
    modified_after_generated_at: bool = False
    summary: str = ""


@dataclass(frozen=True)
class CloseoutComponentCollection:
    components: list[dict[str, Any]]
    source_payloads: dict[str, dict[str, Any]]
    blockers: list[dict[str, Any]]
    accepted_risks: list[dict[str, Any]]
    test_summary_payload: dict[str, Any]
    test_summary_load_status: str


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


def _file_mtime_iso_z(path: Path) -> str:
    if not path.exists():
        return ""
    modified_at = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
    return modified_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _modified_after_generated_at(report_mtime: str, generated_at: str) -> bool:
    if not report_mtime or not generated_at:
        return False
    modified_at = parse_generated_at(report_mtime)
    generated = parse_generated_at(generated_at)
    if modified_at is None or generated is None:
        return False
    return modified_at > generated


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status", "")).strip() or "unknown"


def component(inputs: ComponentInput) -> dict[str, Any]:
    return {
        "name": inputs.spec.name,
        "path": inputs.spec.path,
        "load_status": inputs.load_status,
        "source_status": inputs.source_status,
        "generated_at": inputs.generated_at,
        "source_tree_fingerprint": inputs.source_tree_fingerprint,
        "producer_input_fingerprint": inputs.producer_input_fingerprint,
        "artifact_status": inputs.artifact_status,
        "currentness_status": inputs.currentness_status,
        "currentness_checked_at": inputs.currentness_checked_at,
        "report_mtime": inputs.report_mtime,
        "modified_after_generated_at": inputs.modified_after_generated_at,
        "ready": inputs.ready,
        "blocker_count": len(inputs.blockers),
        "accepted_risk_family_count": len(inputs.accepted_risks),
        "summary": inputs.summary,
    }


def artifact_freshness_stable_contract_debt_only(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    hard_attention_fields = (
        "schema_invalid_artifact_count",
        "schema_unavailable_artifact_count",
        "root_ephemeral_artifact_count",
        "non_utf8_text_artifact_count",
        "stale_artifact_count",
        "mtime_sensitive_attention_artifact_count",
        "mtime_sensitive_attention_issue_count",
        "operational_attention_artifact_count",
        "operational_attention_issue_count",
    )
    if any(int(summary.get(field, 0) or 0) > 0 for field in hard_attention_fields):
        return False
    return int(summary.get("stable_contract_debt_issue_count", 0) or 0) > 0


def release_owned_artifact_freshness_paths(vault: Path) -> set[str]:
    path = vault / FIXED_POINT_POLICY_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    tracked = payload.get("tracked_artifacts")
    if not isinstance(tracked, list):
        return set()
    return {
        rel_path
        for rel_path in tracked
        if isinstance(rel_path, str) and rel_path != "ops/reports/artifact-freshness-report.json"
    }


def release_owned_artifact_freshness_attention(vault: Path, payload: dict[str, Any]) -> bool:
    records = payload.get("artifact_records")
    if not isinstance(records, list):
        return True
    release_owned_paths = release_owned_artifact_freshness_paths(vault)
    if not release_owned_paths:
        return True
    for item in records:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path", "")).strip()
        if rel_path not in release_owned_paths:
            continue
        raw_issues = item.get("issues")
        issues = [str(issue).strip() for issue in raw_issues] if isinstance(raw_issues, list) else []
        if any(
            issue
            in {
                "source_revision_mismatch",
                "source_revision_unknown",
                "source_tree_fingerprint_mismatch",
                "source_tree_fingerprint_unknown",
                "generated_at_older_than_file_mtime",
                "test_target_missing",
            }
            or issue.startswith("test_target_fingerprint_mismatch")
            for issue in issues
        ):
            return True
    return False


def artifact_freshness_gate(
    vault: Path,
    components: list[dict[str, Any]],
    source_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    component_row = next((item for item in components if item["name"] == "artifact_freshness"), {})
    payload = source_payloads.get("artifact_freshness", {})
    return artifact_freshness_gate_record(
        component=component_row,
        payload=payload,
        stable_contract_debt_only=artifact_freshness_stable_contract_debt_only(payload),
        release_owned_attention=release_owned_artifact_freshness_attention(vault, payload),
    )


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


def evaluate_status_component(
    spec: SourceSpec,
    payload: dict[str, Any],
    *,
    pass_statuses: set[str],
    accepted_statuses: set[str],
    blocker_code: str,
    accepted_code: str,
    accepted_message: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    status = _status(payload)
    if status in pass_statuses:
        return [], [], f"{spec.name} status={status}"
    if status in accepted_statuses:
        return [], [
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code=accepted_code,
                severity="warn",
                gate_effect=GATE_EFFECT_ADVISORY,
                message=accepted_message,
            )
        ], f"{spec.name} status={status}"
    return [
        release_closeout_issue(
            source=spec.name,
            source_path=spec.path,
            code=blocker_code,
            message=f"{spec.name} status={status}; expected one of {sorted(pass_statuses)}.",
            required_evidence=[f"Regenerate {spec.path} with a passing status."],
        )
    ], [], f"{spec.name} status={status}"


def evaluate_auto_improve(
    spec: SourceSpec,
    payload: dict[str, Any],
    *,
    learning_claim_context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    blockers: list[dict[str, Any]] = []
    accepted_risks: list[dict[str, Any]] = []
    execution = payload.get("execution_readiness")
    can_run = bool(isinstance(execution, dict) and execution.get("can_run"))
    can_execute_trial = bool(payload.get("can_execute_trial", can_run))
    promotion_blockers = payload.get("promotion_blockers")
    has_promotion_blockers = isinstance(promotion_blockers, list)
    if not can_execute_trial and not has_promotion_blockers:
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="auto_improve_execution_not_ready",
                gate_effect=GATE_EFFECT_BLOCKS_EXECUTION,
                message="auto-improve execution_readiness.can_run is false.",
                required_evidence=[
                    "Regenerate auto-improve readiness after the runnable proposal queue is non-empty."
                ],
            )
        )

    blocker_fields: tuple[tuple[str, Any], ...] = (
        ("promotion_blockers", payload.get("promotion_blockers")),
        ("clean_release_blockers", payload.get("clean_release_blockers")),
        ("learning_claim_blockers", payload.get("learning_claim_blockers")),
    )
    if not any(isinstance(items, list) for _, items in blocker_fields):
        blocker_fields = (
            ("release_blockers", payload.get("release_blockers")),
            ("learning_blockers", payload.get("learning_blockers")),
        )
    claims_learning_improved = bool(learning_claim_context.get("claims_learning_improved"))
    skipped_learning_claim_blocker_count = 0
    seen_blocker_ids: set[str] = set()
    for _, blocker_items in blocker_fields:
        if not isinstance(blocker_items, list):
            continue
        for item in blocker_items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("id", "")).strip() or "auto_improve_release_blocker"
            if code in seen_blocker_ids:
                continue
            if "release_blocker" in item and not bool(item.get("release_blocker")):
                continue
            status = str(item.get("status", "open")).strip() or "open"
            if status not in {"open", "accepted_risk"} and not bool(item.get("accepted_risk")):
                continue
            seen_blocker_ids.add(code)
            if code == LEARNING_REVIEW_REQUIRED_BLOCKER_ID and not claims_learning_improved:
                skipped_learning_claim_blocker_count += 1
                continue
            message = str(item.get("reason", "")).strip() or code
            issue = release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code=code,
                severity=str(item.get("severity", "blocker")).strip() or "blocker",
                gate_effect=canonical_gate_effect(
                    item.get("gate_effect"),
                    active_default=GATE_EFFECT_BLOCKS_PROMOTION,
                ),
                message=message,
                required_evidence=[
                    str(evidence)
                    for evidence in item.get("required_evidence", [])
                    if str(evidence).strip()
                ],
            )
            if bool(item.get("accepted_risk")):
                issue["gate_effect"] = GATE_EFFECT_ADVISORY
                accepted_risks.append(issue)
            else:
                blockers.append(issue)

    learning = payload.get("learning_readiness")
    learning_status = (
        str(learning.get("status", "")).strip()
        if isinstance(learning, dict)
        else "unknown"
    )
    can_promote_result = bool(
        payload.get("can_promote_result", can_execute_trial and learning_status == LEARNING_STATUS_LIKELY)
    )
    return (
        blockers,
        accepted_risks,
        f"can_execute_trial={can_execute_trial}; can_promote_result={can_promote_result}; "
        f"learning_status={learning_status}; claims_learning_improved={claims_learning_improved}; "
        f"skipped_learning_claim_blocker_count={skipped_learning_claim_blocker_count}",
    )


def evaluate_test_summary(
    spec: SourceSpec,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    blockers, accepted_risks, status_summary = evaluate_status_component(
        spec,
        payload,
        pass_statuses={"pass"},
        accepted_statuses=set(),
        blocker_code="test_summary_not_pass",
        accepted_code="",
        accepted_message="",
    )
    lifecycle = payload.get("deselection_lifecycle")
    if not isinstance(lifecycle, dict):
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="test_deselection_lifecycle_missing",
                message="test execution summary is missing deselection_lifecycle.",
                required_evidence=["Regenerate test execution summary with the current deselection policy."],
            )
        )
        return blockers, accepted_risks, f"{status_summary}; deselection_lifecycle=missing"
    if str(lifecycle.get("status", "")).strip() != "pass":
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="test_deselection_lifecycle_failed",
                message="test execution summary deselection lifecycle failed.",
                required_evidence=["Remove expired/over-budget deselections or renew the policy before closeout."],
            )
        )
    for item in payload.get("deselected_tests", []):
        if not isinstance(item, dict):
            continue
        nodeid = str(item.get("nodeid", "")).strip()
        if bool(item.get("release_blocking")):
            blockers.append(
                release_closeout_issue(
                    source=spec.name,
                    source_path=spec.path,
                    code="test_deselection_release_blocking",
                    message=f"{nodeid} is deselected and marked release blocking.",
                    required_evidence=["Run or fix release-blocking deselected tests before closeout."],
                )
            )
            continue
        if not bool(item.get("expected_to_pass_after_refresh")):
            blockers.append(
                release_closeout_issue(
                    source=spec.name,
                    source_path=spec.path,
                    code="test_deselection_not_expected_to_pass_after_refresh",
                    message=f"{nodeid} is deselected without expected_to_pass_after_refresh=true.",
                    required_evidence=["Restore the test or document a release-blocking fix path."],
                )
            )
            continue
        expires_at = str(item.get("expires_at", "")).strip()
        risk_owner = str(item.get("risk_owner", "")).strip()
        policy_ref = str(item.get("policy_ref", "")).strip()
        if not expires_at or not risk_owner or not policy_ref:
            blockers.append(
                release_closeout_issue(
                    source=spec.name,
                    source_path=spec.path,
                    code="test_deselection_acceptance_incomplete",
                    message=f"{nodeid} deselection is missing risk_owner, expires_at, or policy_ref.",
                    required_evidence=["Refresh the structured deselection policy lifecycle metadata."],
                )
            )
            continue
        accepted_risks.append(
            {
                **release_closeout_issue(
                    source=spec.name,
                    source_path=spec.path,
                    code="test_deselection_accepted_risk",
                    severity="warn",
                    gate_effect=GATE_EFFECT_ADVISORY,
                    message=f"{nodeid} is temporarily deselected by structured policy.",
                    required_evidence=[
                        f"Deselection policy: {policy_ref}",
                        "Re-run or remove the deselected test before policy expiry.",
                    ],
                ),
                "risk_acceptance": {
                    "accepted_by": "test_deselection_policy",
                    "accepted_at": str(payload.get("generated_at", "")).strip(),
                    "expires_at": expires_at,
                    "risk_owner": risk_owner,
                    "revalidation_condition": "Remove the deselection or refresh the checked-in report contract evidence.",
                    "rollback_trigger": "Treat this deselection as a blocker if it expires or becomes release_blocking.",
                    "acceptance_source": policy_ref,
                    "linked_blocker_id": nodeid,
                },
            }
        )
    return (
        blockers,
        accepted_risks,
        f"{status_summary}; deselection_lifecycle={lifecycle.get('status', 'unknown')}",
    )


def evaluate_live_make_check(
    spec: SourceSpec,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    blockers, accepted_risks, status_summary = evaluate_status_component(
        spec,
        payload,
        pass_statuses={"pass"},
        accepted_statuses=set(),
        blocker_code="live_make_check_not_pass",
        accepted_code="",
        accepted_message="",
    )
    suite_scope = str(payload.get("suite_scope", "")).strip() or "unknown"
    represents_full_suite = bool(payload.get("represents_full_suite", False))
    if not represents_full_suite or suite_scope != "full_suite":
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="live_make_check_not_full_suite",
                message=(
                    "live make-check evidence must be generated from the full test suite "
                    f"(suite_scope={suite_scope}; represents_full_suite={represents_full_suite})."
                ),
                required_evidence=["Regenerate ops/reports/test-execution-summary-full.json with make test-execution-summary-full."],
            )
        )
    consistency = payload.get("nodeid_outcome_consistency")
    consistency = consistency if isinstance(consistency, dict) else {}
    consistency_status = str(consistency.get("status", "unknown")).strip() or "unknown"
    if consistency_status != "pass":
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="live_make_check_nodeid_outcome_mismatch",
                message=f"full-suite nodeid/outcome consistency status={consistency_status}; expected pass.",
                required_evidence=["Rerun the full-suite summary and reconcile collected nodeids with pytest outcomes."],
            )
        )
    execution_environment = payload.get("execution_environment")
    execution_environment = execution_environment if isinstance(execution_environment, dict) else {}
    toolchain = execution_environment.get("toolchain_contract")
    toolchain = toolchain if isinstance(toolchain, dict) else {}
    toolchain_status = str(toolchain.get("status", "unknown")).strip() or "unknown"
    toolchain_effect = str(toolchain.get("release_evidence_effect", "unknown")).strip() or "unknown"
    if toolchain_status != "pass" or toolchain_effect != "eligible":
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="live_make_check_toolchain_not_eligible",
                message=(
                    "full-suite evidence was not produced by an eligible toolchain "
                    f"(status={toolchain_status}; release_evidence_effect={toolchain_effect})."
                ),
                required_evidence=["Regenerate full-suite evidence with a supported Python/pytest toolchain."],
            )
        )
    return (
        blockers,
        accepted_risks,
        (
            f"{status_summary}; suite_scope={suite_scope}; represents_full_suite={represents_full_suite}; "
            f"nodeid_outcome_consistency={consistency_status}; "
            f"toolchain={toolchain_status}/{toolchain_effect}"
        ),
    )


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


def test_failure_lanes(payload: dict[str, Any], load_status: str) -> list[dict[str, Any]]:
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


def evaluate_release_smoke_source(
    spec: SourceSpec,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    blockers, accepted_risks, summary = evaluate_status_component(
        spec,
        payload,
        pass_statuses={"pass"},
        accepted_statuses=set(),
        blocker_code="release_smoke_failed",
        accepted_code="",
        accepted_message="",
    )
    archive_budget = payload.get("archive_budget")
    if isinstance(archive_budget, dict) and not bool(archive_budget.get("pass", False)):
        blockers.append(
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="release_smoke_boundedness_failed",
                message="release smoke archive path/component boundedness budget failed.",
                required_evidence=[
                    "Shorten archive member paths or update release archive packaging before clean release."
                ],
            )
        )
    return blockers, accepted_risks, summary


def evaluate_external_report_reference_manifest(
    spec: SourceSpec,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    provenance = payload.get("distribution_provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    provenance_status = str(provenance.get("status", "unknown")).strip() or "unknown"
    mode = str(provenance.get("mode", "advisory")).strip() or "advisory"
    summary = f"{spec.name} mode={mode}; distribution_provenance.status={provenance_status}"
    if mode == "strict_review_release" and provenance_status == "basis_current_match":
        return [], [], summary
    if provenance_status == "current_distribution_missing":
        return [], [
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="external_report_strict_unavailable",
                severity="warn",
                gate_effect=GATE_EFFECT_ADVISORY,
                message=(
                    "strict external report release check is unavailable because no current "
                    "distribution ZIP was provided in this non-sealed closeout"
                ),
                required_evidence=[
                    "Run make release-evidence-closeout-sealed before sealed release signoff."
                ],
            )
        ], summary
    return [
        release_closeout_issue(
            source=spec.name,
            source_path=spec.path,
            code="external_report_reference_manifest_failed",
            message=(
                f"{summary}; expected strict_review_release basis_current_match or "
                "typed non-sealed unavailability."
            ),
            required_evidence=[
                "Refresh external report provenance against the current distribution ZIP."
            ],
        )
    ], [], summary


def evaluate_artifact_freshness_source(
    vault: Path,
    spec: SourceSpec,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    status = _status(payload)
    if status == "pass":
        return [], [], f"{spec.name} status={status}"
    if status == "attention":
        if artifact_freshness_stable_contract_debt_only(payload):
            return [], [
                release_closeout_issue(
                    source=spec.name,
                    source_path=spec.path,
                    code="artifact_freshness_stable_contract_debt_advisory",
                    severity="warn",
                    gate_effect=GATE_EFFECT_ADVISORY,
                    message=(
                        "artifact freshness has stable contract debt only; current release evidence "
                        "has no operational freshness blocker."
                    ),
                )
            ], f"{spec.name} status={status}"
        if not release_owned_artifact_freshness_attention(vault, payload):
            return [], [], f"{spec.name} status={status}; release_owned_attention=0"
        return [], [
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code="artifact_freshness_attention",
                severity="warn",
                gate_effect=GATE_EFFECT_ADVISORY,
                message="artifact freshness has attention-level debt but no fail-level freshness blocker.",
            )
        ], f"{spec.name} status={status}"
    return [
        release_closeout_issue(
            source=spec.name,
            source_path=spec.path,
            code="artifact_freshness_failed",
            message=f"{spec.name} status={status}; expected one of ['pass'].",
            required_evidence=[f"Regenerate {spec.path} with a passing status."],
        )
    ], [], f"{spec.name} status={status}"


def evaluate_simple_source(
    vault: Path,
    spec: SourceSpec,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str] | None:
    if spec.name == "artifact_freshness":
        return evaluate_artifact_freshness_source(vault, spec, payload)
    specs = {
        "bootstrap_preflight": ({"pass"}, set(), "bootstrap_preflight_failed", "", ""),
        "source_package_clean_extract": (
            {"pass"},
            set(),
            "source_package_clean_extract_failed",
            "",
            "",
        ),
        "raw_registry": (
            {"pass"},
            {"warn"},
            "raw_registry_preflight_failed",
            "raw_registry_preflight_warnings",
            "raw registry preflight emitted warnings; this is accepted as release advisory risk.",
        ),
        "generated_index": (
            {"pass"},
            {"attention"},
            "generated_index_unknown_status",
            "generated_index_archive_advisory",
            "generated artifact index reports archive candidates as advisory release risk.",
        ),
        "supply_chain_gate": ({"pass"}, set(), "supply_chain_gate_failed", "", ""),
        "sbom_readiness": ({"pass"}, set(), "sbom_readiness_gate_failed", "", ""),
    }
    if spec.name not in specs:
        return None
    pass_statuses, accepted_statuses, blocker_code, accepted_code, accepted_message = specs[
        spec.name
    ]
    return evaluate_status_component(
        spec,
        payload,
        pass_statuses=pass_statuses,
        accepted_statuses=accepted_statuses,
        blocker_code=blocker_code,
        accepted_code=accepted_code,
        accepted_message=accepted_message,
    )


def evaluate_source(
    vault: Path,
    spec: SourceSpec,
    payload: dict[str, Any],
    *,
    learning_claim_context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    simple_result = evaluate_simple_source(vault, spec, payload)
    if simple_result is not None:
        return simple_result
    if spec.name == "release_smoke":
        return evaluate_release_smoke_source(spec, payload)
    if spec.name == "external_report_reference_manifest":
        return evaluate_external_report_reference_manifest(spec, payload)
    if spec.name == "test_summary":
        return evaluate_test_summary(spec, payload)
    if spec.name == "live_make_check":
        return evaluate_live_make_check(spec, payload)
    if spec.name == "auto_improve_readiness":
        return evaluate_auto_improve(
            spec,
            payload,
            learning_claim_context=learning_claim_context,
        )
    raise ValueError(f"unsupported release closeout source: {spec.name}")


def source_tree_coherence(
    vault: Path,
    components: list[dict[str, Any]],
    *,
    current_source_tree_fingerprint: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    loaded_components = [item for item in components if item["load_status"] == "ok"]
    fingerprints = {
        str(item.get("source_tree_fingerprint", "")).strip()
        for item in loaded_components
        if str(item.get("source_tree_fingerprint", "")).strip()
    }
    missing_fingerprint_components = [
        str(item["name"])
        for item in loaded_components
        if not str(item.get("source_tree_fingerprint", "")).strip()
    ]
    modified_after_components = [
        str(item["name"])
        for item in loaded_components
        if bool(item.get("modified_after_generated_at"))
    ]
    status = "pass"
    blockers: list[dict[str, Any]] = []
    accepted_risks: list[dict[str, Any]] = []
    if missing_fingerprint_components:
        status = "fail"
        blockers.append(
            release_closeout_issue(
                source=COHERENCE_SOURCE,
                source_path="ops/reports/release-closeout-summary.json",
                code="source_tree_coherence_missing_fingerprint",
                message=(
                    "release closeout source reports are missing source_tree_fingerprint: "
                    + ", ".join(missing_fingerprint_components)
                ),
                required_evidence=[
                    "Regenerate each component report with a canonical artifact envelope before release closeout."
                ],
            )
        )
    elif len(fingerprints) > 1 or modified_after_components:
        status = "attention"
        accepted_risks.append(
            release_closeout_issue(
                source=COHERENCE_SOURCE,
                source_path="ops/reports/release-closeout-summary.json",
                code="source_tree_coherence_attention",
                severity="warn",
                gate_effect=GATE_EFFECT_ADVISORY,
                message=(
                    "release closeout component evidence does not form a single strict source-tree cohort."
                ),
                required_evidence=[
                    "Regenerate release evidence in one closeout chain or document why fingerprint divergence is acceptable."
                ],
            )
        )
    divergence_diagnostics = release_source_tree_divergence_diagnostics(
        vault,
        loaded_components,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
    )
    return (
        {
            "status": status,
            "policy": COHERENCE_POLICY,
            "component_count": len(components),
            "loaded_component_count": len(loaded_components),
            "component_fingerprint_count": len(fingerprints),
            "missing_fingerprint_component_count": len(missing_fingerprint_components),
            "release_relevant_file_modified_after_component_count": len(modified_after_components),
            "divergence_diagnostics": divergence_diagnostics,
            "components": [
                {
                    "name": str(item["name"]),
                    "path": str(item["path"]),
                    "ready": bool(item["ready"]),
                    "source_tree_fingerprint": str(item.get("source_tree_fingerprint", "")).strip(),
                    "producer_input_fingerprint": str(item.get("producer_input_fingerprint", "")).strip(),
                    "generated_at": str(item.get("generated_at", "")).strip(),
                    "report_mtime": str(item.get("report_mtime", "")).strip(),
                    "modified_after_generated_at": bool(item.get("modified_after_generated_at")),
                }
                for item in components
            ],
        },
        blockers,
        accepted_risks,
    )


def apply_learning_signoff(
    blockers: list[dict[str, Any]],
    accepted_risks: list[dict[str, Any]],
    learning_signoff: dict[str, Any],
    *,
    learning_signoff_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not bool(learning_signoff.get("active")):
        return blockers, accepted_risks
    remaining_blockers: list[dict[str, Any]] = []
    converted_risks = list(accepted_risks)
    for blocker in blockers:
        if blocker.get("code") != LEARNING_REVIEW_REQUIRED_BLOCKER_ID:
            remaining_blockers.append(blocker)
            continue
        accepted = dict(blocker)
        accepted["severity"] = "warn"
        accepted["gate_effect"] = GATE_EFFECT_ADVISORY
        accepted["message"] = (
            f"{accepted['message']} Accepted by {learning_signoff['accepted_by']} "
            f"until {learning_signoff['expires_at']}; owner={learning_signoff['risk_owner']}."
        )
        accepted["required_evidence"] = [
            f"Signoff artifact: {learning_signoff_path}",
            f"Revalidation condition: {learning_signoff['revalidation_condition']}",
            f"Rollback trigger: {learning_signoff['rollback_trigger']}",
        ]
        accepted["risk_acceptance"] = {
            "accepted_by": str(learning_signoff["accepted_by"]),
            "accepted_at": str(learning_signoff["accepted_at"]),
            "expires_at": str(learning_signoff["expires_at"]),
            "risk_owner": str(learning_signoff["risk_owner"]),
            "revalidation_condition": str(learning_signoff["revalidation_condition"]),
            "rollback_trigger": str(learning_signoff["rollback_trigger"]),
            "acceptance_source": learning_signoff_path,
            "linked_blocker_id": LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
        }
        converted_risks.append(accepted)
    return remaining_blockers, converted_risks


def component_input_from_source(
    vault: Path,
    spec: SourceSpec,
    payload: dict[str, Any],
    load_status: str,
    component_blockers: list[dict[str, Any]],
    component_risks: list[dict[str, Any]],
    *,
    ready: bool,
    summary: str,
) -> ComponentInput:
    generated_at = str(payload.get("generated_at", "")).strip()
    report_mtime = _file_mtime_iso_z(vault / spec.path)
    return ComponentInput(
        spec=spec,
        load_status=load_status,
        source_status=_status(payload),
        generated_at=generated_at,
        source_tree_fingerprint=str(
            payload.get("source_tree_fingerprint", "")
        ).strip(),
        producer_input_fingerprint=producer_input_fingerprint(payload),
        artifact_status=str(payload.get("artifact_status", "")).strip()
        or "unknown",
        currentness_status=currentness_field(payload, "status") or "unknown",
        currentness_checked_at=currentness_field(payload, "checked_at"),
        report_mtime=report_mtime,
        modified_after_generated_at=_modified_after_generated_at(
            report_mtime,
            generated_at,
        ),
        ready=ready,
        blockers=component_blockers,
        accepted_risks=component_risks,
        summary=summary,
    )


def collect_closeout_components(
    vault: Path,
    source_specs: tuple[SourceSpec, ...],
    risk_taxonomy: dict[str, Any],
    learning_claim_context: dict[str, Any],
) -> CloseoutComponentCollection:
    components: list[dict[str, Any]] = []
    source_payloads: dict[str, dict[str, Any]] = {}
    blockers: list[dict[str, Any]] = []
    accepted_risks: list[dict[str, Any]] = []
    test_summary_payload: dict[str, Any] = {}
    test_summary_load_status = "missing"
    for spec in source_specs:
        payload, load_status, load_blockers = load_closeout_source(vault, spec)
        source_payloads[spec.name] = payload
        if spec.name == "test_summary":
            test_summary_payload = payload
            test_summary_load_status = load_status
        component_blockers = list(load_blockers)
        component_risks: list[dict[str, Any]] = []
        summary = f"{spec.name} load_status={load_status}"
        if not load_blockers:
            evaluated_blockers, evaluated_risks, summary = evaluate_source(
                vault,
                spec,
                payload,
                learning_claim_context=learning_claim_context,
            )
            component_blockers.extend(evaluated_blockers)
            component_risks.extend(evaluated_risks)
        ready = not any(
            annotated_blocks_source_clean_lane(blocker, risk_taxonomy)
            for blocker in component_blockers
        )
        blockers.extend(component_blockers)
        accepted_risks.extend(component_risks)
        components.append(
            component(
                component_input_from_source(
                    vault,
                    spec,
                    payload,
                    load_status,
                    component_blockers,
                    component_risks,
                    ready=ready,
                    summary=summary,
                )
            )
        )
    return CloseoutComponentCollection(
        components=components,
        source_payloads=source_payloads,
        blockers=blockers,
        accepted_risks=accepted_risks,
        test_summary_payload=test_summary_payload,
        test_summary_load_status=test_summary_load_status,
    )


def closeout_gates(
    vault: Path,
    collection: CloseoutComponentCollection,
    *,
    current_source_tree_fingerprint: str,
) -> CloseoutGates:
    test_failure_lanes_result = test_failure_lanes(
        collection.test_summary_payload,
        collection.test_summary_load_status,
    )
    source_tree_coherence_result, coherence_blockers, coherence_risks = (
        source_tree_coherence(
            vault,
            collection.components,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
        )
    )
    return CloseoutGates(
        test_failure_lanes=test_failure_lanes_result,
        source_tree_coherence=source_tree_coherence_result,
        coherence_blockers=coherence_blockers,
        coherence_risks=coherence_risks,
        artifact_freshness_gate=artifact_freshness_gate(
            vault,
            collection.components,
            collection.source_payloads,
        ),
        release_smoke_boundedness_gate=release_smoke_boundedness_gate(
            collection.source_payloads
        ),
        live_make_check=live_make_check_gate(
            collection.components,
            collection.source_payloads,
        ),
    )


def closeout_risk_state(
    collection: CloseoutComponentCollection,
    gates: CloseoutGates,
    *,
    previous_closeout: dict[str, Any],
    learning_signoff: dict[str, Any],
    risk_taxonomy: dict[str, Any],
    generated_at: str,
    learning_signoff_path: str,
) -> CloseoutRiskState:
    blockers = [*collection.blockers, *gates.coherence_blockers]
    accepted_risks = [*collection.accepted_risks, *gates.coherence_risks]
    blockers, accepted_risks = apply_learning_signoff(
        blockers, accepted_risks, learning_signoff, learning_signoff_path=learning_signoff_path
    )
    expired_risk_blockers, accepted_risks = finalize_accepted_risks(
        accepted_risks, generated_at=generated_at
    )
    blockers.extend(expired_risk_blockers)
    blockers.extend(taxonomy_coverage_blockers([*blockers, *accepted_risks], risk_taxonomy))
    annotated_blockers = [
        annotate_release_risk(blocker, risk_taxonomy) for blocker in blockers
    ]
    annotated_risks = [
        annotate_release_risk(risk, risk_taxonomy) for risk in accepted_risks
    ]
    source_clean_blockers = [
        blocker for blocker in annotated_blockers if blocks_source_clean_lane(blocker)
    ]
    scope_counts = accepted_risk_count_by_scope(annotated_risks)
    return CloseoutRiskState(
        blockers=annotated_blockers,
        accepted_risks=annotated_risks,
        accepted_risk_delta=risk_delta(previous_closeout, annotated_risks),
        source_clean_blockers=source_clean_blockers,
        accepted_risk_scope_counts=scope_counts,
        clean_lane_blocking_risk_count=scope_counts[
            "clean_lane_blocking_family_count"
        ],
    )


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
