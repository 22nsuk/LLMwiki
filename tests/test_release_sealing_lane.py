from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest
from ops.scripts.release_closeout_batch_manifest import main as batch_manifest_main

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.release_sealing

REPO_ROOT = Path(__file__).resolve().parents[1]
BATCH_POLICY_PATH = REPO_ROOT / "ops" / "policies" / "release-closeout-batch.json"
FIXTURE_SOURCE_MTIME = 1_700_000_000


class ReleaseSealingLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        batch_policy_dest = self.vault / "ops" / "policies" / "release-closeout-batch.json"
        batch_policy_dest.parent.mkdir(parents=True, exist_ok=True)
        batch_policy_dest.write_text(BATCH_POLICY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._write_required_release_artifacts()
        self._freeze_fixture_mtimes()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _freeze_fixture_mtimes(self) -> None:
        for path in self.vault.rglob("*"):
            if path.is_file():
                os.utime(path, (FIXTURE_SOURCE_MTIME, FIXTURE_SOURCE_MTIME))

    def _write_required_release_artifacts(self) -> None:
        base_artifact = {
            "artifact_kind": "test_report",
            "generated_at": "2026-05-02T08:00:00Z",
            "producer": "test",
            "source_tree_fingerprint": "abc",
            "currentness": {"status": "current"},
        }
        for artifact_path in [
            "ops/reports/release-smoke-report.json",
            "ops/reports/generated-artifact-index.json",
            "ops/reports/artifact-freshness-report.json",
            "ops/reports/test-execution-summary.json",
            "ops/reports/learning-readiness-signoff-revalidation.json",
            "ops/reports/release-evidence-cohort.json",
            "ops/reports/release-evidence-dashboard.json",
            "ops/reports/release-lane-summary.json",
            "ops/reports/release-clean-blocker-ledger.json",
        ]:
            self._write_json(artifact_path, dict(base_artifact))
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {
                **base_artifact,
                "status": "pass",
                "clean_release_ready": True,
                "machine_release_allowed": True,
                "release_readiness_state": "clean_pass",
                "summary": {"accepted_risk_family_count": 0},
                "components": [],
                "input_fingerprints": {},
            },
        )

    def test_batch_manifest_check_accepts_tmp_json_manifest(self) -> None:
        tmp_manifest = "tmp/release-closeout-batch-manifest.json"

        build_exit = batch_manifest_main(
            ["--vault", self.vault.as_posix(), "--out", tmp_manifest]
        )
        check_exit = batch_manifest_main(
            ["--vault", self.vault.as_posix(), "--out", tmp_manifest, "--check"]
        )

        self.assertEqual(build_exit, 0)
        self.assertEqual(check_exit, 0)
        self.assertTrue((self.vault / tmp_manifest).exists())
        self.assertFalse((REPO_ROOT / tmp_manifest).exists())

    def test_batch_manifest_check_detects_digest_mismatch_from_tmp_manifest(self) -> None:
        tmp_manifest = "tmp/release-closeout-batch-manifest.json"
        build_exit = batch_manifest_main(
            ["--vault", self.vault.as_posix(), "--out", tmp_manifest]
        )
        self.assertEqual(build_exit, 0)

        smoke_path = self.vault / "ops" / "reports" / "release-smoke-report.json"
        smoke_payload = json.loads(smoke_path.read_text(encoding="utf-8"))
        smoke_payload["producer"] = "mutated-after-seal"
        smoke_path.write_text(json.dumps(smoke_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        check_exit = batch_manifest_main(
            ["--vault", self.vault.as_posix(), "--out", tmp_manifest, "--check"]
        )

        self.assertEqual(check_exit, 1)


if __name__ == "__main__":
    unittest.main()
