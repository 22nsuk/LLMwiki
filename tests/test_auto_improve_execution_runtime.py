from __future__ import annotations

import shlex
import sys
import unittest
from pathlib import Path

from ops.scripts.mechanism.auto_improve_execution_runtime import mutation_command


class AutoImproveExecutionRuntimeTests(unittest.TestCase):
    def test_mutation_command_targets_core_executor_module(self) -> None:
        command = mutation_command(
            artifact_root=Path("."),
            run_id="run-executor",
            scope_freeze_rel="runs/run-executor/scope-freeze.json",
            proposal_snapshot_rel="runs/run-executor/proposal-snapshot.json",
            roles=["worker"],
            routing_report_rels=["runs/run-executor/subagent-routing.worker.json"],
            policy_path="ops/policies/wiki-maintainer-policy.yaml",
        )

        argv = shlex.split(command)

        self.assertEqual(argv[:3], [sys.executable, "-m", "ops.scripts.core.executor"])
        self.assertIn("--scope-freeze", argv)
        self.assertIn("--proposal-snapshot", argv)
        self.assertIn("--routing-report", argv)


if __name__ == "__main__":
    unittest.main()
