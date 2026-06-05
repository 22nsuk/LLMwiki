from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "strict_preview_audit.py"
STRICT_CANDIDATE_SELECT = "PTH201"
MODULE_SPEC = importlib.util.spec_from_file_location("strict_preview_audit", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"failed to load strict preview audit helper from {MODULE_PATH}")
STRICT_PREVIEW_AUDIT = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = STRICT_PREVIEW_AUDIT
MODULE_SPEC.loader.exec_module(STRICT_PREVIEW_AUDIT)


class StrictPreviewAuditTests(unittest.TestCase):
    def test_parse_targets_uses_shell_style_words(self) -> None:
        self.assertEqual(
            STRICT_PREVIEW_AUDIT.parse_targets("ops/scripts tests 'tools'"),
            ["ops/scripts", "tests", "tools"],
        )

    def test_parse_targets_rejects_empty_surface(self) -> None:
        with self.assertRaises(ValueError):
            STRICT_PREVIEW_AUDIT.parse_targets("   ")

    def test_parses_ruff_statistics_and_mypy_summary(self) -> None:
        ruff = STRICT_PREVIEW_AUDIT.parse_ruff_output(
            "442\tI001  \t[*] unsorted-imports\n"
            "24\tB904  \t[ ] raise-without-from-inside-except\n"
            "Found 466 errors.\n"
        )
        mypy = STRICT_PREVIEW_AUDIT.parse_mypy_output(
            "tests/example.py:1: error: example  [attr-defined]\n"
            "Found 195 errors in 32 files (checked 482 source files)\n"
        )

        self.assertEqual(ruff["error_count"], 466)
        self.assertEqual(ruff["rule_counts"]["I001"], 442)
        self.assertEqual(ruff["rule_counts"]["B904"], 24)
        self.assertEqual(mypy, {"error_count": 195, "file_count": 32})

    def test_build_report_is_attention_when_any_preview_finds_debt(self) -> None:
        calls: list[list[str]] = []

        def runner(args: Sequence[str], cwd: Path) -> object:
            calls.append(list(args))
            if args[2] == "ruff":
                return STRICT_PREVIEW_AUDIT.CommandResult(
                    1,
                    "1\tI001  \t[*] unsorted-imports\nFound 1 error.\n",
                    "",
                )
            return STRICT_PREVIEW_AUDIT.CommandResult(
                1,
                "Found 2 errors in 1 file (checked 3 source files)\n",
                "",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            report = STRICT_PREVIEW_AUDIT.build_report(
                Path(temp_dir),
                targets=["ops/scripts", "tests", "tools"],
                ruff_select=STRICT_CANDIDATE_SELECT,
                ruff_cache_dir="tmp/tool-cache/ruff/wsl",
                mypy_flags=["--check-untyped-defs"],
                python_executable="python",
                command_runner=runner,
            )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["total_error_count"], 3)
        self.assertEqual(report["targets"], ["ops/scripts", "tests", "tools"])
        self.assertEqual(report["ruff_cache_dir"], "tmp/tool-cache/ruff/wsl")
        self.assertIn("--cache-dir", calls[0])
        self.assertIn("tmp/tool-cache/ruff/wsl", calls[0])
        self.assertIn("--statistics", calls[0])
        self.assertIn("--check-untyped-defs", calls[1])

    def test_build_report_is_attention_when_preview_command_fails_without_counts(self) -> None:
        def runner(args: Sequence[str], cwd: Path) -> object:
            return STRICT_PREVIEW_AUDIT.CommandResult(2, "", "tool configuration failed\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            report = STRICT_PREVIEW_AUDIT.build_report(
                Path(temp_dir),
                targets=["ops/scripts"],
                ruff_select=STRICT_CANDIDATE_SELECT,
                mypy_flags=["--check-untyped-defs"],
                python_executable="python",
                command_runner=runner,
            )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["total_error_count"], 0)
        self.assertEqual(report["ruff"]["returncode"], 2)
        self.assertEqual(report["mypy"]["returncode"], 2)

    def test_main_fail_on_attention_exits_nonzero_for_preview_tool_failure(self) -> None:
        def runner(args: Sequence[str], cwd: Path) -> object:
            return STRICT_PREVIEW_AUDIT.CommandResult(2, "", "tool configuration failed\n")

        with tempfile.TemporaryDirectory() as temp_dir:
            rc = STRICT_PREVIEW_AUDIT.main(
                [
                    "--vault",
                    temp_dir,
                    "--out",
                    "strict-preview-audit.json",
                    "--targets",
                    "ops/scripts",
                    "--fail-on-attention",
                ],
                command_runner=runner,
            )

        self.assertEqual(rc, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
