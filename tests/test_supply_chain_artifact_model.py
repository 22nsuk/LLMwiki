from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.supply_chain_artifact_model import build_model, write_model

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_provenance import (
    LOCKED_CI_INSTALL_SNIPPET,
    seed_dependency_inputs,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC),
    )


def seed_runtime_surface(vault: Path) -> None:
    (vault / "README.md").write_text("root\n", encoding="utf-8")
    (vault / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (vault / "THIRD_PARTY_NOTICES.md").write_text("# Notices\n", encoding="utf-8")
    (vault / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
    (vault / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
    (vault / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (vault / ".github" / "workflows" / "ci.yml").write_text(
        LOCKED_CI_INSTALL_SNIPPET,
        encoding="utf-8",
    )


class SupplyChainArtifactModelTests(unittest.TestCase):
    def test_build_model_records_cross_artifact_refs_and_advisories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_runtime_surface(vault)
            (vault / "ops" / "advisories.json").write_text(
                json.dumps(
                    {
                        "advisories": [
                            {
                                "id": "CVE-2026-0002",
                                "aliases": ["GHSA-test-0002"],
                                "package": "pyyaml",
                                "version_range": "<7",
                                "summary": "Model integration test advisory.",
                                "reference_urls": ["https://example.invalid/CVE-2026-0002"],
                                "analysis": {
                                    "state": "affected",
                                    "justification": "",
                                    "action_statement": "Upgrade on next release window.",
                                    "resolved_version": "",
                                    "note": "Tracked by the runtime maintenance backlog.",
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_model(vault, context=fixed_context())
            destination = write_model(vault, report, "ops/reports/supply-chain-artifact-model.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["subject"]["name"], "sample")
            self.assertEqual(persisted["artifact_context"]["spdx_ref"], "ops/reports/spdx-sbom.json")
            self.assertEqual(persisted["artifact_context"]["openvex_ref"], "ops/reports/openvex-draft.json")
            self.assertEqual(persisted["advisories"][0]["id"], "CVE-2026-0002")
            self.assertEqual(persisted["advisories"][0]["analysis_state"], "affected")
            self.assertTrue(any(item["ref"] == persisted["subject"]["bom_ref"] for item in persisted["dependencies"]))


if __name__ == "__main__":
    unittest.main()
