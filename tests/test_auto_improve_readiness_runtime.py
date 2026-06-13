from __future__ import annotations

import datetime as dt
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import runpy
import sys
import unittest
from pathlib import Path

import pytest

from ops.scripts.mechanism.auto_improve_readiness import main as readiness_cli_main
from ops.scripts.mechanism.auto_improve_readiness_constants_runtime import (
    READINESS_SOURCE_PATHS,
)
from ops.scripts.mechanism.auto_improve_readiness_learning_runtime import (
    learning_claim_blocker_payloads,
)
from ops.scripts.mechanism.auto_improve_readiness_remediation_runtime import (
    remediation_backlog_summary,
)
from ops.scripts.mechanism.auto_improve_readiness_runtime import (
    assess_learning_readiness,
    build_readiness_report,
    load_readiness_inputs,
    readiness_can_run,
    readiness_exit_code,
    write_readiness_report,
)
from tests.auto_improve_readiness_test_runtime import (
    REPO_ROOT,
    AutoImproveReadinessRuntimeFixture,
    _canonical_jsonable,
    fixed_context,
)

pytestmark = pytest.mark.slow


class _BlockFlatReadinessAlias(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: object = None, target: object = None
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname in {
            "ops.scripts.auto_improve_readiness_runtime",
            "ops.scripts.output_runtime",
        }:
            raise ModuleNotFoundError(f"blocked flat compatibility import: {fullname}")
        return None


class AutoImproveReadinessRuntimeTests(
    AutoImproveReadinessRuntimeFixture, unittest.TestCase
):
    def test_source_paths_track_decomposed_runtime_modules(self) -> None:
        self.assertEqual(
            READINESS_SOURCE_PATHS,
            [
                "ops/scripts/mechanism/auto_improve_readiness_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_payload_runtime.py",
                "ops/scripts/core/payload_field_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_learning_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_remediation_runtime.py",
                "ops/scripts/mechanism/auto_improve_readiness_worktree_guard_runtime.py",
            ],
        )
        for rel_path in READINESS_SOURCE_PATHS:
            self.assertTrue((REPO_ROOT / rel_path).is_file(), rel_path)

    def test_direct_script_fallback_uses_canonical_module_imports(self) -> None:
        blocker = _BlockFlatReadinessAlias()
        blocked_aliases = {
            "ops.scripts.auto_improve_readiness_runtime",
            "ops.scripts.output_runtime",
        }
        removed_modules = {
            name: sys.modules.pop(name)
            for name in blocked_aliases
            if name in sys.modules
        }
        sys.meta_path.insert(0, blocker)
        try:
            namespace = runpy.run_path(
                (REPO_ROOT / "ops/scripts/mechanism/auto_improve_readiness.py").as_posix()
            )
        finally:
            sys.meta_path.remove(blocker)
            sys.modules.update(removed_modules)

        self.assertTrue(callable(namespace["main"]))

    def test_cli_resolves_relative_out_under_vault_from_foreign_cwd(self) -> None:
        self._write_ready_queue_reports()
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.temp_dir.name)
            exit_code = readiness_cli_main(
                [
                    "--vault",
                    str(self.vault),
                    "--out",
                    "tmp/readiness-output.json",
                ]
            )
        finally:
            os.chdir(previous_cwd)

        destination = self.vault / "tmp" / "readiness-output.json"
        self.assertEqual(exit_code, 0)
        self.assertTrue(destination.is_file())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertTrue(readiness_can_run(persisted))

    def test_cli_rejects_outside_vault_out_path_without_writing(self) -> None:
        self._write_ready_queue_reports()
        outside_path = Path(self.temp_dir.name) / "outside-readiness.json"

        with self.assertRaisesRegex(ValueError, "repo output path must stay under vault"):
            readiness_cli_main(
                [
                    "--vault",
                    str(self.vault),
                    "--out",
                    str(outside_path),
                ]
            )

        self.assertFalse(outside_path.exists())

    def test_load_readiness_inputs_rejects_missing_artifact_envelope_on_disk_reports(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
            enveloped=False,
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )

        inputs = load_readiness_inputs(self.vault, context=fixed_context())

        self.assertFalse(inputs.reports_present)
        self.assertEqual(inputs.active_outcome_metrics, {})
        self.assertTrue(inputs.active_mechanism_review)
        self.assertTrue(inputs.active_mutation_proposal)

    def test_load_readiness_inputs_accepts_current_reports_when_only_mtime_is_newer(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 7,
                    "recent_window": 20,
                    "recent_attempt_count": 7,
                    "session_reports_considered": 0,
                },
                "metrics": {
                    "rework_count": 5,
                    "moving_averages": {
                        "hold": 0.2857,
                        "discard": 0.1429,
                        "rollback_signal": 0.0,
                    },
                    "defect_escape_proxy": {"count": 3},
                    "operator_effort_proxy": {
                        "phase_totals_seconds": {},
                        "executor_report_count": 0,
                        "reviewer_dispatch_count": 0,
                        "validator_dispatch_count": 0,
                        "auditor_dispatch_count": 0,
                        "hold_count": 2,
                    },
                    "rollback_signal_count": 0,
                    "rollback_rehearsal_coverage_count": 0,
                },
                "recent_attempts": [],
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "status": "attention",
                "summary": {"candidates_emitted": 0},
                "diagnostics": {
                    "bootstrap": {
                        "status": "ready",
                        "summary": "current mechanism history is ready",
                    },
                    "session_calibration": {"status": "no_candidates"},
                },
                "candidates": [],
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "status": "attention",
                "summary": {
                    "source_candidates_read": 0,
                    "proposals_emitted": 0,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": (
                        "no proposals emitted | mechanism review emitted zero candidates | "
                        "outcome_metrics: attempts_considered=7 is below min_attempts_considered=10"
                    ),
                },
                "diagnostics": {
                    "evidence_gaps": [
                        "mechanism review emitted zero candidates",
                        "outcome_metrics: attempts_considered=7 is below min_attempts_considered=10",
                    ]
                },
                "proposals": [],
            },
        )

        outcome_path = self.vault / "ops" / "reports" / "outcome-metrics.json"
        payload = json.loads(outcome_path.read_text(encoding="utf-8"))
        generated_at = dt.datetime.strptime(
            payload["generated_at"], "%Y-%m-%dT%H:%M:%SZ"
        )
        newer_timestamp = (
            (generated_at + dt.timedelta(seconds=1)).replace(tzinfo=dt.UTC).timestamp()
        )
        os.utime(outcome_path, (newer_timestamp, newer_timestamp))

        inputs = load_readiness_inputs(self.vault, context=fixed_context())
        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(inputs.reports_present)
        self.assertEqual(inputs.queue_state.outcome_summary["attempts_considered"], 7)
        self.assertEqual(report["queue"]["attempts_considered"], 7)
        self.assertEqual(
            report["learning_readiness"]["metrics"]["attempts_considered"], 7
        )
        self.assertTrue(report["checks"][0]["pass"])

    def test_load_readiness_inputs_is_byte_stable_for_fixed_inputs(self) -> None:
        self._write_ready_queue_reports()

        first_inputs = load_readiness_inputs(self.vault, context=fixed_context())
        second_inputs = load_readiness_inputs(self.vault, context=fixed_context())

        first_payload = _canonical_jsonable(first_inputs, vault_root=self.vault)
        second_payload = _canonical_jsonable(second_inputs, vault_root=self.vault)
        first_bytes = json.dumps(first_payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        second_bytes = json.dumps(second_payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        assert isinstance(first_payload, dict)
        assert isinstance(second_payload, dict)
        runtime_context = first_payload["runtime_context"]
        queue_state = first_payload["queue_state"]
        assert isinstance(runtime_context, dict)
        assert isinstance(queue_state, dict)
        outcome_summary = queue_state["outcome_summary"]
        proposal_summary = queue_state["proposal_summary"]
        runnable_proposal_ids = queue_state["runnable_proposal_ids"]
        assert isinstance(outcome_summary, dict)
        assert isinstance(proposal_summary, dict)
        assert isinstance(runnable_proposal_ids, list)

        self.assertEqual(first_bytes, second_bytes)
        self.assertTrue(first_payload["reports_present"])
        self.assertEqual(runtime_context["generated_at"], "2026-04-22T04:00:00Z")
        self.assertEqual(runtime_context["session_id"], "")
        self.assertEqual(runtime_context["iteration"], 0)
        self.assertEqual(runtime_context["executor_id"], "")
        self.assertEqual(outcome_summary["attempts_considered"], 12)
        self.assertEqual(proposal_summary["proposals_emitted"], 1)
        self.assertEqual(runnable_proposal_ids, ["proposal-ready"])
        self.assertEqual(
            hashlib.sha256(first_bytes).hexdigest(),
            "0b151c770103a0b3b5b0b423cdc7b0361fadeaa145389d0b737be835c7785354",
        )

    def test_open_remediation_backlog_blocks_promotion_not_trial(self) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/remediation-backlog.json",
            {
                "status": "attention",
                "summary": {
                    "backlog_item_count": 1,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 1,
                    "open_total_count": 1,
                    "open_promotion_count": 1,
                    "open_repeat_count": 0,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "Close or explicitly defer remediation backlog items before promotion.",
                },
                "items": [
                    {
                        "item_id": "active_blocker_goal_status_self_improvement_loop_certificate_incomplete",
                        "blocker_id": "goal_status_self_improvement_loop_certificate_incomplete",
                        "source": "goal_run_status.blockers",
                        "item_type": "active_blocker",
                        "status": "open",
                        "severity": "blocks_promotion",
                        "occurrence_count": 1,
                        "evidence_paths": ["ops/reports/session-synopsis.json"],
                        "repair_target": "Run the bounded self-improvement loop and full gates.",
                        "next_action": "Run the bounded self-improvement loop and full gates.",
                    }
                ],
                "inputs": {
                    "self_improvement_negative_lessons": "ops/reports/self-improvement-negative-lessons.json",
                    "session_synopsis": "ops/reports/session-synopsis.json",
                    "learning_claim_activation": "ops/reports/learning_claim_activation_report.json",
                    "auto_improve_sessions": "ops/reports/auto-improve-sessions",
                    "goal_runtime_certificate": "ops/reports/goal-runtime-certificate.json",
                    "goal_worktree_guard": "ops/reports/goal-worktree-guard.json",
                    "learning_readiness_signoff": "ops/reports/learning-readiness-signoff.json",
                    "status_overrides": "ops/policies/remediation-backlog-status-overrides.json",
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        self.assertEqual(report["promotion_readiness"]["status"], "blocked")
        self.assertIn(
            "promotion_blocked_by_remediation_backlog_open",
            report["promotion_readiness"]["blocker_ids"],
        )
        self.assertIn("remediation_backlog", report["promotion_readiness"]["blocking_scopes"])
        self.assertIn("blocks_promotion", report["promotion_readiness"]["gate_effects"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        blocker = blockers["promotion_blocked_by_remediation_backlog_open"]
        self.assertEqual(blocker["scope"], "remediation_backlog")
        self.assertEqual(
            blocker["signal_ids"],
            ["goal_status_self_improvement_loop_certificate_incomplete"],
        )
        self.assertIn("open_promotion_count=1", blocker["reason"])
        self.assertEqual(
            report["diagnostics"]["remediation_backlog_summary"]["status"], "fail"
        )
        self.assertTrue(
            report["diagnostics"]["remediation_backlog_summary"]["release_blocking"]
        )
        self.assertIn("Trial only; do not promote.", report["next_action"])

    def test_remediation_backlog_summary_uses_schema_summary_when_items_drift(self) -> None:
        summary = remediation_backlog_summary(
            {
                "status": "attention",
                "artifact_kind": "remediation_backlog",
                "summary": {
                    "backlog_item_count": 1,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 1,
                    "open_total_count": 1,
                    "open_promotion_count": 1,
                    "open_repeat_count": 0,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "Close promotion blockers.",
                },
                "items": [],
                "currentness": {"status": "current"},
            },
            remediation_backlog_path="ops/reports/remediation-backlog.json",
        )

        self.assertEqual(summary["status"], "fail")
        self.assertTrue(summary["release_blocking"])
        self.assertEqual(summary["open_total_count"], 1)
        self.assertEqual(summary["open_promotion_count"], 1)
        self.assertEqual(summary["active_blocker_count"], 1)
        self.assertEqual(summary["signal_ids"], ["remediation_backlog_open"])

    def test_remediation_backlog_summary_item_counts_can_raise_summary_floor(self) -> None:
        summary = remediation_backlog_summary(
            {
                "status": "attention",
                "artifact_kind": "remediation_backlog",
                "summary": {
                    "backlog_item_count": 0,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 0,
                    "open_total_count": 0,
                    "open_promotion_count": 0,
                    "open_repeat_count": 0,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "Close promotion blockers.",
                },
                "items": [
                    {
                        "blocker_id": "item_only_promotion_blocker",
                        "status": "open",
                        "severity": "blocks_promotion",
                    }
                ],
            },
            remediation_backlog_path="ops/reports/remediation-backlog.json",
        )

        self.assertEqual(summary["status"], "fail")
        self.assertTrue(summary["release_blocking"])
        self.assertEqual(summary["open_total_count"], 1)
        self.assertEqual(summary["open_promotion_count"], 1)
        self.assertEqual(summary["active_blocker_count"], 1)
        self.assertEqual(summary["signal_ids"], ["item_only_promotion_blocker"])

    def test_remediation_backlog_summary_drift_blocks_promotion_not_trial(self) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/remediation-backlog.json",
            {
                "status": "attention",
                "summary": {
                    "backlog_item_count": 1,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 1,
                    "open_total_count": 1,
                    "open_promotion_count": 1,
                    "open_repeat_count": 0,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "Close promotion blockers.",
                },
                "items": [],
                "inputs": {},
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        blocker = blockers["promotion_blocked_by_remediation_backlog_open"]
        self.assertEqual(blocker["signal_ids"], ["remediation_backlog_open"])
        self.assertIn("open_promotion_count=1", blocker["reason"])
        self.assertEqual(
            report["diagnostics"]["remediation_backlog_summary"]["status"], "fail"
        )
        self.assertTrue(
            report["diagnostics"]["remediation_backlog_summary"]["release_blocking"]
        )

    def test_run_local_remediation_backlog_override_controls_promotion_blocker(
        self,
    ) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/remediation-backlog.json",
            {
                "status": "attention",
                "summary": {
                    "backlog_item_count": 1,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 1,
                    "open_total_count": 1,
                    "open_promotion_count": 1,
                    "open_repeat_count": 0,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "Close canonical backlog items.",
                },
                "items": [
                    {
                        "item_id": "active_blocker_stale_canonical",
                        "blocker_id": "stale_canonical",
                        "source": "session_synopsis.recent_blockers",
                        "item_type": "active_blocker",
                        "status": "open",
                        "severity": "blocks_promotion",
                        "occurrence_count": 1,
                        "evidence_paths": ["ops/reports/session-synopsis.json"],
                        "repair_target": "Canonical stale blocker.",
                        "next_action": "Canonical stale blocker.",
                    }
                ],
                "inputs": {},
            },
        )
        local_payload = self._canonical_report_payload(
            "ops/reports/remediation-backlog.json",
            {
                "status": "pass",
                "summary": {
                    "backlog_item_count": 0,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 0,
                    "open_total_count": 0,
                    "open_promotion_count": 0,
                    "open_repeat_count": 0,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "No run-local backlog items detected.",
                },
                "items": [],
                "inputs": {},
            },
        )
        self._write_report(
            "runs/goal-local/state/remediation-backlog.json",
            local_payload,
            enveloped=False,
        )

        report = build_readiness_report(
            self.vault,
            context=fixed_context(),
            remediation_backlog_path="runs/goal-local/state/remediation-backlog.json",
        )

        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn("promotion_blocked_by_remediation_backlog_open", blocker_ids)
        self.assertEqual(
            report["inputs"]["remediation_backlog_report"],
            "runs/goal-local/state/remediation-backlog.json",
        )
        self.assertEqual(
            report["diagnostics"]["remediation_backlog_summary"]["path"],
            "runs/goal-local/state/remediation-backlog.json",
        )

    def test_repeat_only_remediation_backlog_does_not_block_promotion(self) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/remediation-backlog.json",
            {
                "status": "attention",
                "summary": {
                    "backlog_item_count": 1,
                    "repeated_blocker_count": 1,
                    "active_blocker_count": 0,
                    "open_total_count": 1,
                    "open_promotion_count": 0,
                    "open_repeat_count": 1,
                    "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
                    "next_action": "Close repeated blocker before rerunning the same shape.",
                },
                "items": [
                    {
                        "item_id": "auto_session_repeated_blocker_example",
                        "blocker_id": "mutation_failed",
                        "source": "auto_improve_session.loop_state",
                        "item_type": "repeated_auto_improve_blocker",
                        "status": "open",
                        "severity": "blocks_repeat",
                        "occurrence_count": 2,
                        "evidence_paths": [
                            "ops/reports/auto-improve-sessions/example.json"
                        ],
                        "repair_target": "Resolve repeated mutation failure.",
                        "next_action": "Close this repeat item before rerunning this shape.",
                    }
                ],
                "inputs": {},
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn("promotion_blocked_by_remediation_backlog_open", blocker_ids)
        self.assertEqual(
            report["diagnostics"]["remediation_backlog_summary"]["status"], "pass"
        )
        self.assertFalse(
            report["diagnostics"]["remediation_backlog_summary"]["release_blocking"]
        )

    def test_missing_goal_worktree_guard_blocks_promotion_not_trial(self) -> None:
        (self.vault / "ops" / "reports" / "goal-worktree-guard.json").unlink()
        self._write_ready_queue_reports()

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        self.assertIn("promotion_blocked_by_goal_worktree_guard_failure", blockers)
        self.assertEqual(
            blockers["promotion_blocked_by_goal_worktree_guard_failure"]["scope"],
            "worktree_guard",
        )
        self.assertEqual(
            report["diagnostics"]["goal_worktree_guard_summary"]["status"],
            "not_run",
        )
        self.assertIn("Trial only; do not promote.", report["next_action"])

    def test_dirty_goal_worktree_guard_blocks_promotion_not_trial(self) -> None:
        self._write_goal_worktree_guard(
            status="attention",
            dirty_entry_count=1,
            promotion_blockers=["git_worktree_dirty"],
            can_promote=False,
        )
        self._write_ready_queue_reports()

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        blocker = blockers["promotion_blocked_by_goal_worktree_guard_failure"]
        self.assertEqual(blocker["source_status"], "attention")
        self.assertIn("git_worktree_dirty", blocker["signal_ids"])
        self.assertEqual(
            report["diagnostics"]["goal_worktree_guard_summary"]["dirty_entry_count"],
            1,
        )

    def test_artifact_freshness_failure_blocks_promotion_without_blocking_execution(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "fail",
                "summary": {
                    "schema_invalid_artifact_count": 1,
                    "stable_contract_debt_issue_count": 1,
                },
                "artifact_records": [
                    {
                        "path": "ops/reports/example.json",
                        "schema_validation_status": "fail",
                        "schema_validation_errors": [
                            "$.summary: missing required property 'status'"
                        ],
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        self.assertEqual(
            report["diagnostics"]["artifact_freshness_summary"][
                "schema_invalid_artifact_count"
            ],
            1,
        )
        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertIn("promotion_blocked_by_artifact_contract_failure", blocker_ids)
        artifact_blocker = next(
            item
            for item in report["promotion_blockers"]
            if item["id"] == "promotion_blocked_by_artifact_contract_failure"
        )
        self.assertEqual(artifact_blocker["scope"], "artifact_contract")
        self.assertIn("ops/reports/example.json", artifact_blocker["reason"])

    def test_stable_artifact_contract_debt_is_diagnostic_not_promotion_blocker(
        self,
    ) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "attention",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "stable_contract_debt_issue_count": 2,
                    "root_ephemeral_artifact_count": 0,
                    "non_utf8_text_artifact_count": 0,
                    "mtime_sensitive_attention_issue_count": 0,
                },
                "artifact_records": [
                    {
                        "path": "runs/legacy-run/run-ledger.json",
                        "issues": ["missing_artifact_envelope", "unknown_currentness"],
                        "stable_contract_issues": [
                            "missing_artifact_envelope",
                            "unknown_currentness",
                        ],
                        "schema_validation_status": "pass",
                        "contract_issue_class": "stable_contract_debt",
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertTrue(report["can_promote_result"])
        self.assertEqual(
            report["diagnostics"]["artifact_freshness_summary"][
                "stable_contract_debt_issue_count"
            ],
            2,
        )
        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn("promotion_blocked_by_artifact_contract_failure", blocker_ids)

    def test_selected_contract_operational_attention_blocks_promotion(self) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "pass",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "stable_contract_debt_issue_count": 0,
                    "operational_attention_artifact_count": 1,
                    "operational_attention_issue_count": 1,
                },
                "artifact_records": [
                    {
                        "path": "ops/reports/test-execution-summary.json",
                        "schema_validation_status": "pass",
                        "schema_validation_errors": [],
                        "issues": [
                            "test_target_fingerprint_mismatch:tests/test_makefile_static_gates.py"
                        ],
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        selected_contract_blocker = next(
            item
            for item in report["promotion_blockers"]
            if item["id"] == "promotion_blocked_by_selected_contract_failure"
        )
        self.assertEqual(selected_contract_blocker["scope"], "release_gate")
        self.assertEqual(
            selected_contract_blocker["signal_ids"],
            ["selected_contract_currentness_not_current"],
        )
        self.assertIn(
            "selected_contract release gate is not pass",
            selected_contract_blocker["reason"],
        )
        self.assertIn("operational_attention=", selected_contract_blocker["reason"])

    def test_selected_contract_and_source_package_failures_block_promotion(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/test-execution-summary.json", {"status": "fail"}
        )
        self._write_report(
            "ops/reports/source-package-clean-extract.json", {"status": "fail"}
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        self.assertEqual(
            report["diagnostics"]["selected_contract_summary"]["status"], "fail"
        )
        self.assertEqual(
            report["diagnostics"]["source_package_clean_extract_summary"]["status"],
            "fail",
        )
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        self.assertIn("promotion_blocked_by_selected_contract_failure", blockers)
        self.assertIn("promotion_blocked_by_source_package_failure", blockers)
        self.assertEqual(
            blockers["promotion_blocked_by_selected_contract_failure"]["scope"],
            "release_gate",
        )
        self.assertEqual(
            blockers["promotion_blocked_by_source_package_failure"]["scope"],
            "release_gate",
        )
        self.assertEqual(
            blockers["promotion_blocked_by_selected_contract_failure"]["signal_ids"],
            ["selected_contract_status_not_pass"],
        )
        self.assertEqual(
            blockers["promotion_blocked_by_source_package_failure"]["signal_ids"],
            ["source_package_status_not_pass"],
        )

    def test_release_authority_failures_block_promotion(self) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "clean_release_ready": False,
                "release_readiness_state": "conditional_pass",
                "machine_release_allowed": False,
                "operator_release_allowed": True,
            },
        )
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "status": "fail",
                "release_authority_status": "conditional_pass",
                "sealed_release_status": "unsealed_distribution_not_provided",
                "distribution_package": {"status": "not_provided"},
            },
        )
        self._write_report(
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "status": "fail",
                "preflight_status": "binding_pass_authority_blocked",
                "distribution_binding_status": "pass",
                "authority_preflight_status": "blocked",
                "expected_blocked_preflight": True,
                "failures": [
                    "batch_release_authority_not_clean_pass",
                    "batch_sealed_release_not_clean_pass",
                ],
                "failure_details": [
                    {
                        "failure_id": "batch_release_authority_not_clean_pass",
                        "vocabulary_reason_id": "release_authority_not_clean_pass",
                        "status_axis": "release_authority",
                    }
                ],
                "blocking_reason_ids": [
                    "release_authority_not_clean_pass",
                    "machine_release_not_allowed",
                    "sealed_release_not_clean_pass",
                ],
                "summary": "distribution binding pass; release authority blocked",
            },
            enveloped=False,
        )
        self._write_report(
            "ops/reports/release-closeout-finality-attestation.json",
            {
                "finality_status": "fail",
                "finality_failures": [
                    {"path": "ops/reports/release-closeout-batch-manifest.json"}
                ],
            },
        )
        (self.vault / "tmp" / "release-closeout-post-check-finalizer.json").unlink()

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        self.assertIn("promotion_blocked_by_release_closeout_summary_failure", blockers)
        self.assertIn("promotion_blocked_by_release_batch_manifest_failure", blockers)
        self.assertIn("promotion_blocked_by_release_finality_failure", blockers)
        self.assertIn("promotion_blocked_by_artifact_finalization_failure", blockers)
        self.assertIn(
            "promotion_blocked_by_release_authority_preflight_failure", blockers
        )
        self.assertEqual(
            blockers["promotion_blocked_by_release_closeout_summary_failure"][
                "signal_ids"
            ],
            ["machine_release_not_allowed"],
        )
        self.assertEqual(
            set(
                blockers["promotion_blocked_by_release_batch_manifest_failure"][
                    "signal_ids"
                ]
            ),
            {"release_authority_not_clean_pass", "sealed_release_not_clean_pass"},
        )
        self.assertEqual(
            blockers["promotion_blocked_by_release_authority_preflight_failure"][
                "signal_ids"
            ],
            [
                "release_authority_not_clean_pass",
                "machine_release_not_allowed",
                "sealed_release_not_clean_pass",
                "batch_release_authority_not_clean_pass",
                "batch_sealed_release_not_clean_pass",
            ],
        )
        self.assertIn(
            "machine_release_allowed=false",
            report["diagnostics"]["release_closeout_summary"]["summary"],
        )
        self.assertIn(
            "sealed_release_status=unsealed_distribution_not_provided",
            report["diagnostics"]["release_closeout_batch_manifest_summary"]["summary"],
        )
        self.assertIn("Trial only; do not promote.", report["next_action"])
        self.assertIn("Queue is non-empty.", report["next_action"])
        self.assertIn(
            "Refresh release closeout summary, then rerun make auto-improve-readiness.",
            report["next_action"],
        )
        preflight = report["diagnostics"]["release_authority_preflight_summary"]
        self.assertEqual(
            preflight["preflight_status"], "binding_pass_authority_blocked"
        )
        self.assertEqual(preflight["distribution_binding_status"], "pass")
        self.assertTrue(preflight["expected_blocked_preflight"])
        self.assertEqual(
            preflight["linked_promotion_blocker_ids"],
            [
                "promotion_blocked_by_release_closeout_summary_failure",
                "promotion_blocked_by_release_batch_manifest_failure",
            ],
        )
        self.assertEqual(
            report["diagnostics"]["artifact_finalization_summary"]["status"], "not_run"
        )

    def test_expected_blocked_preflight_self_reference_does_not_block_readiness(
        self,
    ) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "status": "fail",
                "preflight_status": "binding_pass_authority_blocked",
                "preflight_mode": "expected_blocked",
                "distribution_binding_status": "pass",
                "authority_preflight_status": "blocked",
                "expected_blocked_preflight": True,
                "clean_required_preflight": False,
                "failures": [
                    "batch_release_authority_not_clean_pass",
                    "batch_sealed_release_not_clean_pass",
                ],
                "unexpected_failure_ids": [],
                "failure_details": [
                    {
                        "failure_id": "batch_release_authority_not_clean_pass",
                        "vocabulary_reason_id": "release_authority_not_clean_pass",
                        "status_axis": "release_authority",
                    }
                ],
                "blocking_reason_ids": [
                    "release_authority_not_clean_pass",
                    "machine_release_not_allowed",
                    "sealed_release_not_clean_pass",
                ],
                "summary": "distribution binding pass; release authority blocked",
            },
            enveloped=False,
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn(
            "promotion_blocked_by_release_authority_preflight_failure", blocker_ids
        )
        self.assertTrue(report["can_promote_result"])
        self.assertEqual(report["promotion_readiness"]["status"], "pass")
        self.assertEqual(report["promotion_readiness"]["blocker_count"], 0)
        preflight = report["diagnostics"]["release_authority_preflight_summary"]
        self.assertTrue(preflight["expected_blocked_preflight"])
        self.assertEqual(preflight["unexpected_failure_ids"], [])

    def test_release_closeout_summary_gate_prefers_status_v2_authority(self) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "clean_release_ready": True,
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
                "operator_release_allowed": True,
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": "conditional_pass",
                        "semantic_release_status": "conditional_pass",
                        "sealed_release_status": "unsealed_distribution_not_provided",
                    },
                    "blocker_reason_ids": ["machine_release_not_allowed"],
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        self.assertEqual(
            blockers["promotion_blocked_by_release_closeout_summary_failure"][
                "signal_ids"
            ],
            ["machine_release_not_allowed"],
        )
        summary = report["diagnostics"]["release_closeout_summary"]["summary"]
        self.assertIn("machine_release_allowed=false", summary)
        self.assertIn("release_authority_status=conditional_pass", summary)
        self.assertIn(
            "sealed_release_status=unsealed_distribution_not_provided", summary
        )

    def test_missing_release_authority_preflight_blocks_promotion_but_not_trial(
        self,
    ) -> None:
        (
            self.vault / "ops/reports/release-closeout-sealed-rehearsal-check.json"
        ).unlink()
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        (self.vault / "tmp" / "release-closeout-post-check-finalizer.json").unlink()

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        blocker = blockers["promotion_blocked_by_release_authority_preflight_failure"]
        self.assertEqual(blocker["source_status"], "not_run")
        self.assertEqual(
            blocker["signal_ids"], ["release_authority_preflight_not_clean"]
        )
        self.assertIn("Trial only; do not promote.", report["next_action"])
        self.assertEqual(
            report["diagnostics"]["release_authority_preflight_summary"][
                "preflight_status"
            ],
            "not_run",
        )

    def test_release_lineage_mismatch_blocks_promotion(self) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/release-evidence-cohort.json",
            {
                "status": "attention",
                "summary": {"clean_lane_contract_status": "fail"},
                "cohort": {
                    "strict_same_fingerprint": False,
                    "component_fingerprint_count": 2,
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        blockers = {item["id"]: item for item in report["promotion_blockers"]}
        self.assertIn("promotion_blocked_by_release_lineage_mismatch", blockers)
        self.assertEqual(
            blockers["promotion_blocked_by_release_lineage_mismatch"]["scope"],
            "release_gate",
        )
        self.assertEqual(
            blockers["promotion_blocked_by_release_lineage_mismatch"]["signal_ids"],
            [
                "release_lineage_not_strict_same_fingerprint",
                "release_evidence_clean_lane_contract_not_pass",
            ],
        )
        self.assertEqual(
            report["diagnostics"]["release_evidence_cohort_summary"]["status"],
            "fail",
        )
        self.assertIn(
            "strict_same_fingerprint=false",
            report["diagnostics"]["release_evidence_cohort_summary"]["summary"],
        )

    def test_selected_contract_partial_pass_bootstrap_does_not_self_block_promotion(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/test-execution-summary.json", {"status": "partial-pass"}
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["diagnostics"]["selected_contract_summary"]["status"], "pass"
        )
        self.assertFalse(
            report["diagnostics"]["selected_contract_summary"]["release_blocking"]
        )
        self.assertEqual(
            report["diagnostics"]["selected_contract_summary"]["source_status"],
            "partial-pass",
        )

    def test_finality_attestation_closes_artifact_finalization_when_tmp_report_was_cleaned(
        self,
    ) -> None:
        (self.vault / "tmp" / "release-closeout-post-check-finalizer.json").unlink()

        report = build_readiness_report(self.vault, context=fixed_context())

        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn(
            "promotion_blocked_by_artifact_finalization_failure", blocker_ids
        )
        artifact_finalization = report["diagnostics"]["artifact_finalization_summary"]
        self.assertEqual(artifact_finalization["status"], "pass")
        self.assertEqual(
            artifact_finalization["source_status"], "finality_attested_pass"
        )
        self.assertIn(
            "release closeout finality attestation passed",
            artifact_finalization["summary"],
        )
        closeout_summary = report["diagnostics"]["release_closeout_summary"]
        self.assertEqual(closeout_summary["status"], "pass")
        self.assertEqual(closeout_summary["source_status"], "pass")
        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn("promotion_blocked_by_selected_contract_failure", blocker_ids)

    def test_clean_authority_unsealed_batch_manifest_does_not_block_promotion(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "status": "fail",
                "batch_integrity_status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "unsealed_distribution_not_provided",
                "distribution_package": {"status": "not_provided"},
                "auto_improve_lane_status": "pass",
                "machine_release_status": "allowed",
                "release_authority_vocabulary": {
                    "blocker_reason_ids": [
                        "sealed_release_not_clean_pass",
                        "distribution_package_not_materialized",
                    ]
                },
            },
        )
        (self.vault / "tmp" / "release-closeout-post-check-finalizer.json").unlink()

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["can_execute_trial"])
        self.assertTrue(report["can_promote_result"])
        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn(
            "promotion_blocked_by_release_batch_manifest_failure", blocker_ids
        )
        batch_summary = report["diagnostics"]["release_closeout_batch_manifest_summary"]
        self.assertEqual(batch_summary["status"], "pass")
        self.assertIn(
            "sealed_release_status=unsealed_distribution_not_provided",
            batch_summary["summary"],
        )
        self.assertIn("auto_improve_lane_status=pass", batch_summary["summary"])

    def test_batch_manifest_gate_ignores_self_referential_auto_improve_lane_snapshot(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "status": "pass",
                "batch_integrity_status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {"status": "materialized"},
                "auto_improve_lane_status": "blocked",
                "machine_release_status": "allowed",
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        blocker_ids = {item["id"] for item in report["promotion_blockers"]}
        self.assertNotIn(
            "promotion_blocked_by_release_batch_manifest_failure", blocker_ids
        )
        batch_summary = report["diagnostics"]["release_closeout_batch_manifest_summary"]
        self.assertEqual(batch_summary["status"], "pass")
        self.assertFalse(batch_summary["release_blocking"])
        self.assertIn("auto_improve_lane_status=blocked", batch_summary["summary"])

    def test_build_readiness_report_requires_review_when_learning_is_uncertain(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 7,
                    "recent_window": 20,
                    "recent_attempt_count": 7,
                    "session_reports_considered": 0,
                },
                "metrics": {
                    "rework_count": 5,
                    "moving_averages": {
                        "hold": 0.2857,
                        "discard": 0.1429,
                    },
                    "defect_escape_proxy": {
                        "count": 3,
                    },
                },
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"},
                    "session_calibration": {"status": "no_session_context"},
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())
        inputs = load_readiness_inputs(self.vault, context=fixed_context())
        learning = assess_learning_readiness(inputs)
        learning_claim_blockers, learning_promotion_blockers = (
            learning_claim_blocker_payloads(
                learning,
                signoff_active=bool(inputs.learning_signoff_summary.get("active")),
            )
        )

        self.assertEqual(report["execution_readiness"]["status"], "pass")
        self.assertTrue(report["queue"]["ready"])
        self.assertEqual(report["learning_readiness"]["status"], "learning_uncertain")
        self.assertEqual(
            report["learning_readiness"]["gate_effect"],
            "operator_review_required",
        )
        self.assertTrue(report["can_execute_trial"])
        self.assertFalse(report["can_promote_result"])
        self.assertTrue(readiness_can_run(report))
        self.assertEqual(readiness_exit_code(report), 0)
        self.assertTrue(report["learning_readiness"]["can_run"])
        self.assertFalse(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(
            report["learning_readiness"]["metrics"]["attempts_considered"], 7
        )
        self.assertEqual(
            report["learning_readiness"]["metrics"]["session_reports_considered"], 0
        )
        self.assertEqual(
            report["learning_readiness"]["metrics"]["session_calibration_status"],
            "no_session_context",
        )
        self.assertEqual(
            report["learning_readiness"]["metrics"]["telemetry_coverage_ratio"], 0.0
        )
        self.assertEqual(report["learning_readiness"]["metrics"]["rework_count"], 5)
        self.assertEqual(
            report["learning_readiness"]["metrics"]["hold_moving_average"], 0.2857
        )
        self.assertEqual(
            report["learning_readiness"]["metrics"]["discard_moving_average"], 0.1429
        )
        signal_ids = {
            signal["id"] for signal in report["learning_readiness"]["signals"]
        }
        self.assertSetEqual(
            signal_ids,
            {
                "outcome_metrics_attempt_history_below_minimum",
                "outcome_metrics_session_rollup_missing",
                "mechanism_review_session_context_missing",
                "recent_hold_moving_average",
                "high_rework",
                "defect_escape_proxy",
            },
        )
        for signal in report["learning_readiness"]["signals"]:
            self.assertEqual(signal["owner"], "runtime-maintainer")
            self.assertGreaterEqual(signal["minimum_sample_size"], 1)
            self.assertTrue(signal["required_evidence"])
            self.assertIn("make ", signal["next_evaluation_command"])
            self.assertTrue(signal["closure_strategy"])
        attempt_history_signal = next(
            signal
            for signal in report["learning_readiness"]["signals"]
            if signal["id"] == "outcome_metrics_attempt_history_below_minimum"
        )
        self.assertEqual(attempt_history_signal["minimum_sample_size"], 10)
        self.assertIn(
            "summary.attempts_considered",
            attempt_history_signal["required_evidence"][0],
        )
        self.assertEqual(len(report["learning_claim_blockers"]), 1)
        self.assertEqual(report["learning_claim_blockers"], learning_claim_blockers)
        self.assertEqual(report["promotion_blockers"], learning_promotion_blockers)
        self.assertEqual(
            report["promotion_blockers"], report["learning_claim_blockers"]
        )
        learning_claim_blocker = report["learning_claim_blockers"][0]
        self.assertEqual(
            learning_claim_blocker["id"], "learning_blocked_by_review_required"
        )
        self.assertEqual(learning_claim_blocker["scope"], "learning_readiness")
        self.assertEqual(learning_claim_blocker["status"], "open")
        self.assertEqual(learning_claim_blocker["severity"], "blocker")
        self.assertFalse(learning_claim_blocker["accepted_risk"])
        self.assertEqual(
            learning_claim_blocker["gate_effect"],
            "operator_review_required",
        )
        self.assertEqual(learning_claim_blocker["source_status"], "learning_uncertain")
        self.assertSetEqual(set(learning_claim_blocker["signal_ids"]), signal_ids)
        self.assertIn(
            "operator must record accepted risk",
            learning_claim_blocker["required_evidence"][1],
        )
        self.assertEqual(
            report["next_action"],
            report["learning_readiness"]["recommended_next_step"],
        )
        self.assertIn(
            "GOAL_ALLOW_LEARNING_UNCERTAIN=1",
            report["learning_readiness"]["recommended_next_step"],
        )
        self.assertIn(
            "make auto-improve-goal-run",
            report["learning_readiness"]["recommended_next_step"],
        )

    def test_active_learning_signoff_unblocks_promotion_without_claiming_learning(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 0,
                },
                "metrics": {
                    "rework_count": 3,
                    "moving_averages": {"hold": 0.5, "discard": 0.0},
                    "defect_escape_proxy": {"count": 0},
                },
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"},
                    "session_calibration": {"status": "active"},
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {"proposal_id": "proposal-ready", "blocked_by": [], "priority": 55}
                ],
            },
        )
        self._write_report(
            "ops/reports/learning-readiness-signoff.json",
            {
                "artifact_kind": "learning_readiness_signoff",
                "linked_blocker_id": "learning_blocked_by_review_required",
                "accepted_by": "operator@example.test",
                "accepted_at": "2026-05-17T11:00:00Z",
                "expires_at": "2026-05-24T11:00:00Z",
                "risk_owner": "runtime-maintainer",
                "revalidation_condition": "Rerun release evidence before release.",
                "rollback_trigger": "Treat the blocker as active if learning evidence changes.",
            },
            enveloped=False,
        )

        report = build_readiness_report(self.vault, context=fixed_context())
        inputs = load_readiness_inputs(self.vault, context=fixed_context())
        learning = assess_learning_readiness(inputs)
        learning_claim_blockers, learning_promotion_blockers = (
            learning_claim_blocker_payloads(
                learning,
                signoff_active=bool(inputs.learning_signoff_summary.get("active")),
            )
        )

        self.assertTrue(report["can_execute_trial"])
        self.assertTrue(report["can_promote_result"])
        self.assertEqual(
            report["learning_readiness"]["gate_effect"],
            "operator_review_required",
        )
        self.assertEqual(
            [item["id"] for item in report["learning_claim_blockers"]],
            ["learning_blocked_by_review_required"],
        )
        self.assertEqual(report["learning_claim_blockers"], learning_claim_blockers)
        self.assertEqual(learning_promotion_blockers, [])
        self.assertEqual(report["promotion_blockers"], [])
        self.assertEqual(
            report["diagnostics"]["learning_signoff_summary"]["signoff_status"],
            "active",
        )
        self.assertIn(
            "runner heartbeat",
            report["learning_readiness"]["recommended_next_step"],
        )
        self.assertNotIn(
            "auto_improve_loop",
            report["learning_readiness"]["recommended_next_step"],
        )
        self.assertNotIn(
            "--max-proposals 10000",
            report["learning_readiness"]["recommended_next_step"],
        )

    def test_build_readiness_report_reuses_latest_loop_health_summary_when_available(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/auto-session-older.json",
            {
                "session_id": "auto-session-older",
                "generated_at": "2026-04-22T02:00:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 1,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_count": 0,
                        "finalized_run_count": 1,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 1.0},
                        "health_flags": [],
                    }
                },
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/auto-session-newer.json",
            {
                "session_id": "auto-session-newer",
                "generated_at": "2026-04-22T03:00:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 4,
                        "rework_count": 2,
                        "rollback_signal_count": 1,
                        "defect_escape_count": 1,
                        "finalized_run_count": 3,
                        "executor_failure_count": 1,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 1,
                        "coverage_ratios": {"telemetry": 0.75},
                        "health_flags": [
                            "rework_detected",
                            "rollback_signals_present",
                            "executor_failures_present",
                        ],
                    }
                },
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/standalone-run-telemetry.json",
            {
                "session_id": "standalone-run-telemetry",
                "generated_at": "2026-04-22T04:00:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 99,
                        "rework_count": 99,
                        "rollback_signal_count": 99,
                        "defect_escape_count": 99,
                        "finalized_run_count": 99,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 0.01},
                        "health_flags": ["partial_telemetry_coverage"],
                    }
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        loop_health_summary = report["diagnostics"]["loop_health_summary"]
        self.assertEqual(loop_health_summary["status"], "available")
        self.assertEqual(loop_health_summary["gate_effect"], "none")
        self.assertEqual(
            loop_health_summary["source_report"],
            "ops/reports/routing-provenance-aggregates/auto-session-newer.json",
        )
        self.assertEqual(loop_health_summary["session_id"], "auto-session-newer")
        self.assertEqual(loop_health_summary["attempt_count"], 4)
        self.assertEqual(loop_health_summary["rework_count"], 2)
        self.assertEqual(loop_health_summary["rollback_signal_count"], 1)
        self.assertEqual(loop_health_summary["telemetry_coverage_ratio"], 0.75)
        self.assertEqual(report["learning_readiness"]["status"], "learning_likely")
        self.assertEqual(
            report["learning_readiness"]["metrics"]["telemetry_coverage_ratio"], 0.75
        )
        self.assertEqual(report["learning_readiness"]["signals"], [])
        self.assertEqual(report["learning_claim_blockers"], [])
        self.assertEqual(
            loop_health_summary["health_flags"],
            [
                "rework_detected",
                "rollback_signals_present",
                "executor_failures_present",
            ],
        )
        self.assertIn("attempts=4", loop_health_summary["summary"])
        self.assertIn("alerts:", loop_health_summary["summary"])

    def test_build_readiness_report_prefers_telemetry_aggregate_over_empty_latest_session(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {"proposal_id": "proposal-ready", "blocked_by": [], "priority": 55}
                ],
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/auto-session-empty-newer.json",
            {
                "session_id": "auto-session-empty-newer",
                "generated_at": "2026-04-22T05:00:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 0,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_count": 0,
                        "finalized_run_count": 0,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 0.0},
                        "health_flags": ["missing_telemetry_coverage"],
                    }
                },
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/standalone-run-telemetry.json",
            {
                "session_id": "standalone-run-telemetry",
                "generated_at": "2026-04-22T04:00:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 28,
                        "rework_count": 3,
                        "rollback_signal_count": 1,
                        "defect_escape_count": 0,
                        "finalized_run_count": 24,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 0.8571},
                        "health_flags": ["partial_telemetry_coverage"],
                    }
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        loop_health_summary = report["diagnostics"]["loop_health_summary"]
        self.assertEqual(
            loop_health_summary["source_report"],
            "ops/reports/routing-provenance-aggregates/standalone-run-telemetry.json",
        )
        self.assertEqual(loop_health_summary["session_id"], "standalone-run-telemetry")
        self.assertEqual(loop_health_summary["attempt_count"], 28)
        self.assertEqual(loop_health_summary["telemetry_coverage_ratio"], 0.8571)
        self.assertEqual(report["learning_readiness"]["status"], "learning_likely")
        self.assertEqual(report["learning_readiness"]["signals"], [])

    def test_build_readiness_report_requires_review_when_loop_health_telemetry_is_missing(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                },
                "metrics": {
                    "rework_count": 0,
                    "moving_averages": {
                        "hold": 0.0,
                        "discard": 0.0,
                    },
                    "defect_escape_proxy": {
                        "count": 0,
                    },
                },
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/auto-session-zero-telemetry.json",
            {
                "session_id": "auto-session-zero-telemetry",
                "generated_at": "2026-04-22T03:30:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 0,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_count": 0,
                        "finalized_run_count": 0,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 0.0},
                        "health_flags": ["missing_telemetry_coverage"],
                    }
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertEqual(report["execution_readiness"]["status"], "pass")
        self.assertTrue(report["queue"]["ready"])
        self.assertEqual(report["learning_readiness"]["status"], "learning_uncertain")
        self.assertEqual(
            report["learning_readiness"]["gate_effect"],
            "operator_review_required",
        )
        self.assertTrue(report["learning_readiness"]["can_run"])
        self.assertFalse(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(
            report["learning_readiness"]["metrics"]["telemetry_coverage_ratio"], 0.0
        )
        signal_ids = {
            signal["id"] for signal in report["learning_readiness"]["signals"]
        }
        self.assertSetEqual(signal_ids, {"loop_health_telemetry_coverage_missing"})
        self.assertEqual(len(report["learning_claim_blockers"]), 1)
        self.assertEqual(
            report["learning_claim_blockers"][0]["id"],
            "learning_blocked_by_review_required",
        )
        self.assertEqual(
            report["learning_claim_blockers"][0]["signal_ids"],
            ["loop_health_telemetry_coverage_missing"],
        )
        self.assertEqual(
            report["next_action"],
            report["learning_readiness"]["recommended_next_step"],
        )
        self.assertIn("make auto-improve-goal-run", report["next_action"])
        self.assertNotIn("auto_improve_loop", report["next_action"])

    def test_build_readiness_report_treats_partial_loop_health_telemetry_as_non_blocking(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                },
                "metrics": {
                    "rework_count": 0,
                    "moving_averages": {
                        "hold": 0.0,
                        "discard": 0.0,
                    },
                    "defect_escape_proxy": {
                        "count": 0,
                    },
                },
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"},
                    "session_calibration": {"status": "active"},
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/auto-session-partial-telemetry.json",
            {
                "session_id": "auto-session-partial-telemetry",
                "generated_at": "2026-04-22T03:30:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 12,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_count": 0,
                        "finalized_run_count": 12,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 0.5},
                        "health_flags": ["partial_telemetry_coverage"],
                    }
                },
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertEqual(report["learning_readiness"]["status"], "learning_likely")
        self.assertTrue(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(report["learning_readiness"]["signals"], [])
        self.assertEqual(
            report["learning_readiness"]["metrics"]["telemetry_coverage_ratio"], 0.5
        )

    def test_build_readiness_report_requires_typed_same_eval_evidence_for_same_eval_family(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                },
                "metrics": {
                    "rework_count": 0,
                    "moving_averages": {"hold": 0.0, "discard": 0.0},
                    "defect_escape_proxy": {"count": 0},
                },
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"},
                    "session_calibration": {"status": "active"},
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-same-eval",
                        "failure_mode": "repeated_same_eval_or_discard",
                        "run_ids": ["run-same-eval"],
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/auto-session-typed-telemetry.json",
            {
                "session_id": "auto-session-typed-telemetry",
                "generated_at": "2026-04-22T03:30:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 12,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_count": 0,
                        "finalized_run_count": 12,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 1.0},
                        "health_flags": [],
                    }
                },
            },
            enveloped=False,
        )
        run_dir = self.vault / "runs" / "run-same-eval"
        run_dir.mkdir(parents=True)
        (run_dir / "run-telemetry.json").write_text(
            json.dumps(
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "run_id": "run-same-eval",
                    "generated_at": "2026-04-22T03:00:00Z",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {},
                    "same_eval_reason": "legacy free text only",
                    "behavior_delta_digest": "a" * 64,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertFalse(report["learning_readiness"]["likely_to_learn"])
        signal_ids = {
            signal["id"] for signal in report["learning_readiness"]["signals"]
        }
        self.assertIn("same_eval_typed_evidence_missing", signal_ids)
        self.assertEqual(
            report["diagnostics"]["same_eval_telemetry_summary"]["status"],
            "blocked",
        )
        self.assertEqual(
            report["learning_readiness"]["metrics"][
                "same_eval_reason_code_coverage_ratio"
            ],
            0.0,
        )

    def test_build_readiness_report_accepts_complete_typed_same_eval_evidence(
        self,
    ) -> None:
        self.test_build_readiness_report_requires_typed_same_eval_evidence_for_same_eval_family()
        run_path = self.vault / "runs" / "run-same-eval" / "run-telemetry.json"
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        payload["same_eval_reason_code"] = "telemetry_discoverability_improved"
        payload["strict_secondary_improvement_present"] = True
        payload["secondary_improvement_axes"] = ["lint"]
        run_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(
            report["diagnostics"]["same_eval_telemetry_summary"]["status"], "pass"
        )
        self.assertEqual(report["learning_readiness"]["signals"], [])

    def test_build_readiness_report_accepts_legacy_reconstructed_same_eval_evidence(
        self,
    ) -> None:
        self.test_build_readiness_report_requires_typed_same_eval_evidence_for_same_eval_family()
        run_path = self.vault / "runs" / "run-same-eval" / "run-telemetry.json"
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        payload["decision_record"] = {
            "reason_code": "equal_score_secondary_eligibility",
            "source_rule": "equal_score_secondary_eligibility",
        }
        run_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._write_report(
            "ops/reports/learning-confirmed-legacy-reconstruction.json",
            {
                "artifact_kind": "learning_confirmed_legacy_reconstruction",
                "status": "pass",
                "run_reconstructions": [
                    {
                        "run_id": "run-same-eval",
                        "reconstruction_status": "reconstructed",
                        "parsed_strict_secondary_improvement_present": True,
                        "parsed_secondary_axes": ["lint"],
                        "telemetry_behavior_delta_digest": "a" * 64,
                    }
                ],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(
            report["diagnostics"]["same_eval_telemetry_summary"]["status"], "pass"
        )
        self.assertEqual(report["learning_readiness"]["signals"], [])

    def test_build_readiness_report_ignores_blocked_same_eval_proposals_for_typed_signal(
        self,
    ) -> None:
        self._write_ready_queue_reports()
        mutation = json.loads(
            (self.vault / "ops/reports/mutation-proposals.json").read_text(
                encoding="utf-8"
            )
        )
        mutation["summary"]["proposals_emitted"] = 2
        mutation["summary"]["blocked_proposals"] = 1
        mutation["diagnostics"] = {
            "queue_selection": {
                "available_proposal_count": 2,
                "selected_proposal_count": 2,
                "runnable_available_count": 1,
                "blocked_available_count": 1,
                "selected_runnable_count": 1,
                "selected_blocked_count": 1,
                "blocked_reason_counts": [{"reason": "recent_log_overlap", "count": 1}],
            }
        }
        mutation["proposals"] = [
            {
                "proposal_id": "proposal-ready",
                "blocked_by": [],
                "priority": 55,
            },
            {
                "proposal_id": "blocked-same-eval",
                "failure_mode": "repeated_same_eval_or_discard",
                "run_ids": ["run-same-eval-missing-typed-fields"],
                "blocked_by": ["recent_log_overlap"],
                "priority": 54,
            },
        ]
        self._write_report("ops/reports/mutation-proposals.json", mutation)
        run_dir = self.vault / "runs" / "run-same-eval-missing-typed-fields"
        run_dir.mkdir(parents=True)
        (run_dir / "run-telemetry.json").write_text(
            json.dumps(
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "run_id": "run-same-eval-missing-typed-fields",
                    "generated_at": "2026-04-22T03:00:00Z",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(
            report["diagnostics"]["same_eval_telemetry_summary"]["status"],
            "not_applicable",
        )
        self.assertEqual(
            report["diagnostics"]["same_eval_telemetry_summary"]["run_count"], 0
        )
        self.assertEqual(report["learning_readiness"]["signals"], [])

    def test_build_readiness_report_uses_clean_current_loop_health_for_quality_shadow(
        self,
    ) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                },
                "metrics": {
                    "rework_count": 5,
                    "moving_averages": {"hold": 0.5, "discard": 0.0},
                    "defect_escape_proxy": {"count": 3},
                },
            },
        )
        self._write_report(
            "ops/reports/routing-provenance-aggregates/current-clean-goal-run.json",
            {
                "session_id": "current-clean-goal-run",
                "generated_at": "2026-04-22T03:30:00Z",
                "audit_rollup": {
                    "loop_health": {
                        "attempt_count": 1,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_count": 0,
                        "finalized_run_count": 1,
                        "executor_failure_count": 0,
                        "routing_report_parse_gap_count": 0,
                        "executor_report_parse_gap_count": 0,
                        "coverage_ratios": {"telemetry": 1.0},
                        "health_flags": [],
                    }
                },
            },
            enveloped=False,
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertTrue(report["learning_readiness"]["likely_to_learn"])
        self.assertEqual(report["learning_readiness"]["signals"], [])
        self.assertEqual(
            report["diagnostics"]["loop_health_summary"]["source_report"],
            "ops/reports/routing-provenance-aggregates/current-clean-goal-run.json",
        )

    def test_write_readiness_report_uses_bundled_schema_when_vault_schema_is_absent(
        self,
    ) -> None:
        report = build_readiness_report(
            self.vault,
            context=fixed_context(),
            outcome_metrics_report={
                "summary": {
                    "attempts_considered": 12,
                    "session_reports_considered": 1,
                }
            },
            mechanism_review_report={
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
            mutation_proposal_report={
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
        (
            self.vault / "ops" / "schemas" / "auto-improve-readiness-report.schema.json"
        ).unlink()

        destination = write_readiness_report(self.vault, report)
        persisted = json.loads(destination.read_text(encoding="utf-8"))

        self.assertTrue(readiness_can_run(persisted))
        self.assertEqual(persisted["remediations"], [])

    def test_build_readiness_report_summarizes_upstream_attention_statuses(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 3,
                    "recent_window": 20,
                    "recent_attempt_count": 3,
                    "session_reports_considered": 0,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "status": "attention",
                "summary": {"candidates_emitted": 0},
                "diagnostics": {
                    "bootstrap": {
                        "status": "bootstrap_history_insufficient",
                        "summary": "fallback family still below the comparable-run floor",
                        "target_groups_under_min_history": [
                            {
                                "primary_targets": [
                                    "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                                ],
                                "blocked_candidate_types": [
                                    {
                                        "candidate_type": "mechanism_eval_stagnation_candidate",
                                        "required_runs": 2,
                                        "additional_runs_needed": 1,
                                    }
                                ],
                            }
                        ],
                    }
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "status": "attention",
                "summary": {
                    "source_candidates_read": 0,
                    "proposals_emitted": 0,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "no proposals emitted",
                },
                "diagnostics": {
                    "evidence_gaps": [
                        "mechanism review emitted zero candidates",
                    ]
                },
                "proposals": [],
            },
        )

        report = build_readiness_report(self.vault, context=fixed_context())

        self.assertIn(
            "mechanism_review.status=attention (bootstrap_history_insufficient; candidates_emitted=0)",
            report["execution_readiness"]["reasons"],
        )
        self.assertIn(
            "mutation_proposal.status=attention (no proposals emitted; proposals_emitted=0)",
            report["execution_readiness"]["reasons"],
        )
        self.assertGreaterEqual(len(report["queue"]["evidence_gaps"]), 3)
        self.assertEqual(
            report["queue"]["evidence_gaps"][0],
            "mechanism_review.status=attention (bootstrap_history_insufficient; candidates_emitted=0)",
        )
        self.assertEqual(
            report["queue"]["evidence_gaps"][1],
            "mutation_proposal.status=attention (no proposals emitted; proposals_emitted=0)",
        )

    def test_write_readiness_report_does_not_fallback_from_invalid_vault_schema(
        self,
    ) -> None:
        report = build_readiness_report(
            self.vault,
            context=fixed_context(),
            outcome_metrics_report={"summary": {"attempts_considered": 0}},
            mechanism_review_report={"summary": {"candidates_emitted": 0}},
            mutation_proposal_report={
                "summary": {
                    "source_candidates_read": 0,
                    "proposals_emitted": 0,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "empty",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [],
            },
        )
        (
            self.vault / "ops" / "schemas" / "auto-improve-readiness-report.schema.json"
        ).write_text(
            "{not-json",
            encoding="utf-8",
        )

        with self.assertRaises(json.JSONDecodeError):
            write_readiness_report(self.vault, report)


if __name__ == "__main__":
    unittest.main()
