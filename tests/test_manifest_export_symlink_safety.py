from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.export_public_repo import export_public_repo
from ops.scripts.wiki_manifest import build_manifest, release_manifest_excludes_path


pytestmark = pytest.mark.report_contract


def _create_symlink_or_skip(test_case: unittest.TestCase, link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            test_case.skipTest("symlink creation requires privileges not available in this Windows environment")
        raise


class ManifestExportSymlinkSafetyTests(unittest.TestCase):
    def test_release_manifest_excludes_path_matches_manifest_policy(self) -> None:
        self.assertTrue(release_manifest_excludes_path("runs/run-1/evidence.json"))
        self.assertTrue(release_manifest_excludes_path("ops/raw-registry.json"))
        self.assertTrue(release_manifest_excludes_path("ops/script-output-surfaces.json"))
        self.assertTrue(release_manifest_excludes_path("ops/operator/operator-release-summary.json"))
        self.assertTrue(release_manifest_excludes_path("tmp/release.zip"))
        self.assertTrue(release_manifest_excludes_path(".venv-py312/bin/python"))
        self.assertFalse(release_manifest_excludes_path("wiki/source--fake.md"))
        self.assertFalse(release_manifest_excludes_path("../outside.txt"))

    def test_build_manifest_does_not_resolve_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            readme = vault / "README.md"
            readme.write_text("root\n", encoding="utf-8")

            original_resolve = Path.resolve

            def patched_resolve(path: Path, *args: object, **kwargs: object) -> Path:
                if path == readme:
                    raise AssertionError("regular manifest file should not require Path.resolve()")
                return original_resolve(path, *args, **kwargs)

            with mock.patch.object(Path, "resolve", autospec=True, side_effect=patched_resolve):
                manifest = build_manifest(vault, vault / "ops" / "manifest.json")

            manifest_paths = {item["path"] for item in manifest["files"]}
            self.assertIn("README.md", manifest_paths)

    def test_build_manifest_prunes_virtualenv_name_variants_before_file_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            virtualenv_file = vault / ".venv-py312" / "lib64" / "python"
            virtualenv_file.parent.mkdir(parents=True)
            virtualenv_file.write_text("python\n", encoding="utf-8")

            original_is_file = Path.is_file

            def patched_is_file(path: Path) -> bool:
                if ".venv-py312" in path.parts:
                    raise AssertionError(".venv-* directories should be pruned before file checks")
                return original_is_file(path)

            with mock.patch.object(Path, "is_file", autospec=True, side_effect=patched_is_file):
                manifest = build_manifest(vault, vault / "ops" / "manifest.json")

            manifest_paths = {item["path"] for item in manifest["files"]}
            self.assertIn("README.md", manifest_paths)
            self.assertNotIn(".venv-py312/lib64/python", manifest_paths)

    def test_build_manifest_excludes_symlinked_file_even_when_target_is_inside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "tools").mkdir()
            (vault / "tools" / "target.txt").write_text("safe\n", encoding="utf-8")
            _create_symlink_or_skip(self, vault / "tools" / "alias.txt", vault / "tools" / "target.txt")

            manifest = build_manifest(vault, vault / "ops" / "manifest.json")
            manifest_paths = {item["path"] for item in manifest["files"]}

            self.assertIn("tools/target.txt", manifest_paths)
            self.assertNotIn("tools/alias.txt", manifest_paths)

    def test_build_manifest_excludes_review_patch_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "review").mkdir()
            (vault / "review" / "candidate.patch").write_text("patch\n", encoding="utf-8")

            manifest = build_manifest(vault, vault / "ops" / "manifest.json")
            manifest_paths = {item["path"] for item in manifest["files"]}

            self.assertIn("README.md", manifest_paths)
            self.assertNotIn("review/candidate.patch", manifest_paths)

    def test_build_manifest_tolerates_inaccessible_excluded_virtualenv_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / ".venv").mkdir()
            (vault / ".venv" / "lib64").mkdir()

            original_is_file = Path.is_file

            def patched_is_file(path: Path) -> bool:
                if path == vault / ".venv" / "lib64":
                    raise OSError(1920, "The system cannot access the file")
                return original_is_file(path)

            with mock.patch.object(Path, "is_file", autospec=True, side_effect=patched_is_file):
                manifest = build_manifest(vault, vault / "ops" / "manifest.json")

            manifest_paths = {item["path"] for item in manifest["files"]}
            self.assertIn("README.md", manifest_paths)
            self.assertNotIn(".venv/lib64", manifest_paths)

    def test_export_public_repo_excludes_symlinked_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache\n", encoding="utf-8")
            (vault / "THIRD_PARTY_NOTICES.md").write_text("notices\n", encoding="utf-8")
            (vault / "CONTRIBUTING.md").write_text("contrib\n", encoding="utf-8")
            (vault / "SECURITY.md").write_text("security\n", encoding="utf-8")
            (vault / "ARCHITECTURE.md").write_text("arch\n", encoding="utf-8")
            (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            (vault / "pyproject.toml").write_text("[build-system]\nrequires=['setuptools']\n", encoding="utf-8")
            (vault / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
            (vault / "requirements-dev.txt").write_text("-r requirements.txt\npytest\n", encoding="utf-8")
            (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            (vault / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (vault / "tools").mkdir()
            (vault / "tools" / "target.txt").write_text("safe\n", encoding="utf-8")
            _create_symlink_or_skip(self, vault / "tools" / "alias.txt", vault / "tools" / "target.txt")

            public_dir = Path(temp_dir) / "public"
            manifest = export_public_repo(vault, public_dir)

            self.assertIn("tools/target.txt", manifest["files"])
            self.assertNotIn("tools/alias.txt", manifest["files"])
            self.assertFalse((public_dir / "tools" / "alias.txt").exists())

    def test_export_public_repo_tolerates_inaccessible_excluded_virtualenv_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache\n", encoding="utf-8")
            (vault / "THIRD_PARTY_NOTICES.md").write_text("notices\n", encoding="utf-8")
            (vault / "CONTRIBUTING.md").write_text("contrib\n", encoding="utf-8")
            (vault / "SECURITY.md").write_text("security\n", encoding="utf-8")
            (vault / "ARCHITECTURE.md").write_text("arch\n", encoding="utf-8")
            (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            (vault / "pyproject.toml").write_text("[build-system]\nrequires=['setuptools']\n", encoding="utf-8")
            (vault / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
            (vault / "requirements-dev.txt").write_text("-r requirements.txt\npytest\n", encoding="utf-8")
            (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            (vault / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (vault / ".venv").mkdir()
            (vault / ".venv" / "lib64").mkdir()

            original_is_file = Path.is_file

            def patched_is_file(path: Path) -> bool:
                if path == vault / ".venv" / "lib64":
                    raise OSError(1920, "The system cannot access the file")
                return original_is_file(path)

            public_dir = Path(temp_dir) / "public"
            with mock.patch.object(Path, "is_file", autospec=True, side_effect=patched_is_file):
                manifest = export_public_repo(vault, public_dir)

            self.assertIn("README.md", manifest["files"])
            self.assertNotIn(".venv/lib64", manifest["files"])


if __name__ == "__main__":
    unittest.main()
