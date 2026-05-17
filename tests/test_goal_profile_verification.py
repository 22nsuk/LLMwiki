from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.codex_goal_client import get_goal, set_goal
from ops.scripts.goal_profile_verification import (
    GoalProfileVerificationRequest,
    RUNNER_PRODUCER,
    build_report as build_profile_verification_report,
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
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-profile-verification.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.timezone.utc),
    )


def context_from_datetime(value: dt.datetime) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: value,
    )


def parse_iso_z(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GoalProfileVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        for rel_path in (
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/schemas/goal-profile-verification.schema.json",
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/core/codex_goal_client.py",
            "ops/scripts/mechanism/goal_profile_verification.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_backoff.py",
            "ops/scripts/mechanism/goal_runtime_maintenance.py",
            "ops/scripts/mechanism/goal_runtime_profile.py",
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
        set_goal(sample_goal_contract(), vault=self.vault)

    def _seed_profile_evidence(self) -> None:
        reports = self.vault / "ops" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "session-synopsis.json").write_text(
            json.dumps({"status": "attention"}, sort_keys=True),
            encoding="utf-8",
        )
        (reports / "auto-improve-readiness.json").write_text(
            json.dumps({"status": "pass"}, sort_keys=True),
            encoding="utf-8",
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
        heartbeat_count = max(0, elapsed_seconds // 300)
        command_completed = status == "completed"
        report = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status=status,
                profile="30m_trial",
                started_at=started_at,
                completed_at=completed_at,
                last_heartbeat_at=observed_at,
                last_checkpoint_at=observed_at,
                last_command_heartbeat_at=observed_at,
                command_observation_mode="process_heartbeat" if command_completed else "process_poll",
                command_heartbeat_count=heartbeat_count,
                command_timeout_seconds=max(2400, elapsed_seconds + 300),
                last_command_returncode=0 if command_completed else -1,
                last_command_timed_out=False,
                last_command_termination_reason="completed" if command_completed else "",
                context=context_from_datetime(parse_iso_z(observed_at)),
            )
        )
        write_goal_run_status_report(self.vault, report)
        write_run_artifacts(self.vault, report, writer=RUNNER_PRODUCER)

    def _write_goal_run_status(self, *, started_at: str, completed_at: str) -> None:
        started = parse_iso_z(started_at)
        completed = parse_iso_z(completed_at)
        observed_at = started
        while observed_at < completed:
            self._write_goal_run_status_at(
                started_at=started_at,
                observed_at=iso_z(observed_at),
            )
            observed_at += dt.timedelta(minutes=5)

        self._write_goal_run_status_at(
            started_at=started_at,
            observed_at=completed_at,
            status="completed",
            completed_at=completed_at,
        )

    def test_completed_profile_with_minimum_elapsed_time_and_clean_artifacts_is_eligible(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        self._write_goal_run_status(
            started_at="2026-05-17T11:30:00Z",
            completed_at="2026-05-17T12:00:00Z",
        )

        report = build_profile_verification_report(
            GoalProfileVerificationRequest(vault=self.vault, context=fixed_context())
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["profile"]["verification_status"], "eligible")
        self.assertEqual(report["profile"]["observed_elapsed_seconds"], 1800)
        self.assertEqual(report["run_artifacts"]["status"], "clean")
        self.assertTrue(report["run_artifacts"]["runner_command_audit_current"])
        self.assertEqual(report["command_observability"]["status"], "clean")
        self.assertEqual(report["command_observability"]["mode"], "process_heartbeat")
        self.assertTrue(report["command_observability"]["runner_audit_current"])
        self.assertNotEqual(report["input_fingerprints"]["run_status_markdown"], "missing")
        self.assertNotEqual(report["input_fingerprints"]["run_resume_metadata"], "missing")
        self.assertNotEqual(report["input_fingerprints"]["run_audit_log"], "missing")
        self.assertGreaterEqual(
            report["command_observability"]["heartbeat_count"],
            report["command_observability"]["expected_min_heartbeat_count"],
        )
        self.assertEqual(report["contract_update"]["verified_profiles_after"], ["30m_trial"])
        self.assertFalse(report["contract_update"]["applied"])
        self.assertEqual(get_goal(vault=self.vault)["runtime_profile"]["verified_profiles"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_apply_persists_verified_profile_progress_to_goal_contract(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        self._write_goal_run_status(
            started_at="2026-05-17T11:30:00Z",
            completed_at="2026-05-17T12:00:00Z",
        )

        report = build_profile_verification_report(
            GoalProfileVerificationRequest(
                vault=self.vault,
                apply_update=True,
                context=fixed_context(),
            )
        )

        loaded = get_goal(vault=self.vault)
        self.assertTrue(report["contract_update"]["applied"])
        self.assertEqual(loaded["runtime_profile"]["verified_profiles"], ["30m_trial"])
        self.assertEqual(loaded["runtime_profile"]["next_profile"], "6h_ramp")
        self.assertEqual(loaded["promotion_guard"]["profile_verified"], "30m_trial")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_apply_blocks_when_elapsed_time_or_artifacts_are_not_clean(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        self._write_goal_run_status(
            started_at="2026-05-17T11:45:00Z",
            completed_at="2026-05-17T12:00:00Z",
        )
        (self.vault / "runs" / "goal-20260517-trial" / "audit-log.jsonl").unlink()

        report = build_profile_verification_report(
            GoalProfileVerificationRequest(
                vault=self.vault,
                apply_update=True,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["profile"]["verification_status"], "blocked")
        self.assertIn("profile minimum elapsed time not met", report["blockers"])
        self.assertIn("goal run artifacts are not clean", report["blockers"])
        self.assertFalse(report["contract_update"]["applied"])
        self.assertEqual(get_goal(vault=self.vault)["runtime_profile"]["verified_profiles"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_completed_profile_requires_heartbeat_audit_cadence(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        report = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="completed",
                profile="30m_trial",
                started_at="2026-05-17T11:30:00Z",
                completed_at="2026-05-17T12:00:00Z",
                last_heartbeat_at="2026-05-17T12:00:00Z",
                last_checkpoint_at="2026-05-17T12:00:00Z",
                last_command_heartbeat_at="2026-05-17T12:00:00Z",
                context=fixed_context(),
            )
        )
        write_goal_run_status_report(self.vault, report)
        write_run_artifacts(self.vault, report, writer=RUNNER_PRODUCER)

        verification = build_profile_verification_report(
            GoalProfileVerificationRequest(vault=self.vault, context=fixed_context())
        )

        self.assertEqual(verification["profile"]["verification_status"], "blocked")
        self.assertIn(
            "goal run heartbeat audit cadence is incomplete",
            verification["blockers"],
        )
        self.assertEqual(get_goal(vault=self.vault)["runtime_profile"]["verified_profiles"], [])
        self.assertEqual(validate_with_schema(verification, load_schema(SCHEMA_PATH)), [])

    def test_completed_profile_rejects_large_heartbeat_audit_gap(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        started_at = "2026-05-17T11:30:00Z"
        for observed_at in (
            "2026-05-17T11:30:00Z",
            "2026-05-17T11:31:00Z",
            "2026-05-17T11:32:00Z",
            "2026-05-17T11:33:00Z",
            "2026-05-17T11:34:00Z",
        ):
            self._write_goal_run_status_at(
                started_at=started_at,
                observed_at=observed_at,
            )
        self._write_goal_run_status_at(
            started_at=started_at,
            observed_at="2026-05-17T12:00:00Z",
            status="completed",
            completed_at="2026-05-17T12:00:00Z",
        )

        verification = build_profile_verification_report(
            GoalProfileVerificationRequest(vault=self.vault, context=fixed_context())
        )

        self.assertEqual(verification["profile"]["observed_elapsed_seconds"], 1800)
        self.assertEqual(verification["run_artifacts"]["status"], "clean")
        self.assertIn(
            "goal run heartbeat audit gap too large",
            verification["blockers"],
        )
        self.assertNotIn(
            "goal run heartbeat audit cadence is incomplete",
            verification["blockers"],
        )
        self.assertEqual(get_goal(vault=self.vault)["runtime_profile"]["verified_profiles"], [])
        self.assertEqual(validate_with_schema(verification, load_schema(SCHEMA_PATH)), [])

    def test_completed_profile_requires_runner_command_observability(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        self._write_goal_run_status(
            started_at="2026-05-17T11:30:00Z",
            completed_at="2026-05-17T12:00:00Z",
        )
        status_path = self.vault / "ops" / "reports" / "goal-run-status.json"
        report = json.loads(status_path.read_text(encoding="utf-8"))
        report["observability"]["command_observation_mode"] = ""
        report["observability"]["command_heartbeat_count"] = 0
        report["observability"]["command_timeout_seconds"] = 0
        report["observability"]["last_command_returncode"] = -1
        report["observability"]["last_command_timed_out"] = False
        report["observability"]["last_command_termination_reason"] = ""
        write_goal_run_status_report(self.vault, report)
        write_run_artifacts(self.vault, report, writer=RUNNER_PRODUCER)

        verification = build_profile_verification_report(
            GoalProfileVerificationRequest(vault=self.vault, context=fixed_context())
        )

        self.assertEqual(verification["profile"]["verification_status"], "blocked")
        self.assertEqual(verification["run_artifacts"]["status"], "clean")
        self.assertEqual(verification["command_observability"]["status"], "incomplete")
        self.assertIn(
            "goal run command observation mode is not process_heartbeat",
            verification["blockers"],
        )
        self.assertIn(
            "goal run command heartbeat count is incomplete",
            verification["blockers"],
        )
        self.assertIn("goal run command timeout is missing", verification["blockers"])
        self.assertIn("goal run command returncode is not zero", verification["blockers"])
        self.assertIn(
            "goal run command termination reason is not completed",
            verification["blockers"],
        )
        self.assertEqual(validate_with_schema(verification, load_schema(SCHEMA_PATH)), [])

    def test_completed_profile_requires_runner_origin_command_audit(self) -> None:
        self._seed_goal_contract()
        self._seed_profile_evidence()
        report = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="20260517-trial",
                status="completed",
                profile="30m_trial",
                started_at="2026-05-17T11:30:00Z",
                completed_at="2026-05-17T12:00:00Z",
                last_heartbeat_at="2026-05-17T12:00:00Z",
                last_checkpoint_at="2026-05-17T12:00:00Z",
                last_command_heartbeat_at="2026-05-17T12:00:00Z",
                command_observation_mode="process_heartbeat",
                command_heartbeat_count=6,
                command_timeout_seconds=2400,
                last_command_returncode=0,
                last_command_timed_out=False,
                last_command_termination_reason="completed",
                context=fixed_context(),
            )
        )
        write_goal_run_status_report(self.vault, report)
        write_run_artifacts(self.vault, report)

        verification = build_profile_verification_report(
            GoalProfileVerificationRequest(vault=self.vault, context=fixed_context())
        )

        self.assertEqual(verification["run_artifacts"]["status"], "clean")
        self.assertFalse(verification["run_artifacts"]["runner_command_audit_current"])
        self.assertEqual(verification["command_observability"]["status"], "incomplete")
        self.assertFalse(verification["command_observability"]["runner_audit_current"])
        self.assertIn(
            "goal run command audit was not written by goal runtime runner",
            verification["blockers"],
        )
        self.assertEqual(validate_with_schema(verification, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
