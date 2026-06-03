from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.goal_runtime_run_admission import (
    GoalRuntimeRunAdmissionRequest,
    build_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-run-admission.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 21, 0, 0, tzinfo=dt.UTC),
    )


def _canonical_json_digest(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class GoalRuntimeRunAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._seed_passable_start_reports()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _seed_passable_start_reports(self) -> None:
        self._write_json(
            "tmp/goal-runtime-clean-transient.json",
            {
                "artifact_kind": "goal_runtime_clean_transient",
                "status": "pass",
                "summary": {
                    "apply": True,
                    "failed_count": 0,
                    "would_remove_count": 0,
                },
            },
        )
        self._write_json(
            "tmp/goal-runtime-quarantine-preflight.json",
            {
                "artifact_kind": "goal_runtime_quarantine_preflight",
                "status": "pass",
                "summary": {
                    "operator_decision_required_count": 0,
                    "excluded_run_count": 1,
                    "quarantined_run_count": 1,
                    "invalid_exclusion_count": 0,
                },
            },
        )
        self._write_json(
            "tmp/goal-runtime-fixed-point-check.json",
            {
                "artifact_kind": "goal_runtime_fixed_point_check",
                "status": "pass",
                "summary": {"failed_check_count": 0},
            },
        )
        self._write_json(
            "ops/reports/goal-worktree-guard.json",
            {
                "artifact_kind": "goal_worktree_guard",
                "status": "pass",
                "git": {"dirty_entry_count": 0},
                "decisions": {
                    "can_execute_goal_runtime": True,
                    "can_promote_result": True,
                    "fatal_blockers": [],
                    "promotion_blockers": [],
                },
            },
        )
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [{"proposal_id": "repair-runtime"}],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 1,
                        "selected_runnable_count": 1,
                        "blocked_available_count": 0,
                        "blocked_reason_counts": [],
                    }
                },
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "execution_readiness": {
                    "can_run": True,
                    "runnable_proposal_count": 1,
                    "reasons": [],
                },
                "can_promote_result": False,
                "promotion_blockers": [
                    {"id": "promotion_blocked_by_goal_runtime_certificate_incomplete"}
                ],
            },
        )
        self._write_json(
            "ops/reports/remediation-backlog.json",
            {
                "artifact_kind": "remediation_backlog",
                "status": "attention",
                "summary": {
                    "open_total_count": 1,
                    "open_promotion_count": 1,
                    "open_repeat_count": 0,
                    "active_blocker_count": 1,
                },
                "items": [
                    {
                        "blocker_id": "goal_status_self_improvement_loop_certificate_incomplete",
                        "status": "open",
                    }
                ],
            },
        )
        contract = {
            "execution_policy": {
                "learning_uncertain": {
                    "allow_bounded_trial": True,
                    "requires_explicit_authorization": True,
                    "authorization_source": "codex_goal_contract",
                    "command_flag": "--allow-learning-uncertain",
                },
                "post_promote_maintenance": {
                    "minimum_meaningful_cycles": 1,
                    "allow_zero_cycles_for_certificate": False,
                    "completion_condition": "post_promote_observation",
                    "command_flag": "--post-promote-maintenance-cycles",
                },
            },
            "goal_backend": {"process_persistent": True},
            "runtime": {"certificate_status": "verified"},
            "promotion_guard": {"runtime_certificate_verified": True},
        }
        contract_digest = _canonical_json_digest(contract)
        self._write_json("ops/reports/codex-goal-contract.json", contract)
        self._write_json(
            "ops/reports/goal-run-status.json",
            {
                "artifact_kind": "goal_run_status",
                "currentness": {"status": "current"},
                "goal": {
                    "contract_path": "ops/reports/codex-goal-contract.json",
                    "contract_sha256": contract_digest,
                    "contract_status": "loaded",
                    "backend": {"process_persistent": True},
                },
            },
        )
        self._write_json(
            "ops/reports/goal-runtime-certificate.json",
            {
                "artifact_kind": "goal_runtime_certificate",
                "status": "pass",
                "currentness": {"status": "current"},
                "goal": {
                    "contract_path": "ops/reports/codex-goal-contract.json",
                    "contract_sha256_after": contract_digest,
                },
                "run": {"status_report_path": "ops/reports/goal-run-status.json"},
                "certificate": {
                    "verification_status": "already_verified",
                    "eligible": True,
                },
                "contract_update": {"runtime_certificate_verified_after": True},
                "blockers": [],
            },
        )

    def _build_report(
        self,
        *,
        resume_session_id: str = "",
        maintenance_action_plan_path: str = "",
        allow_learning_uncertain: bool = False,
    ) -> dict:
        return build_report(
            GoalRuntimeRunAdmissionRequest(
                vault=self.vault,
                resume_session_id=resume_session_id,
                maintenance_action_plan_path=maintenance_action_plan_path,
                allow_learning_uncertain=allow_learning_uncertain,
                context=fixed_context(),
            )
        )

    def test_build_report_allows_bounded_start_while_promotion_remains_blocked(self) -> None:
        report = self._build_report()

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["start_status"], "pass")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "bounded_repair_allowed")
        self.assertTrue(report["decisions"]["can_start_goal_runtime"])
        self.assertTrue(report["decisions"]["can_mutate_candidate"])
        self.assertFalse(report["decisions"]["can_promote_result_later"])
        self.assertFalse(report["decisions"]["should_pause_before_run"])
        self.assertEqual(report["summary"]["start_blocker_count"], 0)
        self.assertGreater(report["summary"]["promotion_blocker_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_start_when_readiness_and_mutation_queue_are_stale(self) -> None:
        mutation_report = {
            "artifact_kind": "mutation_proposals_report",
            "source_tree_fingerprint": "current-source",
            "currentness": {"status": "current"},
            "proposals": [{"proposal_id": "repair-current"}],
            "diagnostics": {
                "queue_selection": {
                    "runnable_available_count": 1,
                    "selected_runnable_count": 1,
                    "blocked_available_count": 0,
                    "blocked_reason_counts": [],
                }
            },
        }
        self._write_json("ops/reports/mutation-proposals.json", mutation_report)
        readiness = {
            "artifact_kind": "auto_improve_readiness_report",
            "source_tree_fingerprint": "stale-source",
            "currentness": {"status": "current"},
            "input_fingerprints": {
                "mutation_proposal_report": "0" * 64,
            },
            "execution_readiness": {
                "can_run": True,
                "runnable_proposal_count": 1,
                "reasons": [],
            },
            "queue": {
                "runnable_proposal_ids": ["repair-stale"],
            },
            "can_promote_result": False,
            "promotion_blockers": [
                {"id": "promotion_blocked_by_goal_runtime_certificate_incomplete"}
            ],
        }
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["start_status"], "fail")
        self.assertEqual(report["admission_mode"], "blocked")
        self.assertFalse(report["decisions"]["can_start_goal_runtime"])
        check = next(
            item
            for item in report["checks"]
            if item["id"] == "start_readiness_mutation_proposal_current"
        )
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["observed"]["mutation_source_tree_fingerprint"], "current-source")
        self.assertEqual(check["observed"]["readiness_source_tree_fingerprint"], "stale-source")
        self.assertEqual(check["observed"]["mutation_selected_runnable_proposal_ids"], ["repair-current"])
        self.assertEqual(check["observed"]["readiness_runnable_proposal_ids"], ["repair-stale"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_start_for_over_budget_non_structural_proposal(self) -> None:
        target = self.vault / "ops" / "scripts" / "mechanism" / "giant_runtime.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "\n".join(f"VALUE_{index} = {index}" for index in range(901)) + "\n",
            encoding="utf-8",
        )
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [
                    {
                        "proposal_id": "regular-runtime-change",
                        "primary_targets": [
                            "ops/scripts/mechanism/giant_runtime.py",
                        ],
                        "supporting_targets": [],
                    }
                ],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 1,
                        "selected_runnable_count": 1,
                        "blocked_available_count": 0,
                        "blocked_reason_counts": [],
                    }
                },
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["start_status"], "fail")
        check = next(
            item
            for item in report["checks"]
            if item["id"] == "start_structural_complexity_budget_clear"
        )
        self.assertEqual(check["status"], "fail")
        self.assertFalse(check["observed"]["structural_complexity_repair_allowed"])
        self.assertEqual(
            check["observed"]["over_budget_targets"][0]["path"],
            "ops/scripts/mechanism/giant_runtime.py",
        )
        self.assertIn(
            "nonempty_line_count_total",
            check["observed"]["over_budget_targets"][0]["over_budget_metrics"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_allows_over_budget_target_for_explicit_structural_repair(self) -> None:
        target = self.vault / "ops" / "scripts" / "mechanism" / "giant_runtime.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "\n".join(f"VALUE_{index} = {index}" for index in range(901)) + "\n",
            encoding="utf-8",
        )
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [
                    {
                        "proposal_id": (
                            "next_run_failure_repair__giant-runtime__"
                            "structural-complexity-non-regression"
                        ),
                        "failure_mode": "next_run_failure_repair",
                        "primary_targets": [
                            "ops/scripts/mechanism/giant_runtime.py",
                        ],
                        "supporting_targets": [],
                        "metrics_triggered": [
                            "next_run_failure_repair",
                            "structural_complexity_non_regression",
                        ],
                        "must_change_budget_signal": {
                            "signal": (
                                "auto_improve_session.next_run_decisions."
                                "structural_complexity_non_regression"
                            ),
                            "expected_change": "resolved_or_superseded",
                        },
                    }
                ],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 1,
                        "selected_runnable_count": 1,
                        "blocked_available_count": 0,
                        "blocked_reason_counts": [],
                    }
                },
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["start_status"], "pass")
        self.assertEqual(report["admission_mode"], "bounded_repair_allowed")
        check = next(
            item
            for item in report["checks"]
            if item["id"] == "start_structural_complexity_budget_clear"
        )
        self.assertEqual(check["status"], "pass")
        self.assertTrue(check["observed"]["structural_complexity_repair_allowed"])
        self.assertEqual(check["observed"]["status"], "attention")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_ignores_generated_canonical_supporting_target_for_structural_budget(
        self,
    ) -> None:
        source_target = self.vault / "ops" / "scripts" / "mechanism" / "small_runtime.py"
        source_target.parent.mkdir(parents=True, exist_ok=True)
        source_target.write_text("def run() -> None:\n    return None\n", encoding="utf-8")
        generated_target = self.vault / "ops" / "script-output-surfaces.json"
        generated_target.parent.mkdir(parents=True, exist_ok=True)
        generated_target.write_text(
            "\n".join(f'"generated_{index}": true' for index in range(1000)) + "\n",
            encoding="utf-8",
        )
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [
                    {
                        "proposal_id": "small-runtime-change",
                        "primary_targets": [
                            "ops/scripts/mechanism/small_runtime.py",
                        ],
                        "supporting_targets": [
                            "ops/script-output-surfaces.json",
                        ],
                    }
                ],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 1,
                        "selected_runnable_count": 1,
                        "blocked_available_count": 0,
                        "blocked_reason_counts": [],
                    }
                },
            },
        )

        report = self._build_report()

        self.assertNotEqual(report["start_status"], "fail")
        check = next(
            item
            for item in report["checks"]
            if item["id"] == "start_structural_complexity_budget_clear"
        )
        self.assertEqual(check["status"], "pass")
        self.assertEqual(
            check["observed"]["target_paths"],
            ["ops/scripts/mechanism/small_runtime.py"],
        )
        self.assertEqual(
            check["observed"]["ignored_generated_canonical_targets"],
            ["ops/script-output-surfaces.json"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_exposes_distinct_promotion_ready_statuses(self) -> None:
        readiness = json.loads((self.vault / "ops/reports/auto-improve-readiness.json").read_text(encoding="utf-8"))
        readiness["can_promote_result"] = True
        readiness["promotion_blockers"] = []
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)
        backlog = json.loads((self.vault / "ops/reports/remediation-backlog.json").read_text(encoding="utf-8"))
        backlog["status"] = "pass"
        backlog["summary"] = {
            "open_total_count": 0,
            "open_promotion_count": 0,
            "open_repeat_count": 0,
            "active_blocker_count": 0,
        }
        backlog["items"] = []
        self._write_json("ops/reports/remediation-backlog.json", backlog)

        report = self._build_report()

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["start_status"], "pass")
        self.assertEqual(report["promotion_status"], "pass")
        self.assertEqual(report["admission_mode"], "promotion_ready")
        self.assertTrue(report["decisions"]["can_start_goal_runtime"])
        self.assertTrue(report["decisions"]["can_promote_result_later"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_learning_uncertain_start_is_authorized_by_goal_contract(self) -> None:
        readiness = json.loads((self.vault / "ops/reports/auto-improve-readiness.json").read_text(encoding="utf-8"))
        readiness["learning_readiness"] = {
            "status": "learning_uncertain",
            "gate_effect": "operator_review_required",
        }
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)

        report = self._build_report()

        learning_check = next(
            check for check in report["checks"] if check["id"] == "start_learning_uncertain_authorized"
        )
        self.assertEqual(learning_check["status"], "pass")
        self.assertEqual(learning_check["gate_effect"], "none")
        self.assertTrue(learning_check["observed"]["contract_authorized"])
        self.assertFalse(learning_check["observed"]["allow_learning_uncertain"])
        self.assertEqual(report["summary"]["start_blocker_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_learning_uncertain_start_blocks_without_contract_or_override(self) -> None:
        readiness = json.loads((self.vault / "ops/reports/auto-improve-readiness.json").read_text(encoding="utf-8"))
        readiness["learning_readiness"] = {
            "status": "learning_uncertain",
            "gate_effect": "operator_review_required",
        }
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)
        contract = json.loads((self.vault / "ops/reports/codex-goal-contract.json").read_text(encoding="utf-8"))
        contract["execution_policy"]["learning_uncertain"]["allow_bounded_trial"] = False
        self._write_json("ops/reports/codex-goal-contract.json", contract)

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["start_status"], "fail")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "blocked")
        self.assertFalse(report["decisions"]["can_start_goal_runtime"])
        learning_check = next(
            check for check in report["checks"] if check["id"] == "start_learning_uncertain_authorized"
        )
        self.assertEqual(learning_check["status"], "fail")
        self.assertEqual(learning_check["gate_effect"], "operator_review_required")
        self.assertFalse(learning_check["observed"]["contract_authorized"])
        self.assertFalse(learning_check["observed"]["allow_learning_uncertain"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_learning_uncertain_legacy_gate_effect_is_canonicalized(self) -> None:
        readiness = json.loads((self.vault / "ops/reports/auto-improve-readiness.json").read_text(encoding="utf-8"))
        readiness["learning_readiness"] = {
            "status": "learning_uncertain",
            "gate_effect": "review_required",
        }
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)
        contract = json.loads((self.vault / "ops/reports/codex-goal-contract.json").read_text(encoding="utf-8"))
        contract["execution_policy"]["learning_uncertain"]["allow_bounded_trial"] = False
        self._write_json("ops/reports/codex-goal-contract.json", contract)

        report = self._build_report()

        learning_check = next(
            check for check in report["checks"] if check["id"] == "start_learning_uncertain_authorized"
        )
        self.assertEqual(learning_check["status"], "fail")
        self.assertEqual(learning_check["gate_effect"], "operator_review_required")
        self.assertEqual(
            learning_check["observed"]["learning_gate_effect"],
            "operator_review_required",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_learning_uncertain_start_allows_explicit_override(self) -> None:
        readiness = json.loads((self.vault / "ops/reports/auto-improve-readiness.json").read_text(encoding="utf-8"))
        readiness["learning_readiness"] = {
            "status": "learning_uncertain",
            "gate_effect": "operator_review_required",
        }
        self._write_json("ops/reports/auto-improve-readiness.json", readiness)
        contract = json.loads((self.vault / "ops/reports/codex-goal-contract.json").read_text(encoding="utf-8"))
        contract["execution_policy"]["learning_uncertain"]["allow_bounded_trial"] = False
        self._write_json("ops/reports/codex-goal-contract.json", contract)

        report = self._build_report(allow_learning_uncertain=True)

        learning_check = next(
            check for check in report["checks"] if check["id"] == "start_learning_uncertain_authorized"
        )
        self.assertEqual(learning_check["status"], "pass")
        self.assertEqual(learning_check["gate_effect"], "none")
        self.assertFalse(learning_check["observed"]["contract_authorized"])
        self.assertTrue(learning_check["observed"]["allow_learning_uncertain"])
        self.assertEqual(report["summary"]["start_blocker_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_remediation_backlog_check_reads_schema_summary_counts(self) -> None:
        backlog = json.loads((self.vault / "ops/reports/remediation-backlog.json").read_text(encoding="utf-8"))
        backlog["summary"] = {
            "open_total_count": 2,
            "open_promotion_count": 1,
            "open_repeat_count": 1,
            "active_blocker_count": 1,
        }
        self._write_json("ops/reports/remediation-backlog.json", backlog)

        report = self._build_report()

        backlog_check = next(check for check in report["checks"] if check["id"] == "promotion_remediation_backlog_clear")
        self.assertEqual(backlog_check["observed"]["open_total_count"], 2)
        self.assertEqual(backlog_check["observed"]["open_promotion_count"], 1)
        self.assertEqual(backlog_check["observed"]["open_repeat_count"], 1)
        self.assertEqual(backlog_check["observed"]["active_blocker_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_start_when_cleanup_was_not_applied(self) -> None:
        cleanup = json.loads((self.vault / "tmp/goal-runtime-clean-transient.json").read_text(encoding="utf-8"))
        cleanup["summary"]["apply"] = False
        self._write_json("tmp/goal-runtime-clean-transient.json", cleanup)

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["start_status"], "fail")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "blocked")
        self.assertFalse(report["decisions"]["can_start_goal_runtime"])
        cleanup_check = next(check for check in report["checks"] if check["id"] == "start_transient_cleanup_applied")
        self.assertEqual(cleanup_check["status"], "fail")
        self.assertFalse(cleanup_check["observed"]["apply"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_start_when_quarantine_preflight_fails(self) -> None:
        self._write_json(
            "tmp/goal-runtime-quarantine-preflight.json",
            {
                "artifact_kind": "goal_runtime_quarantine_preflight",
                "status": "fail",
                "summary": {
                    "operator_decision_required_count": 1,
                    "excluded_run_count": 0,
                    "quarantined_run_count": 0,
                    "invalid_exclusion_count": 0,
                },
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["start_status"], "fail")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "blocked")
        self.assertFalse(report["decisions"]["can_start_goal_runtime"])
        quarantine_check = next(
            check for check in report["checks"] if check["id"] == "start_history_quarantine_preflight_clear"
        )
        self.assertEqual(quarantine_check["status"], "fail")
        self.assertEqual(quarantine_check["observed"]["operator_decision_required_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_start_when_every_proposal_is_blocked(self) -> None:
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [{"proposal_id": "blocked-runtime", "blocked_by": ["recent_log_overlap"]}],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 0,
                        "selected_runnable_count": 0,
                        "blocked_available_count": 1,
                        "blocked_reason_counts": [{"reason": "recent_log_overlap", "count": 1}],
                    }
                },
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "execution_readiness": {
                    "can_run": False,
                    "runnable_proposal_count": 0,
                    "reasons": ["no runnable proposal is available"],
                },
                "can_promote_result": False,
                "promotion_blockers": [{"id": "execution_blocked_by_no_runnable_proposal"}],
            },
        )

        report = self._build_report()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["start_status"], "fail")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "blocked")
        self.assertFalse(report["decisions"]["can_start_goal_runtime"])
        self.assertTrue(report["decisions"]["should_pause_before_run"])
        queue_check = next(check for check in report["checks"] if check["id"] == "start_runnable_proposal_queue")
        self.assertEqual(queue_check["status"], "fail")
        self.assertEqual(queue_check["gate_effect"], "blocks_execution")
        self.assertIn("recent_log_overlap", json.dumps(queue_check["observed"]))
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_allows_resume_completion_without_new_runnable_proposal(self) -> None:
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [{"proposal_id": "blocked-runtime", "blocked_by": ["recent_log_overlap"]}],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 0,
                        "selected_runnable_count": 0,
                        "blocked_available_count": 1,
                        "blocked_reason_counts": [{"reason": "recent_log_overlap", "count": 1}],
                    }
                },
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "execution_readiness": {
                    "can_run": False,
                    "runnable_proposal_count": 0,
                    "reasons": ["no runnable proposal is available"],
                },
                "can_promote_result": False,
                "promotion_blockers": [{"id": "execution_blocked_by_no_runnable_proposal"}],
            },
        )
        self._write_json(
            "ops/reports/auto-improve-sessions/auto-session-resume.json",
            {
                "artifact_kind": "auto_improve_session",
                "session_id": "auto-session-resume",
                "status": "running",
                "stop_reason": "running",
                "budget": {"max_proposals": 1, "max_minutes": 30, "max_consecutive_failures": 1},
                "iterations": [{"status": "complete", "decision": "PROMOTE", "outcome": "promoted"}],
                "maintenance": {"status": "running"},
            },
        )

        report = self._build_report(resume_session_id="auto-session-resume")

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["start_status"], "pass")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "bounded_repair_allowed")
        self.assertTrue(report["decisions"]["can_start_goal_runtime"])
        self.assertFalse(report["decisions"]["should_pause_before_run"])
        self.assertEqual(report["summary"]["start_blocker_count"], 0)
        self.assertEqual(
            report["inputs"]["resume_session_report"],
            "ops/reports/auto-improve-sessions/auto-session-resume.json",
        )
        queue_check = next(check for check in report["checks"] if check["id"] == "start_runnable_proposal_queue")
        execution_check = next(check for check in report["checks"] if check["id"] == "start_execution_readiness")
        self.assertEqual(queue_check["status"], "pass")
        self.assertEqual(execution_check["status"], "pass")
        self.assertEqual(queue_check["gate_effect"], "none")
        self.assertEqual(execution_check["gate_effect"], "none")
        self.assertTrue(queue_check["observed"]["resume_completion"]["active"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_accepts_current_maintenance_action_plan_for_resume(self) -> None:
        self._write_json(
            "tmp/goal-runtime-maintenance-action.json",
            {
                "artifact_kind": "goal_runtime_maintenance_action_plan",
                "producer": "ops.scripts.auto_improve_runtime",
                "session_id": "auto-session-resume",
                "status": "pass",
                "current_max_proposals": 1,
                "current_iteration_count": 1,
                "next_max_proposals": 2,
                "queue_action": {
                    "status": "action_required",
                    "reason": "stable_runnable_queue",
                    "proposal_ids": ["repair-runtime"],
                    "runner_action": "resume_session_with_additional_proposal_budget",
                    "proposal_budget_increment": 1,
                    "resume_target": "auto-improve-goal-maintenance-action",
                },
                "selected_proposal": {
                    "proposal_id": "repair-runtime",
                    "family": "runtime",
                    "failure_mode": "blocked_queue",
                },
                "blockers": [],
                "recommended_next_action": "Run make auto-improve-goal-maintenance-action.",
                "decisions": {
                    "can_resume": True,
                    "requires_budget_increment": True,
                },
            },
        )

        report = self._build_report(
            resume_session_id="auto-session-resume",
            maintenance_action_plan_path="tmp/goal-runtime-maintenance-action.json",
        )

        plan_check = next(
            check for check in report["checks"] if check["id"] == "start_maintenance_action_plan_current"
        )
        self.assertEqual(plan_check["status"], "pass")
        self.assertEqual(
            report["inputs"]["maintenance_action_plan"],
            "tmp/goal-runtime-maintenance-action.json",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_stale_maintenance_action_plan_for_resume(self) -> None:
        self._write_json(
            "tmp/goal-runtime-maintenance-action.json",
            {
                "artifact_kind": "goal_runtime_maintenance_action_plan",
                "producer": "ops.scripts.auto_improve_runtime",
                "session_id": "auto-session-resume",
                "status": "pass",
                "current_max_proposals": 1,
                "current_iteration_count": 1,
                "next_max_proposals": 2,
                "queue_action": {
                    "status": "action_required",
                    "reason": "stable_runnable_queue",
                    "proposal_ids": ["stale-runtime"],
                    "runner_action": "resume_session_with_additional_proposal_budget",
                    "proposal_budget_increment": 1,
                    "resume_target": "auto-improve-goal-maintenance-action",
                },
                "selected_proposal": {
                    "proposal_id": "stale-runtime",
                    "family": "runtime",
                    "failure_mode": "blocked_queue",
                },
                "blockers": [],
                "recommended_next_action": "Run make auto-improve-goal-maintenance-action.",
                "decisions": {
                    "can_resume": True,
                    "requires_budget_increment": True,
                },
            },
        )

        report = self._build_report(
            resume_session_id="auto-session-resume",
            maintenance_action_plan_path="tmp/goal-runtime-maintenance-action.json",
        )

        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["decisions"]["can_start_goal_runtime"])
        plan_check = next(
            check for check in report["checks"] if check["id"] == "start_maintenance_action_plan_current"
        )
        self.assertEqual(plan_check["status"], "fail")
        self.assertFalse(plan_check["observed"]["selected_in_current_report"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_maintenance_action_plan_when_selected_proposal_is_no_longer_runnable(
        self,
    ) -> None:
        self._write_json(
            "ops/reports/mutation-proposals.json",
            {
                "artifact_kind": "mutation_proposals_report",
                "proposals": [
                    {
                        "proposal_id": "repair-runtime",
                        "blocked_by": ["recent_log_overlap"],
                    }
                ],
                "diagnostics": {
                    "queue_selection": {
                        "runnable_available_count": 0,
                        "selected_runnable_count": 0,
                        "blocked_available_count": 1,
                        "blocked_reason_counts": [{"reason": "recent_log_overlap", "count": 1}],
                    }
                },
            },
        )
        self._write_json(
            "tmp/goal-runtime-maintenance-action.json",
            {
                "artifact_kind": "goal_runtime_maintenance_action_plan",
                "producer": "ops.scripts.auto_improve_runtime",
                "session_id": "auto-session-resume",
                "status": "pass",
                "current_max_proposals": 1,
                "current_iteration_count": 1,
                "next_max_proposals": 2,
                "queue_action": {
                    "status": "action_required",
                    "reason": "stable_runnable_queue",
                    "proposal_ids": ["repair-runtime"],
                    "runner_action": "resume_session_with_additional_proposal_budget",
                    "proposal_budget_increment": 1,
                    "resume_target": "auto-improve-goal-maintenance-action",
                },
                "selected_proposal": {
                    "proposal_id": "repair-runtime",
                    "family": "runtime",
                    "failure_mode": "blocked_queue",
                },
                "blockers": [],
                "recommended_next_action": "Run make auto-improve-goal-maintenance-action.",
                "decisions": {
                    "can_resume": True,
                    "requires_budget_increment": True,
                },
            },
        )

        report = self._build_report(
            resume_session_id="auto-session-resume",
            maintenance_action_plan_path="tmp/goal-runtime-maintenance-action.json",
        )

        self.assertEqual(report["status"], "fail")
        plan_check = next(
            check for check in report["checks"] if check["id"] == "start_maintenance_action_plan_current"
        )
        self.assertEqual(plan_check["status"], "fail")
        self.assertTrue(plan_check["observed"]["selected_in_current_report"])
        self.assertFalse(plan_check["observed"]["selected_runnable"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_allows_bounded_start_but_blocks_promotion_from_dirty_worktree_guard(self) -> None:
        guard = json.loads((self.vault / "ops/reports/goal-worktree-guard.json").read_text(encoding="utf-8"))
        guard["status"] = "attention"
        guard["git"]["dirty_entry_count"] = 2
        guard["decisions"]["can_promote_result"] = False
        guard["decisions"]["promotion_blockers"] = ["git_worktree_dirty"]
        self._write_json("ops/reports/goal-worktree-guard.json", guard)

        report = self._build_report()

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["start_status"], "pass")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "bounded_repair_allowed")
        self.assertTrue(report["decisions"]["can_start_goal_runtime"])
        start_check = next(check for check in report["checks"] if check["id"] == "start_worktree_executable")
        self.assertEqual(start_check["status"], "pass")
        promotion_check = next(check for check in report["checks"] if check["id"] == "promotion_worktree_promotable")
        self.assertEqual(promotion_check["status"], "attention")
        self.assertEqual(promotion_check["gate_effect"], "blocks_promotion")
        self.assertEqual(promotion_check["observed"]["dirty_entry_count"], 2)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_blocks_promotion_when_goal_status_digest_is_stale(self) -> None:
        status = json.loads((self.vault / "ops/reports/goal-run-status.json").read_text(encoding="utf-8"))
        status["goal"]["contract_sha256"] = "0" * 64
        self._write_json("ops/reports/goal-run-status.json", status)

        report = self._build_report()

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["start_status"], "pass")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["admission_mode"], "bounded_repair_allowed")
        self.assertTrue(report["decisions"]["can_start_goal_runtime"])
        self.assertFalse(report["decisions"]["can_promote_result_later"])
        authority_check = next(
            check for check in report["checks"] if check["id"] == "promotion_durable_goal_authority_current"
        )
        self.assertEqual(authority_check["status"], "attention")
        self.assertEqual(authority_check["gate_effect"], "blocks_promotion")
        self.assertFalse(authority_check["observed"]["goal_status_contract_digest_matches"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
