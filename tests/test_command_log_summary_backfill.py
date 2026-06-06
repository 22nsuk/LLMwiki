from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest
from ops.scripts.command_log_summary_backfill import (
    DELETE_CONFIRMATION,
    build_report as build_backfill_report,
)
from ops.scripts.command_log_summary_runtime import (
    command_log_stream_text,
    usage_limit_flag_for_artifact,
)
from ops.scripts.generated_artifact_retention_clean import (
    build_report as build_retention_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def _fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 6, 6, 1, 2, 3, tzinfo=dt.UTC),
    )


class CommandLogSummaryBackfillTests(unittest.TestCase):
    def _vault(self, root: Path) -> Path:
        vault = root / "vault"
        vault.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
        (vault / ".gitignore").write_text("runs/\nops/reports/\ntmp/\n", encoding="utf-8")
        seed_minimal_vault(vault)
        return vault

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _executor_report(self, run_id: str, role: str) -> dict[str, Any]:
        return {
            "$schema": "ops/schemas/executor-report.schema.json",
            "run_id": run_id,
            "role": role,
            "generated_at": "2026-06-06T00:00:00Z",
            "executor": {
                "name": "codex_exec",
                "sandbox_mode": "workspace-write",
                "model": "gpt-5.5",
                "reasoning_effort": "high",
            },
            "status": "pass",
            "command": {"argv": ["codex", "exec", "-"]},
            "artifacts": {
                "prompt": f"runs/archive/{run_id}/{role}-prompt.md",
                "output_last_message": f"runs/archive/{run_id}/{role}-last-message.json",
                "stdout": f"runs/archive/{run_id}/{role}.stdout.txt",
                "stderr": f"runs/archive/{run_id}/{role}.stderr.txt",
                "timeout_failure": None,
            },
            "result": {
                "returncode": 0,
                "timed_out": False,
                "timeout_seconds": 1800,
                "termination_reason": "completed",
                "launch_succeeded": True,
                "signal_sent": "none",
                "final_state_observed": "communicate",
                "stdout_received": True,
                "stderr_received": True,
                "observability": {
                    "heartbeat_count": 0,
                    "heartbeat_interval_seconds": 0,
                    "quiet_seconds": 0,
                    "last_stdout_at": "",
                    "last_stderr_at": "",
                    "last_artifact_touch_at": "",
                    "observation_mode": "communicate",
                },
            },
            "diagnostics": {
                "routing_report": f"runs/archive/{run_id}/subagent-routing.{role}.json",
                "scope_freeze": f"runs/archive/{run_id}/scope-freeze.json",
                "dependency_preflight": {
                    "role_requires_project_check": False,
                    "status": "not_required",
                    "command": {"argv": [], "project_check_lane": ""},
                    "python": {"path": "", "executable": "", "version": "", "exists": False},
                    "required_modules": [],
                    "returncode": 0,
                },
                "notes": [],
            },
        }

    def _seed_archived_executor_run(
        self,
        vault: Path,
        run_id: str = "run-promoted",
        *,
        promoted: bool = True,
        reference_raw_in_timeout: bool = False,
        timeout_uses_legacy_raw_alias: bool = False,
        write_last_message: bool = False,
        last_message_uses_legacy_raw_alias: bool = False,
        stderr_text: str = "stderr details\n",
    ) -> Path:
        run_dir = vault / "runs" / "archive" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "worker.stdout.txt").write_text("stdout details\n", encoding="utf-8")
        (run_dir / "worker.stderr.txt").write_text(stderr_text, encoding="utf-8")
        self._write_json(run_dir / "worker-executor-report.json", self._executor_report(run_id, "worker"))
        if write_last_message:
            last_message = self._executor_report(run_id, "worker")
            if last_message_uses_legacy_raw_alias:
                last_message["artifacts"]["stdout"] = f"runs/{run_id}/worker.stdout.txt"
                last_message["artifacts"]["stderr"] = f"runs/{run_id}/worker.stderr.txt"
            self._write_json(run_dir / "worker-last-message.json", last_message)
        if reference_raw_in_timeout:
            timeout_stdout = (
                f"runs/{run_id}/worker.stdout.txt"
                if timeout_uses_legacy_raw_alias
                else f"runs/archive/{run_id}/worker.stdout.txt"
            )
            timeout_stderr = (
                f"runs/{run_id}/worker.stderr.txt"
                if timeout_uses_legacy_raw_alias
                else f"runs/archive/{run_id}/worker.stderr.txt"
            )
            self._write_json(
                run_dir / "worker-timeout-failure.json",
                {
                    "$schema": "ops/schemas/timeout-failure.schema.json",
                    "run_id": run_id,
                    "phase": "executor",
                    "role": "worker",
                    "generated_at": "2026-06-06T00:00:00Z",
                    "command": {"argv": ["codex", "exec", "-"]},
                    "result": {
                        "returncode": -15,
                        "timed_out": True,
                        "timeout_seconds": 1800,
                        "termination_reason": "timeout",
                        "launch_succeeded": True,
                        "signal_sent": "SIGTERM",
                        "final_state_observed": "timeout",
                        "stdout_received": True,
                        "stderr_received": True,
                    },
                    "artifacts": {
                        "stdout": timeout_stdout,
                        "stderr": timeout_stderr,
                    },
                    "diagnostics": {"notes": []},
                },
            )
        self._write_json(
            run_dir / "run-telemetry.json",
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "run_id": run_id,
                "generated_at": "2026-06-06T00:00:00Z",
                "proposal_snapshot": "",
                "scope_freeze": "",
                "routing_reports": [],
                "executor_reports": [f"runs/archive/{run_id}/worker-executor-report.json"],
                "workspace_preparation": {
                    "mode": "in_place",
                    "baseline_file_count": 0,
                    "copied_file_count": 0,
                    "phase_durations": {"digest": 0, "copy": 0, "total": 0},
                },
                "decision": "PROMOTE" if promoted else "HOLD",
                "finalized": promoted,
                "finalize_result": {},
            },
        )
        self._write_json(
            run_dir / "run-ledger.json",
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": run_id,
                "status": "complete" if promoted else "blocked",
                "events": [
                    {
                        "ts": "2026-06-06T00:00:00Z",
                        "type": "created",
                        "summary": "created",
                        "artifacts": ["seed.yaml"],
                        "decision": "",
                    },
                    {
                        "ts": "2026-06-06T00:01:00Z",
                        "type": "seed_frozen",
                        "summary": "seed",
                        "artifacts": ["seed.yaml"],
                        "decision": "",
                    },
                    {
                        "ts": "2026-06-06T00:02:00Z",
                        "type": "executor_completed",
                        "summary": "executor",
                        "artifacts": [
                            f"runs/archive/{run_id}/worker.stdout.txt",
                            f"runs/archive/{run_id}/worker.stderr.txt",
                        ],
                        "decision": "executor_pass",
                    },
                    {
                        "ts": "2026-06-06T00:03:00Z",
                        "type": "promotion_evaluated",
                        "summary": "promotion",
                        "artifacts": [f"runs/archive/{run_id}/promotion-report.json"],
                        "decision": "PROMOTE" if promoted else "HOLD",
                    },
                    {
                        "ts": "2026-06-06T00:04:00Z",
                        "type": "finalized",
                        "summary": "finalized",
                        "artifacts": [f"runs/archive/{run_id}/run-telemetry.json"],
                        "decision": "PROMOTE" if promoted else "HOLD",
                    },
                ],
            },
        )
        return run_dir

    def _seed_active_run_command_run(self, vault: Path, run_id: str = "run-commands") -> Path:
        run_dir = vault / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "mutation-command.stdout.txt").write_text("mutation applied\n", encoding="utf-8")
        (run_dir / "mutation-command.stderr.txt").write_text("mutation detail\n", encoding="utf-8")
        self._write_json(
            run_dir / "run-telemetry.json",
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "run_id": run_id,
                "generated_at": "2026-06-06T00:00:00Z",
                "proposal_snapshot": "",
                "scope_freeze": "",
                "routing_reports": [],
                "executor_reports": [],
                "workspace_preparation": {
                    "mode": "in_place",
                    "baseline_file_count": 0,
                    "copied_file_count": 0,
                    "phase_durations": {"digest": 0, "copy": 0, "total": 0},
                },
                "command_timeouts": {
                    "mutation_command": {
                        "timed_out": False,
                        "timeout_seconds": 1800,
                        "termination_reason": "completed",
                        "launch_succeeded": True,
                        "signal_sent": "none",
                        "final_state_observed": "communicate",
                        "stdout_received": True,
                        "stderr_received": True,
                    }
                },
                "decision": "PROMOTE",
                "finalized": True,
                "finalize_result": {},
            },
        )
        self._write_json(
            run_dir / "run-ledger.json",
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": run_id,
                "status": "complete",
                "events": [
                    {
                        "ts": "2026-06-06T00:00:00Z",
                        "type": "created",
                        "summary": "created",
                        "artifacts": ["seed.yaml"],
                        "decision": "",
                    },
                    {
                        "ts": "2026-06-06T00:01:00Z",
                        "type": "mutation_applied",
                        "summary": "mutation applied",
                        "artifacts": [
                            f"runs/{run_id}/mutation-command.stdout.txt",
                            f"runs/{run_id}/mutation-command.stderr.txt",
                        ],
                        "decision": "candidate_ready_for_capture",
                    },
                    {
                        "ts": "2026-06-06T00:02:00Z",
                        "type": "promotion_evaluated",
                        "summary": "promotion",
                        "artifacts": [f"runs/{run_id}/promotion-report.json"],
                        "decision": "PROMOTE",
                    },
                    {
                        "ts": "2026-06-06T00:03:00Z",
                        "type": "finalized",
                        "summary": "finalized",
                        "artifacts": [f"runs/{run_id}/run-telemetry.json"],
                        "decision": "PROMOTE",
                    },
                ],
            },
        )
        return run_dir

    def _assert_schema_valid(self, vault: Path, rel_path: str, schema_name: str) -> dict[str, Any]:
        payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
        schema = load_schema(REPO_ROOT / "ops" / "schemas" / schema_name)
        self.assertEqual(validate_with_schema(payload, schema), [])
        return payload

    def test_dry_run_reports_eligible_legacy_executor_logs_without_mutating_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = self._seed_archived_executor_run(vault)
            report_before = (run_dir / "worker-executor-report.json").read_bytes()

            report = build_backfill_report(vault, all_runs=True, context=_fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["candidate_group_count"], 1)
            self.assertEqual(report["records"][0]["status"], "eligible")
            self.assertFalse((run_dir / "command-log-summary.json").exists())
            self.assertFalse((run_dir / "worker.stdout-trace.txt").exists())
            self.assertEqual((run_dir / "worker-executor-report.json").read_bytes(), report_before)

    def test_apply_backfills_executor_logs_updates_report_and_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = self._seed_archived_executor_run(vault)

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["applied_group_count"], 1)
            summary = self._assert_schema_valid(
                vault,
                "runs/archive/run-promoted/command-log-summary.json",
                "command-log-summary.schema.json",
            )
            self.assertEqual(summary["run_id"], "run-promoted")
            self.assertEqual({stream["stream"] for stream in summary["streams"]}, {"stdout", "stderr"})
            for stream in summary["streams"]:
                raw_path = vault / stream["original_path"]
                trace_path = vault / stream["trace_path"]
                self.assertTrue(trace_path.is_file())
                self.assertEqual(stream["original_size_bytes"], raw_path.stat().st_size)
                self.assertEqual(stream["original_sha256"], hashlib.sha256(raw_path.read_bytes()).hexdigest())
                self.assertEqual(stream["trace_sha256"], hashlib.sha256(trace_path.read_bytes()).hexdigest())
            executor_report = self._assert_schema_valid(
                vault,
                "runs/archive/run-promoted/worker-executor-report.json",
                "executor-report.schema.json",
            )
            self.assertEqual(
                executor_report["artifacts"]["stdout"],
                "runs/archive/run-promoted/worker.stdout-trace.txt",
            )
            self.assertEqual(
                executor_report["artifacts"]["command_log_summary"],
                "runs/archive/run-promoted/command-log-summary.json",
            )
            fingerprint = self._assert_schema_valid(
                vault,
                "runs/archive/run-promoted/run-artifact-fingerprint.json",
                "run-artifact-fingerprint.schema.json",
            )
            artifact_paths = {item["path"] for item in fingerprint["artifacts"]}
            self.assertIn("runs/archive/run-promoted/worker.stdout.txt", artifact_paths)
            self.assertIn("runs/archive/run-promoted/worker.stdout-trace.txt", artifact_paths)
            self.assertIn("runs/archive/run-promoted/command-log-summary.json", artifact_paths)
            self.assertNotIn("runs/archive/run-promoted/run-artifact-fingerprint.json", artifact_paths)
            self.assertTrue((run_dir / "worker.stdout.txt").is_file())

    def test_delete_raw_removes_only_promoted_archived_unreferenced_backfilled_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            promoted_run = self._seed_archived_executor_run(vault, "run-promoted")
            held_run = self._seed_archived_executor_run(vault, "run-held", promoted=False)
            referenced_run = self._seed_archived_executor_run(vault, "run-referenced")
            (vault / "ops/reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops/reports/remediation-backlog.json").write_text(
                "runs/archive/run-referenced\n",
                encoding="utf-8",
            )

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                delete_raw=True,
                operator_confirmation=DELETE_CONFIRMATION,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                set(report["deleted_raw_paths"]),
                {
                    "runs/archive/run-promoted/worker.stdout.txt",
                    "runs/archive/run-promoted/worker.stderr.txt",
                },
            )
            self.assertFalse((promoted_run / "worker.stdout.txt").exists())
            self.assertTrue((promoted_run / "worker.stdout-trace.txt").is_file())
            self.assertTrue((promoted_run / "command-log-summary.json").is_file())
            self.assertTrue((held_run / "worker.stdout.txt").is_file())
            self.assertTrue((referenced_run / "worker.stdout.txt").is_file())
            retention = build_retention_report(vault)
            retained = {item["path"]: item for item in retention["retained"]}
            self.assertEqual(
                retained["runs/archive/run-held/worker.stdout.txt"]["reason"],
                "run did not finish as promoted",
            )
            self.assertEqual(
                retained["runs/archive/run-referenced/worker.stdout.txt"]["reason"],
                "current evidence references owning run",
            )

    def test_delete_raw_rewrites_same_run_timeout_references_before_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = self._seed_archived_executor_run(
                vault,
                "run-timeout-reference",
                reference_raw_in_timeout=True,
            )

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                delete_raw=True,
                operator_confirmation=DELETE_CONFIRMATION,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                set(report["deleted_raw_paths"]),
                {
                    "runs/archive/run-timeout-reference/worker.stdout.txt",
                    "runs/archive/run-timeout-reference/worker.stderr.txt",
                },
            )
            self.assertFalse((run_dir / "worker.stdout.txt").exists())
            timeout_failure = self._assert_schema_valid(
                vault,
                "runs/archive/run-timeout-reference/worker-timeout-failure.json",
                "timeout-failure.schema.json",
            )
            self.assertEqual(
                timeout_failure["artifacts"]["stdout"],
                "runs/archive/run-timeout-reference/worker.stdout-trace.txt",
            )

    def test_delete_raw_rewrites_legacy_unarchived_aliases_before_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = self._seed_archived_executor_run(
                vault,
                "run-legacy-alias",
                reference_raw_in_timeout=True,
                timeout_uses_legacy_raw_alias=True,
                write_last_message=True,
                last_message_uses_legacy_raw_alias=True,
            )

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                delete_raw=True,
                operator_confirmation=DELETE_CONFIRMATION,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["stale_same_run_references"], [])
            self.assertFalse((run_dir / "worker.stdout.txt").exists())
            timeout_failure = self._assert_schema_valid(
                vault,
                "runs/archive/run-legacy-alias/worker-timeout-failure.json",
                "timeout-failure.schema.json",
            )
            last_message = self._assert_schema_valid(
                vault,
                "runs/archive/run-legacy-alias/worker-last-message.json",
                "executor-report.schema.json",
            )
            for payload in (timeout_failure, last_message):
                self.assertEqual(
                    payload["artifacts"]["stdout"],
                    "runs/archive/run-legacy-alias/worker.stdout-trace.txt",
                )
                self.assertEqual(
                    payload["artifacts"]["stderr"],
                    "runs/archive/run-legacy-alias/worker.stderr-trace.txt",
                )

    def test_archived_summary_helpers_read_trace_and_usage_limit_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            self._seed_archived_executor_run(
                vault,
                "run-usage",
                stderr_text="you have hit your usage limit; try again at 10\n",
            )

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue(
                usage_limit_flag_for_artifact(
                    vault,
                    "runs/archive/run-usage/worker.stderr-trace.txt",
                )
            )
            self.assertIn(
                "usage limit",
                command_log_stream_text(
                    vault,
                    "run-usage",
                    prefix="worker",
                    stream="stderr",
                ),
            )

    def test_archive_fingerprint_refresh_targets_archive_when_live_run_id_collides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            live_run_dir = vault / "runs" / "run-collision"
            live_run_dir.mkdir(parents=True)
            (live_run_dir / "unrelated.txt").write_text("live\n", encoding="utf-8")
            self._seed_archived_executor_run(vault, "run-collision")

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue(
                (vault / "runs/archive/run-collision/run-artifact-fingerprint.json").is_file()
            )
            self.assertFalse((live_run_dir / "run-artifact-fingerprint.json").exists())

    def test_run_command_backfill_closes_active_promoted_run_before_raw_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = self._seed_active_run_command_run(vault)

            report = build_backfill_report(
                vault,
                apply=True,
                all_runs=True,
                include_run_commands=True,
                close_promoted_unreferenced=True,
                delete_raw=True,
                operator_confirmation=DELETE_CONFIRMATION,
                context=_fixed_context(),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["closure"]["closed_run_ids"], ["run-commands"])
            self.assertEqual(
                set(report["deleted_raw_paths"]),
                {
                    "runs/run-commands/mutation-command.stdout.txt",
                    "runs/run-commands/mutation-command.stderr.txt",
                },
            )
            self.assertFalse((run_dir / "mutation-command.stdout.txt").exists())
            self.assertTrue((run_dir / "mutation-command.stdout-trace.txt").is_file())
            closure = self._assert_schema_valid(
                vault,
                "ops/reports/rework-closures.json",
                "rework-closures.schema.json",
            )
            self.assertEqual(closure["summary"]["closed_rework_count"], 1)
            self.assertTrue(
                all(
                    ref.startswith("runs/run-commands/")
                    for ref in closure["closures"][0]["evidence_refs"]
                )
            )


if __name__ == "__main__":
    unittest.main()
