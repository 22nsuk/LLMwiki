from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.codex_goal_client import get_goal, set_goal
from ops.scripts.goal_run_status import (
    GoalRunStatusRequest,
    build_report as build_goal_run_status_report,
    write_report as write_goal_run_status_report,
    write_run_artifacts,
)
from ops.scripts.goal_runtime_certificate_report import (
    RUNNER_PRODUCER,
    GoalRuntimeCertificateRequest,
    build_report as build_certificate_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_codex_goal_contract import sample_goal_contract

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-certificate.schema.json"


def context_at(value: dt.datetime) -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.UTC, clock=lambda: value)


def parse_iso_z(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            "ops/scripts/mechanism/goal_contract_digest_runtime.py",
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

    def _write_promoted_session_without_maintenance(self, run_id: str) -> None:
        session_path = self.vault / "ops" / "reports" / "auto-improve-sessions" / f"{run_id}.json"
        session_path.parent.mkdir(parents=True, exist_ok=True)
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
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertEqual(report["certificate"]["observed_elapsed_seconds"], 1800)
        self.assertEqual(report["certificate"]["max_runtime_seconds"], 3600)
        self.assertEqual(report["session_evidence"]["status"], "clean")
        self.assertEqual(
            report["session_evidence"]["minimum_meaningful_maintenance_cycle_count"],
            1,
        )
        self.assertFalse(
            report["session_evidence"]["allow_zero_maintenance_cycles_for_certificate"]
        )
        self.assertEqual(report["command_observability"]["status"], "clean")
        self.assertEqual(report["run_artifacts"]["status"], "clean")
        self.assertEqual(report["run_artifacts"]["audit_event_count"], 7)
        self.assertTrue(report["run_artifacts"]["runner_command_audit_current"])
        self.assertEqual(
            [
                (item["artifact"], item["status"])
                for item in report["run_artifacts"]["checks"]
            ],
            [
                ("status_markdown_path", "present"),
                ("resume_metadata_path", "present"),
                ("audit_log_path", "present"),
                ("status_markdown_current", "pass"),
                ("resume_metadata_current", "pass"),
                ("audit_log_current", "pass"),
                ("audit_log_command_observability_current", "pass"),
            ],
        )
        self.assertEqual(
            {
                "run_status_markdown",
                "run_resume_metadata",
                "run_audit_log",
            }
            & set(report["input_fingerprints"]),
            {
                "run_status_markdown",
                "run_resume_metadata",
                "run_audit_log",
            },
        )
        self.assertEqual(report["diagnosis"]["certificate_claim_status"], "eligible")
        self.assertTrue(report["diagnosis"]["certifiable"])
        self.assertFalse(
            report["diagnosis"]["mechanism_promote_evidence_policy"][
                "mechanism_promote_sufficient_for_certificate"
            ]
        )
        self.assertEqual(report["contract_update"]["certificate_status_after"], "verified")
        self.assertFalse(report["contract_update"]["applied"])
        self.assertEqual(get_goal(vault=self.vault)["runtime"]["certificate_status"], "unverified")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_promoted_proposal_budget_session_without_maintenance_blocks_certificate(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")
        self._write_promoted_session_without_maintenance("20260517-loop")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["certificate"]["verification_status"], "blocked")
        self.assertEqual(report["session_evidence"]["status"], "incomplete")
        self.assertEqual(report["session_evidence"]["maintenance_status"], "missing")
        self.assertTrue(report["session_evidence"]["requires_meaningful_maintenance"])
        self.assertEqual(
            report["session_evidence"]["minimum_meaningful_maintenance_cycle_count"],
            1,
        )
        self.assertIn(
            "auto-improve session lacks meaningful runtime maintenance evidence",
            report["blockers"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_apply_marks_contract_certificate_verified(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                apply_update=True,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        loaded = get_goal(vault=self.vault)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["contract_update"]["applied"])
        self.assertEqual(loaded["runtime"]["certificate_status"], "verified")
        self.assertTrue(loaded["promotion_guard"]["runtime_certificate_verified"])

    def test_runtime_certificate_is_independent_from_release_promotion_guard(self) -> None:
        self._seed_goal_contract()
        contract = get_goal(vault=self.vault)
        contract["promotion_guard"].update(
            {
                "can_promote_result": False,
                "promotion_blockers": [
                    "promotion_blocked_by_release_batch_manifest_failure",
                    "promotion_blocked_by_remediation_backlog_open",
                ],
                "sealed_authority_clean": False,
            }
        )
        set_goal(contract, vault=self.vault)
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["session_evidence"]["status"], "clean")
        self.assertEqual(report["command_observability"]["status"], "clean")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

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
                context=context_at(dt.datetime(2026, 5, 17, 12, 15, tzinfo=dt.UTC)),
            )
        )
        write_goal_run_status_report(self.vault, refreshed)
        write_run_artifacts(self.vault, refreshed, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 30, tzinfo=dt.UTC)),
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
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertEqual(report["session_evidence"]["stop_reason"], "queue_exhausted")
        self.assertEqual(report["session_evidence"]["maintenance_status"], "missing")
        self.assertFalse(report["session_evidence"]["requires_meaningful_maintenance"])

    def test_failure_budget_exhausted_session_is_closed_noncertifiable_failure(self) -> None:
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
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["stop_reason"] = "failure_budget_exhausted"
        session["iterations"] = [
            {
                "index": 1,
                "status": "promoted",
                "outcome": "promoted",
                "decision": "PROMOTE",
                "run_id": "20260517-loop-run-01",
                "proposal_id": "repair-runtime",
            },
            {
                "index": 2,
                "status": "failed",
                "outcome": "failed",
                "decision": "REPAIR",
                "run_id": "20260517-loop-run-02",
                "proposal_id": "follow-up-runtime",
                "quarantined": True,
            },
        ]
        session["attempted_proposal_ids"] = ["repair-runtime", "follow-up-runtime"]
        session["quarantined_proposal_ids"] = ["follow-up-runtime"]
        session_path.write_text(json.dumps(session, sort_keys=True), encoding="utf-8")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["certificate"]["verification_status"], "blocked")
        self.assertEqual(report["session_evidence"]["stop_reason"], "failure_budget_exhausted")
        self.assertEqual(
            report["diagnosis"]["certificate_failure_class"],
            "noncertifiable_closed_failure",
        )
        self.assertEqual(
            report["diagnosis"]["certificate_claim_status"],
            "not_yet_certifiable",
        )
        self.assertFalse(report["diagnosis"]["certifiable"])
        self.assertIn(
            "auto-improve session closed as noncertifiable failure after failure budget exhausted",
            report["blockers"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_promoted_mechanism_session_alone_does_not_certify_current_goal_run(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_session_evidence("historical-promoted-session")
        current = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="current-loop",
                status="blocked",
                started_at="2026-05-17T11:00:00Z",
                last_heartbeat_at="2026-05-17T11:05:00Z",
                last_checkpoint_at="2026-05-17T11:05:00Z",
                context=context_at(dt.datetime(2026, 5, 17, 11, 5, tzinfo=dt.UTC)),
            )
        )
        write_goal_run_status_report(self.vault, current)
        write_run_artifacts(self.vault, current, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["diagnosis"]["certificate_claim_status"], "not_yet_certifiable")
        self.assertFalse(report["diagnosis"]["certifiable"])
        self.assertEqual(report["diagnosis"]["current_scope"]["run_id"], "current-loop")
        self.assertEqual(
            report["diagnosis"]["current_scope"]["session_evidence_path"],
            "ops/reports/auto-improve-sessions/current-loop.json",
        )
        self.assertFalse(
            report["diagnosis"]["mechanism_promote_evidence_policy"][
                "mechanism_promote_sufficient_for_certificate"
            ]
        )
        self.assertIn("runtime_run", report["diagnosis"]["primary_blocker_categories"])
        self.assertIn("session_evidence", report["diagnosis"]["primary_blocker_categories"])
        self.assertIn("command_observability", report["diagnosis"]["primary_blocker_categories"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_existing_verified_certificate_is_preserved_when_new_default_run_is_blocked(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")
        verified = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                apply_update=True,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )
        for item in verified["evidence_paths"]:
            if item["evidence_id"] == "goal_worktree_guard":
                item["path"] = "tmp/goal-worktree-guard.json"
        existing_report = self.vault / "ops" / "reports" / "goal-runtime-certificate.json"
        existing_report.parent.mkdir(parents=True, exist_ok=True)
        existing_report.write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")

        set_goal(sample_goal_contract(), vault=self.vault)
        current = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="new-default-trial",
                status="blocked",
                started_at="2026-05-17T12:10:00Z",
                last_heartbeat_at="2026-05-17T12:15:00Z",
                last_checkpoint_at="2026-05-17T12:15:00Z",
                context=context_at(dt.datetime(2026, 5, 17, 12, 15, tzinfo=dt.UTC)),
            )
        )
        write_goal_run_status_report(self.vault, current)
        write_run_artifacts(self.vault, current, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 30, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["run"]["run_id"], "20260517-loop")
        self.assertEqual(report["diagnosis"]["certificate_claim_status"], "eligible")
        self.assertTrue(report["diagnosis"]["certifiable"])
        evidence_paths = {
            item["evidence_id"]: item["path"] for item in report["evidence_paths"]
        }
        self.assertEqual(
            evidence_paths["goal_worktree_guard"],
            "ops/reports/goal-worktree-guard.json",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_stale_existing_verified_certificate_is_not_preserved(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")
        verified = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                apply_update=True,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )
        existing_report = self.vault / "ops" / "reports" / "goal-runtime-certificate.json"
        existing_report.parent.mkdir(parents=True, exist_ok=True)
        existing_report.write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")
        changed_source = self.vault / "ops" / "scripts" / "mechanism" / "goal_runtime_certificate.py"
        changed_source.write_text(
            f"{changed_source.read_text(encoding='utf-8')}\n# fixture source change\n",
            encoding="utf-8",
        )

        set_goal(sample_goal_contract(), vault=self.vault)
        current = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="new-default-trial",
                status="blocked",
                started_at="2026-05-17T12:10:00Z",
                last_heartbeat_at="2026-05-17T12:15:00Z",
                last_checkpoint_at="2026-05-17T12:15:00Z",
                context=context_at(dt.datetime(2026, 5, 17, 12, 15, tzinfo=dt.UTC)),
            )
        )
        write_goal_run_status_report(self.vault, current)
        write_run_artifacts(self.vault, current, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 30, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["run"]["run_id"], "new-default-trial")
        self.assertEqual(report["certificate"]["verification_status"], "blocked")
        self.assertNotEqual(
            report["source_tree_fingerprint"],
            verified["source_tree_fingerprint"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_existing_verified_certificate_is_preserved_after_transient_evidence_cleanup(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")
        verified = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                apply_update=True,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )
        existing_report = self.vault / "ops" / "reports" / "goal-runtime-certificate.json"
        existing_report.parent.mkdir(parents=True, exist_ok=True)
        existing_report.write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")
        missing_session = self.vault / verified["session_evidence"]["path"]
        missing_session.unlink()

        set_goal(sample_goal_contract(), vault=self.vault)
        current = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                run_id="new-default-trial",
                status="blocked",
                started_at="2026-05-17T12:10:00Z",
                last_heartbeat_at="2026-05-17T12:15:00Z",
                last_checkpoint_at="2026-05-17T12:15:00Z",
                context=context_at(dt.datetime(2026, 5, 17, 12, 15, tzinfo=dt.UTC)),
            )
        )
        write_goal_run_status_report(self.vault, current)
        write_run_artifacts(self.vault, current, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 12, 30, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["run"]["run_id"], "20260517-loop")
        self.assertEqual(report["certificate"]["verification_status"], "eligible")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_existing_verified_certificate_does_not_replace_explicit_goal_scope(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T11:30:00Z")
        verified = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                apply_update=True,
                context=context_at(dt.datetime(2026, 5, 17, 12, 0, tzinfo=dt.UTC)),
            )
        )
        existing_report = self.vault / "ops" / "reports" / "goal-runtime-certificate.json"
        existing_report.parent.mkdir(parents=True, exist_ok=True)
        existing_report.write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")

        explicit_contract_path = "runs/goal-explicit-trial/state/codex-goal-contract.json"
        explicit_status_path = "runs/goal-explicit-trial/state/goal-run-status.json"
        set_goal(sample_goal_contract(), vault=self.vault, contract_path=explicit_contract_path)
        current = build_goal_run_status_report(
            GoalRunStatusRequest(
                vault=self.vault,
                goal_contract_path=explicit_contract_path,
                status_report_path=explicit_status_path,
                run_id="explicit-trial",
                status="blocked",
                started_at="2026-05-17T12:10:00Z",
                last_heartbeat_at="2026-05-17T12:15:00Z",
                last_checkpoint_at="2026-05-17T12:15:00Z",
                context=context_at(dt.datetime(2026, 5, 17, 12, 15, tzinfo=dt.UTC)),
            )
        )
        write_goal_run_status_report(self.vault, current, explicit_status_path)
        write_run_artifacts(self.vault, current, writer="ops.scripts.goal_run_status")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                goal_contract_path=explicit_contract_path,
                status_report_path=explicit_status_path,
                context=context_at(dt.datetime(2026, 5, 17, 12, 30, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["certificate"]["verification_status"], "blocked")
        self.assertEqual(report["run"]["run_id"], "explicit-trial")
        self.assertEqual(report["run"]["status_report_path"], explicit_status_path)
        self.assertEqual(report["goal"]["contract_path"], explicit_contract_path)
        self.assertEqual(
            report["diagnosis"]["current_scope"]["status_report_path"],
            explicit_status_path,
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_runtime_duration_is_a_maximum_budget_not_a_minimum(self) -> None:
        self._seed_goal_contract()
        self._seed_full_gate_reports()
        self._write_completed_goal_status(completed_at="2026-05-17T12:30:01Z")

        report = build_certificate_report(
            GoalRuntimeCertificateRequest(
                vault=self.vault,
                context=context_at(dt.datetime(2026, 5, 17, 13, 0, tzinfo=dt.UTC)),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertIn("goal run exceeded runtime duration budget", report["blockers"])
        self.assertEqual(report["diagnosis"]["certificate_claim_status"], "not_yet_certifiable")
        self.assertIn("runtime_budget", report["diagnosis"]["primary_blocker_categories"])
        self.assertNotIn("minimum elapsed time", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()
