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

    def _write_run_inputs(self) -> None:
        self._write_zip()
        self._write_json(
            "build/source-package-smoke/source-package-smoke.json",
            {"artifact_kind": "source_package_smoke", "status": "pass"},
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

    def test_manifest_passes_from_run_inputs_and_ignores_diagnostic_reports(self) -> None:
        self._write_run_inputs()
        self._write_json(
            "ops/reports/release-smoke-report.json",
            {
                "artifact_kind": "release_smoke_report",
                "status": "fail",
                "source_tree_fingerprint": "stale",
            },
        )
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {"artifact_kind": "release_closeout_batch_manifest", "status": "fail"},
        )
        self._write_json(
            "build/release/operator-release-summary.json",
            {"artifact_kind": "operator_release_summary", "status": "attention"},
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
        self.assertEqual(manifest["schema_version"], 3)
        self.assertNotIn("sealed", manifest)
        self.assertNotIn("ops_reports_reference", manifest)
        self.assertNotIn("payload_status", json.dumps(manifest, ensure_ascii=False))
        self.assertEqual(
            sorted(manifest["input_fingerprints"]),
            ["distribution_zip", "source_package_smoke"],
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_manifest(self.vault, manifest, "build/release/release-run-manifest.json").exists())

    def test_step_failure_is_release_run_verdict(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                steps=[
                    {
                        "name": "release-public-current",
                        "status": "fail",
                        "command": ["make", "release-public-current"],
                        "returncode": 1,
                        "duration_ms": 1,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    }
                ],
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("step_failed:release-public-current", manifest["failures"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_fails_on_source_fingerprint_drift(self) -> None:
        self._write_run_inputs()

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
