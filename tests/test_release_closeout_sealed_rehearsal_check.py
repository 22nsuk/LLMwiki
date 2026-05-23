from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import pytest

from ops.scripts.release_closeout_sealed_rehearsal_check import build_report, main, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public
REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-sealed-rehearsal-check.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 9, 12, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseCloseoutSealedRehearsalCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / "external-reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_zip(self) -> tuple[Path, str, int]:
        path = self.vault / "build" / "release" / "LLMwiki-source.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("LLMwiki/README.md", "hello\n")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as archive:
            entry_count = len(archive.infolist())
        return path, digest, entry_count

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_inputs(self) -> Path:
        zip_path, digest, entry_count = self._write_zip()
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {
                "release_authority_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {
                    "status": "materialized",
                    "sha256": digest,
                },
                "external_source_zip_bound": {
                    "status": "bound",
                    "sha256": digest,
                },
            },
        )
        self._write_json(
            "build/release/external-report-reference-manifest.json",
            {
                "distribution_provenance": {
                    "mode": "strict_review_release",
                    "status": "basis_current_match",
                    "basis_zip_matches_current_distribution": True,
                },
                "current_distribution_zip": {
                    "sha256": digest,
                    "entry_count": entry_count,
                },
                "basis_zip": {
                    "sha256": digest,
                    "entry_count": entry_count,
                },
            },
        )
        return zip_path

    def test_sealed_rehearsal_check_passes_for_strict_bound_distribution(self) -> None:
        zip_path = self._write_inputs()

        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(
            report["$schema"],
            "ops/schemas/release-closeout-sealed-rehearsal-check.schema.json",
        )
        self.assertEqual(
            report["producer"],
            "ops.scripts.release_closeout_sealed_rehearsal_check",
        )
        self.assertEqual(report["artifact_status"], "current")
        self.assertEqual(report["currentness"]["status"], "current")
        self.assertEqual(report["preflight_status"], "sealed_clean_pass")
        self.assertEqual(report["preflight_mode"], "clean_required")
        self.assertEqual(report["distribution_binding_status"], "pass")
        self.assertEqual(report["authority_preflight_status"], "clean")
        self.assertFalse(report["expected_blocked_preflight"])
        self.assertTrue(report["clean_required_preflight"])
        self.assertEqual(report["blocking_reason_ids"], [])
        self.assertEqual(report["unexpected_failure_ids"], [])
        self.assertEqual(report["failures"], [])
        self.assertEqual(
            report["batch_manifest"]["sealed_release_status"], "sealed_clean_pass"
        )
        self.assertEqual(
            report["external_report_reference_manifest"]["mode"],
            "strict_review_release",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_sealed_rehearsal_check_default_context_is_utc(self) -> None:
        zip_path = self._write_inputs()

        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertRegex(report["generated_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_sealed_rehearsal_check_accepts_candidate_manifest_paths(self) -> None:
        zip_path = self._write_inputs()
        batch_candidate = self.vault / "tmp" / "sealed-dry-run" / "batch.json"
        external_candidate = self.vault / "tmp" / "sealed-dry-run" / "external.json"
        batch_candidate.parent.mkdir(parents=True, exist_ok=True)
        batch_candidate.write_text(
            (
                self.vault / "build" / "release" / "release-closeout-batch-manifest.json"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        external_candidate.write_text(
            (
                self.vault / "build" / "release" / "external-report-reference-manifest.json"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
            batch_manifest=batch_candidate.relative_to(self.vault).as_posix(),
            external_manifest=external_candidate.relative_to(self.vault).as_posix(),
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(
            report["batch_manifest"]["path"], "tmp/sealed-dry-run/batch.json"
        )
        self.assertEqual(
            report["external_report_reference_manifest"]["path"],
            "tmp/sealed-dry-run/external.json",
        )

    def test_sealed_rehearsal_check_ignores_batch_authority_status(self) -> None:
        zip_path = self._write_inputs()
        batch_path = (
            self.vault / "build" / "release" / "release-closeout-batch-manifest.json"
        )
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["release_authority_status"] = "blocked"
        batch["sealed_release_status"] = "unsealed_distribution_not_provided"
        batch_path.write_text(
            json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["preflight_status"], "sealed_clean_pass")
        self.assertEqual(report["distribution_binding_status"], "pass")

    def test_sealed_rehearsal_check_treats_authority_only_failure_as_pass(
        self,
    ) -> None:
        zip_path = self._write_inputs()
        batch_path = (
            self.vault / "build" / "release" / "release-closeout-batch-manifest.json"
        )
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["release_authority_status"] = "blocked"
        batch["sealed_release_status"] = "unsealed_release_blocked"
        batch["release_authority_vocabulary"] = {
            "blocker_reason_ids": [
                "release_authority_not_clean_pass",
                "machine_release_not_allowed",
                "sealed_release_not_clean_pass",
            ]
        }
        batch_path.write_text(
            json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["preflight_status"], "sealed_clean_pass")
        self.assertEqual(report["preflight_mode"], "clean_required")
        self.assertEqual(report["distribution_binding_status"], "pass")
        self.assertEqual(report["authority_preflight_status"], "clean")
        self.assertFalse(report["expected_blocked_preflight"])
        self.assertTrue(report["clean_required_preflight"])
        self.assertEqual(report["unexpected_failure_ids"], [])
        self.assertEqual(report["blocking_reason_ids"], [])
        self.assertEqual(
            report["summary"],
            "sealed closeout rehearsal passed: distribution ZIP is bound to build/release sidecars",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_allow_blocked_preflight_exits_success_for_authority_only_blocker(
        self,
    ) -> None:
        zip_path = self._write_inputs()
        batch_path = (
            self.vault / "build" / "release" / "release-closeout-batch-manifest.json"
        )
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        batch["release_authority_status"] = "blocked"
        batch["sealed_release_status"] = "unsealed_release_blocked"
        batch_path.write_text(
            json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        result = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--distribution-zip",
                zip_path.relative_to(self.vault).as_posix(),
                "--allow-blocked-preflight",
            ]
        )

        self.assertEqual(result, 0)

    def test_write_report_validates_sealed_preflight_vocabulary_schema(self) -> None:
        zip_path = self._write_inputs()
        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
            context=fixed_context(),
        )

        out_path = write_report(self.vault, report, "tmp/sealed-check.json")
        persisted = json.loads(out_path.read_text(encoding="utf-8"))

        schema = load_schema(
            self.vault
            / "ops"
            / "schemas"
            / "release-closeout-sealed-rehearsal-check.schema.json"
        )
        self.assertEqual(validate_with_schema(persisted, schema), [])
        self.assertEqual(persisted["preflight_mode"], "clean_required")

    def test_sealed_rehearsal_check_accepts_legacy_status_when_zip_binding_is_current(
        self,
    ) -> None:
        zip_path = self._write_inputs()
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {
                "status": "pass",
                "distribution_package": {
                    "status": "materialized",
                    "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                },
                "external_source_zip_bound": {
                    "status": "bound",
                    "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                },
            },
        )

        report = build_report(
            self.vault,
            distribution_zip=zip_path.relative_to(self.vault).as_posix(),
            context=fixed_context(),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["failures"], [])


if __name__ == "__main__":
    unittest.main()
