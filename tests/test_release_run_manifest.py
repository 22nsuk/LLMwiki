from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.release.release_run_manifest import build_manifest, write_manifest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-run-manifest.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseRunManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-run-manifest.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy(self, rel_path: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_zip(self) -> None:
        path = self.vault / "build" / "release" / "LLMwiki-source.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("LLMwiki/README.md", "hello\n")

    def _write_pass_sidecars(self) -> None:
        self._write_zip()
        self._write_json(
            "build/source-package-smoke/source-package-smoke.json",
            {"artifact_kind": "source_package_smoke", "status": "pass"},
        )
        for rel_path in (
            "build/release/release-closeout-batch-manifest.json",
            "build/release/external-report-reference-manifest.json",
            "build/release/operator-release-summary.json",
        ):
            self._write_json(rel_path, {"artifact_kind": Path(rel_path).stem})
        self._write_json(
            "build/release/release-post-seal-attestation.json",
            {"artifact_kind": "release_post_seal_attestation", "status": "pass"},
        )
        self._write_json(
            "build/release/release-closeout-sealed-rehearsal-check.json",
            {"artifact_kind": "release_closeout_sealed_rehearsal_check", "status": "pass"},
        )

    def _patch_clean_repo(self, fingerprint: str):
        return patch.multiple(
            "ops.scripts.release.release_run_manifest",
            release_source_tree_fingerprint=lambda _vault: fingerprint,
            git_commit=lambda _vault: "abc123",
            git_clean=lambda _vault: True,
            remote_sync=lambda _vault: {"status": "pass", "upstream": "origin/main", "ahead": 0, "behind": 0},
            ignored_tracked_file_count=lambda _vault: 0,
        )

    def test_manifest_passes_from_build_release_sidecars_and_diagnostic_ops_reports(self) -> None:
        self._write_pass_sidecars()
        self._write_json(
            "ops/reports/release-smoke-report.json",
            {
                "artifact_kind": "release_smoke_report",
                "status": "fail",
                "source_tree_fingerprint": "stale",
            },
        )

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                steps=[
                    {
                        "name": "release-test-current",
                        "status": "pass",
                        "command": ["make", "release-test-current"],
                        "returncode": 0,
                        "duration_ms": 1,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    }
                ],
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["git_commit"], "abc123")
        self.assertEqual(manifest["source_tree_fingerprint"], "fp-current")
        self.assertEqual(manifest["failures"], [])
        self.assertEqual(manifest["sealed"]["batch_manifest"]["release_run_requirement"], "exists_only")
        self.assertEqual(manifest["sealed"]["batch_manifest"]["release_run_status"], "pass")
        self.assertEqual(manifest["sealed"]["post_seal_attestation"]["release_run_requirement"], "payload_status_pass")
        self.assertEqual(manifest["sealed"]["post_seal_attestation"]["release_run_status"], "pass")
        smoke_ref = next(
            item for item in manifest["ops_reports_reference"] if item["path"] == "ops/reports/release-smoke-report.json"
        )
        self.assertEqual(smoke_ref["payload_status"], "fail")
        self.assertEqual(smoke_ref["authority_role"], "diagnostic_only")
        self.assertEqual(smoke_ref["release_run_requirement"], "reference_only")
        self.assertEqual(smoke_ref["release_run_status"], "reference_only")
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_manifest(self.vault, manifest, "build/release/release-run-manifest.json").exists())

    def test_legacy_sidecar_payload_status_is_not_release_run_verdict(self) -> None:
        self._write_pass_sidecars()
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "status": "fail",
                "release_authority_status": "conditional_pass",
                "sealed_release_status": "sealed_conditional_pass",
            },
        )
        self._write_json(
            "build/release/operator-release-summary.json",
            {
                "artifact_kind": "operator_release_summary",
                "status": "attention",
                "sealed_release_status": "sealed_conditional_pass",
            },
        )

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["sealed"]["status"], "pass")
        self.assertEqual(manifest["sealed"]["batch_manifest"]["payload_status"], "fail")
        self.assertNotIn("status", manifest["sealed"]["batch_manifest"])
        self.assertEqual(manifest["sealed"]["batch_manifest"]["release_run_status"], "pass")
        self.assertEqual(
            manifest["sealed"]["batch_manifest"]["release_authority_status"],
            "conditional_pass",
        )
        self.assertEqual(manifest["sealed"]["operator_summary"]["payload_status"], "attention")
        self.assertEqual(manifest["sealed"]["operator_summary"]["release_run_status"], "pass")
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_fails_on_source_fingerprint_drift(self) -> None:
        self._write_pass_sidecars()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-old",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("source_tree_fingerprint_drift", manifest["failures"])


if __name__ == "__main__":
    unittest.main()
