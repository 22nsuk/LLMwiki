from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_REPORTS = REPO_ROOT / "external-reports"
REFERENCE_MANIFEST = EXTERNAL_REPORTS / "report-reference-manifest.json"
ACTION_MATRIX = REPO_ROOT / "ops" / "reports" / "external-report-action-matrix.json"
PUBLIC_EXPORT_MANIFEST = REPO_ROOT / "PUBLIC-EXPORT-MANIFEST.json"
REFERENCE_EXTENSIONS = {".md", ".pdf", ".docx"}
ACTIVE_MATRIX_EXTENSIONS = {".md", ".json"}

pytestmark = [pytest.mark.report_contract]
if PUBLIC_EXPORT_MANIFEST.exists() and not EXTERNAL_REPORTS.exists():
    pytestmark.append(
        pytest.mark.skip(
            reason=(
                "external report lifecycle static checks require full-vault "
                "external-reports; public exports intentionally omit that surface"
            )
        )
    )


def _active_root_paths(extensions: set[str]) -> list[str]:
    if not EXTERNAL_REPORTS.is_dir():
        return []
    paths: list[str] = []
    for path in sorted(EXTERNAL_REPORTS.iterdir()):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if path == REFERENCE_MANIFEST:
            continue
        paths.append(path.relative_to(REPO_ROOT).as_posix())
    return paths


class ExternalReportLifecycleStaticTests(unittest.TestCase):
    def test_checked_in_reference_manifest_matches_active_external_reports(self) -> None:
        payload = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
        expected = _active_root_paths(REFERENCE_EXTENSIONS)
        actual = sorted(str(item["path"]) for item in payload.get("references", []))

        self.assertEqual(actual, expected)
        self.assertEqual(payload["summary"]["active_reference_set_status"], "current")

    def test_checked_in_action_matrix_covers_active_external_reports(self) -> None:
        payload = json.loads(ACTION_MATRIX.read_text(encoding="utf-8"))
        expected = _active_root_paths(ACTIVE_MATRIX_EXTENSIONS)
        actual = sorted(str(item["path"]) for item in payload.get("active_report_coverage", []))

        self.assertEqual(actual, expected)
        self.assertEqual(payload["summary"]["reference_manifest_alignment_status"], "current")
        self.assertEqual(payload["summary"]["reference_manifest_missing_active_report_count"], 0)
        self.assertEqual(payload["summary"]["reference_manifest_stale_reference_count"], 0)


if __name__ == "__main__":
    unittest.main()
