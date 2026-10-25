from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.scripts.core.policy_runtime import report_path
from ops.scripts.release.external_report_lifecycle_runtime import (
    active_reference_report_paths,
    active_report_paths,
    archived_report_paths,
)
from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = [pytest.mark.report_contract, pytest.mark.report_contract_core]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_checked_in_external_report_manifest_and_matrix_cover_active_root_reports() -> None:
    external_root = REPO_ROOT / "external-reports"
    if not external_root.is_dir():
        pytest.skip("external-reports is local-only and absent in this source tree")

    expected_reference_paths = sorted(
        report_path(REPO_ROOT, path) for path in active_reference_report_paths(REPO_ROOT)
    )
    expected_matrix_paths = sorted(
        report_path(REPO_ROOT, path) for path in active_report_paths(REPO_ROOT)
    )
    expected_archive_basis_paths = sorted(
        report_path(REPO_ROOT, path) for path in archived_report_paths(REPO_ROOT)
    )

    manifest = _load_json(external_root / "report-reference-manifest.json")
    manifest_paths = sorted(
        str(item["path"]) for item in manifest.get("references", []) if isinstance(item, dict)
    )

    assert manifest_paths == expected_reference_paths
    assert manifest["summary"]["active_reference_set_status"] == "current"
    assert manifest["active_reference_set"]["status"] == "current"

    matrix = _load_json(REPO_ROOT / "ops" / "reports" / "external-report-action-matrix.json")
    coverage_paths = sorted(str(item["path"]) for item in matrix["active_report_coverage"])
    matrix_archive_basis_paths = sorted(
        str(item["path"]) for item in matrix["archived_report_action_basis"]
    )
    generated_index = _load_json(
        REPO_ROOT / "ops" / "reports" / "generated-artifact-index.json"
    )
    generated_index_archive_basis_paths = sorted(
        str(item["path"])
        for item in generated_index["archived_external_report_basis"]
    )

    assert coverage_paths == expected_matrix_paths
    assert matrix_archive_basis_paths == expected_archive_basis_paths
    assert generated_index_archive_basis_paths == expected_archive_basis_paths
    assert matrix["summary"]["active_report_count"] == len(expected_matrix_paths)
    assert matrix["summary"]["archived_report_count"] == len(expected_archive_basis_paths)
    assert (
        generated_index["summary"]["external_reports_archive_file_count"]
        == len(expected_archive_basis_paths)
    )
    for coverage in matrix["active_report_coverage"]:
        assert coverage["recommendation_intake_status"] == "reviewed"
        assert coverage["recommendation_candidate_count"] > 0
        assert (
            coverage["recommendation_candidate_count"]
            == coverage["recommendation_covered_count"]
            + coverage["recommendation_unresolved_count"]
        )
        assert coverage["unmatched_recommendation_count"] == coverage[
            "recommendation_unresolved_count"
        ]
        assert len(coverage["unmatched_recommendation_line_sha256"]) == coverage[
            "recommendation_unresolved_count"
        ]
    assert matrix["summary"]["recommendation_intake_status_counts"]["reviewed"] == len(
        expected_matrix_paths
    )
    assert matrix["summary"]["recommendation_candidate_count"] == sum(
        int(item["recommendation_candidate_count"])
        for item in matrix["active_report_coverage"]
    )
    assert matrix["summary"]["recommendation_covered_count"] == sum(
        int(item["recommendation_covered_count"])
        for item in matrix["active_report_coverage"]
    )
    assert matrix["summary"]["recommendation_unresolved_count"] == sum(
        int(item["recommendation_unresolved_count"])
        for item in matrix["active_report_coverage"]
    )
    assert matrix["summary"]["unmatched_active_report_count"] == sum(
        1
        for item in matrix["active_report_coverage"]
        if int(item["recommendation_unresolved_count"]) > 0
    )
    assert matrix["summary"]["reference_manifest_alignment_status"] == "current"
    assert matrix["summary"]["reference_manifest_missing_active_report_count"] == 0
    assert matrix["summary"]["reference_manifest_stale_reference_count"] == 0
