from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.supply_chain.sbom_export_mapping import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_provenance import (
    LOCKED_CI_INSTALL_SNIPPET,
    SOURCE_ZIP_SHA256,
    seed_dependency_inputs,
    seed_source_package_evidence,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.UTC),
    )


class SbomExportMappingTests(unittest.TestCase):
    def test_build_report_maps_dependency_inputs_and_public_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_source_package_evidence(vault)
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache License\n", encoding="utf-8")
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
            (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
            (vault / "ops" / "operator").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "operator" / "operator-release-summary.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "script-output-surfaces.json").write_text("{}", encoding="utf-8")
            (vault / "tests" / "test_example.py").parent.mkdir(parents=True, exist_ok=True)
            (vault / "tests" / "test_example.py").write_text(
                "def test_ok():\n    assert True\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report, "ops/reports/sbom-export-mapping.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            dependency_map = {item["path"]: item for item in persisted["dependency_input_mapping"]}
            self.assertEqual(persisted["status"], "pass")
            self.assertTrue(persisted["surface_summary"]["public_subset_of_release"])
            self.assertEqual(persisted["surface_summary"]["public_only_file_count"], 1)
            self.assertEqual(persisted["surface_summary"]["release_excluded_public_file_count"], 1)
            self.assertEqual(persisted["surface_summary"]["blocking_public_only_file_count"], 0)
            self.assertTrue(persisted["sbom_readiness"]["release_dependency_inputs_complete"])
            self.assertTrue(persisted["sbom_readiness"]["public_dependency_inputs_complete"])
            self.assertTrue(persisted["sbom_readiness"]["full_mapping_ready"])
            self.assertTrue(dependency_map["uv.lock"]["in_public_export"])
            self.assertEqual(dependency_map["uv.lock"]["authority_role"], "canonical")
            self.assertEqual(dependency_map["requirements.txt"]["authority_role"], "compatibility")
            self.assertFalse(dependency_map["requirements.txt"]["in_public_export"])
            self.assertTrue(dependency_map["pyproject.toml"]["in_release_manifest"])
            self.assertEqual(persisted["provenance_summary"]["locked_dependency_edge_count"], 1)
            self.assertEqual(persisted["provenance_summary"]["source_package_evidence_status"], "pass")
            self.assertEqual(persisted["provenance_summary"]["source_zip_sha256"], SOURCE_ZIP_SHA256)
            self.assertTrue(persisted["sbom_readiness"]["source_package_evidence_present"])
            self.assertTrue(persisted["sbom_readiness"]["source_package_reproducible"])
            public_exclusions = {
                item["path"]
                for item in persisted["export_mapping"]
                if item["release_manifest_exclusion"]
            }
            self.assertEqual(
                public_exclusions,
                {"ops/script-output-surfaces.json"},
            )
            self.assertEqual(persisted["gaps"], [])

    def test_write_report_accepts_warn_shape_for_public_export_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache License\n", encoding="utf-8")
            (vault / "THIRD_PARTY_NOTICES.md").write_text("# Notices\n", encoding="utf-8")
            (vault / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
            (vault / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
            (vault / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
            (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())
            report["dependency_input_mapping"][0]["in_public_export"] = False
            report["gaps"] = [
                {
                    "severity": "warn",
                    "code": "dependency-input-missing-from-public-export",
                    "path": "pyproject.toml",
                    "details": "Dependency evidence is not mirrored into the public export surface.",
                }
            ]
            report["status"] = "warn"
            report["sbom_readiness"]["public_dependency_inputs_complete"] = False
            report["sbom_readiness"]["full_mapping_ready"] = False

            destination = write_report(vault, report, "ops/reports/sbom-export-mapping.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "warn")
            self.assertEqual(
                persisted["gaps"][0]["code"],
                "dependency-input-missing-from-public-export",
            )


if __name__ == "__main__":
    unittest.main()
