from __future__ import annotations

import pytest

from ops.scripts.mechanism.mutation_proposal_promotion_runtime import (
    empty_queue_blockers,
    report_status,
    reported_blocked_proposal_count,
    source_evidence_gaps,
)

pytestmark = pytest.mark.public


def test_source_evidence_gaps_dedupes_mechanism_review_and_metric_gaps() -> None:
    report = {
        "summary": {"candidates_emitted": 0},
        "diagnostics": {
            "session_calibration": {"status": "no_session_context"},
            "outcome_metrics_calibration": {
                "status": "missing",
                "evidence_gaps": ["missing outcome metrics", "missing outcome metrics"],
            },
        },
    }

    assert source_evidence_gaps(report, []) == [
        "mechanism review emitted zero candidates",
        "session_calibration.status=no_session_context",
        "outcome_metrics_calibration.status=missing",
        "outcome_metrics: missing outcome metrics",
    ]


def test_empty_queue_blockers_prefers_specific_blockers_over_generic_fallback() -> None:
    blockers = empty_queue_blockers(
        mutation_enabled=True,
        mechanism_review_report={
            "diagnostics": {
                "candidate_blockers": [
                    {
                        "blocker_type": "policy",
                        "reason": "insufficient_signal",
                        "detail": "candidate held for more evidence",
                        "candidate_type": "runtime",
                        "primary_targets": ["ops/scripts/example.py"],
                    }
                ]
            }
        },
        available_proposals=[],
        proposals=[],
        skipped_candidates=[{"reason": "failure_mode_not_allowed", "candidate_id": "c-1"}],
        evidence_gaps=["proposal queue is empty after applying current mutation_proposal filters"],
    )

    assert [blocker["reason"] for blocker in blockers] == [
        "insufficient_signal",
        "failure_mode_not_allowed",
    ]
    assert blockers[0]["primary_targets"] == ["ops/scripts/example.py"]


def test_empty_queue_blockers_classifies_evidence_gap_when_no_specific_blocker() -> None:
    assert empty_queue_blockers(
        mutation_enabled=True,
        mechanism_review_report={},
        available_proposals=[],
        proposals=[],
        skipped_candidates=[],
        evidence_gaps=["outcome_metrics: missing report"],
    ) == [
        {
            "blocker_type": "outcome",
            "reason": "evidence_gap",
            "detail": "outcome_metrics: missing report",
            "source": "evidence_gaps",
        }
    ]


def test_empty_queue_blockers_names_recent_log_overlap_only_empty_selection() -> None:
    blockers = empty_queue_blockers(
        mutation_enabled=True,
        mechanism_review_report={},
        available_proposals=[{"proposal_id": "p-1", "blocked_by": ["recent_log_overlap"]}],
        proposals=[],
        skipped_candidates=[],
        evidence_gaps=[],
    )

    assert blockers[0]["reason"] == "recent_log_overlap_queue_blocked"
    assert blockers[0]["source"] == "queue_selection"
    assert reported_blocked_proposal_count([], blockers) == 1


def test_report_status_and_blocked_count_are_pure_gate_rules() -> None:
    assert report_status(enabled=False, proposals=[{"blocked_by": []}]) == "attention"
    assert report_status(enabled=True, proposals=[]) == "attention"
    assert report_status(enabled=True, proposals=[{"blocked_by": ["recent_log_overlap"]}]) == "attention"
    assert report_status(
        enabled=True,
        proposals=[{"blocked_by": ["recent_log_overlap"]}, {"blocked_by": []}],
    ) == "pass"
    assert report_status(enabled=True, proposals=[{"blocked_by": []}]) == "pass"

    assert reported_blocked_proposal_count(
        [{"blocked_by": []}, {"blocked_by": ["recent_log_overlap"]}],
        [{"reason": "fallback"}],
    ) == 1
    assert reported_blocked_proposal_count([], [{"reason": "fallback"}]) == 1


def test_report_status_requires_explicit_unblocked_proposal_shape() -> None:
    malformed_queue = [{"proposal_id": "missing-blocked-by"}]

    assert report_status(enabled=True, proposals=malformed_queue) == "attention"
    assert reported_blocked_proposal_count(malformed_queue, []) == 1
