from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from ops.scripts.command_runtime import TimedProcessResult
from ops.scripts.public_check_summary import (
    PublicCheckRequest,
    build_report,
    reusable_summary_diagnostics,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "public-check-summary.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 9, 9, 0, tzinfo=dt.timezone.utc),
    )


def seed_public_policy_file(vault: Path) -> None:
    policy_path = vault / "ops" / "scripts" / "public" / "public_surface_policy.py"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("PUBLIC_INCLUDE_PREFIXES = ()\n", encoding="utf-8")


def fake_runner(argv: Sequence[str], cwd: Path, timeout_seconds: int) -> TimedProcessResult:
    del cwd
    module = argv[2] if len(argv) > 2 else ""
    stdout = ""
    if module == "pytest":
        stdout = "217 passed, 5 skipped in 1.23s\n"
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
        timeout_seconds=timeout_seconds,
        termination_reason="completed",
    )


def failing_pytest_runner(argv: Sequence[str], cwd: Path, timeout_seconds: int) -> TimedProcessResult:
    del cwd
    module = argv[2] if len(argv) > 2 else ""
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=1 if module == "pytest" else 0,
        stdout="216 passed, 1 failed in 1.23s\n" if module == "pytest" else "",
        stderr="",
        timed_out=False,
        timeout_seconds=timeout_seconds,
        termination_reason="completed",
    )


class PublicCheckSummaryTests(unittest.TestCase):
    def test_public_check_summary_schema_passes_and_records_export_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(public_out),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            self.assertTrue(destination.exists())
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["public_check_status"], "pass")
            self.assertEqual(report["summary"]["negative_assertion_fail_count"], 0)
            self.assertEqual(report["summary"]["physical_repo_split_status"], "pass")
            self.assertEqual(report["summary"]["private_surface_history_absence_status"], "pass")
            self.assertEqual(report["summary"]["pytest_passed"], 217)
            self.assertEqual(report["summary"]["pytest_skipped"], 5)
            self.assertRegex(report["summary"]["export_root_fingerprint"], r"^[a-f0-9]{64}$")
            self.assertRegex(report["summary"]["public_surface_policy_sha256"], r"^[a-f0-9]{64}$")
            self.assertTrue(report["public_export"]["output_dir"].startswith("<tmp>/"))
            self.assertTrue(report["public_export"]["output_dir"].endswith(f"/{public_out.name}"))
            self.assertEqual(
                report["public_export_negative_assertions"]["excluded_prefix_absence"]["status"],
                "pass",
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["status"],
                "pass",
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["private_pattern_absence"]["status"],
                "pass",
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_fails_on_exported_local_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            (vault / "README.md").write_text(
                f"Do not export local path {vault.resolve()}.\n",
                encoding="utf-8",
            )

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["negative_assertion_fail_count"], 1)
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["status"],
                "fail",
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                ["README.md"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_policy_included_report_files_are_not_private_export_violations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            for rel_path in (
                "ops/reports/goal-worktree-guard.json",
                "ops/reports/release-workflow-order-guard.json",
                "ops/reports/workflow-dependency-planner.json",
            ):
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["negative_assertion_fail_count"], 0)
            self.assertEqual(
                report["public_export_negative_assertions"]["excluded_prefix_absence"]["violations"],
                [],
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["private_pattern_absence"]["violations"],
                [],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_fails_when_public_pytest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                ),
                context=fixed_context(),
                command_runner=failing_pytest_runner,
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["command_fail_count"], 1)
            self.assertEqual(report["summary"]["pytest_failed"], 1)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_reusable_summary_requires_current_source_tree_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            reusable = reusable_summary_diagnostics(vault, destination)
            self.assertTrue(reusable["reusable"])
            self.assertEqual(reusable["reason"], "current_passing_public_check_summary")

            (vault / "README.md").write_text("# Test\n\nChanged after public check.\n", encoding="utf-8")
            stale = reusable_summary_diagnostics(vault, destination)

            self.assertFalse(stale["reusable"])
            self.assertIn("source_tree_fingerprint", stale["reason"])
            self.assertNotEqual(
                stale["current_source_tree_fingerprint"],
                json.loads(destination.read_text(encoding="utf-8"))["source_tree_fingerprint"],
            )

    def test_relative_public_python_resolves_against_source_vault(self) -> None:
        captured_argv: list[list[str]] = []
        captured_cwd: list[Path] = []

        def recording_runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
        ) -> TimedProcessResult:
            captured_argv.append([str(item) for item in argv])
            captured_cwd.append(cwd)
            return fake_runner(argv, cwd, timeout_seconds)

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(public_out),
                    public_python=".venv/bin/python",
                ),
                context=fixed_context(),
                command_runner=recording_runner,
            )

            expected_python = str((vault / ".venv/bin/python").absolute())
            self.assertEqual(report["status"], "pass")
            self.assertEqual({argv[0] for argv in captured_argv}, {expected_python})
            self.assertEqual(set(captured_cwd), {public_out.resolve()})
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
