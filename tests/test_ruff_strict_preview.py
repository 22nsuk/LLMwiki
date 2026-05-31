from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "ruff_strict_preview.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ruff_strict_preview", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"failed to load strict Ruff preview helper from {MODULE_PATH}")
RUFF_STRICT_PREVIEW = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(RUFF_STRICT_PREVIEW)


class RuffStrictPreviewTests(unittest.TestCase):
    def test_parse_targets_uses_shell_style_words(self) -> None:
        self.assertEqual(
            RUFF_STRICT_PREVIEW.parse_targets("ops/scripts tests 'tools'"),
            ["ops/scripts", "tests", "tools"],
        )

    def test_parse_targets_rejects_empty_surface(self) -> None:
        with self.assertRaises(ValueError):
            RUFF_STRICT_PREVIEW.parse_targets("   ")

    def test_parse_args_defaults_to_full_public_surface(self) -> None:
        args = RUFF_STRICT_PREVIEW.parse_args([])

        self.assertEqual(args.targets, "ops/scripts tests tools")
        self.assertEqual(args.select, "B,SIM,UP,I")
        self.assertIsNone(args.cache_dir)
        self.assertFalse(hasattr(args, "allowlist"))

    def test_legacy_allowlist_argument_is_rejected(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            RUFF_STRICT_PREVIEW.parse_args(["--allowlist", "ops/legacy-ruff-targets.txt"])

    def test_build_ruff_command_requires_targets(self) -> None:
        with self.assertRaises(ValueError):
            RUFF_STRICT_PREVIEW.build_ruff_command("B,SIM,UP,I", [])

    def test_build_ruff_command_accepts_cache_dir(self) -> None:
        command = RUFF_STRICT_PREVIEW.build_ruff_command(
            "B,SIM,UP,I",
            ["ops/scripts"],
            cache_dir="tmp/tool-cache/ruff/wsl",
        )

        self.assertIn("--cache-dir", command)
        self.assertIn("tmp/tool-cache/ruff/wsl", command)
        self.assertEqual(command[-1], "ops/scripts")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
