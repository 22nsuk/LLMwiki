from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.supply_chain.spdx_sbom import build_spdx_sbom, write_spdx_sbom
from ops.scripts.supply_chain.supply_chain_artifact_model import build_model
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_artifact_model import seed_runtime_surface
from tests.test_supply_chain_provenance import seed_dependency_inputs


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC),
    )


class SpdxSbomTests(unittest.TestCase):
    def test_build_spdx_sbom_projects_model_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_runtime_surface(vault)

            model = build_model(vault, context=fixed_context())
            report = build_spdx_sbom(vault, artifact_model=model)
            destination = write_spdx_sbom(vault, report, "ops/reports/spdx-sbom.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["artifact_kind"], "spdx_sbom")
            self.assertEqual(persisted["producer"], "ops.scripts.spdx_sbom")
            self.assertEqual(persisted["generated_at"], model["generated_at"])
            self.assertEqual(persisted["currentness"]["status"], "current")
            self.assertEqual(persisted["spdxVersion"], "SPDX-2.3")
            self.assertEqual(len(persisted["packages"]), len(model["components"]) + 1)
            self.assertEqual(persisted["artifact_context"]["model_ref"], "ops/reports/supply-chain-artifact-model.json")
            pyyaml_package = next(item for item in persisted["packages"] if item["name"].lower() == "pyyaml")
            self.assertTrue(
                any(
                    relationship["relatedSpdxElement"] == pyyaml_package["SPDXID"]
                    for relationship in persisted["relationships"]
                )
            )


if __name__ == "__main__":
    unittest.main()
