from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism_run_common_runtime import (
    CommandSpec,
    RunMechanismExperimentArtifactError,
    RunMechanismExperimentUsageError,
    load_current_policy,
)
from ops.scripts.mechanism_run_scaffold_resolution_runtime import (
    PreparedExecutionCommands,
    command_argv,
    prepare_execution_commands,
    resolve_experiment_inputs,
)
from tests.run_mechanism_experiment_test_utils import mutation_proposal_report
from tests.run_mechanism_experiment_test_utils import seed_wrapper_vault


class MechanismRunScaffoldResolutionRuntimeTests(unittest.TestCase):
    def test_prepare_execution_commands_returns_typed_command_specs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            prepared = prepare_execution_commands(
                mutation_command=f"{sys.executable} tools/mutate_success.py",
                check_command=f"{sys.executable} -c \"print('ok')\"",
                cwd=vault,
                timeout_seconds=42,
            )

            self.assertIsInstance(prepared, PreparedExecutionCommands)
            self.assertIsInstance(prepared.mutation, CommandSpec)
            self.assertIsInstance(prepared.check, CommandSpec)
            self.assertEqual(prepared.mutation.timeout_seconds, 42)
            self.assertEqual(prepared.check.timeout_seconds, 42)
            self.assertEqual(prepared.mutation.argv[0], sys.executable)

    def test_command_argv_preserves_relative_virtualenv_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            (vault / ".venv" / "bin").mkdir(parents=True)
            (vault / ".venv" / "bin" / "python").symlink_to(sys.executable)

            argv = command_argv(".venv/bin/python -m pytest -q", cwd=vault)

            self.assertEqual(argv[0], ".venv/bin/python")
            self.assertEqual(argv[1:], ["-m", "pytest", "-q"])

    def test_prepare_execution_commands_rejects_invalid_command_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(RunMechanismExperimentUsageError, "invalid command syntax"):
                prepare_execution_commands(
                    mutation_command=f"{sys.executable} -c \"print('unterminated')",
                    check_command=f"{sys.executable} -c \"print('ok')\"",
                    cwd=vault,
                    timeout_seconds=42,
                )

    def test_prepare_execution_commands_rejects_shell_control_in_check_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)

            with self.assertRaisesRegex(RunMechanismExperimentUsageError, "shell operators are not supported"):
                prepare_execution_commands(
                    mutation_command=f"{sys.executable} tools/mutate_success.py",
                    check_command="echo ok && echo not-ok",
                    cwd=vault,
                    timeout_seconds=42,
                )

    def test_resolve_experiment_inputs_rejects_unknown_proposal_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            reports_dir = vault / "ops" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "mutation-proposals.json").write_text(
                json.dumps(mutation_proposal_report("ops/scripts/example.py"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RunMechanismExperimentUsageError, "unknown proposal_id"):
                resolve_experiment_inputs(
                    vault.resolve(),
                    run_id="run-resolution-unknown-proposal",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=[],
                    supporting_targets=[],
                    test_files=[],
                    log_summary=None,
                    mutation_command=None,
                    check_command=None,
                    proposal_id="missing-proposal",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    scaffold_only=True,
                )

    def test_resolve_experiment_inputs_rejects_explicit_supporting_target_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            reports_dir = vault / "ops" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "mutation-proposals.json").write_text(
                json.dumps(mutation_proposal_report("ops/scripts/example.py"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                RunMechanismExperimentUsageError,
                "explicit --supporting-target values do not match",
            ):
                resolve_experiment_inputs(
                    vault.resolve(),
                    run_id="run-resolution-supporting-mismatch",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=[],
                    supporting_targets=["tests/test_example.py"],
                    test_files=[],
                    log_summary=None,
                    mutation_command=None,
                    check_command=None,
                    proposal_id="repeated_same_eval_or_discard__example",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    scaffold_only=True,
                )

    def test_resolve_experiment_inputs_rejects_proposal_policy_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            policy, _ = load_current_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            report = mutation_proposal_report("ops/scripts/example.py")
            report["policy"]["version"] = policy["version"] + 1
            reports_dir = vault / "ops" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "mutation-proposals.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RunMechanismExperimentArtifactError, "policy.version"):
                resolve_experiment_inputs(
                    vault.resolve(),
                    run_id="run-resolution-policy-mismatch",
                    policy_path="ops/policies/wiki-maintainer-policy.yaml",
                    primary_targets=[],
                    supporting_targets=[],
                    test_files=[],
                    log_summary=None,
                    mutation_command=None,
                    check_command=None,
                    proposal_id="repeated_same_eval_or_discard__example",
                    proposal_report_path="ops/reports/mutation-proposals.json",
                    scaffold_only=True,
                )


if __name__ == "__main__":
    unittest.main()
