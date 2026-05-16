from __future__ import annotations

import pytest

from ops.scripts.mechanism.auto_improve_readiness_release_authority_runtime import (
    _release_authority_preflight_promotion_blockers,
    _release_authority_preflight_summary,
    _selected_contract_summary,
)


pytestmark = pytest.mark.public


def test_selected_contract_currentness_has_distinct_blocking_signal() -> None:
    summary = _selected_contract_summary(
        {
            "artifact_kind": "test_execution_summary",
            "status": "pass",
            "currentness": {"status": "stale"},
        }
    )

    assert summary["status"] == "fail"
    assert summary["source_status"] == "currentness_stale"
    assert summary["currentness_status"] == "stale"
    assert summary["signal_ids"] == ["selected_contract_currentness_not_current"]


def test_release_authority_preflight_summary_preserves_clean_required_vocabulary() -> None:
    summary = _release_authority_preflight_summary(
        {
            "artifact_kind": "release_closeout_sealed_rehearsal_check",
            "status": "pass",
            "preflight_status": "sealed_clean_pass",
            "preflight_mode": "clean_required",
            "distribution_binding_status": "pass",
            "authority_preflight_status": "clean",
            "expected_blocked_preflight": False,
            "clean_required_preflight": True,
            "blocking_reason_ids": [],
            "failures": [],
            "failure_details": [],
            "summary": "sealed release evidence clean",
        }
    )

    assert summary["status"] == "pass"
    assert summary["preflight_mode"] == "clean_required"
    assert summary["expected_blocked_preflight"] is False
    assert summary["clean_required_preflight"] is True


def test_release_authority_preflight_blocks_inconsistent_clean_vocabulary() -> None:
    summary = _release_authority_preflight_summary(
        {
            "artifact_kind": "release_closeout_sealed_rehearsal_check",
            "status": "pass",
            "preflight_status": "sealed_clean_pass",
            "preflight_mode": "expected_blocked",
            "distribution_binding_status": "pass",
            "authority_preflight_status": "clean",
            "expected_blocked_preflight": True,
            "clean_required_preflight": False,
            "blocking_reason_ids": [],
            "failures": [],
            "failure_details": [],
            "summary": "inconsistent clean pass vocabulary",
        }
    )

    blockers = _release_authority_preflight_promotion_blockers(summary)

    assert summary["status"] == "fail"
    assert blockers[0]["source_status"] == "fail"
    assert blockers[0]["signal_ids"] == [
        "release_authority_preflight_not_clean_required",
        "release_authority_preflight_expected_blocked",
        "release_authority_preflight_clean_required_missing",
    ]
