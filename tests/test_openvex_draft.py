from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.cyclonedx_sbom import build_bom
from ops.scripts.openvex_draft import build_openvex_draft, write_openvex_draft
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.supply_chain_artifact_model import build_model

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


class OpenVexDraftTests(unittest.TestCase):
    def test_build_openvex_draft_records_applicability_shell_without_scan_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
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

            report = build_openvex_draft(vault, context=fixed_context())
            destination = write_openvex_draft(vault, report, "ops/reports/openvex-draft.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            bom = build_bom(vault, context=fixed_context())

            self.assertEqual(persisted["@context"], "https://openvex.dev/ns/v0.2.0")
            self.assertEqual(persisted["generated_at"], "2026-04-20T12:00:00Z")
            self.assertEqual(persisted["timestamp"], "2026-04-20T12:00:00Z")
            self.assertEqual(persisted["generated_at"], persisted["timestamp"])
            self.assertEqual(persisted["artifact_kind"], "openvex_draft")
            self.assertEqual(persisted["artifact_status"], "current")
            self.assertEqual(persisted["currentness"]["status"], "current")
            self.assertEqual(persisted["tooling"]["vulnerability_source"], "not_scanned")
            self.assertEqual(
                persisted["tooling"]["spdx_emitter_decision"],
                "shared-artifact-model-spdx-enabled",
            )
            self.assertEqual(persisted["artifact_context"]["spdx_ref"], "ops/reports/spdx-sbom.json")
            self.assertIn("artifact_model", persisted["input_fingerprints"])
            self.assertEqual(persisted["statements"], [])
            self.assertEqual(persisted["metadata"]["status"], "draft")
            self.assertEqual(persisted["metadata"]["statement_count"], 0)
            self.assertEqual(persisted["metadata"]["advisory_count"], 0)
            self.assertEqual(persisted["metadata"]["dependency_edge_count"], 2)
            self.assertEqual(persisted["metadata"]["component_count"], len(bom["components"]))

    def test_build_openvex_draft_reuses_existing_cyclonedx_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "pyproject.toml").write_text(
                '[project]\nname = "sample"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "cyclonedx-bom.json").write_text(
                json.dumps(
                    {
                        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
                        "bomFormat": "CycloneDX",
                        "specVersion": "1.6",
                        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000001",
                        "version": 1,
                        "metadata": {
                            "timestamp": "2026-04-20T12:00:00Z",
                            "component": {
                                "type": "application",
                                "bom-ref": "pkg:generic/sample@0.1.0",
                                "name": "sample",
                                "version": "0.1.0",
                                "purl": "pkg:generic/sample@0.1.0",
                            },
                            "tools": {
                                "components": [
                                    {
                                        "type": "application",
                                        "name": "ops.scripts.cyclonedx_sbom",
                                        "version": "0.1.0-draft",
                                        "bom-ref": "pkg:generic/ops.scripts.cyclonedx_sbom@0.1.0-draft",
                                    }
                                ]
                            },
                            "properties": [],
                        },
                        "components": [
                            {
                                "type": "library",
                                "bom-ref": "pkg:pypi/existing-component@1.0.0",
                                "name": "existing-component",
                                "version": "1.0.0",
                                "purl": "pkg:pypi/existing-component@1.0.0",
                            },
                        ],
                        "dependencies": [
                            {
                                "ref": "pkg:generic/sample@0.1.0",
                                "dependsOn": ["pkg:pypi/existing-component@1.0.0"],
                            },
                            {
                                "ref": "pkg:pypi/existing-component@1.0.0",
                                "dependsOn": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            artifact_model = build_model(vault, context=fixed_context())
            artifact_model["components"].append(
                {
                    "type": "library",
                    "bom-ref": "pkg:pypi/extra-component@2.0.0",
                    "name": "extra-component",
                    "version": "2.0.0",
                    "purl": "pkg:pypi/extra-component@2.0.0",
                }
            )

            report = build_openvex_draft(vault, context=fixed_context(), artifact_model=artifact_model)

            self.assertEqual(report["artifact_kind"], "openvex_draft")
            self.assertEqual(report["currentness"]["status"], "current")
            self.assertIn("cyclonedx_bom", report["input_fingerprints"])
            self.assertEqual(report["metadata"]["component_count"], 1)
            self.assertEqual(report["metadata"]["dependency_edge_count"], 1)

    def test_build_openvex_draft_authors_statement_from_repo_native_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
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
            (vault / "ops").mkdir(exist_ok=True)
            (vault / "ops" / "advisories.json").write_text(
                json.dumps(
                    {
                        "advisories": [
                            {
                                "id": "CVE-2026-0001",
                                "aliases": ["GHSA-test-0001"],
                                "package": "pyyaml",
                                "version_range": "<7",
                                "summary": "Sample repo-native advisory.",
                                "reference_urls": ["https://example.invalid/CVE-2026-0001"],
                                "analysis": {
                                    "state": "not_affected",
                                    "justification": "code_not_reachable",
                                    "action_statement": "",
                                    "resolved_version": "",
                                    "note": "Only documentation tooling uses the affected parser path.",
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_openvex_draft(vault, context=fixed_context())

            self.assertEqual(report["artifact_kind"], "openvex_draft")
            self.assertEqual(report["generated_at"], "2026-04-20T12:00:00Z")
            self.assertEqual(report["tooling"]["vulnerability_source"], "repo-native-advisory-input")
            self.assertEqual(report["metadata"]["statement_count"], 1)
            self.assertEqual(report["metadata"]["advisory_count"], 1)
            self.assertEqual(report["statements"][0]["status"], "not_affected")
            self.assertEqual(report["statements"][0]["vulnerability"]["id"], "CVE-2026-0001")
            self.assertEqual(report["statements"][0]["products"][0]["@id"], "pkg:pypi/pyyaml@6.0.3")


if __name__ == "__main__":
    unittest.main()
