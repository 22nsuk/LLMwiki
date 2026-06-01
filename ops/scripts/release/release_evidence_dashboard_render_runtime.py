from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.policy_runtime import report_path
from ops.scripts.schema_constants_runtime import RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH

PRODUCER = "ops.scripts.release_evidence_dashboard"
CLOSEOUT_PATH = "ops/reports/release-closeout-summary.json"
FIXED_POINT_PATH = "ops/reports/release-closeout-fixed-point.json"
FIXED_POINT_COST_TREND_PATH = "ops/reports/release-closeout-fixed-point-cost-trend.json"
SIGNOFF_REVALIDATION_PATH = "ops/reports/learning-readiness-signoff-revalidation.json"
ARTIFACT_FRESHNESS_PATH = "ops/reports/artifact-freshness-report.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"


@dataclass(frozen=True)
class DashboardRenderInputs:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    generated_at: str
    current_fingerprint: str
    reports: Any
    signals: Any
    gates: list[dict[str, Any]]
    status_counts: Any


def _freshness_debt_summary(
    payload: dict[str, Any], load_status: str
) -> dict[str, Any]:
    if load_status != "ok":
        return {
            "load_status": load_status,
            "status": "unknown",
            "stable_debt_count": 0,
            "schema_invalid_artifact_count": 0,
        }
    summary_payload = payload.get("summary")
    summary: dict[str, Any] = (
        summary_payload if isinstance(summary_payload, dict) else {}
    )
    return {
        "load_status": load_status,
        "status": str(payload.get("status", "")).strip(),
        "stable_debt_count": int(
            summary.get(
                "stable_debt_count", summary.get("stable_contract_debt_issue_count", 0)
            )
            or 0
        ),
        "schema_invalid_artifact_count": int(
            summary.get("schema_invalid_artifact_count", 0) or 0
        ),
    }


def _release_smoke_boundedness_signal(closeout: dict[str, Any]) -> dict[str, Any]:
    gate = closeout.get("release_smoke_boundedness_gate")
    if not isinstance(gate, dict):
        return {
            "path": "ops/reports/release-smoke-report.json",
            "status": "unknown",
            "archive_budget_pass": False,
            "failing_budget_count": 0,
            "top_offender_count": 0,
            "summary": "release smoke boundedness gate unavailable from closeout summary",
        }
    return {
        "path": str(gate.get("path", "ops/reports/release-smoke-report.json")).strip()
        or "ops/reports/release-smoke-report.json",
        "status": str(gate.get("status", "unknown")).strip() or "unknown",
        "archive_budget_pass": bool(gate.get("archive_budget_pass", False)),
        "failing_budget_count": int(gate.get("failing_budget_count", 0) or 0),
        "top_offender_count": int(gate.get("top_offender_count", 0) or 0),
        "summary": str(gate.get("summary", "")).strip()
        or "release smoke boundedness gate loaded",
    }


def _dashboard_inputs_payload(reports: Any, signals: Any) -> dict[str, Any]:
    return {
        "release_closeout_summary": signals.closeout_input,
        "release_closeout_fixed_point": {
            "path": FIXED_POINT_PATH,
            "load_status": reports.fixed_point_load_status,
            "status": signals.finalizer_duration["fixed_point_report_status"],
            "converged": signals.finalizer_duration["converged"],
        },
        "release_closeout_fixed_point_cost_trend": {
            "path": FIXED_POINT_COST_TREND_PATH,
            "load_status": reports.cost_trend_load_status,
            "status": str(reports.cost_trend.get("status", "unknown")).strip()
            if reports.cost_trend_load_status == "ok"
            else "unknown",
        },
        "learning_readiness_signoff_revalidation": {
            "path": SIGNOFF_REVALIDATION_PATH,
            "load_status": reports.revalidation_load_status,
            "status": str(reports.revalidation.get("status", "")).strip(),
        },
        "artifact_freshness": _freshness_debt_summary(
            reports.freshness, reports.freshness_load_status
        ),
        "learning_delta_scoreboard": signals.learning_guard,
    }


def _accepted_risk_delta_payload(closeout: dict[str, Any]) -> dict[str, Any]:
    return closeout.get(
        "accepted_risk_delta",
        {
            "status": "no_previous_report",
            "previous_report_generated_at": "",
            "added_count": 0,
            "removed_count": 0,
            "unchanged_count": 0,
            "added": [],
            "removed": [],
            "unchanged": [],
            "summary": "No release closeout accepted-risk delta was available.",
        },
    )


