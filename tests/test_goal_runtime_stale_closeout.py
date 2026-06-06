from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.goal_runtime_stale_closeout import (
    GoalRuntimeStaleCloseoutRequest,
    build_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-stale-closeout.schema.json"
SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "report_schema_samples.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 21, 0, 0, tzinfo=dt.UTC),
    )


class GoalRuntimeStaleCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_report(self) -> dict:
        return build_report(
            GoalRuntimeStaleCloseoutRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

    def _sample_session(self, *, session_id: str, rel_path: str) -> dict:
        payload = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))["auto_improve_session"]
        payload["session_id"] = session_id
        payload["path"] = rel_path
        payload["status"] = "running"
        payload["stop_reason"] = "running"
        payload["iterations"] = []
        payload["run_ids"] = []
        return payload

    def test_archived_session_path_reference_is_resolved_without_action_required(self) -> None:
        self._write_json(
            "ops/reports/archive/auto-improve-sessions/session-a.json",
            {
                "session_id": "session-a",
                "path": "ops/reports/auto-improve-sessions/session-a.json",
                "status": "complete",
                "stop_reason": "proposal_budget_exhausted",
                "iterations": [],
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["path_resolution_count"], 1)
        self.assertEqual(report["summary"]["action_required_count"], 0)
        self.assertEqual(report["issues"][0]["issue_type"], "session_path_reference_resolved")
        self.assertEqual(
            report["issues"][0]["path"],
            "ops/reports/archive/auto-improve-sessions/session-a.json",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_running_sessions_are_classified_by_attempt_evidence(self) -> None:
        self._write_json(
            "ops/reports/auto-improve-sessions/no-attempts.json",
            {
                "session_id": "no-attempts",
                "path": "ops/reports/auto-improve-sessions/no-attempts.json",
                "status": "running",
                "stop_reason": "running",
                "iterations": [],
                "run_ids": [],
            },
        )
        self._write_json(
            "ops/reports/auto-improve-sessions/incomplete.json",
            {
                "session_id": "incomplete",
                "path": "ops/reports/auto-improve-sessions/incomplete.json",
                "status": "running",
                "stop_reason": "running",
                "iterations": [{"index": 1, "status": "discarded"}],
                "run_ids": ["run-incomplete"],
            },
        )

        report = self._build_report()
        issue_types = {item["issue_type"] for item in report["issues"]}

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["action_required_count"], 2)
        self.assertIn("stale_session_no_attempts", issue_types)
        self.assertIn("stale_session_incomplete_attempts", issue_types)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_running_ledger_with_resolved_history_is_separate_from_abandoned_ledger(self) -> None:
        self._write_json(
            "runs/run-quarantined/run-ledger.json",
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": "run-quarantined",
                "status": "running",
                "events": [
                    {
                        "ts": "2026-05-21T00:00:00Z",
                        "type": "seed_frozen",
                        "summary": "seed",
                        "artifacts": ["runs/run-quarantined/seed.yaml"],
                        "decision": "ready_for_baseline_capture",
                    },
                    {
                        "ts": "2026-05-21T00:01:00Z",
                        "type": "history_status_updated",
                        "summary": "quarantined",
                        "artifacts": ["runs/run-quarantined/run-ledger.json"],
                        "decision": "quarantined",
                    },
                ],
            },
        )
        self._write_json(
            "runs/run-quarantined/promotion-report.json",
            {"history": {"status": "quarantined"}},
        )
        self._write_json(
            "runs/run-abandoned/run-ledger.json",
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": "run-abandoned",
                "status": "running",
                "events": [
                    {
                        "ts": "2026-05-21T00:00:00Z",
                        "type": "seed_frozen",
                        "summary": "seed",
                        "artifacts": ["runs/run-abandoned/seed.yaml"],
                        "decision": "ready_for_baseline_capture",
                    },
                    {
                        "ts": "2026-05-21T00:01:00Z",
                        "type": "baseline_captured",
                        "summary": "baseline",
                        "artifacts": ["runs/run-abandoned/baseline-eval.json"],
                        "decision": "baseline_ready",
                    },
                ],
            },
        )

        report = self._build_report()
        by_type = {item["issue_type"]: item for item in report["issues"]}

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["resolved_by_history_count"], 1)
        self.assertEqual(report["summary"]["action_required_count"], 1)
        self.assertEqual(
            by_type["ledger_history_status_mismatch"]["resolution_status"],
            "resolved_by_history",
        )
        self.assertEqual(
            by_type["ledger_baseline_only_abandoned"]["resolution_status"],
            "action_required",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_apply_closes_stale_session_and_history_resolved_ledger(self) -> None:
        session_path = "ops/reports/auto-improve-sessions/no-attempts.json"
        self._write_json(
            session_path,
            self._sample_session(session_id="no-attempts", rel_path=session_path),
        )
        self._write_json(
            "runs/run-quarantined/run-ledger.json",
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": "run-quarantined",
                "status": "running",
                "events": [
                    {
                        "ts": "2026-05-21T00:00:00Z",
                        "type": "seed_frozen",
                        "summary": "seed",
                        "artifacts": ["runs/run-quarantined/seed.yaml"],
                        "decision": "ready_for_baseline_capture",
                    },
                    {
                        "ts": "2026-05-21T00:01:00Z",
                        "type": "history_status_updated",
                        "summary": "quarantined",
                        "artifacts": ["runs/run-quarantined/run-ledger.json"],
                        "decision": "quarantined",
                    },
                ],
            },
        )
        self._write_json(
            "runs/run-quarantined/promotion-report.json",
            {"history": {"status": "quarantined"}},
        )

        report = build_report(
            GoalRuntimeStaleCloseoutRequest(
                vault=self.vault,
                apply=True,
                context=fixed_context(),
            )
        )
        session = json.loads((self.vault / session_path).read_text(encoding="utf-8"))
        ledger = json.loads(
            (self.vault / "runs/run-quarantined/run-ledger.json").read_text(encoding="utf-8")
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["cleanup"]["updated_count"], 2)
        self.assertEqual(report["summary"]["issue_count"], 0)
        self.assertEqual(session["status"], "blocked")
        self.assertEqual(session["stop_reason"], "stale_closeout_required")
        self.assertEqual(
            session["metadata"]["stale_closeout"]["closed_at"],
            "2026-05-21T00:00:00Z",
        )
        self.assertEqual(ledger["status"], "blocked")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
