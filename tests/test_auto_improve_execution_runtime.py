from __future__ import annotations

import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism.auto_improve_execution_runtime import mutation_command


class AutoImproveExecutionRuntimeTests(unittest.TestCase):
    def test_mutation_command_targets_core_executor_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "vault"
            artifact_root.mkdir()
            command = mutation_command(
                artifact_root=artifact_root,
                run_id="run-executor",
                scope_freeze_rel="runs/run-executor/scope-freeze.json",
                proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                roles=["worker"],
                routing_report_rels=["runs/run-executor/subagent-routing.worker.json"],
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
            )

        argv = shlex.split(command)

        self.assertEqual(argv[:3], [sys.executable, "-m", "ops.scripts.core.executor"])
        self.assertEqual(argv.count("--workspace-root"), 1)
        self.assertEqual(argv[argv.index("--workspace-root") + 1], ".")
        self.assertIn("--scope-freeze", argv)
        self.assertIn("--proposal-snapshot", argv)
        self.assertIn("--routing-report", argv)

    def test_mutation_command_prefers_workspace_virtualenv_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "vault"
            venv_bin = artifact_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")
            command = mutation_command(
                artifact_root=artifact_root,
                run_id="run-executor",
                scope_freeze_rel="runs/run-executor/scope-freeze.json",
                proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                roles=["worker", "reviewer", "validator"],
                routing_report_rels=[
                    "runs/run-executor/subagent-routing.worker.json",
                    "runs/run-executor/subagent-routing.reviewer.json",
                    "runs/run-executor/subagent-routing.validator.json",
                ],
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
            )

        argv = shlex.split(command)

        self.assertEqual(argv[:3], [".venv/bin/python", "-m", "ops.scripts.core.executor"])
        self.assertEqual(argv[argv.index("--workspace-root") + 1], ".")

    def test_mutation_command_does_not_return_unlinked_scripts_python_as_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "vault"
            venv_scripts = artifact_root / ".venv" / "Scripts"
            venv_scripts.mkdir(parents=True)
            scripts_python = venv_scripts / "python.exe"
            scripts_python.write_text("# python shim\n", encoding="utf-8")
            command = mutation_command(
                artifact_root=artifact_root,
                run_id="run-executor",
                scope_freeze_rel="runs/run-executor/scope-freeze.json",
                proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
                roles=["worker"],
                routing_report_rels=["runs/run-executor/subagent-routing.worker.json"],
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
            )

        argv = shlex.split(command)

        self.assertEqual(argv[:3], [str(scripts_python), "-m", "ops.scripts.core.executor"])
        self.assertNotEqual(argv[0], ".venv/Scripts/python.exe")
        self.assertEqual(argv[argv.index("--workspace-root") + 1], ".")


if __name__ == "__main__":
    unittest.main()
