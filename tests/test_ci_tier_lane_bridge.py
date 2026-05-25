from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import pytest
from ops.scripts.ci_tier_lane_bridge import build_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = pytest.mark.report_contract


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


class CiTierLaneBridgeTests(unittest.TestCase):
    def test_ci_matrix_tiers_are_backed_by_lane_registry(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["missing_in_workflow_count"], 0)
        self.assertEqual(report["summary"]["unknown_in_workflow_count"], 0)
        self.assertEqual(report["summary"]["missing_bridge_count"], 0)
        self.assertIn("fast", report["workflow_tiers"])
        self.assertTrue(all(item["registry_backed"] for item in report["bridge"]))
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(Path("ops/schemas/ci-tier-lane-bridge.schema.json")),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
