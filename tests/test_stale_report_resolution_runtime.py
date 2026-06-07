from __future__ import annotations

import string
import tempfile
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given

from ops.scripts.core.stale_report_resolution_runtime import (
    PRIORITY_STALE_CANONICAL_REPORT_PATHS,
    RESOLUTION_STATUS_FAIL,
    RESOLUTION_STATUS_PASS,
    SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL,
    SEALED_SIDECAR_DECISION_REGENERATE,
    SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
    SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
    SEALED_SIDECAR_STATUS_INCOMPLETE,
    SEALED_SIDECAR_STATUS_PASS,
    STALE_CANONICAL_REPORT_PATHS,
    STALE_REPORT_DECISION_REGENERATE,
    STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
    remove_stale_report_from_canonical_set,
    sealed_sidecar_cleanup_record,
    sealed_sidecar_cleanup_retry_summary,
    sealed_sidecar_entry_record,
    stale_report_resolution_record,
    validate_sealed_sidecar_cleanup,
    validate_stale_report_resolutions,
)

SAFE_NAME = st.text(alphabet=string.ascii_lowercase + string.digits + "-", min_size=1, max_size=16)


@st.composite
def valid_stale_resolution_records(draw: st.DrawFn) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for report_path in STALE_CANONICAL_REPORT_PATHS:
        decision = draw(
            st.sampled_from(
                [
                    STALE_REPORT_DECISION_REGENERATE,
                    STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
                ]
            )
        )
        if decision == STALE_REPORT_DECISION_REGENERATE:
            records.append(
                stale_report_resolution_record(
                    report_path,
                    decision=decision,
                    post_state_head_aligned=True,
                )
            )
        else:
            preserved = draw(st.booleans())
            records.append(
                stale_report_resolution_record(
                    report_path,
                    decision=decision,
                    post_state_head_aligned=False,
                    preserved_non_canonical=preserved,
                    preservation_reason="kept for audit trail" if preserved else "",
                )
            )
    return records


@given(records=valid_stale_resolution_records())
def test_property_13_stale_resolver_bookkeeping_and_post_state_alignment(
    records: list[dict[str, object]],
) -> None:
    """Feature: release-evidence-sync, Property 13: stale resolver bookkeeping and post-state alignment"""
    summary = validate_stale_report_resolutions(records)

    assert summary["status"] == RESOLUTION_STATUS_PASS
    assert summary["complete"] is True
    assert summary["missing_reports"] == []
    assert summary["duplicate_reports"] == []
    assert summary["unexpected_reports"] == []
    assert summary["all_retained_reports_head_aligned"] is True
    assert summary["priority_reports_resolved"] is True
    assert summary["priority_unresolved_reports"] == []
    assert summary["errors"] == []
    assert set(summary["required_reports"]) == set(STALE_CANONICAL_REPORT_PATHS)
    for report_path in PRIORITY_STALE_CANONICAL_REPORT_PATHS:
        assert (
            report_path in summary["canonical_retained_reports"]
            or report_path in summary["excluded_reports"]
        )


def test_stale_report_resolution_requires_exactly_one_decision_per_stale_report() -> None:
    records = [
        stale_report_resolution_record(
            STALE_CANONICAL_REPORT_PATHS[0],
            decision=STALE_REPORT_DECISION_REGENERATE,
            post_state_head_aligned=True,
        ),
        stale_report_resolution_record(
            STALE_CANONICAL_REPORT_PATHS[0],
            decision=STALE_REPORT_DECISION_REGENERATE,
            post_state_head_aligned=True,
        ),
    ]

    summary = validate_stale_report_resolutions(records)

    assert summary["status"] == RESOLUTION_STATUS_FAIL
    assert STALE_CANONICAL_REPORT_PATHS[0] in summary["duplicate_reports"]
    assert set(summary["missing_reports"]) == set(STALE_CANONICAL_REPORT_PATHS[1:])


def test_stale_report_resolution_rejects_priority_report_retained_without_head_alignment() -> None:
    records = [
        stale_report_resolution_record(
            report_path,
            decision=STALE_REPORT_DECISION_REGENERATE,
            post_state_head_aligned=report_path != PRIORITY_STALE_CANONICAL_REPORT_PATHS[0],
        )
        for report_path in STALE_CANONICAL_REPORT_PATHS
    ]

    summary = validate_stale_report_resolutions(records)

    assert summary["status"] == RESOLUTION_STATUS_FAIL
    assert PRIORITY_STALE_CANONICAL_REPORT_PATHS[0] in summary["retained_not_head_aligned_reports"]
    assert PRIORITY_STALE_CANONICAL_REPORT_PATHS[0] in summary["priority_unresolved_reports"]


