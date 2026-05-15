from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ops.scripts.learning_claim_evidence_bundle import (
    build_report as build_evidence_bundle,
    write_report as write_evidence_bundle,
)
from ops.scripts.learning_claim_model import ImprovementClaimInputs, improvement_claim_model
from ops.scripts.learning_claim_unlock_review import build_report as build_unlock_review
from ops.scripts.learning_confirmed_evidence_cohort import build_report as build_confirmed_cohort
from ops.scripts.learning_confirmed_evidence_cohort import write_report as write_confirmed_cohort
from ops.scripts.learning_confirmed_legacy_reconstruction import build_report as build_legacy_reconstruction
from ops.scripts.learning_confirmed_legacy_reconstruction import write_report as write_legacy_reconstruction
from ops.scripts.learning_delta_scoreboard import build_report, write_report
from ops.scripts.learning_delta_scoreboard_constants import SCOREBOARD_SOURCE_PATHS
from ops.scripts.learning_readiness_vocabulary import LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-delta-scoreboard.schema.json"
UNLOCK_REVIEW_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "learning-claim-unlock-review.schema.json"
AUTO_UNLOCK_POLICY_PATH = "ops/policies/learning-claim-auto-unlock.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 5, 9, 0, tzinfo=dt.timezone.utc),
    )


def write_unlock_review(
    vault: Path,
    *,
    approved: bool,
    blocking_signal_ids: list[str] | None = None,
    review_status: str | None = None,
) -> dict[str, Any]:
    report = build_unlock_review(
        vault,
        approved_by="operator" if approved else "",
        reviewed_at="2026-05-05T09:00:00Z" if approved else "",
        context=fixed_context(),
    )
    report["review_status"] = review_status or ("approved" if approved else "required")
    report["approved"] = approved
    report["blocking_signal_ids"] = blocking_signal_ids or []
    if approved:
        for item in report["review_items"]:
            item["status"] = "pass"
        report["required_followup"] = []
    path = vault / "ops" / "reports" / "learning-claim-unlock-review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return report


def write_machine_evidence_bundle(vault: Path) -> dict[str, Any]:
    write_legacy_reconstruction(vault, build_legacy_reconstruction(vault, context=fixed_context()))
    report = build_evidence_bundle(vault, context=fixed_context())
    write_evidence_bundle(vault, report)
    write_confirmed_cohort(vault, build_confirmed_cohort(vault, context=fixed_context()))
    return report


