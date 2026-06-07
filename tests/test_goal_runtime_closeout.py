from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.goal_runtime_closeout import (
    GoalRuntimeCloseoutRequest,
    build_report,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "goal-runtime-closeout-plan.schema.json"
pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 21, 0, 0, tzinfo=dt.UTC),
    )


class GoalRuntimeCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/goal-runtime-closeout-plan.schema.json")
        self._fingerprint = release_source_tree_fingerprint(self.vault)
        self._seed_current_evidence()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _seed_evidence_report(self, rel_path: str, *, fingerprint: str, status: str = "pass") -> None:
        self._write_json(
            rel_path,
            {
                "status": status,
                "source_tree_fingerprint": fingerprint,
                "currentness": {"status": "current"},
            },
        )

    def _seed_current_evidence(self) -> None:
        for rel_path in (
            "ops/reports/release-smoke-report.json",
            "ops/reports/source-package-clean-extract.json",
            "ops/reports/public-check-summary.json",
            "ops/reports/test-execution-summary-full.json",
        ):
            self._seed_evidence_report(rel_path, fingerprint=self._fingerprint)

    def test_cheap_budget_reuses_current_expensive_evidence(self) -> None:
        report = build_report(
            GoalRuntimeCloseoutRequest(
                vault=self.vault,
                budget="cheap",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(
            {
                "source_paths",
                "budget",
                "source_fingerprint",
                "release_smoke",
                "source_package",
                "public_check",
                "full_suite",
            }
            & set(report["input_fingerprints"]),
            {
                "source_paths",
                "budget",
                "source_fingerprint",
                "release_smoke",
                "source_package",
                "public_check",
                "full_suite",
            },
        )
        self.assertEqual(
            [
                "candidate_convergence",
                "expensive_evidence",
                "canonical_publish",
                "post_publish_finalization",
            ],
            list(dict.fromkeys(item["phase_group"] for item in report["phase_decisions"])),
        )
        self.assertFalse(report["summary"]["full_suite_required"])
        self.assertEqual(report["summary"]["blocked_by_budget_count"], 0)
        self.assertNotIn("test-execution-summary-full-refresh", report["recommended_targets"])
        self.assertNotIn("test-execution-summary-full-current-or-refresh", report["recommended_targets"])
        self.assertEqual(
            report["recommended_targets"],
            [
                "goal-runtime-closeout-candidate-converge",
                "goal-runtime-closeout-publish",
                "goal-runtime-closeout-finalize",
            ],
        )
        self.assertEqual(report["transaction"]["mode"], "run_local_candidate_then_publish_once")
        self.assertEqual(
            report["transaction"]["candidate_targets"][:3],
            [
                "report-schema-samples-check",
                "goal-runtime-clean-transient",
                "goal-runtime-local-evidence-converge",
            ],
        )
        self.assertEqual(
            report["transaction"]["candidate_outputs"],
            {
                "script_output_surfaces": "runs/goal-auto-improve-trial/state/closeout/script-output-surfaces.json",
                "generated_artifact_index": (
                    "runs/goal-auto-improve-trial/state/closeout/generated-artifact-index.json"
                ),
                "artifact_freshness": (
                    "runs/goal-auto-improve-trial/state/closeout/artifact-freshness-report.json"
                ),
            },
        )
        self.assertEqual(
            report["transaction"]["publish_boundary"]["canonical_publish_count"],
            1,
        )
        self.assertIn(
            "generated-artifact-converge",
            report["transaction"]["publish_boundary"]["canonical_publish_targets"],
        )
        self.assertIn(
            "goal-runtime-fixed-point-check",
            report["transaction"]["post_publish_finalization_targets"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_cheap_budget_blocks_stale_full_suite_instead_of_rerunning_it(self) -> None:
        self._seed_evidence_report(
            "ops/reports/test-execution-summary-full.json",
            fingerprint="stale-source-fingerprint",
        )

        report = build_report(
            GoalRuntimeCloseoutRequest(
                vault=self.vault,
                budget="cheap",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "attention")
        self.assertTrue(report["summary"]["full_suite_required"])
        self.assertEqual(report["summary"]["blocked_by_budget_count"], 1)
        self.assertNotIn("test-execution-summary-full-refresh", report["recommended_targets"])
        self.assertNotIn("test-execution-summary-full-current-or-refresh", report["recommended_targets"])
        self.assertEqual(
            report["recommended_targets"],
            [
                "goal-runtime-closeout-candidate-converge",
            ],
        )
        decision = next(item for item in report["phase_decisions"] if item["phase_id"] == "full_suite")
        self.assertEqual(decision["decision"], "blocked_by_budget")
        self.assertEqual(decision["phase_group"], "expensive_evidence")
        publish_decision = next(
            item
            for item in report["phase_decisions"]
            if item["phase_id"] == "publish_goal_runtime_closeout_publish_script_output_surfaces"
        )
        self.assertEqual(publish_decision["decision"], "skip")
        self.assertIn(
            "test-execution-summary-full-current-or-refresh",
            report["transaction"]["forbidden_default_targets"],
        )
        self.assertIn(
            "test-execution-summary-full-refresh",
            report["transaction"]["forbidden_default_targets"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_full_budget_runs_stale_expensive_evidence_at_most_once(self) -> None:
        for rel_path in (
            "ops/reports/release-smoke-report.json",
            "ops/reports/test-execution-summary-full.json",
        ):
            self._seed_evidence_report(rel_path, fingerprint="stale-source-fingerprint")

        report = build_report(
            GoalRuntimeCloseoutRequest(
                vault=self.vault,
                budget="full",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["blocked_by_budget_count"], 0)
        self.assertEqual(
            report["recommended_targets"].count("test-execution-summary-full-current-or-refresh"),
            1,
        )
        self.assertEqual(report["recommended_targets"].count("release-smoke-full-reuse"), 1)
        self.assertLess(
            report["recommended_targets"].index("goal-runtime-closeout-candidate-converge"),
            report["recommended_targets"].index("test-execution-summary-full-current-or-refresh"),
        )
        self.assertLess(
            report["recommended_targets"].index("test-execution-summary-full-current-or-refresh"),
            report["recommended_targets"].index("goal-runtime-closeout-publish"),
        )
        self.assertLess(
            report["recommended_targets"].index("goal-runtime-closeout-publish"),
            report["recommended_targets"].index("goal-runtime-closeout-finalize"),
        )
        self.assertEqual(report["transaction"]["forbidden_default_targets"], [])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_candidate_root_is_recorded_in_transaction_outputs(self) -> None:
        report = build_report(
            GoalRuntimeCloseoutRequest(
                vault=self.vault,
                budget="cheap",
                candidate_root="runs/goal-custom/state/closeout",
                context=fixed_context(),
            )
        )

        self.assertEqual(report["transaction"]["candidate_root"], "runs/goal-custom/state/closeout")
        self.assertEqual(
            report["transaction"]["candidate_outputs"]["artifact_freshness"],
            "runs/goal-custom/state/closeout/artifact-freshness-report.json",
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_report_validates_schema(self) -> None:
        report = build_report(
            GoalRuntimeCloseoutRequest(
                vault=self.vault,
                budget="cheap",
                context=fixed_context(),
            )
        )

        destination = write_report(self.vault, report)

        self.assertEqual(destination.relative_to(self.vault).as_posix(), "tmp/goal-runtime-closeout-plan.json")
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["artifact_kind"], "goal_runtime_closeout_plan")
