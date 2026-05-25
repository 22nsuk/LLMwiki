from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.wiki_lint import lint

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.slow


class WikiLintRawRegistryDiagnosticsTest(unittest.TestCase):
    def test_lint_surfaces_registry_source_trace_resolution_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "raw-registry.json").write_text("{broken", encoding="utf-8")

            report = lint(vault)

            warning = next(
                issue
                for issue in report["warnings"]
                if issue["type"] == "raw_registry_source_trace_resolution_warning"
            )
            self.assertEqual(warning["page"], "ops/raw-registry.json")
            self.assertEqual(
                warning["detail"]["diagnostic_category"],
                "raw_registry_export_enrichment_load_failed",
            )
            self.assertEqual(
                warning["detail"]["diagnostic_type"],
                "raw_registry_export_invalid_json",
            )


if __name__ == "__main__":
    unittest.main()
