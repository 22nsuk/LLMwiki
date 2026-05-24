from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.external_report_action_matrix import build_report, write_report
from ops.scripts.external_report_lifecycle_runtime import (
    action_statuses,
    lifecycle_decision,
    report_lifecycle_profiles,
)
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

    def test_generated_artifact_policy_status_is_not_self_blocked_by_archive_candidates(self) -> None:
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

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["summary"]["active_report_count"], 2)
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
        self.assertNotIn("external-reports/report-reference-manifest.json", paths)
        self.assertFalse(any("/archive/" in path for path in paths))
        actions = {item["action_id"]: item for item in report["action_items"]}
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
        self_evidence = [
            item
            for item in actions["external_report_lifecycle"]["evidence"]
            if item["path"] == "ops/reports/external-report-action-matrix.json"
        ][0]
        self.assertEqual(self_evidence["status"], report["status"])
        self.assertEqual(self_evidence["producer"], "ops.scripts.external_report_action_matrix")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_reassessment_actions_are_classified_from_current_source_contracts(self) -> None:
        for rel_path, text in {
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py": (
                "from .set_mechanism_run_history import (\n"
                "    MechanismRunRecord,\n"
                ")\n"
            ),
            "tools/ruff_strict_preview.py": "def main(): pass\n",
            "ops/ruff-strict-preview-allowlist.txt": (
                "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py\n"
            ),
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
                "RUFF_STRICT_PREVIEW_ALLOWLIST ?= ops/ruff-strict-preview-allowlist.txt\n"
                "STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools\n"
                "ruff-strict-preview:\n"
                "\tpython tools/ruff_strict_preview.py\n"
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
            "strict-preview allowlist all-target ops/scripts tests tools audit.\n",
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
            "goal-runtime-run-admission-converge: goal-runtime-clean-transient auto-improve-goal-preflight\n"
            "\t$(MAKE) goal-runtime-clean-transient\n"
            "\t$(MAKE) goal-runtime-quarantine-preflight\n"
            "goal-runtime-run-admission-local-refresh: goal-runtime-lock-check goal-runtime-python-preflight\n"
            "\t$(MAKE) goal-runtime-clean-transient\n"
            "\t$(MAKE) goal-runtime-quarantine-preflight\n"
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
            "goal-runtime-clean-transient, goal-runtime-quarantine-preflight, goal-runtime-run-admission, long-run-preflight-clean.\n",
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
            "goal_execution_runtime_certificate",
            "goal_executor_backoff_observability",
            "selected_contract_currentness_gate",
            "git_worktree_goal_guard",
            "goal_runtime_transient_cleanup_gate",
        }:
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
        for action_id in {
            "goal_contract_schema",
            "codex_goal_adapter",
            "auto_improve_goal_contract_input",
        }:
            self.assertEqual(completed_actions[action_id]["current_status"], "implemented", action_id)

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
