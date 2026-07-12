from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_binding_runtime import binding_file_digest
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.operator_release_summary import build_report, main
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "operator-release-summary.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 4, 10, 0, tzinfo=dt.UTC),
    )


class OperatorReleaseSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._seed_release_reports(full_summary=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _digest(self, rel_path: str) -> str:
        return hashlib.sha256((self.vault / rel_path).read_bytes()).hexdigest()

    def _artifact_record(self, rel_path: str, *, binding_mode: str = "content") -> dict[str, str]:
        return {
            "path": rel_path,
            "raw_digest": self._digest(rel_path),
            "binding_digest": binding_file_digest(
                self.vault / rel_path,
                binding_mode=binding_mode,
            )[1],
            "binding_mode": binding_mode,
        }

    def _seed_release_reports(self, *, full_summary: bool) -> None:
        closeout_path = "ops/reports/release-closeout-summary.json"
        test_summary_path = "ops/reports/test-execution-summary.json"
        full_summary_path = "ops/reports/test-execution-summary-full.json"
        learning_path = "ops/reports/learning-readiness-signoff-revalidation.json"
        learning_scoreboard_path = "ops/reports/learning-delta-scoreboard.json"
        self_check_path = "ops/reports/release-evidence-closeout-self-check.json"

        self._write_json(
            closeout_path,
            {
                "artifact_kind": "release_closeout_summary",
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
                "clean_lane_blocking_risk_family_count": 0,
                "summary": {"accepted_risk_family_count": 0},
            },
        )
        self._write_json(
            test_summary_path,
            {
                "artifact_kind": "test_execution_summary",
                "suite": "report-contract-summary",
                "suite_scope": "report_contract_summary",
                "represents_full_suite": False,
                "status": "pass",
                "counts": {"passed": 119},
            },
        )
        if full_summary:
            self._write_json(
                full_summary_path,
                {
                    "artifact_kind": "test_execution_summary",
                    "suite": "full",
                    "suite_scope": "full_suite",
                    "represents_full_suite": True,
                    "status": "pass",
                    "counts": {"passed": 874},
                    "full_suite_evidence": {
                        "reason": "this execution has no pytest selectors and is treated as full-suite evidence"
                    },
                },
            )
        self._write_json(
            learning_path,
            {
                "artifact_kind": "learning_readiness_signoff_revalidation",
                "status": "pass",
                "closeout": {"accepted_learning_risk": False},
                "revalidation": {"status": "current"},
                "release_effect": {
                    "clean_release_effect": "clean_allowed",
                    "operator_summary": "learning readiness is current",
                },
            },
        )
        self._write_json(
            learning_scoreboard_path,
            {
                "artifact_kind": "learning_delta_scoreboard",
                "status": "pass",
                "summary": {
                    "claim_level": "bounded_learning_likely",
                    "bounded_learning_claim_allowed": True,
                    "confirmed_learning_improvement_allowed": False,
                    "confirmed_learning_improvement_status": "not_ready",
                    "confirmed_blocking_predicate_ids": ["repeated_same_family_evidence"],
                },
                "learning_claim_unlock_review": {
                    "confirmed_predicate_results": [
                        {
                            "id": "repeated_same_family_evidence",
                            "status": "fail",
                            "source_path": "ops/reports/learning-confirmed-evidence-cohort.json",
                            "observed_value": "eligible_family_count=0",
                        },
                        {
                            "id": "public_check_pass",
                            "status": "pass",
                            "source_path": "ops/reports/public-check-summary.json",
                            "observed_value": "status=pass",
                        },
                    ]
                },
            },
        )
        self._write_json(
            self_check_path,
            {
                "artifact_kind": "release_evidence_closeout_self_check",
                "status": {"result": "pass"},
            },
        )

        artifact_paths = [closeout_path, test_summary_path, learning_path, self_check_path]
        if full_summary:
            artifact_paths.append(full_summary_path)
        artifacts = [self._artifact_record(rel_path) for rel_path in artifact_paths]
        source_zip_path = "build/release/LLMwiki-source.zip"
        (self.vault / source_zip_path).parent.mkdir(parents=True, exist_ok=True)
        (self.vault / source_zip_path).write_bytes(b"source zip")
        source_zip_digest = self._digest(source_zip_path)
        self._write_json(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "schema_version": 2,
                "artifact_kind": "release_closeout_batch_manifest",
                "artifacts": artifacts,
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {
                    "status": "materialized",
                    "archive_profile": "source_content_package",
                    "path": source_zip_path,
                    "sha256": source_zip_digest,
                    "entry_count": 1,
                    "path_set_matches_release_manifest": True,
                    "content_digest_matches_release_manifest": True,
                },
                "release_decision_snapshot": {
                    "auto_improve_lane_status": "pass",
                    "accepted_risk_count": 0,
                    "gate_attention_count": 0,
                    "learning_claim_blocking_family_count": 0,
                    "advisory_lifecycle_family_count": 0,
                },
            },
        )

    def test_operator_summary_separates_semantic_sealed_and_full_suite_status(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["semantic_release_status"], "clean_pass")
        self.assertEqual(report["sealed_release_status"], "sealed_clean_pass")
        self.assertEqual(report["release_package_mode"], "source_content_package")
        self.assertEqual(report["source_zip_policy_status"], "match")
        self.assertEqual(report["source_zip"]["status"], "match")
        self.assertEqual(report["batch_verify"]["status"], "pass")
        self.assertEqual(report["batch_verify"]["authority_schema_status"], "current")
        self.assertEqual(report["test_evidence"]["primary_suite_scope"], "report_contract_summary")
        self.assertEqual(report["test_evidence"]["full_suite_status"], "pass")
        self.assertEqual(report["tmp_json_policy_status"], "clean")
        self.assertEqual(report["tmp_json_count"], 0)
        self.assertEqual(report["artifact_digest_policy_status"], "match")
        self.assertEqual(report["artifact_digest_mismatch_count"], 0)
        self.assertEqual(report["artifact_digest_missing_count"], 0)
        self.assertEqual(report["learning_claim"]["confirmed_learning_improvement_status"], "not_ready")
        self.assertFalse(report["learning_claim"]["confirmed_wording_allowed"])
        self.assertEqual(report["learning_claim"]["confirmed_wording_policy_status"], "blocked")
        self.assertEqual(report["learning_claim"]["confirmed_evidence_summary"]["valid_run_count"], 0)
        self.assertEqual(report["learning_claim"]["confirmed_evidence_summary"]["min_required_run_count"], 0)
        self.assertEqual(
            report["learning_claim"]["confirmed_blocking_predicate_ids"],
            ["repeated_same_family_evidence"],
        )
        archived_v1 = json.loads(json.dumps(report))
        archived_v1_accepted_risk = archived_v1["accepted_risk"]
        archived_v1_accepted_risk.pop("gate_attention_codes")
        archived_v1_accepted_risk.pop("learning_claim_blocking_codes")
        archived_v1_accepted_risk.pop("advisory_lifecycle_codes")
        self.assertEqual(validate_with_schema(archived_v1, load_schema(SCHEMA_PATH)), [])
        self.assertIn("confirmed_learning=not_ready", report["operator_summary"])
        self.assertIn("valid_runs=0/0", report["operator_summary"])
        self.assertIn("eligible_families=0", report["operator_summary"])
        self.assertIn("rejected_runs=0", report["operator_summary"])
        self.assertIn("confirmed_blockers=repeated_same_family_evidence", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_blocks_confirmed_wording_when_bundle_or_cohort_is_not_active(self) -> None:
        scoreboard_path = self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        scoreboard["summary"].update(
            {
                "claim_level": "confirmed_learning_improvement",
                "bounded_learning_claim_allowed": True,
                "confirmed_learning_improvement_allowed": True,
                "confirmed_learning_improvement_status": "auto_confirmed",
                "confirmed_blocking_predicate_ids": [],
                "learning_claim_evidence_bundle_status": "stale",
                "learning_claim_evidence_bundle_sha256": "b" * 64,
                "learning_confirmed_evidence_cohort_status": "revoked",
                "learning_confirmed_evidence_cohort_sha256": "c" * 64,
            }
        )
        scoreboard["confirmed_evidence_summary"] = {
            "confirmed_evidence_status": "auto_confirmed",
            "valid_run_count": 3,
            "min_required_run_count": 3,
            "eligible_family_count": 1,
            "selected_valid_run_ids": ["run-a", "run-b", "run-c"],
            "blocking_predicate_ids": [],
            "rejected_run_count": 0,
            "rejected_run_diagnostics": [],
        }
        scoreboard_path.write_text(json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertFalse(report["learning_claim"]["confirmed_wording_allowed"])
        self.assertEqual(report["learning_claim"]["confirmed_wording_policy_status"], "blocked")
        self.assertNotIn("confirmed learning improvement allowed", report["operator_summary"].lower())
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_surfaces_legacy_reconstruction_audit_summary(self) -> None:
        scoreboard_path = self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        scoreboard["confirmed_evidence_summary"] = {
            "confirmed_evidence_status": "auto_confirmed",
            "valid_run_count": 3,
            "min_required_run_count": 3,
            "eligible_family_count": 1,
            "selected_valid_run_ids": ["run-a", "run-b", "legacy-promote"],
            "blocking_predicate_ids": [],
            "rejected_run_count": 0,
            "rejected_run_diagnostics": [],
            "legacy_reconstruction_summary": {
                "status": "pass",
                "reconstruction_needed_count": 1,
                "reconstructed_run_count": 1,
                "blocked_run_count": 0,
                "run_diagnostics": [
                    {
                        "run_id": "legacy-promote",
                        "families": ["contract_regression_signals"],
                        "reconstruction_status": "reconstructed",
                        "selection_reason": "selected_from_mechanism_review_candidates_for_active_same_eval_family",
                        "reconstruction_reasons": ["telemetry behavior_delta_digest missing or invalid"],
                        "secondary_axis_evidence_source": "legacy_reconstruction_artifact",
                        "secondary_axis_evidence_detail": "selected_axes=['candidate_eval']",
                        "parsed_secondary_axes": ["candidate_eval"],
                    }
                ],
            },
        }
        scoreboard_path.write_text(json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        legacy_summary = report["learning_claim"]["confirmed_evidence_summary"]["legacy_reconstruction_summary"]
        self.assertEqual(legacy_summary["status"], "pass")
        self.assertEqual(legacy_summary["reconstructed_run_count"], 1)
        self.assertEqual(legacy_summary["run_diagnostics"][0]["run_id"], "legacy-promote")
        self.assertIn("legacy_reconstruction=pass", report["operator_summary"])
        self.assertIn("legacy_reconstructed_runs=1/1", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_rejects_sealed_status_without_distribution_package(self) -> None:
        batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch.pop("distribution_package")
        batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["sealed_release_status"], "unsealed_distribution_not_provided")
        self.assertEqual(report["release_package_mode"], "local_workspace")
        self.assertEqual(report["source_zip_policy_status"], "not_provided")
        self.assertEqual(report["source_zip"]["distribution_status"], "not_provided")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_tmp_json_or_missing_full_suite_demotes_operator_summary_to_attention(self) -> None:
        self.temp_dir.cleanup()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._seed_release_reports(full_summary=False)
        (self.vault / "tmp").mkdir()
        self._write_json("tmp/release-evidence-dashboard.candidate.json", {"candidate": True})

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["sealed_release_status"], "blocked_tmp_json")
        self.assertEqual(report["tmp_json_policy_status"], "dirty")
        self.assertEqual(report["tmp_json_count"], 1)
        self.assertEqual(report["artifact_digest_policy_status"], "match")
        self.assertEqual(report["test_evidence"]["full_suite_status"], "not_run")
        self.assertIn("full-suite summary artifact is missing", report["test_evidence"]["full_suite_reason"])
        self.assertTrue(report["learning_readiness"]["release_effect"]["operator_summary"])

    def test_operator_summary_surfaces_tmp_dirty_and_artifact_mismatch_as_separate_axes(self) -> None:
        self._write_json("tmp/release-evidence-dashboard.candidate.json", {"candidate": True})
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {"artifact_kind": "release_evidence_dashboard", "status": "drifted"},
        )
        batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["artifacts"].append(
            self._artifact_record("ops/reports/release-evidence-dashboard.json")
        )
        self._write_json(
            "ops/reports/release-evidence-dashboard.json",
            {"artifact_kind": "release_evidence_dashboard", "status": "changed"},
        )
        batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["sealed_release_status"], "blocked_tmp_json")
        self.assertEqual(report["tmp_json_policy_status"], "dirty")
        self.assertEqual(report["tmp_json_count"], 1)
        self.assertEqual(report["artifact_digest_policy_status"], "mismatch")
        self.assertEqual(report["artifact_digest_mismatch_count"], 1)
        self.assertEqual(report["artifact_digest_missing_count"], 0)
        self.assertEqual(report["source_zip_policy_status"], "match")
        self.assertIn("source_zip=match", report["operator_summary"])
        self.assertIn("artifact_digest=mismatch", report["operator_summary"])
        self.assertIn("tmp_json=1", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_surfaces_source_zip_digest_drift_as_separate_axis(self) -> None:
        (self.vault / "build" / "release" / "LLMwiki-source.zip").write_bytes(b"changed source zip")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["source_zip_policy_status"], "drift")
        self.assertFalse(report["source_zip"]["file_digest_matches_batch"])
        self.assertEqual(report["tmp_json_policy_status"], "clean")
        self.assertEqual(report["artifact_digest_policy_status"], "match")
        self.assertIn("source_zip=drift", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_v1_batch_manifest_is_not_reused_as_current_authority(self) -> None:
        path = self.vault / "ops/reports/release-closeout-batch-manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = 1
        path.write_text(json.dumps(payload), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["batch_verify"]["status"], "fail")
        self.assertEqual(
            report["batch_verify"]["authority_schema_status"], "unsupported"
        )
        self.assertEqual(report["status"], "attention")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_batch_manifest_v2_requires_exact_integer_type(self) -> None:
        path = self.vault / "ops/reports/release-closeout-batch-manifest.json"
        baseline = json.loads(path.read_text(encoding="utf-8"))

        for invalid_version in ("2", True):
            with self.subTest(schema_version=invalid_version):
                payload = {**baseline, "schema_version": invalid_version}
                path.write_text(json.dumps(payload), encoding="utf-8")

                report = build_report(self.vault, context=fixed_context())

                self.assertEqual(report["batch_verify"]["status"], "fail")
                self.assertEqual(report["batch_verify"]["manifest_schema_version"], 0)
                self.assertEqual(report["artifact_digest_policy_status"], "unknown")
                self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_content_binding_allows_envelope_raw_drift_but_rejects_semantic_drift(self) -> None:
        artifact_path = self.vault / "ops/reports/release-closeout-summary.json"
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        payload.update({"generated_at": "2026-05-05T00:00:00Z", "source_revision": "new-revision"})
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")

        envelope_drift = build_report(self.vault, context=fixed_context())

        self.assertEqual(envelope_drift["batch_verify"]["status"], "pass")

        payload["machine_release_allowed"] = False
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")

        semantic_drift = build_report(self.vault, context=fixed_context())

        self.assertEqual(semantic_drift["batch_verify"]["status"], "fail")
        mismatch = semantic_drift["batch_verify"]["mismatches"][0]
        self.assertEqual(mismatch["binding_mode"], "content")
        self.assertEqual(mismatch["reason"], "binding_digest_mismatch")

    def test_raw_binding_rejects_byte_only_drift(self) -> None:
        batch_path = self.vault / "ops/reports/release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        tracked_path = "ops/reports/release-closeout-summary.json"
        batch["artifacts"][0] = self._artifact_record(tracked_path, binding_mode="raw")
        batch_path.write_text(json.dumps(batch), encoding="utf-8")
        artifact_path = self.vault / tracked_path
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["batch_verify"]["status"], "fail")
        self.assertEqual(report["batch_verify"]["mismatches"][0]["binding_mode"], "raw")

    def test_missing_binding_metadata_never_falls_back_to_raw_digest(self) -> None:
        batch_path = self.vault / "ops/reports/release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["artifacts"][0].pop("binding_digest")
        batch_path.write_text(json.dumps(batch), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["batch_verify"]["status"], "fail")
        mismatch = report["batch_verify"]["mismatches"][0]
        self.assertEqual(mismatch["reason"], "binding_metadata_invalid")
        self.assertEqual(mismatch["actual_binding_digest"], "not_checked")
        self.assertEqual(mismatch["declared_raw_digest"], batch["artifacts"][0]["raw_digest"])

    def test_invalid_binding_digest_never_falls_back_to_raw_digest(self) -> None:
        batch_path = self.vault / "ops/reports/release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["artifacts"][0]["binding_digest"] = "not-a-digest"
        batch_path.write_text(json.dumps(batch), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        mismatch = report["batch_verify"]["mismatches"][0]
        self.assertEqual(mismatch["reason"], "binding_metadata_invalid")
        self.assertEqual(mismatch["actual_binding_digest"], "not_checked")

    def test_operator_summary_uses_clean_lane_blocking_count_from_closeout(self) -> None:
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "artifact_kind": "release_closeout_summary",
                "release_readiness_state": "conditional_pass",
                "machine_release_allowed": False,
                "clean_lane_blocking_risk_family_count": 2,
                "summary": {"accepted_risk_family_count": 3},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["accepted_risk"]["operator_accepted_risk_family_count"], 3)
        self.assertEqual(report["accepted_risk"]["clean_lane_blocking_accepted_risk_family_count"], 2)
        self.assertEqual(report["accepted_risk"]["accepted_risk_count"], 0)
        self.assertEqual(report["accepted_risk"]["release_accepted_risk_count"], 2)
        self.assertEqual(report["accepted_risk"]["accepted_learning_risk_count"], 0)
        self.assertEqual(report["accepted_risk"]["gate_attention_count"], 0)
        self.assertEqual(report["accepted_risk"]["learning_claim_blocking_family_count"], 0)
        self.assertEqual(report["accepted_risk"]["advisory_lifecycle_family_count"], 0)
        self.assertEqual(report["accepted_risk"]["gate_attention_codes"], [])
        self.assertEqual(report["accepted_risk"]["learning_claim_blocking_codes"], [])
        self.assertEqual(report["accepted_risk"]["advisory_lifecycle_codes"], [])
        sources = report["accepted_risk"]["count_sources"]
        self.assertEqual(
            sources["operator_accepted_risk_family_count"]["field_path"],
            "$.summary.accepted_risk_family_count",
        )
        self.assertEqual(
            sources["clean_lane_blocking_accepted_risk_family_count"]["field_path"],
            "$.clean_lane_blocking_risk_family_count",
        )
        self.assertIn(
            "operator_signoff",
            sources["clean_lane_blocking_accepted_risk_family_count"]["excluded_scopes"],
        )
        self.assertNotIn("dashboard_attention_gate_count", sources)

    def test_operator_summary_prefers_closeout_status_v2_over_legacy_readiness(self) -> None:
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "artifact_kind": "release_closeout_summary",
                "status": "pass",
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
                "operator_release_allowed": False,
                "status_v2": {
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
                "summary": {"accepted_risk_family_count": 3},
            },
        )
        batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch.pop("semantic_release_status")
        batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        learning_path = self.vault / "ops" / "reports" / "learning-readiness-signoff-revalidation.json"
        learning = json.loads(learning_path.read_text(encoding="utf-8"))
        learning["closeout"] = {
            "release_readiness_state": "clean_pass",
            "machine_release_allowed": True,
            "operator_release_allowed": False,
            "accepted_learning_risk": False,
            "status_v2": {
                "schema_version": 2,
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
        }
        learning["release_effect"]["operator_summary"] = ""
        learning_path.write_text(json.dumps(learning, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["semantic_release_status"], "conditional_pass")
        self.assertEqual(report["accepted_risk"]["operator_accepted_risk_family_count"], 3)
        self.assertEqual(report["accepted_risk"]["clean_lane_blocking_accepted_risk_family_count"], 3)
        learning_summary = report["learning_readiness"]["release_effect"]["operator_summary"]
        self.assertIn("release_authority_status=conditional_pass", learning_summary)
        self.assertIn("machine_release_allowed=False", learning_summary)
        self.assertIn("operator_release_allowed=True", learning_summary)
        self.assertNotIn("release_readiness_state=clean_pass", learning_summary)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_separates_accepted_risks_from_gate_attention_and_lane_counts(self) -> None:
        batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["release_decision_snapshot"].update(
            {
                "accepted_risk_count": 0,
                "gate_attention_count": 1,
                "learning_claim_blocking_family_count": 2,
                "advisory_lifecycle_family_count": 3,
            }
        )
        batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["accepted_risk"]["accepted_risk_count"], 0)
        self.assertEqual(report["accepted_risk"]["release_accepted_risk_count"], 0)
        self.assertEqual(report["accepted_risk"]["accepted_learning_risk_count"], 0)
        self.assertEqual(report["accepted_risk"]["gate_attention_count"], 1)
        self.assertNotIn("dashboard_attention_gate_count", report["accepted_risk"])
        self.assertEqual(report["accepted_risk"]["learning_claim_blocking_family_count"], 2)
        self.assertEqual(report["accepted_risk"]["advisory_lifecycle_family_count"], 3)
        self.assertIn("release_risk_acceptances=0", report["operator_summary"])
        self.assertIn("learning_risk_acceptances=0", report["operator_summary"])
        self.assertNotIn("accepted_risks=0", report["operator_summary"])
        self.assertIn("gate_attention=1", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_emits_deduplicated_closeout_identity_codes(self) -> None:
        closeout_path = self.vault / "ops/reports/release-closeout-summary.json"
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        learning_issue = {
            "code": "promotion_blocked_by_release_batch_manifest_failure",
            "learning_lane_effect": "blocks_learning_claim",
            "advisory_lifecycle_effect": "not_applicable",
        }
        advisory_issue = {
            "code": "archive_review_backlog",
            "learning_lane_effect": "not_applicable",
            "advisory_lifecycle_effect": "review_backlog",
        }
        closeout["blockers"] = [learning_issue, learning_issue.copy()]
        closeout["accepted_risks"] = [advisory_issue, advisory_issue.copy()]
        self._write_json("ops/reports/release-closeout-summary.json", closeout)

        report = build_report(self.vault, context=fixed_context())

        accepted_risk = report["accepted_risk"]
        self.assertEqual(
            accepted_risk["gate_attention_codes"],
            ["archive_review_backlog", "promotion_blocked_by_release_batch_manifest_failure"],
        )
        self.assertEqual(
            accepted_risk["learning_claim_blocking_codes"],
            ["promotion_blocked_by_release_batch_manifest_failure"],
        )
        self.assertEqual(
            accepted_risk["advisory_lifecycle_codes"],
            ["archive_review_backlog"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_keeps_total_accepted_risks_out_of_release_blockers(self) -> None:
        learning_path = self.vault / "ops" / "reports" / "learning-readiness-signoff-revalidation.json"
        learning = json.loads(learning_path.read_text(encoding="utf-8"))
        learning["closeout"]["accepted_learning_risk"] = True
        learning_path.write_text(json.dumps(learning, ensure_ascii=False, indent=2), encoding="utf-8")
        batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["release_decision_snapshot"]["accepted_risk_count"] = 2
        batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["accepted_risk"]["accepted_risk_count"], 2)
        self.assertEqual(report["accepted_risk"]["release_accepted_risk_count"], 0)
        self.assertEqual(report["accepted_risk"]["accepted_learning_risk_count"], 1)
        self.assertTrue(report["learning_readiness"]["accepted_learning_risk"])
        self.assertIn("release_risk_acceptances=0", report["operator_summary"])
        self.assertIn("learning_risk_acceptances=1", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_operator_summary_uses_release_blocking_count_for_release_acceptances(self) -> None:
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                "artifact_kind": "release_closeout_summary",
                "release_blocking_family_count": 1,
                "clean_lane_blocking_risk_family_count": 2,
                "summary": {"accepted_risk_family_count": 3},
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["accepted_risk"]["release_accepted_risk_count"], 2)
        self.assertIn("release_risk_acceptances=2", report["operator_summary"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_main_writes_report_without_failing_attention_by_default(self) -> None:
        self._write_json("tmp/codex-plan-review/release-evidence-dashboard.candidate.json", {"candidate": True})
        self._write_json("tmp/_patch_vocab_refs.py", {"candidate": True})

        exit_code = main(["--vault", self.vault.as_posix(), "--out", "ops/operator/operator-release-summary.json"])

        self.assertEqual(exit_code, 0)
        destination = self.vault / "ops" / "operator" / "operator-release-summary.json"
        self.assertTrue(destination.exists())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "attention")
        self.assertEqual(persisted["batch_verify"]["tmp_json_count"], 2)
        self.assertIn(
            "tmp/codex-plan-review/release-evidence-dashboard.candidate.json",
            persisted["batch_verify"]["tmp_json_paths"],
        )
        self.assertIn("tmp/_patch_vocab_refs.py", persisted["batch_verify"]["tmp_json_paths"])

    def test_main_can_read_zip_bound_sidecar_batch_manifest(self) -> None:
        default_batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        sidecar_batch_path = self.vault / "build" / "release" / "release-closeout-batch-manifest.json"
        sidecar_batch_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_batch_path.write_text(default_batch_path.read_text(encoding="utf-8"), encoding="utf-8")

        default_batch = json.loads(default_batch_path.read_text(encoding="utf-8"))
        default_batch["sealed_release_status"] = "unsealed_distribution_not_provided"
        default_batch["distribution_package"] = {"status": "not_provided"}
        default_batch_path.write_text(json.dumps(default_batch, ensure_ascii=False, indent=2), encoding="utf-8")

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "build/release/operator-release-summary.json",
                "--batch-manifest",
                "build/release/release-closeout-batch-manifest.json",
            ]
        )

        self.assertEqual(exit_code, 0)
        persisted = json.loads(
            (self.vault / "build" / "release" / "operator-release-summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(persisted["status"], "pass")
        self.assertEqual(persisted["sealed_release_status"], "sealed_clean_pass")
        self.assertEqual(persisted["source_zip_policy_status"], "match")
        self.assertEqual(
            persisted["source_load_status"]["batch_manifest"],
            "ok",
        )
        self.assertIn(
            "--batch-manifest build/release/release-closeout-batch-manifest.json",
            persisted["source_command"],
        )

    def test_main_can_fail_attention_for_strict_gate_usage(self) -> None:
        self._write_json("tmp/release-evidence-dashboard.candidate.json", {"candidate": True})

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "ops/operator/operator-release-summary.json",
                "--fail-on-attention",
            ]
        )

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