def _dashboard_summary_payload(
    gates: list[dict[str, Any]],
    counts: Any,
    learning_guard: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_count": len(gates),
        "authoritative_gate_count": sum(
            1 for gate in gates if gate["authoritative_for_release"]
        ),
        "checked_in_fail_count": sum(
            1 for gate in gates if gate["checked_in_state"] == "fail"
        ),
        "live_rerun_fail_count": sum(
            1 for gate in gates if gate["live_rerun_state"]["status"] == "fail"
        ),
        "live_rerun_not_run_count": counts.not_run_count,
        "accepted_risk_count": counts.accepted_risk_count,
        "gate_attention_count": counts.gate_attention_count,
        "required_input_fail_count": counts.required_input_fail_count,
        "learning_claim_guard_status": learning_guard["status"],
        "learning_claim_allowed": learning_guard["learning_claim_allowed"],
        "learning_likely": learning_guard["learning_likely"],
        "bounded_learning_claim_allowed": learning_guard[
            "bounded_learning_claim_allowed"
        ],
        "confirmed_learning_improvement_allowed": learning_guard[
            "confirmed_learning_improvement_allowed"
        ],
        "improvement_claim_status": learning_guard["improvement_claim_status"],
        "confirmed_learning_improvement_status": learning_guard[
            "confirmed_learning_improvement_status"
        ],
        "evidence_cohort_status": learning_guard["evidence_cohort_status"],
        "learning_claim_blocker_status": learning_guard["learning_claim_blocker_status"],
        "confirmed_blocking_predicate_ids": learning_guard[
            "confirmed_blocking_predicate_ids"
        ],
        "confirmed_evidence_summary": learning_guard["confirmed_evidence_summary"],
        "claim_level": learning_guard["claim_level"],
        "claim_scope": learning_guard["claim_scope"],
        "learning_claim_unlock_review_status": learning_guard[
            "learning_claim_unlock_review_status"
        ],
        "learning_claim_unlock_review_approved": learning_guard[
            "learning_claim_unlock_review_approved"
        ],
        "learning_claim_unlock_review_revocation_status": learning_guard[
            "learning_claim_unlock_review_revocation_status"
        ],
        "learning_claim_evidence_bundle_status": learning_guard[
            "learning_claim_evidence_bundle_status"
        ],
        "claim_wording_allowed": learning_guard["claim_wording_allowed"],
        "claim_wording_policy_status": learning_guard["claim_wording_policy_status"],
        "confirmed_wording_allowed": learning_guard["confirmed_wording_allowed"],
        "confirmed_wording_policy_status": learning_guard[
            "confirmed_wording_policy_status"
        ],
        "self_improvement_claim_model": learning_guard[
            "self_improvement_claim_model"
        ],
        "same_eval_reason_coverage_status": learning_guard[
            "same_eval_reason_coverage_status"
        ],
        "strict_secondary_improvement_coverage_status": learning_guard[
            "strict_secondary_improvement_coverage_status"
        ],
        "behavior_delta_digest_coverage_status": learning_guard[
            "behavior_delta_digest_coverage_status"
        ],
        "placeholder_audit_status": learning_guard["placeholder_audit_status"],
    }


def _dashboard_budget_signals(reports: Any, signals: Any) -> dict[str, Any]:
    return {
        "release_smoke_boundedness": _release_smoke_boundedness_signal(
            reports.closeout
        ),
        "fixed_point_finalizer_cost": signals.finalizer_duration,
    }


def _render_dashboard_report(inputs: DashboardRenderInputs) -> dict[str, Any]:
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.generated_at,
            artifact_kind="release_evidence_dashboard",
            producer=PRODUCER,
            source_command="python -m ops.scripts.release_evidence_dashboard --vault . --out ops/reports/release-evidence-dashboard.json",
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=RELEASE_EVIDENCE_DASHBOARD_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/release_evidence_dashboard.py",
                "ops/scripts/release/release_evidence_dashboard_render_runtime.py",
                "ops/scripts/release/advisory_lifecycle_runtime.py",
                "ops/scripts/release/release_closeout_fixed_point.py",
                "ops/scripts/release/release_closeout_fixed_point_cost_trend.py",
                "ops/scripts/release/release_closeout_summary.py",
                "ops/scripts/core/artifact_freshness_runtime.py",
                "ops/scripts/learning/learning_delta_scoreboard.py",
            ],
            file_inputs={
                "release_closeout_summary": CLOSEOUT_PATH,
                "release_closeout_fixed_point": FIXED_POINT_PATH,
                "release_closeout_fixed_point_cost_trend": FIXED_POINT_COST_TREND_PATH,
                "learning_readiness_signoff_revalidation": SIGNOFF_REVALIDATION_PATH,
                "artifact_freshness": ARTIFACT_FRESHNESS_PATH,
                "learning_delta_scoreboard": LEARNING_DELTA_SCOREBOARD_PATH,
            },
            text_inputs={
                "current_source_tree_fingerprint": inputs.current_fingerprint
            },
        ),
        "vault": report_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "status": inputs.status_counts.status,
        "source_tree_fingerprint_current": inputs.current_fingerprint,
        "inputs": _dashboard_inputs_payload(inputs.reports, inputs.signals),
        "budget_signals": _dashboard_budget_signals(inputs.reports, inputs.signals),
        "confirmed_evidence_summary": inputs.signals.learning_guard[
            "confirmed_evidence_summary"
        ],
        "accepted_risk_delta": _accepted_risk_delta_payload(inputs.reports.closeout),
        "summary": _dashboard_summary_payload(
            inputs.gates,
            inputs.status_counts,
            inputs.signals.learning_guard,
        ),
        "gates": inputs.gates,
    }
