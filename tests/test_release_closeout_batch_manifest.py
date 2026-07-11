from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.eval.wiki_manifest import release_manifest_excludes_path
from ops.scripts.release.release_audit_pack import build_audit_pack
from ops.scripts.release.release_closeout_batch_manifest import (
    ARCHIVE_SELF_DESCRIPTION_PATH,
    BATCH_MANIFEST_SOURCE_PATHS,
    FINALITY_ATTESTATION_PATH,
    BatchArtifactInventory,
    ReleaseDecisionInputs,
    _batch_manifest_render_inputs,
    _batch_status_decision,
    _load_batch_manifest_sources,
    _prepare_batch_manifest_state,
    _render_batch_manifest_report,
    build_batch_manifest,
    main,
    write_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [
    pytest.mark.public,
    pytest.mark.release_sealing,
    pytest.mark.release_sealing_core,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
BATCH_MANIFEST_SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "release-closeout-batch-manifest.schema.json"
)
BATCH_POLICY_PATH = REPO_ROOT / "ops" / "policies" / "release-closeout-batch.json"
FIXED_POINT_POLICY_PATH = (
    REPO_ROOT / "ops" / "policies" / "release-closeout-fixed-point.json"
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 2, 9, 0, tzinfo=dt.UTC),
    )


def context_at(value: dt.datetime) -> RuntimeContext:
    return RuntimeContext(display_timezone=dt.UTC, clock=lambda: value)


def complete_inventory() -> BatchArtifactInventory:
    return BatchArtifactInventory(
        artifacts=[],
        present_count=1,
        current_count=1,
        required_present_count=1,
        required_current_count=1,
        required_count=1,
    )


def release_inputs(**overrides: Any) -> ReleaseDecisionInputs:
    payload: dict[str, Any] = {
        "release_readiness_state": "clean_pass",
        "release_authority_status": "clean_pass",
        "semantic_release_status": "clean_pass",
        "closeout_sealed_release_status": "sealed_clean_pass",
        "status_v2_blocker_reason_ids": [],
        "status_v2_used_legacy_fallback_fields": [],
        "clean_release_ready": True,
        "machine_release_allowed": True,
        "artifact_freshness_status": "pass",
        "artifact_freshness_schema_invalid_count": 0,
        "accepted_risk_family_count": 0,
        "accepted_risk_count": 0,
        "gate_attention_count": 0,
        "learning_lane_status": "pass",
        "auto_improve_lane_status": "pass",
        "learning_claim_guard_status": "pass",
        "learning_claim_allowed": False,
        "claims_learning_improved": False,
        "learning_claim_blocking_family_count": 0,
        "advisory_lifecycle_family_count": 0,
        "accepted_risks": [],
        "source_tree_coherence_status": "pass",
    }
    payload.update(overrides)
    if "release_authority_status" not in overrides:
        payload["release_authority_status"] = payload["release_readiness_state"]
    if "semantic_release_status" not in overrides:
        payload["semantic_release_status"] = payload["release_authority_status"]
    return ReleaseDecisionInputs(**payload)


def materialized_distribution() -> dict[str, Any]:
    return {
        "status": "materialized",
        "path_set_matches_release_manifest": True,
        "content_digest_matches_release_manifest": True,
    }


class ReleaseCloseoutBatchManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        # Copy batch policy into vault so the script can read it
        batch_policy_dest = (
            self.vault / "ops" / "policies" / "release-closeout-batch.json"
        )
        batch_policy_dest.parent.mkdir(parents=True, exist_ok=True)
        batch_policy_dest.write_text(
            BATCH_POLICY_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )
        fixed_point_policy_dest = (
            self.vault / "ops" / "policies" / "release-closeout-fixed-point.json"
        )
        fixed_point_policy_dest.write_text(
            FIXED_POINT_POLICY_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )

    def test_source_paths_include_shared_finality_diagnostics(self) -> None:
        self.assertEqual(
            BATCH_MANIFEST_SOURCE_PATHS,
            [
                "ops/scripts/release/release_closeout_batch_manifest.py",
                "ops/scripts/release/finality_current_diagnostics.py",
            ],
        )
        for rel_path in BATCH_MANIFEST_SOURCE_PATHS:
            self.assertTrue((REPO_ROOT / rel_path).is_file(), rel_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_artifact(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_required_artifacts(self, *, currentness_status: str = "current") -> None:
        base_artifact = {
            "artifact_kind": "test_report",
            "generated_at": "2026-05-02T08:00:00Z",
            "producer": "test",
            "source_tree_fingerprint": "abc",
            "currentness": {"status": currentness_status},
        }
        for artifact_path in [
            "ops/reports/release-smoke-report.json",
            "ops/reports/source-package-clean-extract.json",
            "external-reports/report-reference-manifest.json",
            "ops/reports/generated-artifact-index.json",
            "ops/reports/artifact-freshness-report.json",
            "ops/reports/test-execution-summary.json",
            "ops/reports/test-execution-summary-full.json",
            "ops/reports/learning-readiness-signoff-revalidation.json",
            "ops/reports/learning-delta-scoreboard.json",
            "ops/reports/release-evidence-cohort.json",
            "ops/reports/release-evidence-dashboard.json",
            "ops/reports/release-lane-summary.json",
            "ops/reports/release-clean-blocker-ledger.json",
        ]:
            payload = dict(base_artifact)
            if artifact_path == "ops/reports/release-evidence-dashboard.json":
                payload["summary"] = {
                    "accepted_risk_count": 0,
                    "gate_attention_count": 0,
                }
            if artifact_path == "ops/reports/release-lane-summary.json":
                payload["lane_summary"] = {
                    "auto_improve_lane_status": "pass",
                    "learning_lane_status": "pass",
                    "learning_claim_guard_status": "pass",
                    "learning_claim_allowed": False,
                    "claims_learning_improved": False,
                    "accepted_risk_count": 0,
                    "gate_attention_count": 0,
                    "learning_claim_blocking_family_count": 0,
                    "advisory_lifecycle_family_count": 0,
                }
            self._write_artifact(artifact_path, payload)

    def _write_closeout_summary(self, **overrides: Any) -> None:
        payload = {
            "status": "pass",
            "clean_release_ready": True,
            "machine_release_allowed": True,
            "release_readiness_state": "clean_pass",
            "artifact_freshness_gate": {
                "path": "ops/reports/artifact-freshness-report.json",
                "load_status": "ok",
                "status": "pass",
                "ready": True,
                "schema_invalid_artifact_count": 0,
                "stable_contract_debt_issue_count": 0,
                "gate_effect": "none",
                "display_effect": "none",
                "blocking": False,
            },
            "summary": {"accepted_risk_family_count": 0},
            "currentness": {"status": "current"},
        }
        payload.update(overrides)
        self._write_artifact("ops/reports/release-closeout-summary.json", payload)

    def _write_release_source_zip(
        self,
        rel_path: str = "tmp/release.zip",
        *,
        timestamp: tuple[int, int, int, int, int, int] = (2026, 5, 2, 9, 0, 0),
    ) -> Path:
        archive_path = self.vault / rel_path
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w") as archive:
            for path in sorted(self.vault.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                source_rel = path.relative_to(self.vault).as_posix()
                if source_rel == rel_path or release_manifest_excludes_path(source_rel):
                    continue
                info = zipfile.ZipInfo(f"LLMwiki-source/{source_rel}", timestamp)
                archive.writestr(info, path.read_bytes())
        return archive_path

    @pytest.mark.release_closeout_regression
    def test_batch_manifest_finality_points_to_attestation_without_digest_ownership(
        self,
    ) -> None:
        self._write_required_artifacts()
        self._write_closeout_summary()

        report = build_batch_manifest(self.vault, context=fixed_context())

        self.assertEqual(report["finality"]["finality_required"], True)
        self.assertEqual(
            report["finality"]["finality_attestation_path"], FINALITY_ATTESTATION_PATH
        )
        self.assertEqual(
            report["finality"]["binding_authority"],
            "release-closeout-finality-attestation",
        )
        self.assertNotIn("report_digest", report["finality"])
        self.assertNotIn("report_path", report["finality"])
        self.assertNotIn("converged", report["finality"])
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_build_batch_manifest_matches_explicit_load_prepare_render_pipeline(
        self,
    ) -> None:
        self._write_required_artifacts()
        self._write_closeout_summary()
        context = fixed_context()

        report = build_batch_manifest(self.vault, context=context)
        loaded = _load_batch_manifest_sources(self.vault)
        prepared = _prepare_batch_manifest_state(
            self.vault,
            loaded,
            generated_at=context.isoformat_z(),
        )
        explicit_pipeline_report = _render_batch_manifest_report(
            _batch_manifest_render_inputs(self.vault, loaded, prepared)
        )

        self.assertEqual(explicit_pipeline_report, report)

    def test_status_decision_marks_clean_authority_and_sealed_distribution_pass(
        self,
    ) -> None:
        decision = _batch_status_decision(
            complete_inventory(),
            release_inputs(),
            materialized_distribution(),
        )

        self.assertEqual(decision.status, "pass")
        self.assertEqual(decision.batch_integrity_status, "pass")
        self.assertEqual(decision.release_authority_status, "clean_pass")
        self.assertEqual(decision.sealed_release_status, "sealed_clean_pass")
        self.assertEqual(
            decision.status_v2["status_classification"], "strict_clean_and_sealed"
        )

    def test_status_decision_keeps_conditional_authority_out_of_legacy_pass(
        self,
    ) -> None:
        decision = _batch_status_decision(
            complete_inventory(),
            release_inputs(
                release_readiness_state="conditional_pass",
                clean_release_ready=False,
                machine_release_allowed=False,
            ),
            materialized_distribution(),
        )

        self.assertEqual(decision.status, "fail")
        self.assertEqual(decision.batch_integrity_status, "pass")
        self.assertEqual(decision.release_authority_status, "conditional_pass")
        self.assertEqual(decision.sealed_release_status, "sealed_conditional_pass")
        self.assertEqual(
            decision.status_v2["status_classification"], "conditional_release"
        )

    def test_batch_manifest_marks_unsealed_when_distribution_zip_not_provided(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()

        report = build_batch_manifest(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["batch_integrity_status"], "pass")
        self.assertEqual(report["release_authority_status"], "clean_pass")
        self.assertEqual(report["semantic_release_status"], "clean_pass")
        self.assertEqual(
            report["sealed_release_status"], "unsealed_distribution_not_provided"
        )
        self.assertEqual(report["distribution_package"]["status"], "not_provided")
        self.assertEqual(
            report["release_authority_vocabulary"]["blocker_reason_ids"],
            [
                "sealed_release_not_clean_pass",
                "distribution_package_not_materialized",
            ],
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["operator_summary_round_trip"][
                "status"
            ],
            "pass",
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["operator_summary_round_trip"][
                "parsed"
            ]["sealed_release_status"],
            "unsealed_distribution_not_provided",
        )
        self.assertEqual(report["external_source_zip_bound"]["status"], "not_bound")
        self.assertEqual(
            report["external_source_zip_bound"]["release_authority_status"],
            "clean_pass",
        )
        self.assertEqual(report["artifact_generation_status"], "pass")
        self.assertEqual(report["artifact_digest_sealing_status"], "pass")
        self.assertEqual(report["clean_lane_status"], "pass")
        self.assertEqual(report["auto_improve_lane_status"], "pass")
        self.assertEqual(report["learning_lane_status"], "pass")
        self.assertEqual(report["machine_release_status"], "allowed")
        self.assertEqual(report["operator_release_status"], "allowed")
        self.assertEqual(
            report["release_decision_snapshot"]["learning_lane_status"], "pass"
        )
        self.assertEqual(
            report["release_decision_snapshot"]["auto_improve_lane_status"], "pass"
        )
        self.assertEqual(
            report["release_decision_snapshot"]["learning_claim_allowed"], False
        )
        self.assertEqual(report["release_decision_snapshot"]["accepted_risk_count"], 0)
        self.assertEqual(report["release_decision_snapshot"]["gate_attention_count"], 0)
        self.assertTrue(report["coherence"]["all_required_present"])
        self.assertTrue(report["coherence"]["all_required_current"])
        self.assertEqual(report["summary"]["present_count"], 14)
        self.assertEqual(report["summary"]["current_count"], 14)

    def test_distribution_zip_retires_nonsealed_external_report_attention(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        risk = {
            "source": "external_report_reference_manifest",
            "source_path": "external-reports/report-reference-manifest.json",
            "code": "external_report_strict_unavailable",
            "gate_effect": "advisory",
            "advisory_lifecycle_effect": "review_backlog",
        }
        self._write_closeout_summary(
            summary={
                "accepted_risk_instance_count": 1,
                "accepted_risk_family_count": 1,
            },
            accepted_risks=[risk],
        )
        self._write_artifact(
            "ops/reports/release-evidence-dashboard.json",
            {
                "artifact_kind": "test_report",
                "generated_at": "2026-05-02T08:00:00Z",
                "producer": "test",
                "source_tree_fingerprint": "abc",
                "currentness": {"status": "current"},
                "summary": {
                    "accepted_risk_count": 1,
                    "gate_attention_count": 1,
                },
                "gates": [
                    {
                        "gate_id": "advisory_lifecycle_review",
                        "checked_in_state": "attention",
                        "live_rerun_state": {"status": "attention"},
                        "accepted_risk": {
                            "count": 1,
                            "codes": ["external_report_strict_unavailable"],
                        },
                    }
                ],
            },
        )
        self._write_artifact(
            "ops/reports/release-lane-summary.json",
            {
                "artifact_kind": "test_report",
                "generated_at": "2026-05-02T08:00:00Z",
                "producer": "test",
                "source_tree_fingerprint": "abc",
                "currentness": {"status": "current"},
                "lane_summary": {
                    "auto_improve_lane_status": "pass",
                    "learning_lane_status": "pass",
                    "learning_claim_guard_status": "pass",
                    "learning_claim_allowed": False,
                    "claims_learning_improved": False,
                    "learning_claim_blocking_family_count": 0,
                    "advisory_lifecycle_family_count": 1,
                },
            },
        )

        unsealed = build_batch_manifest(self.vault, context=fixed_context())

        self.assertEqual(unsealed["release_decision_snapshot"]["accepted_risk_count"], 1)
        self.assertEqual(unsealed["release_decision_snapshot"]["gate_attention_count"], 1)
        self.assertEqual(
            unsealed["release_decision_snapshot"]["advisory_lifecycle_family_count"],
            1,
        )
        self.assertEqual(
            unsealed["release_decision_snapshot"]["accepted_risks"],
            [risk],
        )

        archive_path = self._write_release_source_zip()
        sealed = build_batch_manifest(
            self.vault,
            context=fixed_context(),
            distribution_zip_path=archive_path.relative_to(self.vault),
        )

        snapshot = sealed["release_decision_snapshot"]
        self.assertEqual(snapshot["accepted_risk_count"], 0)
        self.assertEqual(snapshot["gate_attention_count"], 0)
        self.assertEqual(snapshot["accepted_risk_family_count"], 0)
        self.assertEqual(snapshot["advisory_lifecycle_family_count"], 0)
        self.assertEqual(snapshot["accepted_risks"], [])
        self.assertEqual(validate_with_schema(sealed, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), [])

    def test_distribution_zip_keeps_unrelated_accepted_risk_attention(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        retired_risk = {
            "source": "external_report_reference_manifest",
            "source_path": "external-reports/report-reference-manifest.json",
            "code": "external_report_strict_unavailable",
            "gate_effect": "advisory",
            "advisory_lifecycle_effect": "review_backlog",
        }
        active_risk = {
            "source": "artifact_freshness",
            "source_path": "ops/reports/artifact-freshness-report.json",
            "code": "artifact_freshness_attention",
            "gate_effect": "advisory",
            "advisory_lifecycle_effect": "review_backlog",
        }
        self._write_closeout_summary(
            summary={
                "accepted_risk_instance_count": 2,
                "accepted_risk_family_count": 2,
            },
            accepted_risks=[retired_risk, active_risk],
        )
        self._write_artifact(
            "ops/reports/release-evidence-dashboard.json",
            {
                "artifact_kind": "test_report",
                "generated_at": "2026-05-02T08:00:00Z",
                "producer": "test",
                "source_tree_fingerprint": "abc",
                "currentness": {"status": "current"},
                "summary": {
                    "accepted_risk_count": 2,
                    "gate_attention_count": 2,
                },
                "gates": [
                    {
                        "gate_id": "external_report_reference_manifest",
                        "checked_in_state": "attention",
                        "live_rerun_state": {"status": "attention"},
                        "accepted_risk": {
                            "count": 1,
                            "codes": ["external_report_strict_unavailable"],
                        },
                    },
                    {
                        "gate_id": "artifact_freshness",
                        "checked_in_state": "attention",
                        "live_rerun_state": {"status": "attention"},
                        "accepted_risk": {
                            "count": 1,
                            "codes": ["artifact_freshness_attention"],
                        },
                    },
                ],
            },
        )
        self._write_artifact(
            "ops/reports/release-lane-summary.json",
            {
                "artifact_kind": "test_report",
                "generated_at": "2026-05-02T08:00:00Z",
                "producer": "test",
                "source_tree_fingerprint": "abc",
                "currentness": {"status": "current"},
                "lane_summary": {
                    "auto_improve_lane_status": "pass",
                    "learning_lane_status": "pass",
                    "learning_claim_guard_status": "pass",
                    "learning_claim_allowed": False,
                    "claims_learning_improved": False,
                    "learning_claim_blocking_family_count": 0,
                    "advisory_lifecycle_family_count": 2,
                },
            },
        )
        archive_path = self._write_release_source_zip()

        sealed = build_batch_manifest(
            self.vault,
            context=fixed_context(),
            distribution_zip_path=archive_path.relative_to(self.vault),
        )

        snapshot = sealed["release_decision_snapshot"]
        self.assertEqual(snapshot["accepted_risk_count"], 1)
        self.assertEqual(snapshot["gate_attention_count"], 1)
        self.assertEqual(snapshot["accepted_risk_family_count"], 1)
        self.assertEqual(snapshot["advisory_lifecycle_family_count"], 1)
        self.assertEqual(snapshot["accepted_risks"], [active_risk])
        self.assertEqual(validate_with_schema(sealed, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), [])

    def test_batch_manifest_prefers_closeout_status_v2_over_legacy_booleans(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary(
            clean_release_ready=True,
            machine_release_allowed=True,
            release_readiness_state="clean_pass",
            status_v2={
                "schema_version": 2,
                "compatibility_status_value": "pass",
                "status_axes": {
                    "release_authority_status": "conditional_pass",
                    "semantic_release_status": "conditional_pass",
                    "sealed_release_status": "sealed_conditional_pass",
                },
                "blocker_reason_ids": [
                    "release_authority_not_clean_pass",
                    "machine_release_not_allowed",
                ],
            },
        )

        report = build_batch_manifest(self.vault, context=fixed_context())

        self.assertEqual(report["release_authority_status"], "conditional_pass")
        self.assertEqual(report["semantic_release_status"], "conditional_pass")
        self.assertEqual(report["machine_release_status"], "blocked")
        self.assertEqual(report["operator_release_status"], "allowed")
        snapshot = report["release_decision_snapshot"]
        self.assertEqual(snapshot["release_readiness_state"], "conditional_pass")
        self.assertEqual(snapshot["release_authority_status"], "conditional_pass")
        self.assertEqual(snapshot["semantic_release_status"], "conditional_pass")
        self.assertEqual(
            snapshot["closeout_sealed_release_status"],
            "sealed_conditional_pass",
        )
        self.assertEqual(
            snapshot["status_v2_blocker_reason_ids"],
            ["release_authority_not_clean_pass", "machine_release_not_allowed"],
        )
        self.assertEqual(snapshot["status_v2_used_legacy_fallback_fields"], [])
        self.assertEqual(
            report["status_v2"]["status_axes"]["release_authority_status"],
            "conditional_pass",
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_batch_manifest_status_fails_when_required_artifacts_missing(self) -> None:
        self._write_closeout_summary()
        # Do not write any required artifacts except closeout summary

        report = build_batch_manifest(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["batch_integrity_status"], "fail")
        self.assertEqual(report["release_authority_status"], "clean_pass")
        self.assertEqual(report["semantic_release_status"], "clean_pass")
        self.assertEqual(
            report["sealed_release_status"], "unsealed_artifact_incomplete"
        )
        self.assertIn(
            "artifact_inventory_not_current",
            report["release_authority_vocabulary"]["blocker_reason_ids"],
        )
        self.assertFalse(report["coherence"]["all_required_present"])
        self.assertFalse(report["coherence"]["all_required_current"])
        # Only closeout summary is present
        self.assertEqual(report["summary"]["present_count"], 1)

    def test_batch_manifest_separates_authority_from_integrity(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary(
            clean_release_ready=False,
            machine_release_allowed=False,
            release_readiness_state="conditional_pass",
            summary={"accepted_risk_family_count": 1},
        )

        report = build_batch_manifest(self.vault, context=fixed_context())

        # Artifact integrity is fine (all present/current)
        self.assertEqual(report["batch_integrity_status"], "pass")
        # Release authority is conditional because clean/machine are blocked
        self.assertEqual(report["release_authority_status"], "conditional_pass")
        self.assertEqual(report["semantic_release_status"], "conditional_pass")
        self.assertEqual(
            report["sealed_release_status"], "unsealed_distribution_not_provided"
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["authority_reason_ids"],
            [
                "release_authority_not_clean_pass",
                "machine_release_not_allowed",
            ],
        )
        self.assertEqual(
            report["release_authority_vocabulary"]["operator_summary_round_trip"][
                "status"
            ],
            "pass",
        )
        self.assertIn(
            "machine_release_allowed=false",
            report["release_authority_vocabulary"]["operator_summary"],
        )
        self.assertEqual(report["artifact_digest_sealing_status"], "pass")
        self.assertEqual(report["clean_lane_status"], "fail")
        self.assertEqual(report["machine_release_status"], "blocked")
        self.assertEqual(report["operator_release_status"], "allowed")
        # Legacy status reflects the combined view
        self.assertEqual(report["status"], "fail")
        self.assertTrue(report["coherence"]["all_required_present"])
        self.assertTrue(report["coherence"]["all_required_current"])
        self.assertEqual(
            report["integrity_layers"]["artifact_inventory_integrity"], "pass"
        )
        self.assertEqual(
            report["integrity_layers"]["artifact_content_integrity"], "pass"
        )
        self.assertEqual(
            report["integrity_layers"]["source_tree_coherence_integrity"], "fail"
        )
        self.assertEqual(
            report["integrity_layers"]["source_tree_coherence_status"], "unknown"
        )

    def test_batch_manifest_records_downstream_input_digest_mismatch_as_json(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        release_smoke_path = (
            self.vault / "ops" / "reports" / "release-smoke-report.json"
        )
        actual_release_smoke_digest = hashlib.sha256(
            release_smoke_path.read_bytes()
        ).hexdigest()
        stale_release_smoke_digest = "f" * 64
        self._write_closeout_summary(
            input_fingerprints={
                "release_smoke": stale_release_smoke_digest,
            },
            components=[
                {
                    "name": "release_smoke",
                    "path": "ops/reports/release-smoke-report.json",
                }
            ],
        )

        report = build_batch_manifest(self.vault, context=fixed_context())

        mismatch = report["downstream_input_digest_mismatch"]
        self.assertEqual(mismatch["status"], "mismatch")
        self.assertEqual(mismatch["compared_input_count"], 1)
        self.assertEqual(mismatch["mismatch_count"], 1)
        self.assertEqual(len(mismatch["mismatches"]), 1)
        self.assertEqual(mismatch["mismatches"][0]["component_name"], "release_smoke")
        self.assertEqual(
            mismatch["mismatches"][0]["source_path"],
            "ops/reports/release-smoke-report.json",
        )
        self.assertEqual(
            mismatch["mismatches"][0]["expected_digest"], stale_release_smoke_digest
        )
        self.assertEqual(
            mismatch["mismatches"][0]["actual_digest"], actual_release_smoke_digest
        )

    def test_batch_manifest_records_source_evidence_freshness(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()

        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )

        freshness = report["source_evidence_freshness"]
        self.assertEqual(freshness["status"], "pass")
        self.assertEqual(freshness["basis"], "filesystem_mtime")
        self.assertEqual(freshness["timestamp_semantics"], "filesystem_timestamp")
        self.assertEqual(
            freshness["source_freshness_temporal_authority"], "filesystem_mtime"
        )
        self.assertEqual(
            freshness["source_freshness_content_authority"], "source_tree_fingerprint"
        )
        self.assertEqual(freshness["zip_metadata_path"], "")
        self.assertTrue(freshness["archive_timestamp_has_timezone"])
        self.assertGreater(freshness["source_file_count"], 0)
        self.assertEqual(freshness["changed_after_generated_at_count"], 0)
        self.assertEqual(freshness["missing_zip_member_count"], 0)
        self.assertEqual(freshness["changed_after_generated_at"], [])
        self.assertIn("source_evidence_freshness status=pass", freshness["summary"])

    def test_batch_manifest_can_use_zip_member_timestamps_for_source_freshness(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip(
            timestamp=(2030, 1, 1, 9, 0, 0),
        )
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, 9, tzinfo=dt.UTC)),
            zip_metadata_path=archive_path.relative_to(self.vault),
            zip_timestamp_timezone="UTC",
        )

        freshness = report["source_evidence_freshness"]
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )
        self.assertEqual(freshness["status"], "pass")
        self.assertEqual(freshness["basis"], "zip_member_timestamp")
        self.assertEqual(freshness["timestamp_semantics"], "archive_member_timestamp")
        self.assertEqual(
            freshness["source_freshness_temporal_authority"], "archive_member_timestamp"
        )
        self.assertEqual(
            freshness["source_freshness_content_authority"], "source_tree_fingerprint"
        )
        self.assertEqual(freshness["zip_metadata_path"], "tmp/release.zip")
        self.assertFalse(freshness["archive_timestamp_has_timezone"])
        self.assertEqual(freshness["timestamp_timezone_assumption"], "UTC")
        self.assertEqual(freshness["changed_after_generated_at_count"], 0)
        self.assertEqual(freshness["missing_zip_member_count"], 0)

    def test_batch_manifest_marks_normalized_zip_timestamps_as_not_temporal_authority(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip(
            timestamp=(1980, 1, 1, 0, 0, 0),
        )

        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, 9, tzinfo=dt.UTC)),
            zip_metadata_path=archive_path.relative_to(self.vault),
            zip_timestamp_timezone="UTC",
        )

        freshness = report["source_evidence_freshness"]
        distribution = report["distribution_package"]
        self.assertEqual(
            freshness["timestamp_semantics"], "normalized_archive_timestamp"
        )
        self.assertEqual(
            freshness["source_freshness_temporal_authority"], "not_claimed"
        )
        self.assertEqual(
            distribution["timestamp_semantics"], "normalized_archive_timestamp"
        )
        self.assertEqual(distribution["status"], "materialized")
        self.assertTrue(distribution["path_set_matches_release_manifest"])
        self.assertTrue(distribution["content_digest_matches_release_manifest"])
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_batch_manifest_records_distribution_closure_and_audit_materialization(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip()

        report = build_batch_manifest(
            self.vault,
            context=fixed_context(),
            distribution_zip_path=archive_path.relative_to(self.vault),
        )

        distribution = report["distribution_package"]
        audit = report["audit_materialization"]
        self.assertEqual(report["status"], "pass")
        self.assertEqual(
            report["status_semantics"]["top_level_status_meaning"],
            "legacy_strict_clean_sealed_claim",
        )
        self.assertEqual(
            report["status_semantics"]["release_authority_status_meaning"],
            "semantic_release_authority_from_closeout",
        )
        self.assertEqual(report["status_v2"]["schema_version"], 2)
        self.assertEqual(report["status_v2"]["migration_readiness_status"], "active")
        self.assertEqual(
            report["status_v2"]["status_axes"]["release_authority_status"],
            report["release_authority_status"],
        )
        self.assertEqual(
            report["status_v2"]["status_axes"]["sealed_release_status"],
            report["sealed_release_status"],
        )
        self.assertEqual(
            report["status_v2"]["status_classification"], "strict_clean_and_sealed"
        )
        self.assertEqual(report["status_v2_preview"], report["status_v2"])
        self.assertEqual(
            report["status_v2_preview"]["compatibility_status_field"], "status"
        )
        self.assertTrue(report["status_v2_preview"]["compatibility_status_deprecated"])
        self.assertEqual(
            report["status_v2_preview"]["release_authority_status_value"],
            report["release_authority_status"],
        )
        self.assertEqual(
            report["status_v2_preview"]["sealed_status_value"],
            report["sealed_release_status"],
        )
        self.assertEqual(
            report["status_v2_preview"]["proposed_top_level_status_replacement"],
            "sealed_release_status",
        )
        self.assertEqual(report["sealed_release_status"], "sealed_clean_pass")
        self.assertEqual(report["release_authority_vocabulary"]["blocker_reason_ids"], [])
        self.assertEqual(report["external_source_zip_bound"]["status"], "bound")
        self.assertEqual(distribution["status"], "materialized")
        self.assertEqual(distribution["archive_profile"], "source_content_package")
        self.assertEqual(distribution["path"], "tmp/release.zip")
        self.assertRegex(distribution["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            distribution["file_count"], distribution["source_manifest_file_count"]
        )
        self.assertTrue(distribution["path_set_matches_release_manifest"])
        self.assertTrue(distribution["content_digest_matches_release_manifest"])
        self.assertEqual(audit["mode"], "referenced_checked_in_artifacts")
        self.assertFalse(audit["bundle_required"])
        self.assertEqual(audit["optional_bundle_target"], "release-audit-pack")
        self.assertRegex(audit["evidence_set_digest"], r"^[a-f0-9]{64}$")
        self.assertEqual(audit["optional_payload_policy"]["status"], "not_available")
        self.assertEqual(audit["optional_payload_policy"]["payload_count"], 0)
        self.assertEqual(audit["optional_payload_policy"]["available_payload_count"], 0)
        self.assertEqual(audit["optional_payloads"], [])
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_batch_manifest_allows_release_archive_self_description_virtual_member(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip()
        with zipfile.ZipFile(archive_path, "a") as archive:
            archive.writestr(
                f"LLMwiki-source/{ARCHIVE_SELF_DESCRIPTION_PATH}",
                json.dumps({"artifact_kind": "release_archive_self_description"}),
            )

        report = build_batch_manifest(
            self.vault,
            context=fixed_context(),
            distribution_zip_path=archive_path.relative_to(self.vault),
        )

        distribution = report["distribution_package"]
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["sealed_release_status"], "sealed_clean_pass")
        self.assertEqual(report["external_source_zip_bound"]["status"], "bound")
        self.assertEqual(distribution["status"], "materialized")
        self.assertTrue(distribution["path_set_matches_release_manifest"])
        self.assertTrue(distribution["content_digest_matches_release_manifest"])
        self.assertEqual(
            distribution["file_count"], distribution["source_manifest_file_count"] + 1
        )
        self.assertEqual(distribution["zip_only_path_count"], 0)
        self.assertEqual(distribution["zip_only_paths"], [])
        self.assertEqual(distribution["allowed_virtual_zip_path_count"], 1)
        self.assertEqual(
            distribution["allowed_virtual_zip_paths"], [ARCHIVE_SELF_DESCRIPTION_PATH]
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_batch_manifest_marks_distribution_drift_as_unsealed(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip()
        with zipfile.ZipFile(archive_path, "a") as archive:
            archive.writestr(
                "LLMwiki-source/extra-review-only.txt",
                "not in source manifest\n",
            )

        report = build_batch_manifest(
            self.vault,
            context=fixed_context(),
            distribution_zip_path=archive_path.relative_to(self.vault),
        )

        distribution = report["distribution_package"]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["sealed_release_status"], "unsealed_distribution_drift")
        self.assertEqual(report["external_source_zip_bound"]["status"], "drift")
        self.assertEqual(distribution["status"], "drift")
        self.assertEqual(distribution["zip_only_path_count"], 1)
        self.assertEqual(distribution["zip_only_paths"], ["extra-review-only.txt"])
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_zip_metadata_check_ignores_filesystem_mtime_drift(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip(
            timestamp=(2030, 1, 1, 9, 0, 0),
        )
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, 9, tzinfo=dt.UTC)),
            zip_metadata_path=archive_path.relative_to(self.vault),
            zip_timestamp_timezone="UTC",
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")
        source_path = self.vault / "ops" / "policies" / "release-closeout-batch.json"
        edited_at = dt.datetime(2030, 1, 2, tzinfo=dt.UTC).timestamp()
        os.utime(source_path, (edited_at, edited_at))

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/test-batch-manifest.json",
                "--check",
                "--zip-metadata",
                "tmp/release.zip",
                "--zip-timestamp-timezone",
                "UTC",
            ]
        )

        self.assertEqual(exit_code, 0)

    def test_check_manifest_fails_when_source_file_is_newer_than_generated_at(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")
        source_path = self.vault / "ops" / "scripts" / "post_evidence_edit.py"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("print('changed after evidence')\n", encoding="utf-8")
        edited_at = dt.datetime(2030, 1, 2, tzinfo=dt.UTC).timestamp()
        os.utime(source_path, (edited_at, edited_at))

        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/test-batch-manifest.json",
                    "--check",
                ]
            )

        self.assertEqual(exit_code, 1)
        stderr_text = stderr.getvalue()
        self.assertIn(
            "batch manifest check failed: source files changed after "
            "checked-in manifest generated_at",
            stderr_text,
        )
        classification_line = stderr_text.split(
            "batch manifest replay mismatch classification:\n",
            maxsplit=1,
        )[1].splitlines()[0]
        classification = json.loads(classification_line)
        self.assertEqual(
            classification["primary_class"],
            "external_source_change_after_evidence",
        )
        self.assertEqual(classification["source_freshness_status"], "fail")
        self.assertNotIn(
            "release-finality-resettle-current-or-refresh",
            classification["recommended_targets"],
        )
        self.assertEqual(
            classification["recommended_lane"],
            "external-source-change-review",
        )

    def test_check_manifest_classifies_content_drift_without_digest_drift(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )
        report["dependency_order"] = [
            *report["dependency_order"],
            "unexpected-local-metadata",
        ]
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/test-batch-manifest.json",
                    "--check",
                ]
            )

        self.assertEqual(exit_code, 1)
        stderr_text = stderr.getvalue()
        self.assertIn("batch manifest check failed: content differs", stderr_text)
        classification_line = stderr_text.split(
            "batch manifest replay mismatch classification:\n",
            maxsplit=1,
        )[1].splitlines()[0]
        classification = json.loads(classification_line)
        self.assertEqual(
            classification["primary_class"],
            "batch_manifest_content_mismatch",
        )
        self.assertEqual(classification["binding_mismatches"], [])
        self.assertIn(
            "release-closeout-batch-manifest-promote",
            classification["recommended_targets"],
        )

    def test_check_manifest_fails_after_sealed_artifact_digest_drift(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")
        self._write_artifact(
            "ops/reports/release-evidence-dashboard.json",
            {
                "artifact_kind": "test_report",
                "generated_at": "2026-05-02T08:00:00Z",
                "producer": "test",
                "source_tree_fingerprint": "abc",
                "currentness": {"status": "current"},
                "summary": {
                    "accepted_risk_count": 1,
                    "gate_attention_count": 0,
                },
            },
        )
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/test-batch-manifest.json",
                    "--check",
                ]
            )

        self.assertEqual(exit_code, 1)
        stderr_text = stderr.getvalue()
        self.assertIn("artifact binding mismatches:", stderr_text)
        self.assertIn("ops/reports/release-evidence-dashboard.json", stderr_text)
        classification_line = stderr_text.split(
            "batch manifest replay mismatch classification:\n",
            maxsplit=1,
        )[1].splitlines()[0]
        classification = json.loads(classification_line)
        self.assertEqual(
            classification["primary_class"],
            "fixed_point_tracked_writer_binding_mismatch",
        )
        self.assertEqual(
            classification["recommended_fixed_point_initial_targets"],
            ["release-evidence-dashboard-report"],
        )

    def test_check_manifest_classifies_freshness_index_cohort_binding_drift(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")
        self._write_artifact(
            "ops/reports/artifact-freshness-report.json",
            {
                "artifact_kind": "test_report",
                "generated_at": "2026-05-02T08:00:00Z",
                "producer": "test",
                "source_tree_fingerprint": "changed",
                "currentness": {"status": "current"},
            },
        )
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/test-batch-manifest.json",
                    "--check",
                ]
            )

        self.assertEqual(exit_code, 1)
        classification_line = stderr.getvalue().split(
            "batch manifest replay mismatch classification:\n",
            maxsplit=1,
        )[1].splitlines()[0]
        classification = json.loads(classification_line)
        self.assertEqual(
            classification["primary_class"],
            "batch_manifest_freshness_index_cohort_binding_mismatch",
        )
        self.assertEqual(
            classification["recommended_fixed_point_initial_targets"],
            ["artifact-freshness"],
        )
        self.assertNotIn(
            "fixed_point_tracked_writer_binding_mismatch",
            classification["classes"],
        )

    def test_batch_manifest_includes_dependency_order_from_policy(self) -> None:
        self._write_required_artifacts()
        self._write_closeout_summary()

        report = build_batch_manifest(self.vault, context=fixed_context())

        expected_order = [
            "release-smoke-report",
            "source-package-clean-extract",
            "external-report-reference-manifest",
            "generated-artifact-index",
            "artifact-freshness-report",
            "test-execution-summary",
            "test-execution-summary-full",
            "release-closeout-summary",
            "learning-readiness-signoff-revalidation",
            "learning-delta-scoreboard",
            "release-evidence-cohort",
            "release-evidence-dashboard",
            "release-lane-summary",
            "release-clean-blocker-ledger",
        ]
        self.assertEqual(report["dependency_order"], expected_order)

    def test_batch_manifest_artifacts_match_policy_spec(self) -> None:
        self._write_required_artifacts()
        self._write_closeout_summary()

        report = build_batch_manifest(self.vault, context=fixed_context())

        artifact_paths = {a["path"] for a in report["artifacts"]}
        expected_paths = {
            "ops/reports/release-smoke-report.json",
            "ops/reports/source-package-clean-extract.json",
            "external-reports/report-reference-manifest.json",
            "ops/reports/generated-artifact-index.json",
            "ops/reports/artifact-freshness-report.json",
            "ops/reports/test-execution-summary.json",
            "ops/reports/test-execution-summary-full.json",
            "ops/reports/release-closeout-summary.json",
            "ops/reports/learning-readiness-signoff-revalidation.json",
            "ops/reports/learning-delta-scoreboard.json",
            "ops/reports/release-evidence-cohort.json",
            "ops/reports/release-evidence-dashboard.json",
            "ops/reports/release-lane-summary.json",
            "ops/reports/release-clean-blocker-ledger.json",
        }
        self.assertEqual(artifact_paths, expected_paths)
        self.assertEqual(report["schema_version"], 2)
        for artifact in report["artifacts"]:
            self.assertIn("required", artifact)
            self.assertTrue(artifact["required"])
            self.assertNotIn("digest", artifact)
            self.assertRegex(artifact["raw_digest"], r"^[a-f0-9]{64}$")
            self.assertRegex(artifact["binding_digest"], r"^[a-f0-9]{64}$")
            expected_mode = (
                "revision"
                if artifact["path"]
                in {
                    "ops/reports/release-closeout-summary.json",
                    "ops/reports/release-evidence-cohort.json",
                }
                else "content"
            )
            self.assertEqual(artifact["binding_mode"], expected_mode)

    def test_check_manifest_allows_raw_only_artifact_drift(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")
        dashboard_path = "ops/reports/release-evidence-dashboard.json"
        dashboard = json.loads(
            (self.vault / dashboard_path).read_text(encoding="utf-8")
        )
        dashboard["generated_at"] = "2026-05-02T08:01:00Z"
        dashboard["source_revision"] = "raw-envelope-alias-only"
        dashboard["currentness"]["checked_at"] = "2026-05-02T08:01:00Z"
        self._write_artifact(dashboard_path, dashboard)

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/test-batch-manifest.json",
                "--check",
            ]
        )

        self.assertEqual(exit_code, 0)

    def test_check_manifest_rejects_v1_as_current_authority(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        report = build_batch_manifest(
            self.vault,
            context=context_at(dt.datetime(2030, 1, 1, tzinfo=dt.UTC)),
        )
        report["schema_version"] = 1
        self._write_artifact("ops/reports/test-batch-manifest.json", report)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "ops/reports/test-batch-manifest.json",
                    "--check",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "only schema_version=2 is current authority",
            stderr.getvalue(),
        )

    def test_release_audit_pack_materializes_v1_digest_as_archive_evidence(
        self,
    ) -> None:
        artifact_path = "ops/reports/legacy-release-evidence.json"
        self._write_artifact(artifact_path, {"status": "retained"})
        artifact_digest = hashlib.sha256(
            (self.vault / artifact_path).read_bytes()
        ).hexdigest()
        legacy_manifest = {
            "schema_version": 1,
            "batch_id": "legacy-archive-batch",
            "artifacts": [
                {
                    "path": artifact_path,
                    "digest": artifact_digest,
                    "required": True,
                    "role": "retained_archive_evidence",
                    "artifact_kind": "test_report",
                }
            ],
        }
        self.assertNotIn("raw_digest", legacy_manifest["artifacts"][0])
        manifest_path = "ops/reports/legacy-batch-manifest.json"
        self._write_artifact(manifest_path, legacy_manifest)

        result = build_audit_pack(
            self.vault,
            batch_manifest_path=manifest_path,
            out_path="tmp/legacy-release-audit-pack.zip",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["missing_required"], [])
        self.assertEqual(result["digest_mismatches"], [])
        with zipfile.ZipFile(self.vault / result["path"]) as archive:
            names = set(archive.namelist())
            pack_manifest = json.loads(archive.read("release-audit-pack-manifest.json"))
        self.assertIn(artifact_path, names)
        self.assertEqual(pack_manifest["batch_id"], "legacy-archive-batch")
        self.assertIn(
            {
                "path": artifact_path,
                "sha256": artifact_digest,
                "role": "retained_archive_evidence",
            },
            pack_manifest["packed_entries"],
        )

    def test_release_audit_pack_rejects_v2_legacy_digest_fallback(self) -> None:
        artifact_path = "ops/reports/release-evidence.json"
        self._write_artifact(artifact_path, {"status": "retained"})
        artifact_digest = hashlib.sha256(
            (self.vault / artifact_path).read_bytes()
        ).hexdigest()
        manifest_path = "ops/reports/malformed-v2-batch-manifest.json"
        self._write_artifact(
            manifest_path,
            {
                "schema_version": 2,
                "batch_id": "malformed-v2-batch",
                "artifacts": [
                    {
                        "path": artifact_path,
                        "digest": artifact_digest,
                        "required": True,
                        "role": "release_evidence",
                        "artifact_kind": "test_report",
                    }
                ],
            },
        )

        with self.assertRaisesRegex(ValueError, "must declare raw_digest"):
            build_audit_pack(
                self.vault,
                batch_manifest_path=manifest_path,
                out_path="tmp/malformed-v2-release-audit-pack.zip",
            )

    def test_batch_manifest_rejects_missing_artifact_binding_mode(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        policy_path = self.vault / "ops/policies/release-closeout-batch.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["artifacts"][0].pop("binding_mode")
        self._write_artifact("ops/policies/release-closeout-batch.json", policy)

        with self.assertRaisesRegex(ValueError, "must declare binding_mode"):
            build_batch_manifest(self.vault, context=fixed_context())

    def test_batch_manifest_rejects_unknown_artifact_binding_mode(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        policy_path = self.vault / "ops/policies/release-closeout-batch.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["artifacts"][0]["binding_mode"] = "unknown"
        self._write_artifact("ops/policies/release-closeout-batch.json", policy)

        with self.assertRaisesRegex(ValueError, "unsupported binding_mode"):
            build_batch_manifest(self.vault, context=fixed_context())

    def test_release_audit_pack_materializes_batch_manifest_artifacts(self) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        archive_path = self._write_release_source_zip()
        report = build_batch_manifest(
            self.vault,
            context=fixed_context(),
            distribution_zip_path=archive_path.relative_to(self.vault),
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")

        result = build_audit_pack(
            self.vault,
            batch_manifest_path="ops/reports/test-batch-manifest.json",
            out_path="tmp/test-release-audit-pack.zip",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["missing_required"], [])
        self.assertEqual(result["digest_mismatches"], [])
        archive_path = self.vault / "tmp" / "test-release-audit-pack.zip"
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            timestamps = {info.date_time for info in archive.infolist()}
            pack_manifest = json.loads(archive.read("release-audit-pack-manifest.json"))
        self.assertIn("ops/reports/test-batch-manifest.json", names)
        self.assertIn("release-audit-pack-manifest.json", names)
        self.assertIn("ops/reports/test-execution-summary-full.json", names)
        self.assertIn("ops/reports/learning-delta-scoreboard.json", names)
        self.assertEqual(timestamps, {(1980, 1, 1, 0, 0, 0)})
        self.assertEqual(pack_manifest["source_zip"]["path"], "tmp/release.zip")
        self.assertEqual(
            pack_manifest["source_zip"]["sha256"],
            report["distribution_package"]["sha256"],
        )

    def test_release_audit_pack_can_include_optional_junit_and_log_payloads(
        self,
    ) -> None:
        self._write_required_artifacts(currentness_status="current")
        self._write_closeout_summary()
        log_path = self.vault / "tmp" / "test-execution-summary-full.log"
        junit_path = self.vault / "tmp" / "test-execution-summary-full.junit.xml"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("pytest full suite log\n", encoding="utf-8")
        junit_path.write_text('<testsuite tests="1" />\n', encoding="utf-8")
        full_summary_path = (
            self.vault / "ops" / "reports" / "test-execution-summary-full.json"
        )
        full_summary = json.loads(full_summary_path.read_text(encoding="utf-8"))
        full_summary["evidence_artifacts"] = [
            {
                "kind": "execution_log",
                "path": "tmp/test-execution-summary-full.log",
                "exists": True,
                "size_bytes": log_path.stat().st_size,
                "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                "source": "captured_pytest_stdout_stderr",
            },
            {
                "kind": "junit_xml",
                "path": "tmp/test-execution-summary-full.junit.xml",
                "exists": True,
                "size_bytes": junit_path.stat().st_size,
                "sha256": hashlib.sha256(junit_path.read_bytes()).hexdigest(),
                "source": "pytest_junit_xml",
            },
        ]
        full_summary_path.write_text(
            json.dumps(full_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = build_batch_manifest(self.vault, context=fixed_context())
        audit = report["audit_materialization"]
        self.assertEqual(audit["optional_payload_policy"]["status"], "available")
        self.assertEqual(audit["optional_payload_policy"]["payload_count"], 2)
        self.assertEqual(audit["optional_payload_policy"]["available_payload_count"], 2)
        self.assertEqual(
            sorted(item["kind"] for item in audit["optional_payloads"]),
            ["execution_log", "junit_xml"],
        )
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )
        write_report(self.vault, report, "ops/reports/test-batch-manifest.json")

        default_result = build_audit_pack(
            self.vault,
            batch_manifest_path="ops/reports/test-batch-manifest.json",
            out_path="tmp/test-release-audit-pack-default.zip",
        )
        self.assertEqual(default_result["status"], "pass")
        with zipfile.ZipFile(
            self.vault / "tmp" / "test-release-audit-pack-default.zip"
        ) as archive:
            default_names = set(archive.namelist())
        self.assertNotIn("tmp/test-execution-summary-full.log", default_names)
        self.assertNotIn("tmp/test-execution-summary-full.junit.xml", default_names)

        optional_result = build_audit_pack(
            self.vault,
            batch_manifest_path="ops/reports/test-batch-manifest.json",
            out_path="tmp/test-release-audit-pack-with-payloads.zip",
            include_optional_payloads=True,
        )
        self.assertEqual(optional_result["status"], "pass")
        self.assertEqual(optional_result["missing_optional"], [])
        with zipfile.ZipFile(
            self.vault / "tmp" / "test-release-audit-pack-with-payloads.zip"
        ) as archive:
            names = set(archive.namelist())
            pack_manifest = json.loads(archive.read("release-audit-pack-manifest.json"))
        self.assertIn("tmp/test-execution-summary-full.log", names)
        self.assertIn("tmp/test-execution-summary-full.junit.xml", names)
        self.assertTrue(pack_manifest["include_optional_payloads"])
        self.assertEqual(pack_manifest["optional_payload_count"], 2)

    def test_main_exits_zero_on_pass(self) -> None:
        self._write_required_artifacts()
        self._write_closeout_summary()
        self._write_release_source_zip()

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/test-batch-manifest.json",
                "--distribution-zip",
                "tmp/release.zip",
            ]
        )

        self.assertEqual(exit_code, 0)
        destination = self.vault / "ops" / "reports" / "test-batch-manifest.json"
        self.assertTrue(destination.exists())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "pass")
        self.assertEqual(persisted["sealed_release_status"], "sealed_clean_pass")

    def test_main_exits_zero_on_write_success_even_if_status_fail(self) -> None:
        self._write_closeout_summary()
        # Missing required artifacts — status will be "fail" but write succeeds

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/reports/test-batch-manifest.json",
            ]
        )

        self.assertEqual(exit_code, 0)
        destination = self.vault / "ops" / "reports" / "test-batch-manifest.json"
        self.assertTrue(destination.exists())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "fail")

    def test_write_report_validates_schema(self) -> None:
        self._write_required_artifacts()
        self._write_closeout_summary()
        report = build_batch_manifest(self.vault, context=fixed_context())

        destination = write_report(
            self.vault, report, "ops/reports/test-batch-manifest.json"
        )

        self.assertTrue(destination.exists())
        self.assertEqual(
            validate_with_schema(report, load_schema(BATCH_MANIFEST_SCHEMA_PATH)), []
        )

    def test_makefile_closeout_recipe_uses_fixed_point_finalizer(self) -> None:
        makefile_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        for mk_file in sorted(REPO_ROOT.glob("mk/*.mk")):
            makefile_text += "\n" + mk_file.read_text(encoding="utf-8")
        import re

        recipe_lines: list[str] = []
        for target in (
            "release-evidence-converge-phase-1",
            "release-evidence-converge-phase-2",
            "release-evidence-converge-phase-3",
        ):
            match = re.search(
                rf"^{target}:[^\n]*(?P<body>(?:\n\t[^\n]*)*)",
                makefile_text,
                flags=re.MULTILINE,
            )
            if match is None:
                self.fail(f"{target} target not found")
            recipe_lines.extend(
                line.strip()
                for line in match.group(0).splitlines()[1:]
                if line.startswith("\t")
            )

        self.assertTrue(recipe_lines, "release-evidence-converge has no recipe lines")
        self.assertEqual(recipe_lines[-1], "$(MAKE) release-closeout-finality-verify")
        fixed_point_index = next(
            (
                i
                for i, line in enumerate(recipe_lines)
                if line == "$(MAKE) release-closeout-fixed-point"
            ),
            None,
        )
        if fixed_point_index is None:
            self.fail("release-closeout-fixed-point not found")
        self.assertNotIn(
            "$(MAKE) release-closeout-batch-manifest-promote", recipe_lines
        )
        self.assertNotIn("$(MAKE) release-evidence-closeout-self-check", recipe_lines)
        allowed_after_fixed_point = {
            "$(MAKE) tmp-json-clean",
            "$(MAKE) release-closeout-finality-verify",
        }
        for i, line in enumerate(recipe_lines):
            if i > fixed_point_index:
                self.assertIn(
                    line,
                    allowed_after_fixed_point,
                    f"step at index {i} is not allowed after release-closeout-fixed-point",
                )
        self.assertEqual(
            recipe_lines.count("$(MAKE) release-closeout-fixed-point"),
            1,
            "release-evidence-converge should execute the writer graph once",
        )


if __name__ == "__main__":
    unittest.main()
