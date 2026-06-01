from __future__ import annotations

import json
from pathlib import Path

from ops.scripts.policy_runtime import report_path

from ops.scripts.release.external_report_inventory_runtime import (
    REFERENCE_MANIFEST,
    active_reference_report_paths,
    active_report_paths,
    coverage_markers,
    matched_actions,
    reference_manifest_alignment,
)


def test_active_report_paths_exclude_reference_manifest_and_archive(tmp_path: Path) -> None:
    reports = tmp_path / "external-reports"
    archive = reports / "archive"
    archive.mkdir(parents=True)
    active = reports / "review.md"
    active.write_text("# Review\n", encoding="utf-8")
    (reports / Path(REFERENCE_MANIFEST).name).write_text("{}", encoding="utf-8")
    (archive / "old.md").write_text("# Old\n", encoding="utf-8")

    assert [report_path(tmp_path, path) for path in active_report_paths(tmp_path)] == [
        "external-reports/review.md"
    ]
    assert [report_path(tmp_path, path) for path in active_reference_report_paths(tmp_path)] == [
        "external-reports/review.md"
    ]


def test_reference_manifest_alignment_reports_current_and_drift(tmp_path: Path) -> None:
    reports = tmp_path / "external-reports"
    reports.mkdir()
    active = reports / "review.md"
    active.write_text("# Review\n", encoding="utf-8")
    manifest = tmp_path / REFERENCE_MANIFEST
    manifest.write_text(
        json.dumps({"references": [{"path": "external-reports/review.md"}]}),
        encoding="utf-8",
    )

    assert reference_manifest_alignment(tmp_path)["status"] == "current"

    manifest.write_text(
        json.dumps({"references": [{"path": "external-reports/stale.md"}]}),
        encoding="utf-8",
    )
    drift = reference_manifest_alignment(tmp_path)

    assert drift["status"] == "drift"
    assert drift["missing_active_report_paths"] == ["external-reports/review.md"]
    assert drift["stale_reference_paths"] == ["external-reports/stale.md"]


def test_coverage_markers_and_action_matching_are_catalog_backed(tmp_path: Path) -> None:
    report = tmp_path / "external-reports" / "review.md"
    report.parent.mkdir()
    text = "Final conclusion with live truth about script-output-surfaces."
    report.write_text(text, encoding="utf-8")

    assert "final_conclusion" in coverage_markers(report, text)
    assert "live_reverification" in coverage_markers(report, text)
    assert "script_output_surfaces_currentness" in matched_actions(text)
