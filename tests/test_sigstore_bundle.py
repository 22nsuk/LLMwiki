from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.cyclonedx_sbom import build_bom, write_bom
from ops.scripts.in_toto_statement import (
    build_in_toto_statement,
    write_in_toto_statement,
)
from ops.scripts.openvex_draft import build_openvex_draft, write_openvex_draft
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.sigstore_bundle import (
    build_bundle_verification,
    write_bundle_verification,
)
from ops.scripts.spdx_sbom import build_spdx_sbom, write_spdx_sbom
from ops.scripts.supply_chain_artifact_model import build_model, write_model

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_artifact_model import seed_runtime_surface
from tests.test_supply_chain_provenance import seed_dependency_inputs


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC),
    )


class SigstoreBundleTests(unittest.TestCase):
    def _seed_supply_chain_reports(self, vault: Path) -> dict[str, Any]:
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
        in_toto = build_in_toto_statement(vault, artifact_model=model)
        write_in_toto_statement(vault, in_toto, "ops/reports/in-toto-statement.json")
        return model

    def test_build_bundle_verification_checks_local_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            model = self._seed_supply_chain_reports(vault)
            report = build_bundle_verification(vault, artifact_model=model)
            destination = write_bundle_verification(vault, report, "ops/reports/sigstore-bundle-verification.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["status"], "local-integrity-only")
            self.assertTrue(
                next(item["pass"] for item in persisted["verification_checks"] if item["rule"] == "subject_files_exist")
            )
            self.assertTrue(
                next(
                    item["pass"] for item in persisted["verification_checks"] if item["rule"] == "in_toto_subject_digests_match"
                )
            )
            self.assertFalse(
                next(item["pass"] for item in persisted["verification_checks"] if item["rule"] == "external_bundle_observed")
            )
            self.assertTrue(any(item["path"] == "ops/reports/openvex-draft.json" for item in persisted["subjects"]))

    def test_build_bundle_verification_requires_external_bundle_for_verified_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            model = self._seed_supply_chain_reports(vault)
            bundle = vault / "tmp" / "sigstore.bundle"
            bundle.parent.mkdir(parents=True, exist_ok=True)
            bundle.write_text("placeholder external bundle reference\n", encoding="utf-8")

            report = build_bundle_verification(vault, artifact_model=model, bundle_ref="tmp/sigstore.bundle")
            destination = write_bundle_verification(vault, report, "ops/reports/sigstore-bundle-verification.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["status"], "verified-external-bundle")
            self.assertEqual(persisted["bundle_ref"], "tmp/sigstore.bundle")
            self.assertTrue(
                next(item["pass"] for item in persisted["verification_checks"] if item["rule"] == "external_bundle_observed")
            )

    def test_build_bundle_verification_keeps_failed_external_bundle_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            model = self._seed_supply_chain_reports(vault)
            bundle = vault / "tmp" / "sigstore.bundle"
            bundle.parent.mkdir(parents=True, exist_ok=True)
            bundle.write_text("placeholder external bundle reference\n", encoding="utf-8")
            (vault / "ops/reports/spdx-sbom.json").unlink()

            report = build_bundle_verification(vault, artifact_model=model, bundle_ref="tmp/sigstore.bundle")
            destination = write_bundle_verification(vault, report, "ops/reports/sigstore-bundle-verification.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["status"], "external-bundle-verification-failed")
            self.assertEqual(persisted["bundle_ref"], "tmp/sigstore.bundle")
            self.assertFalse(
                next(item["pass"] for item in persisted["verification_checks"] if item["rule"] == "subject_files_exist")
            )
            self.assertTrue(
                next(item["pass"] for item in persisted["verification_checks"] if item["rule"] == "external_bundle_observed")
            )


if __name__ == "__main__":
    unittest.main()
