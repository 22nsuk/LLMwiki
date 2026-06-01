from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.supply_chain_benchmark import build_report, write_report

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_supply_chain_artifact_model import seed_runtime_surface
from tests.test_supply_chain_provenance import seed_dependency_inputs

pytestmark = pytest.mark.slow


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC),
    )


class SupplyChainBenchmarkTests(unittest.TestCase):
    def test_build_report_compares_strict_and_cached_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_runtime_surface(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report, "ops/reports/supply-chain-benchmark.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            self.assertFalse(persisted["strict_path"]["intermediate_reuse"])
            self.assertTrue(persisted["cached_path"]["intermediate_reuse"])
            self.assertGreaterEqual(persisted["comparison"]["strict_over_cached_ratio"], 0)


if __name__ == "__main__":
    unittest.main()
