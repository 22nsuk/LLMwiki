from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given

from ops.scripts.core.release_currentness_state_runtime import (
    CURRENTNESS_CLASSIFICATION_ARTIFACT_CURRENT_BUT_HEAD_STALE,
    CURRENTNESS_CLASSIFICATION_CURRENT,
    CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_CURRENT_CHECK_FAILED,
    CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_REUSABLE_WITHOUT_HEAD_ALIGNMENT,
    CURRENTNESS_CLASSIFICATION_REASON_HEAD_ALIGNED_CURRENT,
    CURRENTNESS_CLASSIFICATION_REASON_RELEASE_AUTHORITATIVE_WITHOUT_HEAD_ALIGNMENT,
    CURRENTNESS_CLASSIFICATION_REASON_SOURCE_REVISION_MISMATCH,
    CURRENTNESS_CLASSIFICATION_REASON_SOURCE_TREE_FINGERPRINT_MISMATCH,
    CURRENTNESS_CLASSIFICATION_RELEASE_AUTHORITATIVE_CURRENT,
    CURRENTNESS_CLASSIFICATION_REUSABLE_CURRENT,
    CURRENTNESS_DOMAIN_MODE_RELEASE_AUTHORITATIVE,
    CURRENTNESS_DOMAIN_MODE_REUSABLE,
    components_match_current_source_tree,
    currentness_classification_record,
    currentness_field,
    currentness_relation_is_valid,
    head_alignment,
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


@given(
    source_revision_matches_head=st.booleans(),
    source_tree_fingerprint_matches=st.booleans(),
    domain_current_check_passes=st.booleans(),
    self_declared_status=st.sampled_from(["current", "stale", "unknown", "pass"]),
)
def test_property_5_classification_determined_by_head_alignment(
    source_revision_matches_head: bool,
    source_tree_fingerprint_matches: bool,
    domain_current_check_passes: bool,
    self_declared_status: str,
) -> None:
    """Feature: release-evidence-sync, Property 5: classification determined by HEAD alignment"""
    record = currentness_classification_record(
        report_path="ops/reports/sample.json",
        self_declared_status=self_declared_status,
        source_revision="head" if source_revision_matches_head else "old",
        head_revision="head",
        source_tree_fingerprint="fingerprint" if source_tree_fingerprint_matches else "old-fingerprint",
        current_source_tree_fingerprint="fingerprint",
        domain_current_check_passes=domain_current_check_passes,
        domain_mode=CURRENTNESS_DOMAIN_MODE_REUSABLE,
    )

    assert record["source_revision_matches_head"] is source_revision_matches_head
    assert record["source_tree_fingerprint_matches"] is source_tree_fingerprint_matches
    assert record["domain_current_check_passes"] is domain_current_check_passes
    assert currentness_relation_is_valid(
        operator_facing_classification=record["operator_facing_classification"],
        classification_reason=record["classification_reason"],
    )
    if (
        source_revision_matches_head
        and source_tree_fingerprint_matches
        and domain_current_check_passes
    ):
        assert record["operator_facing_classification"] == CURRENTNESS_CLASSIFICATION_CURRENT
        assert record["classification_reason"] == CURRENTNESS_CLASSIFICATION_REASON_HEAD_ALIGNED_CURRENT
    elif domain_current_check_passes:
        assert record["operator_facing_classification"] == CURRENTNESS_CLASSIFICATION_REUSABLE_CURRENT
        assert (
            record["classification_reason"]
            == CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_REUSABLE_WITHOUT_HEAD_ALIGNMENT
        )
    else:
        assert (
            record["operator_facing_classification"]
            == CURRENTNESS_CLASSIFICATION_ARTIFACT_CURRENT_BUT_HEAD_STALE
        )
        assert record["classification_reason"] in {
            CURRENTNESS_CLASSIFICATION_REASON_SOURCE_TREE_FINGERPRINT_MISMATCH,
            CURRENTNESS_CLASSIFICATION_REASON_SOURCE_REVISION_MISMATCH,
            CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_CURRENT_CHECK_FAILED,
        }


def test_reason_priority_prefers_source_tree_over_revision_over_domain() -> None:
    record = currentness_classification_record(
        report_path="ops/reports/sample.json",
        self_declared_status="current",
        source_revision="old",
        head_revision="head",
        source_tree_fingerprint="old-fingerprint",
        current_source_tree_fingerprint="fingerprint",
        domain_current_check_passes=False,
        domain_mode=CURRENTNESS_DOMAIN_MODE_REUSABLE,
    )

    assert record["classification_reason"] == CURRENTNESS_CLASSIFICATION_REASON_SOURCE_TREE_FINGERPRINT_MISMATCH


def test_reason_priority_prefers_source_revision_over_domain_when_tree_matches() -> None:
    record = currentness_classification_record(
        report_path="ops/reports/sample.json",
        self_declared_status="current",
        source_revision="old",
        head_revision="head",
        source_tree_fingerprint="fingerprint",
        current_source_tree_fingerprint="fingerprint",
        domain_current_check_passes=False,
        domain_mode=CURRENTNESS_DOMAIN_MODE_REUSABLE,
    )

    assert record["classification_reason"] == CURRENTNESS_CLASSIFICATION_REASON_SOURCE_REVISION_MISMATCH


def test_domain_specific_currentness_classes_use_fixed_reason_relation() -> None:
    reusable = currentness_classification_record(
        report_path="ops/reports/sample.json",
        self_declared_status="current",
        source_revision="old",
        head_revision="head",
        source_tree_fingerprint="fingerprint",
        current_source_tree_fingerprint="fingerprint",
        domain_current_check_passes=True,
        domain_mode=CURRENTNESS_DOMAIN_MODE_REUSABLE,
    )
    authoritative = currentness_classification_record(
        report_path="ops/reports/sample.json",
        self_declared_status="current",
        source_revision="old",
        head_revision="head",
        source_tree_fingerprint="fingerprint",
        current_source_tree_fingerprint="fingerprint",
        domain_current_check_passes=True,
        domain_mode=CURRENTNESS_DOMAIN_MODE_RELEASE_AUTHORITATIVE,
    )

    assert reusable["operator_facing_classification"] == CURRENTNESS_CLASSIFICATION_REUSABLE_CURRENT
    assert reusable["classification_reason"] == CURRENTNESS_CLASSIFICATION_REASON_DOMAIN_REUSABLE_WITHOUT_HEAD_ALIGNMENT
    assert authoritative["operator_facing_classification"] == CURRENTNESS_CLASSIFICATION_RELEASE_AUTHORITATIVE_CURRENT
    assert (
        authoritative["classification_reason"]
        == CURRENTNESS_CLASSIFICATION_REASON_RELEASE_AUTHORITATIVE_WITHOUT_HEAD_ALIGNMENT
    )


def test_head_alignment_reports_all_three_predicates() -> None:
    alignment = head_alignment(
        source_revision="head",
        head_revision="head",
        source_tree_fingerprint="fingerprint",
        current_source_tree_fingerprint="fingerprint",
        domain_current_check_passes=True,
    )

    assert alignment == {
        "source_revision_matches_head": True,
        "source_tree_fingerprint_matches": True,
        "domain_current_check_passes": True,
    }
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
