from __future__ import annotations

from hypothesis import given
import hypothesis.strategies as st

from ops.scripts.release.external_report_lifecycle_runtime import (
    ACTION_LIFECYCLE_CURRENTLY_VALID,
    ACTION_LIFECYCLE_HISTORICALLY_TRUE,
    ACTION_LIFECYCLE_RESOLVED,
    ACTION_LIFECYCLE_SUPERSEDED,
    ACTION_LIFECYCLES,
    classify_external_report_action_lifecycle,
    external_report_action_lifecycle_record,
    external_report_action_lifecycle_summary,
    external_report_current_canonical_state,
)


@given(
    lifecycle_hint=st.sampled_from(
        [
            "resolved",
            "historical_46_stale",
            "superseded",
            "currently_valid_5_stale",
            "currently_valid_generic",
        ]
    )
)
def test_property_10_external_report_lifecycle_partition_and_active_set_derivation(
    lifecycle_hint: str,
) -> None:
    """Feature: release-evidence-sync, Property 10: external report lifecycle partition and active-set derivation"""
    claim_text_by_hint = {
        "resolved": "implemented runtime evidence is now present",
        "historical_46_stale": "top-level canonical report 46/46 stale",
        "superseded": "superseded by the 2026-05-29 revalidation report",
        "currently_valid_5_stale": "current state is 5 stale / 47 total with priority 3",
        "currently_valid_generic": "current active external report item needs operator action",
    }
    status_by_hint = {
        "resolved": "implemented",
        "historical_46_stale": "planned",
        "superseded": "planned",
        "currently_valid_5_stale": "planned",
        "currently_valid_generic": "requires_release_run_verification",
    }
    item = {
        "action_id": lifecycle_hint,
        "theme": "external report lifecycle",
        "current_status": status_by_hint[lifecycle_hint],
        "claim_text": claim_text_by_hint[lifecycle_hint],
    }

    record = external_report_action_lifecycle_record(item)
    summary = external_report_action_lifecycle_summary([{**item, **record}])

    assert record["lifecycle"] in ACTION_LIFECYCLES
    assert record["is_active"] is (
        record["lifecycle"] == ACTION_LIFECYCLE_CURRENTLY_VALID
    )
    assert set(summary["active_action_ids"]).isdisjoint(summary["archived_action_ids"])
    if lifecycle_hint == "historical_46_stale":
        assert record["lifecycle"] == ACTION_LIFECYCLE_HISTORICALLY_TRUE
        assert record["is_active"] is False
    elif lifecycle_hint == "superseded":
        assert record["lifecycle"] == ACTION_LIFECYCLE_SUPERSEDED
        assert record["is_active"] is False
    elif lifecycle_hint == "resolved":
        assert record["lifecycle"] == ACTION_LIFECYCLE_RESOLVED
        assert record["is_active"] is False
    else:
        assert record["lifecycle"] == ACTION_LIFECYCLE_CURRENTLY_VALID
        assert record["is_active"] is True


def test_current_external_report_state_uses_revalidated_5_of_47_counts() -> None:
    state = external_report_current_canonical_state()

    assert state["stale_report_count"] == 5
    assert state["total_report_count"] == 47
    assert state["priority_stale_report_count"] == 3
    assert "5 stale / 47 total" in state["summary"]


def test_46_of_46_stale_claim_is_historical_not_current() -> None:
    lifecycle = classify_external_report_action_lifecycle(
        {
            "current_status": "planned",
            "claim_text": "The previous report said 46/46 top-level canonical reports were stale.",
        }
    )

    assert lifecycle == ACTION_LIFECYCLE_HISTORICALLY_TRUE
