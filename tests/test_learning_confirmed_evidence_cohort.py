from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.learning_claim_evidence_bundle import build_report as build_bundle
from ops.scripts.learning_claim_evidence_bundle import write_report as write_bundle
from ops.scripts.learning_confirmed_evidence_cohort import (
    build_report,
    validate_learning_confirmed_evidence_cohort,
    write_report,
)
from ops.scripts.learning_confirmed_legacy_reconstruction import build_report as build_legacy_reconstruction
from ops.scripts.learning_confirmed_legacy_reconstruction import write_report as write_legacy_reconstruction
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-confirmed-evidence-cohort.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 8, 9, 0, tzinfo=dt.timezone.utc),
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_run(
    vault: Path,
    run_id: str,
    *,
    decision: str = "PROMOTE",
    digest_only: bool = False,
    omit_telemetry_digest: bool = False,
    omit_telemetry_secondary: bool = False,
    omit_baseline_assessment: bool = False,
    omit_candidate_assessment: bool = False,
    omit_promotion_report: bool = False,
) -> None:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    behavior_delta_rel = f"runs/{run_id}/behavior-delta.json"
    behavior_delta = (
        {"artifact_kind": "behavior_delta", "run_id": run_id}
        if digest_only
        else {
            "artifact_kind": "behavior_delta",
            "run_id": run_id,
            "summary": {
                "behavior_changed": True,
                "delta_count": 1,
                "regression_count": 0,
            },
            "deltas": [
                {
                    "id": f"{run_id}-delta",
                    "target": "ops/scripts/example.py",
                    "before": "baseline",
                    "after": "candidate",
                    "coverage_status": "covered",
                }
            ],
        }
    )
    encoded = json.dumps(behavior_delta, sort_keys=True)
    _write_json(vault / behavior_delta_rel, behavior_delta)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    telemetry = {
        "decision": decision,
        "behavior_delta": behavior_delta_rel,
        "same_eval_reason_code": "candidate_eval_improved",
    }
    if not omit_telemetry_secondary:
        telemetry["strict_secondary_improvement_present"] = True
        telemetry["secondary_improvement_axes"] = ["candidate_eval"]
    if not omit_telemetry_digest:
        telemetry["behavior_delta_digest"] = digest
    _write_json(run_dir / "run-telemetry.json", telemetry)
    if not omit_baseline_assessment:
        _write_json(
            run_dir / "baseline-mechanism-assessment.json",
            {"artifact_kind": "baseline_mechanism_assessment", "run_id": run_id, "score": 1},
        )
    if not omit_candidate_assessment:
        _write_json(
            run_dir / "candidate-mechanism-assessment.json",
            {"artifact_kind": "candidate_mechanism_assessment", "run_id": run_id, "score": 2},
        )
    if not omit_promotion_report:
        _write_json(
            run_dir / "promotion-report.json",
            {
                "decision": decision,
                "run_id": run_id,
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
                "inputs": {"behavior_delta": behavior_delta_rel},
            },
        )


