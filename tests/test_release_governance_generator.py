from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ops.scripts.test.generate_release_governance_from_lane_registry import (
    BEGIN_MARKER,
    END_MARKER,
    PYTHON_VERSION_SOURCE,
    main,
)
from tests.minimal_vault_runtime import REPO_ROOT


def _seed_registry(vault: Path) -> None:
    (vault / "ops" / "schemas").mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "ops" / "test-lane-registry.json",
        vault / "ops" / "test-lane-registry.json",
    )
    shutil.copyfile(
        REPO_ROOT / "ops" / "schemas" / "test-lane-registry.schema.json",
        vault / "ops" / "schemas" / "test-lane-registry.schema.json",
    )


def _seed_governance(vault: Path) -> None:
    path = vault / ".github" / "release-governance.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "publication_target:",
                "  remote: origin",
                "required_status_checks:",
                "  ci_workflow: CI",
                "  ci_matrix:",
                "    python_versions:",
                '      - "3.12"',
                "    tiers:",
                "      - stale",
                "  singleton_checks:",
                '    - "dependency review"',
                "branch_protection:",
                "  require_pull_request: true",
                "release_evidence:",
                "  workflow: Release",
                "",
            ]
        ),
        encoding="utf-8",
    )


class ReleaseGovernanceGeneratorTests(unittest.TestCase):
    def test_default_sync_updates_managed_ci_matrix_and_preserves_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_registry(vault)
            _seed_governance(vault)

            self.assertEqual(main(["--vault", str(vault)]), 0)
            text = (vault / ".github" / "release-governance.yml").read_text(encoding="utf-8")

            self.assertIn(f"  {BEGIN_MARKER}", text)
            self.assertIn(f"  {END_MARKER}", text)
            self.assertIn("# Tier source: ops/test-lane-registry.json", text)
            self.assertIn("Python versions source: constant in", text)
            self.assertIn("  ci_workflow: CI", text)
            self.assertIn("  singleton_checks:", text)
            self.assertIn("branch_protection:", text)
            self.assertIn("release_evidence:", text)
            self.assertNotIn("      - stale", text)
            self.assertFalse((vault / "tmp" / "release-governance-ci-matrix.fragment.yml").exists())

    def test_check_fails_on_text_drift_with_semantic_json_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _seed_registry(vault)
            _seed_governance(vault)
            self.assertEqual(main(["--vault", str(vault)]), 0)
            path = vault / ".github" / "release-governance.yml"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "Python versions source: constant in",
                    "Python versions source: edited constant in",
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--vault", str(vault), "--check", "--json"])

            report = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["mismatched_fields"], [])
            self.assertEqual(report["managed_block"]["status"], "fail")
            self.assertTrue(report["managed_block"]["text_drift"])
            self.assertEqual(report["python_versions_source"], PYTHON_VERSION_SOURCE)


if __name__ == "__main__":
    unittest.main()
