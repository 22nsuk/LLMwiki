from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.test.ci_tier_lane_bridge import build_report
from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = [
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]


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
        self.assertEqual(report["summary"]["missing_workflow_run_text_count"], 0)
        self.assertEqual(report["summary"]["missing_ci_entrypoint_count"], 0)
        self.assertEqual(report["summary"]["missing_ci_step_count"], 0)
        self.assertIn("fast", report["workflow_tiers"])
        self.assertTrue(all(item["registry_backed"] for item in report["bridge"]))
        by_tier = {item["ci_tier"]: item for item in report["bridge"]}
        self.assertTrue(all(item["ci_entrypoint_declared"] for item in by_tier.values()))
        self.assertTrue(all(not item["missing_ci_steps"] for item in by_tier.values()))
        release_closeout_commands = {
            line.strip()
            for line in by_tier["release-closeout-regression"]["workflow_run_text"].splitlines()
            if line.strip()
        }
        self.assertIn(
            "make release-closeout-finality-verify-ci-artifact",
            release_closeout_commands,
        )
        self.assertNotIn("make release-closeout-finality-verify", release_closeout_commands)
        self.assertIn(
            "make release-authority-sealed-preflight",
            release_closeout_commands,
        )
        self.assertIn("set +e", release_closeout_commands)
        self.assertIn("finality_status=0", release_closeout_commands)
        self.assertIn("sealed_preflight_status=0", release_closeout_commands)
        self.assertIn("finality_status=$?", release_closeout_commands)
        self.assertIn("sealed_preflight_status=$?", release_closeout_commands)
        self.assertIn("exit 0", release_closeout_commands)
        report_contract_run = by_tier["report-contract"]["workflow_run_text"]
        self.assertEqual(report_contract_run.strip(), "make ci-report-contract-tier")
        self.assertEqual(
            validate_with_schema(
                report,
                load_schema(Path("ops/schemas/ci-tier-lane-bridge.schema.json")),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
