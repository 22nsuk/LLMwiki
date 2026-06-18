from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.mechanism.mechanism_review_history_runtime import (
    group_snapshots_by_targets,
    load_mechanism_run_snapshots,
    load_optional_json,
)
from tests.mechanism_review_test_utils import (
    changed_files_manifest,
    eval_report,
    mechanism_report,
    promotion_report,
    seed_review_vault,
    write_json,
)


class MechanismReviewHistoryRuntimeTests(unittest.TestCase):
    def test_load_mechanism_run_snapshots_accepts_legacy_guardrail_count_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)
            policy, _ = load_policy(vault)
            run_id = "run-20260414-legacy-guardrails"
            primary_targets = ["ops/scripts/promotion_gate.py"]
            baseline_eval = f"runs/{run_id}/baseline-eval.json"
            candidate_eval = f"runs/{run_id}/candidate-eval.json"
            baseline_mechanism = f"runs/{run_id}/baseline-mechanism-assessment.json"
            candidate_mechanism = f"runs/{run_id}/candidate-mechanism-assessment.json"

            def legacy_mechanism_report(nonempty: int) -> dict:
                report = mechanism_report(
                    vault,
                    primary_targets=primary_targets,
                    nonempty=nonempty,
                    functions=2,
                    branches=4,
                    test_file_count=1,
                    test_case_count=2,
                    complexity_score=10,
                )
                report["structural_metrics"].pop("test_guardrail_count")
                report["total_structural_metrics"].pop("test_guardrail_count")
                verification_cost = report["complexity_profile"]["dimension_evidence"][
                    "verification_cost"
                ]
                verification_cost.pop("test_guardrail_count")
                return report

            write_json(vault / baseline_eval, eval_report(vault, 8))
            write_json(vault / candidate_eval, eval_report(vault, 8))
            write_json(vault / baseline_mechanism, legacy_mechanism_report(20))
            write_json(vault / candidate_mechanism, legacy_mechanism_report(22))
            write_json(
                vault / "runs" / run_id / "promotion-report.json",
                promotion_report(
                    run_id,
                    primary_targets=primary_targets,
                    decision="DISCARD",
                    baseline_eval_path=baseline_eval,
                    candidate_eval_path=candidate_eval,
                    baseline_mechanism_path=baseline_mechanism,
                    candidate_mechanism_path=candidate_mechanism,
                ),
            )

            snapshots, skipped_runs, excluded_runs, discovered = load_mechanism_run_snapshots(
                vault,
                policy,
                max_runs=10,
            )

            self.assertEqual(discovered, 1)
            self.assertEqual(skipped_runs, [])
            self.assertEqual(excluded_runs, [])
            self.assertEqual([snapshot.run_id for snapshot in snapshots], [run_id])
            self.assertEqual(snapshots[0].baseline_mechanism["structural_metrics"]["test_guardrail_count"], 0)
            self.assertEqual(
                snapshots[0].candidate_mechanism["complexity_profile"]["dimension_evidence"][
                    "verification_cost"
                ]["test_guardrail_count"],
                0,
            )

    def test_load_mechanism_run_snapshots_splits_valid_skipped_and_excluded_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_review_vault(vault)
            policy, _ = load_policy(vault)
            primary_targets = ["ops/scripts/promotion_gate.py"]

            for run_id, history_status in (
                ("run-20260414-active", "active"),
                ("run-20260414-archived", "archived"),
            ):
                baseline_eval = f"runs/{run_id}/baseline-eval.json"
                candidate_eval = f"runs/{run_id}/candidate-eval.json"
                baseline_mechanism = f"runs/{run_id}/baseline-mechanism-assessment.json"
                candidate_mechanism = f"runs/{run_id}/candidate-mechanism-assessment.json"
                changed_files = f"runs/{run_id}/changed-files-manifest.json"
                write_json(vault / baseline_eval, eval_report(vault, 8))
                write_json(vault / candidate_eval, eval_report(vault, 8))
                write_json(
                    vault / changed_files,
                    changed_files_manifest(
                        run_id,
                        changed_files=[
                            {
                                "path": "ops/scripts/promotion_gate.py",
                                "change_type": "modified",
                            }
                        ],
                        primary_targets=primary_targets,
                    ),
                )
                write_json(
                    vault / baseline_mechanism,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=20,
                        functions=2,
                        branches=4,
                        test_file_count=1,
                        test_case_count=1,
                        complexity_score=10,
                    ),
                )
                write_json(
                    vault / candidate_mechanism,
                    mechanism_report(
                        vault,
                        primary_targets=primary_targets,
                        nonempty=22,
                        functions=2,
                        branches=5,
                        test_file_count=1,
                        test_case_count=1,
                        complexity_score=11,
                    ),
                )
                write_json(
                    vault / "runs" / run_id / "promotion-report.json",
                    promotion_report(
                        run_id,
                        primary_targets=primary_targets,
                        decision="DISCARD",
                        baseline_eval_path=baseline_eval,
                        candidate_eval_path=candidate_eval,
                        baseline_mechanism_path=baseline_mechanism,
                        candidate_mechanism_path=candidate_mechanism,
                        changed_files_manifest_path=changed_files,
                        history_status=history_status,
                        history_reason="covered by newer run" if history_status != "active" else "",
                    ),
                )

            skipped_run = "run-20260414-missing-input"
            write_json(
                vault / "runs" / skipped_run / "promotion-report.json",
                promotion_report(
                    skipped_run,
                    primary_targets=primary_targets,
                    decision="DISCARD",
                    baseline_eval_path=f"runs/{skipped_run}/missing-baseline-eval.json",
                    candidate_eval_path=f"runs/{skipped_run}/missing-candidate-eval.json",
                    baseline_mechanism_path=f"runs/{skipped_run}/missing-baseline-mechanism.json",
                    candidate_mechanism_path=f"runs/{skipped_run}/missing-candidate-mechanism.json",
                ),
            )
            archived_run = "run-20260413-archive-dir"
            write_json(
                vault / "runs" / "archive" / archived_run / "promotion-report.json",
                promotion_report(
                    archived_run,
                    primary_targets=primary_targets,
                    decision="DISCARD",
                    baseline_eval_path=f"runs/archive/{archived_run}/missing-baseline-eval.json",
                    candidate_eval_path=f"runs/archive/{archived_run}/missing-candidate-eval.json",
                    baseline_mechanism_path=f"runs/archive/{archived_run}/missing-baseline-mechanism.json",
                    candidate_mechanism_path=f"runs/archive/{archived_run}/missing-candidate-mechanism.json",
                    history_status="archived",
                    history_reason="moved to archive directory",
                ),
            )

            snapshots, skipped_runs, excluded_runs, discovered = load_mechanism_run_snapshots(
                vault,
                policy,
                max_runs=10,
            )

            self.assertEqual(discovered, 4)
            self.assertEqual([snapshot.run_id for snapshot in snapshots], ["run-20260414-active"])
            self.assertEqual(
                snapshots[0].changed_files_manifest["files"],
                [{"path": "ops/scripts/promotion_gate.py", "change_type": "modified"}],
            )
            self.assertEqual(skipped_runs[0]["run_id"], skipped_run)
            self.assertEqual(skipped_runs[0]["reason"], "run_artifact_invalid")
            self.assertEqual(skipped_runs[0]["triage"]["status"], "operator_decision_required")
            self.assertEqual(skipped_runs[0]["triage"]["problem"], "missing_promotion_input_artifact")
            self.assertEqual(
                skipped_runs[0]["triage"]["recommended_action"],
                "restore_missing_artifact_or_archive_run_history",
            )
            self.assertEqual(excluded_runs[0]["run_id"], "run-20260414-archived")
            self.assertEqual(excluded_runs[0]["status"], "archived")
            self.assertEqual(excluded_runs[1]["run_id"], archived_run)
            self.assertEqual(excluded_runs[1]["status"], "archived")
            self.assertEqual(
                excluded_runs[1]["path"],
                f"runs/archive/{archived_run}/promotion-report.json",
            )
            grouped = group_snapshots_by_targets(snapshots)
            self.assertEqual(list(grouped), [tuple(primary_targets)])

    def test_load_optional_json_returns_none_for_missing_malformed_or_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            malformed = root / "bad.json"
            list_payload = root / "list.json"
            malformed.write_text("{", encoding="utf-8")
            list_payload.write_text("[]", encoding="utf-8")

            self.assertIsNone(load_optional_json(root / "missing.json"))
            self.assertIsNone(load_optional_json(malformed))
            self.assertIsNone(load_optional_json(list_payload))


if __name__ == "__main__":
    unittest.main()
