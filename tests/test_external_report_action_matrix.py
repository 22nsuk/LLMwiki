from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.external_report_action_matrix import (
    _reason_detail_summary,
    build_report,
    write_report,
)
from ops.scripts.external_report_lifecycle_runtime import (
    action_status_reason_details,
    action_statuses,
    archive_reconciliation_observation_inventory,
    collaboration_governance_surface_reason_ids,
    coverage_action_basis,
    coverage_with_action_basis,
    lifecycle_decision,
    report_coverage_item,
    report_lifecycle_profiles,
)
from ops.scripts.gate_effect_vocabulary import strongest_gate_effect
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_revision_runtime import resolve_source_revision
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from ops.scripts.release.release_closeout_finality_attestation import (
    BATCH_MANIFEST_PATH,
    DEFAULT_OUT as FINALITY_ATTESTATION_PATH,
    FIXED_POINT_REPORT_PATH,
    SELF_CHECK_PATH,
    build_report as build_finality_attestation_report,
    write_report as write_finality_attestation,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "external-report-action-matrix.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 10, 8, 30, tzinfo=dt.UTC),
    )


def _canonical_json_digest(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    def _write_task_observations(self, observations: list[dict]) -> None:
        self._write_json(
            "ops/reports/task-improvement-observations/task-archive-audit/improvement-observations.json",
            {"observations": observations},
        )

    def _write_static_github_security_surfaces(self) -> None:
        pinned_sha = "a" * 40
        for rel_path, text in {
            ".github/dependabot.yml": "version: 2\nupdates: []\n",
            ".github/workflows/ci.yml": (
                "concurrency: ci\njobs:\n  test:\n    steps:\n"
                f"      - uses: actions/checkout@{pinned_sha}\n"
            ),
            ".github/workflows/release.yml": (
                "concurrency: release\njobs:\n  release:\n    steps:\n"
                f"      - uses: actions/attest-build-provenance@{pinned_sha}\n"
            ),
            ".github/workflows/codeql.yml": (
                "concurrency: codeql\njobs:\n  analyze:\n    steps:\n"
                f"      - uses: github/codeql-action/init@{pinned_sha}\n"
            ),
            ".github/workflows/dependency-review.yml": (
                "concurrency: dependency-review\njobs:\n  review:\n    steps:\n"
                f"      - uses: actions/dependency-review-action@{pinned_sha}\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def _artifact_freshness_payload(
        self,
        *,
        artifact_count: int,
        stale_artifact_count: int,
        operational_attention_artifact_count: int,
        status: str = "pass",
        currentness_status: str = "current",
        source_revision: str | None = None,
        source_tree_fingerprint: str | None = None,
    ) -> dict:
        return {
            "artifact_kind": "artifact_freshness_report",
            "artifact_status": "current",
            "currentness": {"status": currentness_status},
            "source_revision": source_revision or resolve_source_revision(self.vault).revision,
            "source_tree_fingerprint": (
                source_tree_fingerprint or release_source_tree_fingerprint(self.vault)
            ),
            "status": status,
            "summary": {
                "artifact_count": artifact_count,
                "stale_artifact_count": stale_artifact_count,
                "operational_attention_artifact_count": operational_attention_artifact_count,
            },
        }

    def _artifact_freshness_state(
        self,
        *,
        artifact_count: int,
        stale_artifact_count: int,
        operational_attention_artifact_count: int,
    ) -> dict:
        return {
            "evidence_status": "current",
            "evidence_path": "ops/reports/artifact-freshness-report.json",
            "stale_artifact_count": stale_artifact_count,
            "total_artifact_count": artifact_count,
            "operational_attention_artifact_count": operational_attention_artifact_count,
            "summary": f"{stale_artifact_count} stale / {artifact_count} total; "
            f"{operational_attention_artifact_count} operational attention",
            "reason_id": "artifact_freshness_report_current",
            "owner_target": "artifact-freshness",
        }

    def _unavailable_artifact_freshness_state(
        self,
        *,
        evidence_status: str,
        reason_id: str,
    ) -> dict:
        return {
            "evidence_status": evidence_status,
            "evidence_path": "ops/reports/artifact-freshness-report.json",
            "stale_artifact_count": None,
            "total_artifact_count": None,
            "operational_attention_artifact_count": None,
            "summary": (
                f"artifact freshness evidence {evidence_status}; "
                "current canonical artifact freshness state unavailable"
            ),
            "reason_id": reason_id,
            "owner_target": "artifact-freshness",
        }

    def _write_support_reports(self) -> None:
        self._write_json(
            "ops/reports/release-workflow-order-guard.json",
            {"status": "pass"},
        )
        self._write_json(
            "ops/reports/workflow-dependency-planner.json",
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
            "external-reports/report-reference-manifest.json",
            {
                "summary": {
                    "active_reference_set_status": "current",
                    "current_distribution_zip_known": True,
                    "basis_zip_matches_current_distribution": True,
                    "zip_provenance_status": "basis_current_match",
                }
            },
        )
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
        generated_path = "ops/reports/generated-artifact-index.json"
        self._write_json(
            generated_path,
            {"artifact_kind": "generated_artifact_index", "status": "pass"},
        )
        self._write_json(
            BATCH_MANIFEST_PATH,
            {
                "status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "finality": {
                    "finality_required": True,
                    "finality_attestation_path": FINALITY_ATTESTATION_PATH,
                    "binding_authority": "release-closeout-finality-attestation",
                },
            },
        )
        batch_digest = _sha256_file(self.vault / BATCH_MANIFEST_PATH)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {"batch_manifest_fingerprint": batch_digest},
            },
        )
        digest_map = {
            generated_path: _sha256_file(self.vault / generated_path),
            BATCH_MANIFEST_PATH: batch_digest,
            SELF_CHECK_PATH: _sha256_file(self.vault / SELF_CHECK_PATH),
        }
        self._write_json(
            FIXED_POINT_REPORT_PATH,
            {
                "status": "pass",
                "converged": True,
                "converged_iteration": 1,
                "tracked_artifacts": [{"path": path} for path in sorted(digest_map)],
                "final_digest_map": digest_map,
            },
        )
        finality_report = build_finality_attestation_report(self.vault, context=fixed_context())
        write_finality_attestation(self.vault, finality_report)
        current_source_tree_fingerprint = release_source_tree_fingerprint(self.vault)
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "status": "pass",
                "artifact_kind": "release_run_manifest",
                "source_revision": "source_package_without_git",
                "source_tree_fingerprint": current_source_tree_fingerprint,
            },
        )
        self._write_json(
            "build/release/release-sealed-run-manifest.json",
            {
                "status": "pass",
                "artifact_kind": "release_sealed_run_manifest",
                "source_revision": "source_package_without_git",
                "source_tree_fingerprint": current_source_tree_fingerprint,
            },
        )
        self._write_json(
            "build/release/release-auto-promotion-ready-manifest.json",
            {
                "status": "pass",
                "artifact_kind": "release_auto_promotion_ready_manifest",
                "source_revision": "source_package_without_git",
                "source_tree_fingerprint": current_source_tree_fingerprint,
                "auto_promotion_status": "allowed",
                "unattended_promotion_allowed": True,
            },
        )

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

    def test_generated_artifact_policy_status_requires_pass_report_status(self) -> None:
        for rel_path, text in {
            "ops/scripts/core/generated_artifact_index.py": (
                "def tracking_policy():\n"
                "    return {'commit_policy': 'decision-grade', 'retention_classes': ['ephemeral']}\n"
            ),
            "ops/schemas/generated-artifact-index.schema.json": (
                '{"properties":{"tracking_policy":{},"retention_classes":{"enum":["ephemeral"]}}}\n'
            ),
            "tests/test_generated_artifact_index.py": (
                "def test_tracking_policy_mentions_decision_grade(): pass\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {
                "artifact_kind": "generated_artifact_index_report",
                "producer": "ops.scripts.generated_artifact_index",
                "status": "attention",
                "summary": {"archive_candidate_count": 1},
            },
        )

        self.assertEqual(
            action_statuses(self.vault)["generated_artifact_tracking_policy"],
            "partially_automated",
        )
        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {
                "artifact_kind": "generated_artifact_index_report",
                "producer": "ops.scripts.generated_artifact_index",
                "status": "fail",
            },
        )
        self.assertEqual(
            action_statuses(self.vault)["generated_artifact_tracking_policy"],
            "partially_automated",
        )
        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {
                "artifact_kind": "generated_artifact_index_report",
                "producer": "ops.scripts.generated_artifact_index",
                "status": "pass",
                "summary": {"archive_candidate_count": 0},
            },
        )
        self.assertEqual(
            action_statuses(self.vault)["generated_artifact_tracking_policy"],
            "implemented",
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
        self.assertIn(
            "external-reports/release.md",
            actions["script_output_surfaces_currentness"]["source_report_paths"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_report(self.vault, report).exists())

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

    def test_operator_observations_need_resolution_evidence_to_close(self) -> None:
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

        missing_evidence_actions = {
            item["action_id"]: item for item in missing_evidence_report["action_items"]
        }
        for action_id, reason_id in {
            "source_package_distribution_binding": "review_bundle_full_vault_hygiene_gap",
            "github_governance_live_drift_verification": "github_governance_live_drift_gap",
        }.items():
            self.assertEqual(
                missing_evidence_actions[action_id]["current_status"],
                "partially_automated",
            )
            self.assertIn(reason_id, missing_evidence_actions[action_id]["status_reason_ids"])
        for static_action_id in (
            "collaboration_governance_surface",
            "github_native_security_automation",
        ):
            self.assertEqual(
                missing_evidence_actions[static_action_id]["current_status"],
                "implemented",
                static_action_id,
            )
            self.assertNotIn(
                "github_governance_live_drift_gap",
                missing_evidence_actions[static_action_id]["status_reason_ids"],
            )
        live_detail = {
            item["reason_id"]: item
            for item in missing_evidence_actions[
                "github_governance_live_drift_verification"
            ]["status_reason_details"]
        }["github_governance_live_drift_gap"]
        self.assertEqual(live_detail["owning_stage"], "github_live_governance_verification")
        self.assertEqual(live_detail["blocking_scope"], "github_live_governance")

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

        closed_report = build_report(self.vault, context=fixed_context())

        closed_actions = {item["action_id"]: item for item in closed_report["action_items"]}
        self.assertEqual(
            closed_actions["source_package_distribution_binding"]["current_status"],
            "implemented",
        )
        self.assertNotIn(
            "review_bundle_full_vault_hygiene_gap",
            closed_actions["source_package_distribution_binding"]["status_reason_ids"],
        )
        self.assertEqual(
            closed_actions["collaboration_governance_surface"]["current_status"],
            "implemented",
        )
        self.assertNotIn(
            "github_governance_live_drift_gap",
            closed_actions["collaboration_governance_surface"]["status_reason_ids"],
        )
        self.assertEqual(
            closed_actions["github_native_security_automation"]["current_status"],
            "implemented",
        )
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

    def test_broad_actions_do_not_complete_from_surface_only_evidence(self) -> None:
        self._write_json(
            "ops/reports/function-budget-refactor-proposals.json",
            {
                "artifact_kind": "function_budget_refactor_proposals",
                "producer": "ops.scripts.function_budget_refactor_proposals",
                "status": "pass",
                "summary": {
                    "function_budget_candidate_count": 3,
                    "proposal_count": 2,
                    "owner_backlog_count": 1,
                    "large_main_without_tests_or_docs_count": 0,
                },
            },
        )
        self._write_json("ops/reports/supply-chain-gate-report.json", {"status": "pass"})
        self._write_json("ops/reports/sbom-readiness-gate-report.json", {"status": "pass"})
        self._write_json(
            "ops/reports/in-toto-statement.json",
            {"predicateType": "https://slsa.dev/provenance/v1"},
        )
        self._write_json(
            "ops/reports/sigstore-bundle-verification.json",
            {
                "status": "local-integrity-only",
                "verification_checks": [{"rule": "external_bundle_observed"}],
            },
        )
        for rel_path, text in {
            "tests/test_function_budget_refactor_proposals.py": "def test_placeholder(): pass\n",
            "ops/scripts/eval/function_budget_refactor_proposals.py": "def main(): pass\n",
            "mk/supply_chain.mk": (
                "supply-chain-check:\n\tpython -m ops.scripts.supply_chain\n"
                "sigstore-bundle:\n\tpython -m ops.scripts.sigstore\n"
            ),
            ".github/workflows/release.yml": "steps:\n  - uses: actions/attest-build-provenance@v2\n",
            ".github/workflows/dependency-review.yml": (
                "steps:\n  - uses: actions/dependency-review-action@v4\n"
            ),
            ".github/CODEOWNERS": "",
            ".github/pull_request_template.md": "",
            "CONTRIBUTING.md": "",
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._write_task_observations(
            [{"observation_id": "broad_action_completion_threshold_gap", "status": "open"}]
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertFalse(
            any(
                "broad_action_completion_threshold_gap" in item["status_reason_ids"]
                for item in report["action_items"]
            )
        )
        maintainability_action = actions["maintainability_hotspot_refactor_backlog"]
        self.assertEqual(
            maintainability_action["current_status"],
            "partially_automated",
        )
        self.assertIn(
            "maintainability_hotspot_owner_backlog_not_absorbed",
            maintainability_action["status_reason_ids"],
        )
        self.assertNotIn(
            "broad_action_completion_threshold_gap",
            maintainability_action["status_reason_ids"],
        )
        maintainability_details = {
            detail["reason_id"]: detail for detail in maintainability_action["status_reason_details"]
        }
        self.assertEqual(
            maintainability_details[
                "maintainability_hotspot_owner_backlog_not_absorbed"
            ]["blocking_scope"],
            "maintainability_owner_backlog",
        )
        self.assertIn(
            "maintainability_proposal_absorption",
            maintainability_action["blocking_scopes"],
        )
        self.assertNotIn("action_matrix", maintainability_action["blocking_scopes"])
        self.assertEqual(
            maintainability_action["recommended_target"],
            "function-budget-refactor-proposals",
        )
        supply_chain_action = actions["supply_chain_external_verification"]
        self.assertEqual(
            supply_chain_action["current_status"],
            "partially_automated",
        )
        self.assertIn(
            "supply_chain_sigstore_local_integrity_only",
            supply_chain_action["status_reason_ids"],
        )
        self.assertNotIn(
            "broad_action_completion_threshold_gap",
            supply_chain_action["status_reason_ids"],
        )
        supply_chain_details = {
            detail["reason_id"]: detail for detail in supply_chain_action["status_reason_details"]
        }
        self.assertEqual(
            supply_chain_details["supply_chain_sigstore_local_integrity_only"]["blocking_scope"],
            "supply_chain_external_verification",
        )
        self.assertNotIn("action_matrix", supply_chain_action["blocking_scopes"])
        self.assertEqual(supply_chain_action["recommended_target"], "supply-chain-check")
        self.assertEqual(
            actions["collaboration_governance_surface"]["current_status"],
            "partially_automated",
        )
        self.assertNotIn(
            "broad_action_completion_threshold_gap",
            actions["collaboration_governance_surface"]["status_reason_ids"],
        )
        self.assertIn(
            "collaboration_governance_codeowners_review_owner_missing",
            actions["collaboration_governance_surface"]["status_reason_ids"],
        )

    def test_maintainability_and_supply_chain_reason_details_require_exact_mapping(
        self,
    ) -> None:
        maintainability_reasons = [
            "maintainability_hotspot_report_missing",
            "maintainability_hotspot_report_kind_mismatch",
            "maintainability_hotspot_report_producer_mismatch",
            "maintainability_hotspot_report_not_pass",
            "maintainability_hotspot_candidates_remain",
            "maintainability_hotspot_proposals_not_absorbed",
            "maintainability_hotspot_owner_backlog_not_absorbed",
            "maintainability_hotspot_large_main_remains",
        ]
        supply_chain_reasons = [
            "supply_chain_gate_not_pass",
            "supply_chain_sbom_readiness_not_pass",
            "supply_chain_slsa_predicate_missing",
            "supply_chain_sigstore_local_integrity_only",
            "supply_chain_sigstore_external_bundle_not_verified",
            "supply_chain_sigstore_checks_missing",
            "supply_chain_external_bundle_rule_missing",
            "supply_chain_release_attestation_missing",
            "supply_chain_dependency_review_missing",
            "supply_chain_sigstore_bundle_target_missing",
        ]

        details = action_status_reason_details(
            [*maintainability_reasons, *supply_chain_reasons],
            fallback_target="external-report-action-matrix",
        )

        detail_by_reason = {detail["reason_id"]: detail for detail in details}
        for reason_id in maintainability_reasons:
            self.assertIn(reason_id, detail_by_reason)
            self.assertNotEqual(
                detail_by_reason[reason_id]["blocking_scope"],
                "maintainability_hotspot",
            )
            self.assertNotEqual(detail_by_reason[reason_id]["blocking_scope"], "action_matrix")
            self.assertEqual(
                detail_by_reason[reason_id]["recommended_targets"],
                ["function-budget-refactor-proposals"],
            )
        for reason_id in supply_chain_reasons:
            self.assertIn(reason_id, detail_by_reason)
            self.assertEqual(
                detail_by_reason[reason_id]["blocking_scope"],
                "supply_chain_external_verification",
            )
            self.assertNotEqual(detail_by_reason[reason_id]["blocking_scope"], "supply_chain")
            self.assertEqual(
                detail_by_reason[reason_id]["recommended_targets"],
                ["supply-chain-check"],
            )

        unmapped_details = action_status_reason_details(
            [
                "maintainability_hotspot_unmapped_future_reason",
                "supply_chain_unmapped_future_reason",
            ],
            fallback_target="external-report-action-matrix",
        )

        self.assertEqual(
            [detail["blocking_scope"] for detail in unmapped_details],
            ["action_matrix", "action_matrix"],
        )

    def test_collaboration_governance_surface_requires_real_static_surfaces(self) -> None:
        for rel_path, text in {
            ".github/CODEOWNERS": "# * @maintainers\n",
            ".github/pull_request_template.md": (
                "<!-- ## Review\n- [ ] reviewer confirms validation -->\n"
                "## Summary\n- placeholder\n"
            ),
            "CONTRIBUTING.md": (
                "# Contributing\n\n"
                "<!-- commit governance policy -->\n"
                "TODO: commit governance policy.\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        placeholder_report = build_report(self.vault, context=fixed_context())

        placeholder_action = {
            item["action_id"]: item for item in placeholder_report["action_items"]
        }["collaboration_governance_surface"]
        self.assertEqual(placeholder_action["current_status"], "partially_automated")
        self.assertIn(
            "collaboration_governance_codeowners_review_owner_missing",
            placeholder_action["status_reason_ids"],
        )
        self.assertIn(
            "collaboration_governance_pr_template_review_missing",
            placeholder_action["status_reason_ids"],
        )
        self.assertIn(
            "collaboration_governance_contributing_policy_missing",
            placeholder_action["status_reason_ids"],
        )

        for rel_path, text in {
            ".github/CODEOWNERS": "* @maintainers\n",
            ".github/pull_request_template.md": (
                "## Preview\n- [ ] Reviewer confirms validation and boundary impact.\n"
            ),
            "CONTRIBUTING.md": (
                "# Contributing\n\n"
                "## Commit governance\n"
                "Contributors must describe commit taxonomy and governance impact.\n"
            ),
        }.items():
            (self.vault / rel_path).write_text(text, encoding="utf-8")

        preview_report = build_report(self.vault, context=fixed_context())

        preview_action = {
            item["action_id"]: item for item in preview_report["action_items"]
        }["collaboration_governance_surface"]
        self.assertEqual(preview_action["current_status"], "partially_automated")
        self.assertEqual(
            preview_action["status_reason_ids"],
            ["collaboration_governance_pr_template_review_missing"],
        )

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
        }.items():
            (self.vault / rel_path).write_text(text, encoding="utf-8")

        real_report = build_report(self.vault, context=fixed_context())

        real_action = {
            item["action_id"]: item for item in real_report["action_items"]
        }["collaboration_governance_surface"]
        self.assertEqual(real_action["current_status"], "implemented")
        self.assertEqual(real_action["status_reason_ids"], [])

    def test_checked_in_collaboration_governance_surface_is_strictly_implemented(
        self,
    ) -> None:
        self.assertEqual(collaboration_governance_surface_reason_ids(REPO_ROOT), [])

    def test_supply_chain_external_verification_requires_real_workflow_uses_entries(self) -> None:
        self._write_json("ops/reports/supply-chain-gate-report.json", {"status": "pass"})
        self._write_json("ops/reports/sbom-readiness-gate-report.json", {"status": "pass"})
        self._write_json(
            "ops/reports/in-toto-statement.json",
            {"predicateType": "https://slsa.dev/provenance/v1"},
        )
        self._write_json(
            "ops/reports/sigstore-bundle-verification.json",
            {
                "status": "verified-external-bundle",
                "verification_checks": [{"rule": "external_bundle_observed"}],
            },
        )
        for rel_path, text in {
            "mk/supply_chain.mk": (
                "supply-chain-check:\n\tpython -m ops.scripts.supply_chain\n"
                "sigstore-bundle:\n\tpython -m ops.scripts.sigstore\n"
            ),
            ".github/workflows/release.yml": (
                "# uses: actions/attest-build-provenance@v2\n"
            ),
            ".github/workflows/dependency-review.yml": (
                "# uses: actions/dependency-review-action@v4\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        action = {
            item["action_id"]: item for item in report["action_items"]
        }["supply_chain_external_verification"]
        self.assertEqual(action["current_status"], "partially_automated")
        self.assertIn(
            "supply_chain_release_attestation_missing",
            action["status_reason_ids"],
        )
        self.assertIn(
            "supply_chain_dependency_review_missing",
            action["status_reason_ids"],
        )
        self.assertNotIn(
            "supply_chain_sigstore_external_bundle_not_verified",
            action["status_reason_ids"],
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

    def test_matrix_reflects_latest_artifact_freshness_currentness_input(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nexternal report lifecycle.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/release.md"}],
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

        report = build_report(self.vault, context=fixed_context())
        self.assertEqual(
            report["summary"]["canonical_artifact_freshness_state"],
            self._artifact_freshness_state(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
            ),
        )

        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=3,
                operational_attention_artifact_count=2,
                status="attention",
            ),
        )

        refreshed_report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            refreshed_report["summary"]["canonical_artifact_freshness_state"],
            self._artifact_freshness_state(
                artifact_count=12,
                stale_artifact_count=3,
                operational_attention_artifact_count=2,
            ),
        )
        self.assertEqual(validate_with_schema(refreshed_report, load_schema(SCHEMA_PATH)), [])

    def test_matrix_ignores_stale_artifact_freshness_currentness_input(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nexternal report lifecycle.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/release.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
                currentness_status="stale",
            ),
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["summary"]["canonical_artifact_freshness_state"],
            self._unavailable_artifact_freshness_state(
                evidence_status="stale",
                reason_id="artifact_freshness_currentness_not_current",
            ),
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_matrix_ignores_artifact_freshness_source_identity_mismatch(self) -> None:
        (self.external / "release.md").write_text(
            "# Release Review\n\nexternal report lifecycle.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/release.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            self._artifact_freshness_payload(
                artifact_count=12,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
                source_revision="previous-revision",
                source_tree_fingerprint="previous-fingerprint",
            ),
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["summary"]["canonical_artifact_freshness_state"],
            self._unavailable_artifact_freshness_state(
                evidence_status="source_identity_mismatch",
                reason_id="artifact_freshness_source_revision_mismatch",
            ),
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

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

    def test_source_revision_unknown_is_explicit_partial_until_canonical_reports_are_refreshed(self) -> None:
        for rel_path in (
            "ops/scripts/core/source_revision_runtime.py",
            "ops/scripts/core/artifact_freshness_runtime.py",
            "ops/scripts/core/bootstrap_preflight.py",
            "tests/test_source_revision_runtime.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_placeholder(): pass\n", encoding="utf-8")
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            {
                "producer": "ops.scripts.artifact_freshness_runtime",
                "status": "fail",
            },
        )
        self._write_json(
            "ops/reports/legacy-canonical-report.json",
            {"source_revision": "unknown"},
        )
        (self.external / "source-revision.md").write_text(
            "# Source Revision Review\n\n"
            "P0: remove `source_revision: unknown` from canonical reports and use "
            "`source_package_without_git` only when git metadata is absent.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/source-revision.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        action = actions["source_revision_unknown_canonical_reports"]
        self.assertEqual(action["current_status"], "partially_automated")
        self.assertIn("external-reports/source-revision.md", action["source_report_paths"])

        self._write_json(
            "ops/reports/legacy-canonical-report.json",
            {"source_revision": "source_package_without_git"},
        )

        refreshed_report = build_report(self.vault, context=fixed_context())
        refreshed_actions = {item["action_id"]: item for item in refreshed_report["action_items"]}
        self.assertEqual(
            refreshed_actions["source_revision_unknown_canonical_reports"]["current_status"],
            "implemented",
        )

    def test_source_revision_unknown_release_authority_reports_require_release_verification(self) -> None:
        for rel_path in (
            "ops/scripts/core/source_revision_runtime.py",
            "ops/scripts/core/artifact_freshness_runtime.py",
            "ops/scripts/core/bootstrap_preflight.py",
            "tests/test_source_revision_runtime.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_placeholder(): pass\n", encoding="utf-8")
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            {
                "producer": "ops.scripts.artifact_freshness_runtime",
                "status": "pass",
            },
        )
        for rel_path in (
            "ops/reports/learning-readiness-signoff.json",
            "ops/reports/release-closeout-finality-attestation.json",
            "ops/reports/source-package-clean-extract.json",
        ):
            self._write_json(rel_path, {"source_revision": "unknown"})
        (self.external / "source-revision.md").write_text(
            "# Source Revision Review\n\n"
            "P0: remove `source_revision: unknown` from canonical reports without "
            "rewriting release authority evidence by hand.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/source-revision.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["source_revision_unknown_canonical_reports"]["current_status"],
            "requires_release_run_verification",
        )

    def test_reassessment_actions_are_classified_from_current_source_contracts(self) -> None:
        for rel_path, text in {
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py": (
                "from .set_mechanism_run_history import (\n"
                "    MechanismRunRecord,\n"
                ")\n"
            ),
            "tools/ruff_strict_preview.py": "def main(): pass\n",
            "ops/scripts/release/release_source_ready_commit.py": (
                "LOCAL_ONLY_PRIVATE_DEINDEX_CATEGORY = 'local_only_private_deindex'\n"
                "local_only_deindex_paths = []\n"
                "def stage():\n"
                "    return ['rm', '--cached', '--ignore-unmatch']\n"
            ),
            "tests/test_release_source_ready_commit.py": (
                "def test_commits_deindex_with_public_and_generated_updates(): pass\n"
            ),
            "pyproject.toml": "[project]\nname = 'llmwiki-test'\n",
            "uv.lock": "# lock\n",
            "docs/development.md": (
                "Run make help for operator entrypoints. "
                "Use uv lock --check to verify uv.lock.\n"
            ),
            "Makefile": "include mk/core.mk\ninclude mk/static.mk\n",
            "mk/core.mk": (
                ".PHONY: help\n"
                "help:\n"
                "\t@printf '%s\\n' 'release public mechanism report-contract'\n"
            ),
            "mk/static.mk": (
                "RUFF_STRICT_PREVIEW_TARGETS ?= ops/scripts tests tools\n"
                "STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools\n"
                "ruff-strict-preview:\n"
                "\tpython tools/ruff_strict_preview.py --targets \"$(RUFF_STRICT_PREVIEW_TARGETS)\"\n"
                "strict-preview-audit:\n"
                "\tpython tools/strict_preview_audit.py --targets \"$(STRICT_PREVIEW_AUDIT_TARGETS)\"\n"
            ),
            "tools/strict_preview_audit.py": (
                "def build_report():\n"
                "    return {'artifact_kind': 'strict_preview_audit'}\n"
            ),
            "tests/test_strict_preview_audit.py": (
                "def test_targets():\n"
                "    assert 'ops/scripts tests tools'\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.external / "reassessment.md").write_text(
            "# Reassessment\n\n"
            "Ruff strict I001 import order, release_source_ready_commit deindex, "
            "uv lock --check canonical dependency policy, make help operator entrypoint index, "
            "strict-preview all-target ops/scripts tests tools audit after legacy allowlist removal.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/reassessment.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in (
            "ruff_strict_preview_import_order",
            "release_source_ready_deindex_hardening",
            "uv_lock_canonical_policy",
            "operator_entrypoint_index",
            "strict_preview_all_target_audit",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented", action_id)
            self.assertIn(
                "external-reports/reassessment.md",
                actions[action_id]["source_report_paths"],
            )
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

    def test_p2_service_layer_requires_symbols_and_consumer_imports(self) -> None:
        for rel_path, text in {
            "ops/scripts/core/release_authority_state_runtime.py": (
                "def release_status_v2_view(): pass\n"
                "def machine_release_allowed_from_status_view(): pass\n"
                "def clean_required_preflight_passes(): pass\n"
                "def release_authority_reports_verified(): pass\n"
                "def current_release_manifest_pass(): pass\n"
                "def release_artifact_revision(): pass\n"
            ),
            "ops/scripts/core/release_currentness_state_runtime.py": (
                "def currentness_field(): pass\n"
                "def live_rerun_state(): pass\n"
                "def components_match_current_source_tree(): pass\n"
            ),
            "ops/scripts/core/release_risk_state_runtime.py": (
                "def release_risk_identity(): pass\n"
                "def release_risk_blocks_clean_lane(): pass\n"
                "def release_risk_list(): pass\n"
                "def release_blocker_entry(): pass\n"
            ),
            "ops/scripts/core/learning_claim_state_runtime.py": (
                "def confirmed_evidence_summary(): pass\n"
                "def confirmed_predicate_results(): pass\n"
                "def confirmed_blocking_predicate_ids(): pass\n"
                "def confirmed_wording_allowed(): pass\n"
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
            "tests/test_release_currentness_state_runtime.py": "def test_placeholder(): pass\n",
            "tests/test_release_risk_state_runtime.py": "def test_placeholder(): pass\n",
            "tests/test_learning_claim_state_runtime.py": "def test_placeholder(): pass\n",
            "ops/scripts/release/release_evidence_cohort.py": (
                "from ops.scripts.core.release_currentness_state_runtime import currentness_field\n"
            ),
            "ops/scripts/release/release_closeout_summary.py": (
                "from ops.scripts.core.release_currentness_state_runtime import components_match_current_source_tree\n"
                "from ops.scripts.core.release_risk_state_runtime import release_risk_identity\n"
                "components_match_current_source_tree(\nrelease_risk_identity(\n"
            ),
            "ops/scripts/release/release_evidence_dashboard.py": (
                "from ops.scripts.core.release_currentness_state_runtime import live_rerun_state\n"
                "from ops.scripts.core.learning_claim_state_runtime import confirmed_evidence_summary\n"
                "live_rerun_state(\nconfirmed_evidence_summary(\n"
            ),
            "ops/scripts/release/release_clean_blocker_ledger.py": (
                "from ops.scripts.core.release_risk_state_runtime import release_risk_blocks_clean_lane\n"
                "release_risk_blocks_clean_lane(\n"
            ),
            "ops/scripts/learning/learning_delta_scoreboard_unlock_runtime.py": (
                "from ops.scripts.core.learning_claim_state_runtime import confirmed_evidence_summary\n"
                "confirmed_evidence_summary(\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.external / "p2.md").write_text(
            "# P2\n\nrelease/mechanism service layer should separate authority, "
            "currentness, risk, and learning_claim.\n",
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
            actions["release_mechanism_service_layer_extraction"]["current_status"],
            "implemented",
        )

    def test_self_improvement_strategy_actions_remain_open_until_canonical_evidence(self) -> None:
        for rel_path, text in {
            "ops/scripts/core/artifact_freshness_runtime.py": "def build_report(): pass\n",
            "tests/test_artifact_freshness_runtime.py": "def test_placeholder(): pass\n",
            "mk/artifact.mk": "artifact-freshness-check:\n\tpython -m ops.scripts.artifact_freshness\n",
            ".gitignore": "raw/\nwiki/\nsystem/\nruns/\nexternal-reports/*\n",
            "ARCHITECTURE.md": "public mirror excludes raw, wiki, system, runs, external-reports.\n",
            "ops/scripts/public/public_surface_policy.py": "EXCLUDED_PREFIXES = ['raw/', 'wiki/', 'system/', 'runs/', 'external-reports/']\n",
            "tests/test_public_surface_policy.py": "def test_placeholder(): pass\n",
            "tests/test_export_public_repo.py": "def test_placeholder(): pass\n",
            ".github/workflows/ci.yml": "name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n",
            ".github/workflows/release.yml": "name: Release\njobs:\n  release:\n    steps:\n      - uses: actions/upload-artifact@v4\n",
            "tests/test_function_budget_refactor_proposals.py": "def test_placeholder(): pass\n",
            "ops/scripts/eval/function_budget_refactor_proposals.py": "def build_report(): pass\n",
            "ops/scripts/core/generated_artifact_index.py": "def build_report(): pass\n",
            "ops/schemas/generated-artifact-index.schema.json": '{"type": "object"}\n',
            "tests/test_generated_artifact_index.py": "def test_placeholder(): pass\n",
            "ops/scripts/public/export_public_repo.py": "def export_public_repo(): pass\n",
            "ops/scripts/public/public_check_summary.py": "def build_report(): pass\n",
            "tests/test_public_check_summary.py": "def test_placeholder(): pass\n",
            "mk/supply_chain.mk": "supply-chain-check:\n\tpython -m ops.scripts.supply_chain\n",
            "CONTRIBUTING.md": "# Contributing\n",
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            {"status": "pass", "summary": {}},
        )
        self._write_json(
            "ops/reports/public-check-summary.json",
            {"status": "pass", "summary": {"public_export_status": "pass"}},
        )
        self._write_json(
            "ops/reports/function-budget-refactor-proposals.json",
            {"status": "pass", "summary": {"function_budget_candidate_count": 3, "proposal_count": 2}},
        )
        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {"status": "pass", "summary": {"archive_candidate_count": 1}},
        )
        self._write_json("ops/reports/supply-chain-gate-report.json", {"status": "pass"})
        self._write_json("ops/reports/sbom-readiness-gate-report.json", {"status": "pass"})
        self._write_json(
            "ops/reports/in-toto-statement.json",
            {"predicateType": "https://slsa.dev/provenance/v1"},
        )
        self._write_json(
            "ops/reports/sigstore-bundle-verification.json",
            {"status": "pass", "verification_checks": [{"status": "pass"}]},
        )
        (self.external / "self-improvement.md").write_text(
            "# Self Improvement\n\n"
            "artifact freshness progress jsonl, schema validator cache, per-phase timing, check-observed. "
            "repo boundary, private vault, public/dev repo, generated bulk. "
            "Dependabot, CodeQL, dependency review, required status, action pinning, concurrency, GitHub-native. "
            "complexity hotspot, giant test, function budget, orchestrator. "
            "generated artifact commit churn, decision-grade, ephemeral, tracked set, canonical refresh. "
            "negative assertion, excluded_prefix_absence, local_path_absence, private_pattern_absence, public export. "
            "Scorecard, SBOM schema validation, SLSA, in-toto verification, provenance verification. "
            "CODEOWNERS, PR template, commit taxonomy, collaboration governance.\n",
            encoding="utf-8",
        )
        self._write_json(
            "external-reports/report-reference-manifest.json",
            {
                "references": [{"path": "external-reports/self-improvement.md"}],
                "summary": {"active_reference_set_status": "current"},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in (
            "artifact_freshness_performance_observability",
            "repo_boundary_history_hygiene",
            "github_native_security_automation",
            "maintainability_hotspot_refactor_backlog",
            "generated_artifact_tracking_policy",
            "public_export_negative_assertions",
            "supply_chain_external_verification",
            "collaboration_governance_surface",
        ):
            self.assertEqual(actions[action_id]["current_status"], "partially_automated", action_id)
            self.assertIn(
                "external-reports/self-improvement.md",
                actions[action_id]["source_report_paths"],
            )
        profiles = report_lifecycle_profiles(self.vault, [self.external / "self-improvement.md"])
        decision = lifecycle_decision(
            profiles[0],
            profiles=profiles,
            statuses=action_statuses(self.vault),
        )
        self.assertFalse(decision["archive_recommended"])
        self.assertIn("maintainability_hotspot_refactor_backlog", decision["unresolved_action_ids"])
        self.assertGreater(decision["unresolved_action_count"], 0)

    def test_artifact_freshness_stable_contract_debt_has_backfill_target(self) -> None:
        for rel_path, text in {
            "ops/scripts/core/artifact_freshness_runtime.py": (
                "class ArtifactFreshnessContext: pass\n"
                "schema_cache = {}\n"
                "phase_timings = []\n"
                "def progress_jsonl(): return '--progress jsonl'\n"
            ),
            "tests/test_artifact_freshness_runtime.py": "def test_placeholder(): pass\n",
            "mk/artifact.mk": (
                "artifact-freshness-refresh-check:\n\tpython -m ops.scripts.artifact_freshness\n"
                "artifact-freshness-stable-contract-debt-refresh:\n"
                "\tpython -m ops.scripts.backfill_archived_run_artifacts\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "attention",
                "summary": {
                    "stale_artifact_count": 0,
                    "operational_attention_artifact_count": 0,
                    "stable_contract_debt_artifact_count": 3,
                },
            },
        )
        (self.external / "artifact-freshness.md").write_text(
            "# Artifact Freshness\n\nartifact freshness schema validator cache progress jsonl per-phase timing.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        action = actions["artifact_freshness_performance_observability"]
        self.assertEqual(action["current_status"], "partially_automated")
        self.assertEqual(action["status_reason_ids"], ["artifact_freshness_stable_contract_debt"])
        self.assertEqual(action["blocking_scopes"], ["artifact_freshness"])
        self.assertEqual(action["gate_effects"], ["advisory"])
        self.assertEqual(action["strongest_gate_effect"], "advisory")
        detail = action["status_reason_details"][0]
        self.assertEqual(detail["owning_stage"], "artifact_freshness")
        self.assertEqual(detail["blocking_scope"], "artifact_freshness")
        self.assertEqual(detail["gate_effect"], "advisory")
        self.assertIn(
            "artifact-freshness-stable-contract-debt-refresh",
            detail["recommended_targets"],
        )
        self.assertIn("artifact-freshness-refresh-check", detail["recommended_targets"])

    def test_artifact_freshness_operational_attention_does_not_claim_canonical_stale(self) -> None:
        for rel_path, text in {
            "ops/scripts/core/artifact_freshness_runtime.py": (
                "class ArtifactFreshnessContext: pass\n"
                "schema_cache = {}\n"
                "phase_timings = []\n"
                "def progress_jsonl(): return '--progress jsonl'\n"
            ),
            "tests/test_artifact_freshness_runtime.py": "def test_placeholder(): pass\n",
            "mk/artifact.mk": (
                "artifact-freshness-refresh-check:\n\tpython -m ops.scripts.artifact_freshness\n"
                "artifact-freshness-stable-contract-debt-refresh:\n"
                "\tpython -m ops.scripts.backfill_archived_run_artifacts\n"
            ),
        }.items():
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._write_json(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "attention",
                "summary": {
                    "stale_artifact_count": 2,
                    "operational_attention_artifact_count": 2,
                    "stable_contract_debt_artifact_count": 0,
                },
            },
        )
        (self.external / "artifact-freshness.md").write_text(
            "# Artifact Freshness\n\nartifact freshness schema validator cache progress jsonl per-phase timing.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        action = {
            item["action_id"]: item for item in report["action_items"]
        }["artifact_freshness_performance_observability"]
        self.assertEqual(action["status_reason_ids"], ["artifact_freshness_operational_attention"])
        self.assertEqual(action["gate_effects"], ["advisory"])

    def test_release_verified_actions_become_implemented_after_closeout(self) -> None:
        self._write_release_verification_reports()
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented")
            self.assertEqual(actions[action_id]["status_reason_ids"], [])
            self.assertEqual(actions[action_id]["status_reason_details"], [])
        self.assertEqual(actions["release_writer_dependency_single_source"]["current_status"], "implemented")
        self.assertEqual(report["summary"]["requires_release_run_verification_count"], 0)

    def test_finality_digest_drift_blocks_only_evidence_bundle_attestation(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {"artifact_kind": "generated_artifact_index", "status": "changed_after_finality"},
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in (
            "source_package_distribution_binding",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented")
        self.assertEqual(
            actions["release_evidence_bundle_and_attestation"]["current_status"],
            "requires_release_run_verification",
        )
        self.assertIn(
            "release_finality_attestation_verification_failed",
            actions["release_evidence_bundle_and_attestation"]["status_reason_ids"],
        )
        finality_detail = {
            item["reason_id"]: item
            for item in actions["release_evidence_bundle_and_attestation"]["status_reason_details"]
        }["release_finality_attestation_verification_failed"]
        self.assertEqual(finality_detail["owning_stage"], "release_auto_promotion_preseal")
        self.assertIn("release-auto-promotion-preseal", finality_detail["recommended_targets"])
        self.assertEqual(report["summary"]["requires_release_run_verification_count"], 1)

    def test_evidence_bundle_attestation_explains_manifest_dependency_mismatch(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "status": "pass",
                "artifact_kind": "release_run_manifest",
                "source_tree_fingerprint": "old-run-fingerprint",
            },
        )
        self._write_json(
            "build/release/release-sealed-run-manifest.json",
            {
                "status": "pass",
                "artifact_kind": "release_sealed_run_manifest",
                "source_tree_fingerprint": "old-sealed-fingerprint",
            },
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite, promotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        evidence_bundle = actions["release_evidence_bundle_and_attestation"]
        self.assertEqual(evidence_bundle["current_status"], "requires_release_run_verification")
        self.assertIn(
            "release_run_manifest_source_tree_fingerprint_mismatch",
            evidence_bundle["status_reason_ids"],
        )
        self.assertIn(
            "release_sealed_run_manifest_source_tree_fingerprint_mismatch",
            evidence_bundle["status_reason_ids"],
        )
        self.assertNotIn("requires_release_run_verification", evidence_bundle["status_reason_ids"])
        detail_targets = {
            target
            for item in evidence_bundle["status_reason_details"]
            for target in item["recommended_targets"]
        }
        self.assertIn("release-run-ready-plan-check", detail_targets)
        self.assertIn("release-sealed-run-ready-plan", detail_targets)
        self.assertEqual(evidence_bundle["recommended_target"], "release-run-ready")

    def test_release_verified_actions_explain_manifest_revision_mismatch(self) -> None:
        self._write_release_verification_reports()
        current_source_tree_fingerprint = release_source_tree_fingerprint(self.vault)
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "status": "pass",
                "artifact_kind": "release_run_manifest",
                "source_revision": "old-revision",
                "source_tree_fingerprint": current_source_tree_fingerprint,
            },
        )
        (self.external / "release.md").write_text(
            "# Release Review\n\nsource package, evidence bundle, full-suite.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        action = actions["full_suite_evidence_currentness"]
        self.assertEqual(action["current_status"], "requires_release_run_verification")
        self.assertEqual(action["blocking_scopes"], ["release_run"])
        self.assertEqual(action["gate_effects"], ["blocks_promotion"])
        self.assertEqual(action["strongest_gate_effect"], "blocks_promotion")
        self.assertIn(
            "release_run_manifest_source_revision_mismatch",
            action["status_reason_ids"],
        )
        detail = {
            item["reason_id"]: item for item in action["status_reason_details"]
        }["release_run_manifest_source_revision_mismatch"]
        self.assertEqual(detail["owning_stage"], "release_run_ready")
        self.assertEqual(detail["blocking_scope"], "release_run")
        self.assertEqual(detail["gate_effect"], "blocks_promotion")
        self.assertIn("release-run-ready", detail["recommended_targets"])
        self.assertEqual(action["recommended_target"], "release-run-ready")

    def test_promotion_truth_ladder_rejects_ready_manifest_revision_stale(self) -> None:
        self._write_release_verification_reports()
        ready = json.loads(
            (
                self.vault / "build/release/release-auto-promotion-ready-manifest.json"
            ).read_text(encoding="utf-8")
        )
        ready["source_revision"] = "old-revision"
        self._write_json("build/release/release-auto-promotion-ready-manifest.json", ready)
        (self.external / "release.md").write_text(
            "# Release Review\n\npromotion_blockers.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        action = actions["promotion_truth_ladder"]
        self.assertEqual(action["current_status"], "requires_release_run_verification")
        self.assertEqual(action["blocking_scopes"], ["unattended_promotion"])
        self.assertEqual(action["gate_effects"], ["blocks_promotion"])
        self.assertEqual(action["strongest_gate_effect"], "blocks_promotion")
        self.assertIn(
            "release_auto_promotion_ready_manifest_source_revision_mismatch",
            action["status_reason_ids"],
        )
        detail = {
            item["reason_id"]: item for item in action["status_reason_details"]
        }["release_auto_promotion_ready_manifest_source_revision_mismatch"]
        self.assertEqual(detail["owning_stage"], "release_auto_promotion_ready")
        self.assertEqual(detail["blocking_scope"], "unattended_promotion")
        self.assertEqual(detail["gate_effect"], "blocks_promotion")
        self.assertIn("release-auto-promotion-ready", detail["recommended_targets"])
        self.assertEqual(action["recommended_target"], "release-auto-promotion-ready")

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

    def test_command_heartbeat_requires_source_package_heartbeat_capability(self) -> None:
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
                    "heartbeat_event_count": 0,
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

    def test_command_heartbeat_blocks_when_source_package_commands_bypass_heartbeat_runtime(self) -> None:
        for rel_path in (
            "ops/scripts/core/command_runtime.py",
            "ops/schemas/executor-report.schema.json",
            "ops/scripts/core/source_package_clean_extract.py",
            "ops/schemas/source-package-clean-extract.schema.json",
            "ops/reports/source-package-clean-extract.json",
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
                    "status": "attention",
                    "command_count": 4,
                    "heartbeat_enabled_command_count": 3,
                    "heartbeat_event_count": 0,
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
            "requires_release_run_verification",
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
            "ops/scripts/mechanism/goal_runtime_backoff.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "ops/scripts/mechanism/goal_runtime_certificate_report.py",
            "ops/scripts/mechanism/goal_runtime_certificate.py",
            "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
            "ops/scripts/mechanism/goal_worktree_guard.py",
            "ops/schemas/goal-worktree-guard.schema.json",
            "ops/scripts/mechanism/goal_runtime_clean_transient.py",
            "ops/schemas/goal-runtime-clean-transient.schema.json",
            "ops/scripts/mechanism/goal_runtime_run_admission.py",
            "ops/schemas/goal-runtime-run-admission.schema.json",
            "ops/scripts/mechanism/goal_runtime_quarantine_preflight.py",
            "ops/schemas/goal-runtime-quarantine-preflight.schema.json",
            "ops/scripts/mechanism/goal_runtime_stale_closeout.py",
            "ops/schemas/goal-runtime-stale-closeout.schema.json",
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
            "tests/test_goal_runtime_run_admission.py",
            "tests/test_goal_runtime_quarantine_preflight.py",
            "tests/test_goal_runtime_stale_closeout.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        mechanism_makefile = self.vault / "mk/mechanism.mk"
        mechanism_makefile.parent.mkdir(parents=True, exist_ok=True)
        mechanism_makefile.write_text(
            "goal-runtime-clean-transient:\n"
            "\tpython -m ops.scripts.goal_runtime_clean_transient\n"
            "goal-runtime-quarantine-preflight:\n"
            "\tpython -m ops.scripts.goal_runtime_quarantine_preflight --strict\n"
            "goal-runtime-stale-closeout:\n"
            "\tpython -m ops.scripts.goal_runtime_stale_closeout\n"
            "goal-runtime-run-admission-converge: goal-runtime-clean-transient auto-improve-goal-preflight\n"
            "\t$(MAKE) goal-runtime-clean-transient\n"
            "\t$(MAKE) goal-runtime-quarantine-preflight\n"
            "\t$(MAKE) goal-runtime-stale-closeout\n"
            "goal-runtime-run-admission-local-refresh: goal-runtime-lock-check goal-runtime-python-preflight\n"
            "\t$(MAKE) goal-runtime-clean-transient\n"
            "\t$(MAKE) goal-runtime-quarantine-preflight\n"
            "\t$(MAKE) goal-runtime-stale-closeout\n"
            "\t$(MAKE) goal-runtime-local-evidence-converge\n"
            "goal-runtime-run-admission: goal-runtime-run-admission-local-refresh\n"
            "\tpython -m ops.scripts.goal_runtime_run_admission --readiness-report \"$(GOAL_LOCAL_READINESS_OUT)\" --remediation-backlog-report \"$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)\" --strict\n"
            "long-run-preflight-clean: goal-runtime-run-admission-converge\n"
            "auto-improve-goal-preflight: goal-runtime-lock-check goal-runtime-python-preflight\n"
            "\tpython -m ops.scripts.goal_worktree_guard --requested-mode \"$(GOAL_WORKTREE_MODE)\" --out \"$(GOAL_WORKTREE_GUARD_OUT)\"\n"
            "goal-worktree-guard: auto-improve-goal-preflight\n",
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
                "max_proposals": 4,
                "max_consecutive_failures": 3,
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
                "observability": {
                    "command_observation_mode": "process_heartbeat",
                    "last_backoff_until": "",
                    "backoff_reason": "",
                },
            },
        )
        self._write_json(
            "ops/reports/goal-runtime-certificate.json",
            {
                "artifact_kind": "goal_runtime_certificate",
                "producer": "ops.scripts.goal_runtime_certificate_report",
                "status": "pass",
                "certificate": {
                    "target_runtime_mode": "self_improvement_loop",
                    "verification_status": "eligible",
                    "eligible": True,
                },
                "run": {
                    "run_status": "completed",
                    "run_runtime_mode": "self_improvement_loop",
                },
                "run_artifacts": {"status": "clean"},
                "session_evidence": {"status": "clean"},
                "command_observability": {"status": "clean"},
                "contract_update": {"runtime_certificate_verified_after": True},
                "blockers": [],
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
            "ops/reports/goal-worktree-guard.json",
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
        self._write_json(
            "tmp/goal-runtime-run-admission.json",
            {
                "artifact_kind": "goal_runtime_run_admission",
                "producer": "ops.scripts.goal_runtime_run_admission",
                "status": "fail",
                "decisions": {
                    "can_start_goal_runtime": False,
                    "can_mutate_candidate": False,
                    "can_promote_result_later": False,
                    "should_pause_before_run": True,
                },
            },
        )
        self._write_json(
            "tmp/goal-runtime-quarantine-preflight.json",
            {
                "artifact_kind": "goal_runtime_quarantine_preflight",
                "producer": "ops.scripts.goal_runtime_quarantine_preflight",
                "status": "pass",
                "summary": {
                    "operator_decision_required_count": 0,
                    "excluded_run_count": 1,
                    "quarantined_run_count": 1,
                    "invalid_exclusion_count": 0,
                },
            },
        )
        (self.external / "goal.md").write_text(
            "# Goal Review\n\ngoal contract, set_goal, codex_goal_prompt, --goal-contract, "
            "goal-run-status, runtime certificate, retry-after executor backoff, selected contract, Git worktree, transient artifact cleanup, "
            "goal-runtime-clean-transient, goal-runtime-quarantine-preflight, goal-runtime-stale-closeout, goal-runtime-run-admission, long-run-preflight-clean.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        for action_id in (
            "goal_contract_schema",
            "codex_goal_adapter",
            "codex_goal_prompt_generator",
            "auto_improve_goal_contract_input",
            "goal_run_status_audit_resume",
            "goal_execution_runtime_certificate",
            "goal_executor_backoff_observability",
            "selected_contract_currentness_gate",
            "git_worktree_goal_guard",
            "goal_runtime_transient_cleanup_gate",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented", action_id)
        cleanup_gate_evidence = actions["goal_runtime_transient_cleanup_gate"]["evidence"]
        self.assertFalse(
            any(item["path"].startswith("tmp/goal-runtime-") for item in cleanup_gate_evidence),
            "active report completion should depend on durable cleanup/admission surfaces, not transient tmp reports",
        )
        worktree_guard_evidence = actions["git_worktree_goal_guard"]["evidence"]
        self.assertFalse(
            any(item["path"] == "ops/reports/goal-worktree-guard.json" for item in worktree_guard_evidence),
            "active report completion should depend on durable worktree guard surfaces, not transient tmp reports",
        )
        contract["status"] = "completed"
        contract_digest = _canonical_json_digest(contract)
        self._write_json("ops/reports/codex-goal-contract.json", contract)
        prompt_report = json.loads(
            (self.vault / "ops/reports/codex-goal-prompt.json").read_text(encoding="utf-8")
        )
        prompt_report["goal_contract"]["contract_sha256"] = contract_digest
        self._write_json("ops/reports/codex-goal-prompt.json", prompt_report)

        completed_report = build_report(self.vault, context=fixed_context())
        completed_actions = {item["action_id"]: item for item in completed_report["action_items"]}
        for action_id in (
            "goal_contract_schema",
            "codex_goal_adapter",
            "auto_improve_goal_contract_input",
        ):
            self.assertEqual(completed_actions[action_id]["current_status"], "implemented", action_id)

    def test_selected_contract_gate_accepts_attention_freshness_with_current_contract(self) -> None:
        for rel_path in (
            "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
            "tests/test_auto_improve_readiness_release_authority_runtime.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_placeholder(): pass\n", encoding="utf-8")
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
                    "artifact_freshness_summary": {"status": "attention"},
                },
                "promotion_blockers": [],
            },
        )

        self.assertEqual(
            action_statuses(self.vault)["selected_contract_currentness_gate"],
            "implemented",
        )

    def test_goal_certificate_action_requires_verified_clean_certificate_report(self) -> None:
        for rel_path in (
            "mk/mechanism.mk",
            "ops/schemas/codex-goal-contract.schema.json",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_certificate_report.py",
            "ops/scripts/mechanism/goal_runtime_certificate.py",
            "tests/test_goal_runtime_certificate.py",
            "tests/test_goal_run_status.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        self._write_json(
            "ops/reports/goal-runtime-certificate.json",
            {
                "artifact_kind": "goal_runtime_certificate",
                "producer": "ops.scripts.goal_runtime_certificate_report",
                "status": "attention",
                "certificate": {
                    "target_runtime_mode": "self_improvement_loop",
                    "verification_status": "blocked",
                    "eligible": False,
                },
                "run": {
                    "run_status": "running",
                    "run_runtime_mode": "self_improvement_loop",
                },
                "run_artifacts": {"status": "incomplete"},
                "session_evidence": {"status": "missing"},
                "command_observability": {"status": "incomplete"},
                "contract_update": {"runtime_certificate_verified_after": False},
                "blockers": ["goal run is not completed"],
            },
        )
        (self.external / "certificate.md").write_text(
            "# Certificate Review\n\nruntime certificate and self-improvement loop.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["goal_execution_runtime_certificate"]["current_status"],
            "requires_release_run_verification",
        )
        goal_detail_targets = {
            target
            for item in actions["goal_execution_runtime_certificate"]["status_reason_details"]
            for target in item["recommended_targets"]
        }
        self.assertIn("goal-runtime-certificate", goal_detail_targets)
        self.assertIn("release-auto-promotion-goal-run-id-guard", goal_detail_targets)
        self.assertIn("release-auto-promotion-ready-plan", goal_detail_targets)
        self.assertNotIn("auto-improve-goal-run", goal_detail_targets)
        self.assertEqual(
            actions["goal_execution_runtime_certificate"]["blocking_scopes"],
            ["unattended_promotion"],
        )
        self.assertEqual(
            actions["goal_execution_runtime_certificate"]["gate_effects"],
            ["claim_blocker"],
        )
        self.assertEqual(
            actions["goal_execution_runtime_certificate"]["strongest_gate_effect"],
            "claim_blocker",
        )
        for detail in actions["goal_execution_runtime_certificate"]["status_reason_details"]:
            self.assertEqual(detail["blocking_scope"], "unattended_promotion")
            self.assertEqual(detail["gate_effect"], "claim_blocker")
        self.assertEqual(
            actions["goal_execution_runtime_certificate"]["recommended_target"],
            "goal-runtime-certificate",
        )

    def test_goal_prompt_action_accepts_verified_promotion_prompt_without_ban(self) -> None:
        for rel_path in (
            "ops/scripts/mechanism/codex_goal_prompt.py",
            "ops/schemas/codex-goal-prompt.schema.json",
            "tests/test_codex_goal_prompt.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        contract = {
            "$schema": "ops/schemas/codex-goal-contract.schema.json",
            "contract_id": "auto-improve-goal",
            "runtime": {
                "mode": "self_improvement_loop",
                "certificate_status": "verified",
            },
            "promotion_guard": {
                "can_promote_result": True,
                "promotion_blockers": [],
                "runtime_certificate_verified": True,
                "sustained_runtime_claimed": False,
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
                "promotion_guard": {
                    "can_promote_result": True,
                    "promotion_ban_required": False,
                    "promotion_blockers": [],
                    "runtime_certificate_verified": True,
                    "sustained_runtime_claimed": False,
                },
                "prompt": {
                    "includes_budget_limits": True,
                    "includes_allowed_roots": True,
                    "includes_sustained_claim_ban": False,
                },
            },
        )
        (self.external / "goal-prompt.md").write_text(
            "# Goal Prompt Review\n\ncodex_goal_prompt and promotion guard.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["codex_goal_prompt_generator"]["current_status"],
            "implemented",
        )

    def test_goal_status_audit_resume_action_accepts_failed_runtime_status(self) -> None:
        for rel_path in (
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "tests/test_goal_auto_improve_runtime.py",
            "tests/test_goal_run_status.py",
            "tests/test_goal_runtime_runner.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        contract = {
            "$schema": "ops/schemas/codex-goal-contract.schema.json",
            "contract_id": "auto-improve-goal",
            "runtime": {"mode": "self_improvement_loop"},
            "budgets": {"max_wall_clock_seconds": 21600},
            "required_evidence": [
                {
                    "evidence_id": "goal_run_status",
                    "path": "ops/reports/goal-run-status.json",
                    "required_for_promotion": True,
                }
            ],
        }
        contract_digest = _canonical_json_digest(contract)
        self._write_json("ops/reports/codex-goal-contract.json", contract)
        self._write_json(
            "ops/reports/goal-run-status.json",
            {
                "artifact_kind": "goal_run_status",
                "producer": "ops.scripts.goal_run_status",
                "status": "fail",
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
        (self.external / "goal-status.md").write_text(
            "# Goal Status Review\n\ngoal-run-status, audit-log, checkpoint, resume.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["goal_run_status_audit_resume"]["current_status"],
            "implemented",
        )

    def test_goal_status_audit_resume_action_accepts_missing_command_heartbeat(self) -> None:
        for rel_path in (
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "tests/test_goal_auto_improve_runtime.py",
            "tests/test_goal_run_status.py",
            "tests/test_goal_runtime_runner.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        contract = {
            "$schema": "ops/schemas/codex-goal-contract.schema.json",
            "contract_id": "auto-improve-goal",
            "runtime": {"mode": "self_improvement_loop"},
            "budgets": {"max_wall_clock_seconds": 21600},
            "required_evidence": [
                {
                    "evidence_id": "goal_run_status",
                    "path": "ops/reports/goal-run-status.json",
                    "required_for_promotion": True,
                }
            ],
        }
        contract_digest = _canonical_json_digest(contract)
        self._write_json("ops/reports/codex-goal-contract.json", contract)
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
                    "command_heartbeat_status": "not_recorded",
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
        (self.external / "goal-status.md").write_text(
            "# Goal Status Review\n\ngoal-run-status, audit-log, checkpoint, resume.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["goal_run_status_audit_resume"]["current_status"],
            "implemented",
        )

    def test_goal_status_audit_resume_action_accepts_verified_completed_runtime_status(self) -> None:
        for rel_path in (
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/scripts/mechanism/goal_runtime_runner.py",
            "tests/test_goal_auto_improve_runtime.py",
            "tests/test_goal_run_status.py",
            "tests/test_goal_runtime_runner.py",
        ):
            path = self.vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if rel_path.endswith(".json") else "def test_placeholder(): pass\n", encoding="utf-8")
        contract = {
            "$schema": "ops/schemas/codex-goal-contract.schema.json",
            "contract_id": "auto-improve-goal",
            "runtime": {
                "mode": "self_improvement_loop",
                "certificate_status": "verified",
            },
            "budgets": {"max_wall_clock_seconds": 43200},
            "required_evidence": [
                {
                    "evidence_id": "goal_run_status",
                    "path": "runs/goal-runtime/state/goal-run-status.json",
                    "required_for_promotion": True,
                }
            ],
        }
        contract_digest = _canonical_json_digest(contract)
        self._write_json("ops/reports/codex-goal-contract.json", contract)
        self._write_json(
            "ops/reports/goal-run-status.json",
            {
                "artifact_kind": "goal_run_status",
                "producer": "ops.scripts.goal_run_status",
                "status": "pass",
                "goal": {
                    "contract_sha256": contract_digest,
                    "backend": {"process_persistent": True},
                },
                "artifacts": {
                    "status_report_path": "runs/goal-runtime/state/goal-run-status.json",
                    "status_markdown_path": "runs/goal-runtime/state/status.md",
                    "audit_log_path": "runs/goal-runtime/state/audit-log.jsonl",
                    "resume_metadata_path": "runs/goal-runtime/state/resume-metadata.json",
                    "checkpoint_command_log_path": "runs/goal-runtime/state/checkpoint-command-events.jsonl",
                },
                "health": {
                    "heartbeat_status": "stale",
                    "checkpoint_status": "stale",
                    "command_heartbeat_status": "stale",
                    "backoff_status": "inactive",
                    "resume_status": "not_requested",
                    "promotion_status": "allowed",
                    "can_promote_result": True,
                },
                "runtime_certificate": {
                    "status": "complete",
                    "mode": "self_improvement_loop",
                    "certificate_status": "verified",
                    "full_gate_clean": True,
                    "promotion_blockers": [],
                },
            },
        )
        (self.external / "goal-status.md").write_text(
            "# Goal Status Review\n\ngoal-run-status, audit-log, checkpoint, resume.\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        actions = {item["action_id"]: item for item in report["action_items"]}
        self.assertEqual(
            actions["goal_run_status_audit_resume"]["current_status"],
            "implemented",
        )

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
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
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
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(
                actions[action_id]["current_status"],
                "requires_release_run_verification",
            )
            self.assertIn(
                "release_authority_status_not_verified",
                actions[action_id]["status_reason_ids"],
            )
            self.assertIn(
                "release_authority_blocker:machine_release_not_allowed",
                actions[action_id]["status_reason_ids"],
            )
            blocker_detail = {
                item["reason_id"]: item
                for item in actions[action_id]["status_reason_details"]
            }["release_authority_blocker:machine_release_not_allowed"]
            self.assertEqual(blocker_detail["owning_stage"], "release_auto_promotion_preseal")
            self.assertIn("release-evidence-dashboard", blocker_detail["recommended_targets"])

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
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented")
        self.assertEqual(actions["release_writer_dependency_single_source"]["current_status"], "implemented")

    def test_release_verified_actions_allow_non_authoritative_learning_dashboard_fail(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {
                "status": "fail",
                "summary": {
                    "live_rerun_fail_count": 1,
                    "live_rerun_not_run_count": 0,
                    "required_input_fail_count": 0,
                },
                "gates": [
                    {
                        "gate_id": "learning_delta_scoreboard_guard",
                        "authoritative_for_release": False,
                        "live_rerun_state": {"status": "fail"},
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
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(actions[action_id]["current_status"], "implemented")

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
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(
                actions[action_id]["current_status"],
                "requires_release_run_verification",
            )
            self.assertIn(
                "release_dashboard_authoritative_live_rerun_not_run",
                actions[action_id]["status_reason_ids"],
            )
            detail = {
                item["reason_id"]: item
                for item in actions[action_id]["status_reason_details"]
            }["release_dashboard_authoritative_live_rerun_not_run"]
            self.assertEqual(detail["owning_stage"], "release_auto_promotion_preseal")
            self.assertIn("release-auto-promotion-preseal", detail["recommended_targets"])

    def test_release_verified_actions_block_authoritative_dashboard_fail(self) -> None:
        self._write_release_verification_reports()
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {
                "status": "fail",
                "summary": {
                    "live_rerun_fail_count": 1,
                    "live_rerun_not_run_count": 0,
                    "required_input_fail_count": 0,
                },
                "gates": [
                    {
                        "gate_id": "authoritative_gate",
                        "authoritative_for_release": True,
                        "live_rerun_state": {"status": "fail"},
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
        for action_id in (
            "source_package_distribution_binding",
            "release_evidence_bundle_and_attestation",
            "full_suite_evidence_currentness",
            "promotion_truth_ladder",
        ):
            self.assertEqual(
                actions[action_id]["current_status"],
                "requires_release_run_verification",
            )
            self.assertIn(
                "release_dashboard_authoritative_live_rerun_fail",
                actions[action_id]["status_reason_ids"],
            )
            detail = {
                item["reason_id"]: item
                for item in actions[action_id]["status_reason_details"]
            }["release_dashboard_authoritative_live_rerun_fail"]
            self.assertEqual(detail["owning_stage"], "release_auto_promotion_preseal")
            self.assertIn("release-evidence-dashboard", detail["recommended_targets"])


if __name__ == "__main__":
    unittest.main()
