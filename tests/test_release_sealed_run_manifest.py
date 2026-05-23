from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.release.release_sealed_run_manifest import build_manifest, write_manifest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-sealed-run-manifest.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseSealedRunManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-sealed-run-manifest.schema.json")

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

    def _write_zip(self) -> str:
        path = self.vault / "build" / "release" / "LLMwiki-source.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("LLMwiki/README.md", "hello\n")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _write_sealed_inputs(self, *, expected_zip_sha: str | None = None) -> None:
        zip_sha = self._write_zip()
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "artifact_kind": "release_run_manifest",
                "producer": "tests.release_run_manifest",
                "generated_at": "2026-05-23T12:00:00Z",
                "status": "pass",
                "final_source_tree_fingerprint": "fp-current",
                "source_tree_fingerprint": "fp-current",
                "distribution_zip": {
                    "path": "build/release/LLMwiki-source.zip",
                    "exists": True,
                    "size_bytes": 1,
                    "sha256": expected_zip_sha or zip_sha,
                },
            },
        )
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.batch",
                "source_tree_fingerprint": "fp-current",
                "status": "fail",
                "release_authority_status": "conditional_pass",
            },
        )
        self._write_json(
            "build/release/external-report-reference-manifest.json",
            {
                "artifact_kind": "external_report_reference_manifest",
                "producer": "tests.external",
                "source_tree_fingerprint": "fp-current",
                "status": "basis_current_match",
            },
        )
        self._write_json(
            "build/release/release-evidence-closeout-self-check.json",
            {
                "artifact_kind": "release_evidence_closeout_self_check",
                "producer": "tests.self_check",
                "source_tree_fingerprint": "fp-current",
                "status": {"result": "pass"},
            },
        )
        self._write_json(
            "build/release/release-sealed-post-seal-attestation.json",
            {
                "artifact_kind": "release_sealed_post_seal_attestation",
                "producer": "tests.post_seal",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
            },
        )
        self._write_json(
            "build/release/release-closeout-sealed-rehearsal-check.json",
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "producer": "tests.rehearsal",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
            },
        )
        self._write_json(
            "build/release/operator-release-summary.json",
            {"artifact_kind": "operator_release_summary", "status": "attention"},
        )

    def _patch_current_repo(self):
        return patch.multiple(
            "ops.scripts.release.release_sealed_run_manifest",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def test_manifest_passes_with_conditional_batch_and_ignores_operator_summary(self) -> None:
        self._write_sealed_inputs()

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["sealed_package_authority"], "sealed")
        self.assertEqual(manifest["sidecars"]["batch_manifest"]["status"], "fail")
        self.assertNotIn("operator_summary", manifest["sidecars"])
        self.assertNotIn("payload_status", json.dumps(manifest, ensure_ascii=False))
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_manifest(self.vault, manifest, "build/release/release-sealed-run-manifest.json").exists())

    def test_manifest_fails_on_source_zip_digest_drift(self) -> None:
        self._write_sealed_inputs(expected_zip_sha="0" * 64)

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("source_zip_matches_run_manifest", manifest["failures"])

    def test_manifest_fails_when_post_seal_attestation_is_not_pass(self) -> None:
        self._write_sealed_inputs()
        self._write_json(
            "build/release/release-sealed-post-seal-attestation.json",
            {
                "artifact_kind": "release_sealed_post_seal_attestation",
                "producer": "tests.post_seal",
                "source_tree_fingerprint": "fp-current",
                "status": "fail",
            },
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("post_seal_attestation_pass", manifest["failures"])

    def test_manifest_fails_with_legacy_post_seal_attestation_kind(self) -> None:
        self._write_sealed_inputs()
        self._write_json(
            "build/release/release-sealed-post-seal-attestation.json",
            {
                "artifact_kind": "release_post_seal_attestation",
                "producer": "tests.legacy_post_seal",
                "source_tree_fingerprint": "fp-current",
                "status": "pass",
            },
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("sidecars_artifact_kind_ok", manifest["failures"])

    def test_manifest_fails_when_sidecar_json_is_invalid(self) -> None:
        self._write_sealed_inputs()
        (self.vault / "build" / "release" / "release-closeout-batch-manifest.json").write_text(
            "{not json",
            encoding="utf-8",
        )

        with self._patch_current_repo():
            manifest = build_manifest(self.vault, context=fixed_context())

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("sidecars_load_ok", manifest["failures"])


if __name__ == "__main__":
    unittest.main()
