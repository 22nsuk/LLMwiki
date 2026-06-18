from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.artifact_relocation_audit import build_report, write_report
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-relocation-audit.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 13, 12, 0, tzinfo=dt.UTC),
    )


class ArtifactRelocationAuditTests(unittest.TestCase):
    def _candidate(self) -> dict[str, str]:
        old_path = "ops/reports/" + "operator-release-summary.json"
        return {
            "artifact_name": "operator-release-summary.json",
            "classification": "operator_only",
            "old_path": old_path,
            "new_path": "ops/operator/operator-release-summary.json",
            "reason": "test relocation",
        }

    def test_old_path_dependency_blocks_relocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "mk").mkdir()
            old_path = "ops/reports/" + "operator-release-summary.json"
            (vault / "mk" / "release.mk").write_text(
                f"OPERATOR_RELEASE_SUMMARY_OUT ?= {old_path}\n",
                encoding="utf-8",
            )
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "operator-release-summary.json").write_text(
                "{}",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context(), candidates=[self._candidate()])

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["blocking_candidate_count"], 1)
            self.assertEqual(report["summary"]["old_reference_count"], 1)
            self.assertEqual(report["candidates"][0]["relocation_status"], "old_path_references_block_relocation")
            self.assertEqual(
                report["blocking_references"][0]["references"][0]["path"],
                "mk/release.mk",
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_relocated_operator_artifact_passes_when_old_path_is_unreferenced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "mk").mkdir()
            (vault / "mk" / "release.mk").write_text(
                "OPERATOR_RELEASE_SUMMARY_OUT ?= ops/operator/operator-release-summary.json\n",
                encoding="utf-8",
            )
            (vault / "ops" / "operator").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "operator" / "operator-release-summary.json").write_text(
                "{}",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context(), candidates=[self._candidate()])
            destination = write_report(vault, report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["relocated_count"], 1)
            self.assertEqual(report["summary"]["old_reference_count"], 0)
            self.assertEqual(report["candidates"][0]["relocation_status"], "relocated")
            self.assertEqual(destination, (vault / "ops" / "operator" / "artifact-relocation-audit.json").resolve())
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
