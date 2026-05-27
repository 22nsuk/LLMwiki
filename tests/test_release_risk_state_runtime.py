from __future__ import annotations

from typing import Any

from ops.scripts.core.release_risk_state_runtime import (
    release_blocker_entry,
    release_risk_blocks_clean_lane,
    release_risk_identity,
    release_risk_list,
    release_risk_with_effects,
)


def test_release_risk_identity_can_include_linked_blocker() -> None:
    risk = {
        "source": "release-closeout",
        "code": "needs_review",
        "risk_acceptance": {"linked_blocker_id": "learning_review"},
    }

    assert release_risk_identity(risk) == "release-closeout:needs_review"
    assert (
        release_risk_identity(
            risk,
            include_linked_blocker=True,
            separator="::",
        )
        == "release-closeout::needs_review::learning_review"
    )


def test_release_risk_blocks_clean_lane_honors_learning_signoff_exception() -> None:
    risk = {
        "code": "learning_review_required",
        "risk_acceptance": {
            "acceptance_source": "ops/reports/learning-readiness-signoff.json",
            "accepted_by": "operator",
        },
    }

    assert not release_risk_blocks_clean_lane(
        risk,
        learning_review_blocker_id="learning_review_required",
        learning_signoff_path="ops/reports/learning-readiness-signoff.json",
        policy_risk_accepted_by="release_closeout_policy",
    )


def test_release_risk_list_enriches_payload_items() -> None:
    payload = {"accepted_risks": [{"code": "artifact_attention"}]}

    assert release_risk_list(
        payload,
        "accepted_risks",
        lambda _risk: {"clean_lane_effect": "blocks_clean_lane"},
    ) == [{"code": "artifact_attention", "clean_lane_effect": "blocks_clean_lane"}]
    assert release_risk_with_effects(
        {"code": "x", "clean_lane_effect": "existing"},
        {"clean_lane_effect": "new"},
    ) == {"code": "x", "clean_lane_effect": "existing"}


def test_release_blocker_entry_normalizes_acceptance_and_advisory_fields() -> None:
    def advisory_assessment(_risk: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
        return {
            "advisory_lifecycle_status": "active",
            "generated_at_seen": generated_at,
        }

    entry = release_blocker_entry(
        {
            "source": "release-closeout",
            "source_path": "ops/reports/release-closeout-summary.json",
            "code": "needs_review",
            "severity": "warn",
            "gate_effect": "accepted_risk",
            "message": "Needs review.",
            "required_evidence": ["Rerun release closeout."],
            "risk_acceptance": {
                "risk_owner": "runtime-maintainer",
                "expires_at": "2026-06-01T00:00:00Z",
                "acceptance_source": "policy",
            },
        },
        generated_at="2026-05-27T00:00:00Z",
        advisory_lifecycle_assessment=advisory_assessment,
        clean_lane_effect_default="blocks_clean_lane",
    )

    assert entry["id"] == "release-closeout:needs_review"
    assert entry["clean_lane_effect"] == "blocks_clean_lane"
    assert entry["closure_action"] == "Rerun release closeout."
    assert entry["advisory_lifecycle_status"] == "active"