def test_stale_report_resolution_requires_reason_for_preserved_non_canonical_report() -> None:
    records = [
        stale_report_resolution_record(
            report_path,
            decision=STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
            post_state_head_aligned=False,
            preserved_non_canonical=True,
            preservation_reason="",
        )
        for report_path in STALE_CANONICAL_REPORT_PATHS
    ]

    summary = validate_stale_report_resolutions(records)

    assert summary["status"] == RESOLUTION_STATUS_FAIL
    assert set(summary["preserved_without_reason_reports"]) == set(STALE_CANONICAL_REPORT_PATHS)


def test_stale_report_resolution_requires_marker_for_excluded_report() -> None:
    records = [
        {
            **stale_report_resolution_record(
                report_path,
                decision=STALE_REPORT_DECISION_REMOVE_FROM_CANONICAL_SET,
                post_state_head_aligned=False,
            ),
            "non_canonical_marker": "",
        }
        for report_path in STALE_CANONICAL_REPORT_PATHS
    ]

    summary = validate_stale_report_resolutions(records)

    assert summary["status"] == RESOLUTION_STATUS_FAIL
    assert set(summary["excluded_without_marker_reports"]) == set(STALE_CANONICAL_REPORT_PATHS)


@given(name=SAFE_NAME)
def test_remove_stale_report_from_canonical_set_deletes_source_when_not_preserved(name: str) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        source = vault / "ops" / "reports" / f"{name}.json"
        source.parent.mkdir(parents=True)
        source.write_text('{"status":"stale"}\n', encoding="utf-8")

        result = remove_stale_report_from_canonical_set(
            vault,
            report_path=f"ops/reports/{name}.json",
        )

        assert result["deleted"] is True
        assert result["source_exists_after_delete"] is False
        assert not source.exists()
        assert result["resolution"]["excluded_from_canonical"] is True
        assert result["resolution"]["preserved_non_canonical"] is False


def test_remove_stale_report_from_canonical_set_preserves_only_with_reason() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        source = vault / "ops" / "reports" / "sample.json"
        destination = vault / "ops" / "reports" / "observational" / "sample.json"
        source.parent.mkdir(parents=True)
        source.write_text('{"status":"stale"}\n', encoding="utf-8")

        result = remove_stale_report_from_canonical_set(
            vault,
            report_path="ops/reports/sample.json",
            destination_path="ops/reports/observational/sample.json",
            preservation_reason="historical audit evidence",
        )

        assert not source.exists()
        assert destination.exists()
        assert result["resolution"]["preserved_non_canonical"] is True
        assert result["resolution"]["preservation_reason"] == "historical audit evidence"


def test_sealed_sidecar_regenerate_branch_requires_head_aligned_active_result() -> None:
    cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REGENERATE,
        post_state_head_aligned=True,
    )
    active_sidecars = [
        sealed_sidecar_entry_record(
            SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
            head_aligned_current=True,
        ),
        sealed_sidecar_entry_record(
            "build/release/release-sealed-run-manifest.json",
            head_aligned_current=True,
        ),
    ]

    summary = validate_sealed_sidecar_cleanup(cleanup, active_sidecars=active_sidecars)

    assert summary["status"] == SEALED_SIDECAR_STATUS_PASS
    assert summary["complete"] is True
    assert summary["retry_required"] is False


def test_sealed_sidecar_remove_branch_excludes_target_from_active_set() -> None:
    cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
    )
    active_sidecars = [
        sealed_sidecar_entry_record(
            SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
            head_aligned_current=False,
            active=False,
        ),
        sealed_sidecar_entry_record(
            "build/release/release-sealed-run-manifest.json",
            head_aligned_current=True,
        ),
    ]

    summary = validate_sealed_sidecar_cleanup(cleanup, active_sidecars=active_sidecars)

    assert summary["status"] == SEALED_SIDECAR_STATUS_PASS
    assert SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH not in summary["active_authoritative_sidecar_paths"]


