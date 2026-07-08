from __future__ import annotations

import datetime as dt
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.core import filesystem_runtime
from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.promotion_decision_registry_runtime import (
    attach_decision_contract,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.workspace_python_identity_runtime import (
    load_workspace_python_identity,
)
from ops.scripts.mechanism import (
    mechanism_run_promotion_runtime,
    mechanism_run_workspace_runtime,
)
from ops.scripts.mechanism.failure_taxonomy_runtime import (
    GENERATED_EVIDENCE_SETTLE_REQUIRED,
)
from ops.scripts.mechanism.mechanism_run_candidate_snapshot_runtime import (
    write_candidate_changed_files_snapshot,
)
from ops.scripts.mechanism.mechanism_run_promotion_runtime import _finalize_step
from ops.scripts.mechanism.mechanism_run_repo_health_step_runtime import (
    StructuralComplexityBudgetStepResult,
)
from ops.scripts.mechanism.mechanism_run_scaffold_resolution_runtime import (
    ExperimentInputRequest,
    _resolve_experiment_inputs,
)
from ops.scripts.mechanism.mechanism_run_workspace_runtime import (
    _apply_or_discard_workspace_changes,
    _execute_mutation_step,
    _prepare_workspace_copy,
    _repo_health_step,
    _run_command,
    _snapshot_repo_file_digests,
    _write_changed_files_manifest,
)
from ops.scripts.mechanism.run_mechanism_experiment_runtime import (
    RunMechanismExperimentMutationError,
    RunMechanismExperimentUsageError,
    _mechanism_temp_dir_parent,
)
from tests.minimal_vault_runtime import set_policy_value
from tests.run_mechanism_experiment_test_utils import seed_wrapper_vault


def _expected_timeout_summary(
    *,
    timed_out: bool,
    timeout_seconds: int,
    termination_reason: str,
) -> dict[str, object]:
    return {
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "termination_reason": termination_reason,
        "launch_succeeded": True,
        "signal_sent": "none",
        "final_state_observed": "",
        "stdout_received": False,
        "stderr_received": False,
    }


def seed_changed_files_manifest_schema(vault: Path) -> None:
    schema_source = Path(__file__).resolve().parents[1] / "ops" / "schemas" / "changed-files-manifest.schema.json"
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
        schema_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


class RunMechanismExperimentStepTests(unittest.TestCase):
    def test_mechanism_temp_dir_parent_prefers_linux_tmp_when_default_temp_is_wsl_mount(
        self,
    ) -> None:
        with mock.patch(
            "ops.scripts.mechanism.run_mechanism_experiment_runtime.tempfile.gettempdir",
            return_value="/mnt/c/Users/ADMINI~1/AppData/Local/Temp",
        ):
            self.assertEqual(_mechanism_temp_dir_parent(), "/tmp")

    def test_mechanism_temp_dir_parent_keeps_native_linux_tempdir(self) -> None:
        with mock.patch(
            "ops.scripts.mechanism.run_mechanism_experiment_runtime.tempfile.gettempdir",
            return_value="/tmp",
        ):
            self.assertIsNone(_mechanism_temp_dir_parent())

    def test_prepare_workspace_copy_reports_actual_copied_file_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace_root = Path(temp_dir) / "workspace-root"
            target_dir = vault / "ops" / "scripts"
            target_dir.mkdir(parents=True)
            (target_dir / "first.py").write_text("FIRST = True\n", encoding="utf-8")
            (target_dir / "second.py").write_text("SECOND = True\n", encoding="utf-8")

            def partial_copytree(source: Path, destination: Path, **_: object) -> None:
                copied_target_dir = destination / "ops" / "scripts"
                copied_target_dir.mkdir(parents=True)
                (copied_target_dir / "first.py").write_text(
                    (source / "ops" / "scripts" / "first.py").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )

            with mock.patch.object(
                mechanism_run_workspace_runtime.shutil,
                "copytree",
                side_effect=partial_copytree,
            ):
                result = _prepare_workspace_copy(
                    vault,
                    run_id="run-copy-count",
                    workspace_root=workspace_root.as_posix(),
                )

            self.assertEqual(result.telemetry["mode"], "full_copy")
            self.assertEqual(result.telemetry["baseline_file_count"], 2)
            # Partial copytree leaves one tracked file; .venv/.llmwiki shim surfaces are ignored.
            self.assertEqual(result.telemetry["copied_file_count"], 1)

    def test_prepare_workspace_copy_provisions_python_shim_preserving_artifact_venv_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace_root = Path(temp_dir) / "workspace-root"
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "ops" / "scripts" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
            (vault / ".venv" / "bin").mkdir(parents=True)
            base_python = Path(temp_dir) / "base-python"
            base_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            base_python.chmod(0o755)
            artifact_python = vault / ".venv" / "bin" / "python"
            try:
                artifact_python.symlink_to(base_python)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            result = _prepare_workspace_copy(
                vault,
                run_id="run-venv-link",
                workspace_root=workspace_root.as_posix(),
            )

            workspace_venv = result.workspace_vault / ".venv"
            workspace_python = workspace_venv / "bin" / "python"
            self.assertFalse(workspace_venv.is_symlink())
            self.assertTrue(workspace_python.is_file())
            expected_shim = f"#!/bin/sh\nexec {shlex.quote(str(artifact_python))} \"$@\"\n"
            self.assertEqual(workspace_python.read_text(encoding="utf-8"), expected_shim)
            self.assertNotIn(str(base_python), expected_shim)
            identity = load_workspace_python_identity(result.workspace_vault)
            self.assertIsNotNone(identity)
            assert identity is not None
            self.assertEqual(identity.source_realpath, str(base_python.resolve()))
            self.assertNotIn(".venv/bin/python", result.baseline_file_digests)

    def test_prepare_workspace_copy_supports_sparse_manifest_copied_universe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace_root = Path(temp_dir) / "workspace-root"
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "tests").mkdir()
            (vault / "tools").mkdir()
            (vault / "raw").mkdir()
            (vault / "ops" / "scripts" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
            (vault / "tests" / "test_example.py").write_text("def test_ok(): pass\n", encoding="utf-8")
            (vault / "tools" / "helper.py").write_text("print('helper')\n", encoding="utf-8")
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            (vault / "raw" / "source.pdf").write_text("raw\n", encoding="utf-8")

            result = _prepare_workspace_copy(
                vault,
                run_id="run-sparse",
                workspace_root=workspace_root.as_posix(),
                mode="sparse_manifest",
                allowed_apply_roots=["ops/"],
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                declared_dependencies=["tools/"],
            )

            workspace = result.workspace_vault
            self.assertEqual(result.telemetry["mode"], "sparse_manifest")
            self.assertEqual(result.telemetry["diff_model"], "copied_universe")
            self.assertLess(
                result.telemetry["copied_file_count"],
                result.telemetry["baseline_file_count"],
            )
            self.assertEqual(
                result.telemetry["diff_universe_file_count"],
                result.telemetry["copied_file_count"],
            )
            self.assertTrue((workspace / "ops" / "scripts" / "example.py").exists())
            self.assertTrue((workspace / "tests" / "test_example.py").exists())
            self.assertTrue((workspace / "tools" / "helper.py").exists())
            self.assertFalse((workspace / "README.md").exists())

    def test_resolve_experiment_inputs_dedupes_targets_and_prepares_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            resolution = _resolve_experiment_inputs(
                ExperimentInputRequest(
                    vault=vault.resolve(),
                    run_id="run-steps",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py", "ops/scripts/example.py"],
                    supporting_targets=["tests/test_example.py", "tests/test_example.py"],
                    test_files=["tests/test_example.py", "tests/test_example.py"],
                    log_summary=None,
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('ok')\"",
                    proposal_id=None,
                    proposal_report_path=None,
                    scaffold_only=False,
                )
            )

            self.assertEqual(resolution.primary_targets, ["ops/scripts/example.py"])
            self.assertEqual(resolution.supporting_targets, ["tests/test_example.py"])
            self.assertEqual(resolution.test_files, ["tests/test_example.py"])
            self.assertIsNotNone(resolution.mutation_command_spec)
            self.assertIsNotNone(resolution.check_command_spec)
            self.assertEqual(resolution.mutation_command_spec.timeout_seconds, 5400)
            self.assertEqual(resolution.check_command_spec.timeout_seconds, 5400)

    def test_resolve_experiment_inputs_defaults_full_workspace_check_to_make_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            resolution = _resolve_experiment_inputs(
                ExperimentInputRequest(
                    vault=vault.resolve(),
                    run_id="run-steps-full-default-check",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary=None,
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=None,
                    proposal_id=None,
                    proposal_report_path=None,
                    scaffold_only=False,
                )
            )

            self.assertIsNotNone(resolution.check_command_spec)
            self.assertEqual(Path(resolution.check_command_spec.argv[0]).name, "make")
            self.assertEqual(
                resolution.check_command_spec.argv[1:],
                [f"PYTHON={sys.executable}", "check"],
            )

    def test_resolve_experiment_inputs_keeps_sparse_default_check_focused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            set_policy_value(
                vault,
                ("auto_improve_policy", "workspace_preparation"),
                {"mode": "sparse_manifest", "declared_dependencies": ["tools/"]},
            )

            resolution = _resolve_experiment_inputs(
                ExperimentInputRequest(
                    vault=vault.resolve(),
                    run_id="run-steps-sparse-default-check",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_example.py"],
                    log_summary=None,
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=None,
                    proposal_id=None,
                    proposal_report_path=None,
                    scaffold_only=False,
                )
            )

            self.assertIsNotNone(resolution.check_command_spec)
            self.assertEqual(
                resolution.check_command_spec.argv,
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "tests/test_example.py",
                ],
            )

    def test_run_command_records_timeout_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def fake_run_with_timeout(
                argv: list[str],
                *,
                cwd: Path,
                timeout_seconds: int,
            ) -> TimedProcessResult:
                self.assertEqual(argv, [sys.executable, "-c", "print('slow')"])
                self.assertEqual(cwd, root)
                self.assertEqual(timeout_seconds, 7)
                return TimedProcessResult(
                    args=argv,
                    returncode=-15,
                    stdout="",
                    stderr="timed out\n",
                    timed_out=True,
                    timeout_seconds=timeout_seconds,
                    termination_reason="timeout",
                )

            with mock.patch(
                "ops.scripts.mechanism.mechanism_run_workspace_runtime.run_with_timeout",
                side_effect=fake_run_with_timeout,
            ):
                result = _run_command(
                    f"{sys.executable} -c \"print('slow')\"",
                    cwd=root,
                    timeout_seconds=7,
                )

            self.assertEqual(result["returncode"], -15)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 7)
            self.assertEqual(result["termination_reason"], "timeout")

    def test_resolve_experiment_inputs_rejects_missing_test_file_early(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(RunMechanismExperimentUsageError, "missing target: tests/test_typo.py"):
                _resolve_experiment_inputs(
                    vault.resolve(),
                    run_id="run-steps-missing-test",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=[],
                    test_files=["tests/test_typo.py"],
                    log_summary="step coverage",
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command=f"{sys.executable} -c \"print('ok')\"",
                    proposal_id=None,
                    proposal_report_path=None,
                    scaffold_only=False,
                )

    def test_repo_health_step_returns_blocked_state_on_nonzero_returncode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            resolution = _resolve_experiment_inputs(
                vault.resolve(),
                run_id="run-steps",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                log_summary="step coverage",
                mutation_command=f"{sys.executable} tools/mutate_success.py",
                check_command=f"{sys.executable} -c \"print('ok')\"",
                proposal_id=None,
                proposal_report_path=None,
                scaffold_only=False,
            )

            with (
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    return_value={
                        "command": f"{sys.executable} -c \"print('ok')\"",
                        "argv": [sys.executable, "-c", "print('ok')"],
                        "returncode": 1,
                        "stdout": "",
                        "stderr": "boom",
                    },
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "write_command_logs",
                    return_value=[
                        "runs/run-steps/repo-health.stdout.txt",
                        "runs/run-steps/repo-health.stderr.txt",
                    ],
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_write_changed_files_manifest",
                    return_value="runs/run-steps/changed-files-manifest.json",
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "write_structural_complexity_budget_artifact",
                    return_value=StructuralComplexityBudgetStepResult(
                        report_path="runs/run-steps/structural-complexity-budget.json",
                        status="pass",
                    ),
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_write_behavior_delta_artifact",
                    return_value="runs/run-steps/behavior-delta.json",
                ),
                mock.patch.object(mechanism_run_workspace_runtime, "append_ledger_event") as append_event,
            ):
                result = _repo_health_step(
                    vault.resolve(),
                    vault.resolve(),
                    run_id="run-steps",
                    resolution=resolution,
                    baseline_file_digests={},
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.changed_files_manifest, "runs/run-steps/changed-files-manifest.json")
            self.assertEqual(
                result.structural_complexity_budget,
                "runs/run-steps/structural-complexity-budget.json",
            )
            self.assertEqual(result.behavior_delta, "runs/run-steps/behavior-delta.json")
            self.assertEqual(result.result["returncode"], 1)
            self.assertEqual(append_event.call_args.kwargs["decision"], "repo_health_fail")

    def test_experiment_steps_records_timeout_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "runs" / "run-mutation-timeout").mkdir(parents=True)
            seed_wrapper_vault(vault)
            seed_wrapper_vault(workspace)
            resolution = _resolve_experiment_inputs(
                vault.resolve(),
                run_id="run-mutation-timeout",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                log_summary="mutation timeout coverage",
                mutation_command=f"{sys.executable} tools/mutate_success.py",
                check_command=f"{sys.executable} -c \"print('ok')\"",
                proposal_id=None,
                proposal_report_path=None,
                scaffold_only=False,
            )

            with (
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    return_value={
                        "command": f"{sys.executable} tools/mutate_success.py",
                        "argv": [sys.executable, "tools/mutate_success.py"],
                        "returncode": -15,
                        "stdout": "",
                        "stderr": "timed out",
                        "timed_out": True,
                        "timeout_seconds": 5400,
                        "termination_reason": "timeout",
                    },
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "write_command_logs",
                    return_value=[
                        "runs/run-mutation-timeout/mutation-command.stdout.txt",
                        "runs/run-mutation-timeout/mutation-command.stderr.txt",
                    ],
                ),
                mock.patch.object(mechanism_run_workspace_runtime, "append_ledger_event") as append_event,
                self.assertRaisesRegex(
                    RunMechanismExperimentMutationError,
                    "mutation command timed out after 5400 seconds",
                ),
            ):
                _execute_mutation_step(
                    vault.resolve(),
                    workspace.resolve(),
                    run_id="run-mutation-timeout",
                    resolution=resolution,
                )

            self.assertEqual(append_event.call_args.kwargs["decision"], "mutation_timeout")
            timeout_failure_rel = "runs/run-mutation-timeout/mutation-command-timeout-failure.json"
            self.assertIn(timeout_failure_rel, append_event.call_args.kwargs["artifacts"])
            timeout_failure = json.loads((vault / timeout_failure_rel).read_text(encoding="utf-8"))
            self.assertEqual(timeout_failure["phase"], "mutation_command")
            self.assertTrue(timeout_failure["result"]["timed_out"])
            telemetry = json.loads(
                (vault / "runs" / "run-mutation-timeout" / "run-telemetry.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                telemetry["command_timeouts"]["mutation_command"],
                _expected_timeout_summary(
                    timed_out=True,
                    timeout_seconds=5400,
                    termination_reason="timeout",
                ),
            )
            self.assertEqual(telemetry["timeout_failure_artifacts"], [timeout_failure_rel])

    def test_repo_health_step_records_timeout_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            resolution = _resolve_experiment_inputs(
                vault.resolve(),
                run_id="run-steps-timeout",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                log_summary="step timeout coverage",
                mutation_command=f"{sys.executable} tools/mutate_success.py",
                check_command=f"{sys.executable} -c \"print('ok')\"",
                proposal_id=None,
                proposal_report_path=None,
                scaffold_only=False,
            )

            with (
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_run_command",
                    return_value={
                        "command": f"{sys.executable} -c \"print('ok')\"",
                        "argv": [sys.executable, "-c", "print('ok')"],
                        "returncode": -15,
                        "stdout": "",
                        "stderr": "timed out",
                        "timed_out": True,
                        "timeout_seconds": 5400,
                        "termination_reason": "timeout",
                    },
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "write_command_logs",
                    return_value=[
                        "runs/run-steps-timeout/repo-health.stdout.txt",
                        "runs/run-steps-timeout/repo-health.stderr.txt",
                    ],
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_write_changed_files_manifest",
                    return_value="runs/run-steps-timeout/changed-files-manifest.json",
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "write_structural_complexity_budget_artifact",
                    return_value=StructuralComplexityBudgetStepResult(
                        report_path=(
                            "runs/run-steps-timeout/structural-complexity-budget.json"
                        ),
                        status="pass",
                    ),
                ),
                mock.patch.object(
                    mechanism_run_workspace_runtime,
                    "_write_behavior_delta_artifact",
                    return_value="runs/run-steps-timeout/behavior-delta.json",
                ),
                mock.patch.object(mechanism_run_workspace_runtime, "append_ledger_event") as append_event,
            ):
                result = _repo_health_step(
                    vault.resolve(),
                    vault.resolve(),
                    run_id="run-steps-timeout",
                    resolution=resolution,
                    baseline_file_digests={},
                )

            self.assertFalse(result.passed)
            self.assertTrue(result.result["timed_out"])
            self.assertEqual(result.behavior_delta, "runs/run-steps-timeout/behavior-delta.json")
            self.assertEqual(append_event.call_args.kwargs["decision"], "repo_health_timeout")
            timeout_failure_rel = "runs/run-steps-timeout/repo-health-timeout-failure.json"
            self.assertIn(timeout_failure_rel, append_event.call_args.kwargs["artifacts"])
            timeout_failure = json.loads((vault / timeout_failure_rel).read_text(encoding="utf-8"))
            self.assertEqual(timeout_failure["phase"], "repo_health")
            self.assertEqual(
                timeout_failure["artifacts"]["changed_files_manifest"],
                "runs/run-steps-timeout/changed-files-manifest.json",
            )
            self.assertEqual(
                timeout_failure["artifacts"]["structural_complexity_budget"],
                "runs/run-steps-timeout/structural-complexity-budget.json",
            )
            self.assertEqual(
                timeout_failure["artifacts"]["behavior_delta"],
                "runs/run-steps-timeout/behavior-delta.json",
            )

    def test_apply_or_discard_workspace_changes_only_applies_promoted_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            schema_source = Path(__file__).resolve().parents[1] / "ops" / "schemas" / "changed-files-manifest.schema.json"
            (vault / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            live_file = vault / "ops" / "scripts" / "example.py"
            workspace_file = workspace / "ops" / "scripts" / "example.py"
            live_file.write_text("before\n", encoding="utf-8")
            workspace_file.write_text("after\n", encoding="utf-8")
            manifest_path = vault / "runs" / "run-steps" / "changed-files-manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/changed-files-manifest.schema.json",
                        "run_id": "run-steps",
                        "generated_at": "2026-04-14T00:00:00Z",
                        "declared_targets": {
                            "primary_targets": ["ops/scripts/example.py"],
                            "supporting_targets": [],
                            "test_files": [],
                        },
                        "summary": {
                            "total_changed_files": 1,
                            "added": 0,
                            "modified": 1,
                            "deleted": 0,
                        },
                        "files": [{"path": "ops/scripts/example.py", "change_type": "modified"}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            _apply_or_discard_workspace_changes(
                vault,
                workspace,
                decision="DISCARD",
                changed_files_manifest="runs/run-steps/changed-files-manifest.json",
                allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
            )
            self.assertEqual(live_file.read_text(encoding="utf-8"), "before\n")

            _apply_or_discard_workspace_changes(
                vault,
                workspace,
                decision="HOLD",
                changed_files_manifest="runs/run-steps/changed-files-manifest.json",
                allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
            )
            self.assertEqual(live_file.read_text(encoding="utf-8"), "before\n")

            with self.assertRaisesRegex(
                RunMechanismExperimentUsageError,
                "live apply mode requires run_id and context",
            ):
                _apply_or_discard_workspace_changes(
                    vault,
                    workspace,
                    decision="PROMOTE",
                    changed_files_manifest="runs/run-steps/changed-files-manifest.json",
                    allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
                )
            self.assertEqual(live_file.read_text(encoding="utf-8"), "before\n")

    def test_write_candidate_changed_files_snapshot_captures_unapplied_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts" / "target.py").write_text(
                "VALUE = 'before'\n",
                encoding="utf-8",
            )
            (vault / "ops" / "scripts" / "deleted.py").write_text(
                "DELETE_ME = True\n",
                encoding="utf-8",
            )
            (workspace / "ops" / "scripts" / "target.py").write_text(
                "VALUE = 'after'\n",
                encoding="utf-8",
            )
            (workspace / "ops" / "scripts" / "added.py").write_text(
                "ADDED = True\n",
                encoding="utf-8",
            )
            context = RuntimeContext(
                display_timezone=dt.UTC,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
            )
            manifest_rel = _write_changed_files_manifest(
                vault,
                workspace,
                run_id="run-snapshot",
                primary_targets=["ops/scripts/target.py"],
                supporting_targets=["ops/scripts/deleted.py"],
                test_files=[],
                context=context,
            )

            snapshot_rel = write_candidate_changed_files_snapshot(
                vault,
                workspace,
                run_id="run-snapshot",
                changed_files_manifest=manifest_rel,
                decision="DISCARD",
                apply_mode="live",
                apply_status="not_applicable",
                live_applied=False,
                capture_reason="non_promoted_decision",
                context=context,
            )

            snapshot = json.loads((vault / snapshot_rel).read_text(encoding="utf-8"))
            by_path = {entry["path"]: entry for entry in snapshot["files"]}
            self.assertEqual(
                snapshot_rel,
                "runs/run-snapshot/candidate-changed-files-snapshot.json",
            )
            self.assertEqual(snapshot["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(snapshot["changed_files_manifest"], manifest_rel)
            self.assertEqual(snapshot["decision"], "DISCARD")
            self.assertEqual(snapshot["capture_reason"], "non_promoted_decision")
            self.assertEqual(snapshot["apply_status"], "not_applicable")
            self.assertFalse(snapshot["live_applied"])
            self.assertEqual(snapshot["summary"]["total_changed_files"], 3)
            self.assertEqual(snapshot["summary"]["captured_text_files"], 2)
            self.assertEqual(snapshot["summary"]["metadata_only_files"], 1)
            self.assertEqual(by_path["ops/scripts/added.py"]["change_type"], "added")
            self.assertEqual(
                by_path["ops/scripts/added.py"]["candidate"]["content_utf8"],
                "ADDED = True\n",
            )
            self.assertEqual(
                by_path["ops/scripts/target.py"]["candidate"]["content_utf8"],
                "VALUE = 'after'\n",
            )
            self.assertEqual(
                by_path["ops/scripts/deleted.py"]["capture"],
                {"status": "metadata_only", "reason": "candidate_deleted"},
            )

            settle_snapshot_rel = write_candidate_changed_files_snapshot(
                vault,
                workspace,
                run_id="run-snapshot-settle",
                changed_files_manifest=manifest_rel,
                decision="SKIPPED",
                apply_mode="canary_only",
                apply_status="not_applicable",
                live_applied=False,
                capture_reason=GENERATED_EVIDENCE_SETTLE_REQUIRED,
                context=context,
            )
            settle_snapshot = json.loads(
                (vault / settle_snapshot_rel).read_text(encoding="utf-8")
            )
            self.assertEqual(
                settle_snapshot["capture_reason"],
                GENERATED_EVIDENCE_SETTLE_REQUIRED,
            )

    def test_apply_or_discard_workspace_changes_canary_mode_preserves_live_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "runs" / "run-steps").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            schema_source = Path(__file__).resolve().parents[1] / "ops" / "schemas" / "run-ledger.schema.json"
            (vault / "ops" / "schemas" / "run-ledger.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            live_file = vault / "ops" / "scripts" / "example.py"
            workspace_file = workspace / "ops" / "scripts" / "example.py"
            live_file.write_text("before\n", encoding="utf-8")
            workspace_file.write_text("after\n", encoding="utf-8")
            (vault / "runs" / "run-steps" / "changed-files-manifest.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/changed-files-manifest.schema.json",
                        "run_id": "run-steps",
                        "files": [{"path": "ops/scripts/example.py", "change_type": "modified"}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-steps" / "run-ledger.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/run-ledger.schema.json",
                        "run_id": "run-steps",
                        "status": "running",
                        "events": [
                            {
                                "ts": "2026-04-15T03:45:00Z",
                                "type": "created",
                                "summary": "created",
                                "artifacts": ["runs/run-steps/seed.yaml"],
                                "decision": "",
                            },
                            {
                                "ts": "2026-04-15T03:45:00Z",
                                "type": "seed_frozen",
                                "summary": "seed frozen",
                                "artifacts": ["runs/run-steps/seed.yaml"],
                                "decision": "",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            context = RuntimeContext(
                display_timezone=dt.UTC,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
            )

            result = _apply_or_discard_workspace_changes(
                vault,
                workspace,
                run_id="run-steps",
                context=context,
                decision="PROMOTE",
                changed_files_manifest="runs/run-steps/changed-files-manifest.json",
                allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
                apply_mode="canary_only",
            )

            ledger = json.loads((vault / "runs" / "run-steps" / "run-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(result.apply_status, "canary_ready")
            self.assertFalse(result.live_applied)
            self.assertEqual(result.rollback_rehearsal_report, "")
            self.assertEqual(live_file.read_text(encoding="utf-8"), "before\n")
            self.assertTrue((vault / "runs" / "run-steps" / "shadow-apply-report.json").exists())
            self.assertFalse((vault / "runs" / "run-steps" / "rollback-rehearsal-report.json").exists())
            self.assertIn("workspace_apply_canary_ready", [event["type"] for event in ledger["events"]])

    def test_apply_or_discard_workspace_changes_live_mode_requires_rollback_rehearsal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "runs" / "run-steps-live").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            schema_source = Path(__file__).resolve().parents[1] / "ops" / "schemas" / "run-ledger.schema.json"
            (vault / "ops" / "schemas" / "run-ledger.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            live_file = vault / "ops" / "scripts" / "example.py"
            workspace_file = workspace / "ops" / "scripts" / "example.py"
            live_file.write_text("before\n", encoding="utf-8")
            workspace_file.write_text("after\n", encoding="utf-8")
            (vault / "runs" / "run-steps-live" / "changed-files-manifest.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/changed-files-manifest.schema.json",
                        "run_id": "run-steps-live",
                        "files": [{"path": "ops/scripts/example.py", "change_type": "modified"}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-steps-live" / "run-ledger.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/run-ledger.schema.json",
                        "run_id": "run-steps-live",
                        "status": "running",
                        "events": [
                            {
                                "ts": "2026-04-15T03:45:00Z",
                                "type": "created",
                                "summary": "created",
                                "artifacts": ["runs/run-steps-live/seed.yaml"],
                                "decision": "",
                            },
                            {
                                "ts": "2026-04-15T03:45:00Z",
                                "type": "seed_frozen",
                                "summary": "seed frozen",
                                "artifacts": ["runs/run-steps-live/seed.yaml"],
                                "decision": "",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            context = RuntimeContext(
                display_timezone=dt.UTC,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
            )

            result = _apply_or_discard_workspace_changes(
                vault,
                workspace,
                run_id="run-steps-live",
                context=context,
                decision="PROMOTE",
                changed_files_manifest="runs/run-steps-live/changed-files-manifest.json",
                allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
                apply_mode="live",
            )

            ledger = json.loads((vault / "runs" / "run-steps-live" / "run-ledger.json").read_text(encoding="utf-8"))
            rehearsal = json.loads(
                (vault / "runs" / "run-steps-live" / "rollback-rehearsal-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result.apply_status, "live_applied")
            self.assertTrue(result.live_applied)
            self.assertEqual(result.rollback_rehearsal_report, "runs/run-steps-live/rollback-rehearsal-report.json")
            self.assertEqual(rehearsal["status"], "pass")
            self.assertEqual(rehearsal["summary"]["apply_verified"], 1)
            self.assertEqual(rehearsal["summary"]["rollback_verified"], 1)
            self.assertEqual(live_file.read_text(encoding="utf-8"), "after\n")
            self.assertIn("workspace_rollback_rehearsed", [event["type"] for event in ledger["events"]])
            self.assertIn("workspace_applied", [event["type"] for event in ledger["events"]])

    def test_apply_or_discard_workspace_changes_rejects_disallowed_manifest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            schema_source = Path(__file__).resolve().parents[1] / "ops" / "schemas" / "changed-files-manifest.schema.json"
            (vault / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            live_file = vault / "ops" / "scripts" / "example.py"
            live_readme = vault / "README.md"
            workspace_file = workspace / "ops" / "scripts" / "example.py"
            workspace_readme = workspace / "README.md"
            live_file.write_text("before\n", encoding="utf-8")
            live_readme.write_text("live readme\n", encoding="utf-8")
            workspace_file.write_text("after\n", encoding="utf-8")
            workspace_readme.write_text("workspace readme\n", encoding="utf-8")
            manifest_path = vault / "runs" / "run-steps" / "changed-files-manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/changed-files-manifest.schema.json",
                        "run_id": "run-steps",
                        "generated_at": "2026-04-16T00:00:00Z",
                        "declared_targets": {
                            "primary_targets": ["ops/scripts/example.py"],
                            "supporting_targets": ["README.md"],
                            "test_files": [],
                        },
                        "summary": {
                            "total_changed_files": 2,
                            "added": 0,
                            "modified": 2,
                            "deleted": 0,
                        },
                        "files": [
                            {"path": "README.md", "change_type": "modified"},
                            {"path": "ops/scripts/example.py", "change_type": "modified"},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                filesystem_runtime.FilesystemTransactionError,
                "outside allowed_apply_roots: README.md",
            ):
                _apply_or_discard_workspace_changes(
                    vault,
                    workspace,
                    run_id="run-steps",
                    context=RuntimeContext(
                        display_timezone=dt.UTC,
                        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
                    ),
                    decision="PROMOTE",
                    changed_files_manifest="runs/run-steps/changed-files-manifest.json",
                    allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
                )

            self.assertEqual(live_file.read_text(encoding="utf-8"), "before\n")
            self.assertEqual(live_readme.read_text(encoding="utf-8"), "live readme\n")

    def test_write_changed_files_manifest_uses_baseline_snapshot_and_ignores_ephemeral_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace = Path(temp_dir) / "workspace"
            vault.mkdir()
            workspace.mkdir()
            (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
            schema_source = Path(__file__).resolve().parents[1] / "ops" / "schemas" / "changed-files-manifest.schema.json"
            (vault / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
                schema_source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (vault / ".obsidian").mkdir(exist_ok=True)
            (workspace / ".obsidian").mkdir(exist_ok=True)
            (vault / ".venv").mkdir(exist_ok=True)
            (workspace / ".venv").mkdir(exist_ok=True)
            readme_live = vault / "README.md"
            readme_workspace = workspace / "README.md"
            target_live = vault / "ops" / "scripts" / "example.py"
            target_workspace = workspace / "ops" / "scripts" / "example.py"
            obsidian_live = vault / ".obsidian" / "workspace.json"
            obsidian_workspace = workspace / ".obsidian" / "workspace.json"
            readme_live.write_text("baseline readme\n", encoding="utf-8")
            readme_workspace.write_text("baseline readme\n", encoding="utf-8")
            target_live.write_text("before\n", encoding="utf-8")
            target_workspace.write_text("after\n", encoding="utf-8")
            obsidian_live.write_text("{\"workspace\": \"baseline\"}\n", encoding="utf-8")
            obsidian_workspace.write_text("{\"workspace\": \"candidate-noise\"}\n", encoding="utf-8")
            (workspace / ".venv" / "lib64" / "python3.12" / "site-packages").mkdir(parents=True, exist_ok=True)
            (workspace / ".venv" / "lib64" / "python3.12" / "site-packages" / "noise.py").write_text(
                "sentinel = 1\n",
                encoding="utf-8",
            )

            baseline_file_digests = _snapshot_repo_file_digests(vault.resolve(), run_id="run-steps")
            readme_live.write_text("live drift after snapshot\n", encoding="utf-8")

            manifest_rel = _write_changed_files_manifest(
                vault.resolve(),
                workspace.resolve(),
                run_id="run-steps",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=[],
                baseline_file_digests=baseline_file_digests,
            )

            manifest = json.loads((vault / manifest_rel).read_text(encoding="utf-8"))
            self.assertEqual(manifest["summary"]["total_changed_files"], 1)
            self.assertEqual(
                manifest["files"],
                [{"path": "ops/scripts/example.py", "change_type": "modified"}],
            )

    def test_sparse_manifest_diff_does_not_report_uncopied_baseline_files_as_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace_root = Path(temp_dir) / "workspace-root"
            (vault / "ops" / "scripts").mkdir(parents=True)
            (vault / "raw").mkdir()
            seed_changed_files_manifest_schema(vault)
            target = vault / "ops" / "scripts" / "example.py"
            target.write_text("before\n", encoding="utf-8")
            (vault / "README.md").write_text("readme baseline\n", encoding="utf-8")
            (vault / "raw" / "source.pdf").write_text("raw baseline\n", encoding="utf-8")

            workspace = _prepare_workspace_copy(
                vault.resolve(),
                run_id="run-sparse-diff",
                workspace_root=workspace_root.as_posix(),
                mode="sparse_manifest",
                allowed_apply_roots=["ops/"],
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=[],
                declared_dependencies=[],
            )
            (workspace.workspace_vault / "ops" / "scripts" / "example.py").write_text(
                "after\n",
                encoding="utf-8",
            )

            manifest_rel = _write_changed_files_manifest(
                vault.resolve(),
                workspace.workspace_vault.resolve(),
                run_id="run-sparse-diff",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=[],
                baseline_file_digests=workspace.baseline_file_digests,
                diff_model=workspace.telemetry["diff_model"],
            )

            manifest = json.loads((vault / manifest_rel).read_text(encoding="utf-8"))
            self.assertEqual(manifest["diff_universe"]["model"], "copied_universe")
            self.assertEqual(
                manifest["files"],
                [{"path": "ops/scripts/example.py", "change_type": "modified"}],
            )

    def test_sparse_manifest_diff_reports_in_universe_deletes_and_out_of_scope_adds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            workspace_root = Path(temp_dir) / "workspace-root"
            (vault / "ops" / "scripts").mkdir(parents=True)
            seed_changed_files_manifest_schema(vault)
            (vault / "ops" / "scripts" / "example.py").write_text("before\n", encoding="utf-8")

            workspace = _prepare_workspace_copy(
                vault.resolve(),
                run_id="run-sparse-guard",
                workspace_root=workspace_root.as_posix(),
                mode="sparse_manifest",
                allowed_apply_roots=["ops/"],
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=[],
                declared_dependencies=[],
            )
            (workspace.workspace_vault / "ops" / "scripts" / "example.py").unlink()
            (workspace.workspace_vault / "README.md").write_text("out of scope\n", encoding="utf-8")

            manifest_rel = _write_changed_files_manifest(
                vault.resolve(),
                workspace.workspace_vault.resolve(),
                run_id="run-sparse-guard",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=[],
                baseline_file_digests=workspace.baseline_file_digests,
                diff_model=workspace.telemetry["diff_model"],
            )

            manifest = json.loads((vault / manifest_rel).read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["files"],
                [
                    {"path": "README.md", "change_type": "added"},
                    {"path": "ops/scripts/example.py", "change_type": "deleted"},
                ],
            )
            with self.assertRaisesRegex(
                filesystem_runtime.FilesystemTransactionError,
                "outside allowed_apply_roots: README.md",
            ):
                filesystem_runtime.validate_manifest_apply_guard(manifest, ["ops/"])

    def test_finalize_step_requires_approved_or_optional_signoff(self) -> None:
        pending_report = attach_decision_contract(
            {
                "run_id": "run-steps",
                "artifact_class": "system_mechanism",
                "decision": "PROMOTE",
                "signoff": {"required": True, "status": "pending"},
            },
            [],
            subject_id="run-steps",
            subject_kind="system_mechanism",
            policy_version=1,
            source_pass="system_mechanism",
            signoff={"required": True, "status": "pending"},
        )
        approved_report = attach_decision_contract(
            {
                "run_id": "run-steps",
                "artifact_class": "system_mechanism",
                "decision": "PROMOTE",
                "signoff": {"required": True, "status": "approved"},
            },
            [],
            subject_id="run-steps",
            subject_kind="system_mechanism",
            policy_version=1,
            source_pass="system_mechanism",
            signoff={"required": True, "status": "approved"},
        )
        with mock.patch.object(mechanism_run_promotion_runtime, "finalize_run", return_value={"ok": True}) as finalize_run:
            pending = _finalize_step(
                Path(),
                run_id="run-steps",
                promotion_report=pending_report,
                finalize=True,
            )
            approved = _finalize_step(
                Path(),
                run_id="run-steps",
                promotion_report=approved_report,
                finalize=True,
            )

        self.assertFalse(pending.finalized)
        self.assertEqual(pending.finalize_result, {})
        self.assertTrue(approved.finalized)
        self.assertEqual(approved.finalize_result, {"ok": True})
        finalize_run.assert_called_once_with(Path(), "run-steps")


if __name__ == "__main__":
    unittest.main()
