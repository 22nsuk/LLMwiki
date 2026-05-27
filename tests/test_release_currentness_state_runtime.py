from __future__ import annotations

from ops.scripts.core.release_currentness_state_runtime import (
    components_match_current_source_tree,
    currentness_field,
    live_rerun_state,
)


def test_currentness_field_reads_embedded_currentness() -> None:
    payload = {"currentness": {"status": "current", "checked_at": "now"}}

    assert currentness_field(payload, "status") == "current"
    assert currentness_field(payload, "checked_at") == "now"
    assert currentness_field({}, "status") == ""


def test_live_rerun_state_classifies_current_ready_component() -> None:
    component = {
        "source_tree_fingerprint": "abc",
        "currentness_status": "current",
        "ready": True,
    }

    assert live_rerun_state(component, current_fingerprint="abc") == {
        "status": "pass",
        "reason": "checked-in component matches current source tree",
    }


def test_components_match_current_source_tree_requires_loaded_current_cohort() -> None:
    assert components_match_current_source_tree(
        [
            {
                "load_status": "ok",
                "source_tree_fingerprint": "abc",
                "currentness_status": "current",
            }
        ],
        current_source_tree_fingerprint="abc",
    )
    assert not components_match_current_source_tree(
        [
            {
                "load_status": "ok",
                "source_tree_fingerprint": "old",
                "currentness_status": "current",
            }
        ],
        current_source_tree_fingerprint="abc",
    )
