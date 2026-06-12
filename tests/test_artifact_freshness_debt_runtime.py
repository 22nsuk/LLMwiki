from __future__ import annotations

import unittest

from ops.scripts.artifact_freshness_debt_runtime import (
    artifact_freshness_status,
    artifact_record_gate_effect,
    contract_issue_class,
    debt_queues,
    owner_surface,
    report_next_action,
    stale_routing,
    top_debt,
    top_debt_files,
)


class ArtifactFreshnessDebtRuntimeTests(unittest.TestCase):
    def test_run_local_schema_validation_failed_stays_advisory_contract_debt(self) -> None:
        issues: list[str] = ["schema_validation_failed"]
        stable_contract_issues: list[str] = ["schema_validation_failed"]
        record = {
            "path": "runs/run-1/historical-schema-drift.json",
            "owner_surface": "runs",
            "issues": issues,
            "stable_contract_issues": stable_contract_issues,
            "mtime_sensitive_issues": [],
            "safe_to_backfill": False,
            "mtime_sensitive": False,
            "recommended_next_action": "archive_or_classify_historical_run_artifact",
        }

        self.assertEqual(
            contract_issue_class(
                rel_path=str(record["path"]),
                issues=list(issues),
                stable_contract_issues=list(stable_contract_issues),
                mtime_sensitive_issues=[],
                schema_validation_status="historical_schema_drift",
            ),
            "stable_contract_debt",
        )
        self.assertEqual(
            artifact_record_gate_effect(
                rel_path=str(record["path"]),
                issues=list(issues),
                stable_contract_issues=list(stable_contract_issues),
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

    def test_source_identity_only_stale_records_route_to_narrow_resettle(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/public-check-summary.json",
                    "issues": [
                        "source_tree_fingerprint_mismatch",
                        "source_revision_mismatch",
                    ],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                }
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        self.assertEqual(routing["classification"], "source_identity_only")
        self.assertEqual(routing["recommended_lane"], "release-finality-resettle")
        self.assertEqual(
            routing["recommended_targets"],
            ["release-finality-resettle", "release-post-commit-finalize"],
        )
        self.assertEqual(routing["source_identity_only_artifact_count"], 1)
        self.assertEqual(routing["source_identity_only_issue_count"], 2)
        self.assertEqual(routing["execution_blocking_artifact_count"], 0)

    def test_mixed_source_identity_and_schema_debt_keeps_broad_routing(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/public-check-summary.json",
                    "issues": [
                        "source_tree_fingerprint_mismatch",
                        "schema_validation_failed",
                    ],
                    "stable_contract_issues": ["schema_validation_failed"],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "fail",
                    "gate_effect": "blocks_execution",
                }
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        self.assertEqual(routing["classification"], "execution_blocking_debt")
        self.assertEqual(routing["recommended_lane"], "artifact-freshness-refresh-check")
        self.assertEqual(routing["source_identity_only_artifact_count"], 0)
        self.assertEqual(routing["schema_or_contract_debt_artifact_count"], 1)
        self.assertEqual(routing["execution_blocking_artifact_count"], 1)

    def test_overlapping_debt_buckets_do_not_hide_other_operational_attention(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/schema-and-mtime.json",
                    "issues": [
                        "schema_validation_failed",
                        "generated_at_older_than_file_mtime",
                    ],
                    "stable_contract_issues": ["schema_validation_failed"],
                    "mtime_sensitive_issues": ["generated_at_older_than_file_mtime"],
                    "schema_validation_status": "fail",
                    "gate_effect": "claim_blocker",
                },
                {
                    "path": "ops/reports/unknown-currentness.json",
                    "issues": ["unknown_currentness"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                },
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        self.assertEqual(routing["classification"], "schema_or_contract_debt")
        self.assertEqual(routing["problem_artifact_count"], 2)
        self.assertEqual(routing["schema_or_contract_debt_artifact_count"], 1)
        self.assertEqual(routing["mtime_or_test_target_debt_artifact_count"], 1)
        self.assertEqual(routing["other_operational_attention_artifact_count"], 1)

    def test_clean_routing_has_no_release_lane(self) -> None:
        routing = stale_routing([], root_ephemeral_count=0, non_utf8_count=0)

        self.assertEqual(routing["classification"], "clean")
        self.assertEqual(routing["recommended_lane"], "none")
        self.assertEqual(routing["recommended_targets"], [])
        self.assertEqual(routing["problem_artifact_count"], 0)


if __name__ == "__main__":
    unittest.main()
