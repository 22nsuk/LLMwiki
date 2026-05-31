from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.release.release_dependency_reproducibility_runtime import (
    dependency_reproducibility_record,
)


class ReleaseDependencyReproducibilityRuntimeTests(unittest.TestCase):
    def test_record_uses_only_canonical_dependency_authority_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
            (vault / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (vault / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
            (vault / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")

            record = dependency_reproducibility_record(vault)

            paths = [item["path"] for item in record["dependency_files"]]
            self.assertEqual(paths, ["pyproject.toml", "uv.lock"])
            self.assertEqual(record["status"], "locked")
            self.assertEqual(record["canonical_lockfile_path"], "uv.lock")
            self.assertTrue(record["dependency_fingerprint"])
            self.assertNotIn("requirements", record["summary"])

    def test_missing_uv_lock_is_missing_lockfile_without_range_requirements_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
            (vault / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")

            record = dependency_reproducibility_record(vault)

            self.assertEqual(record["status"], "missing_lockfile")
            self.assertEqual(record["canonical_lockfile_sha256"], "")
            self.assertEqual(
                [item["path"] for item in record["dependency_files"]],
                ["pyproject.toml", "uv.lock"],
            )


if __name__ == "__main__":
    unittest.main()
