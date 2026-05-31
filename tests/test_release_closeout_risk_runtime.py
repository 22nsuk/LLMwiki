from __future__ import annotations

from ops.scripts.gate_effect_vocabulary import GATE_EFFECT_OPERATOR_REVIEW_REQUIRED
from ops.scripts.release.release_closeout_risk_runtime import (
    CLEAN_LANE_BLOCKS,
    LEARNING_SIGNOFF_PATH,
    POLICY_RISK_ACCEPTED_BY,
    accepted_risk_count_by_scope,
    finalize_accepted_risks,
    policy_risk_acceptance,
    release_closeout_issue,
    risk_acceptance_is_active,
    risk_delta,
    taxonomy_coverage_blockers,
)


def _risk(code: str, **extra: object) -> dict[str, object]:
    return {
        "source": "test_source",
        "source_path": "ops/reports/test.json",
        "code": code,
        "message": f"{code} message",
        **extra,
    }


def test_policy_risk_acceptance_uses_metadata_and_fixed_expiry_window() -> None:
    acceptance = policy_risk_acceptance(
        _risk("artifact_freshness_attention"),
        generated_at="2026-04-29T09:00:00Z",
    )

    assert acceptance["accepted_by"] == POLICY_RISK_ACCEPTED_BY
    assert acceptance["accepted_at"] == "2026-04-29T09:00:00Z"
    assert acceptance["expires_at"] == "2026-05-06T09:00:00Z"
    assert acceptance["risk_owner"] == "runtime-maintainer"
    assert risk_acceptance_is_active(
        acceptance,
        generated_at="2026-04-30T09:00:00Z",
    )


def test_finalize_accepted_risks_promotes_missing_policy_acceptance() -> None:
    blockers, accepted = finalize_accepted_risks(
        [_risk("generated_index_archive_advisory")],
        generated_at="2026-04-29T09:00:00Z",
    )

    assert blockers == []
    assert accepted[0]["risk_acceptance"]["accepted_by"] == POLICY_RISK_ACCEPTED_BY


def test_finalize_accepted_risks_turns_expired_acceptance_back_into_blocker() -> None:
    blockers, accepted = finalize_accepted_risks(
        [
            _risk(
                "needs_review",
                risk_acceptance={
                    "accepted_by": "operator@example.test",
                    "expires_at": "2026-04-29T08:59:59Z",
                },
                required_evidence=["original evidence"],
            )
        ],
        generated_at="2026-04-29T09:00:00Z",
    )

    assert accepted == []
    assert blockers[0]["severity"] == "blocker"
    assert blockers[0]["gate_effect"] == GATE_EFFECT_OPERATOR_REVIEW_REQUIRED
    assert "missing or expired" in blockers[0]["message"]
    assert blockers[0]["required_evidence"][-1].startswith("Refresh or replace")


def test_risk_delta_uses_linked_blocker_identity() -> None:
    previous = {
        "generated_at": "2026-04-28T09:00:00Z",
        "accepted_risks": [
            _risk(
                "same_code",
                risk_acceptance={"linked_blocker_id": "old_blocker"},
            )
        ],
    }
    current = [
        _risk(
            "same_code",
            risk_acceptance={"linked_blocker_id": "new_blocker"},
        )
    ]

    delta = risk_delta(previous, current)

    assert delta["status"] == "changed"
    assert delta["added_count"] == 1
    assert delta["removed_count"] == 1
    assert "new_blocker" in delta["added"][0]
    assert "old_blocker" in delta["removed"][0]


def test_accepted_risk_count_by_scope_counts_instances_and_families() -> None:
    counts = accepted_risk_count_by_scope(
        [
            _risk(
                "policy_risk",
                risk_acceptance={"accepted_by": POLICY_RISK_ACCEPTED_BY},
                clean_lane_effect=CLEAN_LANE_BLOCKS,
            ),
            _risk(
                "operator_risk",
                risk_acceptance={"acceptance_source": LEARNING_SIGNOFF_PATH},
            ),
            _risk(
                "test_risk",
                risk_acceptance={"accepted_by": "test_deselection_policy"},
            ),
            _risk("upstream_risk"),
        ]
    )

    assert counts["total"] == 4
    assert counts["families"] == 4
    assert counts["policy"] == 1
    assert counts["operator_signoff"] == 1
    assert counts["test_deselection_policy"] == 1
    assert counts["upstream_report"] == 1
    assert counts["clean_lane_blocking_family_count"] == 1


def test_taxonomy_coverage_blockers_report_unregistered_codes() -> None:
    blockers = taxonomy_coverage_blockers(
        [_risk("unregistered_closeout_code")],
        {"risk_codes": []},
    )

    assert len(blockers) == 1
    assert blockers[0]["code"] == "release_risk_taxonomy_unregistered_code"
    assert "unregistered_closeout_code" in blockers[0]["message"]


def test_release_closeout_issue_canonicalizes_empty_gate_effect() -> None:
    issue = release_closeout_issue(
        source="source",
        source_path="path",
        code="code",
        message="message",
        gate_effect="",
    )

    assert issue["gate_effect"] == "blocks_promotion"
