from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.output_runtime import (
    display_path,
    resolve_output_path,
    resolve_repo_output_path,
    resolve_vault_path,
    write_output_text,
)


class OutputRuntimeTest(unittest.TestCase):
    def test_resolve_vault_path_handles_relative_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            absolute = Path(temp_dir) / "outside.json"

            self.assertEqual(
                resolve_vault_path(vault, "reports/result.json"),
                (vault / "reports" / "result.json").resolve(),
            )
            self.assertEqual(resolve_vault_path(vault, absolute), absolute)

    def test_resolve_output_path_requires_default_relative_path_when_out_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            with self.assertRaisesRegex(ValueError, "default_relative_path is required"):
                resolve_output_path(vault, None)

    def test_resolve_repo_output_path_rejects_paths_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            inside = vault / "reports" / "result.json"
            outside = Path(temp_dir) / "outside.json"

            self.assertEqual(
                resolve_repo_output_path(vault, "reports/result.json"),
                inside.resolve(),
            )
            self.assertEqual(resolve_repo_output_path(vault, inside), inside.resolve())
            with self.assertRaisesRegex(ValueError, "repo output path must stay under vault"):
                resolve_repo_output_path(vault, outside)

    def test_repo_output_path_normalizes_windows_separators_for_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            self.assertEqual(
                resolve_repo_output_path(vault, "reports\\nested\\result.json"),
                (vault / "reports" / "nested" / "result.json").resolve(),
            )

    def test_display_path_is_relative_inside_vault_and_absolute_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            inside = vault / "nested" / "report.json"
            outside = Path(temp_dir) / "outside.json"
            inside.parent.mkdir(parents=True)
            inside.write_text("{}", encoding="utf-8")
            outside.write_text("{}", encoding="utf-8")

            self.assertEqual(display_path(vault, inside), "nested/report.json")
            self.assertEqual(display_path(vault, outside), outside.resolve().as_posix())

    def test_write_output_text_returns_written_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "nested" / "dir" / "report.json"
            returned = write_output_text(destination, '{"ok": true}')

            self.assertEqual(returned, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), '{"ok": true}')


if __name__ == "__main__":
    unittest.main()
