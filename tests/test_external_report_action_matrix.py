from __future__ import annotations

import datetime as dt
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

    def test_goal_native_long_run_terms_map_to_specific_actions(self) -> None:
        (self.external / "goal-runtime.md").write_text(
            "# Goal Runtime\n\n"
            "Track run id and session_id in goal-run-status, verify the 30-minute trial "
            "to 6-hour ramp to 2-day candidate to 5-day sustained execution ladder, "
            "and preserve executor retry-after backoff heartbeat observability.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        coverage = {
            item["path"]: item["matched_action_ids"]
            for item in report["active_report_coverage"]
        }
        matched = set(coverage["external-reports/goal-runtime.md"])
        self.assertIn("goal_run_status_audit_resume", matched)
        self.assertIn("goal_execution_ladder_profiles", matched)
        self.assertIn("goal_executor_backoff_observability", matched)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

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
