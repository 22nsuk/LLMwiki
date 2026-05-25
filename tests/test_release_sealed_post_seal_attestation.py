from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from ops.scripts.release.release_sealed_post_seal_attestation import (
    build_attestation,
    write_attestation,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-sealed-post-seal-attestation.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.UTC),
    )


class ReleaseSealedPostSealAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-sealed-post-seal-attestation.schema.json")

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

    def _write_inputs(self, *, external_sha: str | None = None) -> None:
        zip_sha = self._write_zip()
        self._write_json(
            "build/release/release-run-manifest.json",
            {
                "artifact_kind": "release_run_manifest",
                "producer": "tests.run",
                "generated_at": "2026-05-23T12:00:00Z",
                "source_tree_fingerprint": "fp-current",
                "final_source_tree_fingerprint": "fp-current",
                "status": "pass",
                "distribution_zip": {"sha256": zip_sha},
            },
        )
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "tests.batch",
                "source_tree_fingerprint": "fp-current",
                "status": "fail",
                "distribution_package": {"sha256": zip_sha},
            },
        )
        self._write_json(
            "build/release/external-report-reference-manifest.json",
            {
                "artifact_kind": "external_report_reference_manifest",
                "producer": "tests.external",
                "source_tree_fingerprint": "fp-current",
                "status": "basis_current_match",
                "current_distribution_zip": {"sha256": external_sha or zip_sha},
                "basis_zip": {"sha256": external_sha or zip_sha},
            },
        )
        self._write_json(
            "build/release/release-evidence-closeout-self-check.json",
            {
                "artifact_kind": "release_evidence_closeout_self_check",
                "producer": "tests.self_check",
                "source_tree_fingerprint": "fp-current",
                "status": {"result": "pass"},
                "batch_artifact_digest_watch": {"status": "match"},
            },
        )

    def _patch_current_repo(self) -> Any:
        return patch.multiple(
            "ops.scripts.release.release_sealed_post_seal_attestation",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
        )

    def test_attestation_passes_without_operator_diagnostics(self) -> None:
        self._write_inputs()
        self._write_json(
            "build/release/operator-release-summary.json",
            {"artifact_kind": "operator_release_summary", "status": "attention"},
        )

        with self._patch_current_repo():
            attestation = build_attestation(self.vault, context=fixed_context())

        self.assertEqual(attestation["status"], "pass")
        self.assertNotIn("operator_summary", json.dumps(attestation, ensure_ascii=False))
        self.assertNotIn("payload_status", json.dumps(attestation, ensure_ascii=False))
        self.assertEqual(validate_with_schema(attestation, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_attestation(
                self.vault,
                attestation,
                "build/release/release-sealed-post-seal-attestation.json",
            ).exists()
        )

    def test_attestation_fails_when_sidecar_json_is_invalid(self) -> None:
        self._write_inputs()
        (self.vault / "build" / "release" / "release-closeout-batch-manifest.json").write_text(
            "{not json",
            encoding="utf-8",
        )

        with self._patch_current_repo():
            attestation = build_attestation(self.vault, context=fixed_context())

        self.assertEqual(attestation["status"], "fail")
        self.assertIn("batch_manifest_load_ok", attestation["failures"])

    def test_attestation_fails_when_external_zip_digest_drifts(self) -> None:
        self._write_inputs(external_sha="0" * 64)

        with self._patch_current_repo():
            attestation = build_attestation(self.vault, context=fixed_context())

        self.assertEqual(attestation["status"], "fail")
        self.assertIn("external_current_distribution_matches_source_zip", attestation["failures"])


if __name__ == "__main__":
    unittest.main()
