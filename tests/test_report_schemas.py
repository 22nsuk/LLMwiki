from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import ClassVar

import pytest
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.report_contract_test_runtime import (
    ReportPayload,
    ReportPayloadMap,
    ReportSchemaMap,
    load_report_payload_map,
)
from tests.run_mechanism_experiment_test_utils import mutation_proposal_report

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "report_schema_samples.json"
EVAL_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "eval-report.schema.json"
EVAL_COVERAGE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-eval-coverage-report.schema.json"
LINT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "lint-report.schema.json"
WARNING_BUDGET_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "warning-budget-report.schema.json"
STRUCTURAL_COMPLEXITY_BUDGET_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "structural-complexity-budget-report.schema.json"
STAGE2_EVAL_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-stage2-eval-report.schema.json"
MECHANISM_REVIEW_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "mechanism-review-candidates.schema.json"

pytestmark = pytest.mark.report_contract
MUTATION_PROPOSAL_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "mutation-proposals.schema.json"
PROPOSAL_SCOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "proposal-scope.schema.json"
RUN_TELEMETRY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "run-telemetry.schema.json"
GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "generated-artifact-convergence.schema.json"
)
RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "run-artifact-fingerprint.schema.json"
TIMEOUT_FAILURE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "timeout-failure.schema.json"
SHADOW_APPLY_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "shadow-apply-report.schema.json"
ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "rollback-rehearsal-report.schema.json"
BEHAVIOR_DELTA_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "behavior-delta.schema.json"
AUTO_IMPROVE_SESSION_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "auto-improve-session.schema.json"
AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "auto-improve-readiness-report.schema.json"
ARTIFACT_FRESHNESS_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-freshness-report.schema.json"
RUNTIME_EVENT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "runtime-event.schema.json"
PROMOTION_DECISION_TRENDS_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "promotion-decision-trends.schema.json"
ROUTING_PROVENANCE_AGGREGATE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "routing-provenance-aggregate.schema.json"
OUTCOME_METRICS_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "outcome-metrics.schema.json"
SUPPLY_CHAIN_PROVENANCE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "supply-chain-provenance.schema.json"
SUPPLY_CHAIN_GATE_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "supply-chain-gate-report.schema.json"
SBOM_EXPORT_MAPPING_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "sbom-export-mapping.schema.json"
SBOM_READINESS_GATE_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "sbom-readiness-gate-report.schema.json"
CYCLONEDX_16_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "cyclonedx-1.6.schema.json"
OPENVEX_DRAFT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "openvex-draft.schema.json"
REVIEW_ARCHIVE_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "review-archive-report.schema.json"


