from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.supply_chain.cyclonedx_sbom import build_bom, write_bom
from ops.scripts.supply_chain.in_toto_statement import (
    build_in_toto_statement,
    write_in_toto_statement,
)
from ops.scripts.supply_chain.openvex_draft import (
    build_openvex_draft,
    write_openvex_draft,
)
from ops.scripts.supply_chain.spdx_sbom import build_spdx_sbom, write_spdx_sbom
from ops.scripts.supply_chain.supply_chain_artifact_model import (
    build_model,
    write_model,
)
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_artifact_model import seed_runtime_surface
from tests.test_supply_chain_provenance import seed_dependency_inputs


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC),
    )


class InTotoStatementTests(unittest.TestCase):
    def test_build_statement_tracks_generated_artifacts_and_materials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_runtime_surface(vault)

            model = build_model(vault, context=fixed_context())
            write_model(vault, model, "ops/reports/supply-chain-artifact-model.json")
            bom = build_bom(vault, context=fixed_context())
            write_bom(vault, bom, "ops/reports/cyclonedx-bom.json")
            spdx = build_spdx_sbom(vault, artifact_model=model)
            write_spdx_sbom(vault, spdx, "ops/reports/spdx-sbom.json")
            openvex = build_openvex_draft(
                vault,
                context=fixed_context(),
                artifact_model=model,
                cyclonedx_bom=bom,
                use_existing_bom=False,
            )
            write_openvex_draft(vault, openvex, "ops/reports/openvex-draft.json")

            statement = build_in_toto_statement(vault, artifact_model=model)
            destination = write_in_toto_statement(vault, statement, "ops/reports/in-toto-statement.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["predicateType"], "https://slsa.dev/provenance/v1")
            self.assertEqual(persisted["artifact_context"]["spdx_ref"], "ops/reports/spdx-sbom.json")
            self.assertTrue(any(item["name"] == "ops/reports/spdx-sbom.json" for item in persisted["subject"]))
            self.assertTrue(
                any(
                    item["uri"] == "pyproject.toml"
                    for item in persisted["predicate"]["buildDefinition"]["resolvedDependencies"]
                )
            )
            self.assertTrue(
                any(item["uri"] == "uv.lock" for item in persisted["predicate"]["buildDefinition"]["resolvedDependencies"])
            )


if __name__ == "__main__":
    unittest.main()