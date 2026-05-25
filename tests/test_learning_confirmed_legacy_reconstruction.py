from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.learning_confirmed_legacy_reconstruction import (
    build_report,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-confirmed-legacy-reconstruction.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 9, 9, 0, tzinfo=dt.UTC),
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _seed_confirmed_run(vault: Path, *, include_behavior_delta: bool = True) -> str:
    run_id = "legacy-promote"
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    behavior_delta_rel = f"runs/{run_id}/behavior-delta.json"
    behavior_delta = {
        "artifact_kind": "behavior_delta",
        "run_id": run_id,
        "summary": {"behavior_changed": True, "delta_count": 1, "regression_count": 0},
    }
    if include_behavior_delta:
        _write_json(vault / behavior_delta_rel, behavior_delta)
    _write_json(
        run_dir / "run-telemetry.json",
        {
            "decision": "PROMOTE",
            "behavior_delta": behavior_delta_rel,
            "same_eval_reason_code": "candidate_eval_improved",
        },
    )
    _write_json(
        run_dir / "promotion-report.json",
        {
            "decision": "PROMOTE",
            "run_id": run_id,
            "inputs": {"behavior_delta": behavior_delta_rel},
            "checks": [
                {
                    "id": "equal_score_secondary_eligibility",
                    "status": "PASS",
                    "detail": (
                        "allowed=true, score_equal=true, selected_axes=['candidate_eval'], "
                        "selected_non_regression=true, selected_any_improvement=true"
                    ),
                }
            ],
        },
    )
    return hashlib.sha256(json.dumps(behavior_delta, sort_keys=True).encode("utf-8")).hexdigest()


def _seed_inputs(vault: Path, *, include_behavior_delta: bool = True) -> str:
    (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
    expected_digest = _seed_confirmed_run(vault, include_behavior_delta=include_behavior_delta)
    _write_json(
        vault / "ops" / "reports" / "mutation-proposals.json",
        {
            "proposals": [
                {
                    "family": "contract_regression_signals",
                    "failure_mode": "repeated_discard_runs",
                    "primary_targets": ["ops/scripts/example.py"],
                    "run_ids": ["discard-a"],
                }
            ]
        },
    )
    _write_json(
        vault / "ops" / "reports" / "mechanism-review-candidates.json",
        {
            "candidates": [
                {
                    "family": "contract_regression_signals",
                    "primary_targets": ["ops/scripts/example.py"],
                    "run_ids": ["legacy-promote"],
                }
            ]
        },
    )
    return expected_digest


class LearningConfirmedLegacyReconstructionTests(unittest.TestCase):
    def test_legacy_reconstruction_records_digest_and_secondary_axes_without_mutating_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            expected_digest = _seed_inputs(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)
            row = report["run_reconstructions"][0]
            telemetry = json.loads((vault / "runs" / "legacy-promote" / "run-telemetry.json").read_text())

            self.assertTrue(destination.exists())
            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["summary"]["historical_telemetry_mutation"])
            self.assertEqual(report["summary"]["reconstructed_run_count"], 1)
            self.assertEqual(report["summary"]["operator_summary"], "legacy_reconstruction_runs=1; needed=1; reconstructed=1; blocked=0")
            self.assertEqual(row["reconstruction_status"], "reconstructed")
            self.assertIn("active_same_eval_family", row["selection_reason"])
            self.assertEqual(row["behavior_delta_artifact_sha256"], expected_digest)
            self.assertEqual(row["parsed_secondary_axes"], ["candidate_eval"])
            self.assertEqual(
                row["parsed_secondary_axis_evidence"]["source"],
                "promotion_report_check_detail",
            )
            operator_diagnostic = report["summary"]["operator_reconstruction_diagnostics"][0]
            self.assertEqual(operator_diagnostic["run_id"], "legacy-promote")
            self.assertTrue(operator_diagnostic["reconstruction_needed"])
            self.assertEqual(operator_diagnostic["parsed_secondary_axes"], ["candidate_eval"])
            self.assertIn("selected_axes=['candidate_eval']", operator_diagnostic["parsed_secondary_axis_evidence"]["detail"])
            self.assertNotIn("behavior_delta_digest", telemetry)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_legacy_reconstruction_blocks_when_required_behavior_delta_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            _seed_inputs(vault, include_behavior_delta=False)

            report = build_report(vault, context=fixed_context())
            row = report["run_reconstructions"][0]

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["blocked_run_count"], 1)
            self.assertEqual(row["reconstruction_status"], "blocked")
            self.assertIn("behavior-delta artifact digest unavailable", row["reasons"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
