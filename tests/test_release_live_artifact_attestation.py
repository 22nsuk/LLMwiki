from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import shlex
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_live_artifact_attestation import (
    build_attestation,
    distribution_binding_reason_ids,
    verify_attestation,
    write_attestation,
)
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
        self.dist_dir = self.vault / "dist"
        self.dist_dir.mkdir()
        self.package_name = "llm-wiki-vnext"
        self.package_version = "0.1.0"
        self.source_revision = "a" * 40
        self.source_tree_fingerprint = "test-source-tree"
        self.evidence_set_digest = "e" * 64
        with zipfile.ZipFile(self.source_zip, "w") as archive:
            archive.writestr("LLMwiki/README.md", "source\n")
            archive.writestr(
                "LLMwiki/pyproject.toml",
                "[project]\n"
                f'name = "{self.package_name}"\n'
                f'version = "{self.package_version}"\n',
            )
            archive.writestr(
                "LLMwiki/release-archive-self-description.json",
                json.dumps(
                    {
                        "archive_root_name": "LLMwiki",
                        "git_commit": self.source_revision,
                        "source_tree_fingerprint": self.source_tree_fingerprint,
                    }
                ),
            )
        metadata = (
            "Metadata-Version: 2.1\n"
            f"Name: {self.package_name}\n"
            f"Version: {self.package_version}\n"
        ).encode()
        with zipfile.ZipFile(
            self.dist_dir / "llm_wiki_vnext-0.1.0-py3-none-any.whl", "w"
        ) as archive:
            archive.writestr("llm_wiki_vnext-0.1.0.dist-info/METADATA", metadata)
        with tarfile.open(
            self.dist_dir / "llm_wiki_vnext-0.1.0.tar.gz", "w:gz"
        ) as archive:
            for member_name in (
                "llm_wiki_vnext-0.1.0/PKG-INFO",
                "llm_wiki_vnext-0.1.0/llm_wiki_vnext.egg-info/PKG-INFO",
            ):
                member = tarfile.TarInfo(member_name)
                member.size = len(metadata)
                archive.addfile(member, io.BytesIO(metadata))
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
            "source_tree_fingerprint": self.source_tree_fingerprint,
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
        self.assertEqual(
            attestation["bindings"]["distribution_package_name"],
            self.package_name,
        )
        self.assertEqual(
            attestation["bindings"]["distribution_package_version"],
            self.package_version,
        )
        self.assertEqual(
            attestation["bindings"]["distribution_source_revision"],
            self.source_revision,
        )
        self.assertEqual(
            attestation["bindings"]["source_tree_fingerprint"],
            self.source_tree_fingerprint,
        )
        self.assertEqual(
            attestation["distribution_manifest"]["source_tree_fingerprint"],
            self.source_tree_fingerprint,
        )
        for check_name in (
            "distribution_manifest_source_tree_fingerprint_bound",
            "source_zip_matches_closeout_source_tree_fingerprint",
            "source_zip_matches_batch_source_tree_fingerprint",
            "source_zip_matches_self_check_source_tree_fingerprint",
        ):
            self.assertTrue(attestation["verification"]["checks"][check_name])
        source_command = shlex.split(attestation["source_command"])
        self.assertEqual(
            source_command[source_command.index("--expected-package-version") + 1],
            self.package_version,
        )
        self.assertEqual(
            source_command[source_command.index("--expected-source-revision") + 1],
            self.source_revision,
        )
        self.assertEqual(attestation["distribution_manifest"]["file_count"], 2)
        self.assertIn("distribution_sdist", attestation["input_fingerprints"])
        self.assertIn("distribution_wheel", attestation["input_fingerprints"])
        self.assertEqual(
            [item["distribution_type"] for item in attestation["distribution_manifest"]["files"]],
            ["sdist", "wheel"],
        )
        self.assertTrue(
            all("path" not in item for item in attestation["distribution_manifest"]["files"])
        )
        self.assertTrue(attestation["release_authority"]["machine_release_allowed"])
        self.assertEqual(validate_with_schema(attestation, load_schema(SCHEMA_PATH)), [])

    def test_build_attestation_rejects_source_zip_tree_fingerprint_mismatch(
        self,
    ) -> None:
        batch_path = self.vault / "ops/reports/release-closeout-batch-manifest.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["source_tree_fingerprint"] = "different-source-tree"
        batch_path.write_text(
            json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertFalse(
            attestation["verification"]["checks"][
                "source_zip_matches_batch_source_tree_fingerprint"
            ]
        )
        self.assertEqual(
            attestation["bindings"]["source_tree_fingerprint"],
            self.source_tree_fingerprint,
        )

    def test_source_command_quotes_effective_identity_and_authority_paths(
        self,
    ) -> None:
        source_zip_path = "tmp/release payload/live source.zip"
        evidence_bundle_path = "tmp/release payload/evidence bundle.zip"
        dist_dir = "tmp/release payload/dist files"
        closeout_summary_path = "tmp/authority's reports/closeout summary.json"
        batch_manifest_path = "tmp/authority's reports/batch manifest.json"
        self_check_path = "tmp/authority's reports/self check.json"
        for source, destination in (
            (self.source_zip, self.vault / source_zip_path),
            (self.evidence_bundle, self.vault / evidence_bundle_path),
            (
                self.vault / "ops/reports/release-closeout-summary.json",
                self.vault / closeout_summary_path,
            ),
            (
                self.vault / "ops/reports/release-closeout-batch-manifest.json",
                self.vault / batch_manifest_path,
            ),
            (
                self.vault / "ops/reports/release-evidence-closeout-self-check.json",
                self.vault / self_check_path,
            ),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        shutil.copytree(self.dist_dir, self.vault / dist_dir)

        attestation = build_attestation(
            self.vault,
            source_zip_path=source_zip_path,
            evidence_bundle_path=evidence_bundle_path,
            dist_dir=dist_dir,
            closeout_summary_path=closeout_summary_path,
            batch_manifest_path=batch_manifest_path,
            self_check_path=self_check_path,
            expected_package_version=self.package_version,
            expected_source_revision=self.source_revision,
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "pass")
        self.assertEqual(
            shlex.split(attestation["source_command"]),
            [
                "python",
                "-m",
                "ops.scripts.release.release_live_artifact_attestation",
                "build",
                "--vault",
                ".",
                "--source-zip-path",
                source_zip_path,
                "--evidence-bundle-path",
                evidence_bundle_path,
                "--dist-dir",
                dist_dir,
                "--closeout-summary-path",
                closeout_summary_path,
                "--batch-manifest-path",
                batch_manifest_path,
                "--self-check-path",
                self_check_path,
                "--expected-package-version",
                self.package_version,
                "--expected-source-revision",
                self.source_revision,
            ],
        )

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

    def test_verify_attestation_accepts_identical_dist_at_a_different_path(self) -> None:
        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )
        write_attestation(self.vault, attestation, "tmp/release-live-attestation.json")
        downloaded_dist = self.vault / "tmp" / "downloaded-dist"
        shutil.copytree(self.dist_dir, downloaded_dist)

        result = verify_attestation(
            self.vault,
            attestation_path="tmp/release-live-attestation.json",
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            dist_dir="tmp/downloaded-dist",
            closeout_summary_path="ops/reports/release-closeout-summary.json",
            batch_manifest_path="ops/reports/release-closeout-batch-manifest.json",
            self_check_path="ops/reports/release-evidence-closeout-self-check.json",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["binding_mismatches"], [])

    def test_verify_attestation_rejects_mutated_wheel_bytes(self) -> None:
        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )
        write_attestation(self.vault, attestation, "tmp/release-live-attestation.json")
        wheel = next(self.dist_dir.glob("*.whl"))
        wheel.write_bytes(wheel.read_bytes() + b"tampered")

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
        self.assertIn("distribution_manifest_sha256", result["binding_mismatches"])
        self.assertIn(
            "release_live_distribution_file_sha256_mismatch",
            distribution_binding_reason_ids(
                self.vault,
                attestation_path="tmp/release-live-attestation.json",
            ),
        )

    def test_verify_attestation_rejects_tampered_embedded_manifest(self) -> None:
        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )
        attestation["distribution_manifest"]["package_version"] = "9.9.9"
        write_attestation(self.vault, attestation, "tmp/release-live-attestation.json")

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
        self.assertEqual(
            result["attestation_self_binding_mismatches"],
            ["distribution_manifest_sha256", "distribution_package_version"],
        )

    def test_build_attestation_rejects_expected_release_identity_mismatch(self) -> None:
        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            expected_package_version="9.9.9",
            expected_source_revision="b" * 40,
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertFalse(
            attestation["verification"]["checks"]["expected_package_version_matches"]
        )
        self.assertFalse(
            attestation["verification"]["checks"]["expected_source_revision_matches"]
        )

    def test_build_attestation_rejects_an_extra_distribution_file(self) -> None:
        (self.dist_dir / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

        attestation = build_attestation(
            self.vault,
            source_zip_path="tmp/live-source.zip",
            evidence_bundle_path="tmp/release-evidence-bundle.zip",
            context=fixed_context(),
        )

        self.assertEqual(attestation["status"], "fail")
        self.assertIn(
            "unexpected_distribution_files",
            attestation["distribution_manifest"]["failures"],
        )


if __name__ == "__main__":
    unittest.main()
