from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.remediation_backlog import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
from tests.minimal_vault_runtime import seed_minimal_vault


pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "remediation-backlog.schema.json"
OVERRIDE_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "remediation-backlog-status-overrides.schema.json"
)
OVERRIDE_POLICY_PATH = REPO_ROOT / "ops" / "policies" / "remediation-backlog-status-overrides.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 17, 13, 30, tzinfo=dt.timezone.utc),
    )


def write_json(vault: Path, rel_path: str, payload: dict) -> None:
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def seed_backlog_inputs(vault: Path) -> None:
    write_json(
        vault,
        "ops/reports/self-improvement-negative-lessons.json",
        {
            "status": "attention",
            "lessons": [
                {
                    "lesson_id": "blocked_queue_recent_log_overlap",
                    "source": "learning_claim_activation.negative_learning_ledger",
                    "decisions": ["BLOCKED"],
                    "run_ids": [],
                    "occurrence_count": 2,
                    "forbidden_repeat": "Do not repeat this run shape.",
                    "repair_target": "Resolve queue blocked reason recent_log_overlap.",
                    "evidence_digests": [
                        {
                            "path": "ops/reports/auto-improve-readiness.json",
                            "exists": True,
                            "sha256": "a" * 64,
                            "status": "present",
                        }
                    ],
                    "repeat_policy": "do_not_repeat_until_repaired",
                    "backlog_candidate": True,
                }
            ],
        },
    )
    write_json(
        vault,
        "ops/reports/session-synopsis.json",
        {
            "recent_blockers": [
                {
                    "id": "promotion_blocked_by_release_authority_preflight_failure",
                    "source": "auto_improve_readiness.promotion_blockers",
                    "status": "open",
                    "reason": "sealed preflight not clean",
                    "repair_target": "Refresh sealed authority preflight evidence.",
                },
                {
                    "id": "promotion_blocked_by_remediation_backlog_open",
                    "source": "auto_improve_readiness.promotion_blockers",
                    "status": "open",
                    "reason": "remediation backlog is not clear for promotion",
                    "repair_target": "Close remediation backlog items.",
                },
                {
                    "id": "goal_status_promotion_blocked_by_remediation_backlog_open",
                    "source": "goal_run_status.blockers",
                    "status": "open",
                    "reason": "goal status echoes the remediation backlog promotion blocker",
                    "repair_target": "Close remediation backlog items.",
                }
            ]
        },
    )
    write_json(
        vault,
        "ops/reports/learning_claim_activation_report.json",
        {"status": "pass"},
    )
    write_json(
        vault,
        "ops/reports/auto-improve-sessions/auto-session-repeat.json",
        {
            "session_id": "auto-session-repeat",
            "path": "ops/reports/auto-improve-sessions/auto-session-repeat.json",
            "loop_state": {
                "blocking_reason_counts": {"validation_blocked": 2},
                "repeated_blocker_stop": True,
                "repeated_blocker_reason": "validation_blocked",
                "remediation_backlog_path": "ops/reports/remediation-backlog.json",
            },
        },
    )


