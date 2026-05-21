from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.codex_goal_client import get_goal, set_goal
from ops.scripts.goal_runtime_certificate_report import (
    GoalRuntimeCertificateRequest,
    RUNNER_PRODUCER,
    build_report as build_certificate_report,
)
from ops.scripts.goal_run_status import (
    GoalRunStatusRequest,
    build_report as build_goal_run_status_report,
    write_report as write_goal_run_status_report,
    write_run_artifacts,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_codex_goal_contract import sample_goal_contract

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-certificate.schema.json"


def context_at(value: dt.datetime) -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.timezone.utc, clock=lambda: value)


def parse_iso_z(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GoalRuntimeCertificateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        for rel_path in (
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/schemas/goal-runtime-certificate.schema.json",
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/core/codex_goal_client.py",
            "ops/scripts/mechanism/goal_runtime_certificate.py",
            "ops/scripts/mechanism/goal_runtime_certificate_report.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_backoff.py",
            "ops/scripts/mechanism/goal_runtime_maintenance.py",
            "ops/scripts/mechanism/goal_runtime_resume.py",
        ):
            self._copy_support_file(rel_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _seed_goal_contract(self) -> None:
        contract = sample_goal_contract()
        contract["promotion_guard"].update(
            {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
            }
        )
        set_goal(contract, vault=self.vault)

    def _seed_full_gate_reports(self) -> None:
        reports = self.vault / "ops" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        for name in (
            "auto-improve-readiness.json",
            "session-synopsis.json",
            "remediation-backlog.json",
            "source-package-clean-extract.json",
            "public-check-summary.json",
            "release-closeout-summary.json",
        ):
            (reports / name).write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        (reports / "release-closeout-sealed-rehearsal-check.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "preflight_status": "sealed_clean_pass",
                    "distribution_binding_status": "pass",
                    "authority_preflight_status": "clean",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        guard = self.vault / "tmp" / "goal-worktree-guard.json"
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

    def _write_session_evidence(self, run_id: str, *, target_elapsed_seconds: int = 1800) -> None:
        session_path = self.vault / "ops" / "reports" / "auto-improve-sessions" / f"{run_id}.json"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        elapsed_values = list(range(0, target_elapsed_seconds + 1, 300))
        payload = {
            "status": "complete",
            "stop_reason": "proposal_budget_exhausted",
            "iterations": [
                {
                    "index": 1,
                    "status": "promoted",
                    "outcome": "promoted",
                    "decision": "PROMOTE",
                    "run_id": f"{run_id}-run-01",
                }
            ],
            "maintenance": {
                "mode": "proposal_budget_runtime_maintenance",
                "status": "complete",
                "target_elapsed_seconds": target_elapsed_seconds,
                "expected_min_cycle_count": len(elapsed_values),
                "cycle_count": len(elapsed_values),
                "meaningful_cycle_count": len(elapsed_values),
                "last_cycle_elapsed_seconds": target_elapsed_seconds,
                "cycles": [
                    {
                        "status": "pass",
                        "elapsed_seconds": elapsed_seconds,
                        "work_items": [
                            "mechanism_review_report",
                            "mutation_proposal_report",
                            "auto_improve_readiness_report",
                            "auto_improve_session_report",
                        ],
                    }
                    for elapsed_seconds in elapsed_values
                ],
            },
        }
        session_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _write_completed_goal_status(self, *, completed_at: str) -> None:
        started_at = "2026-05-17T11:00:00Z"
        started = parse_iso_z(started_at)
        completed = parse_iso_z(completed_at)
        observed_at = started
        while observed_at < completed:
            self._write_goal_run_status_at(started_at=started_at, observed_at=iso_z(observed_at))
            observed_at += dt.timedelta(minutes=5)
        self._write_goal_run_status_at(
            started_at=started_at,
            observed_at=completed_at,
            status="completed",
            completed_at=completed_at,
        )
        self._write_session_evidence(
            "20260517-loop",
            target_elapsed_seconds=int((completed - started).total_seconds()),
        )

    def _write_goal_run_status_at(
        self,
        *,
        started_at: str,
        observed_at: str,
        status: str = "running",
        completed_at: str = "",
    ) -> None:
        elapsed_seconds = int((parse_iso_z(observed_at) - parse_iso_z(started_at)).total_seconds())
        command_completed = status == "completed"
        report = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-loop",
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                last_heartbeat_at=observed_at,
                last_checkpoint_at=observed_at,
                last_command_heartbeat_at=observed_at,
                command_observation_mode="process_heartbeat",
                command_heartbeat_count=max(0, elapsed_seconds // 300),
                command_timeout_seconds=21600,
                last_command_returncode=0 if command_completed else -1,
                last_command_timed_out=False,
                last_command_termination_reason="completed" if command_completed else "",
                context=context_at(parse_iso_z(observed_at)),
            )
        )
        write_goal_run_status_report(self.vault, report)
        write_run_artifacts(self.vault, report, writer=RUNNER_PRODUCER)

    def test_completed_loop_with_full_gates_is_eligible_without_minimum_elapsed_time(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertEqual(report["certificate"]["observed_elapsed_seconds"], 1800)
        self.assertEqual(report["certificate"]["max_runtime_seconds"], 3600)
        self.assertEqual(report["session_evidence"]["status"], "clean")
        self.assertEqual(report["command_observability"]["status"], "clean")
        self.assertEqual(report["contract_update"]["certificate_status_after"], "verified")
        self.assertFalse(report["contract_update"]["applied"])
        self.assertEqual(get_goal(vault=self.vault)["runtime"]["certificate_status"], "unverified")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_apply_marks_contract_certificate_verified(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                apply_update=True,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc)),
            )
        )

        loaded = get_goal(vault=self.vault)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["contract_update"]["applied"])
        self.assertEqual(loaded["runtime"]["certificate_status"], "verified")
        self.assertTrue(loaded["promotion_guard"]["runtime_certificate_verified"])

    def test_refreshed_completed_status_accepts_original_runner_command_audit(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")

        refreshed = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-loop",
                status="completed",
                started_at="2026-05-17T11:00:00Z",
                completed_at="2026-05-17T11:30:00Z",
                context=context_at(dt.datetime(2026, 5, 17, 12, 15, tzinfo=dt.timezone.utc)),
            )
        )
        write_goal_run_status_report(self.vault, refreshed)
        write_run_artifacts(self.vault, refreshed, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 30, tzinfo=dt.timezone.utc)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertTrue(report["command_observability"]["runner_audit_current"])
        self.assertEqual(report["command_observability"]["status"], "clean")

    def test_queue_exhausted_after_success_is_eligible_without_maintenance_cycles(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")
        session_path = (
            self.vault
            / "ops"
            / "reports"
            / "auto-improve-sessions"
            / "20260517-loop.json"
        )
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(
                {
                    "status": "complete",
                    "stop_reason": "queue_exhausted",
                    "iterations": [
                        {
                            "index": 1,
                            "status": "promoted",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                            "run_id": "20260517-loop-run-01",
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertEqual(report["session_evidence"]["stop_reason"], "queue_exhausted")
        self.assertEqual(report["session_evidence"]["maintenance_status"], "missing")
        self.assertFalse(report["session_evidence"]["requires_meaningful_maintenance"])

    def test_runtime_duration_is_a_maximum_budget_not_a_minimum(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T12:30:01Z")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 13, 0, tzinfo=dt.timezone.utc)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertIn("goal run exceeded runtime duration budget", report["blockers"])
        self.assertNotIn("minimum elapsed time", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()
