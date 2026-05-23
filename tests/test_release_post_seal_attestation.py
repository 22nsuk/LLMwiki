from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ops.scripts.release_post_seal_attestation import build_attestation, verify_attestation, write_attestation
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-post-seal-attestation.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 8, 2, 0, tzinfo=dt.timezone.utc),
    )


class ReleasePostSealAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "build" / "release").mkdir(parents=True, exist_ok=True)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self.source_zip = self.vault / "build" / "release" / "LLMwiki-source.zip"
        self._write_source_zip_with_pre_seal_description()
        self.source_zip_sha256 = hashlib.sha256(self.source_zip.read_bytes()).hexdigest()
        self.evidence_set_digest = "a" * 64
        self.learning_bundle_sha256 = "b" * 64
        self.learning_cohort_sha256 = "c" * 64
        self._write_release_authority_reports()
        self._write_learning_reports()
        self._write_operator_summary()

    def _write_source_zip_with_pre_seal_description(self) -> None:
        with zipfile.ZipFile(self.source_zip, "w") as archive:
            archive.writestr("LLMwiki/README.md", "source\n")
            archive.writestr(
                "LLMwiki/release-archive-self-description.json",
                json.dumps(
                    {
                        "artifact_kind": "release_archive_self_description",
                        "evidence_linkage": {
                            "linkage_phase": "pre_seal_package_build_snapshot",
                            "post_seal_authority": "ops/reports/release-closeout-batch-manifest.json",
                            "linked_artifacts": [
                                {
                                    "path": "ops/reports/release-closeout-batch-manifest.json",
                                    "exists": True,
                                    "included_in_zip": False,
                                    "sha256": "0" * 64,
                                    "size_bytes": 1,
                                },
                                {
                                    "path": "ops/reports/release-evidence-closeout-self-check.json",
                                    "exists": True,
                                    "included_in_zip": False,
                                    "sha256": "0" * 64,
                                    "size_bytes": 1,
                                },
                                {
                                    "path": "ops/operator/operator-release-summary.json",
                                    "exists": True,
                                    "included_in_zip": False,
                                    "sha256": "0" * 64,
                                    "size_bytes": 1,
                                },
                                {
                                    "path": "ops/reports/learning-claim-evidence-bundle.json",
                                    "exists": True,
                                    "included_in_zip": False,
                                    "sha256": "0" * 64,
                                    "size_bytes": 1,
                                },
                                {
                                    "path": "ops/reports/learning-confirmed-evidence-cohort.json",
                                    "exists": True,
                                    "included_in_zip": False,
                                    "sha256": "0" * 64,
                                    "size_bytes": 1,
                                },
                                {
                                    "path": "ops/reports/learning-delta-scoreboard.json",
                                    "exists": True,
                                    "included_in_zip": False,
                                    "sha256": "0" * 64,
                                    "size_bytes": 1,
                                },
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
            )

    def _write_release_authority_reports(self) -> None:
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.release_closeout_batch_manifest",
                "status": "fail",
                "release_authority_status": "blocked",
                "semantic_release_status": "blocked",
                "sealed_release_status": "unsealed_release_blocked",
                "machine_release_status": "blocked",
                "operator_release_status": "blocked",
                "distribution_package": {
                    "status": "materialized",
                    "path": "build/release/LLMwiki-source.zip",
                    "sha256": self.source_zip_sha256,
                },
                "audit_materialization": {"evidence_set_digest": self.evidence_set_digest},
                "release_decision_snapshot": {
                    "accepted_risk_count": 2,
                    "advisory_lifecycle_family_count": 1,
                    "accepted_risks": [],
                },
            },
        )
        self._write_report(
            "ops/reports/release-evidence-closeout-self-check.json",
            {
                "artifact_kind": "release_evidence_closeout_self_check",
                "producer": "tests.release_evidence_closeout_self_check",
                "status": {"result": "pass"},
                "batch_artifact_digest_watch": {"status": "match"},
            },
        )
        self._write_report(
            "ops/reports/public-check-summary.json",
            {
                "artifact_kind": "public_check_summary",
                "producer": "tests.public_check_summary",
                "status": "pass",
            },
        )

    def _write_learning_reports(self) -> None:
        self._write_report(
            "ops/reports/learning-claim-evidence-bundle.json",
            {
                "artifact_kind": "learning_claim_evidence_bundle",
                "producer": "tests.learning_claim_evidence_bundle",
                "status": "pass",
                "summary": {
                    "revocation_status": "active",
                    "bundle_sha256": self.learning_bundle_sha256,
                },
                "bundle_identity": {
                    "evidence_bundle_digest": self.learning_bundle_sha256,
                },
            },
        )
        self.learning_bundle_report_sha256 = self._sha("ops/reports/learning-claim-evidence-bundle.json")
        self._write_report(
            "ops/reports/learning-confirmed-evidence-cohort.json",
            {
                "artifact_kind": "learning_confirmed_evidence_cohort",
                "producer": "tests.learning_confirmed_evidence_cohort",
                "status": "pass",
                "summary": {
                    "confirmed_evidence_status": "auto_confirmed",
                    "confirmed_learning_improvement_allowed": True,
                    "valid_run_count": 3,
                    "min_required_run_count": 3,
                    "eligible_family_count": 1,
                    "selected_valid_run_ids": ["run-a", "run-b", "run-c"],
                },
                "cohort_identity": {
                    "cohort_digest": self.learning_cohort_sha256,
                },
            },
        )
        self.learning_cohort_report_sha256 = self._sha("ops/reports/learning-confirmed-evidence-cohort.json")
        self._write_report(
            "ops/reports/learning-delta-scoreboard.json",
            {
                "artifact_kind": "learning_delta_scoreboard",
                "producer": "tests.learning_delta_scoreboard",
                "status": "pass",
                "summary": {
                    "claim_level": "confirmed_learning_improvement",
                    "confirmed_learning_improvement_status": "auto_confirmed",
                    "confirmed_learning_improvement_allowed": True,
                    "learning_claim_evidence_bundle_status": "active",
                    "learning_claim_evidence_bundle_sha256": self.learning_bundle_sha256,
                    "learning_confirmed_evidence_cohort_status": "active",
                    "learning_confirmed_evidence_cohort_sha256": self.learning_cohort_sha256,
                },
                "learning_claim_unlock_review": {
                    "bundle_sha256": self.learning_bundle_sha256,
                    "confirmed_evidence_cohort_sha256": self.learning_cohort_sha256,
                },
            },
        )

    def _write_operator_summary(self) -> None:
        self._write_report(
            "ops/operator/operator-release-summary.json",
            {
                "artifact_kind": "operator_release_summary",
                "producer": "tests.operator_release_summary",
                "status": "attention",
                "source_zip": {
                    "status": "match",
                    "path": "build/release/LLMwiki-source.zip",
                    "sha256": self.source_zip_sha256,
                    "actual_sha256": self.source_zip_sha256,
                },
                "batch_verify": {"status": "pass"},
                "artifact_digest_policy_status": "match",
                "test_evidence": {
                    "full_suite_status": "pass",
                },
                "learning_readiness": {
                    "revalidation_status": "missing_signoff",
                    "accepted_learning_risk": False,
                },
                "learning_claim": {
                    "claim_level": "confirmed_learning_improvement",
                    "bounded_learning_claim_allowed": True,
                    "confirmed_learning_improvement_allowed": True,
                    "confirmed_learning_improvement_status": "auto_confirmed",
                    "confirmed_blocking_predicate_ids": [],
                    "confirmed_evidence_summary": {
                        "confirmed_evidence_status": "auto_confirmed",
                        "valid_run_count": 3,
                        "min_required_run_count": 3,
                        "eligible_family_count": 1,
                        "selected_valid_run_ids": ["run-a", "run-b", "run-c"],
                        "blocking_predicate_ids": [],
                        "rejected_run_count": 0,
                        "rejected_run_diagnostics": [],
                    },
                    "confirmed_predicate_results": [],
                    "learning_claim_evidence_bundle_status": "active",
                    "learning_claim_evidence_bundle_sha256": self.learning_bundle_sha256,
                    "learning_confirmed_evidence_cohort_status": "active",
                    "learning_confirmed_evidence_cohort_sha256": self.learning_cohort_sha256,
                    "confirmed_wording_allowed": False,
                    "confirmed_wording_policy_status": "blocked",
                    "confirmed_wording_policy_reason": (
                        "release authority is intentionally blocked in this fixture"
                    ),
                },
                "accepted_risk": {
                    "accepted_risk_count": 2,
                    "release_accepted_risk_count": 2,
                    "accepted_learning_risk_count": 0,
                    "clean_lane_blocking_accepted_risk_family_count": 1,
                    "advisory_lifecycle_family_count": 1,
                },
                "operator_summary": "intentionally stale human summary that must not be parsed",
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_report(self, rel_path: str, payload: dict[str, object]) -> None:
        report = {
            "generated_at": "2026-05-08T01:00:00Z",
            "source_tree_fingerprint": "test-source-tree",
            **payload,
        }
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sha(self, rel_path: str) -> str:
        return hashlib.sha256((self.vault / rel_path).read_bytes()).hexdigest()

    def _enable_pre_seal_confirmed_wording(self) -> None:
        operator_path = self.vault / "ops" / "operator" / "operator-release-summary.json"
        operator = json.loads(operator_path.read_text(encoding="utf-8"))
        operator["learning_readiness"]["revalidation_status"] = "current"
        operator["learning_claim"]["confirmed_wording_allowed"] = True
        operator["learning_claim"]["confirmed_wording_policy_status"] = "pre_seal_ready"
        operator_path.write_text(json.dumps(operator, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_post_seal_sidecar_copy(self, source_rel_path: str, sidecar_rel_path: str) -> str:
        source_path = self.vault / source_rel_path
        sidecar_path = self.vault / sidecar_rel_path
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        payload["generated_at"] = "2026-05-08T01:30:00Z"
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return hashlib.sha256(sidecar_path.read_bytes()).hexdigest()

    def test_post_seal_attestation_binds_batch_self_check_operator_and_source_zip(self) -> None:
        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "pass")
        self.assertFalse(attestation["sidecar"]["included_in_source_zip"])
        self.assertEqual(attestation["bindings"]["source_zip_sha256"], self.source_zip_sha256)
        self.assertEqual(attestation["bindings"]["batch_distribution_zip_sha256"], self.source_zip_sha256)
        self.assertEqual(attestation["bindings"]["evidence_set_digest"], self.evidence_set_digest)
        self.assertEqual(
            attestation["bindings"]["learning_claim_evidence_bundle_sha256"],
            self.learning_bundle_report_sha256,
        )
        self.assertEqual(
            attestation["bindings"]["learning_confirmed_evidence_cohort_sha256"],
            self.learning_cohort_report_sha256,
        )
        self.assertEqual(attestation["release_authority"]["semantic_release_status"], "blocked")
        self.assertEqual(attestation["release_authority"]["operator_summary_status"], "attention")
        self.assertEqual(attestation["release_authority"]["full_suite_status"], "pass")
        self.assertEqual(attestation["release_authority"]["learning_revalidation_status"], "missing_signoff")
        self.assertEqual(attestation["release_authority"]["accepted_risk_count"], 2)
        self.assertEqual(attestation["release_authority"]["release_accepted_risk_count"], 2)
        self.assertEqual(attestation["release_authority"]["accepted_learning_risk_count"], 0)
        self.assertEqual(attestation["release_authority"]["clean_lane_blocking_accepted_risk_family_count"], 1)
        self.assertEqual(attestation["release_authority"]["advisory_lifecycle_family_count"], 1)
        claim_authority = attestation["learning_claim_authority"]
        self.assertEqual(claim_authority["claim_level"], "confirmed_learning_improvement")
        self.assertEqual(claim_authority["confirmed_learning_improvement_status"], "auto_confirmed")
        self.assertEqual(claim_authority["learning_claim_evidence_bundle_sha256"], self.learning_bundle_sha256)
        self.assertEqual(
            claim_authority["learning_confirmed_evidence_cohort_sha256"],
            self.learning_cohort_sha256,
        )
        self.assertEqual(claim_authority["valid_run_count"], 3)
        self.assertEqual(claim_authority["min_required_run_count"], 3)
        self.assertEqual(claim_authority["eligible_family_count"], 1)
        self.assertEqual(claim_authority["selected_valid_run_ids"], ["run-a", "run-b", "run-c"])
        self.assertFalse(claim_authority["no_human_confirmed_wording_allowed"])
        linkage = attestation["pre_seal_post_seal_linkage"]
        self.assertEqual(linkage["status"], "pass")
        self.assertEqual(linkage["self_description_status"], "present")
        self.assertEqual(linkage["linkage_phase"], "pre_seal_package_build_snapshot")
        self.assertEqual(linkage["drift_count"], 6)
        self.assertEqual(linkage["missing_required_link_count"], 0)
        self.assertEqual(linkage["current_missing_count"], 0)
        self.assertEqual(linkage["binding_mismatch_count"], 0)
        self.assertIn(
            "ops/reports/learning-claim-evidence-bundle.json",
            linkage["required_linked_artifact_paths"],
        )
        self.assertEqual(
            {artifact["linkage_status"] for artifact in linkage["artifacts"]},
            {"drift"},
        )
        for artifact in linkage["artifacts"]:
            self.assertEqual(artifact["pre_seal_observed_sha256"], "0" * 64)
            self.assertEqual(len(artifact["current_post_seal_sha256"]), 64)
            self.assertEqual(
                artifact["authoritative_post_seal_digest_source"],
                f"reports.{Path(artifact['path']).stem.replace('-', '_')}.sha256",
            )
            self.assertTrue(artifact["binding_matches_current"])
        reason_codes = {item["code"] for item in attestation["release_authority"]["blocking_reasons"]}
        self.assertIn("learning_revalidation_not_current", reason_codes)
        self.assertIn("clean_lane_blocking_accepted_risk", reason_codes)
        self.assertIn("advisory_lifecycle_backlog", reason_codes)
        self.assertNotIn(
            "intentionally stale human summary that must not be parsed",
            json.dumps(attestation["release_authority"]["blocking_reasons"], ensure_ascii=False),
        )
        self.assertEqual(attestation["verification"]["failed_checks"], [])
        self.assertEqual(validate_with_schema(attestation, load_schema(SCHEMA_PATH)), [])

        destination = write_attestation(
            self.vault,
            attestation,
            "build/release/release-post-seal-attestation.json",
        )
        verified = verify_attestation(
            self.vault,
            attestation_path="build/release/release-post-seal-attestation.json",
        )
        self.assertEqual(destination, (self.vault / "build" / "release" / "release-post-seal-attestation.json"))
        self.assertEqual(verified["status"], "pass")

    def test_sidecar_batch_and_operator_reports_do_not_bind_canonical_pre_seal_paths(self) -> None:
        batch_sidecar_sha = self._write_post_seal_sidecar_copy(
            "ops/reports/release-closeout-batch-manifest.json",
            "build/release/release-closeout-batch-manifest.json",
        )
        operator_sidecar_sha = self._write_post_seal_sidecar_copy(
            "ops/operator/operator-release-summary.json",
            "build/release/operator-release-summary.json",
        )

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            batch_manifest_path="build/release/release-closeout-batch-manifest.json",
            operator_summary_path="build/release/operator-release-summary.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "pass")
        self.assertEqual(
            attestation["reports"]["release_closeout_batch_manifest"]["path"],
            "build/release/release-closeout-batch-manifest.json",
        )
        self.assertEqual(
            attestation["reports"]["operator_release_summary"]["path"],
            "build/release/operator-release-summary.json",
        )
        self.assertEqual(attestation["bindings"]["release_closeout_batch_manifest_sha256"], batch_sidecar_sha)
        self.assertEqual(attestation["bindings"]["operator_release_summary_sha256"], operator_sidecar_sha)
        linkage = attestation["pre_seal_post_seal_linkage"]
        self.assertEqual(linkage["status"], "pass")
        self.assertEqual(linkage["binding_mismatch_count"], 0)
        artifacts_by_path = {artifact["path"]: artifact for artifact in linkage["artifacts"]}
        batch_link = artifacts_by_path["ops/reports/release-closeout-batch-manifest.json"]
        operator_link = artifacts_by_path["ops/operator/operator-release-summary.json"]
        self.assertEqual(batch_link["authoritative_post_seal_digest_source"], "current_file")
        self.assertEqual(operator_link["authoritative_post_seal_digest_source"], "current_file")
        self.assertEqual(batch_link["binding_sha256"], "")
        self.assertEqual(operator_link["binding_sha256"], "")
        self.assertTrue(batch_link["binding_matches_current"])
        self.assertTrue(operator_link["binding_matches_current"])
        self.assertEqual(attestation["verification"]["failed_checks"], [])

    def test_release_authority_requires_typed_blocking_fields(self) -> None:
        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )
        attestation["release_authority"].pop("blocking_reasons")
        attestation["release_authority"].pop("full_suite_status")

        errors = validate_with_schema(attestation, load_schema(SCHEMA_PATH))

        self.assertIn("$.release_authority: missing required property 'blocking_reasons'", errors)
        self.assertIn("$.release_authority: missing required property 'full_suite_status'", errors)

    def test_attestation_requires_pre_seal_post_seal_linkage(self) -> None:
        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )
        attestation.pop("pre_seal_post_seal_linkage")

        errors = validate_with_schema(attestation, load_schema(SCHEMA_PATH))

        self.assertIn("$: missing required property 'pre_seal_post_seal_linkage'", errors)

    def test_attestation_fails_when_source_zip_self_description_omits_required_learning_linkage(self) -> None:
        with zipfile.ZipFile(self.source_zip) as archive:
            readme = archive.read("LLMwiki/README.md")
            self_description = json.loads(
                archive.read("LLMwiki/release-archive-self-description.json").decode("utf-8")
            )
        self_description["evidence_linkage"]["linked_artifacts"] = [
            artifact
            for artifact in self_description["evidence_linkage"]["linked_artifacts"]
            if artifact["path"] != "ops/reports/learning-delta-scoreboard.json"
        ]
        with zipfile.ZipFile(self.source_zip, "w") as archive:
            archive.writestr("LLMwiki/README.md", readme)
            archive.writestr(
                "LLMwiki/release-archive-self-description.json",
                json.dumps(self_description, ensure_ascii=False),
            )
        self.source_zip_sha256 = hashlib.sha256(self.source_zip.read_bytes()).hexdigest()
        manifest_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["distribution_package"]["sha256"] = self.source_zip_sha256
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        operator_path = self.vault / "ops" / "operator" / "operator-release-summary.json"
        operator = json.loads(operator_path.read_text(encoding="utf-8"))
        operator["source_zip"]["sha256"] = self.source_zip_sha256
        operator["source_zip"]["actual_sha256"] = self.source_zip_sha256
        operator_path.write_text(json.dumps(operator, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertEqual(attestation["pre_seal_post_seal_linkage"]["missing_required_link_count"], 1)
        self.assertEqual(
            attestation["pre_seal_post_seal_linkage"]["missing_required_linked_artifact_paths"],
            ["ops/reports/learning-delta-scoreboard.json"],
        )
        self.assertIn(
            "pre_seal_post_seal_required_links_present",
            attestation["verification"]["failed_checks"],
        )

    def test_operator_bundle_digest_drift_fails_learning_claim_authority_verification(self) -> None:
        operator_path = self.vault / "ops" / "operator" / "operator-release-summary.json"
        operator = json.loads(operator_path.read_text(encoding="utf-8"))
        operator["learning_claim"]["learning_claim_evidence_bundle_sha256"] = "d" * 64
        operator_path.write_text(json.dumps(operator, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertIn(
            "learning_claim_authority_operator_bundle_digest_match",
            attestation["verification"]["failed_checks"],
        )

    def test_bundle_identity_drift_fails_learning_claim_authority_verification(self) -> None:
        bundle_path = self.vault / "ops" / "reports" / "learning-claim-evidence-bundle.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle["bundle_identity"]["evidence_bundle_digest"] = "d" * 64
        bundle["summary"]["bundle_sha256"] = "d" * 64
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertEqual(
            attestation["learning_claim_authority"]["learning_claim_evidence_bundle_sha256"],
            "d" * 64,
        )
        self.assertEqual(
            attestation["learning_claim_authority"]["operator_learning_claim_evidence_bundle_sha256"],
            self.learning_bundle_sha256,
        )
        self.assertIn(
            "learning_claim_authority_operator_bundle_digest_match",
            attestation["verification"]["failed_checks"],
        )
        self.assertNotIn(
            "learning_claim_authority_scoreboard_operator_bundle_digest_match",
            attestation["verification"]["failed_checks"],
        )

    def test_cohort_identity_drift_fails_learning_claim_authority_verification(self) -> None:
        cohort_path = self.vault / "ops" / "reports" / "learning-confirmed-evidence-cohort.json"
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        cohort["cohort_identity"]["cohort_digest"] = "e" * 64
        cohort["summary"]["cohort_sha256"] = "e" * 64
        cohort_path.write_text(json.dumps(cohort, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertEqual(
            attestation["learning_claim_authority"]["learning_confirmed_evidence_cohort_sha256"],
            "e" * 64,
        )
        self.assertEqual(
            attestation["learning_claim_authority"]["operator_learning_confirmed_evidence_cohort_sha256"],
            self.learning_cohort_sha256,
        )
        self.assertIn(
            "learning_claim_authority_operator_cohort_digest_match",
            attestation["verification"]["failed_checks"],
        )
        self.assertNotIn(
            "learning_claim_authority_scoreboard_operator_cohort_digest_match",
            attestation["verification"]["failed_checks"],
        )

    def test_scoreboard_operator_digest_mismatch_fails_learning_claim_authority_verification(self) -> None:
        scoreboard_path = self.vault / "ops" / "reports" / "learning-delta-scoreboard.json"
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
        scoreboard["summary"]["learning_claim_evidence_bundle_sha256"] = "d" * 64
        scoreboard["summary"]["learning_confirmed_evidence_cohort_sha256"] = "e" * 64
        scoreboard["learning_claim_unlock_review"]["bundle_sha256"] = "d" * 64
        scoreboard["learning_claim_unlock_review"]["confirmed_evidence_cohort_sha256"] = "e" * 64
        scoreboard_path.write_text(json.dumps(scoreboard, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertEqual(
            attestation["learning_claim_authority"]["learning_claim_evidence_bundle_sha256"],
            self.learning_bundle_sha256,
        )
        self.assertEqual(
            attestation["learning_claim_authority"]["scoreboard_learning_claim_evidence_bundle_sha256"],
            "d" * 64,
        )
        self.assertIn(
            "learning_claim_authority_scoreboard_operator_bundle_digest_match",
            attestation["verification"]["failed_checks"],
        )
        self.assertIn(
            "learning_claim_authority_scoreboard_operator_cohort_digest_match",
            attestation["verification"]["failed_checks"],
        )
        self.assertNotIn(
            "learning_claim_authority_operator_bundle_digest_match",
            attestation["verification"]["failed_checks"],
        )
        self.assertNotIn(
            "learning_claim_authority_operator_cohort_digest_match",
            attestation["verification"]["failed_checks"],
        )

    def test_public_check_status_drift_closes_no_human_confirmed_wording(self) -> None:
        self._enable_pre_seal_confirmed_wording()
        public_check_path = self.vault / "ops" / "reports" / "public-check-summary.json"
        public_check = json.loads(public_check_path.read_text(encoding="utf-8"))
        public_check["status"] = "fail"
        public_check["summary"] = {"failed_gate": "public-check"}
        public_check_path.write_text(json.dumps(public_check, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        claim_authority = attestation["learning_claim_authority"]
        self.assertEqual(attestation["status"], "pass")
        self.assertEqual(claim_authority["public_check_status"], "fail")
        self.assertFalse(claim_authority["required_conditions"]["public_check_pass"])
        self.assertFalse(claim_authority["pre_seal_confirmed_wording_ready"])
        self.assertFalse(claim_authority["no_human_confirmed_wording_allowed"])
        self.assertEqual(attestation["verification"]["failed_checks"], [])

    def test_no_human_confirmed_wording_opens_only_after_post_seal_authority_passes(self) -> None:
        self._enable_pre_seal_confirmed_wording()

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "pass")
        self.assertTrue(attestation["learning_claim_authority"]["pre_seal_confirmed_wording_ready"])
        self.assertTrue(attestation["learning_claim_authority"]["no_human_confirmed_wording_allowed"])
        self.assertTrue(
            attestation["learning_claim_authority"]["required_conditions"]["post_seal_attestation_pass"]
        )

    def test_allowed_machine_release_status_is_not_reported_as_blocker(self) -> None:
        manifest_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["machine_release_status"] = "allowed"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            out_path="build/release/release-post-seal-attestation.json",
            context=fixed_context(),
        )
        reason_codes = {item["code"] for item in attestation["release_authority"]["blocking_reasons"]}

        self.assertNotIn("machine_release_not_allowed", reason_codes)


if __name__ == "__main__":
    unittest.main()