def test_sealed_sidecar_preserve_branch_requires_marker_and_reason() -> None:
    cleanup = {
        **sealed_sidecar_cleanup_record(
            decision=SEALED_SIDECAR_DECISION_PRESERVE_NON_CANONICAL,
            preservation_reason="",
        ),
        "non_canonical_marker": "",
    }

    summary = validate_sealed_sidecar_cleanup(cleanup, active_sidecars=[])

    assert summary["status"] == SEALED_SIDECAR_STATUS_INCOMPLETE
    assert {error["code"] for error in summary["errors"]} >= {
        "preserved_sidecar_missing_marker",
        "preserved_sidecar_missing_reason",
    }


def test_sealed_sidecar_cleanup_is_incomplete_when_removed_target_is_still_active() -> None:
    cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
    )
    active_sidecars = [
        sealed_sidecar_entry_record(
            SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
            head_aligned_current=True,
        )
    ]

    summary = validate_sealed_sidecar_cleanup(cleanup, active_sidecars=active_sidecars)

    assert summary["status"] == SEALED_SIDECAR_STATUS_INCOMPLETE
    assert "target_sidecar_still_active" in {error["code"] for error in summary["errors"]}


def test_sealed_sidecar_cleanup_preserves_exact_error_order_and_output_shape() -> None:
    cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
    )
    active_sidecars = [
        sealed_sidecar_entry_record(
            SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
            head_aligned_current=False,
        )
    ]

    summary = validate_sealed_sidecar_cleanup(cleanup, active_sidecars=active_sidecars)

    assert summary == {
        "status": SEALED_SIDECAR_STATUS_INCOMPLETE,
        "complete": False,
        "retry_required": True,
        "sidecar_path": SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
        "decision": SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
        "active_authoritative_sidecar_paths": [
            SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH
        ],
        "stale_active_sidecar_paths": [
            SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH
        ],
        "errors": [
            {
                "report_path": SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
                "code": "active_sidecar_not_head_aligned",
                "message": "active authoritative sealed sidecars must be HEAD_Aligned_Current",
            },
            {
                "report_path": SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
                "code": "target_sidecar_still_active",
                "message": "removed or preserved target sidecar is still active",
            },
        ],
    }


def test_sealed_sidecar_retry_summary_runs_until_active_authority_is_head_aligned() -> None:
    first_cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REGENERATE,
        post_state_head_aligned=True,
    )
    second_cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REGENERATE,
        post_state_head_aligned=True,
    )

    summary = sealed_sidecar_cleanup_retry_summary(
        [
            {
                "cleanup_record": first_cleanup,
                "active_sidecars": [
                    sealed_sidecar_entry_record(
                        SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
                        head_aligned_current=True,
                    ),
                    sealed_sidecar_entry_record(
                        "build/release/release-sealed-run-manifest.json",
                        head_aligned_current=False,
                    ),
                ],
            },
            {
                "cleanup_record": second_cleanup,
                "active_sidecars": [
                    sealed_sidecar_entry_record(
                        SEALED_SIDECAR_POST_SEAL_ATTESTATION_PATH,
                        head_aligned_current=True,
                    ),
                    sealed_sidecar_entry_record(
                        "build/release/release-sealed-run-manifest.json",
                        head_aligned_current=True,
                    ),
                ],
            },
        ]
    )

    assert summary["status"] == SEALED_SIDECAR_STATUS_PASS
    assert summary["attempt_count"] == 2
    assert summary["validations"][0]["status"] == SEALED_SIDECAR_STATUS_INCOMPLETE
    assert summary["validations"][1]["status"] == SEALED_SIDECAR_STATUS_PASS


def test_sealed_sidecar_validation_ignores_non_authoritative_build_release_diagnostics() -> None:
    cleanup = sealed_sidecar_cleanup_record(
        decision=SEALED_SIDECAR_DECISION_REMOVE_FROM_ACTIVE_SET,
    )
    active_sidecars = [
        sealed_sidecar_entry_record(
            "build/release/release-auto-promotion-ready-plan.json",
            head_aligned_current=False,
        )
    ]

    summary = validate_sealed_sidecar_cleanup(cleanup, active_sidecars=active_sidecars)

    assert summary["status"] == SEALED_SIDECAR_STATUS_PASS
