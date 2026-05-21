from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.scripts.release.release_ready_commit import main


def _git(vault: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=vault,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


class ReleaseReadyCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        _git(self.vault, "init", "-q")
        _git(self.vault, "config", "user.email", "release-ready@example.test")
        _git(self.vault, "config", "user.name", "Release Ready Test")
        (self.vault / ".gitignore").write_text("tmp/\n", encoding="utf-8")
        (self.vault / "README.md").write_text("# Test\n", encoding="utf-8")
        (self.vault / "ops" / "reports").mkdir(parents=True)
        (self.vault / "ops" / "reports" / "release-smoke-report.json").write_text(
            "{}\n", encoding="utf-8"
        )
        _git(self.vault, "add", ".")
        _git(self.vault, "commit", "-m", "initial")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_commits_public_source_and_generated_evidence_together(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")
        (self.vault / "ops" / "reports" / "release-smoke-report.json").write_text(
            '{"status": "pass"}\n', encoding="utf-8"
        )
        (self.vault / "ops" / "scripts").mkdir(parents=True)
        (self.vault / "ops" / "scripts" / "new_helper.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 0)
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("README.md", changed_paths)
        self.assertIn("ops/reports/release-smoke-report.json", changed_paths)
        self.assertIn("ops/scripts/new_helper.py", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "committed")
        categories = {entry["path"]: entry["category"] for entry in report["entries"]}
        self.assertEqual(categories["README.md"], "public_source")
        self.assertEqual(
            categories["ops/reports/release-smoke-report.json"], "generated_canonical"
        )

    def test_rejects_private_dirty_paths_before_staging(self) -> None:
        (self.vault / "raw").mkdir()
        (self.vault / "raw" / "private.md").write_text("secret corpus\n", encoding="utf-8")

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 1)
        self.assertIn("?? raw/", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "unexpected_dirty_paths")
        self.assertEqual(report["unexpected_paths"], ["raw"])

    def test_rejects_preexisting_staged_changes_by_default(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nStaged.\n", encoding="utf-8")
        _git(self.vault, "add", "README.md")

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 1)
        report = json.loads(
            (self.vault / "tmp" / "release-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "preexisting_staged_changes")
        self.assertEqual(report["staged_paths"], ["README.md"])


if __name__ == "__main__":
    unittest.main()
