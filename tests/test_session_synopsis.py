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
                },
                {
                    "id": "promotion_blocked_by_remediation_backlog_open",
                    "status": "open",
                    "reason": "remediation backlog is not clear for promotion",
                    "recommended_next_step": "Close remediation backlog items.",
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
    write_json(
        vault,
        "ops/reports/goal-run-status.json",
        {
            "status": "attention",
            "goal": {
                "contract_id": "goal-20260517-auto-improve-runtime",
                "contract_sha256": "a" * 64,
            },
            "run": {
                "run_id": "20260517-trial",
                "status": "blocked",
                "profile": "30m_trial",
            },
            "health": {
                "promotion_status": "blocked",
                "can_promote_result": False,
                "checkpoint_status": "current",
            },
            "blockers": [
                "profile ladder incomplete",
                "sealed authority clean pass not verified",
                "promotion_blocked_by_remediation_backlog_open",
            ],
            "profile_ladder": {
                "status": "incomplete",
                "current_profile": "30m_trial",
                "run_profile": "30m_trial",
                "verified_profiles": [],
                "highest_verified_profile": "unverified",
                "next_profile_required": "30m_trial",
                "profile_verified_by_promotion_guard": "unverified",
                "profile_guard_consistent": True,
                "sustained_claim_allowed": False,
                "profiles": [
                    {
                        "profile": "30m_trial",
                        "evidence_paths": [
                            {
                                "path": "ops/reports/goal-run-status.json",
                                "status": "present",
                            }
                        ],
                    },
                    {
                        "profile": "5d_sustained",
                        "evidence_paths": [
                            {
                                "path": "ops/reports/release-closeout-sealed-rehearsal-check.json",
                                "status": "missing",
                            }
                        ],
                    },
                ],
            },
            "periodic_evidence": {"status": "not_due"},
            "artifacts": {
                "audit_log_path": "runs/goal-20260517-trial/audit-log.jsonl",
                "resume_metadata_path": "runs/goal-20260517-trial/resume-metadata.json",
            },
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
            self.assertEqual(report["summary"]["recent_blocker_count"], 4)
            self.assertNotIn(
                "promotion_blocked_by_remediation_backlog_open",
                {blocker["id"] for blocker in report["recent_blockers"]},
            )
            self.assertNotIn(
                "goal_status_promotion_blocked_by_remediation_backlog_open",
                {blocker["id"] for blocker in report["recent_blockers"]},
            )
            self.assertEqual(report["summary"]["forbidden_repeat_pattern_count"], 1)
            self.assertEqual(report["summary"]["recommended_seed_run_count"], 1)
            self.assertEqual(
                report["summary"]["active_goal_id"],
                "goal-20260517-auto-improve-runtime",
            )
            self.assertEqual(report["summary"]["active_goal_run_id"], "20260517-trial")
            self.assertEqual(report["active_goal"]["link_status"], "linked")
            self.assertEqual(report["active_goal"]["checkpoint_status"], "current")
            self.assertEqual(report["active_goal"]["periodic_evidence_status"], "not_due")
            self.assertEqual(report["source_package_replay"]["replay_command"], "make release-source-package-check")
            self.assertEqual(report["summary"]["goal_profile_ladder_status"], "incomplete")
            self.assertEqual(report["summary"]["goal_next_profile_required"], "30m_trial")
            self.assertFalse(report["summary"]["sustained_claim_allowed"])
            self.assertEqual(report["goal_profile_ladder"]["status"], "incomplete")
            self.assertEqual(
                report["goal_profile_ladder"]["missing_evidence"][0]["path"],
                "ops/reports/release-closeout-sealed-rehearsal-check.json",
            )
            self.assertFalse(report["next_session_entrypoint"]["promotion_allowed"])
            self.assertFalse(report["next_session_entrypoint"]["claim_wording_allowed"])
            self.assertEqual(
                report["next_session_entrypoint"]["target_profile"],
                "30m_trial",
            )
            self.assertEqual(
                report["next_session_entrypoint"]["profile_ladder_status"],
                "incomplete",
            )
            self.assertFalse(report["next_session_entrypoint"]["sustained_claim_allowed"])
            self.assertIn("make auto-improve-goal-status", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make auto-improve-goal-preflight", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make auto-improve-goal-run", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make goal-profile-verification", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make session-synopsis", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make remediation-backlog", report["next_session_entrypoint"]["first_commands"])
            self.assertTrue(
                any(
                    blocker["source"] == "goal_run_status.blockers"
                    for blocker in report["recent_blockers"]
                )
            )
            self.assertEqual(report["recommended_seed_runs"][0]["run_id"], "run-seed-a")

    def test_readiness_blocker_supersedes_goal_status_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_synopsis_inputs(vault)
            write_json(
                vault,
                "ops/reports/auto-improve-readiness.json",
                {
                    "can_promote_result": False,
                    "next_action": "Trial only; do not promote.",
                    "promotion_blockers": [
                        {
                            "id": "learning_blocked_by_review_required",
                            "status": "open",
                            "reason": "operator review required",
                            "recommended_next_step": "Review bounded learning evidence.",
                        }
                    ],
                    "fallback": {"seed_runs": []},
                },
            )
            goal_status = json.loads(
                (vault / "ops/reports/goal-run-status.json").read_text(encoding="utf-8")
            )
            goal_status["blockers"] = [
                "learning_blocked_by_review_required",
                "profile ladder incomplete",
            ]
            write_json(vault, "ops/reports/goal-run-status.json", goal_status)

            report = build_report(vault, context=fixed_context())
            blocker_ids = [blocker["id"] for blocker in report["recent_blockers"]]

            self.assertIn("learning_blocked_by_review_required", blocker_ids)
            self.assertNotIn("goal_status_learning_blocked_by_review_required", blocker_ids)
            self.assertIn("goal_status_profile_ladder_incomplete", blocker_ids)
            self.assertEqual(blocker_ids.count("learning_blocked_by_review_required"), 1)

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
