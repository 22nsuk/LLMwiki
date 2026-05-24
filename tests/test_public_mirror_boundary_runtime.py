from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.public_mirror_boundary_runtime import (
    PublicMirrorBoundaryError,
    assert_within_public_mirror,
    is_within_public_mirror,
    repo_relative_path,
)

pytestmark = pytest.mark.public


class PublicMirrorBoundaryRuntimeTests(unittest.TestCase):
    def test_public_source_file_is_accepted(self) -> None:
        self.assertEqual(
            assert_within_public_mirror(Path("."), "docs/README.md"),
            "docs/README.md",
        )

    def test_private_and_generated_surfaces_are_rejected(self) -> None:
        for rel_path in (
            "external-reports/active.md",
            "ops/reports/generated.json",
            "runs/run-1/status.json",
            "raw/source.pdf",
            "wiki/page.md",
            "system/system-log.md",
        ):
            with self.subTest(rel_path=rel_path):
                self.assertFalse(is_within_public_mirror(Path("."), rel_path))
                with self.assertRaises(PublicMirrorBoundaryError):
                    assert_within_public_mirror(Path("."), rel_path)

    def test_parent_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            outside = Path(temp_dir) / "outside.md"
            outside.write_text("secret\n", encoding="utf-8")

            with self.assertRaises(PublicMirrorBoundaryError) as context:
                repo_relative_path(vault, "../outside.md")

            self.assertEqual(context.exception.reason, "path_escapes_vault")

    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            docs = vault / "docs"
            docs.mkdir(parents=True)
            outside = Path(temp_dir) / "outside.md"
            outside.write_text("secret\n", encoding="utf-8")
            link = docs / "outside.md"
            link.symlink_to(outside)

            with self.assertRaises(PublicMirrorBoundaryError):
                assert_within_public_mirror(vault, link)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
