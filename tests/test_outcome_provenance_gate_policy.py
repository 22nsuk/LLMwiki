from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.outcome_provenance_gate_policy import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "outcome-provenance-gate-policy.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 10, 6, 0, tzinfo=dt.UTC),
    )


class OutcomeProvenanceGatePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/outcome-provenance-gate-policy.schema.json")
        self._copy_support_file("ops/schemas/rollback-rehearsal-report.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def test_report_blocks_default_gate_when_outcome_or_provenance_evidence_is_immature(self) -> None:
        self._write_json(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {"attempts_considered": 4, "recent_attempt_count": 4},
                "metrics": {
                    "rework_count": 1,
                    "rollback_signal_count": 2,
                    "rollback_rehearsal_coverage_count": 1,
                    "defect_escape_count": 0,
                    "moving_averages": {"hold": 0.25, "discard": 0.0},
                },
            },
        )
        self._write_json(
            "ops/reports/supply-chain-gate-report.json",
            {"status": "fail", "checks": [{"rule": "ci_install_note_drift", "pass": False}]},
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["current_policy_mode"], "audit_only")
        self.assertEqual(report["default_gate_readiness"]["status"], "blocked")
        self.assertIn("rollback_rehearsal_coverage_gap", report["default_gate_readiness"]["blockers"])
        self.assertIn("supply_chain_gate_not_clean", report["default_gate_readiness"]["blockers"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

    def test_report_marks_default_candidate_when_all_maturity_inputs_are_clean(self) -> None:
        self._write_json(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {"attempts_considered": 1, "recent_attempt_count": 1},
                "metrics": {
                    "rework_count": 0,
                    "rollback_signal_count": 1,
                    "rollback_rehearsal_coverage_count": 1,
                    "defect_escape_count": 0,
                    "moving_averages": {"hold": 0.0, "discard": 0.0},
                },
            },
        )
        self._write_json(
            "ops/reports/supply-chain-gate-report.json",
            {"status": "pass", "checks": [{"rule": "all_required_inputs_exist", "pass": True}]},
        )
        self._write_json(
            "ops/reports/routing-provenance-aggregates/session.json",
            {"loop_health": {"health_flags": []}},
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["recommended_next_mode"], "default_gate_candidate")
        self.assertEqual(report["default_gate_readiness"]["blockers"], [])


if __name__ == "__main__":
    unittest.main()
