from __future__ import annotations

from ops.scripts.learning_claim_unlock_review import (
    AutoPolicyThresholds,
    _auto_policy_metric_predicates,
    _auto_policy_readiness_predicates,
    _auto_policy_thresholds,
    _claim_level_for_decision,
    _required_followup_for_unlock,
    _unlock_review_decision,
    _unlock_review_items,
)


def _machine_claimable_readiness() -> dict:
    return {
        "can_execute_trial": True,
        "can_promote_result": True,
        "learning_readiness": {
            "status": "learning_likely",
            "likely_to_learn": True,
            "metrics": {
                "same_eval_run_count": 2,
                "same_eval_reason_code_coverage_ratio": 1.0,
                "strict_secondary_improvement_coverage_ratio": 1.0,
                "behavior_delta_digest_coverage_ratio": 1.0,
                "rework_count": 0,
                "defect_escape_pair_count": 0,
            },
        },
        "queue": {
            "ready": True,
            "runnable_proposal_count": 1,
        },
    }


def test_auto_policy_thresholds_normalize_invalid_policy_values() -> None:
    thresholds = _auto_policy_thresholds(
        {
            "min_same_eval_run_count": "3",
            "min_coverage_ratio": "not-a-float",
            "max_rework_count": None,
            "max_defect_escape_pair_count": "2",
            "min_runnable_proposal_count": "4",
        }
    )

    assert thresholds == AutoPolicyThresholds(
        min_same_eval_runs=3,
        min_coverage=1.0,
        max_rework_count=0,
        max_defect_escape_pair_count=2,
        min_runnable_proposal_count=4,
    )


def test_auto_policy_predicates_keep_readiness_and_metric_failures_distinct() -> None:
    readiness = _machine_claimable_readiness()
    readiness["can_promote_result"] = False
    readiness["learning_readiness"]["metrics"]["same_eval_run_count"] = 1
    bundle_validation = {
        "bundle_status": "active",
        "bundle_fingerprint_match_status": "match",
        "revocation_status": "active",
    }
    thresholds = AutoPolicyThresholds(
        min_same_eval_runs=2,
        min_coverage=1.0,
        max_rework_count=0,
        max_defect_escape_pair_count=0,
        min_runnable_proposal_count=1,
    )

    readiness_predicates = {
        item["id"]: item
        for item in _auto_policy_readiness_predicates(
            readiness=readiness,
            bundle_validation=bundle_validation,
            evidence_bundle_path="ops/reports/learning-claim-evidence-bundle.json",
            blocking_signal_ids=[],
            blocking_blocker_ids=[],
            thresholds=thresholds,
        )
    }
    metric_predicates = {
        item["id"]: item
        for item in _auto_policy_metric_predicates(
            readiness=readiness,
            thresholds=thresholds,
        )
    }

    assert readiness_predicates["auto_improve_can_promote_result"]["status"] == "fail"
    assert readiness_predicates["learning_readiness_no_blockers"]["status"] == "pass"
    assert metric_predicates["same_eval_run_count_minimum"]["status"] == "fail"
    assert metric_predicates["behavior_delta_digest_coverage_full"]["status"] == "pass"


def test_claim_level_uses_confirmed_claim_before_bounded_claim() -> None:
    assert (
        _claim_level_for_decision(
            "auto_approved",
            {"confirmed_learning_improvement_allowed": True},
        )
        == "confirmed_learning_improvement"
    )
    assert (
        _claim_level_for_decision(
            "auto_approved",
            {"confirmed_learning_improvement_allowed": False},
        )
        == "bounded_learning_likely"
    )
    assert (
        _claim_level_for_decision(
            "requires_human",
            {"confirmed_learning_improvement_allowed": False},
        )
        == "none"
    )


def test_unlock_review_decision_prefers_machine_policy_without_operator_review() -> None:
    decision = _unlock_review_decision(
        machine_policy={"decision": "auto_approved"},
        approved_by="",
        reviewed_at="",
        blocking_signal_ids=[],
        blocking_blocker_ids=[],
    )

    assert decision.approved
    assert decision.review_status == "auto_approved"
    assert decision.approval_mode == "machine_policy"
    assert decision.reviewed_surface_status == "pass"
    assert _required_followup_for_unlock(decision.approved) == []


def test_unlock_review_decision_blocks_operator_approval_when_readiness_has_blockers() -> None:
    decision = _unlock_review_decision(
        machine_policy={"decision": "requires_human"},
        approved_by=" operator ",
        reviewed_at=" 2026-05-14T00:00:00Z ",
        blocking_signal_ids=["same_eval_missing"],
        blocking_blocker_ids=["release_blocker"],
    )
    review_items = {
        item["id"]: item
        for item in _unlock_review_items(
            machine_policy={"decision": "requires_human"},
            decision=decision,
            blocking_signal_ids=["same_eval_missing"],
            blocking_blocker_ids=["release_blocker"],
        )
    }

    assert not decision.approved
    assert decision.review_status == "required"
    assert decision.approval_mode == "none"
    assert decision.approved_by == "operator"
    assert decision.reviewed_at == "2026-05-14T00:00:00Z"
    assert review_items["auto_improve_readiness"]["status"] == "fail"
    assert review_items["auto_improve_readiness"]["requires_human_review"] is False
    assert _required_followup_for_unlock(decision.approved)
