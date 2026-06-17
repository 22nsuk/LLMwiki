from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_lane_summary import build_report, main, write_report
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
LANE_SUMMARY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-lane-summary.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 3, 9, 0, tzinfo=dt.UTC),
    )


@dataclass(frozen=True)
class LaneSummaryInputOptions:
    cohort_status: str = "pass"
    clean_lane_status: str = "pass"
    release_readiness_state: str = "clean_pass"
    machine_release_allowed: bool = True
    operator_release_allowed: bool = True
    accepted_risk_family_count: int = 0
    accepted_risk_instance_count: int = 0
    accepted_risk_count: int = 0
    gate_attention_count: int = 0
    clean_lane_blocking_family_count: int = 0
    learning_claim_blocking_family_count: int = 0
    advisory_lifecycle_family_count: int = 0
    blockers: list[dict[str, Any]] | None = None
    claims_learning_improved: bool = False
    learning_claim_allowed: bool = False
    learning_claim_guard_status: str = "pass"


def lane_summary_input_options(**overrides: Any) -> LaneSummaryInputOptions:
    return replace(LaneSummaryInputOptions(), **overrides)


class ReleaseLaneSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_report(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_inputs(self, **overrides: Any) -> None:
        options = lane_summary_input_options(**overrides)
        sealed_release_status = (
            "sealed_clean_pass"
            if options.release_readiness_state == "clean_pass"
            and options.machine_release_allowed
            else "unsealed_distribution_not_provided"
        )
        blocker_reason_ids = (
            [] if options.machine_release_allowed else ["machine_release_not_allowed"]
        )
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "release_readiness_state": options.release_readiness_state,
                "release_authority_status": options.release_readiness_state,
                "semantic_release_status": options.release_readiness_state,
                "sealed_release_status": sealed_release_status,
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": options.release_readiness_state,
                        "semantic_release_status": options.release_readiness_state,
                        "sealed_release_status": sealed_release_status,
                    },
                    "blocker_reason_ids": blocker_reason_ids,
                },
                "machine_release_allowed": options.machine_release_allowed,
                "operator_release_allowed": options.operator_release_allowed,
                "summary": {
                    "accepted_risk_family_count": options.accepted_risk_family_count,
                    "accepted_risk_instance_count": options.accepted_risk_instance_count,
                },
                "accepted_risk_count_by_scope": {
                    "learning_claim_blocking_family_count": (
                        options.learning_claim_blocking_family_count
                    ),
                    "advisory_lifecycle_family_count": (
                        options.advisory_lifecycle_family_count
                    ),
                },
                "blockers": options.blockers or [],
                "currentness": {"status": "current"},
            },
        )
        self._write_report(
            "ops/reports/release-evidence-cohort.json",
            {
                "status": options.cohort_status,
                "clean_lane_contract": {
                    "status": options.clean_lane_status,
                    "clean_lane_blocking_family_count": (
                        options.clean_lane_blocking_family_count
                    ),
                },
                "currentness": {"status": "current"},
            },
        )
        self._write_report(
            "ops/reports/release-evidence-dashboard.json",
            {
                "status": "pass",
                "summary": {
                    "accepted_risk_count": options.accepted_risk_count,
                    "gate_attention_count": options.gate_attention_count,
                },
                "currentness": {"status": "current"},
            },
        )
        self._write_report(
            "ops/reports/learning-delta-scoreboard.json",
            {
                "status": "pass",
                "summary": {
                    "claims_learning_improved": options.claims_learning_improved,
                    "learning_claim_allowed": options.learning_claim_allowed,
                },
                "learning_claim_guard": {
                    "status": options.learning_claim_guard_status,
                },
                "currentness": {"status": "current"},
            },
        )

    def test_lane_summary_shows_all_pass_for_clean_release(self) -> None:
        self._write_inputs()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        ls = report["lane_summary"]
        self.assertEqual(ls["cohort_status"], "pass")
        self.assertEqual(ls["clean_lane_status"], "pass")
        self.assertEqual(ls["conditional_lane_status"], "pass")
        self.assertEqual(ls["auto_improve_lane_status"], "pass")
        self.assertEqual(ls["learning_lane_status"], "pass")
        self.assertEqual(ls["machine_release_status"], "allowed")
        self.assertEqual(ls["operator_release_status"], "allowed")
        self.assertEqual(ls["release_authority_status"], "clean_pass")
        self.assertEqual(ls["sealed_release_status"], "sealed_clean_pass")
        self.assertEqual(ls["accepted_risk_family_count"], 0)
        self.assertEqual(ls["accepted_risk_instance_count"], 0)
        self.assertEqual(ls["accepted_risk_count"], 0)
        self.assertEqual(ls["gate_attention_count"], 0)
        self.assertNotIn("accepted_risk_gate_attention_count", ls)
        self.assertEqual(ls["clean_lane_blocking_family_count"], 0)
        self.assertEqual(ls["learning_claim_blocking_family_count"], 0)
        self.assertEqual(ls["advisory_lifecycle_family_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(LANE_SUMMARY_SCHEMA_PATH)), [])

    def test_lane_summary_shows_conditional_state(self) -> None:
        self._write_inputs(
            release_readiness_state="conditional_pass",
            machine_release_allowed=False,
            operator_release_allowed=True,
            accepted_risk_family_count=1,
            accepted_risk_instance_count=1,
            accepted_risk_count=1,
            gate_attention_count=2,
            clean_lane_blocking_family_count=1,
            advisory_lifecycle_family_count=1,
            clean_lane_status="fail",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        ls = report["lane_summary"]
        self.assertEqual(ls["cohort_status"], "pass")
        self.assertEqual(ls["clean_lane_status"], "fail")
        self.assertEqual(ls["conditional_lane_status"], "pass")
        self.assertEqual(ls["auto_improve_lane_status"], "pass")
        self.assertEqual(ls["machine_release_status"], "blocked")
        self.assertEqual(ls["operator_release_status"], "allowed")
        self.assertEqual(ls["release_authority_status"], "conditional_pass")
        self.assertEqual(ls["sealed_release_status"], "unsealed_distribution_not_provided")
        self.assertEqual(ls["accepted_risk_family_count"], 1)
        self.assertEqual(ls["accepted_risk_instance_count"], 1)
        self.assertEqual(ls["accepted_risk_count"], 1)
        self.assertEqual(ls["gate_attention_count"], 2)
        self.assertNotIn("accepted_risk_gate_attention_count", ls)
        self.assertEqual(ls["clean_lane_blocking_family_count"], 1)
        self.assertEqual(ls["advisory_lifecycle_family_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(LANE_SUMMARY_SCHEMA_PATH)), [])

    def test_lane_summary_blocks_learning_lane_without_blocking_source_clean_lane(self) -> None:
        self._write_inputs(
            claims_learning_improved=True,
            learning_claim_allowed=False,
            learning_claim_guard_status="blocked",
            learning_claim_blocking_family_count=1,
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        ls = report["lane_summary"]
        self.assertEqual(ls["clean_lane_status"], "pass")
        self.assertEqual(ls["auto_improve_lane_status"], "pass")
        self.assertEqual(ls["machine_release_status"], "allowed")
        self.assertEqual(ls["learning_lane_status"], "blocked")
        self.assertEqual(ls["learning_claim_guard_status"], "blocked")
        self.assertEqual(ls["learning_claim_blocking_family_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(LANE_SUMMARY_SCHEMA_PATH)), [])

    def test_lane_summary_blocks_auto_improve_and_learning_lanes_without_blocking_source_release(self) -> None:
        self._write_inputs(
            blockers=[
                {
                    "source": "auto_improve_readiness",
                    "source_path": "ops/reports/auto-improve-readiness.json",
                    "code": "learning_blocked_by_execution_not_runnable",
                    "severity": "blocker",
                    "gate_effect": "blocks_execution",
                    "message": "no runnable proposal is available",
                    "required_evidence": ["restore runnable proposal queue"],
                    "clean_lane_effect": "does_not_block_clean_lane",
                    "conditional_lane_effect": "not_applicable",
                    "learning_lane_effect": "blocks_learning_claim",
                    "advisory_lifecycle_effect": "not_applicable",
                }
            ],
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        ls = report["lane_summary"]
        self.assertEqual(ls["clean_lane_status"], "pass")
        self.assertEqual(ls["machine_release_status"], "allowed")
        self.assertEqual(ls["auto_improve_lane_status"], "blocked")
        self.assertEqual(ls["learning_lane_status"], "blocked")
        self.assertEqual(ls["learning_claim_blocking_family_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(LANE_SUMMARY_SCHEMA_PATH)), [])

    def test_lane_summary_shows_blocked_when_cohort_fails(self) -> None:
        self._write_inputs(
            cohort_status="fail",
            release_readiness_state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        ls = report["lane_summary"]
        self.assertEqual(ls["cohort_status"], "fail")
        self.assertEqual(ls["conditional_lane_status"], "fail")
        self.assertEqual(ls["machine_release_status"], "blocked")
        self.assertEqual(ls["operator_release_status"], "blocked")
        self.assertEqual(ls["release_authority_status"], "blocked")
        self.assertEqual(ls["sealed_release_status"], "unsealed_distribution_not_provided")
        self.assertEqual(validate_with_schema(report, load_schema(LANE_SUMMARY_SCHEMA_PATH)), [])

    def test_lane_summary_provenance_lists_sources(self) -> None:
        self._write_inputs()

        report = build_report(self.vault, context=fixed_context())

        provenance = report["provenance"]
        self.assertEqual(provenance["cohort_source"], "ops/reports/release-evidence-cohort.json")
        self.assertEqual(provenance["closeout_source"], "ops/reports/release-closeout-summary.json")
        self.assertEqual(provenance["dashboard_source"], "ops/reports/release-evidence-dashboard.json")
        self.assertEqual(provenance["learning_delta_scoreboard_source"], "ops/reports/learning-delta-scoreboard.json")

    def test_main_exits_zero_for_pass(self) -> None:
        self._write_inputs()

        exit_code = main(["--vault", self.vault.as_posix(), "--out", "ops/reports/test-lane-summary.json"])

        self.assertEqual(exit_code, 0)
        destination = self.vault / "ops" / "reports" / "test-lane-summary.json"
        self.assertTrue(destination.exists())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "pass")

    def test_main_exits_one_for_fail(self) -> None:
        self._write_inputs(
            cohort_status="fail",
            release_readiness_state="blocked",
            machine_release_allowed=False,
            operator_release_allowed=False,
        )

        exit_code = main(["--vault", self.vault.as_posix(), "--out", "ops/reports/test-lane-summary.json"])

        self.assertEqual(exit_code, 1)
        destination = self.vault / "ops" / "reports" / "test-lane-summary.json"
        self.assertTrue(destination.exists())
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "fail")

    def test_write_report_validates_schema(self) -> None:
        self._write_inputs()
        report = build_report(self.vault, context=fixed_context())

        destination = write_report(self.vault, report, "ops/reports/test-lane-summary.json")

        self.assertTrue(destination.exists())
        self.assertEqual(validate_with_schema(report, load_schema(LANE_SUMMARY_SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