def write_external_manifest(vault: Path) -> None:
    (vault / "external-reports").mkdir(parents=True, exist_ok=True)
    (vault / "external-reports" / "report-reference-manifest.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )


def write_machine_bundle_inputs(vault: Path, run_ids: tuple[str, ...] = ("run-a", "run-b")) -> None:
    (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "reports" / "outcome-metrics.json").write_text("{}", encoding="utf-8")
    (vault / "ops" / "reports" / "public-check-summary.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )
    (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
        json.dumps(
            {
                "proposals": [
                    {
                        "family": "contract_regression_signals",
                        "failure_mode": "repeated_same_eval_or_discard",
                        "primary_targets": [
                            "ops/scripts/mechanism/mutation_proposal_runtime.py"
                        ],
                        "supporting_targets": [],
                        "run_ids": list(run_ids),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (vault / "ops" / "reports" / "mechanism-review-candidates.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "family": "contract_regression_signals",
                        "primary_targets": [
                            "ops/scripts/mechanism/mutation_proposal_runtime.py"
                        ],
                        "supporting_targets": [],
                        "run_ids": list(run_ids),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for index, run_id in enumerate(run_ids):
        (vault / "runs" / run_id).mkdir(parents=True, exist_ok=True)
        behavior_delta_rel = f"runs/{run_id}/behavior-delta.json"
        behavior_delta_payload = json.dumps(
            {
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
                        "target": "ops/scripts/mechanism/mutation_proposal_runtime.py",
                        "before": f"baseline-{index}",
                        "after": f"candidate-{index}",
                        "coverage_status": "covered",
                    }
                ],
            },
            sort_keys=True,
        )
        (vault / behavior_delta_rel).write_text(behavior_delta_payload, encoding="utf-8")
        behavior_delta_digest = hashlib.sha256(behavior_delta_payload.encode("utf-8")).hexdigest()
        (vault / "runs" / run_id / "baseline-mechanism-assessment.json").write_text(
            json.dumps({"artifact_kind": "baseline_mechanism_assessment", "run_id": run_id, "score": index}),
            encoding="utf-8",
        )
        (vault / "runs" / run_id / "candidate-mechanism-assessment.json").write_text(
            json.dumps({"artifact_kind": "candidate_mechanism_assessment", "run_id": run_id, "score": index + 1}),
            encoding="utf-8",
        )
        (vault / "runs" / run_id / "promotion-report.json").write_text(
            json.dumps(
                {
                    "decision": "PROMOTE",
                    "run_id": run_id,
                    "checks": [
                        {
                            "id": "equal_score_secondary_eligibility",
                            "status": "PASS",
                            "detail": (
                                "allowed=true, score_equal=true, selected_axes=['complexity'], "
                                "selected_non_regression=true, selected_any_improvement=true"
                            ),
                        }
                    ],
                    "inputs": {"behavior_delta": behavior_delta_rel},
                }
            ),
            encoding="utf-8",
        )
        (vault / "runs" / run_id / "run-telemetry.json").write_text(
            json.dumps(
                {
                    "decision": "PROMOTE",
                    "behavior_delta": behavior_delta_rel,
                    "same_eval_reason_code": "telemetry_discoverability_improved",
                    "strict_secondary_improvement_present": True,
                    "secondary_improvement_axes": ["complexity"],
                    "behavior_delta_digest": behavior_delta_digest,
                }
            ),
            encoding="utf-8",
        )
    write_external_manifest(vault)


def machine_claimable_readiness() -> dict[str, Any]:
    return {
        "generated_at": "2026-05-05T09:00:00Z",
        "source_tree_fingerprint": "a" * 64,
        "input_fingerprints": {"mutation_proposal_report": "b" * 64},
        "can_execute_trial": True,
        "can_promote_result": True,
        "queue": {
            "ready": True,
            "runnable_proposal_count": 1,
        },
        "learning_readiness": {
            "status": "learning_likely",
            "can_run": True,
            "likely_to_learn": True,
            "signals": [],
            "metrics": {
                "same_eval_run_count": 2,
                "same_eval_reason_code_coverage_ratio": 1.0,
                "strict_secondary_improvement_coverage_ratio": 1.0,
                "behavior_delta_digest_coverage_ratio": 1.0,
                "rework_count": 0,
                "defect_escape_pair_count": 0,
            },
        },
        "release_blockers": [],
    }


class LearningDeltaScoreboardTests(unittest.TestCase):
    def test_source_paths_track_decomposed_scoreboard_modules(self) -> None:
        self.assertEqual(
            SCOREBOARD_SOURCE_PATHS,
            [
                "ops/scripts/learning/learning_delta_scoreboard.py",
                "ops/scripts/learning/learning_delta_scoreboard_constants.py",
                "ops/scripts/learning/learning_delta_scoreboard_unlock_runtime.py",
                "ops/scripts/learning/learning_delta_scoreboard_anti_slop_runtime.py",
                "ops/scripts/mechanism/auto_improve_iteration_telemetry_runtime.py",
            ],
        )
        for rel_path in SCOREBOARD_SOURCE_PATHS:
            self.assertTrue((REPO_ROOT / rel_path).is_file(), rel_path)

    def test_claim_model_keeps_regression_safe_separate_from_learning_proof(self) -> None:
        model = improvement_claim_model(
            ImprovementClaimInputs(
                guard_status="pass",
                claims_learning_improved=False,
                learning_claim_evidence_complete=False,
                bounded_learning_claim_allowed=False,
                confirmed_learning_improvement_allowed=False,
                improvement_claim_status="not_ready",
                evidence_cohort_status="not_ready",
                claim_level="none",
                bundle_status="not_evaluated",
                blocking_predicate_ids=[],
                same_eval_run_count=0,
                same_eval_reason_coverage_status="no_evidence",
                strict_secondary_improvement_coverage_status="no_evidence",
                behavior_delta_digest_coverage_status="no_evidence",
            )
        )
        stages = {item["stage"]: item["status"] for item in model["stages"]}

        self.assertEqual(stages["regression_safe"], "pass")
        self.assertEqual(stages["same_eval_gain"], "not_claimed")
        self.assertEqual(stages["production_learning"], "blocked")
        self.assertEqual(model["highest_supported_stage"], "regression_safe")
        self.assertEqual(model["learning_claim_blocker_status"], "clear")
        self.assertFalse(model["claim_wording_allowed"])

    def test_claim_model_allows_production_wording_only_after_confirmed_evidence_aligns(self) -> None:
        model = improvement_claim_model(
            ImprovementClaimInputs(
                guard_status="pass",
                claims_learning_improved=True,
                learning_claim_evidence_complete=True,
                bounded_learning_claim_allowed=True,
                confirmed_learning_improvement_allowed=True,
                improvement_claim_status="auto_confirmed",
                evidence_cohort_status="auto_confirmed",
                claim_level="confirmed_learning_improvement",
                bundle_status="active",
                blocking_predicate_ids=[],
                same_eval_run_count=2,
                same_eval_reason_coverage_status="complete",
                strict_secondary_improvement_coverage_status="complete",
                behavior_delta_digest_coverage_status="complete",
            )
        )
        stages = {item["stage"]: item["status"] for item in model["stages"]}

        self.assertEqual(stages["regression_safe"], "pass")
        self.assertEqual(stages["same_eval_gain"], "pass")
        self.assertEqual(stages["persistence"], "pass")
        self.assertEqual(stages["production_learning"], "pass")
        self.assertEqual(model["highest_supported_stage"], "production_learning")
        self.assertEqual(model["learning_claim_blocker_status"], "clear")
        self.assertTrue(model["claim_wording_allowed"])

    def test_claim_model_blocks_persistence_and_wording_when_predicates_block(self) -> None:
        model = improvement_claim_model(
            ImprovementClaimInputs(
                guard_status="pass",
                claims_learning_improved=True,
                learning_claim_evidence_complete=True,
                bounded_learning_claim_allowed=True,
                confirmed_learning_improvement_allowed=True,
                improvement_claim_status="auto_confirmed",
                evidence_cohort_status="auto_confirmed",
                claim_level="confirmed_learning_improvement",
                bundle_status="active",
                blocking_predicate_ids=["same_family_persistence_missing"],
                same_eval_run_count=2,
                same_eval_reason_coverage_status="complete",
                strict_secondary_improvement_coverage_status="complete",
                behavior_delta_digest_coverage_status="complete",
            )
        )
        stages = {item["stage"]: item["status"] for item in model["stages"]}

        self.assertEqual(stages["same_eval_gain"], "pass")
        self.assertEqual(stages["persistence"], "blocked")
        self.assertEqual(stages["production_learning"], "blocked")
        self.assertEqual(model["highest_supported_stage"], "same_eval_gain")
        self.assertEqual(model["learning_claim_blocker_status"], "blocked")
        self.assertFalse(model["claim_wording_allowed"])

    def test_unlock_review_records_machine_readable_approval_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps({"learning_readiness": {"signals": []}}),
                encoding="utf-8",
            )

            report = build_unlock_review(vault, context=fixed_context())
            review_items = {item["id"]: item for item in report["review_items"]}

            self.assertFalse(report["approved"])
            self.assertEqual(
                review_items["release_evidence_dashboard"]["required_condition"],
                "release_evidence_dashboard.reviewed_by_operator == true",
            )
            self.assertEqual(review_items["release_evidence_dashboard"]["observed_value"], "reviewed=false")
            self.assertTrue(review_items["release_evidence_dashboard"]["requires_human_review"])
            self.assertEqual(review_items["auto_improve_readiness"]["status"], "pass")
            self.assertEqual(
                review_items["auto_improve_readiness"]["required_condition"],
                "auto_improve_readiness.learning_readiness.signals == [] "
                "and auto_improve_readiness.release_blockers == []",
            )
            self.assertEqual(
                review_items["auto_improve_readiness"]["observed_value"],
                "learning_readiness.signals=[]; release_blockers=[]",
            )
            self.assertFalse(review_items["auto_improve_readiness"]["requires_human_review"])
            self.assertEqual(
                review_items["strict_secondary_axes"]["required_condition"],
                "strict_secondary_axes.reviewed_by_operator == true",
            )
            self.assertEqual(
                review_items["behavior_delta_provenance"]["required_condition"],
                "behavior_delta_digest_provenance.reviewed_by_operator == true",
            )
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_unlock_review_auto_approves_machine_policy_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(machine_claimable_readiness()),
                encoding="utf-8",
            )
            write_machine_bundle_inputs(vault)
            write_machine_evidence_bundle(vault)

            report = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )

            self.assertTrue(report["approved"])
            self.assertEqual(report["review_status"], "auto_approved")
            self.assertEqual(report["approval_mode"], "machine_policy")
            self.assertEqual(report["reviewed_by"], "")
            self.assertEqual(report["reviewed_at"], "")
            self.assertEqual(report["machine_policy_decision"]["decision"], "auto_approved")
            self.assertEqual(report["machine_policy_decision"]["revocation_status"], "active")
            self.assertEqual(report["machine_policy_decision"]["bundle_fingerprint_match_status"], "match")
            self.assertEqual(report["machine_policy_decision"]["claim_level"], "bounded_learning_likely")
            self.assertEqual(report["machine_policy_decision"]["learning_claim_blocker_status"], "blocked")
            self.assertTrue(report["machine_policy_decision"]["bounded_learning_claim_allowed"])
            self.assertFalse(report["machine_policy_decision"]["confirmed_learning_improvement_allowed"])
            self.assertRegex(report["machine_policy_decision"]["evidence_bundle_digest"], r"^[a-f0-9]{64}$")
            self.assertTrue(
                all(item["status"] == "pass" for item in report["machine_policy_decision"]["predicate_results"])
            )
            self.assertTrue(all(item["status"] == "pass" for item in report["review_items"]))
            self.assertTrue(all(not item["requires_human_review"] for item in report["review_items"]))
            self.assertEqual(report["required_followup"], [])
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_unlock_review_auto_policy_requires_human_when_coverage_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            readiness = machine_claimable_readiness()
            readiness["learning_readiness"]["metrics"]["behavior_delta_digest_coverage_ratio"] = 0.5
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )
            write_machine_bundle_inputs(vault)
            write_machine_evidence_bundle(vault)

            report = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )
            predicates = {item["id"]: item for item in report["machine_policy_decision"]["predicate_results"]}

            self.assertFalse(report["approved"])
            self.assertEqual(report["review_status"], "required")
            self.assertEqual(report["approval_mode"], "none")
            self.assertEqual(report["machine_policy_decision"]["decision"], "requires_human")
            self.assertEqual(predicates["behavior_delta_digest_coverage_full"]["status"], "fail")
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_unlock_review_confirmed_lane_opens_with_strict_no_human_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            readiness = machine_claimable_readiness()
            readiness["learning_readiness"]["metrics"]["same_eval_run_count"] = 3
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )
            write_machine_bundle_inputs(vault, run_ids=("run-a", "run-b", "run-c"))
            (vault / "ops" / "reports" / "test-execution-summary-full.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "public-check-summary.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "learning-readiness-signoff-revalidation.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "release-clean-blocker-ledger.json").write_text(
                json.dumps({"learning_claim_blockers": []}),
                encoding="utf-8",
            )
            write_machine_evidence_bundle(vault)

            report = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )

            self.assertEqual(report["machine_policy_decision"]["decision"], "auto_approved")
            self.assertEqual(
                report["machine_policy_decision"]["confirmed_learning_improvement_status"],
                "auto_confirmed",
            )
            self.assertTrue(report["machine_policy_decision"]["confirmed_learning_improvement_allowed"])
            self.assertEqual(report["machine_policy_decision"]["claim_level"], "confirmed_learning_improvement")
            self.assertEqual(report["machine_policy_decision"]["learning_claim_blocker_status"], "clear")
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_unlock_review_refuses_approval_when_readiness_pressure_remains(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps({"learning_readiness": {"signals": [{"id": "high_rework"}]}}),
                encoding="utf-8",
            )

            report = build_unlock_review(
                vault,
                approved_by="operator",
                reviewed_at="2026-05-05T09:00:00Z",
                context=fixed_context(),
            )
            review_items = {item["id"]: item for item in report["review_items"]}

            self.assertEqual(report["review_status"], "required")
            self.assertFalse(report["approved"])
            self.assertEqual(report["blocking_signal_ids"], ["high_rework"])
            self.assertEqual(report["blocking_blocker_ids"], [])
            self.assertEqual(review_items["release_evidence_dashboard"]["status"], "pass")
            self.assertEqual(review_items["auto_improve_readiness"]["status"], "fail")
            self.assertEqual(
                review_items["auto_improve_readiness"]["observed_value"],
                "learning_readiness.signals=high_rework; release_blockers=<none>",
            )
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_unlock_review_refuses_approval_when_learning_not_runnable_blocker_remains(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "learning_readiness": {
                            "status": "not_runnable",
                            "signals": [],
                        },
                        "release_blockers": [
                            {
                                "id": LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID,
                                "status": "open",
                                "release_blocker": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = build_unlock_review(
                vault,
                approved_by="operator",
                reviewed_at="2026-05-05T09:00:00Z",
                context=fixed_context(),
            )
            review_items = {item["id"]: item for item in report["review_items"]}

            self.assertEqual(report["review_status"], "required")
            self.assertFalse(report["approved"])
            self.assertEqual(report["blocking_signal_ids"], [])
            self.assertEqual(report["blocking_blocker_ids"], [LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID])
            self.assertEqual(review_items["release_evidence_dashboard"]["status"], "pass")
            self.assertEqual(review_items["auto_improve_readiness"]["status"], "fail")
            self.assertEqual(
                review_items["auto_improve_readiness"]["observed_value"],
                f"learning_readiness.signals=<none>; release_blockers={LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID}",
            )
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_scoreboard_blocks_learning_claim_without_same_eval_reason_and_digest_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "can_promote_result": True,
                        "learning_readiness": {"likely_to_learn": True},
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "outcome-metrics.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "failure_mode": "repeated_same_eval_or_discard",
                                "run_ids": ["run-a", "run-b"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-a").mkdir(parents=True)
            (vault / "runs" / "run-a" / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "same_eval_reason": "lint improved",
                        "same_eval_reason_code": "telemetry_discoverability_improved",
                        "strict_secondary_improvement_present": True,
                        "secondary_improvement_axes": ["lint"],
                        "behavior_delta_digest": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text(
                "| stale | {ref_current.get('sha256')} |\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["learning_claim_guard"]["status"], "blocked")
            self.assertEqual(report["summary"]["telemetry_coverage_ratio"], 0.5)
            self.assertFalse(report["summary"]["learning_claim_evidence_complete"])
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "not_ready")
            self.assertFalse(report["summary"]["learning_claim_unlock_review_approved"])
            self.assertEqual(report["summary"]["same_eval_reason_coverage_ratio"], 0.5)
            self.assertEqual(report["summary"]["same_eval_reason_coverage_status"], "partial")
            self.assertEqual(report["summary"]["strict_secondary_improvement_coverage_ratio"], 0.5)
            self.assertEqual(report["summary"]["behavior_delta_digest_coverage_ratio"], 0.5)
            self.assertEqual(report["coverage"]["same_eval_reason_code"]["status"], "partial")
            self.assertEqual(
                report["aggregate_selector"]["effective_learning_coverage"]["selected_source"],
                "proposal_family_coverage",
            )
            self.assertEqual(report["external_report_placeholder_audit"]["placeholder_count"], 1)
            self.assertEqual(report["anti_slop_score"]["status"], "blocked")
            self.assertEqual(report["anti_slop_score"]["score"], 20)
            self.assertEqual(report["summary"]["anti_slop_status"], "blocked")
            self.assertEqual(report["summary"]["anti_slop_score"], 20)
            self.assertEqual(
                [item["id"] for item in report["anti_slop_score"]["deductions"]],
                [
                    "external_report_placeholders",
                    "learning_claim_evidence_coverage_not_full",
                    "unsupported_learning_claim",
                    "claim_wording_not_allowed",
                ],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
            destination = write_report(vault, report)
            self.assertTrue(destination.exists())

    def test_scoreboard_passes_when_no_learning_claim_and_reports_are_placeholder_free(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "can_promote_result": False,
                        "learning_readiness": {"likely_to_learn": False},
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "outcome-metrics.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps({"proposals": []}),
                encoding="utf-8",
            )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["learning_claim_guard"]["status"], "pass")
            self.assertEqual(report["anti_slop_score"]["status"], "clean")
            self.assertEqual(report["anti_slop_score"]["score"], 100)
            self.assertEqual(report["anti_slop_score"]["deductions"], [])
            self.assertEqual(report["summary"]["anti_slop_status"], "clean")
            self.assertFalse(report["summary"]["learning_claim_allowed"])
            self.assertEqual(report["summary"]["telemetry_coverage_status"], "not_applicable")
            self.assertEqual(report["coverage"]["same_eval_reason_code"]["status"], "not_applicable")
            self.assertEqual(report["external_report_placeholder_audit"]["status"], "pass")
            self.assertFalse(report["summary"]["learning_claim_evidence_complete"])
            self.assertEqual(report["learning_claim_unlock_review"]["status"], "not_ready")
            evidence_paths = {item["path"] for item in report["evidence_scopes"]}
            self.assertNotIn("ops/reports/release-closeout-batch-manifest.json", evidence_paths)
            self.assertNotIn("ops/operator/operator-release-summary.json", evidence_paths)
            self.assertNotIn(
                "ops/reports/routing-provenance-aggregates/auto-improve-2026-05-02t03-27-31z.json",
                evidence_paths,
            )

    def test_scoreboard_marks_no_evidence_when_learning_claim_has_no_same_eval_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "can_promote_result": True,
                        "learning_readiness": {"likely_to_learn": True},
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps({"proposals": []}),
                encoding="utf-8",
            )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["learning_claim_guard"]["status"], "blocked")
            self.assertEqual(report["summary"]["telemetry_coverage_status"], "no_evidence")
            self.assertEqual(report["summary"]["same_eval_reason_coverage_status"], "no_evidence")
            self.assertEqual(report["coverage"]["strict_secondary_improvement"]["status"], "no_evidence")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_scoreboard_keeps_learning_claim_closed_after_full_coverage_until_unlock_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "can_promote_result": True,
                        "learning_readiness": {"likely_to_learn": True},
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "family": "contract_regression_signals",
                                "failure_mode": "repeated_same_eval_or_discard",
                                "primary_targets": [
                                    "ops/scripts/mechanism/mutation_proposal_runtime.py"
                                ],
                                "supporting_targets": [],
                                "run_ids": ["run-a"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mechanism-review-candidates.json").write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "family": "contract_regression_signals",
                                "primary_targets": [
                                    "ops/scripts/mechanism/mutation_proposal_runtime.py"
                                ],
                                "supporting_targets": [],
                                "run_ids": ["run-a"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-a").mkdir(parents=True)
            (vault / "runs" / "run-a" / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "same_eval_reason_code": "telemetry_discoverability_improved",
                        "strict_secondary_improvement_present": True,
                        "secondary_improvement_axes": ["complexity"],
                        "behavior_delta_digest": "b" * 64,
                    }
                ),
                encoding="utf-8",
            )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["learning_claim_guard"]["status"], "blocked")
            self.assertFalse(report["summary"]["learning_claim_allowed"])
            self.assertTrue(report["summary"]["learning_claim_evidence_complete"])
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "required")
            self.assertFalse(report["summary"]["learning_claim_unlock_review_approved"])
            self.assertEqual(report["learning_claim_unlock_review"]["status"], "required")
            self.assertIn(
                "learning_claim_unlock_review.status in [approved, auto_approved]",
                report["learning_claim_guard"]["required_conditions"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_scoreboard_allows_learning_claim_after_approved_unlock_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "can_promote_result": True,
                        "learning_readiness": {
                            "likely_to_learn": True,
                            "signals": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "failure_mode": "repeated_same_eval_or_discard",
                                "run_ids": ["run-a"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-a").mkdir(parents=True)
            (vault / "runs" / "run-a" / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "same_eval_reason_code": "telemetry_discoverability_improved",
                        "strict_secondary_improvement_present": True,
                        "secondary_improvement_axes": ["complexity"],
                        "behavior_delta_digest": "c" * 64,
                    }
                ),
                encoding="utf-8",
            )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")
            unlock_review = write_unlock_review(vault, approved=True)

            report = build_report(vault, context=fixed_context())

            self.assertEqual(validate_with_schema(unlock_review, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["learning_claim_guard"]["status"], "pass")
            self.assertTrue(report["summary"]["learning_claim_allowed"])
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "approved")
            self.assertTrue(report["summary"]["learning_claim_unlock_review_approved"])
            self.assertEqual(
                report["learning_claim_unlock_review"]["source_path"],
                "ops/reports/learning-claim-unlock-review.json",
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_scoreboard_allows_learning_claim_after_machine_policy_unlock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(machine_claimable_readiness()),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "family": "contract_regression_signals",
                                "failure_mode": "repeated_same_eval_or_discard",
                                "primary_targets": [
                                    "ops/scripts/mechanism/mutation_proposal_runtime.py"
                                ],
                                "supporting_targets": [],
                                "run_ids": ["run-a", "run-b"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mechanism-review-candidates.json").write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "family": "contract_regression_signals",
                                "primary_targets": [
                                    "ops/scripts/mechanism/mutation_proposal_runtime.py"
                                ],
                                "supporting_targets": [],
                                "run_ids": ["run-a", "run-b"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            for run_id, digest_char in (("run-a", "e"), ("run-b", "f")):
                (vault / "runs" / run_id).mkdir(parents=True)
                (vault / "runs" / run_id / "run-telemetry.json").write_text(
                    json.dumps(
                        {
                            "decision": "PROMOTE",
                            "same_eval_reason_code": "telemetry_discoverability_improved",
                            "strict_secondary_improvement_present": True,
                            "secondary_improvement_axes": ["complexity"],
                            "behavior_delta_digest": digest_char * 64,
                        }
                    ),
                    encoding="utf-8",
                )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")
            (vault / "ops" / "reports" / "outcome-metrics.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports" / "public-check-summary.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            write_external_manifest(vault)
            write_machine_evidence_bundle(vault)
            unlock_review = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )
            unlock_path = vault / "ops" / "reports" / "learning-claim-unlock-review.json"
            unlock_path.write_text(json.dumps(unlock_review), encoding="utf-8")

            report = build_report(vault, context=fixed_context())

            self.assertEqual(validate_with_schema(unlock_review, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["learning_claim_guard"]["status"], "pass")
            self.assertTrue(report["summary"]["learning_claim_allowed"])
            self.assertTrue(report["summary"]["bounded_learning_claim_allowed"])
            self.assertFalse(report["summary"]["confirmed_learning_improvement_allowed"])
            self.assertEqual(report["summary"]["improvement_claim_status"], "not_ready")
            self.assertEqual(report["summary"]["evidence_cohort_status"], "not_ready")
            self.assertEqual(report["summary"]["learning_claim_blocker_status"], "blocked")
            self.assertEqual(report["learning_claim_guard"]["learning_claim_blocker_status"], "blocked")
            self.assertEqual(
                report["summary"]["self_improvement_claim_model"]["learning_claim_blocker_status"],
                "blocked",
            )
            self.assertFalse(report["summary"]["claim_wording_allowed"])
            self.assertEqual(report["summary"]["claim_level"], "bounded_learning_likely")
            self.assertEqual(
                report["summary"]["self_improvement_claim_model"][
                    "highest_supported_stage"
                ],
                "same_eval_gain",
            )
            self.assertEqual(report["summary"]["learning_claim_evidence_bundle_status"], "active")
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "auto_approved")
            self.assertTrue(report["summary"]["learning_claim_unlock_review_approved"])
            self.assertEqual(
                report["confirmed_evidence_summary"]["confirmed_evidence_status"],
                "not_ready",
            )
            self.assertEqual(
                report["confirmed_evidence_summary"]["evidence_cohort_status"],
                "not_ready",
            )
            self.assertEqual(report["confirmed_evidence_summary"]["valid_run_count"], 0)
            self.assertEqual(report["learning_claim_unlock_review"]["status"], "auto_approved")
            self.assertEqual(
                report["learning_claim_unlock_review"]["confirmed_evidence_summary"],
                report["confirmed_evidence_summary"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_scoreboard_revokes_machine_unlock_when_bound_bundle_goes_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            readiness = machine_claimable_readiness()
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )
            write_machine_bundle_inputs(vault)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")
            write_machine_evidence_bundle(vault)
            unlock_review = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )
            (vault / "ops" / "reports" / "learning-claim-unlock-review.json").write_text(
                json.dumps(unlock_review),
                encoding="utf-8",
            )
            readiness["queue"]["runnable_proposal_count"] = 2
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["learning_claim_guard"]["status"], "blocked")
            self.assertFalse(report["summary"]["learning_claim_allowed"])
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "stale")
            self.assertEqual(report["summary"]["learning_claim_unlock_review_revocation_status"], "stale")
            self.assertEqual(report["summary"]["learning_claim_evidence_bundle_status"], "stale")
            self.assertFalse(report["learning_claim_unlock_review"]["approved"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_scoreboard_stales_machine_unlock_when_public_check_summary_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            readiness = machine_claimable_readiness()
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )
            write_machine_bundle_inputs(vault)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")
            write_machine_evidence_bundle(vault)
            unlock_review = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )
            (vault / "ops" / "reports" / "learning-claim-unlock-review.json").write_text(
                json.dumps(unlock_review),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "public-check-summary.json").write_text(
                json.dumps({"status": "pass", "run_id": "later"}),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["learning_claim_guard"]["status"], "blocked")
            self.assertFalse(report["summary"]["learning_claim_allowed"])
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "stale")
            self.assertEqual(report["summary"]["learning_claim_unlock_review_revocation_status"], "stale")
            self.assertEqual(report["summary"]["learning_claim_evidence_bundle_status"], "stale")
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_unlock_review_rejects_machine_policy_when_behavior_delta_artifact_digest_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            readiness = machine_claimable_readiness()
            (vault / "ops" / "reports").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(readiness),
                encoding="utf-8",
            )
            write_machine_bundle_inputs(vault, run_ids=("run-a", "run-b", "run-c"))
            write_machine_evidence_bundle(vault)
            (vault / "runs" / "run-a" / "behavior-delta.json").write_text(
                json.dumps({"artifact_kind": "behavior_delta", "run_id": "run-a", "summary": {"delta_count": 2}}),
                encoding="utf-8",
            )

            report = build_unlock_review(
                vault,
                auto_policy_path=AUTO_UNLOCK_POLICY_PATH,
                context=fixed_context(),
            )
            predicates = {item["id"]: item for item in report["machine_policy_decision"]["predicate_results"]}

            self.assertFalse(report["approved"])
            self.assertEqual(report["machine_policy_decision"]["decision"], "rejected")
            self.assertEqual(report["machine_policy_decision"]["revocation_status"], "revoked")
            self.assertEqual(
                report["machine_policy_decision"]["confirmed_learning_improvement_status"],
                "revoked",
            )
            self.assertEqual(predicates["learning_claim_evidence_bundle_active"]["status"], "fail")
            self.assertEqual(validate_with_schema(report, load_schema(UNLOCK_REVIEW_SCHEMA_PATH)), [])

    def test_scoreboard_ignores_approved_unlock_review_when_readiness_signals_remain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports" / "routing-provenance-aggregates").mkdir(parents=True)
            (vault / "ops" / "reports" / "auto-improve-readiness.json").write_text(
                json.dumps(
                    {
                        "can_promote_result": True,
                        "learning_readiness": {
                            "likely_to_learn": True,
                            "signals": [{"id": "high_rework"}],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "mutation-proposals.json").write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "failure_mode": "repeated_same_eval_or_discard",
                                "run_ids": ["run-a"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (vault / "runs" / "run-a").mkdir(parents=True)
            (vault / "runs" / "run-a" / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "decision": "PROMOTE",
                        "same_eval_reason_code": "telemetry_discoverability_improved",
                        "strict_secondary_improvement_present": True,
                        "secondary_improvement_axes": ["complexity"],
                        "behavior_delta_digest": "d" * 64,
                    }
                ),
                encoding="utf-8",
            )
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "review.md").write_text("resolved report\n", encoding="utf-8")
            write_unlock_review(vault, approved=True)

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["learning_claim_guard"]["status"], "blocked")
            self.assertFalse(report["summary"]["learning_claim_allowed"])
            self.assertEqual(report["summary"]["learning_claim_unlock_review_status"], "required")
            self.assertFalse(report["summary"]["learning_claim_unlock_review_approved"])
            self.assertIn("high_rework", report["learning_claim_unlock_review"]["reason"])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
