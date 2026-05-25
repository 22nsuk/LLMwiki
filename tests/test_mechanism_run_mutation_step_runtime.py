from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.mechanism_run_common_runtime import (
    CommandSpec,
    ExperimentResolution,
    RunMechanismExperimentMutationError,
    RunMechanismExperimentUsageError,
)
from ops.scripts.mechanism_run_mutation_step_runtime import (
    MutationStepDependencies,
    execute_mutation_step,
)
from ops.scripts.runtime_context import RuntimeContext


def _context() -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.UTC)


def _resolution(*, include_mutation_command: bool = True) -> ExperimentResolution:
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
        mutation_command_spec=(
            CommandSpec("python tools/mutate.py", ["python", "tools/mutate.py"], 5400)
            if include_mutation_command
            else None
        ),
        check_command_spec=CommandSpec("python -c pass", ["python", "-c", "pass"], 5400),
        scope_freeze_path="runs/run-steps/scope-freeze.json",
        routing_report_paths=[],
        executor_report_paths=[],
    )


class MechanismRunMutationStepRuntimeTests(unittest.TestCase):
    def test_execute_mutation_step_requires_prepared_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, self.assertRaisesRegex(
            RunMechanismExperimentUsageError,
            "execution commands were not prepared",
        ):
            execute_mutation_step(
                Path(temp_dir),
                Path(temp_dir),
                run_id="run-steps",
                resolution=_resolution(include_mutation_command=False),
                dependencies=MutationStepDependencies(
                    command_argv=mock.Mock(),
                    run_command=mock.Mock(),
                    write_command_logs=mock.Mock(),
                    write_timeout_failure_artifact=mock.Mock(),
                    append_ledger_event=mock.Mock(),
                    write_experiment_telemetry=mock.Mock(),
                    sanitize_path_text=mock.Mock(),
                ),
            )

    def test_mechanism_run_mutation_step_records_timeout_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            dependencies = MutationStepDependencies(
                command_argv=mock.Mock(return_value=["python", "tools/mutate.py"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "python tools/mutate.py",
                        "argv": ["python", "tools/mutate.py"],
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
                        "runs/run-steps/mutation-command.stdout.txt",
                        "runs/run-steps/mutation-command.stderr.txt",
                    ]
                ),
                write_timeout_failure_artifact=mock.Mock(
                    return_value="runs/run-steps/mutation-command-timeout-failure.json"
                ),
                append_ledger_event=mock.Mock(),
                write_experiment_telemetry=mock.Mock(),
                sanitize_path_text=mock.Mock(
                    side_effect=lambda text, *, roots: text.replace(
                        f"{workspace.as_posix()}/",
                        "",
                    )
                ),
            )

            with self.assertRaisesRegex(
                RunMechanismExperimentMutationError,
                "mutation command timed out after 5400 seconds",
            ):
                execute_mutation_step(
                    vault,
                    workspace,
                    run_id="run-steps",
                    resolution=_resolution(),
                    dependencies=dependencies,
                )

        dependencies.write_timeout_failure_artifact.assert_called_once()
        self.assertEqual(
            dependencies.append_ledger_event.call_args.kwargs["decision"],
            "mutation_timeout",
        )
        self.assertIn(
            "runs/run-steps/mutation-command-timeout-failure.json",
            dependencies.append_ledger_event.call_args.kwargs["artifacts"],
        )
        self.assertEqual(
            dependencies.write_experiment_telemetry.call_args.kwargs["result"]["mutation_command"][
                "stdout"
            ],
            "stdout.txt",
        )

    def test_execute_mutation_step_returns_sanitized_success_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            dependencies = MutationStepDependencies(
                command_argv=mock.Mock(return_value=["python", "tools/mutate.py"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "python tools/mutate.py",
                        "argv": ["python", "tools/mutate.py"],
                        "returncode": 0,
                        "stdout": f"{workspace.as_posix()}/stdout.txt",
                        "stderr": f"{workspace.as_posix()}/stderr.txt",
                    }
                ),
                write_command_logs=mock.Mock(
                    return_value=[
                        "runs/run-steps/mutation-command.stdout.txt",
                        "runs/run-steps/mutation-command.stderr.txt",
                    ]
                ),
                write_timeout_failure_artifact=mock.Mock(),
                append_ledger_event=mock.Mock(),
                write_experiment_telemetry=mock.Mock(),
                sanitize_path_text=mock.Mock(
                    side_effect=lambda text, *, roots: text.replace(
                        f"{workspace.as_posix()}/",
                        "",
                    )
                ),
            )

            result = execute_mutation_step(
                vault,
                workspace,
                run_id="run-steps",
                resolution=_resolution(),
                dependencies=dependencies,
            )

        self.assertEqual(result.result["stdout"], "stdout.txt")
        self.assertEqual(result.result["stderr"], "stderr.txt")
        self.assertEqual(
            dependencies.append_ledger_event.call_args.kwargs["decision"],
            "candidate_ready_for_capture",
        )
        dependencies.write_timeout_failure_artifact.assert_not_called()
        dependencies.write_experiment_telemetry.assert_not_called()
