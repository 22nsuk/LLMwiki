from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.cyclonedx_sbom import build_bom, write_bom
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import CYCLONEDX_16_SCHEMA_PATH, CYCLONEDX_16_SCHEMA_URI
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_provenance import (
    LOCKED_CI_INSTALL_SNIPPET,
    SOURCE_ZIP_SHA256,
    seed_dependency_inputs,
    seed_source_package_evidence,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.timezone.utc),
    )


class CycloneDxSbomTests(unittest.TestCase):
    def test_build_bom_from_locked_dependencies_validates_and_maps_runtime_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_source_package_evidence(vault)
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

            bom = build_bom(vault, context=fixed_context())
            destination = write_bom(vault, bom, "ops/reports/cyclonedx-bom.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertEqual(persisted["bomFormat"], "CycloneDX")
            self.assertEqual(persisted["specVersion"], "1.6")
            self.assertEqual(persisted["metadata"]["component"]["name"], "sample")
            self.assertTrue(persisted["serialNumber"].startswith("urn:uuid:"))

            components = {item["name"]: item for item in persisted["components"]}
            self.assertIn("pyyaml", {name.lower() for name in components})
            self.assertEqual(components["pyyaml"]["version"], "6.0.3")
            self.assertEqual(components["pyyaml"]["scope"], "required")
            self.assertEqual(components["typing-extensions"]["scope"], "required")
            self.assertEqual(components["pytest"]["scope"], "excluded")

            root_ref = persisted["metadata"]["component"]["bom-ref"]
            deps = {item["ref"]: item.get("dependsOn", []) for item in persisted["dependencies"]}
            self.assertIn(root_ref, deps)
            self.assertEqual(deps[root_ref], ["pkg:pypi/pyyaml@6.0.3"])
            self.assertEqual(deps["pkg:pypi/pyyaml@6.0.3"], ["pkg:pypi/typing-extensions@4.15.0"])

            properties = {
                item["name"]: item["value"]
                for item in persisted["metadata"]["properties"]
            }
            artifact_envelope = json.loads(properties["urn:openai:artifact-envelope"])
            self.assertEqual(properties["urn:openai:sbom:locked-dependency-edge-count"], "1")
            self.assertEqual(
                properties["urn:openai:sbom:spdx-emitter-decision"],
                "shared-artifact-model-spdx-enabled",
            )
            self.assertEqual(properties["urn:openai:sbom:model-ref"], "ops/reports/supply-chain-artifact-model.json")
            self.assertEqual(properties["urn:openai:sbom:spdx-ref"], "ops/reports/spdx-sbom.json")
            self.assertEqual(properties["urn:openai:sbom:source-package-status"], "pass")
            self.assertEqual(properties["urn:openai:sbom:source-package-reproducibility-status"], "pass")
            self.assertEqual(properties["urn:openai:sbom:source-zip-sha256"], SOURCE_ZIP_SHA256)
            self.assertEqual(artifact_envelope["artifact_kind"], "cyclonedx_sbom")
            self.assertEqual(artifact_envelope["artifact_status"], "current")
            self.assertEqual(artifact_envelope["currentness"]["status"], "current")
            self.assertEqual(artifact_envelope["generated_at"], persisted["metadata"]["timestamp"])

    def test_http_schema_uri_validates_offline_through_local_alias(self) -> None:
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

            bom = build_bom(vault, context=fixed_context())
            http_schema = load_schema(CYCLONEDX_16_SCHEMA_URI)
            vendored_schema = load_schema(vault / CYCLONEDX_16_SCHEMA_PATH)

            self.assertEqual(bom["$schema"], CYCLONEDX_16_SCHEMA_URI)
            self.assertEqual(http_schema["title"], vendored_schema["title"])
            self.assertEqual(validate_with_schema(bom, http_schema), [])

    def test_build_bom_falls_back_to_declared_dependencies_when_lock_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "pyproject.toml").write_text(
                """
[project]
name = "fallback-app"
version = "1.2.3"
dependencies = [
  "Requests>=2.32,<3",
]
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (vault / "README.md").write_text("root\n", encoding="utf-8")
            (vault / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
            (vault / "THIRD_PARTY_NOTICES.md").write_text("# Notices\n", encoding="utf-8")
            (vault / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
            (vault / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
            (vault / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
            (vault / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            (vault / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

            bom = build_bom(vault, context=fixed_context())
            components = {item["name"]: item for item in bom["components"]}
            self.assertIn("Requests", components)
            self.assertNotIn("version", components["Requests"])
            self.assertEqual(components["Requests"]["scope"], "required")
            self.assertEqual(
                bom["dependencies"][0]["dependsOn"],
                ["pkg:pypi/requests"],
            )
            metadata_properties = {
                item["name"]: item["value"]
                for item in bom["metadata"]["properties"]
            }
            self.assertIn("urn:openai:artifact-envelope", metadata_properties)


if __name__ == "__main__":
    unittest.main()
