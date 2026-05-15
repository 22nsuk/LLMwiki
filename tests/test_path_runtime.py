from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.path_runtime import stable_report_path


class PathRuntimeTest(unittest.TestCase):
    def test_stable_report_path_returns_repo_relative_for_absolute_path_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            path = vault / "wiki" / "concept--fake.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Concept\n", encoding="utf-8")

            self.assertEqual(stable_report_path(vault, path), "wiki/concept--fake.md")

    def test_stable_report_path_treats_relative_repo_paths_as_vault_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            (vault / "wiki").mkdir(parents=True)

            self.assertEqual(
                stable_report_path(vault, Path("wiki/concept--fake.md")),
                "wiki/concept--fake.md",
            )

    def test_stable_report_path_normalizes_internal_parent_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("# Readme\n", encoding="utf-8")

            self.assertEqual(stable_report_path(vault, Path("ops/../README.md")), "README.md")

    def test_stable_report_path_falls_back_to_absolute_path_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "vault"
            outside = root / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")

            self.assertEqual(stable_report_path(vault, outside), outside.resolve().as_posix())

    def test_stable_report_path_resolves_symlink_target_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = root / "vault"
            vault.mkdir()
            outside = root / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            symlink = vault / "wiki-link.md"
            try:
                symlink.symlink_to(outside)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation is unavailable in this environment")

            self.assertEqual(stable_report_path(vault, symlink), outside.resolve().as_posix())


if __name__ == "__main__":
    unittest.main()
