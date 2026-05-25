from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ops.scripts.external_report_reference_manifest import (
    ExternalReportReferenceManifestRequest,
    ZipIdentityInput,
    build_report,
    main,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "external-report-reference-manifest.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 4, 10, 30, tzinfo=dt.UTC),
    )


class ExternalReportReferenceManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self.external = self.vault / "external-reports"
        self.external.mkdir()
        (self.external / "archive").mkdir()
        (self.external / "llmwiki_review_test_structure_improvement_report_20260504.md").write_text(
            "# Review\n\nbody\n",
            encoding="utf-8",
        )
        (self.external / "llmwiki_consolidated_improvement_execution_report_20260503.md").write_text(
            "# Consolidated\n",
            encoding="utf-8",
        )
        (self.external / "archive" / "old.md").write_text("# Archived\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_manifest_records_non_archived_external_report_digests_and_basis_zip(self) -> None:
        basis_sha = "a" * 64
        current_sha = "c" * 64

        report = build_report(
            self.vault,
            request=ExternalReportReferenceManifestRequest(
                basis_zip=ZipIdentityInput(
                    name="LLMwiki.zip",
                    sha256=basis_sha,
                    entry_count=1819,
                ),
                current_distribution_zip=ZipIdentityInput(
                    name="LLMwiki(12).zip",
                    sha256=current_sha,
                    entry_count=1829,
                ),
            ),
            context=fixed_context(),
        )

        self.assertEqual(report["summary"]["report_count"], 2)
        self.assertTrue(report["summary"]["basis_zip_known"])
        self.assertTrue(report["summary"]["review_basis_zip_known"])
        self.assertTrue(report["summary"]["current_distribution_zip_known"])
        self.assertEqual(report["review_basis_zip"]["sha256"], basis_sha)
        self.assertEqual(report["basis_zip"], report["review_basis_zip"])
        self.assertEqual(report["current_distribution_zip"]["sha256"], current_sha)
        self.assertEqual(report["distribution_provenance"]["mode"], "advisory")
        self.assertEqual(report["distribution_provenance"]["status"], "basis_current_mismatch")
        self.assertFalse(report["distribution_provenance"]["basis_zip_matches_current_distribution"])
        self.assertEqual(report["distribution_provenance"]["identity_mismatch_fields"], ["sha256", "entry_count"])
        self.assertTrue(report["distribution_provenance"]["name_mismatch"])
        self.assertFalse(report["summary"]["basis_zip_matches_current_distribution"])
        self.assertEqual(report["summary"]["zip_provenance_status"], "basis_current_mismatch")
        self.assertEqual(report["active_reference_set"]["status"], "no_prior_manifest")
        self.assertEqual(report["active_reference_set"]["previous_report_count"], None)
        self.assertEqual(report["active_reference_set"]["current_report_count"], 2)
        self.assertEqual(report["summary"]["active_reference_set_status"], "no_prior_manifest")
        self.assertIn("current_distribution_zip_sha256", report["input_fingerprints"])
        self.assertIn("current_distribution_zip_entry_count", report["input_fingerprints"])
        self.assertIn("mode", report["input_fingerprints"])
        self.assertIn("zip_provenance_status", report["input_fingerprints"])
        self.assertEqual(report["excluded_file_count"], 1)
        self.assertEqual(report["summary"]["excluded_file_count"], 1)
        self.assertIn("archive is excluded", report["archive_exclusion_policy"])
        paths = {item["path"]: item for item in report["references"]}
        review_path = "external-reports/llmwiki_review_test_structure_improvement_report_20260504.md"
        self.assertEqual(paths[review_path]["line_count"], 3)
        self.assertEqual(paths[review_path]["evidence_role"], "test_structure_review")
        self.assertEqual(paths[review_path]["storage_path"], review_path)
        self.assertEqual(
            paths[review_path]["display_name"],
            "llmwiki_review_test_structure_improvement_report_20260504.md",
        )
        self.assertIn(review_path, paths[review_path]["path_aliases"])
        self.assertEqual(paths[review_path]["content_sha256"], paths[review_path]["sha256"])
        self.assertEqual(paths[review_path]["normalization_form"], "NFC")
        self.assertEqual(paths[review_path]["escape_diagnostics"]["display_path"], review_path)
        self.assertEqual(
            paths[review_path]["sha256"],
            hashlib.sha256((self.vault / review_path).read_bytes()).hexdigest(),
        )
        self.assertFalse(any("/archive/" in item["path"] for item in report["references"]))
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_advisory_mode_allows_unknown_basis_zip_without_stale_defaults(self) -> None:
        report = build_report(
            self.vault,
            request=ExternalReportReferenceManifestRequest(),
            context=fixed_context(),
        )

        self.assertEqual(report["review_basis_zip"]["name"], "")
        self.assertEqual(report["review_basis_zip"]["sha256"], "")
        self.assertIsNone(report["review_basis_zip"]["entry_count"])
        self.assertFalse(report["summary"]["basis_zip_known"])
        self.assertEqual(report["distribution_provenance"]["status"], "current_distribution_missing")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_main_writes_manifest_to_external_reports(self) -> None:
        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "external-reports/report-reference-manifest.json",
                "--basis-zip-sha256",
                "b" * 64,
                "--basis-zip-entry-count",
                "1819",
                "--current-distribution-zip-name",
                "LLMwiki(12).zip",
                "--current-distribution-zip-sha256",
                "c" * 64,
                "--current-distribution-zip-entry-count",
                "1829",
            ]
        )

        self.assertEqual(exit_code, 0)
        destination = self.external / "report-reference-manifest.json"
        self.assertTrue(destination.exists())
        payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["summary"]["report_count"], 2)
        self.assertEqual(payload["current_distribution_zip"]["entry_count"], 1829)
        self.assertEqual(payload["distribution_provenance"]["status"], "basis_current_mismatch")

    def test_strict_review_release_requires_current_distribution_zip_path(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            main(
                [
                    "--vault",
                    self.vault.as_posix(),
                    "--out",
                    "external-reports/report-reference-manifest.json",
                    "--mode",
                    "strict_review_release",
                    "--basis-zip-sha256",
                    "b" * 64,
                    "--basis-zip-entry-count",
                    "1819",
                ]
            )

        self.assertEqual(caught.exception.code, 2)
        self.assertFalse((self.external / "report-reference-manifest.json").exists())

    def test_active_reference_set_records_prior_manifest_count_drift(self) -> None:
        prior_manifest = self.external / "report-reference-manifest.json"
        prior_manifest.write_text(
            json.dumps(
                {
                    "references": [
                        {
                            "path": (
                                "external-reports/"
                                "llmwiki_review_test_structure_improvement_report_20260504.md"
                            )
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        report = build_report(
            self.vault,
            request=ExternalReportReferenceManifestRequest(
                out_path="external-reports/report-reference-manifest.json",
                basis_zip=ZipIdentityInput(
                    name="LLMwiki.zip",
                    sha256="b" * 64,
                    entry_count=1819,
                ),
            ),
            context=fixed_context(),
        )

        self.assertEqual(report["active_reference_set"]["status"], "drift")
        self.assertEqual(report["active_reference_set"]["previous_report_count"], 1)
        self.assertEqual(report["active_reference_set"]["current_report_count"], 2)
        self.assertEqual(
            report["active_reference_set"]["added_paths"],
            ["external-reports/llmwiki_consolidated_improvement_execution_report_20260503.md"],
        )
        self.assertEqual(report["active_reference_set"]["removed_paths"], [])
        self.assertEqual(report["summary"]["active_reference_set_status"], "drift")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_main_can_compute_current_distribution_zip_identity_from_zip_path(self) -> None:
        zip_path = self.vault / "LLMwiki-test.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("README.md", "hello\n")
            archive.writestr("ops/scripts/example.py", "print('ok')\n")
        expected_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "external-reports/report-reference-manifest.json",
                "--basis-zip-sha256",
                "b" * 64,
                "--basis-zip-entry-count",
                "1819",
                "--strict-review-release",
                "--current-distribution-zip-path",
                zip_path.as_posix(),
            ]
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads((self.external / "report-reference-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["current_distribution_zip"]["name"], "LLMwiki-test.zip")
        self.assertEqual(payload["current_distribution_zip"]["sha256"], expected_sha)
        self.assertEqual(payload["current_distribution_zip"]["entry_count"], 2)
        self.assertEqual(payload["current_distribution_zip"]["source"], "computed")
        self.assertTrue(payload["summary"]["current_distribution_zip_known"])
        self.assertEqual(payload["distribution_provenance"]["mode"], "strict_review_release")
        self.assertEqual(payload["distribution_provenance"]["status"], "basis_current_mismatch")

    def test_main_can_promote_current_distribution_zip_as_active_basis(self) -> None:
        zip_path = self.vault / "LLMwiki-source.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("README.md", "hello\n")
            archive.writestr("ops/scripts/example.py", "print('ok')\n")
        expected_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()

        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "external-reports/report-reference-manifest.json",
                "--strict-review-release",
                "--basis-zip-path",
                zip_path.as_posix(),
                "--current-distribution-zip-path",
                zip_path.as_posix(),
            ]
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads((self.external / "report-reference-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["review_basis_zip"]["name"], "LLMwiki-source.zip")
        self.assertEqual(payload["review_basis_zip"]["sha256"], expected_sha)
        self.assertEqual(payload["review_basis_zip"]["entry_count"], 2)
        self.assertEqual(payload["review_basis_zip"]["source"], "computed")
        self.assertEqual(payload["current_distribution_zip"], payload["review_basis_zip"])
        self.assertTrue(payload["summary"]["basis_zip_known"])
        self.assertTrue(payload["summary"]["basis_zip_matches_current_distribution"])
        self.assertEqual(payload["distribution_provenance"]["mode"], "strict_review_release")
        self.assertEqual(payload["distribution_provenance"]["status"], "basis_current_match")
        self.assertEqual(payload["distribution_provenance"]["identity_mismatch_fields"], [])
        self.assertEqual(validate_with_schema(payload, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
