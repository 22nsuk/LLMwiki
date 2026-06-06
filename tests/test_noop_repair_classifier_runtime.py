from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.executor_noop_runtime import (
    EXECUTOR_NOOP_MUTATION_FAILURE_MARKER,
    executor_noop_mutation_failure_message,
    text_has_executor_noop_mutation_failure,
)
from ops.scripts.experiment_telemetry_runtime import write_command_logs
from ops.scripts.noop_repair_classifier_runtime import (
    repair_decision_ended_as_noop_mutation_failure,
    run_has_noop_mutation_failure,
)
from ops.scripts.runtime_context import RuntimeContext

from tests.minimal_vault_runtime import seed_minimal_vault


class NoopRepairClassifierRuntimeTests(unittest.TestCase):
    def test_executor_noop_marker_preserves_legacy_wire_text(self) -> None:
        self.assertEqual(
            EXECUTOR_NOOP_MUTATION_FAILURE_MARKER,
            "reported pass without modifying any declared primary target",
        )
        message = executor_noop_mutation_failure_message(
            "worker",
            ["ops/scripts/example_runtime.py"],
        )

        self.assertEqual(
            message,
            (
                "worker reported pass without modifying any declared primary target; "
                "primary_targets=[ops/scripts/example_runtime.py]"
            ),
        )
        self.assertTrue(text_has_executor_noop_mutation_failure(message))

    def test_run_noop_classifier_consumes_executor_marker_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            run_dir = vault / "runs" / "run-noop"
            run_dir.mkdir(parents=True)
            (run_dir / "mutation-command.stderr.txt").write_text(
                executor_noop_mutation_failure_message(
                    "worker",
                    ["ops/scripts/example_runtime.py"],
                ),
                encoding="utf-8",
            )

            self.assertTrue(run_has_noop_mutation_failure(vault, "run-noop"))

    def test_run_noop_classifier_consumes_summary_when_raw_stderr_was_retained_out(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            message = executor_noop_mutation_failure_message(
                "worker",
                ["ops/scripts/example_runtime.py"],
            )
            write_command_logs(
                vault,
                "run-noop-summary",
                "mutation-command",
                {
                    "command": "python tools/mutate.py",
                    "argv": ["python", "tools/mutate.py"],
                    "returncode": 1,
                    "stdout": "",
                    "stderr": message,
                    "timed_out": False,
                    "timeout_seconds": 5,
                    "termination_reason": "completed",
                },
                context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
            )
            (vault / "runs/run-noop-summary/mutation-command.stderr.txt").unlink()

            self.assertTrue(run_has_noop_mutation_failure(vault, "run-noop-summary"))

    def test_repair_decision_closes_only_mutation_failed_noop_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            run_dir = vault / "runs" / "run-noop"
            run_dir.mkdir(parents=True)
            (run_dir / "mutation-command.stderr.txt").write_text(
                executor_noop_mutation_failure_message(
                    "worker",
                    ["ops/scripts/example_runtime.py"],
                ),
                encoding="utf-8",
            )
            decision = {
                "proposal_family": "next_run_failure_repair",
                "proposal_id": "next_run_failure_repair__example-runtime__validation-blocked",
                "failure_taxonomy": "mutation_failed",
                "source_run_id": "run-noop",
            }

            self.assertTrue(
                repair_decision_ended_as_noop_mutation_failure(
                    vault,
                    decision,
                    queue_unblock_family="queue_unblock",
                )
            )
            self.assertFalse(
                repair_decision_ended_as_noop_mutation_failure(
                    vault,
                    {**decision, "failure_taxonomy": "validation_blocked"},
                    queue_unblock_family="queue_unblock",
                )
            )


if __name__ == "__main__":
    unittest.main()
