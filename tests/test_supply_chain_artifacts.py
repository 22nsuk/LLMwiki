from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.supply_chain_artifacts import main as run_supply_chain_artifacts
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_provenance import LOCKED_CI_INSTALL_SNIPPET, seed_dependency_inputs


class SupplyChainArtifactsPipelineTests(unittest.TestCase):
    def _seed_pipeline_vault(self, vault: Path) -> None:
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
        (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (vault / ".github" / "workflows" / "ci.yml").write_text(
            LOCKED_CI_INSTALL_SNIPPET,
            encoding="utf-8",
        )
        (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
        (vault / "ops" / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
        (vault / "tests" / "test_example.py").parent.mkdir(parents=True, exist_ok=True)
        (vault / "tests" / "test_example.py").write_text(
            "def test_ok():\n    assert True\n",
            encoding="utf-8",
        )

    def test_pipeline_writes_all_reports_and_reuses_single_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            self._seed_pipeline_vault(vault)

            exit_code = run_supply_chain_artifacts(["--vault", str(vault)])

            self.assertEqual(exit_code, 0)
            reports_dir = vault / "ops" / "reports"
            expected = {
                "security-advisories.json",
                "supply-chain-provenance.json",
                "supply-chain-gate-report.json",
                "sbom-export-mapping.json",
                "sbom-readiness-gate-report.json",
                "supply-chain-artifact-model.json",
                "cyclonedx-bom.json",
                "spdx-sbom.json",
                "openvex-draft.json",
                "in-toto-statement.json",
                "sigstore-bundle-verification.json",
            }
            self.assertEqual({path.name for path in reports_dir.iterdir()}, expected)
            bom = json.loads((reports_dir / "cyclonedx-bom.json").read_text(encoding="utf-8"))
            openvex = json.loads((reports_dir / "openvex-draft.json").read_text(encoding="utf-8"))
            spdx = json.loads((reports_dir / "spdx-sbom.json").read_text(encoding="utf-8"))
            self.assertEqual(openvex["metadata"]["component_count"], len(bom["components"]))
            self.assertEqual(
                openvex["metadata"]["dependency_edge_count"],
                sum(len(item.get("dependsOn", [])) for item in bom["dependencies"]),
            )
            self.assertEqual(spdx["artifact_context"]["openvex_ref"], "ops/reports/openvex-draft.json")

    def test_pipeline_ignores_inaccessible_excluded_virtualenv_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            self._seed_pipeline_vault(vault)
            (vault / ".venv" / "lib64").mkdir(parents=True)

            original_is_file = Path.is_file

            def patched_is_file(path: Path) -> bool:
                if path == vault / ".venv" / "lib64":
                    raise OSError(1920, "The system cannot access the file")
                return original_is_file(path)

            with mock.patch.object(Path, "is_file", autospec=True, side_effect=patched_is_file):
                exit_code = run_supply_chain_artifacts(["--vault", str(vault)])

            self.assertEqual(exit_code, 0)
            reports_dir = vault / "ops" / "reports"
            self.assertTrue((reports_dir / "cyclonedx-bom.json").exists())
            self.assertTrue((reports_dir / "openvex-draft.json").exists())


if __name__ == "__main__":
    unittest.main()
