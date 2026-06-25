from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.scripts.core.policy_runtime import report_path
from ops.scripts.release.external_report_inventory_runtime import (
    REFERENCE_MANIFEST,
    active_reference_report_paths,
    active_report_paths,
    archived_report_count,
    archived_report_paths,
    coverage_markers,
    is_unmatched_recommendation_line,
    matched_actions,
    reference_manifest_alignment,
    report_type_for_path,
    unmatched_recommendation_count,
)
from tests.minimal_vault_runtime import REPO_ROOT

ARCHIVED_REVIEW_REPORT_PATHS = (
    "external-reports/archive/llmwiki_project_review_report(7).md",
    "external-reports/archive/llmwiki_project_review_report(8).md",
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
    assert [report_path(tmp_path, path) for path in archived_report_paths(tmp_path)] == [
        "external-reports/archive/old.md"
    ]
    assert archived_report_count(tmp_path) == 1


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


def test_unmatched_recommendation_count_ignores_headings_and_priority_notation_meta() -> None:
    text = "\n".join(
        [
            "## 7.1 P0 — section heading",
            "- **우선순위 표기:** 이 문서의 `P0/P1/P2`는 수정 순서를 위한 프로젝트 우선순위이며 정식 CVSS 등급은 아니다.",
            "1. P0 runner·executor 모듈을 strict mypy 대상으로 지정",
        ]
    )

    assert not is_unmatched_recommendation_line("## 7.1 P0 — section heading")
    assert not is_unmatched_recommendation_line(
        "- **우선순위 표기:** 이 문서의 `P0/P1/P2`는 수정 순서를 위한 프로젝트 우선순위이며 정식 CVSS 등급은 아니다."
    )
    assert not is_unmatched_recommendation_line(
        "1. P0 runner·executor 모듈을 strict mypy 대상으로 지정"
    )
    assert unmatched_recommendation_count(text) == 0


def test_archived_reports_seven_and_eight_have_no_unmatched_recommendations() -> None:
    report_paths = [REPO_ROOT / rel_path for rel_path in ARCHIVED_REVIEW_REPORT_PATHS]
    if not all(path.is_file() for path in report_paths):
        pytest.skip(
            "archived external reports (7)/(8) are local-only and absent in this source tree"
        )

    for path in report_paths:
        text = path.read_text(encoding="utf-8")
        assert unmatched_recommendation_count(text) == 0, report_path(REPO_ROOT, path)


def test_active_selector_includes_binary_reports_with_explicit_type(tmp_path: Path) -> None:
    reports = tmp_path / "external-reports"
    archive = reports / "archive"
    archive.mkdir(parents=True)
    pdf = reports / "review.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    (archive / "old.pdf").write_bytes(b"%PDF-1.4\n")
    (reports / Path(REFERENCE_MANIFEST).name).write_text("{}", encoding="utf-8")

    assert [report_path(tmp_path, path) for path in active_report_paths(tmp_path)] == [
        "external-reports/review.pdf"
    ]
    assert report_type_for_path(pdf) == "binary_report"
