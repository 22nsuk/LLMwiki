from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.goal_runtime_certificate_run_id_guard import (
    GoalRuntimeCertificateRunIdGuardRequest,
    build_report,
)

pytestmark = pytest.mark.public


class GoalRuntimeCertificateRunIdGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict[str, object]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def test_default_goal_run_id_cannot_overwrite_existing_run_evidence(self) -> None:
        self._write_json(
            "ops/reports/goal-run-status.json",
            {"run": {"run_id": "completed-run", "status": "completed"}},
        )

        report = build_report(
            GoalRuntimeCertificateRunIdGuardRequest(
                vault=self.vault,
                goal_run_id="auto-improve-trial",
                goal_run_id_origin="file",
            )
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["blockers"],
            ["default_goal_run_id_would_overwrite_existing_run_evidence"],
        )
        self.assertEqual(report["conflicting_run_ids"], ["completed-run"])
        self.assertIn("GOAL_RUN_ID=<completed-run-id>", report["recommended_next_action"])

    def test_explicit_default_goal_run_id_can_replace_existing_run_evidence(self) -> None:
        self._write_json(
            "ops/reports/goal-runtime-certificate.json",
            {"run": {"run_id": "completed-run", "status": "completed"}},
        )

        report = build_report(
            GoalRuntimeCertificateRunIdGuardRequest(
                vault=self.vault,
                goal_run_id="auto-improve-trial",
                goal_run_id_origin="command line",
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["conflicting_run_ids"], ["completed-run"])

    def test_matching_default_goal_run_id_passes(self) -> None:
        self._write_json(
            "ops/reports/goal-run-status.json",
            {"run": {"run_id": "auto-improve-trial", "status": "blocked"}},
        )

        report = build_report(
            GoalRuntimeCertificateRunIdGuardRequest(
                vault=self.vault,
                goal_run_id="auto-improve-trial",
                goal_run_id_origin="file",
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["conflicting_run_ids"], [])

