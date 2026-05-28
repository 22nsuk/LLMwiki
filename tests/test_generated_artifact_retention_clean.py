from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.generated_artifact_retention_clean import build_report

pytestmark = pytest.mark.report_contract


class GeneratedArtifactRetentionCleanTests(unittest.TestCase):
    def _vault(self, root: Path) -> Path:
        vault = root / "vault"
        vault.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
        (vault / ".gitignore").write_text(
            "\n".join(
                [
                    "build/",
                    "tmp/",
                    "ops/reports/",
                    "ops/operator/",
                    "runs/",
                    "raw/",
                    "wiki/",
                    "system/",
                    "external-reports/",
                    ".pytest_cache/",
                    ".ruff_cache/",
                    ".mypy_cache/",
                    "llm_wiki_vnext.egg-info/",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return vault

    def test_dry_run_reports_delete_candidates_without_removing_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text("{}", encoding="utf-8")
            (vault / "build/release").mkdir(parents=True)
            (vault / "build/release/release-run-manifest.json").write_text("{}", encoding="utf-8")
            (vault / "runs/goal-demo/state").mkdir(parents=True)
            (vault / "runs/goal-demo/state/local.json").write_text("{}", encoding="utf-8")

            report = build_report(vault)

            candidates = {item["path"]: item for item in report["delete_candidates"]}
            retained = {item["path"]: item for item in report["retained"]}
            self.assertEqual(report["status"], "pass")
            self.assertTrue(candidates["build/source-package-smoke"]["exists"])
            self.assertTrue(candidates["build/source-package-smoke"]["ignored"])
            self.assertEqual(report["deleted_paths"], [])
            self.assertIn("build/release", retained)
            self.assertTrue(retained["build/release"]["exists"])
            self.assertIn("runs/goal-demo/state", retained)
            self.assertTrue((vault / "build/source-package-smoke/report.json").is_file())

    def test_apply_deletes_only_ignored_allowlist_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text("{}", encoding="utf-8")
            (vault / "build/release").mkdir(parents=True)
            (vault / "build/release/release-run-manifest.json").write_text("{}", encoding="utf-8")
            (vault / "raw").mkdir()
            (vault / "raw/private.md").write_text("private", encoding="utf-8")

            report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "pass")
            self.assertIn("build/source-package-smoke", report["deleted_paths"])
            self.assertFalse((vault / "build/source-package-smoke").exists())
            self.assertTrue((vault / "build/release/release-run-manifest.json").is_file())
            self.assertTrue((vault / "raw/private.md").is_file())

    def test_apply_blocks_non_ignored_allowlist_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / ".gitignore").write_text("", encoding="utf-8")
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text("{}", encoding="utf-8")

            report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["deleted_paths"], [])
            self.assertEqual(
                report["blockers"],
                [
                    {
                        "path": "build/source-package-smoke",
                        "reason": "delete candidate exists but is not ignored by git",
                    }
                ],
            )
            self.assertTrue((vault / "build/source-package-smoke/report.json").is_file())


if __name__ == "__main__":
    unittest.main()
