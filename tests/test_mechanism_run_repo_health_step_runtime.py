from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.mechanism_run_common_runtime import (
    CommandSpec,
    ExperimentResolution,
    RunMechanismExperimentUsageError,
)
from ops.scripts.mechanism_run_repo_health_step_runtime import (
    RepoHealthStepDependencies,
    repo_health_step,
)
from ops.scripts.runtime_context import RuntimeContext


def _context() -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.timezone.utc)


def _resolution(*, include_check_command: bool = True) -> ExperimentResolution:
    return ExperimentResolution(
        policy={},
        resolved_policy_path=Path("ops/policies/wiki-maintainer-policy.yaml"),
        policy_path_text="ops/policies/wiki-maintainer-policy.yaml",
        context=_context(),
        primary_targets=["ops/scripts/example.py"],
        supporting_targets=[],
        test_files=["tests/test_example.py"],
        proposal=None,
        proposal_source_report=None,
        log_summary="step coverage",
        mutation_command_spec=CommandSpec("python tools/mutate.py", ["python", "tools/mutate.py"], 5400),
        check_command_spec=(
            CommandSpec("python -m pytest -q", ["python", "-m", "pytest", "-q"], 5400)
            if include_check_command
            else None
        ),
        scope_freeze_path="runs/run-steps/scope-freeze.json",
        routing_report_paths=[],
        executor_report_paths=[],
    )


class MechanismRunRepoHealthStepRuntimeTests(unittest.TestCase):
    def test_repo_health_step_requires_prepared_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                RunMechanismExperimentUsageError,
                "execution commands were not prepared",
            ):
                repo_health_step(
                    Path(temp_dir),
                    Path(temp_dir),
                    run_id="run-steps",
                    resolution=_resolution(include_check_command=False),
                    baseline_file_digests={},
                    dependencies=RepoHealthStepDependencies(
                        command_argv=mock.Mock(),
                        run_command=mock.Mock(),
                        write_command_logs=mock.Mock(),
                        write_timeout_failure_artifact=mock.Mock(),
                        append_ledger_event=mock.Mock(),
                        write_changed_files_manifest=mock.Mock(),
                        write_behavior_delta_artifact=mock.Mock(),
                        sanitize_path_text=mock.Mock(),
                    ),
                )

    def test_repo_health_step_records_timeout_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            dependencies = RepoHealthStepDependencies(
                command_argv=mock.Mock(return_value=["python", "-m", "pytest", "-q"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "python -m pytest -q",
                        "argv": ["python", "-m", "pytest", "-q"],
                        "returncode": -15,
                        "stdout": f"{workspace.as_posix()}/stdout.txt",
                        "stderr": f"{workspace.as_posix()}/stderr.txt",
                        "timed_out": True,
                        "timeout_seconds": 5400,
                        "termination_reason": "timeout",
                    }
                ),
                write_command_logs=mock.Mock(
                    return_value=[
                        "runs/run-steps/repo-health.stdout.txt",
                        "runs/run-steps/repo-health.stderr.txt",
                    ]
                ),
                write_timeout_failure_artifact=mock.Mock(
                    return_value="runs/run-steps/repo-health-timeout-failure.json"
                ),
                append_ledger_event=mock.Mock(),
                write_changed_files_manifest=mock.Mock(
                    return_value="runs/run-steps/changed-files-manifest.json"
                ),
                write_behavior_delta_artifact=mock.Mock(
                    return_value="runs/run-steps/behavior-delta.json"
                ),
                sanitize_path_text=mock.Mock(
                    side_effect=lambda text, *, roots: text.replace(
                        f"{workspace.as_posix()}/",
                        "",
                    )
                ),
            )

            result = repo_health_step(
                vault,
                workspace,
                run_id="run-steps",
                resolution=_resolution(),
                baseline_file_digests={},
                dependencies=dependencies,
            )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.changed_files_manifest,
            "runs/run-steps/changed-files-manifest.json",
        )
        self.assertEqual(result.behavior_delta, "runs/run-steps/behavior-delta.json")
        self.assertEqual(
            dependencies.append_ledger_event.call_args.kwargs["decision"],
            "repo_health_timeout",
        )
        self.assertIn(
            "runs/run-steps/repo-health-timeout-failure.json",
            dependencies.append_ledger_event.call_args.kwargs["artifacts"],
        )

    def test_repo_health_step_returns_pass_result_without_timeout_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            dependencies = RepoHealthStepDependencies(
                command_argv=mock.Mock(return_value=["python", "-m", "pytest", "-q"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "python -m pytest -q",
                        "argv": ["python", "-m", "pytest", "-q"],
                        "returncode": 0,
                        "stdout": f"{workspace.as_posix()}/stdout.txt",
                        "stderr": f"{workspace.as_posix()}/stderr.txt",
                    }
                ),
                write_command_logs=mock.Mock(
                    return_value=[
                        "runs/run-steps/repo-health.stdout.txt",
                        "runs/run-steps/repo-health.stderr.txt",
                    ]
                ),
                write_timeout_failure_artifact=mock.Mock(),
                append_ledger_event=mock.Mock(),
                write_changed_files_manifest=mock.Mock(
                    return_value="runs/run-steps/changed-files-manifest.json"
                ),
                write_behavior_delta_artifact=mock.Mock(
                    return_value="runs/run-steps/behavior-delta.json"
                ),
                sanitize_path_text=mock.Mock(
                    side_effect=lambda text, *, roots: text.replace(
                        f"{workspace.as_posix()}/",
                        "",
                    )
                ),
            )

            result = repo_health_step(
                vault,
                workspace,
                run_id="run-steps",
                resolution=_resolution(),
                baseline_file_digests={},
                dependencies=dependencies,
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.result["stdout"], "stdout.txt")
        self.assertEqual(
            dependencies.append_ledger_event.call_args.kwargs["decision"],
            "repo_health_pass",
        )
        dependencies.write_timeout_failure_artifact.assert_not_called()
