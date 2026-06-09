from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest
from ops.scripts.release_closeout_fixed_point_cost_trend import (
    DEFAULT_OUT,
    FIXED_POINT_REPORT_PATH,
    build_report,
    main,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT
    / "ops"
    / "schemas"
    / "release-closeout-fixed-point-cost-trend.schema.json"
)


def context_at(hour: int) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 9, hour, 0, tzinfo=dt.UTC),
    )


class ReleaseCloseoutFixedPointCostTrendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._copy_support_file(
            "ops/schemas/release-closeout-fixed-point-cost-trend.schema.json"
        )
        self._copy_support_file("ops/policies/release-closeout-fixed-point.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            (REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8"
        )

    def _write_fixed_point(self, *, digest_seed: str, writer_total_ms: int) -> None:
        payload: dict[str, Any] = {
            "generated_at": f"2026-05-09T{digest_seed}:00:00Z",
            "status": "pass",
            "converged": True,
            "iteration_count": 2,
            "duration_summary": {
                "iteration_count": 2,
                "command_run_count": 2,
                "total_duration_ms": writer_total_ms,
                "writer_costs": [
                    {
                        "name": "release-evidence-dashboard",
                        "target": "release-evidence-dashboard-report",
                        "run_count": 1,
                        "total_duration_ms": writer_total_ms,
                        "average_duration_ms": writer_total_ms,
                        "max_duration_ms": writer_total_ms,
                    }
                ],
            },
        }
        path = self.vault / FIXED_POINT_REPORT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _make_policy_sensitive(self) -> None:
        path = self.vault / "ops" / "policies" / "release-closeout-fixed-point.json"
        policy = json.loads(path.read_text(encoding="utf-8"))
        policy["cost_trend"]["thresholds"]["default"].update(
            {
                "min_previous_samples": 1,
                "total_duration_ms_attention": 5000,
                "max_duration_ms_attention": 5000,
                "relative_total_duration_attention_multiplier": 2.0,
                "minimum_relative_delta_ms": 1000,
            }
        )
        path.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def test_cost_trend_records_sample_and_validates(self) -> None:
        self._write_fixed_point(digest_seed="10", writer_total_ms=1000)

        report = build_report(self.vault, context=context_at(10))

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["fixed_point_report"]["sample_available"])
        self.assertEqual(report["sample_count"], 1)
        self.assertEqual(report["latest_sample"]["total_duration_ms"], 1000)
        self.assertRegex(
            report["latest_sample"]["fixed_point_report_digest"], r"^[a-f0-9]{64}$"
        )
        self.assertEqual(report["threshold_summary"]["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_cost_trend_marks_attention_when_writer_cost_surges(self) -> None:
        self._make_policy_sensitive()
        self._write_fixed_point(digest_seed="10", writer_total_ms=1000)
        first = build_report(self.vault, context=context_at(10))
        write_report(self.vault, first, DEFAULT_OUT)
        self._write_fixed_point(digest_seed="11", writer_total_ms=9000)

        second = build_report(self.vault, context=context_at(11))

        self.assertEqual(second["status"], "attention")
        self.assertEqual(second["sample_count"], 2)
        trend = second["writer_trends"][0]
        self.assertEqual(trend["target"], "release-evidence-dashboard-report")
        self.assertEqual(trend["threshold_status"], "attention")
        self.assertIn("total_duration_ms_attention", trend["breached_thresholds"])
        self.assertIn(
            "relative_total_duration_attention_multiplier", trend["breached_thresholds"]
        )
        self.assertEqual(
            second["threshold_summary"]["breached_writers"],
            ["release-evidence-dashboard-report"],
        )
        self.assertEqual(validate_with_schema(second, load_schema(SCHEMA_PATH)), [])

    def test_main_no_fail_writes_attention_diagnostic_when_fixed_point_missing(self) -> None:
        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--out",
                "tmp/release-closeout-fixed-point-cost-trend-ci.json",
                "--no-fail",
            ]
        )

        self.assertEqual(exit_code, 0)
        report = json.loads(
            (
                self.vault / "tmp" / "release-closeout-fixed-point-cost-trend-ci.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "attention")
        self.assertFalse(report["fixed_point_report"]["sample_available"])
        self.assertNotEqual(report["fixed_point_report"]["load_status"], "ok")
        self.assertEqual(report["fixed_point_report"]["digest"], "")
        self.assertEqual(report["sample_count"], 0)
        self.assertIsNone(report["latest_sample"])
        self.assertEqual(report["samples"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
