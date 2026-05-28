from __future__ import annotations

import unittest

from ops.scripts.artifact_freshness_debt_runtime import (
    artifact_freshness_status,
    artifact_record_gate_effect,
    contract_issue_class,
    debt_queues,
    owner_surface,
    report_next_action,
    top_debt,
    top_debt_files,
)


class ArtifactFreshnessDebtRuntimeTests(unittest.TestCase):
    def test_run_local_schema_validation_failed_stays_advisory_contract_debt(self) -> None:
        record = {
            "path": "runs/run-1/repo-health-artifact-freshness-report-check.json",
            "owner_surface": "runs",
            "issues": ["schema_validation_failed"],
            "stable_contract_issues": ["schema_validation_failed"],
            "mtime_sensitive_issues": [],
            "safe_to_backfill": False,
            "mtime_sensitive": False,
            "recommended_next_action": "archive_or_classify_historical_run_artifact",
        }

        self.assertEqual(
            contract_issue_class(
                rel_path=str(record["path"]),
                issues=list(record["issues"]),
                stable_contract_issues=list(record["stable_contract_issues"]),
                mtime_sensitive_issues=[],
                schema_validation_status="historical_schema_drift",
            ),
            "stable_contract_debt",
        )
        self.assertEqual(
            artifact_record_gate_effect(
                rel_path=str(record["path"]),
                issues=list(record["issues"]),
                stable_contract_issues=list(record["stable_contract_issues"]),
                mtime_sensitive_issues=[],
            ),
            "advisory",
        )

        schema_debt = top_debt([record], [], [])[0]
        queues = {item["queue"]: item for item in debt_queues([record])}

        self.assertEqual(schema_debt["gate_effect"], "advisory")
        self.assertEqual(
            schema_debt["recommended_next_action"],
            "archive_or_classify_historical_run_artifact",
        )
        self.assertEqual(queues["runs_historical_archive"]["status"], "open")
        self.assertEqual(queues["runs_historical_archive"]["gate_effect"], "advisory")

    def test_root_ephemeral_debt_action_is_normalized_across_rollups(self) -> None:
        root_ephemeral = [{"path": "pytest_target.log", "matched_pattern": "pytest_*.log"}]

        debt = top_debt([], root_ephemeral, [])[0]
        debt_file = top_debt_files([], root_ephemeral, [])[0]

        self.assertEqual(owner_surface("pytest_target.log"), "root_ephemeral")
        self.assertEqual(debt["issue"], "root_ephemeral_artifact")
        self.assertEqual(debt["gate_effect"], "blocks_execution")
        self.assertEqual(debt["recommended_next_action"], "remove_root_ephemeral_artifact")
        self.assertEqual(debt_file["recommended_next_action"], "remove_root_ephemeral_artifact")

    def test_mtime_sensitive_attention_is_advisory_without_issue_list_debt(self) -> None:
        self.assertEqual(
            contract_issue_class(
                rel_path="ops/reports/generated-artifact-index.json",
                issues=[],
                stable_contract_issues=[],
                mtime_sensitive_issues=["generated_at_older_than_file_mtime"],
                schema_validation_status="pass",
            ),
            "mtime_sensitive_attention",
        )
        self.assertEqual(
            artifact_record_gate_effect(
                rel_path="ops/reports/generated-artifact-index.json",
                issues=[],
                stable_contract_issues=[],
                mtime_sensitive_issues=["generated_at_older_than_file_mtime"],
            ),
            "advisory",
        )

    def test_status_and_report_action_precedence_remain_report_level(self) -> None:
        self.assertEqual(
            artifact_freshness_status(
                root_ephemeral_count=0,
                non_utf8_count=0,
                missing_envelope_count=0,
                missing_schema_count=0,
                stale_count=1,
                unknown_currentness_count=0,
                schema_invalid_count=0,
                schema_unavailable_count=0,
            ),
            "attention",
        )
        self.assertEqual(
            report_next_action(
                root_ephemeral_count=0,
                non_utf8_count=0,
                schema_invalid_count=0,
                missing_envelope_count=1,
                missing_schema_count=0,
                stale_count=1,
                unknown_currentness_count=0,
            ),
            "regenerate_stale_artifacts",
        )


if __name__ == "__main__":
    unittest.main()
