from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.session_synopsis import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "session-synopsis.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 10, 0, tzinfo=dt.timezone.utc),
    )


def write_json(vault: Path, rel_path: str, payload: dict[str, Any]) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def seed_synopsis_inputs(vault: Path) -> None:
    write_json(
        vault,
        "ops/reports/auto-improve-readiness.json",
        {
            "can_promote_result": False,
            "next_action": "Trial only; do not promote. Refresh release closeout evidence.",
            "promotion_blockers": [
                {
                    "id": "promotion_blocked_by_release_authority_preflight_failure",
                    "status": "open",
                    "reason": "sealed preflight not clean",
                    "recommended_next_step": "Refresh sealed authority preflight evidence.",
                }
            ],
            "fallback": {"seed_runs": ["run-seed-a"]},
        },
    )
    write_json(
        vault,
        "ops/reports/learning-delta-scoreboard.json",
        {
            "summary": {
                "confirmed_evidence_summary": {
                    "selected_valid_run_ids": ["run-valid-a", "run-valid-b"]
                }
            }
        },
    )
    write_json(
        vault,
        "ops/reports/learning_claim_activation_report.json",
        {
            "summary": {"claim_wording_allowed": False},
            "blocked_predicates": [
                {
                    "id": "learning_claim_unlock_review_not_approved",
                    "status": "blocked",
                    "observed_value": "review_status=required",
                    "required_condition": "unlock review approved",
                    "repair_target": "Approve or auto-approve the unlock review with active evidence.",
                }
            ],
            "anti_slop_preview_ledger": {
                "axes": [
                    {
                        "axis": "context_efficiency",
                        "status": "warn",
                        "current": "session synopsis missing",
                        "required": "session synopsis digest present",
                        "repair_target": "Generate session-synopsis.json.",
                    }
                ]
            },
            "negative_learning_ledger": {
                "patterns": [
                    {
                        "pattern_id": "discard_same_eval",
                        "decisions": ["DISCARD"],
                        "run_ids": ["run-discard-a"],
                        "occurrence_count": 1,
                        "forbidden_repeat": "Do not repeat this run shape.",
                        "repair_target": "Change the evidence predicate before retry.",
                    }
                ]
            },
        },
    )
    write_json(vault, "ops/reports/source-package-clean-extract.json", {"status": "pass"})
    write_json(
        vault,
        "ops/reports/task-improvement-observations/task-20260515-reconciled-improvement-plan/improvement-observations.json",
        {
            "observations": [
                {
                    "observation_id": "automated_slice",
                    "status": "automated",
                    "surface": "ops/scripts/example.py",
                    "suggested_followup": "Automated example slice.",
                }
            ]
        },
    )


class SessionSynopsisTests(unittest.TestCase):
    def test_build_report_summarizes_next_session_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_synopsis_inputs(vault)

            report = build_report(vault, context=fixed_context())

            schema = load_schema(SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["artifact_kind"], "session_synopsis")
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["recent_blocker_count"], 2)
            self.assertEqual(report["summary"]["forbidden_repeat_pattern_count"], 1)
            self.assertEqual(report["summary"]["recommended_seed_run_count"], 1)
            self.assertEqual(report["source_package_replay"]["replay_command"], "make release-source-package-check")
            self.assertFalse(report["next_session_entrypoint"]["promotion_allowed"])
            self.assertFalse(report["next_session_entrypoint"]["claim_wording_allowed"])
            self.assertIn("make session-synopsis", report["next_session_entrypoint"]["first_commands"])
            self.assertEqual(report["recommended_seed_runs"][0]["run_id"], "run-seed-a")

    def test_write_report_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_synopsis_inputs(vault)
            report = build_report(vault, context=fixed_context())

            out_path = write_report(vault, report)

            self.assertEqual(out_path, vault / "ops/reports/session-synopsis.json")
            self.assertTrue(out_path.exists())


if __name__ == "__main__":
    unittest.main()
