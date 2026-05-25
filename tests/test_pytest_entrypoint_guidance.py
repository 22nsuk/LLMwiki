from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pytest_console_script() -> str:
    executable_dirs = (
        Path(sys.executable).parent,
        Path(sys.executable).resolve().parent,
        REPO_ROOT / ".venv" / "bin",
        REPO_ROOT / ".venv" / "Scripts",
    )
    for executable_dir in executable_dirs:
        for name in ("pytest", "pytest.exe"):
            candidate = executable_dir / name
            if candidate.exists():
                return str(candidate)
    for name in ("pytest", "pytest.exe"):
        found = shutil.which(name)
        if found:
            return found
    raise unittest.SkipTest("pytest console script is unavailable")


class PytestEntrypointGuidanceTests(unittest.TestCase):
    def test_bare_pytest_fails_with_supported_entrypoint_guidance(self) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        completed = subprocess.run(
            [_pytest_console_script(), "--collect-only", "-q", "tests/test_command_runtime.py"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        combined_output = f"{completed.stdout}\n{completed.stderr}"
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("plain `pytest` is not a supported entrypoint", combined_output)
        self.assertIn(".venv/bin/python -m pytest", combined_output)

    def test_python_module_pytest_entrypoint_remains_supported(self) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/test_command_runtime.py"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
