from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
from ops.scripts.experiment_telemetry_runtime import (
    append_ledger_event,
    write_command_logs,
    write_run_ledger,
    write_run_telemetry,
    write_timeout_failure_artifact,
)
from ops.scripts.runtime_context import RuntimeContext

from tests.minimal_vault_runtime import seed_minimal_vault


class ExperimentTelemetryRuntimeTests(unittest.TestCase):
    def test_write_run_ledger_refreshes_embedded_envelope_on_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            write_run_ledger(
                vault,
                "run-ledger-refresh",
                {
                    "$schema": "ops/schemas/run-ledger.schema.json",
                    "run_id": "run-ledger-refresh",
                    "status": "draft",
                    "events": [
                        {
                            "ts": "2026-04-16T00:00:00Z",
                            "type": "created",
                            "summary": "created",
                            "artifacts": ["seed.yaml"],
                            "decision": "",
                        }
                    ],
                },
            )
            append_ledger_event(
                vault,
                "run-ledger-refresh",
                event_type="seed_frozen",
                summary="updated",
                artifacts=["run-ledger.json"],
                decision="",
                context=RuntimeContext(
                    display_timezone=dt.UTC,
                    clock=lambda: dt.datetime(2026, 4, 16, 0, 5, tzinfo=dt.UTC),
                ),
            )

            payload = json.loads(
                (vault / "runs" / "run-ledger-refresh" / "run-ledger.json").read_text(
                    encoding="utf-8"
                )
            )
            embedded_envelope = next(
                item["value"]
                for item in payload["metadata"]["properties"]
                if item["name"] == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
            )
            envelope = json.loads(embedded_envelope)
            self.assertEqual(envelope["artifact_kind"], "run_ledger")
            self.assertEqual(envelope["generated_at"], "2026-04-16T00:05:00Z")

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

    def test_write_command_logs_writes_summary_and_capped_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            context = RuntimeContext(
                display_timezone=dt.UTC,
                clock=lambda: dt.datetime(2026, 4, 16, 0, 5, tzinfo=dt.UTC),
            )

            logs = write_command_logs(
                vault,
                "run-command-summary",
                "mutation-command",
                {
                    "command": "python tools/mutate.py",
                    "argv": ["python", "tools/mutate.py"],
                    "returncode": 1,
                    "stdout": "ok\n",
                    "stderr": "usage limit; try again at June 6, 2026 9:30 PM\n",
                    "timed_out": False,
                    "timeout_seconds": 5,
                    "termination_reason": "completed",
                },
                context=context,
            )

            self.assertEqual(
                logs,
                [
                    "runs/run-command-summary/mutation-command.stdout.txt",
                    "runs/run-command-summary/mutation-command.stderr.txt",
                ],
            )
            summary = json.loads(
                (
                    vault
                    / "runs/run-command-summary/command-log-summary.json"
                ).read_text(encoding="utf-8")
            )
            stderr_stream = next(
                item for item in summary["streams"] if item["stream"] == "stderr"
            )
            self.assertEqual(summary["generated_at"], "2026-04-16T00:05:00Z")
            self.assertEqual(stderr_stream["original_path"], logs[1])
            self.assertEqual(
                stderr_stream["trace_path"],
                "runs/run-command-summary/mutation-command.stderr-trace.txt",
            )
            self.assertIn("executor_usage_limited", stderr_stream["diagnostic_flags"])
            self.assertTrue((vault / stderr_stream["trace_path"]).is_file())

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
            embedded_envelope = next(
                item["value"]
                for item in payload["metadata"]["properties"]
                if item["name"] == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
            )
            envelope = json.loads(embedded_envelope)
            self.assertEqual(envelope["artifact_kind"], "run_telemetry")
            self.assertEqual(envelope["artifact_status"], "archived")
            self.assertEqual(envelope["retention_policy"], "archive")

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

    def test_write_run_telemetry_is_byte_stable_for_equivalent_payload_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            base_payload = {
                "run_id": "run-telemetry-byte-stable",
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
                "finalized": True,
                "finalize_result": {
                    "shadow_apply_report": {"status": "pass", "changed": False},
                    "rollback_rehearsal_report": {"status": "pass"},
                    "live_applied": True,
                    "apply_mode": "live",
                    "apply_status": "live_applied",
                },
            }
            reordered_payload = {
                "finalize_result": {
                    "apply_status": "live_applied",
                    "apply_mode": "live",
                    "live_applied": True,
                    "rollback_rehearsal_report": {"status": "pass"},
                    "shadow_apply_report": {"changed": False, "status": "pass"},
                },
                "finalized": True,
                "decision": "",
                "workspace_preparation": {
                    "phase_durations": {
                        "total": 0.3,
                        "copy": 0.2,
                        "digest": 0.1,
                    },
                    "copied_file_count": 3,
                    "baseline_file_count": 3,
                    "mode": "full_copy",
                },
                "executor_reports": [],
                "routing_reports": [],
                "scope_freeze": "",
                "proposal_snapshot": "",
                "generated_at": "2026-04-16T00:00:00Z",
                "run_id": "run-telemetry-byte-stable",
            }

            rel_path = write_run_telemetry(vault, "run-telemetry-byte-stable", base_payload)
            first_bytes = (vault / rel_path).read_bytes()
            rel_path = write_run_telemetry(
                vault,
                "run-telemetry-byte-stable",
                reordered_payload,
            )
            second_bytes = (vault / rel_path).read_bytes()

            self.assertEqual(first_bytes, second_bytes)

    def test_write_run_telemetry_rejects_invalid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            with self.assertRaisesRegex(ValueError, "generated_at"):
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
