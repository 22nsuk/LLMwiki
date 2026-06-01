from __future__ import annotations

import string
import tempfile
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given

from ops.scripts.core.report_bucket_runtime import (
    BUCKET_ARCHIVAL_HISTORICAL,
    BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR,
    BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE,
    BUCKET_OBSERVATIONAL_DIAGNOSTIC,
    DOCUMENTATION_STATUS_FAIL,
    DOCUMENTATION_STATUS_PASS,
    REPORT_BUCKETS,
    assign_report_bucket,
    assign_report_buckets,
    classify_report_bucket,
    move_report_delete_first,
    report_bucket_documentation_status,
)

SAFE_NAME = st.text(alphabet=string.ascii_lowercase + string.digits + "-", min_size=1, max_size=20)


@given(
    prefix=st.sampled_from(
        [
            "ops/reports",
            "ops/reports/auto-improve-sessions",
            "ops/reports/archive",
            "build/release",
            "build/release/archive",
            "tmp",
            "external-reports",
            "external-reports/archive",
        ]
    ),
    name=SAFE_NAME,
)
def test_property_8_report_bucket_assignment_is_total_disjoint_partition(prefix: str, name: str) -> None:
    """Feature: release-evidence-sync, Property 8: bucket assignment is a total disjoint partition"""
    assignment = assign_report_bucket(f"{prefix}/{name}.json")

    assert assignment["bucket"] in REPORT_BUCKETS
    assert sum(1 for bucket in REPORT_BUCKETS if assignment["bucket"] == bucket) == 1
    assert assignment["documentation_compliance_status"] == DOCUMENTATION_STATUS_PASS


@given(documentation_status=st.sampled_from([DOCUMENTATION_STATUS_PASS, DOCUMENTATION_STATUS_FAIL]))
def test_documentation_compliance_is_independent_from_bucket_assignment(
    documentation_status: str,
) -> None:
    assignment = assign_report_bucket(
        "ops/reports/release-closeout-summary.json",
        documentation_compliance_status=documentation_status,
    )

    assert assignment["bucket"] == BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE
    assert assignment["documentation_compliance_status"] == documentation_status


@given(name=SAFE_NAME)
def test_property_9_bucket_moves_remove_non_authoritative_reports_from_canonical(
    name: str,
) -> None:
    """Feature: release-evidence-sync, Property 9: bucket moves remove non-authoritative reports from canonical"""
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        source = vault / "ops" / "reports" / f"{name}.json"
        destination = vault / "ops" / "reports" / "observational" / f"{name}.json"
        source.parent.mkdir(parents=True)
        source.write_text('{"status":"stale"}\n', encoding="utf-8")

        result = move_report_delete_first(
            vault,
            source_path=f"ops/reports/{name}.json",
            destination_path=f"ops/reports/observational/{name}.json",
        )

        assert result["source_exists_after_move"] is False
        assert result["destination_exists_after_move"] is True
        assert not source.exists()
        assert destination.exists()


def test_report_bucket_examples_match_release_surface_contract() -> None:
    assert (
        classify_report_bucket("ops/reports/release-closeout-summary.json")
        == BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE
    )
    assert (
        classify_report_bucket("build/release/release-sealed-run-manifest.json")
        == BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR
    )
    assert (
        classify_report_bucket("build/release/release-auto-promotion-ready-plan.json")
        == BUCKET_OBSERVATIONAL_DIAGNOSTIC
    )
    assert (
        classify_report_bucket("ops/reports/archive/release-closeout-summary.json")
        == BUCKET_ARCHIVAL_HISTORICAL
    )


def test_report_bucket_documentation_status_surfaces_missing_docs_without_blocking_assignment() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        (vault / "docs").mkdir(parents=True)
        (vault / "docs" / "repository-surfaces.md").write_text(
            "Only mentions ops/reports/.\n",
            encoding="utf-8",
        )

        report = assign_report_buckets(
            vault,
            ["ops/reports/release-closeout-summary.json"],
        )

        assert report["documentation_compliance_status"] == DOCUMENTATION_STATUS_FAIL
        assert report["assignments"][0]["bucket"] == BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE
        assert report["assignments"][0]["documentation_compliance_status"] == DOCUMENTATION_STATUS_FAIL


def test_report_bucket_documentation_status_passes_when_bucket_contract_is_documented() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        docs = vault / "docs" / "repository-surfaces.md"
        docs.parent.mkdir(parents=True)
        docs.write_text(
            "\n".join(
                [
                    BUCKET_CHECKED_IN_CANONICAL_SOURCE_SIDE,
                    BUCKET_BUILD_RELEASE_AUTHORITATIVE_SIDECAR,
                    BUCKET_OBSERVATIONAL_DIAGNOSTIC,
                    BUCKET_ARCHIVAL_HISTORICAL,
                    "ops/reports/",
                    "build/release/",
                ]
            ),
            encoding="utf-8",
        )

        status = report_bucket_documentation_status(vault)

        assert status["status"] == DOCUMENTATION_STATUS_PASS
        assert status["missing_fragments"] == []
