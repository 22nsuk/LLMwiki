from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest
from ops.scripts.release_evidence_dashboard import build_report, main, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "release-evidence-dashboard.schema.json"
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 30, 9, 0, tzinfo=dt.UTC),
    )


class ReleaseEvidenceDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_report(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_closeout_summary_input(self) -> None:
        current_fingerprint = release_source_tree_fingerprint(self.vault)
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "checked_in_release_ready": True,
                "live_rerun_release_ready": True,
                "conditional_release_ready": False,
                "clean_release_ready": True,
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
                "operator_release_allowed": True,
                "requires_accepted_risk_review": False,
                "live_make_check": {
                    "path": "ops/reports/test-execution-summary-full.json",
                    "load_status": "ok",
                    "status": "pass",
                    "source_status": "pass",
                    "ready": True,
                    "represents_full_suite": True,
                    "suite_scope": "full_suite",
                    "nodeid_count": 1052,
                    "outcome_count": 1052,
                    "nodeid_outcome_consistency_status": "pass",
                    "toolchain_contract_status": "pass",
                    "toolchain_release_evidence_effect": "eligible",
                    "blocking": False,
                    "summary": "live_make_check status=pass",
                },
                "components": [
                    {
                        "name": "release_smoke",
                        "path": "ops/reports/release-smoke-report.json",
                        "ready": True,
                        "source_tree_fingerprint": current_fingerprint,
                        "currentness_status": "current",
                    }
                ],
                "test_failure_lanes": [
                    {
                        "lane_id": "report_schema_contract",
                        "source_path": "ops/reports/test-execution-summary.json",
                        "status": "pass",
                        "represented_in_summary": True,
                        "failed_count": 0,
                        "failed_nodeids": [],
                        "summary": "report schema contract lane passed",
                        "next_action": "none",
                    },
                    {
                        "lane_id": "runtime_telemetry_schema_contract",
                        "source_path": "ops/reports/test-execution-summary.json",
                        "status": "pass",
                        "represented_in_summary": True,
                        "failed_count": 0,
                        "failed_nodeids": [],
                        "summary": "runtime telemetry schema-contract lane passed",
                        "next_action": "none",
                    },
                ],
                "accepted_risk_delta": {
                    "status": "unchanged",
                    "previous_report_generated_at": "2026-04-30T08:00:00Z",
                    "added_count": 0,
                    "removed_count": 0,
                    "unchanged_count": 0,
                    "added": [],
                    "removed": [],
                    "unchanged": [],
                    "summary": "accepted_risk_delta status=unchanged; added=0; removed=0; unchanged=0",
                },
                "release_smoke_boundedness_gate": {
                    "path": "ops/reports/release-smoke-report.json",
                    "load_status": "ok",
                    "status": "pass",
                    "archive_budget_pass": True,
                    "failing_budget_count": 0,
                    "top_offender_count": 0,
                    "summary": "release_smoke_boundedness status=pass",
                },
                "blockers": [],
                "accepted_risks": [],
            },
        )

    def _write_artifact_freshness_input(self) -> None:
        self._write_report(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "pass",
                "summary": {"stable_debt_count": 0},
            },
        )

    def _write_fixed_point_inputs(self) -> None:
        fixed_point_payload = {
            "generated_at": "2026-04-30T08:30:00Z",
            "status": "pass",
            "converged": True,
            "iteration_count": 3,
            "duration_summary": {
                "iteration_count": 3,
                "command_run_count": 12,
                "total_duration_ms": 1200,
                "writer_costs": [
                    {
                        "name": "generated-artifact-index",
                        "target": "generated-artifact-index-body",
                        "run_count": 1,
                        "selected_iteration_count": 1,
                        "total_duration_ms": 300,
                        "average_duration_ms": 300,
                        "max_duration_ms": 300,
                        "skipped_after_first_iteration_count": 2,
                    },
                    {
                        "name": "release-evidence-dashboard",
                        "target": "release-evidence-dashboard-report",
                        "run_count": 3,
                        "selected_iteration_count": 3,
                        "total_duration_ms": 450,
                        "average_duration_ms": 150,
                        "max_duration_ms": 200,
                        "skipped_after_first_iteration_count": 0,
                    },
                ],
                "expensive_prerequisites_once": {
                    "targets": [
                        "closure-registry-envelope",
                        "manual-mutate-defect-registry",
                        "release-risk-taxonomy-matrix",
                    ],
                    "configured_target_count": 3,
                    "observed_target_count": 3,
                    "first_iteration_run_count": 3,
                    "post_first_iteration_selected_count": 0,
                    "post_first_iteration_run_count": 0,
                    "skipped_post_first_iteration_selection_count": 6,
                    "total_duration_ms": 450,
                    "skip_policy_effective": True,
                    "summary": "expensive prerequisites were selected only in iteration 1",
                },
                "summary": "2 writers ran 12 commands across 3 iterations",
            },
        }
        self._write_report(
            "ops/reports/release-closeout-fixed-point.json",
            fixed_point_payload,
        )
        fixed_point_digest = hashlib.sha256(
            (
                self.vault / "ops" / "reports" / "release-closeout-fixed-point.json"
            ).read_bytes()
        ).hexdigest()
        self._write_report(
            "ops/reports/release-closeout-fixed-point-cost-trend.json",
            {
                "status": "pass",
                "sample_count": 2,
                "latest_sample": {
                    "fixed_point_report_digest": fixed_point_digest,
                },
                "threshold_summary": {
                    "status": "pass",
                    "breached_writer_count": 0,
                    "breached_writers": [],
                    "summary": "fixed-point writer costs are within configured thresholds",
                },
            },
        )

    def _write_signoff_revalidation_input(self) -> None:
        self._write_report(
            "ops/reports/learning-readiness-signoff-revalidation.json",
            {
                "status": "pass",
                "required_actions": [],
                "signoff": {
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "2026-05-07T00:00:00Z",
                },
            },
        )

    def _write_learning_delta_scoreboard_input(self) -> None:
        self._write_report(
            "ops/reports/learning-delta-scoreboard.json",
            {
                "status": "pass",
                "summary": {
                    "claims_learning_improved": False,
                    "learning_claim_allowed": False,
                    "learning_likely": False,
                    "bounded_learning_claim_allowed": False,
                    "confirmed_learning_improvement_allowed": False,
                    "confirmed_learning_improvement_status": "not_ready",
                    "confirmed_blocking_predicate_ids": [],
                    "claim_vocabulary_version": 1,
                    "claim_level": "none",
                    "claim_scope": "",
                    "learning_claim_unlock_review_status": "not_ready",
                    "learning_claim_unlock_review_approved": False,
                    "learning_claim_unlock_review_revocation_status": "not_evaluated",
                    "learning_claim_evidence_bundle_status": "not_evaluated",
                    "telemetry_coverage_ratio": 0.75,
                    "same_eval_run_count": 4,
                    "same_eval_reason_coverage_ratio": 0.0,
                    "strict_secondary_improvement_coverage_ratio": 0.0,
                    "behavior_delta_digest_coverage_ratio": 0.0,
                    "placeholder_count": 0,
                    "evidence_scope_count": 6,
                },
                "learning_claim_guard": {
                    "status": "pass",
                    "reason": "learning claims are not being made in this release snapshot",
                    "required_conditions": [],
                },
                "learning_claim_unlock_review": {
                    "status": "not_ready",
                    "approved": False,
                    "claim_level": "none",
                    "claim_scope": "",
                    "bounded_learning_claim_allowed": False,
                    "confirmed_learning_improvement_allowed": False,
                    "confirmed_learning_improvement_status": "not_ready",
                    "confirmed_blocking_predicate_ids": [],
                    "confirmed_predicate_results": [],
                    "bundle_status": "not_evaluated",
                    "bundle_sha256": "",
                    "current_bundle_sha256": "",
                    "revocation_status": "not_evaluated",
                    "source_path": "",
                    "reason": "test fixture has no learning claim",
                    "required_review_items": [],
                },
                "external_report_placeholder_audit": {
                    "status": "pass",
                    "placeholder_count": 0,
                    "placeholders": [],
                },
            },
        )

    def _write_inputs(self) -> None:
        self._write_closeout_summary_input()
        self._write_artifact_freshness_input()
        self._write_fixed_point_inputs()
        self._write_signoff_revalidation_input()
        self._write_learning_delta_scoreboard_input()

    def test_dashboard_validates_and_labels_checked_in_claims(self) -> None:
        self._write_inputs()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["required_input_fail_count"], 0)
        self.assertEqual(report["summary"]["gate_count"], 6)
        self.assertEqual(report["summary"]["authoritative_gate_count"], 6)
        self.assertEqual(report["summary"]["learning_claim_guard_status"], "pass")
        self.assertFalse(report["summary"]["bounded_learning_claim_allowed"])
        self.assertFalse(report["summary"]["confirmed_learning_improvement_allowed"])
        self.assertEqual(report["summary"]["improvement_claim_status"], "not_ready")
        self.assertEqual(report["summary"]["evidence_cohort_status"], "not_ready")
        self.assertFalse(report["summary"]["claim_wording_allowed"])
        self.assertEqual(report["summary"]["claim_wording_policy_status"], "blocked")
        self.assertEqual(report["summary"]["claim_level"], "none")
        self.assertEqual(
            report["summary"]["self_improvement_claim_model"][
                "highest_supported_stage"
            ],
            "regression_safe",
        )
        self.assertEqual(
            report["summary"]["learning_claim_unlock_review_status"], "not_ready"
        )
        self.assertEqual(
            report["summary"]["learning_claim_evidence_bundle_status"], "not_evaluated"
        )
        self.assertFalse(report["summary"]["confirmed_wording_allowed"])
        self.assertEqual(
            report["summary"]["confirmed_wording_policy_status"], "blocked"
        )
        self.assertEqual(
            report["confirmed_evidence_summary"]["confirmed_evidence_status"],
            "not_ready",
        )
        self.assertEqual(
            report["confirmed_evidence_summary"]["evidence_cohort_status"],
            "not_ready",
        )
        self.assertEqual(
            report["summary"]["confirmed_evidence_summary"],
            report["confirmed_evidence_summary"],
        )
        self.assertEqual(
            report["inputs"]["learning_delta_scoreboard"]["confirmed_evidence_summary"],
            report["confirmed_evidence_summary"],
        )
        self.assertFalse(report["summary"]["learning_claim_unlock_review_approved"])
        self.assertEqual(report["summary"]["same_eval_reason_coverage_status"], "none")
        self.assertEqual(
            report["summary"]["strict_secondary_improvement_coverage_status"], "none"
        )
        self.assertEqual(
            report["summary"]["behavior_delta_digest_coverage_status"], "none"
        )
        self.assertEqual(report["summary"]["accepted_risk_count"], 0)
        self.assertEqual(report["summary"]["gate_attention_count"], 0)
        self.assertNotIn("accepted_risk_gate_attention_count", report["summary"])
        self.assertEqual(
            report["budget_signals"]["release_smoke_boundedness"]["status"], "pass"
        )
        self.assertTrue(
            report["budget_signals"]["release_smoke_boundedness"]["archive_budget_pass"]
        )
        finalizer_cost = report["budget_signals"]["fixed_point_finalizer_cost"]
        self.assertEqual(finalizer_cost["status"], "pass")
        self.assertEqual(finalizer_cost["fixed_point_report_status"], "pass")
        self.assertTrue(finalizer_cost["converged"])
        self.assertEqual(finalizer_cost["total_duration_ms"], 1200)
        self.assertEqual(finalizer_cost["threshold_summary"]["status"], "pass")
        self.assertRegex(
            finalizer_cost["evidence_basis"]["fixed_point_report_digest"],
            r"^[a-f0-9]{64}$",
        )
        self.assertEqual(
            finalizer_cost["evidence_basis"]["current_fixed_point_report_digest"],
            finalizer_cost["evidence_basis"]["fixed_point_report_digest"],
        )
        self.assertEqual(
            finalizer_cost["evidence_basis"]["sampled_fixed_point_report_digest"],
            finalizer_cost["evidence_basis"]["fixed_point_report_digest"],
        )
        self.assertEqual(
            finalizer_cost["evidence_basis"]["basis_relation_to_current_fixed_point"],
            "sampled_current_fixed_point",
        )
        self.assertRegex(
            finalizer_cost["evidence_basis"]["cost_trend_digest"],
            r"^[a-f0-9]{64}$",
        )
        self.assertTrue(
            finalizer_cost["expensive_prerequisites_once"]["skip_policy_effective"]
        )
        self.assertEqual(
            finalizer_cost["expensive_prerequisites_once"][
                "post_first_iteration_run_count"
            ],
            0,
        )
        self.assertEqual(
            report["inputs"]["release_closeout_fixed_point"]["load_status"], "ok"
        )
        self.assertEqual(
            report["inputs"]["release_closeout_fixed_point_cost_trend"]["status"],
            "pass",
        )
        self.assertTrue(
            report["inputs"]["release_closeout_summary"]["machine_release_allowed"]
        )
        self.assertEqual(
            report["inputs"]["release_closeout_summary"]["live_make_check_status"],
            "pass",
        )
        self.assertTrue(
            report["inputs"]["release_closeout_summary"]["live_make_check_ready"]
        )
        self.assertEqual(
            report["inputs"]["learning_delta_scoreboard"]["placeholder_audit_status"],
            "pass",
        )
        self.assertEqual(report["gates"][0]["live_rerun_state"]["status"], "pass")
        self.assertEqual(report["accepted_risk_delta"]["status"], "unchanged")
        labels = {
            claim["provenance_label"]
            for gate in report["gates"]
            for claim in gate["claims"]
        }
        self.assertIn("checked_in_json_confirmed", labels)
        self.assertIn("fingerprint_equivalent_to_checked_in", labels)
        self.assertNotIn("live_rerun_confirmed", labels)
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_explicitly_marks_stale_cost_trend_sample_basis(self) -> None:
        self._write_inputs()
        trend_path = (
            self.vault
            / "ops"
            / "reports"
            / "release-closeout-fixed-point-cost-trend.json"
        )
        trend = json.loads(trend_path.read_text(encoding="utf-8"))
        trend["latest_sample"]["fixed_point_report_digest"] = "b" * 64
        trend_path.write_text(
            json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        basis = report["budget_signals"]["fixed_point_finalizer_cost"]["evidence_basis"]
        self.assertEqual(
            basis["basis_relation_to_current_fixed_point"],
            "sampled_different_fixed_point",
        )
        self.assertEqual(basis["sampled_fixed_point_report_digest"], "b" * 64)
        self.assertNotEqual(
            basis["sampled_fixed_point_report_digest"],
            basis["current_fixed_point_report_digest"],
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_surfaces_expired_advisory_lifecycle_as_operator_attention(self) -> None:
        self._write_inputs()
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout["accepted_risks"] = [
            {
                "source": "external_report_reference_manifest",
                "source_path": "external-reports/report-reference-manifest.json",
                "code": "external_report_strict_unavailable",
                "severity": "warn",
                "gate_effect": "accepted_risk",
                "advisory_lifecycle_effect": "review_backlog",
                "message": "strict external report release check is unavailable",
                "required_evidence": ["run sealed external report release check"],
                "risk_acceptance": {
                    "accepted_by": "release_closeout_policy",
                    "accepted_at": "2026-04-29T09:00:00Z",
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "2026-04-30T08:00:00Z",
                    "acceptance_source": "ops/scripts/release_closeout_summary.py",
                    "revalidation_condition": "rerun sealed external report release check",
                    "rollback_trigger": "treat as blocker in sealed release lanes",
                },
            }
        ]
        closeout_path.write_text(
            json.dumps(closeout, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "advisory_lifecycle_review"
        )
        self.assertEqual(gate["checked_in_state"], "attention")
        self.assertEqual(gate["accepted_risk"]["count"], 1)
        self.assertIn("advisory_backlog_status=expired", gate["live_rerun_state"]["reason"])
        self.assertIn("expired or incomplete", gate["next_action"])
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_attention_when_fixed_point_cost_threshold_breaches(self) -> None:
        self._write_inputs()
        trend_path = (
            self.vault
            / "ops"
            / "reports"
            / "release-closeout-fixed-point-cost-trend.json"
        )
        trend = json.loads(trend_path.read_text(encoding="utf-8"))
        trend["status"] = "attention"
        trend["threshold_summary"] = {
            "status": "attention",
            "breached_writer_count": 1,
            "breached_writers": ["release-evidence-dashboard-report"],
            "summary": "1 fixed-point writer cost threshold breach",
        }
        trend_path.write_text(
            json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        finalizer_cost = report["budget_signals"]["fixed_point_finalizer_cost"]
        self.assertEqual(finalizer_cost["status"], "attention")
        self.assertEqual(
            finalizer_cost["threshold_summary"]["breached_writer_count"], 1
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_fails_when_learning_claim_guard_is_blocked(self) -> None:
        self._write_inputs()
        scoreboard_path = (
            self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        )
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        scoreboard["summary"]["claims_learning_improved"] = True
        scoreboard["summary"]["learning_claim_unlock_review_status"] = "required"
        scoreboard["summary"]["confirmed_blocking_predicate_ids"] = [
            "repeated_same_family_evidence"
        ]
        scoreboard["learning_claim_guard"]["status"] = "blocked"
        scoreboard["learning_claim_guard"]["reason"] = (
            "same-eval reason and digest coverage are incomplete"
        )
        scoreboard["learning_claim_unlock_review"]["status"] = "required"
        scoreboard["learning_claim_unlock_review"]["source_path"] = (
            "ops/reports/learning-claim-unlock-review.json"
        )
        scoreboard["learning_claim_unlock_review"][
            "confirmed_blocking_predicate_ids"
        ] = ["repeated_same_family_evidence"]
        scoreboard["learning_claim_unlock_review"]["confirmed_predicate_results"] = [
            {
                "id": "repeated_same_family_evidence",
                "status": "fail",
                "source_path": "ops/reports/learning-confirmed-evidence-cohort.json",
                "required_condition": "same proposal family valid before/after evidence count >= 3",
                "observed_value": "eligible_family_count=0",
                "summary": "Confirmed learning improvement requires repeated same-family evidence.",
            },
            {
                "id": "public_check_pass",
                "status": "pass",
                "source_path": "ops/reports/public-check-summary.json",
                "required_condition": "public_check_summary.status == pass",
                "observed_value": "status=pass",
                "summary": "Public mirror check must pass before confirmed improvement opens.",
            },
        ]
        scoreboard_path.write_text(
            json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["learning_claim_guard_status"], "blocked")
        self.assertEqual(
            report["summary"]["learning_claim_unlock_review_status"], "required"
        )
        self.assertEqual(
            report["summary"]["confirmed_blocking_predicate_ids"],
            ["repeated_same_family_evidence"],
        )
        self.assertEqual(
            report["inputs"]["learning_delta_scoreboard"][
                "confirmed_blocking_predicate_ids"
            ],
            ["repeated_same_family_evidence"],
        )
        gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "learning_delta_scoreboard_guard"
        )
        self.assertEqual(gate["checked_in_state"], "fail")
        self.assertIn("same-eval reason", gate["live_rerun_state"]["reason"])
        self.assertIn(
            "learning claim unlock review is required", gate["claims"][1]["claim"]
        )
        self.assertIn("repeated_same_family_evidence=fail", gate["claims"][2]["claim"])
        self.assertIn("public_check_pass=pass", gate["claims"][2]["claim"])
        self.assertFalse(report["summary"]["confirmed_wording_allowed"])
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_allows_source_release_attention_when_only_learning_unlock_review_is_missing(
        self,
    ) -> None:
        self._write_inputs()
        scoreboard_path = (
            self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        )
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        scoreboard["summary"].update(
            {
                "claims_learning_improved": True,
                "learning_claim_allowed": False,
                "learning_claim_unlock_review_status": "required",
                "telemetry_coverage_ratio": 1.0,
                "telemetry_coverage_status": "full",
                "same_eval_reason_coverage_ratio": 1.0,
                "same_eval_reason_coverage_status": "full",
                "strict_secondary_improvement_coverage_ratio": 1.0,
                "strict_secondary_improvement_coverage_status": "full",
                "behavior_delta_digest_coverage_ratio": 1.0,
                "behavior_delta_digest_coverage_status": "full",
            }
        )
        scoreboard["learning_claim_guard"]["status"] = "blocked"
        scoreboard["learning_claim_guard"]["reason"] = (
            "learning claim unlock review artifact is required after full evidence coverage"
        )
        scoreboard["learning_claim_unlock_review"]["status"] = "required"
        scoreboard["learning_claim_unlock_review"]["source_path"] = (
            "ops/reports/learning-claim-unlock-review.json"
        )
        scoreboard_path.write_text(
            json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["checked_in_fail_count"], 0)
        self.assertEqual(report["summary"]["live_rerun_fail_count"], 0)
        self.assertEqual(report["summary"]["gate_attention_count"], 1)
        self.assertEqual(report["summary"]["learning_claim_guard_status"], "blocked")
        gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "learning_delta_scoreboard_guard"
        )
        self.assertEqual(gate["checked_in_state"], "attention")
        self.assertEqual(gate["live_rerun_state"]["status"], "attention")
        self.assertIn("source release evidence may proceed", gate["next_action"])
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_surfaces_test_failure_lanes_as_gates(self) -> None:
        self._write_inputs()
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout["test_failure_lanes"][0] = {
            "lane_id": "report_schema_contract",
            "source_path": "ops/reports/test-execution-summary.json",
            "status": "fail",
            "represented_in_summary": True,
            "failed_count": 1,
            "failed_nodeids": [
                "tests/test_report_schema_sample_regeneration.py::ReportSchemaSampleRegenerationTests::test_generated_openvex_sample_matches_frozen_fixture"
            ],
            "summary": "Schema and source-owned report contract tests must pass before release evidence is authoritative.",
            "next_action": "Regenerate schema samples and rerun report-contract summary.",
        }
        closeout_path.write_text(
            json.dumps(closeout, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        lane_gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "test_failure_lane_report_schema_contract"
        )
        self.assertEqual(lane_gate["checked_in_state"], "fail")
        self.assertEqual(lane_gate["live_rerun_state"]["status"], "fail")
        self.assertIn("Regenerate schema samples", lane_gate["next_action"])
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_missing_closeout_input_fails_dashboard(self) -> None:
        self._write_inputs()
        (self.vault / "ops" / "reports" / "release-closeout-summary.json").unlink()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["required_input_fail_count"], 1)
        self.assertEqual(
            report["inputs"]["release_closeout_summary"]["load_status"], "missing"
        )
        self.assertEqual(
            report["inputs"]["release_closeout_summary"]["release_readiness_state"],
            "blocked",
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_accepted_risk_component_is_attention_not_live_failure(self) -> None:
        self._write_inputs()
        current_fingerprint = release_source_tree_fingerprint(self.vault)
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "checked_in_release_ready": True,
                    "live_rerun_release_ready": False,
                    "conditional_release_ready": True,
                    "clean_release_ready": False,
                    "release_readiness_state": "conditional_pass",
                    "machine_release_allowed": False,
                    "operator_release_allowed": True,
                    "requires_accepted_risk_review": True,
                    "components": [
                        {
                            "name": "auto_improve_readiness",
                            "path": "ops/reports/auto-improve-readiness.json",
                            "ready": False,
                            "source_tree_fingerprint": current_fingerprint,
                            "currentness_status": "current",
                        }
                    ],
                    "blockers": [],
                    "accepted_risks": [
                        {
                            "source": "auto_improve_readiness",
                            "code": "learning_blocked_by_review_required",
                            "risk_acceptance": {
                                "risk_owner": "runtime-maintainer",
                                "expires_at": "2026-05-07T00:00:00Z",
                                "revalidation_condition": "rerun closeout before release",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["live_rerun_fail_count"], 0)
        self.assertEqual(report["summary"]["accepted_risk_count"], 1)
        self.assertEqual(report["summary"]["gate_attention_count"], 2)
        self.assertNotIn("accepted_risk_gate_attention_count", report["summary"])
        gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "auto_improve_readiness"
        )
        self.assertEqual(gate["checked_in_state"], "attention")
        self.assertEqual(gate["live_rerun_state"]["status"], "attention")
        labels = {claim["provenance_label"] for claim in gate["claims"]}
        self.assertIn("fingerprint_equivalent_to_checked_in", labels)
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_revalidation_attention_is_gate_attention_not_accepted_risk_count(
        self,
    ) -> None:
        self._write_inputs()
        revalidation_path = (
            self.vault
            / "ops"
            / "reports"
            / "learning-readiness-signoff-revalidation.json"
        )
        revalidation = json.loads(revalidation_path.read_text(encoding="utf-8"))
        revalidation["status"] = "attention"
        revalidation["required_actions"] = [
            {"action": "Refresh learning readiness signoff."}
        ]
        revalidation_path.write_text(
            json.dumps(revalidation, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["accepted_risk_count"], 0)
        self.assertEqual(report["summary"]["gate_attention_count"], 1)
        self.assertNotIn("accepted_risk_gate_attention_count", report["summary"])
        gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "learning_readiness_signoff_revalidation"
        )
        self.assertEqual(gate["checked_in_state"], "attention")
        self.assertEqual(gate["accepted_risk"]["count"], 0)
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_prefers_authoritative_closeout_state_over_component_aggregation(
        self,
    ) -> None:
        self._write_inputs()
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout["status"] = "pass"
        closeout["checked_in_release_ready"] = True
        closeout["live_rerun_release_ready"] = False
        closeout["conditional_release_ready"] = False
        closeout["clean_release_ready"] = False
        closeout["release_readiness_state"] = "unknown"
        closeout["machine_release_allowed"] = False
        closeout["operator_release_allowed"] = False
        closeout["requires_accepted_risk_review"] = False
        closeout_path.write_text(
            json.dumps(closeout, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["inputs"]["release_closeout_summary"]["release_readiness_state"],
            "unknown",
        )
        closeout_gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "release_closeout_decision"
        )
        self.assertEqual(closeout_gate["checked_in_state"], "fail")
        self.assertEqual(closeout_gate["live_rerun_state"]["status"], "fail")
        self.assertFalse(closeout_gate["authoritative_for_release"])
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_closeout_input_prefers_status_v2_axes_over_legacy_booleans(self) -> None:
        self._write_inputs()
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout["release_readiness_state"] = "clean_pass"
        closeout["clean_release_ready"] = True
        closeout["machine_release_allowed"] = True
        closeout["operator_release_allowed"] = False
        closeout["requires_accepted_risk_review"] = False
        closeout["status_v2"] = {
            "schema_version": 2,
            "compatibility_status_value": "pass",
            "status_axes": {
                "release_authority_status": "conditional_pass",
                "semantic_release_status": "conditional_pass",
                "sealed_release_status": "unsealed_distribution_not_provided",
            },
            "blocker_reason_ids": ["machine_release_not_allowed"],
        }
        closeout_path.write_text(
            json.dumps(closeout, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        closeout_input = report["inputs"]["release_closeout_summary"]
        self.assertEqual(closeout_input["release_readiness_state"], "conditional_pass")
        self.assertEqual(closeout_input["release_authority_status"], "conditional_pass")
        self.assertEqual(
            closeout_input["sealed_release_status"],
            "unsealed_distribution_not_provided",
        )
        self.assertEqual(
            closeout_input["status_v2_blocker_reason_ids"],
            ["machine_release_not_allowed"],
        )
        self.assertFalse(closeout_input["machine_release_allowed"])
        self.assertTrue(closeout_input["operator_release_allowed"])
        self.assertTrue(closeout_input["requires_accepted_risk_review"])
        closeout_gate = next(
            gate
            for gate in report["gates"]
            if gate["gate_id"] == "release_closeout_decision"
        )
        self.assertEqual(closeout_gate["checked_in_state"], "attention")
        self.assertFalse(closeout_gate["authoritative_for_release"])
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_fingerprint_mismatch_is_labeled_as_diagnostic_workspace_only(self) -> None:
        self._write_inputs()
        closeout_path = self.vault / "ops" / "reports" / "release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout["components"][0]["source_tree_fingerprint"] = "different-fingerprint"
        closeout_path.write_text(
            json.dumps(closeout, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        gate = next(
            gate for gate in report["gates"] if gate["gate_id"] == "release_smoke"
        )
        self.assertEqual(gate["live_rerun_state"]["status"], "not_run")
        labels = {claim["provenance_label"] for claim in gate["claims"]}
        self.assertIn("diagnostic_workspace_only", labels)
        self.assertNotIn("live_rerun_confirmed", labels)
        self.assertEqual(
            validate_with_schema(report, load_schema(DASHBOARD_SCHEMA_PATH)), []
        )

    def test_dashboard_write_report_validates_schema(self) -> None:
        self._write_inputs()
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(
            self.vault, report, "ops/reports/release-evidence-dashboard.json"
        )

        self.assertEqual(
            destination.resolve(),
            (
                self.vault / "ops" / "reports" / "release-evidence-dashboard.json"
            ).resolve(),
        )
        self.assertTrue(destination.exists())

    def test_main_returns_nonzero_on_fail_without_no_fail(self) -> None:
        self._write_inputs()
        (self.vault / "ops" / "reports" / "release-closeout-summary.json").unlink()

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/release-evidence-dashboard.json",
            ]
        )

        self.assertEqual(exit_code, 1)

    def test_main_returns_zero_on_fail_with_no_fail(self) -> None:
        self._write_inputs()
        (self.vault / "ops" / "reports" / "release-closeout-summary.json").unlink()

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/release-evidence-dashboard.json",
                "--no-fail",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            (
                self.vault / "ops" / "reports" / "release-evidence-dashboard.json"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
