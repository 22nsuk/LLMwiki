from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.codex_goal_client import set_goal
from ops.scripts.goal_run_status import (
    DEFAULT_STATUS_PATH,
    GoalRunStatusRequest,
    build_report,
    write_report,
    write_run_artifacts,
)
from ops.scripts.goal_runtime_backoff import backoff_status, freshness_status
from ops.scripts.goal_runtime_maintenance import (
    PERIODIC_CHECKPOINT_COMMAND_EVENT,
    append_checkpoint_command_event,
    build_periodic_evidence,
)
from ops.scripts.goal_runtime_certificate import build_runtime_certificate
from ops.scripts.goal_runtime_resume import resume_metadata_from_report, resume_status
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_codex_goal_contract import sample_goal_contract

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-run-status.schema.json"
RESUME_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-run-resume-metadata.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc),
    )


def context_at(hour: int, minute: int) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 17, hour, minute, tzinfo=dt.timezone.utc),
    )


class GoalRunStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/codex-goal-contract.schema.json")
        self._copy_support_file("ops/schemas/goal-run-status.schema.json")
        self._copy_support_file("ops/scripts/core/codex_goal_client.py")
        self._copy_support_file("ops/scripts/mechanism/goal_run_status.py")
        self._copy_support_file("ops/scripts/mechanism/goal_runtime_backoff.py")
        self._copy_support_file("ops/scripts/mechanism/goal_runtime_maintenance.py")
        self._copy_support_file("ops/scripts/mechanism/goal_runtime_certificate.py")
        self._copy_support_file("ops/scripts/mechanism/goal_runtime_resume.py")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _seed_goal_contract(self) -> None:
        set_goal(sample_goal_contract(), vault=self.vault)

    def _seed_session_synopsis(self) -> None:
        path = self.vault / "ops" / "reports" / "session-synopsis.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "status": "attention",
                    "generated_at": "2026-05-17T11:45:00Z",
                    "summary": {
                        "recent_blocker_count": 2,
                        "evidence_gap_count": 1,
                        "next_action": "Trial only; do not promote.",
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _seed_full_gate_reports(self) -> None:
        reports = self.vault / "ops" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        for name in (
            "auto-improve-readiness.json",
            "goal-run-status.json",
            "session-synopsis.json",
            "remediation-backlog.json",
            "source-package-clean-extract.json",
            "public-check-summary.json",
            "release-closeout-summary.json",
        ):
            (reports / name).write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        guard = self.vault / "ops" / "reports" / "goal-worktree-guard.json"
        guard.parent.mkdir(parents=True, exist_ok=True)
        guard.write_text(
            json.dumps(
                {
                    "artifact_kind": "goal_worktree_guard",
                    "status": "pass",
                    "decisions": {
                        "can_promote_result": True,
                        "promotion_blockers": [],
                        "fatal_blockers": [],
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _seed_checkpoint_command_event(
        self,
        *,
        run_id: str = "20260517-ramp",
        checkpoint_id: str = "checkpoint_6h",
        generated_at: str = "2026-05-17T11:30:00Z",
        status: str = "pass",
    ) -> None:
        append_checkpoint_command_event(
            self.vault,
            f"runs/goal-{run_id}/checkpoint-command-events.jsonl",
            {
                "event": PERIODIC_CHECKPOINT_COMMAND_EVENT,
                "generated_at": generated_at,
                "run_id": run_id,
                "checkpoint_id": checkpoint_id,
                "status": status,
                "command_count": 3,
                "failed_command_count": 0 if status == "pass" else 1,
                "commands": [],
            },
        )

    def test_goal_run_status_report_links_contract_and_observability(self) -> None:
        self._seed_goal_contract()
        self._seed_session_synopsis()

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                last_heartbeat_at="2026-05-17T11:55:00Z",
                last_checkpoint_at="2026-05-17T11:30:00Z",
                last_command_heartbeat_at="2026-05-17T11:54:00Z",
                quiet_seconds=60,
                command_observation_mode="process_heartbeat",
                command_heartbeat_count=3,
                command_timeout_seconds=1800,
                last_stdout_at="2026-05-17T11:53:00Z",
                last_command_returncode=-1,
                last_command_timed_out=False,
                last_command_termination_reason="",
                last_backoff_until="2026-05-17T12:05:00Z",
                backoff_reason="rate_limit_retry_after",
                resume_from_checkpoint=True,
                resume_command="python -m ops.scripts.auto_improve_loop --resume",
                status_report_path="ops/reports/goal-run-status.json",
                out_path="tmp/goal-run-status.candidate.json",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["artifact_kind"], "goal_run_status")
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["goal"]["backend"]["process_persistent"], True)
        self.assertEqual(report["goal"]["contract_id"], "goal-20260517-auto-improve-runtime")
        self.assertRegex(report["goal"]["contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["observability"]["command_observation_mode"], "process_heartbeat")
        self.assertEqual(report["observability"]["command_heartbeat_count"], 3)
        self.assertEqual(report["observability"]["command_timeout_seconds"], 1800)
        self.assertEqual(report["observability"]["last_stdout_at"], "2026-05-17T11:53:00Z")
        self.assertEqual(report["observability"]["last_command_returncode"], -1)
        self.assertEqual(report["observability"]["last_backoff_until"], "2026-05-17T12:05:00Z")
        self.assertEqual(report["observability"]["resume_from_checkpoint"], True)
        self.assertEqual(report["health"]["heartbeat_status"], "current")
        self.assertEqual(report["health"]["checkpoint_status"], "current")
        self.assertEqual(report["health"]["command_heartbeat_status"], "current")
        self.assertEqual(report["health"]["backoff_status"], "active")
        self.assertEqual(report["health"]["resume_status"], "ready")
        self.assertEqual(report["health"]["promotion_status"], "blocked")
        self.assertEqual(report["health"]["can_promote_result"], False)
        self.assertEqual(report["runtime_certificate"]["status"], "pending")
        self.assertEqual(report["runtime_certificate"]["mode"], "self_improvement_loop")
        self.assertEqual(report["runtime_certificate"]["certificate_status"], "unverified")
        self.assertEqual(report["runtime_certificate"]["full_gate_clean"], False)
        self.assertEqual(report["periodic_evidence"]["status"], "not_due")
        self.assertEqual(report["periodic_evidence"]["next_checkpoint_id"], "checkpoint_6h")
        self.assertEqual(report["session_synopsis"]["link_status"], "linked")
        self.assertEqual(report["session_synopsis"]["recent_blocker_count"], 2)
        self.assertEqual(report["session_synopsis"]["next_action"], "Trial only; do not promote.")
        self.assertEqual(report["artifacts"]["status_report_path"], "ops/reports/goal-run-status.json")
        self.assertEqual(
            report["artifacts"]["checkpoint_command_log_path"],
            "runs/goal-20260517-trial/checkpoint-command-events.jsonl",
        )
        self.assertEqual(report["blockers"], ["self-improvement loop certificate incomplete"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_marks_stale_command_heartbeat_as_attention_blocker(self) -> None:
        self._seed_goal_contract()

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                last_heartbeat_at="2026-05-17T11:30:00Z",
                last_checkpoint_at="2026-05-17T10:00:00Z",
                last_command_heartbeat_at="",
                status="running",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["health"]["heartbeat_status"], "stale")
        self.assertEqual(report["health"]["checkpoint_status"], "stale")
        self.assertEqual(report["health"]["command_heartbeat_status"], "not_recorded")
        self.assertIn("heartbeat stale", report["blockers"])
        self.assertIn("checkpoint stale", report["blockers"])
        self.assertIn("command heartbeat not_recorded", report["blockers"])
        self.assertEqual(report["status"], "attention")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_does_not_age_completed_run_into_active_heartbeat_blocker(self) -> None:
        self._seed_goal_contract()

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-completed",
                status="completed",
                started_at="2026-05-17T05:00:00Z",
                completed_at="2026-05-17T05:30:00Z",
                last_heartbeat_at="2026-05-17T05:30:00Z",
                last_checkpoint_at="2026-05-17T05:30:00Z",
                last_command_heartbeat_at="2026-05-17T05:30:00Z",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["health"]["heartbeat_status"], "stale")
        self.assertEqual(report["periodic_evidence"]["status"], "not_due")
        self.assertNotIn("heartbeat stale", report["blockers"])
        self.assertNotIn("checkpoint stale", report["blockers"])
        self.assertNotIn("periodic evidence checkpoint missing", report["blockers"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_marks_due_periodic_evidence_as_attention_blocker(self) -> None:
        self._seed_goal_contract()

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-ramp",
                started_at="2026-05-17T05:00:00Z",
                last_heartbeat_at="2026-05-17T11:59:00Z",
                last_checkpoint_at="2026-05-17T10:30:00Z",
                last_command_heartbeat_at="2026-05-17T11:58:00Z",
                status="running",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["periodic_evidence"]["status"], "missing_due_evidence")
        self.assertEqual(report["periodic_evidence"]["due_checkpoint_count"], 1)
        self.assertEqual(
            report["periodic_evidence"]["missing_due_checkpoint_ids"],
            ["checkpoint_6h"],
        )
        self.assertIn("periodic evidence checkpoint missing", report["blockers"])
        self.assertEqual(report["status"], "attention")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_rejects_stale_due_periodic_evidence(self) -> None:
        self._seed_goal_contract()
        reports = self.vault / "ops" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        for report_name in ("auto-improve-readiness.json", "session-synopsis.json"):
            (reports / report_name).write_text(
                json.dumps({"generated_at": "2026-05-17T10:59:00Z"}, sort_keys=True),
                encoding="utf-8",
            )

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-ramp",
                started_at="2026-05-17T05:00:00Z",
                last_heartbeat_at="2026-05-17T11:59:00Z",
                last_checkpoint_at="2026-05-17T11:30:00Z",
                last_command_heartbeat_at="2026-05-17T11:58:00Z",
                status="running",
                context=fixed_context(),
            )
        )

        checkpoint_6h = report["periodic_evidence"]["checkpoints"][0]
        self.assertEqual(report["periodic_evidence"]["status"], "missing_due_evidence")
        self.assertEqual(checkpoint_6h["status"], "missing")
        self.assertEqual(
            {item["freshness_status"] for item in checkpoint_6h["evidence_paths"]},
            {"stale"},
        )
        self.assertIn("periodic evidence checkpoint missing", report["blockers"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_requires_checkpoint_command_event_for_due_periodic_evidence(self) -> None:
        self._seed_goal_contract()
        reports = self.vault / "ops" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        for report_name in ("auto-improve-readiness.json", "session-synopsis.json"):
            (reports / report_name).write_text(
                json.dumps({"generated_at": "2026-05-17T11:20:00Z"}, sort_keys=True),
                encoding="utf-8",
            )

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-ramp",
                started_at="2026-05-17T05:00:00Z",
                last_heartbeat_at="2026-05-17T11:59:00Z",
                last_checkpoint_at="2026-05-17T11:30:00Z",
                last_command_heartbeat_at="2026-05-17T11:58:00Z",
                status="running",
                context=fixed_context(),
            )
        )

        checkpoint_6h = report["periodic_evidence"]["checkpoints"][0]
        self.assertEqual(report["periodic_evidence"]["status"], "missing_due_evidence")
        self.assertEqual(checkpoint_6h["command_run"]["status"], "not_run")
        self.assertEqual(checkpoint_6h["status"], "missing")
        self.assertIn("periodic evidence checkpoint missing", report["blockers"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_can_observe_12h_checkpoint_with_fresh_report_evidence(self) -> None:
        self._seed_goal_contract()
        reports = self.vault / "ops" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        for report_name in (
            "auto-improve-readiness.json",
            "session-synopsis.json",
            "test-execution-summary.json",
            "source-package-clean-extract.json",
        ):
            (reports / report_name).write_text(
                json.dumps({"generated_at": "2026-05-17T17:30:00Z"}, sort_keys=True),
                encoding="utf-8",
            )
        self._seed_checkpoint_command_event(generated_at="2026-05-17T11:30:00Z")
        self._seed_checkpoint_command_event(
            checkpoint_id="checkpoint_12h",
            generated_at="2026-05-17T17:30:00Z",
        )

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-ramp",
                started_at="2026-05-17T05:00:00Z",
                last_heartbeat_at="2026-05-17T17:59:00Z",
                last_checkpoint_at="2026-05-17T17:30:00Z",
                last_command_heartbeat_at="2026-05-17T17:58:00Z",
                status="running",
                context=context_at(18, 0),
            )
        )

        checkpoint_12h = report["periodic_evidence"]["checkpoints"][1]
        self.assertEqual(report["periodic_evidence"]["status"], "current")
        self.assertEqual(report["periodic_evidence"]["observed_checkpoint_count"], 2)
        self.assertEqual(checkpoint_12h["status"], "observed")
        self.assertEqual(checkpoint_12h["command_run"]["status"], "pass")
        self.assertEqual(
            [item["path"] for item in checkpoint_12h["evidence_paths"]],
            [
                "ops/reports/test-execution-summary.json",
                "ops/reports/source-package-clean-extract.json",
            ],
        )
        self.assertNotIn("periodic evidence checkpoint missing", report["blockers"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_writes_report_and_run_artifacts(self) -> None:
        self._seed_goal_contract()
        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                context=fixed_context(),
            )
        )

        report_path = write_report(self.vault, report)
        written_paths = write_run_artifacts(self.vault, report)

        self.assertEqual(report_path, self.vault / DEFAULT_STATUS_PATH)
        self.assertTrue((self.vault / "runs" / "goal-20260517-trial" / "status.md").is_file())
        self.assertEqual(len(written_paths), 3)
        resume_metadata = json.loads(
            (self.vault / "runs" / "goal-20260517-trial" / "resume-metadata.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            resume_metadata["$schema"],
            "ops/schemas/goal-run-resume-metadata.schema.json",
        )
        self.assertEqual(resume_metadata["artifact_kind"], "goal_run_resume_metadata")
        self.assertEqual(resume_metadata["contract_sha256"], report["goal"]["contract_sha256"])
        self.assertEqual(validate_with_schema(resume_metadata, load_schema(RESUME_SCHEMA_PATH)), [])
        audit_lines = (
            self.vault / "runs" / "goal-20260517-trial" / "audit-log.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(audit_lines), 1)
        audit_event = json.loads(audit_lines[0])
        self.assertEqual(audit_event["event"], "goal_run_status_written")
        self.assertEqual(audit_event["writer"], "ops.scripts.goal_run_status")

    def test_goal_run_status_uses_run_local_state_paths_for_active_status(self) -> None:
        contract = sample_goal_contract()
        contract["goal_backend"].update(
            {
                "backend_type": "run_local_file",
                "storage_path": "runs/goal-20260517-trial/state/codex-goal-contract.json",
            }
        )
        set_goal(
            contract,
            vault=self.vault,
            contract_path="runs/goal-20260517-trial/state/codex-goal-contract.json",
        )

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                goal_contract_path="runs/goal-20260517-trial/state/codex-goal-contract.json",
                status_report_path="runs/goal-20260517-trial/state/goal-run-status.json",
                context=fixed_context(),
            )
        )
        report_path = write_report(
            self.vault,
            report,
            out_path="runs/goal-20260517-trial/state/goal-run-status.json",
        )
        written_paths = write_run_artifacts(self.vault, report)

        self.assertEqual(
            report_path,
            self.vault / "runs" / "goal-20260517-trial" / "state" / "goal-run-status.json",
        )
        self.assertEqual(report["goal"]["backend"]["name"], "run_local_file")
        self.assertEqual(
            report["artifacts"]["status_markdown_path"],
            "runs/goal-20260517-trial/state/status.md",
        )
        self.assertEqual(
            report["artifacts"]["audit_log_path"],
            "runs/goal-20260517-trial/state/audit-log.jsonl",
        )
        self.assertEqual(
            report["artifacts"]["resume_metadata_path"],
            "runs/goal-20260517-trial/state/resume-metadata.json",
        )
        self.assertEqual(
            [path.relative_to(self.vault).as_posix() for path in written_paths],
            [
                "runs/goal-20260517-trial/state/status.md",
                "runs/goal-20260517-trial/state/resume-metadata.json",
                "runs/goal-20260517-trial/state/audit-log.jsonl",
            ],
        )

    def test_goal_run_status_finalization_preserves_prior_run_clock(self) -> None:
        self._seed_goal_contract()
        initial = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="running",
                last_heartbeat_at="2026-05-17T11:30:00Z",
                last_checkpoint_at="2026-05-17T11:30:00Z",
                last_command_heartbeat_at="2026-05-17T11:30:00Z",
                context=context_at(11, 30),
            )
        )
        write_report(self.vault, initial)
        write_run_artifacts(self.vault, initial)

        final = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="completed",
                completed_at="2026-05-17T12:00:00Z",
                context=fixed_context(),
            )
        )

        self.assertEqual(final["run"]["started_at"], "2026-05-17T11:30:00Z")
        self.assertEqual(final["run"]["completed_at"], "2026-05-17T12:00:00Z")
        self.assertEqual(final["observability"]["last_heartbeat_at"], "2026-05-17T11:30:00Z")
        self.assertEqual(
            final["observability"]["last_command_heartbeat_at"],
            "2026-05-17T11:30:00Z",
        )
        self.assertEqual(final["health"]["heartbeat_status"], "stale")
        self.assertEqual(validate_with_schema(final, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_refresh_preserves_terminal_runner_status(self) -> None:
        self._seed_goal_contract()
        final = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="completed",
                started_at="2026-05-17T11:00:00Z",
                completed_at="2026-05-17T12:00:00Z",
                last_heartbeat_at="2026-05-17T12:00:00Z",
                last_checkpoint_at="2026-05-17T12:00:00Z",
                last_command_heartbeat_at="2026-05-17T12:00:00Z",
                command_observation_mode="process_heartbeat",
                command_heartbeat_count=12,
                command_timeout_seconds=7200,
                last_command_returncode=0,
                last_command_termination_reason="completed",
                context=context_at(12, 0),
            )
        )
        write_report(self.vault, final)
        write_run_artifacts(self.vault, final)

        refreshed = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="blocked",
                context=context_at(12, 5),
            )
        )

        self.assertEqual(refreshed["run"]["status"], "completed")
        self.assertEqual(refreshed["run"]["started_at"], "2026-05-17T11:00:00Z")
        self.assertEqual(refreshed["run"]["completed_at"], "2026-05-17T12:00:00Z")
        self.assertEqual(refreshed["observability"]["last_command_returncode"], 0)
        self.assertEqual(
            refreshed["observability"]["last_command_termination_reason"],
            "completed",
        )
        self.assertEqual(validate_with_schema(refreshed, load_schema(SCHEMA_PATH)), [])

    def test_goal_run_status_requires_existing_persistent_goal_contract(self) -> None:
        with self.assertRaises(Exception):
            build_report(
                GoalRunStatusRequest(
                    vault=self.vault,
                    run_id="20260517-trial",
                    context=fixed_context(),
                )
            )

    def test_goal_runtime_decomposition_helpers_cover_backoff_resume_and_checkpoint(self) -> None:
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
            json.dumps({"generated_at": "2026-05-17T11:15:00Z"}, sort_keys=True),
            encoding="utf-8",
        )
        (self.vault / "ops" / "reports" / "session-synopsis.json").write_text(
            json.dumps({"generated_at": "2026-05-17T11:20:00Z"}, sort_keys=True),
            encoding="utf-8",
        )
        (
            self.vault
            / "ops"
            / "reports"
            / "release-closeout-summary.json"
        ).write_text(
            json.dumps(
                {
                    "status": "fail",
                    "generated_at": "2026-05-17T11:25:00Z",
                    "preflight_status": "binding_pass_authority_blocked",
                    "distribution_binding_status": "pass",
                    "authority_preflight_status": "blocked",
                }
            ),
            encoding="utf-8",
        )
        self._seed_checkpoint_command_event()

        periodic = build_periodic_evidence(
            self.vault,
            generated_at="2026-05-17T12:00:00Z",
            started_at="2026-05-17T05:00:00Z",
            last_checkpoint_at="2026-05-17T11:30:00Z",
            checkpoint_command_log_path="runs/goal-20260517-ramp/checkpoint-command-events.jsonl",
        )

        self.assertEqual(periodic["status"], "current")
        self.assertEqual(periodic["observed_checkpoint_count"], 1)
        self.assertEqual(periodic["missing_due_checkpoint_ids"], [])
        self.assertEqual(periodic["checkpoints"][0]["command_run"]["status"], "pass")
        self.assertEqual(
            {item["freshness_status"] for item in periodic["checkpoints"][0]["evidence_paths"]},
            {"fresh"},
        )
        self.assertEqual(
            freshness_status(
                now_iso="2026-05-17T12:00:00Z",
                observed_iso="2026-05-17T11:52:00Z",
                interval_seconds=300,
            ),
            "current",
        )
        self.assertEqual(
            backoff_status("2026-05-17T12:00:00Z", "2026-05-17T12:03:00Z"),
            "active",
        )
        self.assertEqual(
            resume_status(resume_from_checkpoint=True, resume_command=""),
            "missing_resume_command",
        )
        runtime_certificate = build_runtime_certificate(
            self.vault,
            contract=sample_goal_contract(),
            run_mode="self_improvement_loop",
        )
        self.assertEqual(runtime_certificate["status"], "pending")
        self.assertEqual(runtime_certificate["mode"], "self_improvement_loop")
        sealed_evidence = next(
            item
            for item in runtime_certificate["required_evidence"]
            if item["path"] == "ops/reports/release-closeout-summary.json"
        )
        self.assertEqual(sealed_evidence["status"], "present")
        self.assertEqual(sealed_evidence["report_status"], "fail")
        self.assertEqual(
            sealed_evidence["preflight_status"],
            "binding_pass_authority_blocked",
        )
        self.assertEqual(
            resume_metadata_from_report(
                {
                    "run": {"run_id": "trial"},
                    "goal": {"contract_sha256": "a" * 64},
                    "observability": {
                        "resume_from_checkpoint": True,
                        "resume_command": "python -m ops.scripts.auto_improve_loop --resume",
                    },
                }
            )["resume_command"],
            "python -m ops.scripts.auto_improve_loop --resume",
        )

    def test_goal_run_status_allows_sustained_claim_after_certificate_and_clean_guard(self) -> None:
        contract = sample_goal_contract()
        contract["runtime"]["certificate_status"] = "verified"
        contract["runtime"]["verified_at"] = "2026-05-17T11:00:00Z"
        contract["promotion_guard"].update(
            {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
                "runtime_certificate_verified": True,
                "sustained_runtime_claimed": True,
            }
        )
        set_goal(contract, vault=self.vault)
        self._seed_full_gate_reports()

        report = build_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260522-sustained",
                status="completed",
                last_heartbeat_at="2026-05-17T11:59:00Z",
                last_checkpoint_at="2026-05-17T11:59:00Z",
                last_command_heartbeat_at="2026-05-17T11:59:00Z",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["runtime_certificate"]["status"], "complete")
        self.assertTrue(report["runtime_certificate"]["full_gate_clean"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
