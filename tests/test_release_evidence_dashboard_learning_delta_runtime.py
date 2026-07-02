from __future__ import annotations

import pytest

from ops.scripts.release.release_evidence_dashboard_learning_delta_runtime import (
    learning_delta_guard_gate,
    learning_delta_guard_summary,
)
from ops.scripts.release.release_evidence_dashboard_render_runtime import (
    LEARNING_DELTA_SCOREBOARD_PATH,
)

pytestmark = pytest.mark.runtime_hotspot_smoke


def _scoreboard_payload() -> dict:
    return {
        "status": "pass",
        "summary": {
            "claims_learning_improved": False,
            "learning_claim_allowed": False,
            "learning_likely": False,
            "bounded_learning_claim_allowed": False,
            "confirmed_learning_improvement_allowed": False,
            "confirmed_learning_improvement_status": "not_ready",
            "confirmed_blocking_predicate_ids": [],
            "claim_level": "none",
            "claim_scope": "",
            "learning_claim_unlock_review_status": "not_ready",
            "learning_claim_unlock_review_approved": False,
            "learning_claim_unlock_review_revocation_status": "not_evaluated",
            "learning_claim_evidence_bundle_status": "not_evaluated",
            "telemetry_coverage_ratio": 0.75,
            "same_eval_run_count": 4,
            "same_eval_reason_coverage_ratio": 0.0,
            "strict_secondary_improvement_coverage_ratio": 0.0,
            "behavior_delta_digest_coverage_ratio": 0.0,
            "placeholder_count": 0,
        },
        "learning_claim_guard": {
            "status": "pass",
            "reason": "learning claims are not being made in this release snapshot",
        },
        "learning_claim_unlock_review": {
            "status": "not_ready",
            "approved": False,
            "claim_level": "none",
            "claim_scope": "",
            "bounded_learning_claim_allowed": False,
            "confirmed_learning_improvement_allowed": False,
            "confirmed_learning_improvement_status": "not_ready",
            "confirmed_blocking_predicate_ids": [],
            "confirmed_predicate_results": [],
            "bundle_status": "not_evaluated",
            "revocation_status": "not_evaluated",
            "source_path": "",
        },
        "external_report_placeholder_audit": {
            "status": "pass",
            "placeholder_count": 0,
            "placeholders": [],
        },
    }


def test_learning_delta_guard_summary_and_gate_pass_when_no_claim_is_made() -> None:
    summary = learning_delta_guard_summary(_scoreboard_payload(), "ok")
    gate = learning_delta_guard_gate(summary)

    assert summary["path"] == LEARNING_DELTA_SCOREBOARD_PATH
    assert summary["status"] == "pass"
    assert summary["improvement_claim_status"] == "not_ready"
    assert summary["same_eval_reason_coverage_status"] == "none"
    assert summary["learning_claim_evidence_bundle_status"] == "not_evaluated"
    assert gate["checked_in_state"] == "pass"
    assert gate["live_rerun_state"]["status"] == "pass"
    assert gate["required_evidence"] == []


def test_learning_delta_guard_gate_fails_with_confirmed_blocker() -> None:
    payload = _scoreboard_payload()
    payload["summary"].update(
        {
            "claims_learning_improved": True,
            "learning_claim_unlock_review_status": "required",
            "confirmed_blocking_predicate_ids": [
                "repeated_same_family_evidence"
            ],
        }
    )
    payload["learning_claim_guard"].update(
        {
            "status": "blocked",
            "reason": "same-eval reason and digest coverage are incomplete",
        }
    )
    payload["learning_claim_unlock_review"].update(
        {
            "status": "required",
            "source_path": "ops/reports/learning-claim-unlock-review.json",
            "confirmed_blocking_predicate_ids": [
                "repeated_same_family_evidence"
            ],
            "confirmed_predicate_results": [
                {
                    "id": "repeated_same_family_evidence",
                    "status": "fail",
                    "source_path": "ops/reports/learning-confirmed-evidence-cohort.json",
                    "summary": "Confirmed learning improvement requires repeated same-family evidence.",
                }
            ],
        }
    )

    summary = learning_delta_guard_summary(payload, "ok")
    gate = learning_delta_guard_gate(summary)

    assert summary["confirmed_blocking_predicate_ids"] == [
        "repeated_same_family_evidence"
    ]
    assert summary["learning_claim_blocker_status"] == "blocked"
    assert gate["checked_in_state"] == "fail"
    assert "same-eval reason" in gate["live_rerun_state"]["reason"]
    assert "repeated_same_family_evidence=fail" in gate["claims"][2]["claim"]


def test_learning_delta_guard_gate_attention_for_missing_unlock_review_only() -> None:
    payload = _scoreboard_payload()
    payload["summary"].update(
        {
            "claims_learning_improved": True,
            "learning_claim_allowed": False,
            "learning_claim_unlock_review_status": "required",
            "telemetry_coverage_ratio": 1.0,
            "telemetry_coverage_status": "full",
            "same_eval_reason_coverage_ratio": 1.0,
            "same_eval_reason_coverage_status": "full",
            "strict_secondary_improvement_coverage_ratio": 1.0,
            "strict_secondary_improvement_coverage_status": "full",
            "behavior_delta_digest_coverage_ratio": 1.0,
            "behavior_delta_digest_coverage_status": "full",
        }
    )
    payload["learning_claim_guard"].update(
        {
            "status": "blocked",
            "reason": "learning claim unlock review artifact is required after full evidence coverage",
        }
    )
    payload["learning_claim_unlock_review"].update(
        {
            "status": "required",
            "source_path": "ops/reports/learning-claim-unlock-review.json",
        }
    )

    summary = learning_delta_guard_summary(payload, "ok")
    gate = learning_delta_guard_gate(summary)

    assert gate["checked_in_state"] == "attention"
    assert gate["live_rerun_state"]["status"] == "attention"
    assert "source release evidence may proceed" in gate["next_action"]


def test_missing_learning_delta_scoreboard_fails_with_diagnostic_provenance() -> None:
    summary = learning_delta_guard_summary({}, "missing")
    gate = learning_delta_guard_gate(summary)

    assert summary["status"] == "unknown"
    assert summary["confirmed_evidence_summary"]["confirmed_evidence_status"] == "not_ready"
    assert gate["checked_in_state"] == "fail"
    assert gate["claims"][0]["provenance_label"] == "diagnostic_workspace_only"
