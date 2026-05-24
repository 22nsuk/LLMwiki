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
                "runtime_mode": "self_improvement_loop",
            },
            "health": {
                "promotion_status": "blocked",
                "can_promote_result": False,
                "checkpoint_status": "current",
            },
            "blockers": [
                "self-improvement loop certificate incomplete",
                "sealed authority clean pass not verified",
                "promotion_blocked_by_remediation_backlog_open",
            ],
            "runtime_certificate": {
                "status": "pending",
                "mode": "self_improvement_loop",
                "run_mode": "self_improvement_loop",
                "duration_seconds": 21600,
                "certificate_status": "unverified",
                "full_gate_clean": False,
                "missing_evidence": [
                    {
                        "evidence_id": "release_authority",
                        "path": "ops/reports/release-closeout-sealed-rehearsal-check.json",
                        "status": "missing",
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
            self.assertEqual(report["summary"]["goal_runtime_certificate_status"], "pending")
            self.assertEqual(report["summary"]["goal_runtime_mode"], "self_improvement_loop")
            self.assertFalse(report["summary"]["runtime_certificate_full_gate_clean"])
            self.assertEqual(report["goal_runtime_certificate"]["status"], "pending")
            self.assertEqual(
                report["goal_runtime_certificate"]["missing_evidence"][0]["path"],
                "ops/reports/release-closeout-sealed-rehearsal-check.json",
            )
            self.assertFalse(report["next_session_entrypoint"]["promotion_allowed"])
            self.assertFalse(report["next_session_entrypoint"]["claim_wording_allowed"])
            self.assertEqual(
                report["next_session_entrypoint"]["target_runtime_mode"],
                "self_improvement_loop",
            )
            self.assertEqual(
                report["next_session_entrypoint"]["runtime_certificate_status"],
                "pending",
            )
            self.assertFalse(report["next_session_entrypoint"]["runtime_certificate_full_gate_clean"])
            self.assertIn("make auto-improve-goal-status", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make auto-improve-goal-preflight", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make auto-improve-goal-run", report["next_session_entrypoint"]["first_commands"])
            self.assertIn("make goal-runtime-certificate", report["next_session_entrypoint"]["first_commands"])
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
                "self-improvement loop certificate incomplete",
            ]
            write_json(vault, "ops/reports/goal-run-status.json", goal_status)

            report = build_report(vault, context=fixed_context())
            blocker_ids = [blocker["id"] for blocker in report["recent_blockers"]]

            self.assertIn("learning_blocked_by_review_required", blocker_ids)
            self.assertNotIn("goal_status_learning_blocked_by_review_required", blocker_ids)
            self.assertIn("goal_status_self_improvement_loop_certificate_incomplete", blocker_ids)
            self.assertEqual(blocker_ids.count("learning_blocked_by_review_required"), 1)

    def test_readiness_blockers_are_not_dropped_when_goal_status_adds_pressure(self) -> None:
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
                            "id": "execution_blocked_by_no_runnable_proposal",
                            "status": "open",
                            "reason": "no runnable proposal is available",
                            "recommended_next_step": "Refresh mutation proposals.",
                        },
                        {
                            "id": "learning_blocked_by_execution_not_runnable",
                            "status": "open",
                            "reason": "execution is not runnable",
                            "recommended_next_step": "Wait for a runnable proposal.",
                        },
                        {
                            "id": "promotion_blocked_by_artifact_contract_failure",
                            "status": "open",
                            "reason": "artifact freshness attention",
                            "recommended_next_step": "Refresh generated artifacts.",
                        },
                        {
                            "id": "promotion_blocked_by_goal_worktree_guard_failure",
                            "status": "open",
                            "reason": "git worktree dirty",
                            "recommended_next_step": "Commit or clear the worktree.",
                        },
                        {
                            "id": "promotion_blocked_by_remediation_backlog_open",
                            "status": "open",
                            "reason": "remediation backlog is not clear for promotion",
                            "recommended_next_step": "Close remediation backlog items.",
                        },
                    ],
                    "fallback": {"seed_runs": []},
                },
            )
            goal_status = json.loads(
                (vault / "ops/reports/goal-run-status.json").read_text(encoding="utf-8")
            )
            goal_status["blockers"] = [
                "git_worktree_dirty",
                "self-improvement loop certificate incomplete",
            ]
            write_json(vault, "ops/reports/goal-run-status.json", goal_status)

            report = build_report(vault, context=fixed_context())
            blocker_ids = {blocker["id"] for blocker in report["recent_blockers"]}

            self.assertIn("goal_status_git_worktree_dirty", blocker_ids)
            self.assertIn("goal_status_self_improvement_loop_certificate_incomplete", blocker_ids)
            self.assertIn("execution_blocked_by_no_runnable_proposal", blocker_ids)
            self.assertIn("learning_blocked_by_execution_not_runnable", blocker_ids)
            self.assertIn("promotion_blocked_by_artifact_contract_failure", blocker_ids)
            self.assertIn("promotion_blocked_by_goal_worktree_guard_failure", blocker_ids)
            self.assertNotIn("promotion_blocked_by_remediation_backlog_open", blocker_ids)

    def test_completed_terminal_queue_suppresses_finalization_only_blockers(self) -> None:
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
                    "next_action": "Refresh sealed authority preflight.",
                    "diagnostics": {
                        "release_authority_preflight_summary": {
                            "status": "fail",
                            "preflight_status": "binding_pass_authority_blocked",
                            "preflight_mode": "expected_blocked",
                            "distribution_binding_status": "pass",
                            "authority_preflight_status": "blocked",
                            "expected_blocked_preflight": True,
                            "failure_ids": [
                                "batch_release_authority_not_clean_pass",
                                "batch_sealed_release_not_clean_pass",
                            ],
                            "unexpected_failure_ids": [],
                            "blocker_reason_ids": [
                                "release_authority_not_clean_pass",
                                "machine_release_not_allowed",
                                "sealed_release_not_clean_pass",
                            ],
                        }
                    },
                    "promotion_blockers": [
                        {
                            "id": "execution_blocked_by_no_runnable_proposal",
                            "status": "open",
                            "reason": "queue exhausted after successful terminal iteration",
                            "recommended_next_step": "Seed a new runnable proposal.",
                        },
                        {
                            "id": "learning_blocked_by_execution_not_runnable",
                            "status": "open",
                            "reason": "execution is not runnable",
                            "recommended_next_step": "Wait for a runnable proposal.",
                        },
                        {
                            "id": "promotion_blocked_by_artifact_contract_failure",
                            "status": "open",
                            "reason": "artifact freshness attention",
                            "recommended_next_step": "Refresh generated artifacts.",
                        },
                    ],
                    "fallback": {"seed_runs": []},
                },
            )
            goal_status = json.loads(
                (vault / "ops/reports/goal-run-status.json").read_text(encoding="utf-8")
            )
            goal_status["run"] = {
                "run_id": "terminal-loop",
                "status": "completed",
                "runtime_mode": "self_improvement_loop",
            }
            goal_status["blockers"] = [
                "self-improvement loop certificate incomplete",
                "sealed authority clean pass not verified",
            ]
            write_json(vault, "ops/reports/goal-run-status.json", goal_status)
            write_json(
                vault,
                "ops/reports/auto-improve-sessions/terminal-loop.json",
                {
                    "status": "complete",
                    "stop_reason": "queue_exhausted",
                    "iterations": [{"decision": "PROMOTE", "outcome": "promoted"}],
                },
            )
            write_json(
                vault,
                "ops/reports/learning_claim_activation_report.json",
                {
                    "status": "pass",
                    "summary": {
                        "activation_status": "not_candidate",
                        "claim_level": "none",
                        "claim_wording_allowed": False,
                        "gate_effect": "none",
                    },
                    "blocked_predicates": [
                        {
                            "id": "learning_claim_unlock_review_not_approved",
                            "status": "stale",
                            "repair_target": "Approve only for an active learning claim.",
                        }
                    ],
                    "anti_slop_preview_ledger": {
                        "axes": [
                            {
                                "axis": "context_efficiency",
                                "status": "warn",
                                "current": "not bound",
                                "required": "active learning claim",
                                "repair_target": "Bind before claiming learning.",
                            }
                        ]
                    },
                },
            )

            report = build_report(vault, context=fixed_context())
            blocker_ids = {blocker["id"] for blocker in report["recent_blockers"]}
            gap_ids = {gap["id"] for gap in report["evidence_gaps"]}

            self.assertNotIn("execution_blocked_by_no_runnable_proposal", blocker_ids)
            self.assertNotIn("learning_blocked_by_execution_not_runnable", blocker_ids)
            self.assertNotIn(
                "goal_status_self_improvement_loop_certificate_incomplete",
                blocker_ids,
            )
            self.assertNotIn("goal_status_sealed_authority_clean_pass_not_verified", blocker_ids)
            self.assertNotIn("learning_claim_unlock_review_not_approved", blocker_ids)
            self.assertNotIn("learning_claim_unlock_review_not_approved", gap_ids)
            self.assertNotIn("context_efficiency", gap_ids)
            self.assertIn("promotion_blocked_by_artifact_contract_failure", blocker_ids)

    def test_blocked_none_claim_does_not_surface_claim_only_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_synopsis_inputs(vault)
            write_json(
                vault,
                "ops/reports/learning_claim_activation_report.json",
                {
                    "status": "pass",
                    "summary": {
                        "activation_status": "blocked",
                        "claim_level": "none",
                        "claim_wording_allowed": False,
                        "gate_effect": "none",
                    },
                    "blocked_predicates": [
                        {
                            "id": "same_eval_run_count_minimum",
                            "status": "fail",
                            "repair_target": "Keep claim_level=none until typed evidence is complete.",
                        }
                    ],
                    "anti_slop_preview_ledger": {
                        "axes": [
                            {
                                "axis": "context_efficiency",
                                "status": "warn",
                                "current": "not bound",
                                "required": "active learning claim",
                                "repair_target": "Bind before claiming learning.",
                            }
                        ]
                    },
                },
            )

            report = build_report(vault, context=fixed_context())
            blocker_ids = {blocker["id"] for blocker in report["recent_blockers"]}
            gap_ids = {gap["id"] for gap in report["evidence_gaps"]}

            self.assertNotIn("same_eval_run_count_minimum", blocker_ids)
            self.assertNotIn("same_eval_run_count_minimum", gap_ids)
            self.assertNotIn("context_efficiency", gap_ids)

    def test_build_report_can_read_run_local_readiness_and_goal_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_synopsis_inputs(vault)
            write_json(
                vault,
                "runs/goal-local/state/auto-improve-readiness.json",
                {
                    "can_promote_result": True,
                    "next_action": "Run-local evidence is converged.",
                    "promotion_blockers": [],
                    "fallback": {"seed_runs": ["run-local-seed"]},
                },
            )
            write_json(
                vault,
                "runs/goal-local/state/goal-run-status.json",
                {
                    "goal": {"contract_id": "goal-local"},
                    "run": {
                        "run_id": "local-run",
                        "status": "blocked",
                        "runtime_mode": "self_improvement_loop",
                    },
                    "health": {
                        "promotion_status": "ready",
                        "can_promote_result": True,
                        "checkpoint_status": "current",
                    },
                    "promotion_guard": {"can_promote_result": True, "promotion_blockers": []},
                    "blockers": [],
                    "runtime_certificate": {
                        "status": "complete",
                        "mode": "self_improvement_loop",
                        "run_mode": "self_improvement_loop",
                        "duration_seconds": 21600,
                        "certificate_status": "complete",
                        "full_gate_clean": True,
                        "missing_evidence": [],
                    },
                    "periodic_evidence": {"status": "current"},
                    "artifacts": {},
                },
            )

            report = build_report(
                vault,
                context=fixed_context(),
                input_path_overrides={
                    "auto_improve_readiness": "runs/goal-local/state/auto-improve-readiness.json",
                    "goal_run_status": "runs/goal-local/state/goal-run-status.json",
                },
            )

            self.assertEqual(
                report["inputs"]["auto_improve_readiness"],
                "runs/goal-local/state/auto-improve-readiness.json",
            )
            self.assertEqual(
                report["inputs"]["goal_run_status"],
                "runs/goal-local/state/goal-run-status.json",
            )
            self.assertEqual(report["active_goal"]["report_path"], "runs/goal-local/state/goal-run-status.json")
            self.assertEqual(report["summary"]["active_goal_id"], "goal-local")
            self.assertEqual(report["summary"]["active_goal_run_id"], "local-run")
            self.assertEqual(report["recommended_seed_runs"][0]["run_id"], "run-local-seed")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

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
