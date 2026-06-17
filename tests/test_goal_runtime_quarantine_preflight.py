from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.goal_runtime_quarantine_preflight import (
    GoalRuntimeQuarantinePreflightRequest,
    build_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-quarantine-preflight.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 21, 0, 0, tzinfo=dt.UTC),
    )


class GoalRuntimeQuarantinePreflightTests(unittest.TestCase):
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
            GoalRuntimeQuarantinePreflightRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

    def test_build_report_passes_when_quarantined_runs_are_excluded(self) -> None:
        self._write_json(
            "ops/reports/mechanism-review-candidates.json",
            {
                "artifact_kind": "mechanism_review_candidates_report",
                "producer": "ops.scripts.mechanism_review_runtime",
                "status": "pass",
                "diagnostics": {
                    "skipped_runs": [],
                    "excluded_runs": [
                        {
                            "run_id": "run-quarantined",
                            "status": "quarantined",
                            "reason": "superseded contaminated evidence",
                            "path": "runs/run-quarantined/promotion-report.json",
                        },
                        {
                            "run_id": "run-archived",
                            "status": "archived",
                            "reason": "superseded by retry",
                            "path": "runs/archive/run-archived/promotion-report.json",
                        },
                    ],
                },
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["excluded_run_count"], 2)
        self.assertEqual(report["summary"]["quarantined_run_count"], 1)
        self.assertEqual(report["summary"]["operator_decision_required_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_unresolved_history_cleanup(self) -> None:
        self._write_json(
            "ops/reports/mechanism-review-candidates.json",
            {
                "artifact_kind": "mechanism_review_candidates_report",
                "producer": "ops.scripts.mechanism_review_runtime",
                "status": "attention",
                "diagnostics": {
                    "skipped_runs": [
                        {
                            "run_id": "run-missing-input",
                            "reason": "run_artifact_invalid",
                            "path": "runs/run-missing-input/candidate-eval.json",
                            "detail": "missing artifact",
                            "triage": {
                                "status": "operator_decision_required",
                                "recommended_action": "restore_missing_artifact_or_archive_run_history",
                                "options": [
                                    "restore the missing artifact from ledgered evidence",
                                    "archive or quarantine the promotion report history",
                                ],
                            },
                        }
                    ],
                    "excluded_runs": [],
                },
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["operator_decision_required_count"], 1)
        self.assertEqual(report["unresolved_history_cleanup"][0]["run_id"], "run-missing-input")
        self.assertIn("archive", report["recommended_next_action"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
