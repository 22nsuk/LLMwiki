from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ops.scripts.release_live_artifact_attestation import (
    build_attestation,
    verify_attestation,
    write_attestation,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-live-artifact-attestation.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 7, 9, 0, tzinfo=dt.UTC),
    )


class ReleaseLiveArtifactAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / "tmp").mkdir(parents=True, exist_ok=True)
        self.source_zip = self.vault / "tmp" / "live-source.zip"
        self.evidence_bundle = self.vault / "tmp" / "release-evidence-bundle.zip"
        self.evidence_set_digest = "e" * 64
        with zipfile.ZipFile(self.source_zip, "w") as archive:
            archive.writestr("README.md", "source\n")
        self.source_zip_sha256 = hashlib.sha256(self.source_zip.read_bytes()).hexdigest()
        with zipfile.ZipFile(self.evidence_bundle, "w") as archive:
            archive.writestr(
                "release-audit-pack-manifest.json",
                json.dumps(
                    {
                        "source_of_truth": "ops/reports/release-closeout-batch-manifest.json",
                        "batch_id": "batch-demo",
                        "source_zip": {
                            "status": "materialized",
                            "path": "tmp/live-source.zip",
                            "sha256": self.source_zip_sha256,
                        },
                        "evidence_set_digest": self.evidence_set_digest,
                        "packed_entry_count": 3,
                    }
                ),
            )
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "artifact_kind": "release_closeout_summary",
                "producer": "tests.release_closeout_summary",
                "machine_release_allowed": True,
                "clean_release_ready": True,
                "release_readiness_state": "clean_pass",
            },
        )
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.release_closeout_batch_manifest",
                "status": "pass",
                "batch_integrity_status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {
                    "status": "materialized",
                    "sha256": self.source_zip_sha256,
                },
                "external_source_zip_bound": {
                    "status": "bound",
                    "sha256": self.source_zip_sha256,
                },
                "audit_materialization": {"evidence_set_digest": self.evidence_set_digest},
            },
        )
        self._write_report(
            "ops/reports/release-evidence-closeout-self-check.json",
            {
                "artifact_kind": "release_evidence_closeout_self_check",
                "producer": "tests.release_evidence_closeout_self_check",
                "status": "pass",
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_report(self, rel_path: str, payload: dict[str, object]) -> None:
        report = {
            "generated_at": "2026-05-07T08:00:00Z",
            "source_tree_fingerprint": "test-source-tree",
            **payload,
        }
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_build_attestation_binds_source_zip_evidence_bundle_and_live_reports(self) -> None:
        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "pass")
        self.assertEqual(attestation["verification"]["status"], "pass")
        self.assertEqual(attestation["bindings"]["evidence_set_digest"], self.evidence_set_digest)
        self.assertEqual(attestation["bindings"]["audit_pack_evidence_set_digest"], self.evidence_set_digest)
        self.assertEqual(attestation["bindings"]["source_zip_sha256"], self.source_zip_sha256)
        self.assertEqual(attestation["bindings"]["batch_distribution_zip_sha256"], self.source_zip_sha256)
        self.assertEqual(attestation["bindings"]["external_source_zip_bound_sha256"], self.source_zip_sha256)
        self.assertEqual(attestation["bindings"]["audit_pack_source_zip_sha256"], self.source_zip_sha256)
        self.assertTrue(attestation["release_authority"]["machine_release_allowed"])
        self.assertEqual(validate_with_schema(attestation, load_schema(SCHEMA_PATH)), [])

    def test_build_attestation_rejects_unsealed_batch_distribution(self) -> None:
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.release_closeout_batch_manifest",
                "status": "fail",
                "batch_integrity_status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "unsealed_distribution_not_provided",
                "distribution_package": {"status": "not_provided"},
                "audit_materialization": {"evidence_set_digest": self.evidence_set_digest},
            },
        )
        self._write_report(
            "ops/reports/release-evidence-closeout-self-check.json",
            {
                "artifact_kind": "release_evidence_closeout_self_check",
                "producer": "tests.release_evidence_closeout_self_check",
                "status": {"result": "pass"},
            },
        )

        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertTrue(attestation["verification"]["checks"]["batch_manifest_integrity_pass"])
        self.assertTrue(attestation["verification"]["checks"]["batch_manifest_release_authority_clean_pass"])
        self.assertFalse(attestation["verification"]["checks"]["batch_manifest_sealed_clean_pass"])
        self.assertFalse(attestation["verification"]["checks"]["source_zip_matches_batch_distribution"])
        self.assertEqual(attestation["release_authority"]["self_check_status"], "pass")

    def test_build_attestation_ignores_legacy_status_for_batch_authority(self) -> None:
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.release_closeout_batch_manifest",
                "status": "fail",
                "batch_integrity_status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {
                    "status": "materialized",
                    "sha256": self.source_zip_sha256,
                },
                "external_source_zip_bound": {
                    "status": "bound",
                    "sha256": self.source_zip_sha256,
                },
                "audit_materialization": {
                    "evidence_set_digest": self.evidence_set_digest
                },
            },
        )

        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "pass")
        self.assertTrue(
            attestation["verification"]["checks"]["batch_manifest_integrity_pass"]
        )
        self.assertTrue(
            attestation["verification"]["checks"][
                "batch_manifest_release_authority_clean_pass"
            ]
        )
        self.assertTrue(
            attestation["verification"]["checks"]["batch_manifest_sealed_clean_pass"]
        )

    def test_build_attestation_rejects_legacy_status_without_migrated_fields(
        self,
    ) -> None:
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.release_closeout_batch_manifest",
                "status": "pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {
                    "status": "materialized",
                    "sha256": self.source_zip_sha256,
                },
                "external_source_zip_bound": {
                    "status": "bound",
                    "sha256": self.source_zip_sha256,
                },
                "audit_materialization": {
                    "evidence_set_digest": self.evidence_set_digest
                },
            },
        )

        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertFalse(
            attestation["verification"]["checks"]["batch_manifest_integrity_pass"]
        )
        self.assertFalse(
            attestation["verification"]["checks"][
                "batch_manifest_release_authority_clean_pass"
            ]
        )

    def test_verify_attestation_rejects_rebound_source_zip(self) -> None:
        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )
        write_attestation(self.vault, attestation, "tmp/release-live-attestation.json")
        with zipfile.ZipFile(self.source_zip, "a") as archive:
            archive.writestr("changed.txt", "changed\n")

        result = verify_attestation(
            self.vault,
            attestation_path="tmp/release-live-attestation.json",
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            closeout_summary_path="ops/reports/release-closeout-summary.json",
            batch_manifest_path="ops/reports/release-closeout-batch-manifest.json",
            self_check_path="ops/reports/release-evidence-closeout-self-check.json",
        )

        self.assertEqual(result["status"], "fail")
        self.assertIn("source_zip_sha256", result["binding_mismatches"])


if __name__ == "__main__":
    unittest.main()
