from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_repo_conftest():
    spec = importlib.util.spec_from_file_location(
        "repo_conftest_under_test",
        REPO_ROOT / "tests" / "conftest.py",
    )
    if spec is None or spec.loader is None:
        raise unittest.SkipTest("tests/conftest.py is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("LLMWIKI_MAKE_PYTEST_ENTRYPOINT", None)

        completed = subprocess.run(
            [
                _pytest_console_script(),
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_command_runtime.py",
            ],
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
        self.assertIn("make test-all", combined_output)
        self.assertIn(".venv/bin/python -m pytest", combined_output)
        self.assertIn(
            "make test-execution-summary-full-current-or-refresh",
            combined_output,
        )

    def test_selectorless_python_module_pytest_fails_with_make_lane_guidance(self) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("LLMWIKI_MAKE_PYTEST_ENTRYPOINT", None)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )

        combined_output = f"{completed.stdout}\n{completed.stderr}"
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("selectorless `.venv/bin/python -m pytest`", combined_output)
        self.assertIn("make test-all", combined_output)
        self.assertIn("make test-execution-summary-full-current-or-refresh", combined_output)

    def test_python_module_pytest_entrypoint_with_focused_selector_remains_supported(self) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("LLMWIKI_MAKE_PYTEST_ENTRYPOINT", None)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_command_runtime.py",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )

    def test_pytest_scope_helper_rejects_broad_selector_without_make_owner(self) -> None:
        conftest = _load_repo_conftest()

        self.assertFalse(
            conftest._argv_has_focused_pytest_scope(
                ["pytest/__main__.py", "--collect-only", "-q", "-p", "no:cacheprovider"]
            )
        )
        self.assertFalse(conftest._argv_has_focused_pytest_scope(["pytest/__main__.py", "tests"]))
        self.assertTrue(
            conftest._argv_has_focused_pytest_scope(
                ["pytest/__main__.py", "tests/test_command_runtime.py"]
            )
        )
        self.assertTrue(conftest._argv_has_focused_pytest_scope(["pytest/__main__.py", "-m", "not slow"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
