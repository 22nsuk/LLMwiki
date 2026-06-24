from __future__ import annotations

import gzip
import json
import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.scripts.core.generated_artifact_retention_clean import build_report

pytestmark = pytest.mark.report_contract


class GeneratedArtifactRunsCompressionTests(unittest.TestCase):
    def _vault(self, root: Path) -> Path:
        vault = root / "vault"
        vault.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
        (vault / ".gitignore").write_text("runs/\n", encoding="utf-8")
        return vault

    def test_compresses_old_unprotected_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = vault / "runs" / "run-old"
            run_dir.mkdir(parents=True)
            artifact = run_dir / "executor-report.json"
            artifact.write_text('{"status":"ok"}\n', encoding="utf-8")
            old_time = (datetime.now(tz=UTC) - timedelta(days=45)).timestamp()
            os.utime(artifact, (old_time, old_time))
            report = build_report(vault, apply=True, compress_runs=True, compress_ttl_days=30)
            self.assertEqual(report["compressed_paths"], ["runs/run-old/executor-report.json.gz"])
            self.assertFalse(artifact.exists())
            compressed = vault / "runs/run-old/executor-report.json.gz"
            self.assertTrue(compressed.is_file())
            with gzip.open(compressed, "rt", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {"status": "ok"})

    def test_preserves_promoted_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            run_dir = vault / "runs" / "run-promoted"
            run_dir.mkdir(parents=True)
            artifact = run_dir / "executor-report.json"
            artifact.write_text('{"status":"ok"}\n', encoding="utf-8")
            (run_dir / "run-telemetry.json").write_text(
                json.dumps({"decision": "PROMOTE", "finalized": True}),
                encoding="utf-8",
            )
            old_time = (datetime.now(tz=UTC) - timedelta(days=45)).timestamp()
            os.utime(artifact, (old_time, old_time))
            report = build_report(vault, apply=True, compress_runs=True, compress_ttl_days=30)
            self.assertEqual(report["compressed_paths"], [])
            self.assertTrue(artifact.is_file())
