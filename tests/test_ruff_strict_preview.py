from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "ruff_strict_preview.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ruff_strict_preview", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"failed to load strict Ruff preview helper from {MODULE_PATH}")
RUFF_STRICT_PREVIEW = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(RUFF_STRICT_PREVIEW)


class RuffStrictPreviewTests(unittest.TestCase):
    def test_load_allowlist_targets_ignores_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (vault / "tests").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
            (vault / "tests" / "test_example.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            (vault / "ops").mkdir(exist_ok=True)
            (vault / "ops" / "allowlist.txt").write_text(
                "# comment\n\nops/scripts/example.py\n  tests/test_example.py  \n",
                encoding="utf-8",
            )

            targets = RUFF_STRICT_PREVIEW.load_allowlist_targets(vault, "ops/allowlist.txt")

            self.assertEqual(targets, ["ops/scripts/example.py", "tests/test_example.py"])

    def test_load_allowlist_targets_rejects_missing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "allowlist.txt").write_text("ops/scripts/missing.py\n", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                RUFF_STRICT_PREVIEW.load_allowlist_targets(vault, "ops/allowlist.txt")

    def test_load_allowlist_targets_tolerates_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
            allowlist = vault / "ops" / "allowlist.txt"
            allowlist.write_text("\ufeffops/scripts/example.py\n", encoding="utf-8")

            targets = RUFF_STRICT_PREVIEW.load_allowlist_targets(vault, "ops/allowlist.txt")

            self.assertEqual(targets, ["ops/scripts/example.py"])

    def test_build_ruff_command_requires_targets(self) -> None:
        with self.assertRaises(ValueError):
            RUFF_STRICT_PREVIEW.build_ruff_command("B,SIM,UP,I", [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()