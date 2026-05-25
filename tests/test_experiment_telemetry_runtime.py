from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.experiment_telemetry_runtime import (
    write_run_telemetry,
    write_timeout_failure_artifact,
)
from ops.scripts.runtime_context import RuntimeContext

from tests.minimal_vault_runtime import seed_minimal_vault


class ExperimentTelemetryRuntimeTests(unittest.TestCase):
    def test_write_timeout_failure_artifact_validates_and_writes_schema_backed_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            rel_path = write_timeout_failure_artifact(
                vault,
                "run-timeout",
                phase="mutation_command",
                command={"command": "python tools/mutate.py", "argv": ["python", "tools/mutate.py"]},
                result={
                    "returncode": -15,
                    "timed_out": True,
                    "timeout_seconds": 5,
                    "termination_reason": "timeout",
                },
                artifacts={
                    "stdout": "runs/run-timeout/mutation-command.stdout.txt",
                    "stderr": "runs/run-timeout/mutation-command.stderr.txt",
                },
                context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                diagnostics={"notes": ["mutation timeout"]},
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(rel_path, "runs/run-timeout/mutation-command-timeout-failure.json")
            self.assertEqual(payload["$schema"], "ops/schemas/timeout-failure.schema.json")
            self.assertEqual(payload["phase"], "mutation_command")
            self.assertTrue(payload["result"]["timed_out"])

    def test_write_timeout_failure_artifact_rejects_non_timeout_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            with self.assertRaisesRegex(ValueError, "requires timed_out=true"):
                write_timeout_failure_artifact(
                    vault,
                    "run-not-timeout",
                    phase="mutation_command",
                    command={"argv": ["python"]},
                    result={
                        "returncode": 0,
                        "timed_out": False,
                        "timeout_seconds": 5,
                        "termination_reason": "completed",
                    },
                    artifacts={
                        "stdout": "runs/run-not-timeout/stdout.txt",
                        "stderr": "runs/run-not-timeout/stderr.txt",
                    },
                    context=RuntimeContext(display_timezone=__import__("datetime").timezone.utc),
                )

    def test_write_run_telemetry_validates_payload_and_injects_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            rel_path = write_run_telemetry(
                vault,
                "run-telemetry-valid",
                {
                    "run_id": "run-telemetry-valid",
                    "generated_at": "2026-04-16T00:00:00Z",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "workspace_preparation": {
                        "mode": "full_copy",
                        "baseline_file_count": 3,
                        "copied_file_count": 3,
                        "phase_durations": {
                            "digest": 0.1,
                            "copy": 0.2,
                            "total": 0.3,
                        },
                    },
                    "decision": "",
                    "finalized": False,
                    "finalize_result": {},
                },
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "ops/schemas/run-telemetry.schema.json")
            self.assertEqual(payload["run_id"], "run-telemetry-valid")
            self.assertEqual(payload["workspace_preparation"]["mode"], "full_copy")

    def test_write_run_telemetry_normalizes_legacy_timeout_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            rel_path = write_run_telemetry(
                vault,
                "run-telemetry-legacy-timeout-shape",
                {
                    "run_id": "run-telemetry-legacy-timeout-shape",
                    "generated_at": "2026-04-16T00:00:00Z",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "workspace_preparation": {
                        "mode": "full_copy",
                        "baseline_file_count": 3,
                        "copied_file_count": 3,
                        "phase_durations": {
                            "digest": 0.1,
                            "copy": 0.2,
                            "total": 0.3,
                        },
                    },
                    "command_timeouts": {
                        "mutation_command": {
                            "timed_out": False,
                            "timeout_seconds": 5400,
                            "termination_reason": "completed",
                        }
                    },
                    "decision": "",
                    "finalized": False,
                    "finalize_result": {},
                },
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            timeout_result = payload["command_timeouts"]["mutation_command"]

            self.assertTrue(timeout_result["launch_succeeded"])
            self.assertEqual(timeout_result["signal_sent"], "none")
            self.assertEqual(timeout_result["final_state_observed"], "")
            self.assertFalse(timeout_result["stdout_received"])
            self.assertFalse(timeout_result["stderr_received"])

    def test_write_run_telemetry_rejects_invalid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            with self.assertRaisesRegex(ValueError, "schema validation failed for runs/run-telemetry-invalid/run-telemetry.json"):
                write_run_telemetry(
                    vault,
                    "run-telemetry-invalid",
                    {
                        "run_id": "run-telemetry-invalid",
                        "proposal_snapshot": "",
                        "scope_freeze": "",
                        "routing_reports": [],
                        "executor_reports": [],
                        "decision": "",
                        "finalized": False,
                        "finalize_result": {},
                    },
                )

    def test_write_run_telemetry_rejects_mismatched_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            with self.assertRaisesRegex(ValueError, "run telemetry payload run_id must match destination run id"):
                write_run_telemetry(
                    vault,
                    "run-telemetry-destination",
                    {
                        "run_id": "different-run-id",
                        "generated_at": "2026-04-16T00:00:00Z",
                        "proposal_snapshot": "",
                        "scope_freeze": "",
                        "routing_reports": [],
                        "executor_reports": [],
                        "decision": "",
                        "finalized": False,
                        "finalize_result": {},
                    },
                )


if __name__ == "__main__":
    unittest.main()
