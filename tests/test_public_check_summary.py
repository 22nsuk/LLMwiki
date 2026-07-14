from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

import ops.scripts.public.public_check_summary as public_check_summary_module
from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.public.public_check_summary import (
    PublicCheckRequest,
    _default_command_runner,
    _public_check_config_fingerprint,
    _public_export_negative_assertions,
    _public_pytest_summary_cache_path,
    _resolve_public_python,
    build_report,
    reusable_summary_diagnostics,
    write_report,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "public-check-summary.schema.json"
PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH = Path("ops/reports/test-execution-summary-public.json")


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 9, 9, 0, tzinfo=dt.UTC),
    )


def seed_public_policy_file(vault: Path) -> None:
    policy_path = vault / "ops" / "scripts" / "public" / "public_surface_policy.py"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("PUBLIC_INCLUDE_PREFIXES = ()\n", encoding="utf-8")


def write_public_pytest_summary(
    cwd: Path,
    *,
    passed: int,
    failed: int,
    errors: int,
    skipped: int,
) -> None:
    summary_path = cwd / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "counts": {
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "skipped": skipped,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def fake_runner(argv: Sequence[str], cwd: Path, timeout_seconds: int) -> TimedProcessResult:
    module = argv[2] if len(argv) > 2 else ""
    stdout = ""
    if module == "ops.scripts.test_execution_summary":
        write_public_pytest_summary(cwd, passed=217, failed=0, errors=0, skipped=5)
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
    module = argv[2] if len(argv) > 2 else ""
    if module == "ops.scripts.test_execution_summary":
        write_public_pytest_summary(cwd, passed=216, failed=1, errors=0, skipped=0)
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=1 if module == "ops.scripts.test_execution_summary" else 0,
        stdout="",
        stderr="",
        timed_out=False,
        timeout_seconds=timeout_seconds,
        termination_reason="completed",
    )


def timeout_pytest_runner(argv: Sequence[str], cwd: Path, timeout_seconds: int) -> TimedProcessResult:
    module = argv[2] if len(argv) > 2 else ""
    timed_out = module == "ops.scripts.test_execution_summary"
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=-9 if timed_out else 0,
        stdout="",
        stderr="",
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
        termination_reason="execution_timeout" if timed_out else "completed",
        signal_sent="sigkill" if timed_out else "none",
        final_state_observed="drain_after_kill" if timed_out else "communicate",
        heartbeat_count=3 if timed_out else 0,
        heartbeat_interval_seconds=10 if timed_out else 0,
        quiet_seconds=30 if timed_out else 0,
        observation_mode="process_heartbeat" if timed_out else "communicate",
    )


