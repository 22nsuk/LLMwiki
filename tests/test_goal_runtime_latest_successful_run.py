from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from ops.scripts.mechanism.goal_runtime_latest_successful_run import (
    latest_successful_goal_run,
    main as latest_successful_goal_run_main,
)

pytestmark = pytest.mark.public


class GoalRuntimeLatestSuccessfulRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _write_successful_session(
        self,
        session_id: str,
        *,
        generated_at: str,
        iteration_run_id: str | None = None,
        finalized: bool = True,
        decision: str = "PROMOTE",
        quarantined: bool = False,
    ) -> None:
        iteration_run_id = iteration_run_id or f"{session_id}-run-01"
        promotion_report = f"runs/{iteration_run_id}/promotion-report.json"
        run_telemetry = f"runs/{iteration_run_id}/run-telemetry.json"
        self._write_json(
            f"ops/reports/auto-improve-sessions/{session_id}.json",
            {
                "session_id": session_id,
                "generated_at": generated_at,
                "status": "complete",
                "iterations": [
                    {
                        "index": 1,
                        "run_id": iteration_run_id,
                        "decision": decision,
                        "outcome": "promoted" if decision == "PROMOTE" else "discarded",
                        "quarantined": quarantined,
                        "promotion_report": promotion_report,
                        "run_telemetry": run_telemetry,
                    }
                ],
            },
        )
        self._write_json(
            promotion_report,
            {
                "run_id": iteration_run_id,
                "decision": decision,
            },
        )
        self._write_json(
            run_telemetry,
            {
                "run_id": iteration_run_id,
                "decision": decision,
                "finalized": finalized,
            },
        )

    def test_selects_latest_complete_session_with_finalized_promote_iteration(self) -> None:
        self._write_successful_session(
            "older-session",
            generated_at="2026-06-18T09:00:00Z",
        )
        self._write_successful_session(
            "newer-session",
            generated_at="2026-06-18T10:00:00Z",
            iteration_run_id="newer-session-run-02",
        )

        selected = latest_successful_goal_run(self.vault)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.goal_run_id, "newer-session")
        self.assertEqual(selected.iteration_run_id, "newer-session-run-02")
        self.assertEqual(
            selected.session_report_path,
            "ops/reports/auto-improve-sessions/newer-session.json",
        )

    def test_ignores_unfinalized_or_quarantined_promotions(self) -> None:
        self._write_successful_session(
            "unfinalized-session",
            generated_at="2026-06-18T11:00:00Z",
            finalized=False,
        )
        self._write_successful_session(
            "quarantined-session",
            generated_at="2026-06-18T12:00:00Z",
            quarantined=True,
        )
        self._write_successful_session(
            "usable-session",
            generated_at="2026-06-18T10:00:00Z",
        )

        selected = latest_successful_goal_run(self.vault)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.goal_run_id, "usable-session")

    def test_cli_prints_goal_run_id(self) -> None:
        self._write_successful_session(
            "cli-session",
            generated_at="2026-06-18T10:00:00Z",
        )

        stdout = StringIO()
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.chdir(self.vault)
            with redirect_stdout(stdout):
                status = latest_successful_goal_run_main(["--vault", "."])

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue().strip(), "cli-session")

    def test_cli_json_prints_selected_session_details(self) -> None:
        self._write_successful_session(
            "json-session",
            generated_at="2026-06-18T10:00:00Z",
            iteration_run_id="json-session-run-02",
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            status = latest_successful_goal_run_main(
                ["--vault", str(self.vault), "--format", "json"]
            )

        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["goal_run_id"], "json-session")
        self.assertEqual(payload["iteration_run_id"], "json-session-run-02")

    def test_returns_failure_when_no_successful_session_exists(self) -> None:
        self._write_successful_session(
            "discarded-session",
            generated_at="2026-06-18T10:00:00Z",
            decision="DISCARD",
        )

        stderr = StringIO()
        self.assertIsNone(latest_successful_goal_run(self.vault))
        with redirect_stderr(stderr):
            status = latest_successful_goal_run_main(["--vault", str(self.vault)])
        self.assertEqual(status, 1)
        self.assertIn("no completed successful goal session", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
