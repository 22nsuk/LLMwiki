from __future__ import annotations

from ops.scripts.core.learning_claim_state_runtime import (
    confirmed_blocking_predicate_ids,
    confirmed_evidence_summary,
    confirmed_predicate_results,
    confirmed_wording_allowed,
    evidence_cohort_status,
    improvement_claim_status,
    learning_claim_bundle_status,
)


def test_confirmed_predicates_and_blockers_are_normalized() -> None:
    predicates = confirmed_predicate_results(
        {
            "confirmed_predicate_results": [
                {"id": "same_eval", "status": "pass"},
                {"id": "coverage", "status": "fail"},
                "ignored",
            ]
        }
    )

    assert predicates == [
        {"id": "same_eval", "status": "pass"},
        {"id": "coverage", "status": "fail"},
    ]
    assert confirmed_blocking_predicate_ids(predicates) == ["coverage"]
    assert confirmed_blocking_predicate_ids(
        predicates,
        summary={"confirmed_blocking_predicate_ids": ["explicit"]},
    ) == ["explicit"]


def test_confirmed_evidence_summary_preserves_legacy_shape() -> None:
    summary = confirmed_evidence_summary(
        {
            "confirmed_evidence_status": "auto_confirmed",
            "valid_run_count": 2,
            "selected_valid_run_ids": ["run-1", ""],
        },
        blocking_predicate_ids=["coverage"],
    )

    assert summary["evidence_cohort_status"] == "auto_confirmed"
    assert summary["selected_valid_run_ids"] == ["run-1"]
    assert summary["blocking_predicate_ids"] == ["coverage"]


def test_learning_status_helpers_use_fallbacks() -> None:
    confirmed = {"evidence_cohort_status": "auto_confirmed"}

    assert improvement_claim_status({}) == "not_ready"
    assert evidence_cohort_status({}, confirmed) == "auto_confirmed"
    assert learning_claim_bundle_status({}) == "not_evaluated"


def test_confirmed_wording_allowed_requires_confirmed_alignment() -> None:
    assert confirmed_wording_allowed(
        summary={"confirmed_learning_improvement_allowed": True},
        claim_level="confirmed_learning_improvement",
        confirmed_status="auto_confirmed",
        evidence_cohort_status="auto_confirmed",
        bundle_status="active",
        blocking_predicate_ids=[],
    )
    assert not confirmed_wording_allowed(
        summary={"confirmed_learning_improvement_allowed": True},
        claim_level="confirmed_learning_improvement",
        confirmed_status="auto_confirmed",
        evidence_cohort_status="auto_confirmed",
        bundle_status="active",
        blocking_predicate_ids=["coverage"],
    )
