from __future__ import annotations

import datetime as dt
import json
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
    StructuralComplexityBudgetStepResult,
    repo_health_step,
)
from ops.scripts.runtime_context import RuntimeContext


def _context() -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.UTC)


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


def _structural_budget_pass() -> StructuralComplexityBudgetStepResult:
    return StructuralComplexityBudgetStepResult(
        report_path="runs/run-steps/structural-complexity-budget.json",
        status="pass",
    )


class MechanismRunRepoHealthStepRuntimeTests(unittest.TestCase):
    def test_repo_health_step_requires_prepared_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, self.assertRaisesRegex(
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
                    write_structural_complexity_budget_artifact=mock.Mock(),
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
                write_structural_complexity_budget_artifact=mock.Mock(
                    return_value=_structural_budget_pass()
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
            result.structural_complexity_budget,
            "runs/run-steps/structural-complexity-budget.json",
        )
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
                write_structural_complexity_budget_artifact=mock.Mock(
                    return_value=_structural_budget_pass()
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
        self.assertEqual(result.structural_complexity_budget_status, "pass")
        self.assertEqual(
            dependencies.append_ledger_event.call_args.kwargs["decision"],
            "repo_health_pass",
        )
        dependencies.write_timeout_failure_artifact.assert_not_called()

    def test_repo_health_step_blocks_promotion_on_structural_complexity_attention(self) -> None:
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
                        "stdout": "repo health ok\n",
                        "stderr": "",
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
                write_structural_complexity_budget_artifact=mock.Mock(
                    return_value=StructuralComplexityBudgetStepResult(
                        report_path="runs/run-steps/structural-complexity-budget.json",
                        status="attention",
                    )
                ),
                write_behavior_delta_artifact=mock.Mock(
                    return_value="runs/run-steps/behavior-delta.json"
                ),
                sanitize_path_text=mock.Mock(side_effect=lambda text, *, roots: text),
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
        self.assertEqual(result.structural_complexity_budget_status, "attention")
        self.assertEqual(
            dependencies.append_ledger_event.call_args.kwargs["decision"],
            "structural_complexity_non_regression",
        )
        self.assertIn(
            "runs/run-steps/structural-complexity-budget.json",
            dependencies.append_ledger_event.call_args.kwargs["artifacts"],
        )
        dependencies.write_timeout_failure_artifact.assert_not_called()

    def test_repo_health_step_copies_artifact_freshness_diagnostic_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            diagnostic = workspace / "tmp" / "artifact-freshness-report-check.json"
            diagnostic.parent.mkdir(parents=True)
            diagnostic.write_text('{"status":"fail","failures":["stale"]}\n', encoding="utf-8")
            dependencies = RepoHealthStepDependencies(
                command_argv=mock.Mock(return_value=["make", "check"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "make check",
                        "argv": ["make", "check"],
                        "returncode": 1,
                        "stdout": "tmp/artifact-freshness-report-check.json\n",
                        "stderr": "artifact freshness failed\n",
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
                write_structural_complexity_budget_artifact=mock.Mock(
                    return_value=_structural_budget_pass()
                ),
                write_behavior_delta_artifact=mock.Mock(
                    return_value="runs/run-steps/behavior-delta.json"
                ),
                sanitize_path_text=mock.Mock(side_effect=lambda text, *, roots: text),
            )

            result = repo_health_step(
                vault,
                workspace,
                run_id="run-steps",
                resolution=_resolution(),
                baseline_file_digests={},
                dependencies=dependencies,
            )

            copied = vault / "runs" / "run-steps" / "repo-health-artifact-freshness-report-check.json"
            self.assertFalse(result.passed)
            self.assertEqual(
                copied.read_text(encoding="utf-8"),
                '{"status":"fail","failures":["stale"]}\n',
            )
            self.assertIn(
                "runs/run-steps/repo-health-artifact-freshness-report-check.json",
                dependencies.append_ledger_event.call_args.kwargs["artifacts"],
            )

    def test_repo_health_step_compacts_passing_artifact_freshness_diagnostic_report(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            diagnostic = workspace / "tmp" / "artifact-freshness-report-check.json"
            diagnostic.parent.mkdir(parents=True)
            diagnostic.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/artifact-freshness-report.schema.json",
                        "artifact_kind": "artifact_freshness_report",
                        "generated_at": "2026-04-24T12:00:00Z",
                        "producer": "ops.scripts.artifact_freshness_runtime",
                        "source_command": "make artifact-freshness-check",
                        "source_revision": "abc",
                        "source_tree_fingerprint": "fingerprint",
                        "status": "pass",
                        "gate_effect": "none",
                        "recommended_next_action": "none",
                        "currentness": {"status": "current"},
                        "summary": {"artifact_count": 12},
                        "top_debt": [],
                        "top_debt_files": [],
                        "debt_queues": [],
                        "artifact_records": [{"path": "ops/reports/large.json"}],
                        "owner_surface": {"ops_reports": 1},
                    }
                ),
                encoding="utf-8",
            )
            dependencies = RepoHealthStepDependencies(
                command_argv=mock.Mock(return_value=["make", "check"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "make check",
                        "argv": ["make", "check"],
                        "returncode": 0,
                        "stdout": "artifact freshness passed\n",
                        "stderr": "",
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
                write_structural_complexity_budget_artifact=mock.Mock(
                    return_value=_structural_budget_pass()
                ),
                write_behavior_delta_artifact=mock.Mock(
                    return_value="runs/run-steps/behavior-delta.json"
                ),
                sanitize_path_text=mock.Mock(side_effect=lambda text, *, roots: text),
            )

            result = repo_health_step(
                vault,
                workspace,
                run_id="run-steps",
                resolution=_resolution(),
                baseline_file_digests={},
                dependencies=dependencies,
            )

            copied = vault / "runs" / "run-steps" / "repo-health-artifact-freshness-report-check.json"
            payload = json.loads(copied.read_text(encoding="utf-8"))
            self.assertTrue(result.passed)
            self.assertEqual(payload["preservation_mode"], "compact_summary")
            self.assertFalse(payload["full_scan_preserved"])
            self.assertEqual(payload["source_artifact_kind"], "artifact_freshness_report")
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["source_tree_fingerprint"], "fingerprint")
            self.assertEqual(payload["summary"], {"artifact_count": 12})
            self.assertEqual(payload["top_debt_files"], [])
            self.assertNotIn("artifact_records", payload)
            self.assertNotIn("owner_surface", payload)

    def test_repo_health_step_preserves_full_freshness_scan_when_gate_blocks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            diagnostic = workspace / "tmp" / "artifact-freshness-report-check.json"
            diagnostic.parent.mkdir(parents=True)
            original_payload = {
                "status": "attention",
                "gate_effect": "blocks_promotion",
                "top_debt_files": [{"path": "ops/reports/generated.json"}],
                "artifact_records": [{"path": "ops/reports/generated.json"}],
            }
            diagnostic.write_text(json.dumps(original_payload), encoding="utf-8")
            dependencies = RepoHealthStepDependencies(
                command_argv=mock.Mock(return_value=["make", "check"]),
                run_command=mock.Mock(
                    return_value={
                        "command": "make check",
                        "argv": ["make", "check"],
                        "returncode": 1,
                        "stdout": "artifact freshness attention\n",
                        "stderr": "artifact freshness blocked promotion\n",
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
                write_structural_complexity_budget_artifact=mock.Mock(
                    return_value=_structural_budget_pass()
                ),
                write_behavior_delta_artifact=mock.Mock(
                    return_value="runs/run-steps/behavior-delta.json"
                ),
                sanitize_path_text=mock.Mock(side_effect=lambda text, *, roots: text),
            )

            result = repo_health_step(
                vault,
                workspace,
                run_id="run-steps",
                resolution=_resolution(),
                baseline_file_digests={},
                dependencies=dependencies,
            )

            copied = vault / "runs" / "run-steps" / "repo-health-artifact-freshness-report-check.json"
            self.assertFalse(result.passed)
            self.assertEqual(
                json.loads(copied.read_text(encoding="utf-8")),
                original_payload,
            )