class PublicCheckSummaryTests(unittest.TestCase):
    def _build_report_with_exported_text(
        self,
        temp_dir: str,
        rel_path: str,
        text: str,
    ) -> dict[str, Any]:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        seed_public_policy_file(vault)
        target = vault / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return build_report(
            vault,
            PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="python",
                pytest_flags="-q",
            ),
            context=fixed_context(),
            command_runner=fake_runner,
        )

    def test_default_runner_exports_public_python_for_nested_make_entrypoints(self) -> None:
        captured_env: dict[str, str] = {}

        def fake_run_with_timeout(
            argv: Sequence[str],
            *,
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str] | None = None,
            heartbeat_interval_seconds: int | None = None,
            heartbeat_callback: object | None = None,
        ) -> TimedProcessResult:
            captured_env.update(dict(env or {}))
            return TimedProcessResult(
                args=[str(item) for item in argv],
                returncode=0,
                stdout="",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="completed",
                heartbeat_interval_seconds=heartbeat_interval_seconds or 0,
            )

        with patch("ops.scripts.public.public_check_summary.run_with_timeout", fake_run_with_timeout):
            _default_command_runner(
                ["python", "-m", "pytest"],
                Path(),
                30,
                public_python="/workspace/.venv/bin/python",
                heartbeat_interval_seconds=0,
            )

        self.assertEqual(captured_env["PYTHON"], "/workspace/.venv/bin/python")
        self.assertEqual(captured_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")

    def test_build_report_default_runner_exports_resolved_public_python_to_all_commands(self) -> None:
        captured_envs: list[dict[str, str]] = []

        def fake_run_with_timeout(
            argv: Sequence[str],
            *,
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str] | None = None,
            heartbeat_interval_seconds: int | None = None,
            heartbeat_callback: object | None = None,
        ) -> TimedProcessResult:
            captured_envs.append(dict(env or {}))
            module = argv[2] if len(argv) > 2 else ""
            if module == "ops.scripts.test_execution_summary":
                write_public_pytest_summary(cwd, passed=3, failed=0, errors=0, skipped=0)
            return TimedProcessResult(
                args=[str(item) for item in argv],
                returncode=0,
                stdout="",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="completed",
                heartbeat_interval_seconds=heartbeat_interval_seconds or 0,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            with patch("ops.scripts.public.public_check_summary.run_with_timeout", fake_run_with_timeout):
                report = build_report(
                    vault,
                    PublicCheckRequest(
                        public_out=str(Path(temp_dir) / "public"),
                        public_python=".venv/bin/python",
                    ),
                    context=fixed_context(),
                )

        expected_python = str((vault / ".venv/bin/python").absolute())
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(captured_envs), 3)
        self.assertEqual({env["PYTHON"] for env in captured_envs}, {expected_python})
        self.assertEqual({env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] for env in captured_envs}, {"1"})

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
            self.assertEqual(report["summary"]["timeout_command_count"], 0)
            self.assertEqual(report["summary"]["max_command_heartbeat_count"], 0)
            self.assertEqual(report["summary"]["max_command_quiet_seconds"], 0)
            self.assertEqual(report["summary"]["public_pytest_heartbeat_count"], 0)
            self.assertEqual(report["summary"]["public_pytest_quiet_seconds"], 0)
            self.assertEqual(report["summary"]["public_pytest_termination_reason"], "completed")
            self.assertEqual(report["summary"]["public_pytest_signal_sent"], "none")
            self.assertEqual(report["summary"]["public_pytest_final_state_observed"], "unknown")
            self.assertEqual(
                {command["observation_mode"] for command in report["commands"]},
                {"communicate"},
            )
            self.assertEqual(
                {command["heartbeat_interval_seconds"] for command in report["commands"]},
                {0},
            )
            self.assertIn("ops.scripts.test_execution_summary", report["commands"][-1]["command"])
            self.assertIn("--reuse-if-current", report["commands"][-1]["command"])
            self.assertEqual({command["signal_sent"] for command in report["commands"]}, {"none"})
            self.assertEqual(
                {command["final_state_observed"] for command in report["commands"]},
                {"unknown"},
            )
            self.assertRegex(report["summary"]["export_root_fingerprint"], r"^[a-f0-9]{64}$")
            self.assertRegex(report["summary"]["public_surface_policy_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(
                report["summary"]["public_check_config_fingerprint"],
                r"^[a-f0-9]{64}$",
            )
            self.assertEqual(
                report["summary"]["public_check_config_fingerprint"],
                report["input_fingerprints"]["public_check_config"],
            )
            self.assertEqual(report["source_command"], "python -m ops.scripts.public_check_summary --vault .")
            self.assertTrue(report["public_export"]["output_dir"].startswith("<tmp>/"))
            self.assertTrue(report["public_export"]["output_dir"].endswith(f"/{public_out.name}"))
            self.assertTrue(_public_pytest_summary_cache_path().exists())
            self.assertFalse((public_out / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH).exists())
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
            self.assertEqual(
                [
                    cause["id"]
                    for cause in report["failure_causes"]
                    if cause["kind"] == "negative_assertion_failure"
                ],
                ["negative_assertion:local_path_absence"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_fails_on_exported_foreign_local_path_leak(self) -> None:
        for leaked_path in (
            "/workspace/LLMwiki/repo",
            "/Users/alice/work/repo",
            "/private/var/folders/ab/tmp/repo",
            "workspace:/home/alice/work/repo",
        ):
            with self.subTest(leaked_path=leaked_path), tempfile.TemporaryDirectory() as temp_dir:
                report = self._build_report_with_exported_text(
                    temp_dir,
                    "README.md",
                    f"Do not export local path {leaked_path}.\n",
                )

                self.assertEqual(report["status"], "fail")
                self.assertEqual(
                    report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                    ["README.md"],
                )

    def test_public_check_summary_allows_exported_api_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build_report_with_exported_text(
                temp_dir,
                "README.md",
                "GET /users/{id}\n",
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                [],
            )

    def test_public_check_summary_rejects_foreign_paths_in_unregistered_source_files(
        self,
    ) -> None:
        for rel_path in (
            "ops/scripts/leak.py",
            "tests/leak.py",
            "tools/leak.py",
        ):
            with self.subTest(rel_path=rel_path), tempfile.TemporaryDirectory() as temp_dir:
                report = self._build_report_with_exported_text(
                    temp_dir,
                    rel_path,
                    'DEV_ROOT = "/Users/alice/work/repo"\n',
                )

                self.assertEqual(report["status"], "fail")
                self.assertEqual(
                    report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                    [rel_path],
                )

    def test_public_check_summary_allows_registered_source_path_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/test_public_check_summary.py",
                'FIXTURE_ROOT = "/workspace/example"\n',
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                [],
            )

    def test_public_check_summary_allows_registered_fixture_containing_current_vault(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_vault = Path("/", "workspace", "LLMwiki")
            public_out = Path(temp_dir) / "public"
            fixture_path = public_out / "tests" / "test_public_check_summary.py"
            fixture_path.parent.mkdir(parents=True)
            fixture_path.write_text(
                f'FIXTURE_ROOT = "{source_vault}/repo"\n',
                encoding="utf-8",
            )
            assertions = _public_export_negative_assertions(
                public_out,
                {},
                [{"path": "tests/test_public_check_summary.py"}],
                source_vault=source_vault,
            )

            self.assertEqual(
                assertions["local_path_absence"]["violations"],
                [],
            )

    def test_public_check_summary_rejects_unregistered_path_beside_allowed_fixture(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            allowed_fixture = "/" + "workspace/example"
            unexpected_path = "/" + "Users/real-user/private-repo"
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/test_public_check_summary.py",
                f'FIXTURE_ROOT = "{allowed_fixture}"\n'
                f'DEV_ROOT = "{unexpected_path}"\n',
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                ["tests/test_public_check_summary.py"],
            )

    def test_public_check_summary_rejects_current_vault_in_unregistered_source_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_vault = (Path(temp_dir) / "vault").resolve()
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/leak.py",
                f'DEV_ROOT = "{source_vault}/repo"\n',
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"]["violations"],
                ["tests/leak.py"],
            )

    def test_generated_report_files_are_excluded_without_private_export_violations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            for rel_path in (
                "ops/operator/operator-release-summary.json",
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
            self.assertEqual(len(report["failure_causes"]), 1)
            cause = report["failure_causes"][0]
            self.assertEqual(cause["kind"], "command_failure")
            self.assertEqual(cause["id"], "command:pytest_public")
            self.assertEqual(cause["command_id"], "pytest_public")
            self.assertEqual(cause["returncode"], 1)
            self.assertEqual(cause["pytest_counts"]["failed"], 1)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_cli_prints_compact_failure_summary(self) -> None:
        fake_report = {
            "status": "fail",
            "summary": {
                "public_check_status": "fail",
                "command_fail_count": 1,
                "negative_assertion_fail_count": 0,
            },
            "failure_causes": [
                {
                    "severity": "error",
                    "kind": "command_failure",
                    "id": "command:pytest_public",
                    "message": "public check command pytest_public failed",
                    "command_id": "pytest_public",
                    "status": "fail",
                    "returncode": 1,
                    "timed_out": False,
                    "termination_reason": "completed",
                }
            ],
        }

        def fake_write_report(vault: Path, report: dict[str, object], out_path: str) -> Path:
            destination = vault / out_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report), encoding="utf-8")
            return destination

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()

            with (
                patch.object(public_check_summary_module, "build_report", return_value=fake_report),
                patch.object(
                    public_check_summary_module,
                    "write_report",
                    side_effect=fake_write_report,
                ),
            ):
                completed = invoke_cli_main(
                    public_check_summary_module.main,
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "tmp/public-check-summary.candidate.json",
                    ],
                    cwd=launcher,
                )

        stdout_lines = completed.stdout.splitlines()
        self.assertEqual(stdout_lines[0], "tmp/public-check-summary.candidate.json")
        payload = json.loads("\n".join(stdout_lines[1:]))
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["failure_causes"][0]["id"], "command:pytest_public")

    def test_public_check_summary_exposes_public_pytest_timeout_cleanup_diagnostics(self) -> None:
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
                    heartbeat_interval_seconds=10,
                    timeout_seconds=30,
                ),
                context=fixed_context(),
                command_runner=timeout_pytest_runner,
            )

            pytest_command = report["commands"][-1]
            self.assertEqual(report["status"], "timeout")
            self.assertEqual(report["summary"]["public_check_status"], "timeout")
            self.assertEqual(report["summary"]["command_fail_count"], 1)
            self.assertEqual(report["summary"]["timeout_command_count"], 1)
            self.assertEqual(report["summary"]["max_command_heartbeat_count"], 3)
            self.assertEqual(report["summary"]["max_command_quiet_seconds"], 30)
            self.assertEqual(report["summary"]["public_pytest_heartbeat_count"], 3)
            self.assertEqual(report["summary"]["public_pytest_quiet_seconds"], 30)
            self.assertEqual(report["summary"]["public_pytest_termination_reason"], "execution_timeout")
            self.assertEqual(report["summary"]["public_pytest_signal_sent"], "sigkill")
            self.assertEqual(report["summary"]["public_pytest_final_state_observed"], "drain_after_kill")
            self.assertTrue(pytest_command["timed_out"])
            self.assertEqual(pytest_command["signal_sent"], "sigkill")
            self.assertEqual(pytest_command["final_state_observed"], "drain_after_kill")
            self.assertEqual(pytest_command["heartbeat_count"], 3)
            self.assertEqual(pytest_command["quiet_seconds"], 30)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_reuses_external_public_pytest_cache_without_exporting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache" / "test-execution-summary-public.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"counts": {"passed": 9, "failed": 0, "errors": 0, "skipped": 1}}),
                encoding="utf-8",
            )
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            def reuse_only_runner(
                argv: Sequence[str],
                cwd: Path,
                timeout_seconds: int,
            ) -> TimedProcessResult:
                module = argv[2] if len(argv) > 2 else ""
                if module == "ops.scripts.test_execution_summary":
                    self.assertIn("--reuse-if-current", argv)
                    self.assertIn("--reuse-from", argv)
                    self.assertIn(cache_path.as_posix(), argv)
                    write_public_pytest_summary(cwd, passed=9, failed=0, errors=0, skipped=1)
                return TimedProcessResult(
                    args=[str(item) for item in argv],
                    returncode=0,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    timeout_seconds=timeout_seconds,
                    termination_reason="completed",
                )

            with patch(
                "ops.scripts.public.public_check_summary._public_pytest_summary_cache_path",
                return_value=cache_path,
            ):
                report = build_report(
                    vault,
                    PublicCheckRequest(
                        public_out=str(public_out),
                        public_python="python",
                    ),
                    context=fixed_context(),
                    command_runner=reuse_only_runner,
                )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["pytest_passed"], 9)
            self.assertEqual(report["summary"]["pytest_skipped"], 1)
            self.assertFalse((public_out / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH).exists())

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

    def test_reusable_summary_requires_matching_public_check_config_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            original_request = PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="/home/alice/.venv/bin/python",
                ruff_targets="ops/scripts tests",
                mypy_targets="ops/scripts",
                pytest_mark_expr="public",
                pytest_flags="-q",
                timeout_seconds=90,
                heartbeat_interval_seconds=10,
            )

            report = build_report(
                vault,
                original_request,
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            matching = reusable_summary_diagnostics(vault, destination, original_request)
            self.assertTrue(matching["reusable"])
            self.assertEqual(
                matching["public_check_config_fingerprint"],
                report["input_fingerprints"]["public_check_config"],
            )

            mismatched_python = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="/home/bob/.venv/bin/python",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_python["reusable"])
            self.assertIn("public_check_config", mismatched_python["reason"])
            self.assertNotEqual(
                mismatched_python["expected_public_check_config_fingerprint"],
                mismatched_python["observed_public_check_config_fingerprint"],
            )

            mismatched_public_out = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out="tmp/public",
                    public_python="/home/alice/.venv/bin/python",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_public_out["reusable"])
            self.assertIn("public_check_config", mismatched_public_out["reason"])

            mismatched_pytest = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="/home/alice/.venv/bin/python",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_pytest["reusable"])
            self.assertIn("public_check_config", mismatched_pytest["reason"])

            mismatched_ruff = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="/home/alice/.venv/bin/python",
                    ruff_targets="ops/scripts",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_ruff["reusable"])
            self.assertIn("public_check_config", mismatched_ruff["reason"])

    def test_public_check_config_fingerprint_excludes_internal_pytest_cache_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            request = PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="python",
                pytest_flags="-q",
            )

            with patch(
                "ops.scripts.public.public_check_summary._public_pytest_summary_cache_path",
                return_value=Path(temp_dir) / "cache-a" / "test-execution-summary-public.json",
            ):
                left = _public_check_config_fingerprint(vault, request)

            with patch(
                "ops.scripts.public.public_check_summary._public_pytest_summary_cache_path",
                return_value=Path(temp_dir) / "cache-b" / "test-execution-summary-public.json",
            ):
                right = _public_check_config_fingerprint(vault, request)

            self.assertEqual(left, right)

    def test_cli_reuse_only_rejects_mismatched_public_check_config(self) -> None:
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
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = public_check_summary_module.main(
                    [
                        "--vault",
                        str(vault),
                        "--reuse-only",
                        "--reuse-from",
                        str(destination),
                        "--public-out",
                        str(public_out),
                        "--public-python",
                        "python",
                        "--pytest-mark-expr",
                        "",
                        "--pytest-flags=-q",
                    ]
                )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["summary_mode"], "executed")
            self.assertIn("public_check_config", payload["reuse_diagnostics"]["reason"])

    def test_exact_current_cli_check_does_not_rewrite_canonical_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"
            request = PublicCheckRequest(
                public_out=str(public_out), public_python="python", pytest_flags="-q"
            )
            report = build_report(
                vault, request, context=fixed_context(), command_runner=fake_runner
            )
            destination = write_report(vault, report)
            before_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
            before_mtime_ns = destination.stat().st_mtime_ns

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = public_check_summary_module.main(
                    [
                        "--vault", str(vault),
                        "--reuse-only", "--reuse-from", str(destination),
                        "--public-out", str(public_out),
                        "--public-python", "python",
                        "--pytest-flags=-q",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["summary_mode"], "reused")
            self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(), before_sha256)
            self.assertEqual(destination.stat().st_mtime_ns, before_mtime_ns)

    def test_default_then_full_execution_preserves_both_canonical_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            def execute(mode: str, selector: str, out_path: str) -> Path:
                report = build_report(
                    vault,
                    PublicCheckRequest(
                        mode=mode,
                        public_out=str(public_out),
                        public_python="python",
                        pytest_mark_expr=selector,
                    ),
                    context=fixed_context(),
                    command_runner=fake_runner,
                )
                return write_report(vault, report, out_path)

            default_path = execute(
                "default", "public", "ops/reports/public-check-summary.json"
            )
            default_sha256 = hashlib.sha256(default_path.read_bytes()).hexdigest()
            full_path = execute(
                "full", "", "ops/reports/public-check-summary-full.json"
            )

            self.assertTrue(default_path.is_file())
            self.assertTrue(full_path.is_file())
            self.assertEqual(hashlib.sha256(default_path.read_bytes()).hexdigest(), default_sha256)
            self.assertEqual(
                json.loads(full_path.read_text(encoding="utf-8"))["source_command"],
                "python -m ops.scripts.public_check_summary --vault . --mode full",
            )

    def test_cli_mode_defaults_make_full_selectorless(self) -> None:
        default_args = public_check_summary_module.parse_args([])
        full_args = public_check_summary_module.parse_args(["--mode", "full"])
        explicit_empty = public_check_summary_module.parse_args(
            ["--mode", "full", "--pytest-mark-expr", ""]
        )

        self.assertEqual(default_args.pytest_mark_expr, "public")
        self.assertEqual(full_args.pytest_mark_expr, "")
        self.assertEqual(explicit_empty.pytest_mark_expr, "")
        with self.assertRaises(SystemExit):
            public_check_summary_module.parse_args(
                ["--mode", "full", "--pytest-mark-expr", "public"]
            )

    def test_programmatic_full_mode_is_selectorless_and_rejects_marker_filters(self) -> None:
        request = PublicCheckRequest(mode="full")

        command, _summary_path = public_check_summary_module._pytest_public_summary_command(
            public_python="python",
            request=request,
            reuse_from=Path("ops/reports/test-execution-summary-public.json"),
        )

        self.assertEqual(request.pytest_mark_expr, "")
        self.assertEqual(command[-3:], ["python", "-m", "pytest"])
        self.assertNotIn("public", command)
        with self.assertRaisesRegex(
            ValueError, "full mode requires an empty pytest marker expression"
        ):
            PublicCheckRequest(mode="full", pytest_mark_expr="public")

    def test_cross_mode_reuse_is_rejected_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"
            requests = {
                "default": PublicCheckRequest(
                    mode="default", public_out=str(public_out), public_python="python"
                ),
                "full": PublicCheckRequest(
                    mode="full",
                    public_out=str(public_out),
                    public_python="python",
                    pytest_mark_expr="",
                ),
            }
            paths = {}
            for mode, request in requests.items():
                report = build_report(
                    vault, request, context=fixed_context(), command_runner=fake_runner
                )
                suffix = "-full" if mode == "full" else ""
                paths[mode] = write_report(
                    vault, report, f"ops/reports/public-check-summary{suffix}.json"
                )

            for expected_mode, artifact_mode in (("default", "full"), ("full", "default")):
                diagnostics = reusable_summary_diagnostics(
                    vault, paths[artifact_mode], requests[expected_mode]
                )
                self.assertFalse(diagnostics["reusable"])
                self.assertIn("source_command", diagnostics["reason"])
                self.assertIn("public_check_config", diagnostics["reason"])

    def test_script_output_surfaces_refresh_does_not_stale_public_summary_without_source_drift(self) -> None:
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
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            script_output_surfaces = vault / "ops" / "script-output-surfaces.json"
            script_output_surfaces.parent.mkdir(parents=True, exist_ok=True)
            script_output_surfaces.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/script-output-surfaces.schema.json",
                        "artifact_kind": "script_output_surfaces",
                        "producer": "ops.scripts.script_output_surfaces",
                        "source_tree_scope": {
                            "mode": "include_prefixes",
                            "include_prefixes": ["ops/scripts"]
                        },
                        "version": 1,
                        "description": "test fixture",
                        "classification_values": ["repo_artifact"],
                        "surfaces": []
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            reusable = reusable_summary_diagnostics(vault, destination)

            self.assertTrue(reusable["reusable"])
            self.assertEqual(reusable["reason"], "current_passing_public_check_summary")

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

    def test_unresolved_home_public_python_preserves_previous_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            with patch.object(Path, "expanduser", side_effect=RuntimeError("home unavailable")):
                resolved = _resolve_public_python(vault, "~/bin/python")

            self.assertEqual(resolved, str((vault / "~/bin/python").absolute()))


if __name__ == "__main__":
    unittest.main()
