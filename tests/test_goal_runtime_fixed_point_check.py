from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import pytest

from ops.scripts.goal_runtime_fixed_point_check import (
    GoalRuntimeFixedPointCheckRequest,
    build_report,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-fixed-point-check.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 20, 0, 0, tzinfo=dt.timezone.utc),
    )


class GoalRuntimeFixedPointCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/goal-runtime-fixed-point-check.schema.json")
        self._seed_aligned_reports()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _seed_aligned_reports(self) -> None:
        promotion_blockers = [
            "execution_blocked_by_no_runnable_proposal",
            "promotion_blocked_by_remediation_backlog_open",
        ]
        backlog_blockers = [
            "execution_blocked_by_no_runnable_proposal",
            "learning_claim_unlock_review_not_approved",
        ]
        self._write_json(
            "ops/reports/codex-goal-contract.json",
            {
                "contract_id": "auto-improve-goal",
                "status": "active",
                "runtime": {"mode": "self_improvement_loop"},
                "promotion_guard": {
                    "can_promote_result": False,
                    "promotion_blockers": promotion_blockers,
                },
            },
        )
        self._write_json(
            "ops/reports/goal-run-status.json",
            {
                "goal": {"contract_id": "auto-improve-goal"},
                "run": {
                    "run_id": "auto-improve-trial",
                    "status": "blocked",
                    "runtime_mode": "self_improvement_loop",
                },
                "promotion_guard": {
                    "can_promote_result": False,
                    "promotion_blockers": promotion_blockers,
                },
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "promotion_blockers": [
                    {
                        "id": "execution_blocked_by_no_runnable_proposal",
                        "status": "open",
                    },
                    {
                        "id": "promotion_blocked_by_remediation_backlog_open",
                        "status": "open",
                        "signal_ids": backlog_blockers,
                    },
                ],
            },
        )
        self._write_json(
            "ops/reports/session-synopsis.json",
            {
                "active_goal": {
                    "contract_id": "auto-improve-goal",
                    "run_id": "auto-improve-trial",
                    "run_status": "blocked",
                    "runtime_mode": "self_improvement_loop",
                    "can_promote_result": False,
                },
                "recent_blockers": [
                    {
                        "id": "execution_blocked_by_no_runnable_proposal",
                        "source": "auto_improve_readiness.promotion_blockers",
                    },
                    {
                        "id": "learning_claim_unlock_review_not_approved",
                        "source": "learning_claim_activation.blocked_predicates",
                    },
                ],
            },
        )
        self._write_json(
            "ops/reports/remediation-backlog.json",
            {
                "items": [
                    {
                        "blocker_id": blocker_id,
                        "item_type": "active_blocker",
                        "severity": "blocks_promotion",
                        "status": "open",
                    }
                    for blocker_id in backlog_blockers
                ]
            },
        )

    def test_build_report_passes_when_goal_runtime_surfaces_are_semantically_aligned(self) -> None:
        report = build_report(
            GoalRuntimeFixedPointCheckRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["failed_check_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_fails_when_session_synopsis_has_stale_readiness_blockers(self) -> None:
        self._write_json(
            "ops/reports/session-synopsis.json",
            {
                "active_goal": {
                    "contract_id": "auto-improve-goal",
                    "run_id": "auto-improve-trial",
                    "run_status": "blocked",
                    "runtime_mode": "self_improvement_loop",
                    "can_promote_result": False,
                },
                "recent_blockers": [
                    {
                        "id": "learning_blocked_by_review_required",
                        "source": "auto_improve_readiness.promotion_blockers",
                    }
                ],
            },
        )

        report = build_report(
            GoalRuntimeFixedPointCheckRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "fail")
        check = next(item for item in report["checks"] if item["id"] == "session_readiness_blockers")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["expected"],
            ["execution_blocked_by_no_runnable_proposal"],
        )
        self.assertEqual(check["observed"], ["learning_blocked_by_review_required"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_completed_terminal_queue_allows_suppressed_readiness_blockers(self) -> None:
        for rel_path in (
            "ops/reports/codex-goal-contract.json",
            "ops/reports/goal-run-status.json",
        ):
            payload = json.loads((self.vault / rel_path).read_text(encoding="utf-8"))
            payload["promotion_guard"] = {
                "can_promote_result": False,
                "promotion_blockers": [],
            }
            if rel_path.endswith("goal-run-status.json"):
                payload["run"] = {
                    "run_id": "terminal-loop",
                    "status": "completed",
                    "runtime_mode": "self_improvement_loop",
                }
            self._write_json(rel_path, payload)
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "promotion_blockers": [
                    {
                        "id": "execution_blocked_by_no_runnable_proposal",
                        "status": "open",
                    },
                    {
                        "id": "learning_blocked_by_execution_not_runnable",
                        "status": "open",
                    },
                ],
            },
        )
        self._write_json(
            "ops/reports/auto-improve-sessions/terminal-loop.json",
            {
                "status": "complete",
                "stop_reason": "queue_exhausted",
                "iterations": [{"decision": "PROMOTE", "outcome": "promoted"}],
            },
        )
        self._write_json(
            "ops/reports/session-synopsis.json",
            {
                "active_goal": {
                    "contract_id": "auto-improve-goal",
                    "run_id": "terminal-loop",
                    "run_status": "completed",
                    "runtime_mode": "self_improvement_loop",
                    "can_promote_result": False,
                },
                "recent_blockers": [],
            },
        )
        self._write_json("ops/reports/remediation-backlog.json", {"items": []})

        report = build_report(
            GoalRuntimeFixedPointCheckRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        check = next(item for item in report["checks"] if item["id"] == "session_readiness_blockers")
        self.assertEqual(check["expected"], [])
        self.assertEqual(check["observed"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_repeated_backlog_items_do_not_have_to_echo_in_session_or_readiness(self) -> None:
        self._write_json(
            "ops/reports/remediation-backlog.json",
            {
                "items": [
                    {
                        "blocker_id": "execution_blocked_by_no_runnable_proposal",
                        "item_type": "active_blocker",
                        "severity": "blocks_promotion",
                        "status": "open",
                    },
                    {
                        "blocker_id": "learning_claim_unlock_review_not_approved",
                        "item_type": "active_blocker",
                        "severity": "blocks_promotion",
                        "status": "open",
                    },
                    {
                        "blocker_id": "blocked_queue_recent_log_overlap",
                        "item_type": "repeated_negative_lesson",
                        "severity": "blocks_repeat",
                        "status": "open",
                    },
                ]
            },
        )

        report = build_report(
            GoalRuntimeFixedPointCheckRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        checks = {check["id"]: check for check in report["checks"]}
        self.assertEqual(
            checks["readiness_backlog_signals"]["expected"],
            [
                "execution_blocked_by_no_runnable_proposal",
                "learning_claim_unlock_review_not_approved",
            ],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_can_check_run_local_goal_runtime_surfaces(self) -> None:
        for rel_path in (
            "codex-goal-contract.json",
            "goal-run-status.json",
            "auto-improve-readiness.json",
            "session-synopsis.json",
            "remediation-backlog.json",
        ):
            source = self.vault / "ops" / "reports" / rel_path
            destination = self.vault / "runs" / "goal-local" / "state" / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self._write_json(
            "ops/reports/session-synopsis.json",
            {
                "active_goal": {},
                "recent_blockers": [
                    {
                        "id": "stale_canonical_blocker",
                        "source": "auto_improve_readiness.promotion_blockers",
                    }
                ],
            },
        )

        report = build_report(
            GoalRuntimeFixedPointCheckRequest(
                vault=self.vault,
                context=fixed_context(),
                codex_goal_contract_path="runs/goal-local/state/codex-goal-contract.json",
                goal_run_status_path="runs/goal-local/state/goal-run-status.json",
                auto_improve_readiness_path="runs/goal-local/state/auto-improve-readiness.json",
                session_synopsis_path="runs/goal-local/state/session-synopsis.json",
                remediation_backlog_path="runs/goal-local/state/remediation-backlog.json",
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertNotEqual(report["input_fingerprints"]["session_synopsis"], "missing")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_report_uses_schema_backed_output(self) -> None:
        report = build_report(
            GoalRuntimeFixedPointCheckRequest(
                vault=self.vault,
                context=fixed_context(),
            )
        )

        out_path = write_report(self.vault, report)

        self.assertEqual(out_path, self.vault / "tmp/goal-runtime-fixed-point-check.json")
        self.assertTrue(out_path.is_file())


if __name__ == "__main__":
    unittest.main()
