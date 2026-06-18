from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.core.gate_effect_vocabulary import strongest_gate_effect
from ops.scripts.core.generated_artifact_index import (
    build_report as build_generated_artifact_index_report,
    write_report as write_generated_artifact_index_report,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.mechanism.goal_contract_digest_runtime import (
    semantic_goal_contract_digest,
)
from ops.scripts.release.external_report_action_matrix import (
    _active_action_resolution_summary,
    _reason_detail_summary,
    build_report,
    write_report,
)
from ops.scripts.release.external_report_lifecycle_runtime import (
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
from ops.scripts.release.release_closeout_finality_attestation import (
    BATCH_MANIFEST_PATH,
    DEFAULT_OUT as FINALITY_ATTESTATION_PATH,
    FIXED_POINT_REPORT_PATH,
    SELF_CHECK_PATH,
    build_report as build_finality_attestation_report,
    write_report as write_finality_attestation,
)
from ops.scripts.release.review_archive import CLEAN_SOURCE_COMMAND
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault
from tests.runtime_test_context import frozen_context

_PUBLIC_REEXPORTS = (
    action_status_reason_details,
    action_statuses,
    archive_reconciliation_observation_inventory,
    build_generated_artifact_index_report,
    build_report,
    collaboration_governance_surface_reason_ids,
    coverage_action_basis,
    coverage_with_action_basis,
    lifecycle_decision,
    load_schema,
    report_coverage_item,
    report_lifecycle_profiles,
    strongest_gate_effect,
    validate_with_schema,
    write_generated_artifact_index_report,
    write_report,
    _active_action_resolution_summary,
    _reason_detail_summary,
)

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "external-report-action-matrix.schema.json"
EXTERNAL_REPORT_FIXTURE_SCHEMA_NAMES = frozenset(
    {
        "artifact-envelope.schema.json",
        "codex-goal-contract.schema.json",
        "codex-goal-prompt.schema.json",
        "executor-report.schema.json",
        "generated-artifact-index.schema.json",
        "goal-run-status.schema.json",
        "goal-runtime-clean-transient.schema.json",
        "goal-runtime-quarantine-preflight.schema.json",
        "goal-runtime-run-admission.schema.json",
        "goal-runtime-stale-closeout.schema.json",
        "goal-worktree-guard.schema.json",
        "release-authority-inventory.schema.json",
        "release-closeout-finality-attestation.schema.json",
        "release-closeout-sealed-rehearsal-check.schema.json",
        "release-closeout-summary.schema.json",
        "remediation-backlog.schema.json",
        "review-archive-report.schema.json",
        "self-improvement-negative-lessons.schema.json",
        "source-package-clean-extract.schema.json",
        "strict-lint-inventory.schema.json",
        "strict-type-inventory.schema.json",
        "wiki-maintainer-policy.schema.json",
    }
)


def fixed_context() -> RuntimeContext:
    return frozen_context(dt.datetime(2026, 5, 10, 8, 30, tzinfo=dt.UTC))


def _canonical_json_digest(payload: dict) -> str:
    return semantic_goal_contract_digest(payload)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()




class ExternalReportActionMatrixTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault, schema_names=EXTERNAL_REPORT_FIXTURE_SCHEMA_NAMES)
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
    def _actions_by_id(self, report: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["action_id"]: item for item in report["action_items"]}
    def _write_clean_review_archive_report(self) -> None:
        timestamp = "2026-05-10T08:30:00Z"
        manifest_digest = "a" * 64
        file_digest = "b" * 64
        manifest = {
            "files": [
                {
                    "path": "README.md",
                    "sha256": file_digest,
                    "size_bytes": 1,
                }
            ]
        }
        self._write_json(
            "ops/reports/review-archive-report.json",
            {
                "$schema": "ops/schemas/review-archive-report.schema.json",
                "vault": ".",
                "generated_at": timestamp,
                "artifact_kind": "review_archive_report",
                "producer": "ops.scripts.review_archive",
                "source_command": CLEAN_SOURCE_COMMAND,
                "source_revision": "source_package_without_git",
                "source_tree_fingerprint": "c" * 64,
                "input_fingerprints": {
                    "artifact_envelope_schema": "d" * 64,
                    "policy": "e" * 64,
                    "schema": "f" * 64,
                    "source_paths": "0" * 64,
                },
                "schema_version": 1,
                "artifact_status": "current",
                "retention_policy": "canonical_report",
                "encoding": "utf-8",
                "currentness": {"status": "current", "checked_at": timestamp},
                "policy": {
                    "path": "ops/policies/wiki-maintainer-policy.yaml",
                    "version": 1,
                },
                "profile": "clean",
                "status": "pass",
                "archive_path": "build/review/llm-wiki-vnext-review.zip",
                "archive_file": {
                    "path": "build/review/llm-wiki-vnext-review.zip",
                    "exists": True,
                    "size_bytes": 1,
                    "sha256": "1" * 64,
                },
                "packed_file_count": 1,
                "manifest": manifest,
                "manifest_digest": manifest_digest,
                "archive_manifest": manifest,
                "archive_manifest_digest": manifest_digest,
                "archive_timestamp_normalization": {
                    "status": "pass",
                    "timestamp_semantics": "normalized_archive_timestamp",
                    "expected_timestamp_utc": "1980-01-01T00:00:00Z",
                    "observed_timestamp_count": 1,
                    "observed_min_timestamp_utc": "1980-01-01T00:00:00Z",
                    "observed_max_timestamp_utc": "1980-01-01T00:00:00Z",
                    "mismatch_count": 0,
                    "mismatch_paths": [],
                },
                "current_snapshot_representativeness": {
                    "status": "representative",
                    "representative_of_current_tree": True,
                    "representative_of_current_zip": True,
                    "checked_at": timestamp,
                    "current_manifest_digest": manifest_digest,
                    "archive_manifest_digest": manifest_digest,
                    "next_action": "none",
                },
                "snapshot_hygiene": {
                    "profile": "clean",
                    "status": "pass",
                    "enforced": True,
                    "forbidden_count": 0,
                    "forbidden_paths": [],
                    "rules": [
                        "tmp/**/*.candidate.json",
                        "public-surface __pycache__ directories",
                        "public-surface *.pyc files",
                    ],
                    "summary": "clean profile enforced; forbidden_count=0",
                },
                "exclusion_policy": "public_surface_policy",
                "excluded_prefixes": ["raw/", "runs/", "wiki/"],
                "excluded_files": ["AGENTS.local.md"],
            },
        )
    def _write_schema_invalid_clean_review_archive_report(self) -> None:
        self._write_json(
            "ops/reports/review-archive-report.json",
            {
                "artifact_kind": "review_archive_report",
                "producer": "ops.scripts.review_archive",
                "source_command": CLEAN_SOURCE_COMMAND,
                "artifact_status": "current",
                "currentness": {"status": "current"},
                "profile": "clean",
                "status": "pass",
                "archive_file": {"exists": True, "sha256": "b" * 64},
                "exclusion_policy": "public_surface_policy",
                "manifest_digest": "a" * 64,
                "archive_manifest_digest": "a" * 64,
                "snapshot_hygiene": {
                    "profile": "clean",
                    "status": "pass",
                    "enforced": True,
                    "forbidden_count": 0,
                    "forbidden_paths": [],
                },
                "current_snapshot_representativeness": {
                    "status": "representative",
                    "representative_of_current_tree": True,
                    "representative_of_current_zip": True,
                    "next_action": "none",
                },
            },
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
        stale_routing: dict | None = None,
    ) -> dict:
        payload = {
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
        if stale_routing is not None:
            payload["stale_routing"] = stale_routing
        return payload

    def _artifact_freshness_state(
        self,
        *,
        artifact_count: int,
        stale_artifact_count: int,
        operational_attention_artifact_count: int,
        stale_routing: dict | None = None,
    ) -> dict:
        state = {
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
        if stale_routing is not None:
            state["stale_routing"] = stale_routing
        return state

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