def seed_inputs(
    vault: Path,
    *,
    proposal_run_ids: list[list[str]],
    proposal_failure_modes: list[str] | None = None,
    digest_only: bool = False,
) -> None:
    (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
    (vault / "external-reports").mkdir(parents=True, exist_ok=True)
    _write_json(
        vault / "ops" / "reports" / "auto-improve-readiness.json",
        {"learning_readiness": {"status": "learning_likely"}},
    )
    _write_json(vault / "ops" / "reports" / "outcome-metrics.json", {})
    _write_json(vault / "ops" / "reports" / "public-check-summary.json", {"status": "pass"})
    _write_json(vault / "external-reports" / "report-reference-manifest.json", {"status": "pass"})
    failure_modes = proposal_failure_modes or ["repeated_same_eval_or_discard"] * len(proposal_run_ids)
    proposals = [
        {
            "family": failure_modes[index],
            "failure_mode": failure_modes[index],
            "primary_targets": ["ops/scripts/example.py"],
            "supporting_targets": [],
            "run_ids": run_ids,
        }
        for index, run_ids in enumerate(proposal_run_ids)
    ]
    _write_json(vault / "ops" / "reports" / "mutation-proposals.json", {"proposals": proposals})
    _write_json(
        vault / "ops" / "reports" / "mechanism-review-candidates.json",
        {
            "candidates": [
                {
                    "family": failure_modes[index],
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "run_ids": run_ids,
                }
                for index, run_ids in enumerate(proposal_run_ids)
            ]
        },
    )
    for run_id in sorted({run_id for run_ids in proposal_run_ids for run_id in run_ids}):
        _write_run(vault, run_id, digest_only=digest_only)
    write_legacy_reconstruction(vault, build_legacy_reconstruction(vault, context=fixed_context()))
    write_bundle(vault, build_bundle(vault, context=fixed_context()))


class LearningConfirmedEvidenceCohortTests(unittest.TestCase):
    def test_same_family_three_before_after_runs_auto_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_inputs(vault, proposal_run_ids=[["run-a", "run-b", "run-c"]])

            report = build_report(vault, context=fixed_context())
            write_report(vault, report)
            validation = validate_learning_confirmed_evidence_cohort(vault, context=fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["confirmed_evidence_status"], "auto_confirmed")
            self.assertTrue(report["summary"]["confirmed_learning_improvement_allowed"])
            self.assertEqual(report["summary"]["eligible_family_count"], 1)
            self.assertEqual(report["summary"]["valid_run_count"], 3)
            self.assertEqual(report["summary"]["selected_valid_run_ids"], ["run-a", "run-b", "run-c"])
            self.assertEqual(report["summary"]["eligible_family_ids"], ["repeated_same_eval_or_discard"])
            self.assertEqual(report["summary"]["max_valid_run_count"], 3)
            self.assertEqual(report["summary"]["rejected_run_count"], 0)
            self.assertEqual(report["summary"]["rejected_run_diagnostics"], [])
            self.assertEqual(validation["revocation_status"], "active")
            self.assertTrue(validation["confirmed_learning_improvement_allowed"])
            self.assertEqual(
                validation["confirmed_evidence_summary"]["selected_valid_run_ids"],
                ["run-a", "run-b", "run-c"],
            )
            first_run = {item["run_id"]: item for item in report["run_evidence"]}["run-a"]
            self.assertEqual(first_run["confirmed_run_artifact_binding_status"], "pass")
            artifact_ids = {item["id"] for item in first_run["confirmed_run_artifacts"]}
            self.assertEqual(
                artifact_ids,
                {"baseline_mechanism_assessment", "candidate_mechanism_assessment", "promotion_report"},
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_mechanism_review_history_can_auto_confirm_with_legacy_artifact_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "external-reports").mkdir(parents=True, exist_ok=True)
            _write_json(
                vault / "ops" / "reports" / "auto-improve-readiness.json",
                {"learning_readiness": {"status": "learning_likely"}},
            )
            _write_json(vault / "ops" / "reports" / "outcome-metrics.json", {})
            _write_json(vault / "ops" / "reports" / "public-check-summary.json", {"status": "pass"})
            _write_json(vault / "external-reports" / "report-reference-manifest.json", {"status": "pass"})
            _write_json(
                vault / "ops" / "reports" / "mutation-proposals.json",
                {
                    "proposals": [
                        {
                            "family": "contract_regression_signals",
                            "failure_mode": "repeated_discard_runs",
                            "primary_targets": [
                                "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                            ],
                            "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                            "run_ids": ["discard-a", "discard-b"],
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
                            "primary_targets": [
                                "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
                            ],
                            "supporting_targets": ["ops/schemas/run-telemetry.schema.json"],
                            "run_ids": ["promote-a", "promote-b", "legacy-promote"],
                        }
                    ]
                },
            )
            _write_run(vault, "discard-a", decision="DISCARD")
            _write_run(vault, "discard-b", decision="DISCARD")
            _write_run(vault, "promote-a")
            _write_run(vault, "promote-b")
            _write_run(
                vault,
                "legacy-promote",
                omit_telemetry_digest=True,
                omit_telemetry_secondary=True,
            )
            write_legacy_reconstruction(vault, build_legacy_reconstruction(vault, context=fixed_context()))
            write_bundle(vault, build_bundle(vault, context=fixed_context()))

            report = build_report(vault, context=fixed_context())
            legacy = {item["run_id"]: item for item in report["run_evidence"]}["legacy-promote"]

            self.assertEqual(report["summary"]["confirmed_evidence_status"], "auto_confirmed")
            self.assertEqual(report["summary"]["valid_run_count"], 3)
            self.assertEqual(report["summary"]["legacy_reconstruction_summary"]["status"], "pass")
            self.assertEqual(
                report["summary"]["legacy_reconstruction_summary"]["reconstructed_run_count"],
                1,
            )
            self.assertEqual(legacy["behavior_delta_digest_source"], "legacy_reconstruction_artifact")
            self.assertEqual(legacy["legacy_reconstruction_status"], "reconstructed")
            self.assertIn("active_same_eval_family", legacy["legacy_reconstruction_selection_reason"])
            self.assertEqual(legacy["secondary_axis_evidence_source"], "legacy_reconstruction_artifact")
            self.assertIn("selected_axes=", legacy["secondary_axis_evidence_detail"])
            self.assertEqual(legacy["families"], ["contract_regression_signals"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_digest_only_three_runs_do_not_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_inputs(vault, proposal_run_ids=[["run-a", "run-b", "run-c"]], digest_only=True)

            report = build_report(vault, context=fixed_context())
            predicates = {item["id"]: item for item in report["predicate_results"]}

            self.assertEqual(report["summary"]["confirmed_evidence_status"], "not_ready")
            self.assertFalse(report["summary"]["confirmed_learning_improvement_allowed"])
            self.assertEqual(report["summary"]["valid_run_count"], 0)
            self.assertEqual(predicates["repeated_same_family_evidence"]["status"], "fail")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_missing_confirmed_run_assessment_rejects_that_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_inputs(vault, proposal_run_ids=[["run-a", "run-b", "run-c"]])
            (vault / "runs" / "run-c" / "baseline-mechanism-assessment.json").unlink()
            write_bundle(vault, build_bundle(vault, context=fixed_context()))

            report = build_report(vault, context=fixed_context())
            run_c = {item["run_id"]: item for item in report["run_evidence"]}["run-c"]

            self.assertEqual(report["summary"]["confirmed_evidence_status"], "not_ready")
            self.assertEqual(report["summary"]["valid_run_count"], 2)
            self.assertEqual(run_c["status"], "fail")
            self.assertEqual(run_c["confirmed_run_artifact_binding_status"], "missing_required_artifact")
            self.assertIn("baseline_mechanism_assessment", run_c["confirmed_run_artifact_missing_ids"])
            self.assertIn("confirmed run artifact missing: baseline_mechanism_assessment", run_c["reasons"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_three_runs_split_across_families_do_not_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_inputs(
                vault,
                proposal_run_ids=[["run-a", "run-b"], ["run-c"]],
                proposal_failure_modes=["repeated_same_eval_or_discard", "repeated_discard_runs"],
            )

            report = build_report(vault, context=fixed_context())
            predicates = {item["id"]: item for item in report["predicate_results"]}

            self.assertEqual(report["summary"]["confirmed_evidence_status"], "not_ready")
            self.assertFalse(report["summary"]["confirmed_learning_improvement_allowed"])
            self.assertEqual(report["summary"]["family_count"], 2)
            self.assertEqual(report["summary"]["valid_run_count"], 3)
            self.assertEqual(predicates["repeated_same_family_evidence"]["status"], "fail")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
