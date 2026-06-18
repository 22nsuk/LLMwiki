from __future__ import annotations

import json
import unittest

import pytest

from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.release.external_report_lifecycle_runtime import (
    release_lane_mutability_split_status,
)
from tests.external_report_action_matrix_test_runtime import (
    SCHEMA_PATH,
    ExternalReportActionMatrixTestBase,
    _active_action_resolution_summary,
    _reason_detail_summary,
    _sha256_file,
    archive_reconciliation_observation_inventory,
    build_generated_artifact_index_report,
    build_report,
    coverage_action_basis,
    coverage_with_action_basis,
    fixed_context,
    load_schema,
    report_coverage_item,
    strongest_gate_effect,
    validate_with_schema,
    write_generated_artifact_index_report,
    write_report,
)

pytestmark = pytest.mark.public


class ExternalReportActionMatrixLifecycleTests(ExternalReportActionMatrixTestBase):
    def test_release_lane_mutability_split_reads_split_make_surfaces(self) -> None:
        self.assertEqual(release_lane_mutability_split_status(self.vault), "planned")

        release_evidence_mk = self.vault / "mk" / "release-evidence.mk"
        release_evidence_mk.parent.mkdir(parents=True, exist_ok=True)
        release_evidence_mk.write_text(
            "release-evidence-converge: release-evidence-converge-phase-3\n"
            "release-verify-current:\n"
            "\t$(MAKE) release-evidence-dashboard\n"
            "release-sealed-verify:\n"
            "\t$(MAKE) release-sealed-run-ready\n",
            encoding="utf-8",
        )

        self.assertEqual(release_lane_mutability_split_status(self.vault), "implemented")

    def test_gate_effect_strength_order_is_explicit_for_claim_blockers(self) -> None:
        self.assertEqual(
            strongest_gate_effect(["claim_blocker", "operator_review_required"]),
            "operator_review_required",
        )
        self.assertEqual(
            strongest_gate_effect(["operator_review_required", "claim_blocker"]),
            "operator_review_required",
        )
        self.assertEqual(
            strongest_gate_effect(["claim_blocker", "blocks_promotion"]),
            "blocks_promotion",
        )
    def test_reason_detail_summary_orders_mixed_gate_effects_deterministically(self) -> None:
        summary = _reason_detail_summary(
            [
                {
                    "reason_id": "goal_runtime_certificate_not_verified",
                    "owning_stage": "goal_runtime_certificate",
                    "blocking_scope": "unattended_promotion",
                    "gate_effect": "claim_blocker",
                    "recommended_targets": ["goal-runtime-certificate"],
                },
                {
                    "reason_id": "operator_signoff_required",
                    "owning_stage": "operator_review",
                    "blocking_scope": "operator_review",
                    "gate_effect": "operator_review_required",
                    "recommended_targets": ["operator-release-summary"],
                },
            ]
        )

        self.assertEqual(summary["blocking_scopes"], ["operator_review", "unattended_promotion"])
        self.assertEqual(summary["gate_effects"], ["claim_blocker", "operator_review_required"])
        self.assertEqual(summary["strongest_gate_effect"], "operator_review_required")

    def test_active_action_resolution_summary_separates_source_from_authority(self) -> None:
        summary = _active_action_resolution_summary(
            [
                {
                    "action_id": "source_fix",
                    "is_active": True,
                    "verification_readiness_status": "source_action_required",
                },
                {
                    "action_id": "release_evidence",
                    "is_active": True,
                    "verification_readiness_status": "release_run_pending",
                },
                {
                    "action_id": "operator_review",
                    "is_active": True,
                    "verification_readiness_status": "operator_pending",
                },
                {
                    "action_id": "resolved_source_fix",
                    "is_active": False,
                    "verification_readiness_status": "source_action_required",
                },
            ]
        )

        self.assertEqual(summary["status"], "source_action_available")
        self.assertTrue(summary["code_action_available"])
        self.assertEqual(summary["recommended_lane"], "source-action")
        self.assertEqual(summary["recommended_targets"], ["source-action"])
        self.assertEqual(summary["source_action_required_count"], 1)
        self.assertEqual(summary["release_or_operator_pending_count"], 2)
        self.assertEqual(
            summary["active_action_ids_by_verification_readiness_status"],
            {
                "operator_pending": ["operator_review"],
                "release_run_pending": ["release_evidence"],
                "source_action_required": ["source_fix"],
            },
        )

        authority_only = _active_action_resolution_summary(
            [
                {
                    "action_id": "release_evidence",
                    "is_active": True,
                    "verification_readiness_status": "release_run_pending",
                },
                {
                    "action_id": "operator_review",
                    "is_active": True,
                    "verification_readiness_status": "operator_pending",
                },
            ]
        )

        self.assertEqual(
            authority_only["status"],
            "release_or_operator_authority_required",
        )
        self.assertFalse(authority_only["code_action_available"])
        self.assertEqual(authority_only["recommended_lane"], "release-or-operator-authority")
        self.assertEqual(
            authority_only["recommended_targets"],
            ["release-or-operator-authority"],
        )

        artifact_only = _active_action_resolution_summary(
            [
                {
                    "action_id": "artifact_freshness",
                    "is_active": True,
                    "verification_readiness_status": "artifact_freshness_pending",
                    "recommended_target": "freshness-source-identity-converge",
                }
            ]
        )

        self.assertEqual(artifact_only["status"], "artifact_freshness_pending")
        self.assertEqual(
            artifact_only["recommended_lane"],
            "freshness-source-identity-converge",
        )
        self.assertEqual(
            artifact_only["recommended_targets"],
            ["freshness-source-identity-converge"],
        )

        artifact_with_owner_routes = _active_action_resolution_summary(
            [
                {
                    "action_id": "artifact_freshness",
                    "is_active": True,
                    "verification_readiness_status": "artifact_freshness_pending",
                    "recommended_target": "freshness-source-identity-converge",
                    "status_reason_details": [
                        {
                            "reason_id": "artifact_freshness_source_identity_resettle",
                            "recommended_targets": [
                                "freshness-source-identity-converge",
                                "artifact-freshness-refresh-check",
                                "external-report-reference-manifest-settle",
                                "GOAL_RUN_ID=<completed-run-id> make goal-runtime-status-finalize",
                            ],
                        }
                    ],
                }
            ]
        )

        self.assertEqual(
            artifact_with_owner_routes["recommended_targets"],
            [
                "freshness-source-identity-converge",
                "artifact-freshness-refresh-check",
                "external-report-reference-manifest-settle",
                "GOAL_RUN_ID=<completed-run-id> make goal-runtime-status-finalize",
            ],
        )
    def test_schema_rejects_unknown_gate_effects_and_previous_action_shape(self) -> None:
        report = build_report(self.vault, context=fixed_context())
        schema = load_schema(SCHEMA_PATH)
        self.assertEqual(validate_with_schema(report, schema), [])

        invalid_effect = json.loads(json.dumps(report))
        detailed_action = next(
            item for item in invalid_effect["action_items"] if item["status_reason_details"]
        )
        detailed_action["gate_effects"] = ["mystery_gate"]
        detailed_action["strongest_gate_effect"] = "mystery_gate"
        detailed_action["status_reason_details"][0]["gate_effect"] = "mystery_gate"
        errors = validate_with_schema(invalid_effect, schema)
        self.assertTrue(
            any(error.endswith("expected one of ['none', 'advisory', 'claim_blocker', 'operator_review_required', 'blocks_promotion', 'blocks_execution']") for error in errors),
            errors,
        )

        previous_shape = json.loads(json.dumps(report))
        previous_shape["action_items"][0].pop("blocking_scopes", None)
        previous_shape["action_items"][0].pop("gate_effects", None)
        previous_shape["action_items"][0].pop("strongest_gate_effect", None)
        previous_shape["action_items"][0].pop("source_action_status", None)
        previous_shape["action_items"][0].pop("verification_readiness_status", None)
        detailed_previous_action = next(
            item for item in previous_shape["action_items"] if item["status_reason_details"]
        )
        detailed_previous_action["status_reason_details"][0].pop("blocking_scope", None)
        detailed_previous_action["status_reason_details"][0].pop("gate_effect", None)
        previous_errors = validate_with_schema(previous_shape, schema)
        self.assertIn(
            "$.action_items[0]: missing required property 'blocking_scopes'",
            previous_errors,
        )
        self.assertIn(
            "$.action_items[0]: missing required property 'source_action_status'",
            previous_errors,
        )
        self.assertIn(
            "$.action_items[0]: missing required property 'verification_readiness_status'",
            previous_errors,
        )
        self.assertIn(
            "$.action_items[0]: missing required property 'gate_effects'",
            previous_errors,
        )
        self.assertIn(
            "$.action_items[0]: missing required property 'strongest_gate_effect'",
            previous_errors,
        )
        self.assertTrue(
            any(error.endswith("missing required property 'blocking_scope'") for error in previous_errors),
            previous_errors,
        )
        self.assertTrue(
            any(error.endswith("missing required property 'gate_effect'") for error in previous_errors),
            previous_errors,
        )
    def test_matrix_covers_non_archived_reports_and_validates_schema(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nP0: script-output-surfaces, workflow_dependency_planner, "
            "source package, evidence bundle, full-suite, promotion_blockers, active reference set, "
            "release-evidence-converge, release-verify-current, release-sealed-verify, "
            "pre_distribution_package_binding_status, source_closeout_distribution_binding_status, "
            "marker-wide explicit selector parity, test-release-sealing-core, test-report-contract-core.\n",
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
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
            ),
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["summary"]["active_report_count"], 2)
        self.assertEqual(report["summary"]["archived_report_count"], 1)
        self.assertEqual(report["summary"]["reference_manifest_alignment_status"], "drift")
        self.assertEqual(report["summary"]["reference_manifest_missing_active_report_count"], 2)
        self.assertEqual(
            report["summary"]["canonical_artifact_freshness_state"],
            self._artifact_freshness_state(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
            ),
        )
        self.assertEqual(
            report["reference_manifest_alignment"]["missing_active_report_paths"],
            ["external-reports/maintenance.md", "external-reports/release.md"],
        )
        self.assertEqual(report["summary"]["unmatched_active_report_count"], 0)
        paths = {item["path"] for item in report["active_report_coverage"]}
        self.assertIn("external-reports/release.md", paths)
        self.assertIn("external-reports/maintenance.md", paths)
        self.assertNotIn("external-reports/report-reference-manifest.json", paths)
        self.assertFalse(any("/archive/" in path for path in paths))
        archived_basis = {
            item["path"]: item for item in report["archived_report_action_basis"]
        }
        self.assertEqual(set(archived_basis), {"external-reports/archive/old.md"})
        old_basis = archived_basis["external-reports/archive/old.md"]
        self.assertEqual(
            old_basis["content_sha256"],
            _sha256_file(self.external / "archive" / "old.md"),
        )
        self.assertIn(
            "script_output_surfaces_currentness",
            old_basis["matched_action_ids"],
        )
        self.assertEqual(
            old_basis["matched_action_count"],
            len(old_basis["matched_action_ids"]),
        )
        self.assertEqual(old_basis["unmatched_recommendation_count"], 0)
        self.assertNotIn("reason", old_basis)
        self.assertNotIn("coverage_markers", old_basis)
        coverage = {item["path"]: item for item in report["active_report_coverage"]}
        release_coverage = coverage["external-reports/release.md"]
        self.assertEqual(
            release_coverage["content_sha256"],
            _sha256_file(self.external / "release.md"),
        )
        self.assertEqual(
            release_coverage["unresolved_action_count"],
            len(release_coverage["unresolved_action_ids"]),
        )
        self.assertIn(
            "source_package_distribution_binding",
            release_coverage["unresolved_action_ids"],
        )
        self.assertEqual(release_coverage["unmatched_recommendation_count"], 0)
        self.assertEqual(
            release_coverage["archive_decision_code"],
            "unresolved_actions_keep_report_active",
        )
        raw_release_coverage = report_coverage_item(self.vault, self.external / "release.md")
        self.assertNotIn("unresolved_action_ids", raw_release_coverage)
        self.assertNotIn("unresolved_action_count", raw_release_coverage)
        actions = {item["action_id"]: item for item in report["action_items"]}
        status_by_action = {
            action["action_id"]: action["current_status"]
            for action in report["action_items"]
        }
        action_basis = coverage_action_basis(raw_release_coverage, status_by_action)
        self.assertEqual(
            action_basis["unresolved_action_ids"],
            release_coverage["unresolved_action_ids"],
        )
        self.assertEqual(
            action_basis["unresolved_action_count"],
            release_coverage["unresolved_action_count"],
        )
        self.assertEqual(
            coverage_with_action_basis([raw_release_coverage], status_by_action)[0],
            release_coverage,
        )
        self.assertEqual(actions["release_writer_dependency_single_source"]["current_status"], "implemented")
        self.assertEqual(actions["outcome_provenance_gate_policy"]["current_status"], "implemented")
        self.assertEqual(actions["external_report_lifecycle"]["current_status"], "partially_automated")
        self.assertEqual(actions["active_report_manifest_freshness"]["current_status"], "partially_automated")
        self.assertEqual(actions["release_lane_mutability_split"]["current_status"], "planned")
        self.assertEqual(actions["sealed_summary_vocabulary_demotion"]["current_status"], "implemented")
        self.assertEqual(actions["selector_marker_scope_parity"]["current_status"], "planned")
        for action_id in (
            "active_report_manifest_freshness",
            "release_lane_mutability_split",
            "sealed_summary_vocabulary_demotion",
            "selector_marker_scope_parity",
        ):
            self.assertIn("external-reports/release.md", actions[action_id]["source_report_paths"])
        release_lane_evidence_paths = {
            item["path"] for item in actions["release_lane_mutability_split"]["evidence"]
        }
        self.assertIn("mk/release-evidence.mk", release_lane_evidence_paths)
        self.assertIn("mk/release-authority.mk", release_lane_evidence_paths)
        self.assertIn("mk/release-learning.mk", release_lane_evidence_paths)
        self.assertIn(
            "external-reports/release.md",
            actions["script_output_surfaces_currentness"]["source_report_paths"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

    def test_matrix_summary_surfaces_artifact_freshness_stale_routing(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nexternal report lifecycle.\n",
            encoding="utf-8",
        )
        stale_routing = {
            "classification": "source_identity_only",
            "recommended_lane": "freshness-source-identity-converge",
            "recommended_targets": ["freshness-source-identity-converge"],
            "reason_ids": ["source_identity_only_stale"],
            "summary": (
                "3 stale artifact(s) only differ by source revision or source-tree "
                "fingerprint; use the source-identity convergence lane first."
            ),
        }
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=3,
                operational_attention_artifact_count=3,
                status="attention",
                stale_routing=stale_routing,
            ),
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["summary"]["canonical_artifact_freshness_state"],
            self._artifact_freshness_state(
                artifact_count=12,
                stale_artifact_count=3,
                operational_attention_artifact_count=3,
                stale_routing=stale_routing,
            ),
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_matrix_passes_when_reference_manifest_matches_active_reports(self) -> None:
        self._write_json(
            "ops/reports/external-report-action-matrix.json",
            {"status": "fail", "producer": "stale.previous.run"},
        )
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
        self_evidence = next(
            item
            for item in actions["external_report_lifecycle"]["evidence"]
            if item["path"] == "ops/reports/external-report-action-matrix.json"
        )
        self.assertEqual(self_evidence["status"], report["status"])
        self.assertEqual(self_evidence["producer"], "ops.scripts.external_report_action_matrix")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
    def test_reference_manifest_drift_is_not_masked_by_reused_report_contract_summary(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nexternal report lifecycle.\n",
            encoding="utf-8",
        )
        (self.external / "new-active.md").write_text(
            "# Follow-up Review\n\nexternal report lifecycle.\n",
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
        self._write_json(
            "ops/reports/test-execution-summary.json",
            {
                "artifact_kind": "test_execution_summary",
                "producer": "ops.scripts.test_execution_summary",
                "status": "pass",
                "source_revision": "source_package_without_git",
                "source_tree_fingerprint": release_source_tree_fingerprint(self.vault),
                "currentness": {"status": "current"},
                "suite": "report-contract",
            },
        )

        stale_manifest_report = build_report(self.vault, context=fixed_context())

        self.assertEqual(stale_manifest_report["status"], "attention")
        self.assertEqual(
            stale_manifest_report["summary"]["reference_manifest_alignment_status"],
            "drift",
        )
        self.assertEqual(
            stale_manifest_report["summary"][
                "reference_manifest_missing_active_report_count"
            ],
            1,
        )
        self.assertEqual(
            stale_manifest_report["reference_manifest_alignment"][
                "missing_active_report_paths"
            ],
            ["external-reports/new-active.md"],
        )
        self.assertIn(
            "external_report_reference_manifest",
            stale_manifest_report["input_fingerprints"],
        )

        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [
                    {"path": "external-reports/new-active.md"},
                    {"path": "external-reports/release.md"},
                ],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        current_manifest_report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            current_manifest_report["summary"]["reference_manifest_alignment_status"],
            "current",
        )
        self.assertEqual(
            current_manifest_report["summary"][
                "reference_manifest_missing_active_report_count"
            ],
            0,
        )
        self.assertNotEqual(
            stale_manifest_report["input_fingerprints"][
                "external_report_reference_manifest"
            ],
            current_manifest_report["input_fingerprints"][
                "external_report_reference_manifest"
            ],
        )
        self.assertEqual(
            current_manifest_report["input_fingerprints"]["active_external_reports"],
            stale_manifest_report["input_fingerprints"]["active_external_reports"],
        )
        self.assertEqual(validate_with_schema(current_manifest_report, load_schema(SCHEMA_PATH)), [])
    def test_open_archive_reconciliation_observations_keep_absorption_actions_active(self) -> None:
        self._write_static_github_security_surfaces()
        for rel_path, text in {
            "ops/schemas/release-authority-inventory.schema.json": "{}\n",
            "ops/scripts/release/release_authority_inventory.py": "def main(): pass\n",
            "tests/test_release_authority_inventory.py": "def test_inventory(): pass\n",
            "docs/repository-surfaces.md": (
                "# Repository Surfaces\n\n"
                "Full local vault, Public mirror, and Release source ZIP.\n"
                "ops/scripts/public/public_surface_policy.py, make public-export, "
                "make release-run-ready, build/release/, AGENTS.local.md.\n"
            ),
            "docs/README.md": "See repository-surfaces.md.\n",
            "README.md": "See docs/repository-surfaces.md.\n",
            "ARCHITECTURE.md": "See docs/repository-surfaces.md.\n",
            "docs/public-mirror.md": "See docs/repository-surfaces.md.\n",
            "docs/release.md": "See docs/repository-surfaces.md.\n",
            "tests/test_doc_graph_integrity.py": "def test_doc_graph_integrity(): pass\n",
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.external / "review.md").write_text(
            "# Review\n\nexternal report lifecycle active report set function-budget "
            "GitHub governance supply chain source package Windows path currentness.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/review.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
            ),
        )
        self._write_task_observations(
            [
                {
                    "observation_id": "archived_report_action_trace_gap",
                    "status": "planned",
                },
                {
                    "observation_id": "broad_action_completion_threshold_gap",
                    "status": "open",
                },
                {
                    "observation_id": "status_surface_currentness_visibility_gap",
                    "status": "planned",
                },
            ]
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(actions["external_report_lifecycle"]["current_status"], "partially_automated")
        self.assertIn(
            "archived_report_action_trace_gap",
            actions["external_report_lifecycle"]["status_reason_ids"],
        )
        self.assertEqual(
            actions["active_report_manifest_freshness"]["current_status"],
            "partially_automated",
        )
        self.assertIn(
            "archived_report_action_trace_gap",
            actions["active_report_manifest_freshness"]["status_reason_ids"],
        )
        self.assertNotIn(
            "archived_report_action_trace_gap",
            actions["generated_artifact_tracking_policy"]["status_reason_ids"],
        )
        for action_id in (
            "function_budget_proposal_adapter",
            "release_authority_inventory",
            "github_native_security_automation",
            "repository_surface_entrypoint_documentation",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented", action_id)
            self.assertEqual(actions[action_id]["status_reason_ids"], [], action_id)
            self.assertNotIn("action_matrix", actions[action_id]["blocking_scopes"], action_id)
        for action in report["action_items"]:
            self.assertNotIn(
                "broad_action_completion_threshold_gap",
                action["status_reason_ids"],
                action["action_id"],
            )
            if action["current_status"] != "implemented":
                self.assertTrue(action["status_reason_ids"], action["action_id"])
        self.assertIn(
            "status_surface_currentness_visibility_gap",
            actions["artifact_freshness_performance_observability"]["status_reason_ids"],
        )
        detail_by_reason = {
            detail["reason_id"]: detail["blocking_scope"]
            for detail in actions["external_report_lifecycle"]["status_reason_details"]
        }
        self.assertEqual(detail_by_reason["archived_report_action_trace_gap"], "external_report_lifecycle")
        self.assertIn("archive_reconciliation_observations", report["input_fingerprints"])
        self.assertGreaterEqual(report["summary"]["partially_automated_count"], 3)
        self.assertGreaterEqual(report["summary"]["currently_valid_action_count"], 3)
    def test_archive_reconciliation_observation_status_changes_fingerprint_and_status(self) -> None:
        (self.external / "review.md").write_text(
            "# Review\n\nexternal report lifecycle active report set.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/review.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )
        (self.external / "archive" / "legacy-review.md").write_text(
            "# Legacy Review\n\nexternal report lifecycle active report set.\n",
            encoding="utf-8",
        )
        self._write_task_observations(
            [{"observation_id": "archived_report_action_trace_gap", "status": "planned"}]
        )

        open_report = build_report(self.vault, context=fixed_context())

        open_action = {
            item["action_id"]: item for item in open_report["action_items"]
        }["external_report_lifecycle"]
        self.assertEqual(open_action["current_status"], "partially_automated")
        self.assertIn("archive_reconciliation_observations", open_report["input_fingerprints"])
        self.assertIn(
            "archive_reconciliation_observation_paths",
            open_report["input_fingerprints"],
        )

        self._write_task_observations(
            [{"observation_id": "archived_report_action_trace_gap", "status": "automated"}]
        )
        missing_evidence_report = build_report(self.vault, context=fixed_context())

        missing_evidence_action = {
            item["action_id"]: item for item in missing_evidence_report["action_items"]
        }["external_report_lifecycle"]
        self.assertEqual(missing_evidence_action["current_status"], "partially_automated")
        self.assertIn(
            "archived_report_action_trace_gap",
            missing_evidence_action["status_reason_ids"],
        )
        missing_evidence_records = archive_reconciliation_observation_inventory(self.vault)
        self.assertEqual(
            missing_evidence_records[0]["status"],
            "automated_missing_resolution_evidence",
        )

        open_fingerprints = open_report["input_fingerprints"]
        missing_evidence_fingerprints = missing_evidence_report["input_fingerprints"]
        self.assertNotEqual(
            open_fingerprints["archive_reconciliation_observations"],
            missing_evidence_fingerprints["archive_reconciliation_observations"],
        )
        self._write_task_observations(
            [
                {
                    "observation_id": "archived_report_action_trace_gap",
                    "status": "automated",
                    "resolution_evidence": [
                        "source:ops/scripts/release/external_report_lifecycle_runtime.py",
                        "test:tests/test_external_report_action_matrix.py",
                    ],
                }
            ]
        )
        prefixed_evidence_without_archived_basis = build_report(
            self.vault,
            context=fixed_context(),
        )

        unverified_action = {
            item["action_id"]: item
            for item in prefixed_evidence_without_archived_basis["action_items"]
        }["external_report_lifecycle"]
        self.assertEqual(unverified_action["current_status"], "partially_automated")
        self.assertIn(
            "archived_report_action_trace_gap",
            unverified_action["status_reason_ids"],
        )
        unverified_records = archive_reconciliation_observation_inventory(self.vault)
        self.assertEqual(
            unverified_records[0]["status"],
            "automated_missing_resolution_evidence",
        )

        generated_index = build_generated_artifact_index_report(
            self.vault,
            context=fixed_context(),
        )
        self.assertEqual(
            {
                item["path"]
                for item in generated_index["archived_external_report_basis"]
            },
            {"external-reports/archive/legacy-review.md"},
        )
        write_generated_artifact_index_report(self.vault, generated_index)
        closed_report = build_report(self.vault, context=fixed_context())

        closed_action = {
            item["action_id"]: item for item in closed_report["action_items"]
        }["external_report_lifecycle"]
        self.assertEqual(closed_action["current_status"], "implemented")
        self.assertNotIn("archived_report_action_trace_gap", closed_action["status_reason_ids"])
        self.assertNotEqual(
            missing_evidence_report["input_fingerprints"]["archive_reconciliation_observations"],
            closed_report["input_fingerprints"]["archive_reconciliation_observations"],
        )
        self.assertNotEqual(
            missing_evidence_report["input_fingerprints"]["archive_reconciliation_observation_paths"],
            closed_report["input_fingerprints"]["archive_reconciliation_observation_paths"],
        )
        closed_basis = {
            item["path"]: item for item in closed_report["archived_report_action_basis"]
        }
        self.assertEqual(set(closed_basis), {"external-reports/archive/legacy-review.md"})
        self.assertEqual(
            closed_basis["external-reports/archive/legacy-review.md"][
                "matched_action_count"
            ],
            len(
                closed_basis["external-reports/archive/legacy-review.md"][
                    "matched_action_ids"
                ]
            ),
        )
    def test_status_and_dev_install_observations_close_with_resolution_evidence(self) -> None:
        (self.external / "status-dev.md").write_text(
            "# Status and dependency setup\n\n"
            "uv lock --check canonical dependency policy, make help operator entrypoint index, "
            "artifact freshness validator cache progress jsonl per-phase timing, "
            "selected contract currentness.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/status-dev.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
            ),
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
        self._write_task_observations(
            [
                {
                    "observation_id": "status_surface_currentness_visibility_gap",
                    "status": "automated",
                    "resolution_evidence": [
                        "source:ops/scripts/release/release_status_surface.py",
                        "test:tests/test_release_status_surface.py",
                    ],
                },
                {
                    "observation_id": "dev_install_index_portability_gap",
                    "status": "automated",
                    "resolution_evidence": [
                        "source:mk/core.mk",
                        "test:tests/test_makefile_static_gates.py",
                    ],
                },
            ]
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        reason_expectations = {
            "uv_lock_canonical_policy": "dev_install_index_portability_gap",
            "operator_entrypoint_index": "dev_install_index_portability_gap",
            "selected_contract_currentness_gate": "status_surface_currentness_visibility_gap",
            "artifact_freshness_performance_observability": (
                "status_surface_currentness_visibility_gap"
            ),
        }
        for action_id, reason_id in reason_expectations.items():
            with self.subTest(action_id=action_id):
                self.assertNotIn(reason_id, actions[action_id]["status_reason_ids"])

    def _write_github_governance_live_drift_fixture(self) -> None:
        self._write_static_github_security_surfaces()
        for rel_path, text in {
            ".github/CODEOWNERS": "* @maintainers\n",
            ".github/pull_request_template.md": (
                "## Review\n- [ ] Reviewer confirms validation and boundary impact.\n"
            ),
            "CONTRIBUTING.md": (
                "# Contributing\n\n"
                "## Commit governance\n"
                "Contributors must describe commit taxonomy and governance impact.\n"
            ),
            ".github/release-governance.yml": "required_checks:\n  - test\n",
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._write_json(
            "ops/reports/github-governance-live-drift.json",
            {
                "artifact_kind": "github_governance_live_drift_verification",
                "status": "attention",
            },
        )

    def _assert_observation_gap_open(
        self,
        actions: dict[str, dict],
        *,
        action_id: str,
        reason_id: str,
    ) -> None:
        self.assertEqual(actions[action_id]["current_status"], "partially_automated")
        self.assertIn(reason_id, actions[action_id]["status_reason_ids"])

    def _assert_static_github_actions_ignore_live_gap(
        self,
        actions: dict[str, dict],
    ) -> None:
        for static_action_id in (
            "collaboration_governance_surface",
            "github_native_security_automation",
        ):
            self.assertEqual(
                actions[static_action_id]["current_status"],
                "implemented",
                static_action_id,
            )
            self.assertNotIn(
                "github_governance_live_drift_gap",
                actions[static_action_id]["status_reason_ids"],
            )

    def _assert_github_live_gap_requires_operator_evidence(
        self,
        actions: dict[str, dict],
    ) -> None:
        live_action = actions["github_governance_live_drift_verification"]
        live_detail = {
            item["reason_id"]: item for item in live_action["status_reason_details"]
        }["github_governance_live_drift_gap"]
        self.assertEqual(live_detail["owning_stage"], "github_live_governance_verification")
        self.assertEqual(live_detail["blocking_scope"], "github_live_governance")
        self.assertEqual(live_detail["gate_effect"], "operator_review_required")
        self.assertEqual(live_action["verification_readiness_status"], "operator_pending")

    def _assert_review_bundle_gap_requires_clean_report(
        self,
        actions: dict[str, dict],
    ) -> None:
        review_detail = {
            item["reason_id"]: item
            for item in actions["source_package_distribution_binding"]["status_reason_details"]
        }["review_bundle_full_vault_hygiene_gap"]
        self.assertEqual(review_detail["owning_stage"], "review_bundle_hygiene")
        self.assertEqual(review_detail["blocking_scope"], "review_archive")
        self.assertEqual(
            review_detail["recommended_targets"],
            ["review-archive", "external-report-action-matrix"],
        )

    def test_operator_observations_need_resolution_evidence_to_close(self) -> None:
        self._write_github_governance_live_drift_fixture()
        self._write_release_verification_reports()
        self._write_task_observations(
            [
                {
                    "observation_id": "review_bundle_full_vault_hygiene_gap",
                    "status": "automated",
                },
                {
                    "observation_id": "github_governance_live_drift_gap",
                    "status": "automated",
                },
            ]
        )

        missing_evidence_report = build_report(self.vault, context=fixed_context())

        missing_evidence_actions = self._actions_by_id(missing_evidence_report)
        for action_id, reason_id in {
            "source_package_distribution_binding": "review_bundle_full_vault_hygiene_gap",
            "github_governance_live_drift_verification": "github_governance_live_drift_gap",
        }.items():
            self._assert_observation_gap_open(
                missing_evidence_actions,
                action_id=action_id,
                reason_id=reason_id,
            )
        self._assert_static_github_actions_ignore_live_gap(missing_evidence_actions)
        self._assert_github_live_gap_requires_operator_evidence(missing_evidence_actions)
        self._assert_review_bundle_gap_requires_clean_report(missing_evidence_actions)

        self._write_task_observations(
            [
                {
                    "observation_id": "review_bundle_full_vault_hygiene_gap",
                    "status": "automated",
                    "resolution_evidence": [
                        "source:ops/scripts/release/external_report_lifecycle_runtime.py",
                        "test:tests/test_external_report_action_matrix.py",
                    ],
                },
                {
                    "observation_id": "github_governance_live_drift_gap",
                    "status": "automated",
                    "resolution_evidence": [
                        "source:docs/release.md",
                        "test:tests/test_external_report_action_matrix.py",
                    ],
                },
            ]
        )

        prefixed_evidence_without_clean_review_report = build_report(
            self.vault, context=fixed_context()
        )

        unverified_actions = self._actions_by_id(
            prefixed_evidence_without_clean_review_report
        )
        self._assert_observation_gap_open(
            unverified_actions,
            action_id="source_package_distribution_binding",
            reason_id="review_bundle_full_vault_hygiene_gap",
        )

        self._write_schema_invalid_clean_review_archive_report()

        invalid_schema_report = build_report(self.vault, context=fixed_context())

        invalid_schema_actions = self._actions_by_id(invalid_schema_report)
        self._assert_observation_gap_open(
            invalid_schema_actions,
            action_id="source_package_distribution_binding",
            reason_id="review_bundle_full_vault_hygiene_gap",
        )

        self._write_clean_review_archive_report()

        closed_report = build_report(self.vault, context=fixed_context())

        closed_actions = self._actions_by_id(closed_report)
        self.assertEqual(
            closed_actions["source_package_distribution_binding"]["current_status"],
            "implemented",
        )
        self.assertNotIn(
            "review_bundle_full_vault_hygiene_gap",
            closed_actions["source_package_distribution_binding"]["status_reason_ids"],
        )
        self._assert_static_github_actions_ignore_live_gap(closed_actions)
        self.assertEqual(
            closed_actions["github_governance_live_drift_verification"]["current_status"],
            "partially_automated",
        )
        self.assertNotIn(
            "github_governance_live_drift_gap",
            closed_actions["github_governance_live_drift_verification"]["status_reason_ids"],
        )
        self.assertIn(
            "github_live_governance_operator_evidence_not_pass",
            closed_actions["github_governance_live_drift_verification"]["status_reason_ids"],
        )
    def test_source_package_binding_requires_reference_manifest_distribution_binding(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {"summary": {"active_reference_set_status": "current"}},
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        action = {
            item["action_id"]: item for item in report["action_items"]
        }["source_package_distribution_binding"]
        self.assertEqual(action["current_status"], "requires_release_run_verification")
        self.assertIn("external_report_current_distribution_zip_missing", action["status_reason_ids"])
        self.assertIn("external_report_basis_zip_not_bound", action["status_reason_ids"])
    def test_binary_active_report_is_operator_only_action_not_unmatched(self) -> None:
        (self.external / "review.pdf").write_bytes(b"%PDF-1.4\n")
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/review.pdf"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["summary"]["active_report_count"], 1)
        self.assertEqual(report["summary"]["unmatched_active_report_count"], 0)
        coverage = report["active_report_coverage"][0]
        self.assertEqual(coverage["report_type"], "binary_report")
        self.assertEqual(
            coverage["content_sha256"],
            _sha256_file(self.external / "review.pdf"),
        )
        self.assertEqual(
            coverage["matched_action_ids"],
            ["operator_only_external_report_binary"],
        )
        self.assertEqual(coverage["unmatched_recommendation_count"], 0)
        self.assertEqual(coverage["unresolved_action_ids"], ["operator_only_external_report_binary"])
        self.assertEqual(coverage["unresolved_action_count"], 1)
        self.assertEqual(
            coverage["operator_only_rationale"],
            "binary_report_requires_operator_review",
        )
        self.assertEqual(
            coverage["archive_decision_code"],
            "binary_report_requires_operator_review",
        )
        actions = {item["action_id"]: item for item in report["action_items"]}
        binary_action = actions["operator_only_external_report_binary"]
        self.assertEqual(binary_action["current_status"], "planned")
        self.assertIn("external-reports/review.pdf", binary_action["source_report_paths"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
    def test_roadmap_surfaces_are_cataloged_individually(self) -> None:
        for rel_path in (
            "ops/scripts/core/public_mirror_boundary_runtime.py",
            "tests/test_public_mirror_boundary_runtime.py",
            "ops/schemas/strict-lint-inventory.schema.json",
            "ops/scripts/eval/lint_uplift_plan.py",
            "tests/test_lint_uplift_plan.py",
            "ops/schemas/strict-type-inventory.schema.json",
            "ops/scripts/eval/type_uplift_plan.py",
            "tests/test_type_uplift_plan.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        (self.vault / "mk" / "eval.mk").parent.mkdir(parents=True, exist_ok=True)
        (self.vault / "mk" / "eval.mk").write_text(
            "lint-uplift-plan:\n\tpython -m ops.scripts.lint_uplift_plan\n"
            "type-uplift-plan:\n\tpython -m ops.scripts.type_uplift_plan\n",
            encoding="utf-8",
        )
        (self.external / "roadmap.md").write_text(
            "# Roadmap\n\n"
            "public_mirror_boundary_runtime, Lint uplift plan, Type uplift plan, "
            "Mechanism navigation index, CLI surface inventory, Tools migration plan, "
            "Release authority inventory, Observation closeout lint, Subagent profile schema, "
            "CI tier lane bridge, Compatibility alias deprecation, Public surface snapshot, "
            "Doc graph integrity.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/roadmap.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        coverage = {item["path"]: item for item in report["active_report_coverage"]}
        matched = set(coverage["external-reports/roadmap.md"]["matched_action_ids"])
        expected = {
            "public_mirror_boundary_helper",
            "lint_uplift_plan_full_scope",
            "type_uplift_plan_full_scope",
            "mechanism_navigation_index",
            "cli_surface_inventory",
            "tools_migration_plan",
            "release_authority_inventory",
            "observation_closeout_lint",
            "subagent_profile_schema",
            "ci_tier_lane_bridge",
            "compatibility_alias_deprecation",
            "public_surface_snapshot",
            "doc_graph_integrity_lint",
        }
        self.assertTrue(expected <= matched)
        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(actions["public_mirror_boundary_helper"]["current_status"], "implemented")
        self.assertEqual(actions["lint_uplift_plan_full_scope"]["current_status"], "implemented")
        self.assertEqual(actions["type_uplift_plan_full_scope"]["current_status"], "implemented")
        self.assertEqual(actions["mechanism_navigation_index"]["current_status"], "planned")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
    def test_p2_repository_surface_and_service_layer_actions_are_tracked(self) -> None:
        for rel_path, text in {
            "docs/repository-surfaces.md": (
                "Full local vault, Public mirror, Release source ZIP, "
                "ops/scripts/public/public_surface_policy.py, make public-export, "
                "make release-run-ready, build/release/, AGENTS.local.md.\n"
            ),
            "docs/README.md": "[Surfaces](repository-surfaces.md)\n",
            "README.md": "[Surfaces](docs/repository-surfaces.md)\n",
            "ARCHITECTURE.md": "[Surfaces](./docs/repository-surfaces.md)\n",
            "docs/public-mirror.md": "[Surfaces](repository-surfaces.md)\n",
            "docs/release.md": "[Surfaces](repository-surfaces.md)\n",
            "tests/test_doc_graph_integrity.py": "def test_placeholder(): pass\n",
            "ops/scripts/core/release_authority_state_runtime.py": (
                "def release_status_v2_view(): pass\n"
                "def machine_release_allowed_from_status_view(): pass\n"
                "def clean_required_preflight_passes(): pass\n"
                "def release_authority_reports_verified(): pass\n"
                "def current_release_manifest_pass(): pass\n"
                "def release_artifact_revision(): pass\n"
            ),
            "ops/scripts/release/release_status_v2.py": (
                "from ops.scripts.core.release_authority_state_runtime import release_status_v2_view\n"
            ),
            "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py": (
                "machine_release_allowed_from_status_view\nclean_required_preflight_passes\n"
            ),
            "ops/scripts/release/external_report_lifecycle_runtime.py": (
                "release_authority_reports_verified\ncurrent_release_manifest_pass\n"
            ),
            "ops/scripts/release/release_authority_inventory.py": "release_artifact_revision\n",
            "tests/test_release_authority_state_runtime.py": "def test_placeholder(): pass\n",
            "tests/test_release_status_v2.py": "def test_placeholder(): pass\n",
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.external / "p2.md").write_text(
            "# P2\n\n"
            "repository-surfaces, full-vault, public export, release source zip. "
            "release/mechanism service layer should separate authority, currentness, "
            "risk, learning_claim, JSON payload assembly, and domain decision logic.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/p2.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["repository_surface_entrypoint_documentation"]["current_status"],
            "implemented",
        )
        self.assertEqual(
            actions["release_mechanism_service_layer_extraction"]["current_status"],
            "partially_automated",
        )
        coverage = {item["path"]: item for item in report["active_report_coverage"]}
        self.assertIn(
            "repository_surface_entrypoint_documentation",
            coverage["external-reports/p2.md"]["matched_action_ids"],
        )
        self.assertIn(
            "release_mechanism_service_layer_extraction",
            coverage["external-reports/p2.md"]["matched_action_ids"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
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




if __name__ == "__main__":
    unittest.main()
