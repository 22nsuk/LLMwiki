from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.generated_artifact_index import build_report, write_report
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.external_report_action_matrix import (
    build_report as build_action_matrix_report,
)
from ops.scripts.release.external_report_inventory_runtime import (
    LOCAL_REPORT_LINE_DIGESTS,
    REFERENCE_MANIFEST,
)
from ops.scripts.release.release_closeout_fixed_point import (
    fixed_point_output_paths_at_or_downstream,
)
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_INDEX_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "generated-artifact-index.schema.json"
)
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 23, 12, 0, tzinfo=dt.UTC),
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GeneratedArtifactIndexTests(unittest.TestCase):
    def test_index_marks_current_reports_and_archive_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            graph_owned_paths = fixed_point_output_paths_at_or_downstream(
                vault,
                "generated-artifact-index-body",
            )
            for rel_path in graph_owned_paths:
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            (vault / "ops" / "operator").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "operator" / "operator-runtime-notes.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "eval-initial-2026-04-12.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (vault / "external-reports" / "current_code_review_20260423.md").write_text(
                "# current\n\nsource package, promotion_blockers, evidence bundle\n",
                encoding="utf-8",
            )
            (vault / "external-reports" / "current_code_review_20260421.md").write_text(
                "# stale current\n\nsource package\n",
                encoding="utf-8",
            )
            (vault / "external-reports" / "code_review_20260420.md").write_text(
                "# old\n\npromotion_blockers\n",
                encoding="utf-8",
            )
            (vault / "runs" / "run-20260420-old").mkdir(parents=True, exist_ok=True)
            (vault / "runs" / "run-20260420-old" / "promotion-report.json").write_text(
                json.dumps({"decision": "DISCARD", "history": {"status": "archived"}}),
                encoding="utf-8",
            )
            (vault / "runs" / "run-20260423-active").mkdir(parents=True, exist_ok=True)
            (
                vault / "runs" / "run-20260423-active" / "promotion-report.json"
            ).write_text(
                json.dumps({"decision": "PROMOTE", "history": {"status": "active"}}),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)
            schema = load_schema(
                vault / "ops" / "schemas" / "generated-artifact-index.schema.json"
            )
            envelope_schema = load_schema(ENVELOPE_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(validate_with_schema(report, envelope_schema), [])
            self.assertEqual(
                destination,
                (vault / "ops" / "reports" / "generated-artifact-index.json").resolve(),
            )
            self.assertEqual(report["status"], "attention")
            self.assertEqual(
                report["tracking_policy"]["policy_id"],
                "generated_artifact_tracking_policy",
            )
            self.assertIn("decision-grade", report["tracking_policy"]["commit_policy"])
            self.assertIn("ephemeral", report["tracking_policy"]["retention_classes"])
            self.assertIn(
                "external-reports private reference manifest and active review reports",
                report["tracking_policy"]["decision_grade_surfaces"],
            )
            self.assertTrue(report["now"])
            self.assertTrue(report["next"])
            self.assertTrue(report["why_blocked"])
            self.assertEqual(
                report["external_report_action_matrix_basis"]["status"], "missing"
            )
            self.assertEqual(report["archived_external_report_basis"], [])
            candidate_paths = {item["path"] for item in report["archive_candidates"]}
            self.assertIn("ops/reports/eval-initial-2026-04-12.json", candidate_paths)
            self.assertIn(
                "external-reports/current_code_review_20260421.md", candidate_paths
            )
            self.assertIn("external-reports/code_review_20260420.md", candidate_paths)
            self.assertIn("runs/run-20260420-old", candidate_paths)
            current_paths = {item["path"] for item in report["canonical_reports"]}
            self.assertNotIn(
                "ops/operator/operator-release-summary.json",
                current_paths,
            )
            self.assertIn("ops/operator/operator-runtime-notes.json", current_paths)
            self.assertTrue(graph_owned_paths.isdisjoint(current_paths))
            self.assertIn(
                "external-reports/current_code_review_20260423.md", current_paths
            )
            operator_report = next(
                item
                for item in report["canonical_reports"]
                if item["path"] == "ops/operator/operator-runtime-notes.json"
            )
            self.assertEqual(operator_report["surface"], "operator_reports")
            self.assertEqual(
                operator_report["decision_relevance"], "operator_reference"
            )
            archived_external = next(
                item
                for item in report["archive_candidates"]
                if item["path"] == "external-reports/current_code_review_20260421.md"
            )
            self.assertEqual(archived_external["decision_relevance"], "review_context")
            self.assertEqual(
                archived_external["superseded_by"],
                ["external-reports/current_code_review_20260423.md"],
            )

    def test_schema_requires_tracking_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            report = build_report(vault, context=fixed_context())
            invalid_report = json.loads(json.dumps(report))
            invalid_report.pop("tracking_policy")

            errors = validate_with_schema(
                invalid_report,
                load_schema(GENERATED_INDEX_SCHEMA_PATH),
            )

            self.assertIn("$: missing required property 'tracking_policy'", errors)

    def test_schema_requires_external_report_action_basis_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (
                vault / "external-reports" / "archive" / "archived_original.md"
            ).write_text(
                "# Archived\n\nsource package\n",
                encoding="utf-8",
            )
            (
                vault / "external-reports" / "active_successor_without_date.md"
            ).write_text(
                "# Successor\n\nsource package, promotion_blockers, evidence bundle\n",
                encoding="utf-8",
            )
            (vault / "external-reports" / "undated_covered_old_report.md").write_text(
                "# Old\n\nsource package\n",
                encoding="utf-8",
            )
            (
                vault / "external-reports" / "dated_unique_old_report_20260420.md"
            ).write_text(
                "# Still Unique\n\nfunction-budget\n",
                encoding="utf-8",
            )
            schema = load_schema(GENERATED_INDEX_SCHEMA_PATH)
            report = build_report(vault, context=fixed_context())
            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(
                {item["path"] for item in report["archived_external_report_basis"]},
                {"external-reports/archive/archived_original.md"},
            )

            missing_archived_basis = json.loads(json.dumps(report))
            missing_archived_basis.pop("archived_external_report_basis")
            archived_basis_errors = validate_with_schema(missing_archived_basis, schema)
            self.assertTrue(
                any(
                    "archived_external_report_basis" in error
                    for error in archived_basis_errors
                ),
                archived_basis_errors,
            )

            missing_current_basis = json.loads(json.dumps(report))
            current_external = next(
                item
                for item in missing_current_basis["canonical_reports"]
                if item["path"]
                == "external-reports/dated_unique_old_report_20260420.md"
            )
            current_external.pop("content_sha256")
            current_errors = validate_with_schema(missing_current_basis, schema)
            self.assertTrue(
                any(
                    "canonical_reports" in error and "content_sha256" in error
                    for error in current_errors
                ),
                current_errors,
            )

            missing_archive_basis = json.loads(json.dumps(report))
            archived_external = next(
                item
                for item in missing_archive_basis["archive_candidates"]
                if item["path"] == "external-reports/undated_covered_old_report.md"
            )
            archived_external.pop("archive_decision_code")
            archive_errors = validate_with_schema(missing_archive_basis, schema)
            self.assertTrue(
                any(
                    "archive_candidates" in error and "archive_decision_code" in error
                    for error in archive_errors
                ),
                archive_errors,
            )

            missing_archived_record_basis = json.loads(json.dumps(report))
            missing_archived_record_basis["archived_external_report_basis"][0].pop(
                "content_sha256"
            )
            archived_record_errors = validate_with_schema(
                missing_archived_record_basis,
                schema,
            )
            self.assertTrue(
                any(
                    "archived_external_report_basis" in error
                    and "content_sha256" in error
                    for error in archived_record_errors
                ),
                archived_record_errors,
            )

    def test_schema_keeps_action_basis_optional_for_non_external_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "runtime-health.json").write_text(
                "{}",
                encoding="utf-8",
            )
            schema = load_schema(GENERATED_INDEX_SCHEMA_PATH)
            report = build_report(vault, context=fixed_context())
            ops_report = next(
                item
                for item in report["canonical_reports"]
                if item["path"] == "ops/reports/runtime-health.json"
            )

            self.assertEqual(ops_report["surface"], "ops_reports")
            self.assertEqual(validate_with_schema(report, schema), [])

    def test_external_report_archive_lifecycle_uses_content_not_filename_dates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (vault / "external-reports" / "archive" / "legacy_source.md").write_text(
                "# Legacy Source\n\nsource package\n",
                encoding="utf-8",
            )
            (
                vault / "external-reports" / "archive" / "operator_review.pdf"
            ).write_bytes(b"%PDF-1.4\n")
            (
                vault / "external-reports" / "active_successor_without_date.md"
            ).write_text(
                "# Successor\n\nsource package, promotion_blockers, evidence bundle\n",
                encoding="utf-8",
            )
            (vault / "external-reports" / "undated_covered_old_report.md").write_text(
                "# Old\n\nsource package\n",
                encoding="utf-8",
            )
            (
                vault / "external-reports" / "dated_unique_old_report_20260420.md"
            ).write_text(
                "# Still Unique\n\nfunction-budget\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            candidate_paths = {item["path"] for item in report["archive_candidates"]}
            current_paths = {item["path"] for item in report["canonical_reports"]}
            self.assertIn(
                "external-reports/undated_covered_old_report.md", candidate_paths
            )
            self.assertIn(
                "external-reports/dated_unique_old_report_20260420.md", current_paths
            )
            self.assertIn(
                "external-reports/active_successor_without_date.md", current_paths
            )
            unique_external = next(
                item
                for item in report["canonical_reports"]
                if item["path"]
                == "external-reports/dated_unique_old_report_20260420.md"
            )
            self.assertEqual(unique_external["report_type"], "narrative_report")
            self.assertEqual(
                unique_external["content_sha256"],
                _sha256_file(
                    vault / "external-reports" / "dated_unique_old_report_20260420.md"
                ),
            )
            self.assertEqual(unique_external["matched_action_count"], 1)
            self.assertEqual(unique_external["unmatched_recommendation_count"], 0)
            self.assertEqual(unique_external["operator_only_rationale"], "")
            self.assertEqual(
                unique_external["archive_decision_code"],
                "unresolved_actions_keep_report_active",
            )
            self.assertEqual(
                unique_external["unresolved_action_ids"],
                ["function_budget_proposal_adapter"],
            )
            self.assertEqual(unique_external["unresolved_action_count"], 1)
            self.assertIn(
                "function_budget_proposal_adapter",
                unique_external["reason"],
            )
            archived_external = next(
                item
                for item in report["archive_candidates"]
                if item["path"] == "external-reports/undated_covered_old_report.md"
            )
            self.assertEqual(
                archived_external["archive_decision_code"],
                "unresolved_actions_covered_by_broader_report",
            )
            self.assertEqual(
                archived_external["superseded_by"],
                ["external-reports/active_successor_without_date.md"],
            )
            self.assertIn(
                "no unique unresolved action themes", archived_external["reason"]
            )
            self.assertEqual(
                archived_external["unresolved_action_ids"],
                ["source_package_distribution_binding"],
            )
            archived_basis = {
                item["path"]: item for item in report["archived_external_report_basis"]
            }
            self.assertEqual(
                set(archived_basis),
                {
                    "external-reports/archive/legacy_source.md",
                    "external-reports/archive/operator_review.pdf",
                },
            )
            legacy_basis = archived_basis["external-reports/archive/legacy_source.md"]
            self.assertEqual(
                legacy_basis["content_sha256"],
                _sha256_file(
                    vault / "external-reports" / "archive" / "legacy_source.md"
                ),
            )
            self.assertIn(
                "source_package_distribution_binding",
                legacy_basis["matched_action_ids"],
            )
            self.assertEqual(legacy_basis["unmatched_recommendation_count"], 0)
            self.assertNotIn("reason", legacy_basis)
            self.assertNotIn("superseded_by", legacy_basis)
            operator_basis = archived_basis[
                "external-reports/archive/operator_review.pdf"
            ]
            self.assertEqual(operator_basis["report_type"], "binary_report")
            self.assertEqual(
                operator_basis["operator_only_rationale"],
                "binary_report_requires_operator_review",
            )
            self.assertEqual(
                operator_basis["archive_decision_code"],
                "binary_report_requires_operator_review",
            )

    def test_external_report_archive_lifecycle_closes_implemented_action_reports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "script-output-surfaces.json").write_text(
                "{}", encoding="utf-8"
            )
            (vault / "external-reports" / "closed_undated_report.md").write_text(
                "# Closed\n\nscript-output-surfaces\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            archived_external = next(
                item
                for item in report["archive_candidates"]
                if item["path"] == "external-reports/closed_undated_report.md"
            )
            self.assertIn(
                "implemented in canonical evidence", archived_external["reason"]
            )

    def test_external_report_archive_lifecycle_uses_current_action_matrix_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (
                vault / "external-reports" / "closed_release_evidence_report.md"
            ).write_text(
                "# Closed\n\nevidence bundle\n",
                encoding="utf-8",
            )
            action_matrix = build_action_matrix_report(vault, context=fixed_context())
            action_matrix["action_items"] = [
                {
                    "action_id": "release_evidence_bundle_and_attestation",
                    "current_status": "implemented",
                }
            ]
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (
                vault / "ops" / "reports" / "external-report-action-matrix.json"
            ).write_text(
                json.dumps(action_matrix),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            candidate_paths = {item["path"] for item in report["archive_candidates"]}
            self.assertIn(
                "external-reports/closed_release_evidence_report.md", candidate_paths
            )
            self.assertEqual(
                report["external_report_action_matrix_basis"]["status"], "current"
            )
            self.assertIn(
                "external_report_action_matrix_statuses",
                report["input_fingerprints"],
            )

    def test_external_report_lifecycle_rejects_stale_action_matrix_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (
                vault / "ops" / "reports" / "external-report-action-matrix.json"
            ).write_text(
                json.dumps(
                    {
                        "artifact_kind": "external_report_action_matrix",
                        "artifact_status": "current",
                        "currentness": {"status": "current"},
                        "source_revision": "old-revision",
                        "source_tree_fingerprint": "old-fingerprint",
                        "action_items": [
                            {
                                "action_id": "release_evidence_bundle_and_attestation",
                                "current_status": "implemented",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (
                vault / "external-reports" / "closed_release_evidence_report.md"
            ).write_text(
                "# Closed\n\nevidence bundle\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            self.assertEqual(
                report["external_report_action_matrix_basis"]["status"],
                "source_identity_mismatch",
            )
            self.assertEqual(
                report["external_report_action_matrix_basis"]["reason_id"],
                "action_matrix_source_tree_fingerprint_mismatch",
            )
            candidate_paths = {item["path"] for item in report["archive_candidates"]}
            current_paths = {item["path"] for item in report["canonical_reports"]}
            self.assertNotIn(
                "external-reports/closed_release_evidence_report.md", candidate_paths
            )
            self.assertIn(
                "external-reports/closed_release_evidence_report.md", current_paths
            )
            self.assertEqual(
                validate_with_schema(report, load_schema(GENERATED_INDEX_SCHEMA_PATH)),
                [],
            )

    def test_external_report_lifecycle_accepts_revision_alias_for_same_source_tree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            action_matrix = build_action_matrix_report(vault, context=fixed_context())
            action_matrix["source_revision"] = "previous-revision-same-tree"
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (
                vault / "ops" / "reports" / "external-report-action-matrix.json"
            ).write_text(
                json.dumps(action_matrix),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            basis = report["external_report_action_matrix_basis"]

            self.assertEqual(basis["status"], "current")
            self.assertEqual(basis["reason_id"], "action_matrix_basis_current")
            self.assertEqual(basis["source_revision_status"], "provenance_only")
            self.assertEqual(
                validate_with_schema(report, load_schema(GENERATED_INDEX_SCHEMA_PATH)),
                [],
            )

    def test_external_report_lifecycle_rejects_input_stale_action_matrix_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports" / "archive").mkdir(parents=True, exist_ok=True)
            (
                vault / "external-reports" / "closed_release_evidence_report.md"
            ).write_text(
                "# Closed\n\nevidence bundle\n",
                encoding="utf-8",
            )
            action_matrix = build_action_matrix_report(vault, context=fixed_context())
            action_matrix["action_items"] = [
                {
                    "action_id": "release_evidence_bundle_and_attestation",
                    "current_status": "implemented",
                }
            ]
            action_matrix["input_fingerprints"] = {
                **action_matrix["input_fingerprints"],
                "action_catalog": "stale-fingerprint",
            }
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (
                vault / "ops" / "reports" / "external-report-action-matrix.json"
            ).write_text(
                json.dumps(action_matrix),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            self.assertEqual(
                report["external_report_action_matrix_basis"]["status"], "stale"
            )
            self.assertEqual(
                report["external_report_action_matrix_basis"]["reason_id"],
                "action_matrix_input_fingerprint_mismatch",
            )
            self.assertEqual(
                report["external_report_action_matrix_basis"][
                    "input_fingerprint_mismatch_keys"
                ],
                ["action_catalog"],
            )
            candidate_paths = {item["path"] for item in report["archive_candidates"]}
            current_paths = {item["path"] for item in report["canonical_reports"]}
            self.assertNotIn(
                "external-reports/closed_release_evidence_report.md", candidate_paths
            )
            self.assertIn(
                "external-reports/closed_release_evidence_report.md", current_paths
            )
            self.assertEqual(
                validate_with_schema(report, load_schema(GENERATED_INDEX_SCHEMA_PATH)),
                [],
            )

    def test_index_summary_and_input_fingerprints_track_task_improvement_observations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            baseline_report = build_report(vault, context=fixed_context())

            task_dir = (
                vault
                / "ops"
                / "reports"
                / "task-improvement-observations"
                / "task-demo"
            )
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "improvement-observations.json").write_text(
                "{}", encoding="utf-8"
            )

            updated_report = build_report(vault, context=fixed_context())

            self.assertIn(
                "task_improvement_observation_inventory",
                baseline_report["input_fingerprints"],
            )
            self.assertEqual(
                baseline_report["summary"]["task_improvement_observation_count"], 0
            )
            self.assertEqual(
                updated_report["summary"]["task_improvement_observation_count"], 1
            )
            self.assertNotEqual(
                baseline_report["input_fingerprints"][
                    "task_improvement_observation_inventory"
                ],
                updated_report["input_fingerprints"][
                    "task_improvement_observation_inventory"
                ],
            )

    def test_ops_report_fingerprint_tracks_inventory_semantics_not_observation_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            reports_dir = vault / "ops" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "artifact-freshness-report.json").write_text(
                json.dumps({"observed": "first"}),
                encoding="utf-8",
            )
            (reports_dir / "test-execution-summary.json").write_text(
                json.dumps({"observed": "first"}),
                encoding="utf-8",
            )

            baseline_report = build_report(vault, context=fixed_context())

            (reports_dir / "artifact-freshness-report.json").write_text(
                json.dumps({"observed": "second", "content_only": True}),
                encoding="utf-8",
            )
            (reports_dir / "test-execution-summary.json").write_text(
                json.dumps({"observed": "second", "content_only": True}),
                encoding="utf-8",
            )

            content_changed_report = build_report(vault, context=fixed_context())

            self.assertIn("ops_report_inventory", baseline_report["input_fingerprints"])
            self.assertNotIn("ops_report_files", baseline_report["input_fingerprints"])
            self.assertEqual(
                baseline_report["input_fingerprints"]["ops_report_inventory"],
                content_changed_report["input_fingerprints"]["ops_report_inventory"],
            )

            (reports_dir / "eval-initial-2026-04-12.json").write_text(
                "{}", encoding="utf-8"
            )
            inventory_changed_report = build_report(vault, context=fixed_context())

            self.assertNotEqual(
                baseline_report["input_fingerprints"]["ops_report_inventory"],
                inventory_changed_report["input_fingerprints"]["ops_report_inventory"],
            )

    def test_external_report_fingerprint_tracks_content_lifecycle_semantics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports").mkdir(exist_ok=True)
            report_path = vault / "external-reports" / "active_report.md"
            report_path.write_text("# Active\n\nsource package\n", encoding="utf-8")

            baseline_report = build_report(vault, context=fixed_context())

            report_path.write_text(
                "# Active\n\nsource package, function-budget\n", encoding="utf-8"
            )
            updated_report = build_report(vault, context=fixed_context())

            self.assertIn(
                "external_report_inventory", baseline_report["input_fingerprints"]
            )
            self.assertNotEqual(
                baseline_report["input_fingerprints"]["external_report_inventory"],
                updated_report["input_fingerprints"]["external_report_inventory"],
            )

    def test_written_index_remains_equal_to_regenerated_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                "{}", encoding="utf-8"
            )
            (vault / "ops" / "reports" / "generated-artifact-index.json").write_text(
                "{}", encoding="utf-8"
            )

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)
            reloaded = json.loads(destination.read_text(encoding="utf-8"))
            regenerated = build_report(vault, context=fixed_context())

            self.assertEqual(regenerated, reloaded)

    def test_index_surfaces_run_artifact_load_issues_in_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "runs" / "run-20260423-active").mkdir(parents=True, exist_ok=True)
            (
                vault / "runs" / "run-20260423-active" / "promotion-report.json"
            ).write_text(
                "{not-json",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            run_record = next(
                item
                for item in report["canonical_reports"]
                if item["path"] == "runs/run-20260423-active"
            )
            self.assertIn("promotion-report.json:decode_error", run_record["reason"])
            self.assertIn("run-ledger.json:missing", run_record["reason"])

    def test_external_report_manifest_is_not_labeled_as_review_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / REFERENCE_MANIFEST).write_text(
                json.dumps(
                    {
                        "references": [],
                        "summary": {"active_reference_set_status": "current"},
                    }
                ),
                encoding="utf-8",
            )
            (vault / LOCAL_REPORT_LINE_DIGESTS).write_text("{}", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

            manifest_record = next(
                item
                for item in report["canonical_reports"]
                if item["path"] == REFERENCE_MANIFEST
            )
            external_rule = next(
                item
                for item in report["archive_rules"]
                if item["surface"] == "external_reports"
            )
            self.assertEqual(manifest_record["role"], "current_reference_manifest")
            self.assertIn("private reference manifest", external_rule["canonical_rule"])
            self.assertNotIn("current review report", json.dumps(manifest_record))
            indexed_paths = {
                item["path"]
                for item in [
                    *report["canonical_reports"],
                    *report["archive_candidates"],
                ]
            }
            self.assertNotIn(LOCAL_REPORT_LINE_DIGESTS, indexed_paths)
            self.assertEqual(
                validate_with_schema(report, load_schema(GENERATED_INDEX_SCHEMA_PATH)),
                [],
            )


if __name__ == "__main__":
    unittest.main()
