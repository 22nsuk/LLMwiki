from __future__ import annotations

import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.test.changed_path_minimum_executor import _resolved_argv, execute_plan

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]
REPO_ROOT = Path(__file__).resolve().parents[1]


def _report(
    *specs: dict[str, object],
    path_recommendations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "changed_path_minimum_plan": {
            "selected_commands": [spec["command"] for spec in specs],
            "selected_command_specs": list(specs),
            "final_checkpoint_commands": ["make release-run-ready"],
            "path_recommendations": path_recommendations or [],
        }
    }


class ChangedPathMinimumExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        for rel_path in (
            "ops/test-lane-registry.json",
            "ops/schemas/test-lane-registry.schema.json",
        ):
            destination = self.vault / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                (REPO_ROOT / rel_path).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        workspace_python = self.vault / ".venv/bin/python"
        workspace_python.parent.mkdir(parents=True, exist_ok=True)
        workspace_python.touch()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_executes_specs_in_order_without_final_checkpoint(self) -> None:
        calls: list[dict[str, Any]] = []

        def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append({"argv": argv, **kwargs})
            return subprocess.CompletedProcess(argv, 0)

        report = _report(
            {"command": "make static", "argv": ["make", "static"], "env": {}},
            {
                "command": (
                    "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p "
                    "no:cacheprovider tests/test_example.py"
                ),
                "argv": [
                    ".venv/bin/python",
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "tests/test_example.py",
                ],
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
            },
        )

        self.assertEqual(execute_plan(self.vault, report, run_command=run), 0)
        self.assertEqual(
            [call["argv"][1:] for call in calls],
            [
                ["static"],
                [
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "tests/test_example.py",
                ],
            ],
        )
        self.assertEqual(
            Path(calls[1]["argv"][0]).resolve(),
            next(
                path.resolve()
                for path in (
                    self.vault / ".venv/bin/python",
                    self.vault / ".venv/Scripts/python.exe",
                )
                if path.is_file()
            ),
        )
        self.assertEqual(calls[1]["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertNotIn(
            "release-run-ready",
            [token for call in calls for token in call["argv"]],
        )

    def test_stops_after_first_failure(self) -> None:
        calls: list[list[str]] = []

        def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 7)

        report = _report(
            {"command": "make static", "argv": ["make", "static"], "env": {}},
            {"command": "make test", "argv": ["make", "test"], "env": {}},
        )

        self.assertEqual(execute_plan(self.vault, report, run_command=run), 7)
        self.assertEqual(calls, [["make", "static"]])

    def test_skips_deleted_dynamic_pytest_selector_and_keeps_other_commands(self) -> None:
        selector = "tests/test_deleted.py"
        pytest_command = (
            "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p "
            f"no:cacheprovider {selector}"
        )
        report = _report(
            {"command": "make static", "argv": ["make", "static"], "env": {}},
            {
                "command": pytest_command,
                "argv": [*self._pytest_prefix(), selector],
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
            },
            path_recommendations=[
                {
                    "path": selector,
                    "commands": ["make static", pytest_command],
                }
            ],
        )
        calls: list[list[str]] = []

        def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        output = StringIO()
        with redirect_stdout(output):
            result = execute_plan(self.vault, report, run_command=run)

        self.assertEqual(result, 0)
        self.assertEqual(calls, [["make", "static"]])
        self.assertIn(
            'changed-path minimum skipped deleted selector [2/2]: "tests/test_deleted.py"',
            output.getvalue(),
        )

    def test_does_not_skip_missing_fixed_registry_selector(self) -> None:
        selector = "tests/test_missing_registry_selector.py"
        command = (
            "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p "
            f"no:cacheprovider {selector}"
        )
        report = _report(
            {
                "command": command,
                "argv": [*self._pytest_prefix(), selector],
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
            },
            path_recommendations=[
                {
                    "path": "ops/scripts/example.py",
                    "commands": [command],
                }
            ],
        )
        calls: list[list[str]] = []

        def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 4)

        self.assertEqual(execute_plan(self.vault, report, run_command=run), 4)
        self.assertEqual(len(calls), 1)

    def test_rejects_commands_outside_the_registry_execution_grammar(self) -> None:
        unsafe_reports = (
            _report(
                {
                    "command": "shell",
                    "argv": ["sh", "-c", "echo unsafe"],
                    "env": {},
                }
            ),
            _report({"command": "make", "argv": ["make", "test", "EXTRA=1"], "env": {}}),
            _report({"command": "make tmp-clean", "argv": ["make", "tmp-clean"], "env": {}}),
            _report(
                {
                    "command": "pytest",
                    "argv": [*self._pytest_prefix(), "../private.py"],
                    "env": {"PYTHONDONTWRITEBYTECODE": "1"},
                }
            ),
        )

        for report in unsafe_reports:
            with self.subTest(report=report), self.assertRaises(ValueError):
                execute_plan(self.vault, report)

    def test_rejects_display_and_execution_spec_drift(self) -> None:
        report = _report(
            {"command": "make static", "argv": ["make", "static"], "env": {}}
        )
        report["changed_path_minimum_plan"]["selected_commands"] = ["make test"]  # type: ignore[index]

        with self.assertRaisesRegex(ValueError, "do not match"):
            execute_plan(self.vault, report)

    def test_rejects_display_command_that_names_a_different_make_target(self) -> None:
        report = _report(
            {"command": "make static", "argv": ["make", "test"], "env": {}}
        )

        with self.assertRaisesRegex(ValueError, "does not match argv"):
            execute_plan(self.vault, report)

    def test_rejects_display_command_that_names_a_different_pytest_selector(self) -> None:
        report = _report(
            {
                "command": (
                    "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p "
                    "no:cacheprovider tests/test_one.py"
                ),
                "argv": [*self._pytest_prefix(), "tests/test_two.py"],
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
            }
        )

        with self.assertRaisesRegex(ValueError, "does not match argv"):
            execute_plan(self.vault, report)

    def test_rejects_selector_symlink_that_resolves_outside_tests(self) -> None:
        outside = Path(self.temp_dir.name) / "outside.py"
        outside.write_text("def test_outside(): pass\n", encoding="utf-8")
        tests_dir = self.vault / "tests"
        tests_dir.mkdir()
        selector_path = tests_dir / "test_link.py"
        try:
            selector_path.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        selector = "tests/test_link.py"
        command = (
            "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p "
            f"no:cacheprovider {selector}"
        )
        report = _report(
            {
                "command": command,
                "argv": [*self._pytest_prefix(), selector],
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
            }
        )

        with self.assertRaisesRegex(ValueError, "resolves outside tests"):
            execute_plan(self.vault, report)

    def test_rejects_tests_root_symlink_that_resolves_outside_repository(self) -> None:
        outside_tests = Path(self.temp_dir.name) / "outside-tests"
        outside_tests.mkdir()
        (outside_tests / "test_external.py").write_text(
            "def test_external(): pass\n",
            encoding="utf-8",
        )
        tests_dir = self.vault / "tests"
        try:
            tests_dir.symlink_to(outside_tests, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        selector = "tests/test_external.py"
        command = (
            "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p "
            f"no:cacheprovider {selector}"
        )
        report = _report(
            {
                "command": command,
                "argv": [*self._pytest_prefix(), selector],
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
            }
        )

        with self.assertRaisesRegex(ValueError, "tests root resolves outside"):
            execute_plan(self.vault, report)

    def test_fails_closed_when_workspace_python_is_missing(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            self.assertRaisesRegex(RuntimeError, "make dev-install"),
        ):
            _resolved_argv(Path(temp_dir), self._pytest_prefix())

    @staticmethod
    def _pytest_prefix() -> list[str]:
        return [
            ".venv/bin/python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