class ReportSchemaContractTest(unittest.TestCase):
    samples: ClassVar[ReportPayloadMap]
    schemas: ClassVar[ReportSchemaMap]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.samples = load_report_payload_map(FIXTURE_PATH)
        cls.schemas = {
            "eval": load_schema(EVAL_SCHEMA_PATH),
            "eval_coverage": load_schema(EVAL_COVERAGE_SCHEMA_PATH),
            "lint": load_schema(LINT_SCHEMA_PATH),
            "warning_budget": load_schema(WARNING_BUDGET_SCHEMA_PATH),
            "structural_complexity_budget": load_schema(STRUCTURAL_COMPLEXITY_BUDGET_SCHEMA_PATH),
            "stage2": load_schema(STAGE2_EVAL_SCHEMA_PATH),
            "mechanism_review": load_schema(MECHANISM_REVIEW_SCHEMA_PATH),
            "mutation_proposal": load_schema(MUTATION_PROPOSAL_SCHEMA_PATH),
            "proposal_scope": load_schema(PROPOSAL_SCOPE_SCHEMA_PATH),
            "run_telemetry": load_schema(RUN_TELEMETRY_SCHEMA_PATH),
            "generated_artifact_convergence": load_schema(
                GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH
            ),
            "run_artifact_fingerprint": load_schema(RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH),
            "timeout_failure": load_schema(TIMEOUT_FAILURE_SCHEMA_PATH),
            "shadow_apply_report": load_schema(SHADOW_APPLY_REPORT_SCHEMA_PATH),
            "rollback_rehearsal_report": load_schema(ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH),
            "behavior_delta": load_schema(BEHAVIOR_DELTA_SCHEMA_PATH),
            "auto_improve_session": load_schema(AUTO_IMPROVE_SESSION_SCHEMA_PATH),
            "auto_improve_readiness_report": load_schema(AUTO_IMPROVE_READINESS_REPORT_SCHEMA_PATH),
            "artifact_freshness_report": load_schema(ARTIFACT_FRESHNESS_REPORT_SCHEMA_PATH),
            "runtime_event": load_schema(RUNTIME_EVENT_SCHEMA_PATH),
            "promotion_decision_trends": load_schema(PROMOTION_DECISION_TRENDS_SCHEMA_PATH),
            "routing_provenance_aggregate": load_schema(ROUTING_PROVENANCE_AGGREGATE_SCHEMA_PATH),
            "outcome_metrics": load_schema(OUTCOME_METRICS_SCHEMA_PATH),
            "supply_chain_provenance": load_schema(SUPPLY_CHAIN_PROVENANCE_SCHEMA_PATH),
            "supply_chain_gate_report": load_schema(SUPPLY_CHAIN_GATE_REPORT_SCHEMA_PATH),
            "sbom_export_mapping": load_schema(SBOM_EXPORT_MAPPING_SCHEMA_PATH),
            "sbom_readiness_gate_report": load_schema(SBOM_READINESS_GATE_REPORT_SCHEMA_PATH),
            "cyclonedx_bom": load_schema(CYCLONEDX_16_SCHEMA_PATH),
            "openvex_draft": load_schema(OPENVEX_DRAFT_SCHEMA_PATH),
            "review_archive": load_schema(REVIEW_ARCHIVE_REPORT_SCHEMA_PATH),
        }

    def assert_policy_identity_contract(self, report: ReportPayload, schema: ReportPayload) -> None:
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_policy = copy.deepcopy(report)
        missing_policy.pop("policy", None)
        self.assertIn(
            "$: missing required property 'policy'",
            validate_with_schema(missing_policy, schema),
        )

        missing_path = copy.deepcopy(report)
        missing_path["policy"].pop("path", None)
        self.assertIn(
            "$.policy: missing required property 'path'",
            validate_with_schema(missing_path, schema),
        )

        missing_version = copy.deepcopy(report)
        missing_version["policy"].pop("version", None)
        self.assertIn(
            "$.policy: missing required property 'version'",
            validate_with_schema(missing_version, schema),
        )

    def assert_artifact_envelope_contract(self, report: ReportPayload, schema: ReportPayload) -> None:
        missing_artifact_kind = copy.deepcopy(report)
        missing_artifact_kind.pop("artifact_kind", None)
        self.assertIn(
            "$: missing required property 'artifact_kind'",
            validate_with_schema(missing_artifact_kind, schema),
        )

        missing_currentness = copy.deepcopy(report)
        missing_currentness.pop("currentness", None)
        self.assertIn(
            "$: missing required property 'currentness'",
            validate_with_schema(missing_currentness, schema),
        )

    def test_sample_eval_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(self.samples["eval"], self.schemas["eval"])
        self.assert_artifact_envelope_contract(self.samples["eval"], self.schemas["eval"])

    def test_sample_lint_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(self.samples["lint"], self.schemas["lint"])
        self.assert_artifact_envelope_contract(self.samples["lint"], self.schemas["lint"])

    def test_sample_warning_budget_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(
            self.samples["warning_budget"],
            self.schemas["warning_budget"],
        )

        over_budget = copy.deepcopy(self.samples["warning_budget"])
        over_budget["checks"][0]["actual"] = 1
        over_budget["checks"][0]["status"] = "fail"
        over_budget["summary"]["failed_check_count"] = 1
        over_budget["status"] = "fail"
        self.assertEqual(validate_with_schema(over_budget, self.schemas["warning_budget"]), [])

    def test_sample_structural_complexity_budget_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(
            self.samples["structural_complexity_budget"],
            self.schemas["structural_complexity_budget"],
        )
        self.assert_artifact_envelope_contract(
            self.samples["structural_complexity_budget"],
            self.schemas["structural_complexity_budget"],
        )

        missing_profiles = copy.deepcopy(self.samples["structural_complexity_budget"])
        missing_profiles.pop("profiles", None)
        self.assertIn(
            "$: missing required property 'profiles'",
            validate_with_schema(missing_profiles, self.schemas["structural_complexity_budget"]),
        )

        missing_budget_deltas = copy.deepcopy(self.samples["structural_complexity_budget"])
        missing_budget_deltas["targets"][0].pop("budget_deltas", None)
        self.assertIn(
            "$.targets[0]: missing required property 'budget_deltas'",
            validate_with_schema(missing_budget_deltas, self.schemas["structural_complexity_budget"]),
        )

        invalid_function_monitoring_gate = copy.deepcopy(self.samples["structural_complexity_budget"])
        invalid_function_monitoring_gate["diagnostics"]["function_budget_monitoring"]["gate_effect"] = "warn"
        self.assertIn(
            "$.diagnostics.function_budget_monitoring.gate_effect: expected one of ['preview']",
            validate_with_schema(
                invalid_function_monitoring_gate,
                self.schemas["structural_complexity_budget"],
            ),
        )

    def test_sample_eval_coverage_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(
            self.samples["eval_coverage"],
            self.schemas["eval_coverage"],
        )
        self.assert_artifact_envelope_contract(
            self.samples["eval_coverage"],
            self.schemas["eval_coverage"],
        )

    def test_sample_stage2_eval_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(self.samples["stage2"], self.schemas["stage2"])
        self.assert_artifact_envelope_contract(self.samples["stage2"], self.schemas["stage2"])

    def test_sample_mechanism_review_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(
            self.samples["mechanism_review"],
            self.schemas["mechanism_review"],
        )
        self.assert_artifact_envelope_contract(
            self.samples["mechanism_review"],
            self.schemas["mechanism_review"],
        )
        missing_outcome_preview = copy.deepcopy(self.samples["mechanism_review"])
        missing_outcome_preview["diagnostics"].pop("outcome_metrics_calibration", None)
        self.assertIn(
            "$.diagnostics: missing required property 'outcome_metrics_calibration'",
            validate_with_schema(missing_outcome_preview, self.schemas["mechanism_review"]),
        )

    def test_sample_mutation_proposal_report_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(
            self.samples["mutation_proposal"],
            self.schemas["mutation_proposal"],
        )
        self.assert_artifact_envelope_contract(
            self.samples["mutation_proposal"],
            self.schemas["mutation_proposal"],
        )

        populated_report = mutation_proposal_report("ops/scripts/example.py")
        self.assertEqual(validate_with_schema(populated_report, self.schemas["mutation_proposal"]), [])

        missing_blast_radius = copy.deepcopy(populated_report)
        missing_blast_radius["proposals"][0].pop("blast_radius_score", None)
        self.assertIn(
            "$.proposals[0]: missing required property 'blast_radius_score'",
            validate_with_schema(missing_blast_radius, self.schemas["mutation_proposal"]),
        )

        missing_budget_signal = copy.deepcopy(populated_report)
        missing_budget_signal["proposals"][0]["must_change_budget_signal"].pop("signal", None)
        self.assertIn(
            "$.proposals[0].must_change_budget_signal: missing required property 'signal'",
            validate_with_schema(missing_budget_signal, self.schemas["mutation_proposal"]),
        )

    def test_sample_run_telemetry_report_validates_and_requires_core_fields(self) -> None:
        report = self.samples["run_telemetry"]
        schema = self.schemas["run_telemetry"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_run_id = copy.deepcopy(report)
        missing_run_id.pop("run_id", None)
        self.assertIn(
            "$: missing required property 'run_id'",
            validate_with_schema(missing_run_id, schema),
        )

        missing_generated_at = copy.deepcopy(report)
        missing_generated_at.pop("generated_at", None)
        self.assertIn(
            "$: missing required property 'generated_at'",
            validate_with_schema(missing_generated_at, schema),
        )

        invalid_decision = copy.deepcopy(report)
        invalid_decision["decision"] = "UNKNOWN"
        self.assertIn(
            "$.decision: expected one of ['', 'PROMOTE', 'HOLD', 'DISCARD', 'SKIPPED']",
            validate_with_schema(invalid_decision, schema),
        )

    def test_sample_generated_artifact_convergence_report_validates_and_requires_phase(self) -> None:
        report = self.samples["generated_artifact_convergence"]
        schema = self.schemas["generated_artifact_convergence"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_phase = copy.deepcopy(report)
        missing_phase.pop("phase", None)
        self.assertIn(
            "$: missing required property 'phase'",
            validate_with_schema(missing_phase, schema),
        )

    def test_run_telemetry_discard_evidence_requires_path_when_source_is_pathlike(
        self,
    ) -> None:
        report = copy.deepcopy(self.samples["run_telemetry"])
        schema = self.schemas["run_telemetry"]
        report["decision"] = "DISCARD"
        report["discard_non_regression_evidence"] = {
            "promotion_report_source": "inline",
            "candidate_eval_pass": True,
            "eval_score_improves": False,
            "lint_non_regression": True,
            "structural_complexity_non_regression": True,
            "tests_non_regression": True,
            "non_regression_check_statuses": {
                "candidate_eval_pass": "PASS",
                "eval_score_improves": "WARN",
                "lint_non_regression": "PASS",
                "structural_complexity_non_regression": "PASS",
                "tests_non_regression": "PASS",
            },
            "blocking_check_ids": ["equal_score_secondary_eligibility"],
            "decision_record_reason_code": "equal_score_secondary_eligibility",
        }
        self.assertEqual(validate_with_schema(report, schema), [])

        for source in ("path", "default_path"):
            missing_report_path = copy.deepcopy(report)
            missing_report_path["discard_non_regression_evidence"][
                "promotion_report_source"
            ] = source
            self.assertIn(
                "$.discard_non_regression_evidence: missing required property 'promotion_report'",
                validate_with_schema(missing_report_path, schema),
            )

    def test_sample_auto_improve_readiness_report_validates_and_requires_queue_block(self) -> None:
        report = self.samples["auto_improve_readiness_report"]
        schema = self.schemas["auto_improve_readiness_report"]
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assert_artifact_envelope_contract(report, schema)

        missing_queue = copy.deepcopy(report)
        missing_queue.pop("queue", None)
        self.assertIn(
            "$: missing required property 'queue'",
            validate_with_schema(missing_queue, schema),
        )

        missing_execution = copy.deepcopy(report)
        missing_execution.pop("execution_readiness", None)
        self.assertIn(
            "$: missing required property 'execution_readiness'",
            validate_with_schema(missing_execution, schema),
        )

        missing_execution_status = copy.deepcopy(report)
        missing_execution_status.pop("execution_status", None)
        self.assertIn(
            "$: missing required property 'execution_status'",
            validate_with_schema(missing_execution_status, schema),
        )

        missing_promotion_status = copy.deepcopy(report)
        missing_promotion_status.pop("promotion_status", None)
        self.assertIn(
            "$: missing required property 'promotion_status'",
            validate_with_schema(missing_promotion_status, schema),
        )

        missing_diagnostics = copy.deepcopy(report)
        missing_diagnostics.pop("diagnostics", None)
        self.assertIn(
            "$: missing required property 'diagnostics'",
            validate_with_schema(missing_diagnostics, schema),
        )

        missing_learning_telemetry_coverage = copy.deepcopy(report)
        missing_learning_telemetry_coverage["learning_readiness"]["metrics"].pop(
            "telemetry_coverage_ratio",
            None,
        )
        self.assertIn(
            "$.learning_readiness.metrics: missing required property 'telemetry_coverage_ratio'",
            validate_with_schema(missing_learning_telemetry_coverage, schema),
        )

        missing_learning_claim_blockers = copy.deepcopy(report)
        missing_learning_claim_blockers.pop("learning_claim_blockers", None)
        self.assertIn(
            "$: missing required property 'learning_claim_blockers'",
            validate_with_schema(missing_learning_claim_blockers, schema),
        )

        missing_execution_blockers = copy.deepcopy(report)
        missing_execution_blockers.pop("execution_blockers", None)
        self.assertIn(
            "$: missing required property 'execution_blockers'",
            validate_with_schema(missing_execution_blockers, schema),
        )

        missing_promotion_blockers = copy.deepcopy(report)
        missing_promotion_blockers.pop("promotion_blockers", None)
        self.assertIn(
            "$: missing required property 'promotion_blockers'",
            validate_with_schema(missing_promotion_blockers, schema),
        )

        missing_clean_release_blockers = copy.deepcopy(report)
        missing_clean_release_blockers.pop("clean_release_blockers", None)
        self.assertIn(
            "$: missing required property 'clean_release_blockers'",
            validate_with_schema(missing_clean_release_blockers, schema),
        )

        missing_can_execute_trial = copy.deepcopy(report)
        missing_can_execute_trial.pop("can_execute_trial", None)
        self.assertIn(
            "$: missing required property 'can_execute_trial'",
            validate_with_schema(missing_can_execute_trial, schema),
        )

        invalid_learning_claim_blocker_id = copy.deepcopy(report)
        invalid_learning_claim_blocker_id["learning_claim_blockers"][0]["id"] = "learning_uncertain"
        errors = validate_with_schema(invalid_learning_claim_blocker_id, schema)
        self.assertTrue(
            any(
                error.startswith("$.learning_claim_blockers[0].id: expected one of ")
                and "promotion_blocked_by_release_lineage_mismatch" in error
                for error in errors
            ),
            errors,
        )

        missing_remediations = copy.deepcopy(report)
        missing_remediations.pop("remediations", None)
        self.assertIn(
            "$: missing required property 'remediations'",
            validate_with_schema(missing_remediations, schema),
        )

        invalid_status = copy.deepcopy(report)
        invalid_status["fallback"]["status"] = "unknown"
        self.assertIn(
            "$.fallback.status: expected one of ['not_needed', 'blocked_queue', 'seed_recommended', 'history_seeded']",
            validate_with_schema(invalid_status, schema),
        )

        invalid_loop_health_status = copy.deepcopy(report)
        invalid_loop_health_status["diagnostics"]["loop_health_summary"]["status"] = "unknown"
        self.assertIn(
            "$.diagnostics.loop_health_summary.status: expected one of ['missing', 'available']",
            validate_with_schema(invalid_loop_health_status, schema),
        )

        legacy_status = copy.deepcopy(report)
        legacy_status["status"] = "warn"
        self.assertIn(
            "$: unexpected property 'status'",
            validate_with_schema(legacy_status, schema),
        )

        legacy_combined_state = copy.deepcopy(report)
        legacy_combined_state["combined_state"] = {
            "status": "warn",
            "gate_effect": "legacy_execution_only",
            "execution_status": "warn",
            "learning_status": "not_runnable",
            "summary": "legacy",
        }
        self.assertIn(
            "$: unexpected property 'combined_state'",
            validate_with_schema(legacy_combined_state, schema),
        )

        legacy_shadow_gate = copy.deepcopy(report)
        legacy_shadow_gate["diagnostics"]["learnability_shadow_gate"] = {
            "status": "not_runnable",
            "gate_effect": "shadow",
            "can_run": False,
            "likely_to_learn": False,
            "reasons": ["no runnable proposal is available"],
            "can_run_reason": "no runnable proposal is available",
            "likely_to_learn_reason": "no runnable proposal is available",
            "metrics": report["learning_readiness"]["metrics"],
            "signals": report["learning_readiness"]["signals"],
            "recommended_next_step": report["learning_readiness"]["recommended_next_step"],
            "notes": ["legacy alias"],
        }
        self.assertIn(
            "$.diagnostics: unexpected property 'learnability_shadow_gate'",
            validate_with_schema(legacy_shadow_gate, schema),
        )

    def test_sample_artifact_freshness_report_validates_and_rejects_legacy_gate_effects(self) -> None:
        report = self.samples["artifact_freshness_report"]
        schema = self.schemas["artifact_freshness_report"]
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assert_artifact_envelope_contract(report, schema)
        self.assertEqual(report["gate_effect"], "none")

        missing_gate_effect = copy.deepcopy(report)
        missing_gate_effect.pop("gate_effect", None)
        self.assertIn(
            "$: missing required property 'gate_effect'",
            validate_with_schema(missing_gate_effect, schema),
        )

        for legacy_gate_effect in ("active", "review_required", "shadow"):
            invalid = copy.deepcopy(report)
            invalid["gate_effect"] = legacy_gate_effect
            errors = validate_with_schema(invalid, schema)
            self.assertTrue(
                any(error.startswith("$.gate_effect: expected one of ") for error in errors),
                errors,
            )

    def test_sample_runtime_event_validates_and_requires_linking_fields(self) -> None:
        report = self.samples["runtime_event"]
        schema = self.schemas["runtime_event"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_proposal_id = copy.deepcopy(report)
        missing_proposal_id.pop("proposal_id", None)
        self.assertIn(
            "$: missing required property 'proposal_id'",
            validate_with_schema(missing_proposal_id, schema),
        )

    def test_sample_run_artifact_fingerprint_validates_and_requires_hashes(self) -> None:
        report = self.samples["run_artifact_fingerprint"]
        schema = self.schemas["run_artifact_fingerprint"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_sha = copy.deepcopy(report)
        missing_sha["artifacts"][0].pop("sha256", None)
        self.assertIn(
            "$.artifacts[0]: missing required property 'sha256'",
            validate_with_schema(missing_sha, schema),
        )

    def test_sample_timeout_failure_validates_and_requires_timed_out(self) -> None:
        report = self.samples["timeout_failure"]
        schema = self.schemas["timeout_failure"]
        self.assertEqual(validate_with_schema(report, schema), [])

        not_timeout = copy.deepcopy(report)
        not_timeout["result"]["timed_out"] = False
        self.assertIn(
            "$.result.timed_out: expected constant True",
            validate_with_schema(not_timeout, schema),
        )

    def test_sample_shadow_apply_report_validates_and_requires_shadow_mode(self) -> None:
        report = self.samples["shadow_apply_report"]
        schema = self.schemas["shadow_apply_report"]
        self.assertEqual(validate_with_schema(report, schema), [])

        invalid_mode = copy.deepcopy(report)
        invalid_mode["mode"] = "live"
        self.assertIn(
            "$.mode: expected one of ['shadow']",
            validate_with_schema(invalid_mode, schema),
        )

    def test_sample_rollback_rehearsal_report_validates_and_requires_mode(self) -> None:
        report = self.samples["rollback_rehearsal_report"]
        schema = self.schemas["rollback_rehearsal_report"]
        self.assertEqual(validate_with_schema(report, schema), [])

        invalid_mode = copy.deepcopy(report)
        invalid_mode["mode"] = "shadow"
        self.assertIn(
            "$.mode: expected one of ['rollback_rehearsal']",
            validate_with_schema(invalid_mode, schema),
        )

    def test_sample_behavior_delta_validates_and_requires_inputs(self) -> None:
        report = self.samples["behavior_delta"]
        schema = self.schemas["behavior_delta"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_manifest = copy.deepcopy(report)
        missing_manifest["inputs"].pop("changed_files_manifest", None)
        self.assertIn(
            "$.inputs: missing required property 'changed_files_manifest'",
            validate_with_schema(missing_manifest, schema),
        )

    def test_sample_promotion_decision_trends_validates_and_requires_policy_identity(self) -> None:
        self.assert_policy_identity_contract(
            self.samples["promotion_decision_trends"],
            self.schemas["promotion_decision_trends"],
        )

        missing_recent_report = copy.deepcopy(self.samples["promotion_decision_trends"])
        missing_recent_report["recent_runs"][0].pop("promotion_report", None)
        self.assertIn(
            "$.recent_runs[0]: missing required property 'promotion_report'",
            validate_with_schema(missing_recent_report, self.schemas["promotion_decision_trends"]),
        )

    def test_sample_routing_provenance_aggregate_validates_and_requires_artifact_links(self) -> None:
        report = self.samples["routing_provenance_aggregate"]
        schema = self.schemas["routing_provenance_aggregate"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_artifacts = copy.deepcopy(report)
        missing_artifacts["runs"][0].pop("artifacts", None)
        self.assertIn(
            "$.runs[0]: missing required property 'artifacts'",
            validate_with_schema(missing_artifacts, schema),
        )

        missing_audit_rollup = copy.deepcopy(report)
        missing_audit_rollup.pop("audit_rollup", None)
        self.assertIn(
            "$: missing required property 'audit_rollup'",
            validate_with_schema(missing_audit_rollup, schema),
        )

        missing_loop_health = copy.deepcopy(report)
        missing_loop_health["audit_rollup"].pop("loop_health", None)
        self.assertIn(
            "$.audit_rollup: missing required property 'loop_health'",
            validate_with_schema(missing_loop_health, schema),
        )

    def test_sample_outcome_metrics_validates_and_requires_metrics(self) -> None:
        report = self.samples["outcome_metrics"]
        schema = self.schemas["outcome_metrics"]
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assert_artifact_envelope_contract(report, schema)

        missing_metrics = copy.deepcopy(report)
        missing_metrics.pop("metrics", None)
        self.assertIn(
            "$: missing required property 'metrics'",
            validate_with_schema(missing_metrics, schema),
        )

    def test_sample_auto_improve_session_validates_and_requires_outcome_metrics(self) -> None:
        report = self.samples["auto_improve_session"]
        schema = self.schemas["auto_improve_session"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_outcome_metrics = copy.deepcopy(report)
        missing_outcome_metrics["rollups"].pop("outcome_metrics", None)
        self.assertIn(
            "$.rollups: missing required property 'outcome_metrics'",
            validate_with_schema(missing_outcome_metrics, schema),
        )

        missing_learning_summary = copy.deepcopy(report)
        missing_learning_summary.pop("learning_summary", None)
        self.assertIn(
            "$: missing required property 'learning_summary'",
            validate_with_schema(missing_learning_summary, schema),
        )

    def test_sample_supply_chain_provenance_validates_and_requires_inputs(self) -> None:
        report = self.samples["supply_chain_provenance"]
        schema = self.schemas["supply_chain_provenance"]
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assertEqual(
            [item["path"] for item in report["inputs"]],
            ["pyproject.toml", "uv.lock", "requirements.txt", "requirements-dev.txt"],
        )
        self.assertEqual(report["locked_packages"][0]["dependencies"][0]["name"], "typing-extensions")

        missing_inputs = copy.deepcopy(report)
        missing_inputs.pop("inputs", None)
        self.assertIn(
            "$: missing required property 'inputs'",
            validate_with_schema(missing_inputs, schema),
        )

        missing_lock = copy.deepcopy(report)
        missing_lock.pop("lock_evidence", None)
        self.assertIn(
            "$: missing required property 'lock_evidence'",
            validate_with_schema(missing_lock, schema),
        )

    def test_sample_supply_chain_gate_report_validates_and_requires_checks(self) -> None:
        report = self.samples["supply_chain_gate_report"]
        schema = self.schemas["supply_chain_gate_report"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_checks = copy.deepcopy(report)
        missing_checks.pop("checks", None)
        self.assertIn(
            "$: missing required property 'checks'",
            validate_with_schema(missing_checks, schema),
        )

    def test_sample_sbom_export_mapping_validates_and_requires_mapping(self) -> None:
        report = self.samples["sbom_export_mapping"]
        schema = self.schemas["sbom_export_mapping"]
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assertEqual(report["provenance_summary"]["locked_dependency_edge_count"], 1)

        missing_mapping = copy.deepcopy(report)
        missing_mapping.pop("dependency_input_mapping", None)
        self.assertIn(
            "$: missing required property 'dependency_input_mapping'",
            validate_with_schema(missing_mapping, schema),
        )

        invalid_category = copy.deepcopy(report)
        invalid_category["export_mapping"][0]["category"] = "wiki"
        self.assertIn(
            "$.export_mapping[0].category: expected one of ['agent-config', 'ci-workflow', 'dependency-input', 'ops', 'root-metadata', 'tests', 'tools']",
            validate_with_schema(invalid_category, schema),
        )

    def test_sample_sbom_readiness_gate_report_validates_and_requires_checks(self) -> None:
        report = self.samples["sbom_readiness_gate_report"]
        schema = self.schemas["sbom_readiness_gate_report"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_checks = copy.deepcopy(report)
        missing_checks.pop("checks", None)
        self.assertIn(
            "$: missing required property 'checks'",
            validate_with_schema(missing_checks, schema),
        )

    def test_sample_cyclonedx_bom_validates_and_requires_dependency_graph(self) -> None:
        report = self.samples["cyclonedx_bom"]
        schema = self.schemas["cyclonedx_bom"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_dependencies = copy.deepcopy(report)
        missing_dependencies.pop("dependencies", None)
        self.assertIn(
            "$: missing required property 'dependencies'",
            validate_with_schema(missing_dependencies, schema),
        )

    def test_sample_openvex_draft_validates_and_requires_tooling(self) -> None:
        report = self.samples["openvex_draft"]
        schema = self.schemas["openvex_draft"]
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assert_artifact_envelope_contract(report, schema)
        self.assertEqual(report["tooling"]["spdx_emitter_decision"], "shared-artifact-model-spdx-enabled")
        self.assertEqual(report["artifact_context"]["spdx_ref"], "ops/reports/spdx-sbom.json")
        self.assertEqual(report["generated_at"], report["timestamp"])
        self.assertEqual(report["metadata"]["component_count"], len(self.samples["cyclonedx_bom"]["components"]))

        missing_tooling = copy.deepcopy(report)
        missing_tooling.pop("tooling", None)
        self.assertIn(
            "$: missing required property 'tooling'",
            validate_with_schema(missing_tooling, schema),
        )

        missing_artifact_context = copy.deepcopy(report)
        missing_artifact_context.pop("artifact_context", None)
        self.assertIn(
            "$: missing required property 'artifact_context'",
            validate_with_schema(missing_artifact_context, schema),
        )

    def test_sample_review_archive_report_validates_and_requires_archive_metadata(self) -> None:
        report = self.samples["review_archive"]
        schema = self.schemas["review_archive"]
        self.assert_policy_identity_contract(report, schema)
        self.assert_artifact_envelope_contract(report, schema)

        missing_archive_file = copy.deepcopy(report)
        missing_archive_file.pop("archive_file", None)
        self.assertIn(
            "$: missing required property 'archive_file'",
            validate_with_schema(missing_archive_file, schema),
        )

        invalid_exclusion_policy = copy.deepcopy(report)
        invalid_exclusion_policy["exclusion_policy"] = "release_manifest_policy"
        self.assertIn(
            "$.exclusion_policy: expected one of ['public_surface_policy']",
            validate_with_schema(invalid_exclusion_policy, schema),
        )

    def test_sample_proposal_scope_report_validates_and_requires_apply_guardrails(self) -> None:
        report = self.samples["proposal_scope"]
        schema = self.schemas["proposal_scope"]
        self.assertEqual(validate_with_schema(report, schema), [])

        missing_guardrails = copy.deepcopy(report)
        missing_guardrails.pop("apply_guardrails", None)
        self.assertIn(
            "$: missing required property 'apply_guardrails'",
            validate_with_schema(missing_guardrails, schema),
        )

        missing_allowed_roots = copy.deepcopy(report)
        missing_allowed_roots["apply_guardrails"].pop("allowed_apply_roots", None)
        self.assertIn(
            "$.apply_guardrails: missing required property 'allowed_apply_roots'",
            validate_with_schema(missing_allowed_roots, schema),
        )


if __name__ == "__main__":
    unittest.main()
