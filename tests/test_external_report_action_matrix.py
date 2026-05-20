from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.external_report_action_matrix import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "external-report-action-matrix.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 10, 8, 30, tzinfo=dt.timezone.utc),
    )


def _canonical_json_digest(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class ExternalReportActionMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self.external = self.vault / "external-reports"
        self.external.mkdir(exist_ok=True)
        (self.external / "archive").mkdir(exist_ok=True)
        self._copy_schema()
        self._write_support_reports()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_schema(self) -> None:
        destination = self.vault / "ops" / "schemas" / "external-report-action-matrix.schema.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _write_support_reports(self) -> None:
        self._write_json(
            "tmp/release-workflow-order-guard.json",
            {"status": "pass"},
        )
        self._write_json(
            "tmp/workflow-dependency-planner.json",
            {
                "workflow_rules": [
                    {
                        "workflow_id": "workflow_dependency_planner_closeout",
                        "targets": ["workflow-dependency-planner", "generated-artifact-index-body"],
                    }
                ]
            },
        )
        self._write_json(
            "ops/reports/outcome-provenance-gate-policy.json",
            {"status": "pass"},
        )
        self._write_json(
            "ops/reports/function-budget-refactor-proposals.json",
            {"status": "attention"},
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {"summary": {"active_reference_set_status": "current"}},
        )

    def _write_release_verification_reports(self) -> None:
        self._write_json("ops/reports/source-package-clean-extract.json", {"status": "pass"})
        self._write_json("ops/reports/release-smoke-report.json", {"status": "pass"})
        self._write_json(
            "ops/reports/test-execution-summary-full.json",
            {
                "status": "pass",
                "counts": {"passed": 1085, "failed": 0, "errors": 0},
                "pytest_collect_nodeid_digest": {"nodeid_count": 1085},
            },
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {"can_promote_result": True, "promotion_blockers": []},
        )
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "release_readiness_state": "clean_pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "machine_release_allowed": True,
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": "clean_pass",
                        "semantic_release_status": "clean_pass",
                        "sealed_release_status": "sealed_clean_pass",
                    },
                    "blocker_reason_ids": [],
                },
                "summary": {
                    "live_make_check_status": "pass",
                    "blocker_count": 4,
                    "source_clean_blocker_count": 0,
                },
            },
        )
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {
                "status": "pass",
                "summary": {
                    "live_rerun_fail_count": 0,
                    "live_rerun_not_run_count": 0,
                    "required_input_fail_count": 0,
                },
            },
        )
        self._write_json(
            "ops/reports/release-closeout-fixed-point.json",
            {"status": "pass", "converged": True},
        )
        self._write_json(
            "ops/reports/release-closeout-finality-attestation.json",
            {"fixed_point_report": {"status": "pass"}},
        )
        self._write_json("ops/reports/release-closeout-batch-manifest.json", {"status": "fail"})

    def test_matrix_covers_non_archived_reports_and_validates_schema(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nP0: script-output-surfaces, workflow_dependency_planner, "
            "source package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )
        (self.external / "maintenance.md").write_text(
            "# Maintenance\n\nP1: function-budget review candidate, Windows path alias, "
            "outcome provenance, external report lifecycle.\n",
            encoding="utf-8",
        )
        (self.external / "archive" / "old.md").write_text(
            "# Old\n\nP0: script-output-surfaces\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["summary"]["active_report_count"], 3)
        self.assertEqual(report["summary"]["archived_report_count"], 1)
        self.assertEqual(report["summary"]["reference_manifest_alignment_status"], "drift")
        self.assertEqual(report["summary"]["reference_manifest_missing_active_report_count"], 2)
        self.assertEqual(
            report["reference_manifest_alignment"]["missing_active_report_paths"],
            ["external-reports/maintenance.md", "external-reports/release.md"],
        )
        self.assertEqual(report["summary"]["unmatched_active_report_count"], 0)
        paths = {item["path"] for item in report["active_report_coverage"]}
        self.assertIn("external-reports/release.md", paths)
        self.assertIn("external-reports/maintenance.md", paths)
        self.assertIn("external-reports/report-reference-manifest.json", paths)
        self.assertFalse(any("/archive/" in path for path in paths))
        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(actions["release_writer_dependency_single_source"]["current_status"], "implemented")
        self.assertEqual(actions["outcome_provenance_gate_policy"]["current_status"], "implemented")
        self.assertEqual(actions["external_report_lifecycle"]["current_status"], "partially_automated")
        self.assertIn(
            "external-reports/release.md",
            actions["script_output_surfaces_currentness"]["source_report_paths"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

    def test_matrix_passes_when_reference_manifest_matches_active_reports(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nexternal report lifecycle.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [
                    {"path": "external-reports/release.md"},
                ],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(report["summary"]["reference_manifest_alignment_status"], "current")
        self.assertEqual(report["summary"]["reference_manifest_missing_active_report_count"], 0)
        self.assertEqual(report["summary"]["reference_manifest_stale_reference_count"], 0)
        self.assertEqual(actions["external_report_lifecycle"]["current_status"], "implemented")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_release_verified_actions_become_implemented_after_closeout(self) -> None:
        self._write_release_verification_reports()
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in {
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        }:
            self.assertEqual(actions[action_id]["current_status"], "implemented")
        self.assertEqual(actions["release_writer_dependency_single_source"]["current_status"], "implemented")
        self.assertEqual(report["summary"]["requires_release_run_verification_count"], 0)

    def test_negative_lessons_and_remediation_backlog_are_implementation_artifacts(self) -> None:
        for rel_path in (
            "ops/schemas/self-improvement-negative-lessons.schema.json",
            "ops/schemas/remediation-backlog.schema.json",
            "tests/test_self_improvement_negative_lessons.py",
            "tests/test_remediation_backlog.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        self._write_json(
            "ops/reports/self-improvement-negative-lessons.json",
            {
                "artifact_kind": "self_improvement_negative_lessons",
                "producer": "ops.scripts.self_improvement_negative_lessons",
                "status": "attention",
            },
        )
        self._write_json(
            "ops/reports/remediation-backlog.json",
            {
                "artifact_kind": "remediation_backlog",
                "producer": "ops.scripts.remediation_backlog",
                "status": "attention",
            },
        )
        (self.external / "learning.md").write_text(
            "# Learning Review\n\nnegative learning and remediation backlog.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(actions["negative_learning_ledger"]["current_status"], "implemented")
        self.assertEqual(actions["remediation_backlog"]["current_status"], "implemented")

    def test_command_heartbeat_requires_source_package_heartbeat_evidence(self) -> None:
        for rel_path in (
            "ops/scripts/core/command_runtime.py",
            "ops/schemas/executor-report.schema.json",
            "ops/scripts/core/source_package_clean_extract.py",
            "ops/schemas/source-package-clean-extract.schema.json",
            "tests/test_command_runtime_heartbeat.py",
            "tests/test_source_package_clean_extract.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        self._write_json(
            "ops/reports/source-package-clean-extract.json",
            {
                "status": "pass",
                "heartbeat_observability": {
                    "status": "pass",
                    "command_count": 4,
                    "heartbeat_enabled_command_count": 4,
                    "heartbeat_event_count": 2,
                },
            },
        )
        (self.external / "heartbeat.md").write_text(
            "# Heartbeat Review\n\nquiet_seconds and heartbeat observability.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["command_heartbeat_observability"]["current_status"],
            "implemented",
        )

    def test_sealed_preflight_canonicalization_requires_canonical_report(self) -> None:
        for rel_path in (
            "mk/release.mk",
            "ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py",
            "ops/scripts/release/release_closeout_sealed_rehearsal_check.py",
            "ops/schemas/release-closeout-sealed-rehearsal-check.schema.json",
            "tests/test_release_closeout_sealed_rehearsal_check.py",
            "tests/test_auto_improve_readiness_runtime.py",
            "tests/test_makefile_static_gates.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        self._write_json(
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
            },
        )
        (self.external / "sealed.md").write_text(
            "# Sealed Review\n\nsealed preflight and binding_pass_authority_blocked.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["sealed_preflight_canonicalization"]["current_status"],
            "implemented",
        )

    def test_goal_native_actions_require_current_canonical_runtime_reports(self) -> None:
        for rel_path in (
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/scripts/core/codex_goal_client.py",
            "ops/scripts/mechanism/codex_goal_prompt.py",
            "ops/schemas/codex-goal-prompt.schema.json",
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/auto_improve_runtime.py",
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "ops/scripts/mechanism/goal_runtime_certificate_report.py",
            "ops/scripts/mechanism/goal_runtime_certificate.py",
            "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
            "ops/scripts/mechanism/goal_worktree_guard.py",
            "ops/schemas/goal-worktree-guard.schema.json",
            "ops/scripts/mechanism/goal_runtime_clean_transient.py",
            "ops/schemas/goal-runtime-clean-transient.schema.json",
            "tests/test_codex_goal_contract.py",
            "tests/test_codex_goal_client.py",
            "tests/test_codex_goal_prompt.py",
            "tests/test_auto_improve_runtime.py",
            "tests/test_goal_auto_improve_runtime.py",
            "tests/test_goal_run_status.py",
            "tests/test_goal_runtime_runner.py",
            "tests/test_goal_runtime_certificate.py",
            "tests/test_auto_improve_readiness_release_authority_runtime.py",
            "tests/test_goal_worktree_guard.py",
            "tests/test_goal_runtime_clean_transient.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        mechanism_makefile = self.vault / "mk/mechanism.mk"
        mechanism_makefile.parent.mkdir(parents=True, exist_ok=True)
        mechanism_makefile.write_text(
            "goal-runtime-clean-transient:\n"
            "\tpython -m ops.scripts.goal_runtime_clean_transient\n"
            "long-run-preflight-clean: goal-runtime-clean-transient auto-improve-goal-preflight\n",
            encoding="utf-8",
        )
        contract = {
            "$schema": "ops/schemas/codex-goal-contract.schema.json",
            "schema_version": 1,
            "contract_id": "auto-improve-goal",
            "objective": "Run bounded auto-improve only after the loop certificate is durable.",
            "non_goals": ["Do not claim sustained runtime before certificate verification."],
            "allowed_roots": [{"path": "ops/", "purpose": "runtime contracts"}],
            "budgets": {
                "max_wall_clock_seconds": 21600,
                "max_proposals": 1,
                "max_consecutive_failures": 1,
                "heartbeat_interval_seconds": 300,
                "checkpoint_interval_seconds": 1800,
            },
            "created_at": "2026-05-17T00:00:00Z",
            "created_by": "codex",
            "status": "active",
            "runtime": {
                "mode": "self_improvement_loop",
                "duration_seconds": 21600,
                "max_unattended_seconds": 21600,
                "certificate_status": "unverified",
                "verified_at": "",
            },
            "goal_backend": {
                "backend_type": "file",
                "process_persistent": True,
                "storage_path": "ops/reports/codex-goal-contract.json",
            },
            "stop_conditions": [{"condition_id": "promotion_guard_blocked"}],
            "required_evidence": [
                {"evidence_id": "auto_improve_readiness", "path": "ops/reports/auto-improve-readiness.json", "required_for_promotion": True},
                {"evidence_id": "goal_run_status", "path": "ops/reports/goal-run-status.json", "required_for_promotion": True},
            ],
            "promotion_guard": {
                "can_promote_result": True,
                "promotion_blockers": [],
                "sealed_authority_clean": True,
                "runtime_certificate_verified": False,
                "sustained_runtime_claimed": False,
                "no_sustained_claim_before_certificate_verified": True,
            },
        }
        contract_digest = _canonical_json_digest(contract)
        self._write_json("ops/reports/codex-goal-contract.json", contract)
        self._write_json(
            "ops/reports/codex-goal-prompt.json",
            {
                "artifact_kind": "codex_goal_prompt",
                "producer": "ops.scripts.codex_goal_prompt",
                "status": "pass",
                "goal_contract": {
                    "contract_sha256": contract_digest,
                    "process_persistent_backend": True,
                },
                "promotion_guard": {"sustained_runtime_claimed": False},
                "prompt": {
                    "includes_budget_limits": True,
                    "includes_allowed_roots": True,
                    "includes_sustained_claim_ban": True,
                },
            },
        )
        self._write_json(
            "ops/reports/goal-run-status.json",
            {
                "artifact_kind": "goal_run_status",
                "producer": "ops.scripts.goal_run_status",
                "status": "attention",
                "goal": {
                    "contract_sha256": contract_digest,
                    "backend": {"process_persistent": True},
                },
                "artifacts": {
                    "status_report_path": "ops/reports/goal-run-status.json",
                    "status_markdown_path": "runs/goal-auto-improve-trial/status.md",
                    "audit_log_path": "runs/goal-auto-improve-trial/audit-log.jsonl",
                    "resume_metadata_path": "runs/goal-auto-improve-trial/resume-metadata.json",
                    "checkpoint_command_log_path": "runs/goal-auto-improve-trial/checkpoint-command-events.jsonl",
                },
                "health": {
                    "heartbeat_status": "current",
                    "checkpoint_status": "current",
                    "command_heartbeat_status": "current",
                    "backoff_status": "inactive",
                    "resume_status": "not_requested",
                    "promotion_status": "blocked",
                    "can_promote_result": False,
                },
                "runtime_certificate": {
                    "status": "pending",
                    "mode": "self_improvement_loop",
                },
            },
        )
        self._write_json(
            "ops/reports/test-execution-summary.json",
            {"artifact_kind": "test_execution_summary", "status": "pass"},
        )
        self._write_json(
            "ops/reports/auto-improve-readiness.json",
            {
                "artifact_kind": "auto_improve_readiness_report",
                "diagnostics": {
                    "selected_contract_summary": {
                        "path": "ops/reports/test-execution-summary.json",
                        "status": "pass",
                    },
                    "artifact_freshness_summary": {"status": "pass"},
                },
                "promotion_blockers": [],
            },
        )
        self._write_json(
            "tmp/goal-worktree-guard.json",
            {
                "artifact_kind": "goal_worktree_guard",
                "producer": "ops.scripts.goal_worktree_guard",
                "status": "attention",
                "requested_mode": "git",
                "detected_mode": "git_worktree",
                "decisions": {
                    "can_execute_goal_runtime": True,
                    "can_promote_result": False,
                },
                "blockers": [{"blocker_id": "git_worktree_dirty"}],
            },
        )
        self._write_json(
            "tmp/goal-runtime-clean-transient.json",
            {
                "artifact_kind": "goal_runtime_clean_transient",
                "producer": "ops.scripts.goal_runtime_clean_transient",
                "status": "pass",
                "summary": {
                    "apply": True,
                    "candidate_count": 0,
                    "removable_count": 0,
                    "removed_count": 0,
                    "would_remove_count": 0,
                    "skipped_protected_count": 0,
                    "failed_count": 0,
                },
            },
        )
        (self.external / "goal.md").write_text(
            "# Goal Review\n\ngoal contract, set_goal, codex_goal_prompt, --goal-contract, "
            "goal-run-status, selected contract, Git worktree, transient artifact cleanup, "
            "goal-runtime-clean-transient, long-run-preflight-clean.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in {
            "goal_contract_schema",
            "codex_goal_adapter",
            "codex_goal_prompt_generator",
            "auto_improve_goal_contract_input",
            "goal_run_status_audit_resume",
            "selected_contract_currentness_gate",
            "git_worktree_goal_guard",
            "goal_runtime_transient_cleanup_gate",
        }:
            self.assertEqual(actions[action_id]["current_status"], "implemented", action_id)

    def test_release_verified_actions_accept_conditional_status_v2_authority(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "release_readiness_state": "clean_pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "machine_release_allowed": True,
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
                "summary": {
                    "live_make_check_status": "pass",
                    "blocker_count": 0,
                    "source_clean_blocker_count": 0,
                },
            },
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in {
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        }:
            self.assertEqual(
                actions[action_id]["current_status"],
                "implemented",
            )

    def test_release_verified_actions_follow_blocked_status_v2_authority(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "release_readiness_state": "clean_pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "machine_release_allowed": True,
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": "blocked",
                        "semantic_release_status": "blocked",
                        "sealed_release_status": "unsealed_release_blocked",
                    },
                    "blocker_reason_ids": ["machine_release_not_allowed"],
                },
                "summary": {
                    "live_make_check_status": "pass",
                    "blocker_count": 0,
                    "source_clean_blocker_count": 0,
                },
            },
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in {
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        }:
            self.assertEqual(
                actions[action_id]["current_status"],
                "requires_release_run_verification",
            )

    def test_release_verified_actions_allow_advisory_dashboard_attention(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {
                "status": "attention",
                "summary": {
                    "live_rerun_fail_count": 0,
                    "live_rerun_not_run_count": 1,
                    "required_input_fail_count": 0,
                },
                "gates": [
                    {
                        "gate_id": "advisory_gate",
                        "authoritative_for_release": False,
                        "live_rerun_state": {"status": "not_run"},
                    }
                ],
            },
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in {
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        }:
            self.assertEqual(actions[action_id]["current_status"], "implemented")
        self.assertEqual(actions["release_writer_dependency_single_source"]["current_status"], "implemented")

    def test_release_verified_actions_block_authoritative_dashboard_not_run(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {
                "status": "attention",
                "summary": {
                    "live_rerun_fail_count": 0,
                    "live_rerun_not_run_count": 1,
                    "required_input_fail_count": 0,
                },
                "gates": [
                    {
                        "gate_id": "authoritative_gate",
                        "authoritative_for_release": True,
                        "live_rerun_state": {"status": "not_run"},
                    }
                ],
            },
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in {
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        }:
            self.assertEqual(
                actions[action_id]["current_status"],
                "requires_release_run_verification",
            )


if __name__ == "__main__":
    unittest.main()