class RemediationBacklogTests(unittest.TestCase):
    def test_checked_in_status_overrides_policy_validates(self) -> None:
        payload = json.loads(OVERRIDE_POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(validate_with_schema(payload, load_schema(OVERRIDE_SCHEMA_PATH)), [])

    def test_repeated_negative_lessons_and_active_blockers_become_backlog_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}

            self.assertEqual(report["artifact_kind"], "remediation_backlog")
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["backlog_item_count"], 3)
            self.assertEqual(report["summary"]["repeated_blocker_count"], 2)
            self.assertEqual(report["summary"]["active_blocker_count"], 1)
            self.assertEqual(report["summary"]["open_total_count"], 3)
            self.assertEqual(report["summary"]["open_promotion_count"], 1)
            self.assertEqual(report["summary"]["open_repeat_count"], 2)
            self.assertIn("negative_lesson_blocked_queue_recent_log_overlap", items)
            self.assertIn(
                "active_blocker_promotion_blocked_by_release_authority_preflight_failure",
                items,
            )
            self.assertIn(
                "auto_session_repeated_blocker_auto_session_repeat_validation_blocked",
                items,
            )
            self.assertEqual(
                items["negative_lesson_blocked_queue_recent_log_overlap"]["severity"],
                "blocks_repeat",
            )
            self.assertEqual(
                items[
                    "auto_session_repeated_blocker_auto_session_repeat_validation_blocked"
                ]["occurrence_count"],
                2,
            )
            self.assertEqual(
                report["inputs"]["status_overrides"],
                "ops/policies/remediation-backlog-status-overrides.json",
            )
            self.assertEqual(report["inputs"]["goal_worktree_guard"], "ops/reports/goal-worktree-guard.json")
            self.assertNotEqual(report["input_fingerprints"]["auto_improve_sessions"], "missing")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_status_overrides_can_close_repeated_items_without_editing_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)
            write_json(
                vault,
                "ops/policies/remediation-backlog-status-overrides.json",
                {
                    "$schema": "ops/schemas/remediation-backlog-status-overrides.schema.json",
                    "overrides": [
                        {
                            "item_id": "negative_lesson_blocked_queue_recent_log_overlap",
                            "status": "closed",
                            "reason": "Repair evidence accepted; do not block this repeat pattern.",
                            "evidence_paths": [
                                "ops/reports/task-improvement-observations/example.json"
                            ],
                        }
                    ],
                },
            )

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}
            closed_item = items["negative_lesson_blocked_queue_recent_log_overlap"]

            self.assertEqual(closed_item["status"], "closed")
            self.assertEqual(
                closed_item["next_action"],
                "Repair evidence accepted; do not block this repeat pattern.",
            )
            self.assertIn(
                "ops/reports/task-improvement-observations/example.json",
                closed_item["evidence_paths"],
            )
            self.assertEqual(report["summary"]["open_total_count"], 2)
            self.assertEqual(report["summary"]["open_promotion_count"], 1)
            self.assertEqual(report["summary"]["open_repeat_count"], 1)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_current_mutation_queue_unblock_closes_recent_log_overlap_repeat_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)
            write_json(
                vault,
                "ops/reports/auto-improve-sessions/stage3-auto-promotion-20260524.json",
                {
                    "session_id": "stage3-auto-promotion-20260524",
                    "stop_reason": "repeated_blocker_backlog_required",
                    "attempted_proposal_ids": [],
                    "run_ids": [],
                    "iterations": [],
                    "loop_state": {
                        "blocking_reason_counts": {"blocked_queue_recent_log_overlap": 2},
                        "repeated_blocker_stop": True,
                        "repeated_blocker_reason": "blocked_queue_recent_log_overlap",
                    },
                },
            )
            write_json(
                vault,
                "ops/reports/mutation-proposals.json",
                {
                    "status": "pass",
                    "source_tree_fingerprint": release_source_tree_fingerprint(vault),
                    "proposals": [
                        {
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime"
                            ),
                            "failure_mode": "recent_log_overlap_queue_blocked",
                            "blocked_by": [],
                        }
                    ],
                },
            )

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}

            self.assertEqual(
                items["negative_lesson_blocked_queue_recent_log_overlap"]["status"],
                "closed",
            )
            self.assertEqual(
                items[
                    "auto_session_repeated_blocker_stage3_auto_promotion_20260524_"
                    "blocked_queue_recent_log_overlap"
                ]["status"],
                "closed",
            )
            self.assertIn(
                "ops/reports/mutation-proposals.json",
                items["negative_lesson_blocked_queue_recent_log_overlap"]["evidence_paths"],
            )
            self.assertEqual(
                items[
                    "auto_session_repeated_blocker_auto_session_repeat_validation_blocked"
                ]["status"],
                "open",
            )
            self.assertEqual(report["summary"]["open_repeat_count"], 1)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_current_runnable_repair_closes_recent_log_overlap_repeat_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)
            write_json(
                vault,
                "ops/reports/mutation-proposals.json",
                {
                    "status": "pass",
                    "source_tree_fingerprint": release_source_tree_fingerprint(vault),
                    "proposals": [
                        {
                            "proposal_id": (
                                "next_run_failure_repair__mechanism-run-validation-runtime__"
                                "equal-score-secondary-eligibility"
                            ),
                            "family": "next_run_failure_repair",
                            "failure_mode": "next_run_failure_repair",
                            "blocked_by": [],
                        }
                    ],
                },
            )

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}

            self.assertEqual(
                items["negative_lesson_blocked_queue_recent_log_overlap"]["status"],
                "closed",
            )
            self.assertIn(
                "ops/reports/mutation-proposals.json",
                items["negative_lesson_blocked_queue_recent_log_overlap"]["evidence_paths"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_clean_auto_promotion_manifest_closes_legacy_promotion_report_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_json(
                vault,
                "ops/reports/self-improvement-negative-lessons.json",
                {
                    "status": "attention",
                    "lessons": [
                        {
                            "lesson_id": "hold_legacy_promotion_report",
                            "source": "learning_claim_activation.negative_learning_ledger",
                            "decisions": ["HOLD"],
                            "run_ids": ["run-one", "run-two"],
                            "occurrence_count": 2,
                            "forbidden_repeat": "Do not repeat this run shape.",
                            "repair_target": (
                                "Change the mechanism or evidence predicate before rerunning "
                                "another HOLD attempt with same_eval_reason_code="
                                "legacy_promotion_report."
                            ),
                            "evidence_digests": [],
                            "repeat_policy": "do_not_repeat_until_repaired",
                            "backlog_candidate": True,
                        }
                    ],
                },
            )
            write_json(vault, "ops/reports/session-synopsis.json", {"recent_blockers": []})
            write_json(vault, "ops/reports/learning_claim_activation_report.json", {"status": "pass"})
            write_json(
                vault,
                "ops/policies/remediation-backlog-status-overrides.json",
                {
                    "$schema": "ops/schemas/remediation-backlog-status-overrides.schema.json",
                    "overrides": [],
                },
            )
            write_json(
                vault,
                "build/release/release-auto-promotion-ready-manifest.json",
                {
                    "artifact_kind": "release_auto_promotion_ready_manifest",
                    "status": "pass",
                    "source_tree_fingerprint": release_source_tree_fingerprint(vault),
                    "auto_promotion_status": "allowed",
                    "unattended_promotion_allowed": True,
                    "blockers": [],
                    "failures": [],
                },
            )

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}

            self.assertEqual(
                items["negative_lesson_hold_legacy_promotion_report"]["status"],
                "closed",
            )
            self.assertIn(
                "build/release/release-auto-promotion-ready-manifest.json",
                items["negative_lesson_hold_legacy_promotion_report"]["evidence_paths"],
            )
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["open_total_count"], 0)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_active_learning_signoff_defers_learning_review_backlog_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_json(vault, "ops/reports/self-improvement-negative-lessons.json", {"lessons": []})
            write_json(
                vault,
                "ops/reports/session-synopsis.json",
                {
                    "recent_blockers": [
                        {
                            "id": "learning_blocked_by_review_required",
                            "source": "auto_improve_readiness.promotion_blockers",
                            "status": "open",
                            "reason": "learning uncertainty requires review",
                            "repair_target": "Record accepted risk or improve learning metrics.",
                        },
                        {
                            "id": "goal_status_learning_blocked_by_review_required",
                            "source": "goal_run_status.blockers",
                            "status": "open",
                            "reason": "goal status mirrors the learning review blocker",
                            "repair_target": "Record accepted risk or improve learning metrics.",
                        }
                    ]
                },
            )
            write_json(vault, "ops/reports/learning_claim_activation_report.json", {"status": "pass"})
            write_json(
                vault,
                "ops/reports/learning-readiness-signoff.json",
                {
                    "artifact_kind": "learning_readiness_signoff",
                    "linked_blocker_id": "learning_blocked_by_review_required",
                    "accepted_by": "operator@example.test",
                    "accepted_at": "2026-05-17T11:00:00Z",
                    "expires_at": "2026-05-24T11:00:00Z",
                    "risk_owner": "runtime-maintainer",
                },
            )

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}

            self.assertEqual(
                items["active_blocker_learning_blocked_by_review_required"]["status"],
                "deferred",
            )
            self.assertEqual(
                items["active_blocker_goal_status_learning_blocked_by_review_required"][
                    "status"
                ],
                "deferred",
            )
            self.assertIn(
                "ops/reports/learning-readiness-signoff.json",
                items["active_blocker_learning_blocked_by_review_required"]["evidence_paths"],
            )
            self.assertIn(
                "ops/reports/learning-readiness-signoff.json",
                items["active_blocker_goal_status_learning_blocked_by_review_required"][
                    "evidence_paths"
                ],
            )
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["open_total_count"], 0)
            self.assertEqual(report["summary"]["open_promotion_count"], 0)
            self.assertEqual(report["summary"]["open_repeat_count"], 0)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_current_clean_goal_worktree_guard_closes_historical_dirty_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_json(vault, "ops/reports/self-improvement-negative-lessons.json", {"lessons": []})
            write_json(
                vault,
                "ops/reports/session-synopsis.json",
                {
                    "recent_blockers": [
                        {
                            "id": "promotion_blocked_by_goal_worktree_guard_failure",
                            "source": "auto_improve_readiness.promotion_blockers",
                            "status": "open",
                            "reason": "historical dirty worktree blocker",
                            "repair_target": "Refresh goal worktree guard evidence.",
                        },
                        {
                            "id": "goal_status_promotion_blocked_by_goal_worktree_guard_failure",
                            "source": "goal_run_status.blockers",
                            "status": "open",
                            "reason": "goal status echoes historical dirty worktree blocker",
                            "repair_target": "Refresh goal worktree guard evidence.",
                        },
                        {
                            "id": "promotion_blocked_by_release_batch_manifest_failure",
                            "source": "auto_improve_readiness.promotion_blockers",
                            "status": "open",
                            "reason": "batch manifest still needs review",
                            "repair_target": "Refresh batch manifest evidence.",
                        },
                    ]
                },
            )
            write_json(vault, "ops/reports/learning_claim_activation_report.json", {"status": "pass"})
            write_json(
                vault,
                "ops/reports/goal-worktree-guard.json",
                {
                    "artifact_kind": "goal_worktree_guard",
                    "status": "pass",
                    "git": {"dirty_entry_count": 0},
                    "decisions": {
                        "can_promote_result": True,
                        "promotion_blockers": [],
                    },
                    "blockers": [],
                },
            )

            report = build_report(vault, context=fixed_context())
            items = {item["item_id"]: item for item in report["items"]}

            self.assertEqual(
                items["active_blocker_promotion_blocked_by_goal_worktree_guard_failure"][
                    "status"
                ],
                "closed",
            )
            self.assertEqual(
                items[
                    "active_blocker_goal_status_promotion_blocked_by_goal_worktree_guard_failure"
                ]["status"],
                "closed",
            )
            self.assertEqual(
                items["active_blocker_promotion_blocked_by_release_batch_manifest_failure"][
                    "status"
                ],
                "open",
            )
            self.assertEqual(report["summary"]["open_promotion_count"], 1)
            self.assertIn(
                "ops/reports/goal-worktree-guard.json",
                items["active_blocker_promotion_blocked_by_goal_worktree_guard_failure"][
                    "evidence_paths"
                ],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_verified_certificate_closes_incomplete_certificate_item_from_canonical_report(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_json(vault, "ops/reports/self-improvement-negative-lessons.json", {"lessons": []})
            write_json(
                vault,
                "ops/reports/session-synopsis.json",
                {
                    "recent_blockers": [
                        {
                            "id": "goal_status_self_improvement_loop_certificate_incomplete",
                            "source": "goal_run_status.blockers",
                            "status": "open",
                            "reason": "self-improvement loop certificate incomplete",
                            "repair_target": "Refresh goal runtime certificate.",
                        }
                    ]
                },
            )
            write_json(vault, "ops/reports/learning_claim_activation_report.json", {"status": "pass"})
            certificate = {
                "artifact_kind": "goal_runtime_certificate",
                "producer": "ops.scripts.goal_runtime_certificate_report",
                "status": "pass",
                "goal": {"contract_path": "runs/goal-live/state/codex-goal-contract.json"},
                "certificate": {"verification_status": "already_verified", "eligible": True},
                "contract_update": {"runtime_certificate_verified_after": True},
                "run": {"status_report_path": "runs/goal-live/state/goal-run-status.json"},
                "session_evidence": {"path": "ops/reports/auto-improve-sessions/live.json"},
                "run_artifacts": {
                    "checks": [
                        {"path": "runs/goal-live/state/audit-log.jsonl", "status": "pass"}
                    ]
                },
                "evidence_paths": [
                    {"path": "ops/reports/auto-improve-readiness.json", "status": "present"}
                ],
                "blockers": [],
            }
            write_json(vault, "ops/reports/goal-runtime-certificate.json", certificate)

            report = build_report(vault, context=fixed_context())
            item = report["items"][0]
            self.assertEqual(item["status"], "closed")
            self.assertEqual(
                item["next_action"], "Verified goal-runtime-certificate evidence is present."
            )
            self.assertEqual(report["status"], "pass")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_clean_goal_run_defers_certificate_item_until_release_authority_is_sealed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_json(vault, "ops/reports/self-improvement-negative-lessons.json", {"lessons": []})
            write_json(
                vault,
                "ops/reports/session-synopsis.json",
                {
                    "recent_blockers": [
                        {
                            "id": "goal_status_self_improvement_loop_certificate_incomplete",
                            "source": "goal_run_status.blockers",
                            "status": "open",
                            "reason": "self-improvement loop certificate incomplete",
                            "repair_target": "Refresh goal runtime certificate.",
                        }
                    ]
                },
            )
            write_json(vault, "ops/reports/learning_claim_activation_report.json", {"status": "pass"})
            write_json(
                vault,
                "ops/reports/goal-runtime-certificate.json",
                {
                    "artifact_kind": "goal_runtime_certificate",
                    "producer": "ops.scripts.goal_runtime_certificate_report",
                    "status": "attention",
                    "goal": {"contract_path": "runs/goal-live/state/codex-goal-contract.json"},
                    "run": {
                        "status_report_path": "runs/goal-live/state/goal-run-status.json",
                        "run_id": "goal-live",
                        "run_status": "completed",
                    },
                    "certificate": {"verification_status": "blocked", "eligible": False},
                    "contract_update": {"runtime_certificate_verified_after": False},
                    "session_evidence": {"status": "clean"},
                    "run_artifacts": {"status": "clean"},
                    "blockers": [
                        "can_promote_result is not clean for runtime certificate",
                        "sealed authority clean pass is not verified for runtime certificate",
                        "promotion guard still has blockers",
                    ],
                },
            )

            report = build_report(vault, context=fixed_context())
            item = report["items"][0]

            self.assertEqual(item["status"], "deferred")
            self.assertIn("post-seal runtime-certificate gate", item["next_action"])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["open_promotion_count"], 0)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_can_read_run_local_session_and_negative_lessons(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)
            write_json(
                vault,
                "runs/goal-local/state/self-improvement-negative-lessons.json",
                {
                    "status": "pass",
                    "lessons": [],
                },
            )
            write_json(
                vault,
                "runs/goal-local/state/session-synopsis.json",
                {
                    "recent_blockers": [
                        {
                            "id": "local_release_blocker",
                            "source": "auto_improve_readiness.promotion_blockers",
                            "status": "open",
                            "reason": "local evidence has not converged",
                            "repair_target": "Converge run-local readiness and backlog.",
                        }
                    ]
                },
            )

            report = build_report(
                vault,
                context=fixed_context(),
                negative_lessons_path="runs/goal-local/state/self-improvement-negative-lessons.json",
                session_synopsis_path="runs/goal-local/state/session-synopsis.json",
            )

            items = {item["item_id"]: item for item in report["items"]}
            self.assertIn("active_blocker_local_release_blocker", items)
            self.assertEqual(
                items["active_blocker_local_release_blocker"]["evidence_paths"],
                ["runs/goal-local/state/session-synopsis.json"],
            )
            self.assertEqual(
                report["inputs"]["self_improvement_negative_lessons"],
                "runs/goal-local/state/self-improvement-negative-lessons.json",
            )
            self.assertEqual(
                report["inputs"]["session_synopsis"],
                "runs/goal-local/state/session-synopsis.json",
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_stale_zero_iteration_backlog_guard_stop_does_not_recreate_closed_lesson(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)
            write_json(
                vault,
                "ops/reports/self-improvement-negative-lessons.json",
                {
                    "status": "attention",
                    "lessons": [
                        {
                            "lesson_id": "discard_specific_reason",
                            "source": "learning_claim_activation.negative_learning_ledger",
                            "decisions": ["DISCARD"],
                            "run_ids": ["run-specific"],
                            "occurrence_count": 1,
                            "forbidden_repeat": "Do not repeat this run shape.",
                            "repair_target": "Specific advisory only.",
                            "evidence_digests": [],
                            "repeat_policy": "do_not_repeat_until_repaired",
                            "backlog_candidate": False,
                        }
                    ],
                },
            )
            write_json(
                vault,
                "ops/reports/auto-improve-sessions/stale-zero-iteration-stop.json",
                {
                    "session_id": "stale-zero-iteration-stop",
                    "stop_reason": "repeated_blocker_backlog_required",
                    "attempted_proposal_ids": [],
                    "run_ids": [],
                    "iterations": [],
                    "loop_state": {
                        "blocking_reason_counts": {"discard_unspecified": 2},
                        "repeated_blocker_stop": True,
                        "repeated_blocker_reason": "discard_unspecified",
                    },
                },
            )

            report = build_report(vault, context=fixed_context())
            item_ids = {item["item_id"] for item in report["items"]}

            self.assertNotIn(
                "auto_session_repeated_blocker_stale_zero_iteration_stop_discard_unspecified",
                item_ids,
            )
            self.assertNotIn("negative_lesson_discard_specific_reason", item_ids)
            self.assertIn(
                "auto_session_repeated_blocker_auto_session_repeat_validation_blocked",
                item_ids,
            )

    def test_invalid_status_override_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)
            write_json(
                vault,
                "ops/policies/remediation-backlog-status-overrides.json",
                {
                    "$schema": "ops/schemas/remediation-backlog-status-overrides.schema.json",
                    "overrides": [
                        {
                            "item_id": "negative_lesson_blocked_queue_recent_log_overlap",
                            "status": "open",
                            "reason": "Invalid override status should not be ignored.",
                            "evidence_paths": [],
                        }
                    ],
                },
            )

            with self.assertRaisesRegex(ValueError, "status"):
                build_report(vault, context=fixed_context())

    def test_write_report_validates_and_uses_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_backlog_inputs(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)

            self.assertEqual(destination, vault / "ops" / "reports" / "remediation-backlog.json")
            self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
