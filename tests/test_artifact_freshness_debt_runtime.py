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

    def test_source_identity_only_stale_records_route_to_source_identity_converge(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/public-check-summary.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "public_check_summary",
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
        self.assertEqual(routing["recommended_lane"], "freshness-source-identity-converge")
        self.assertEqual(
            routing["recommended_targets"],
            ["freshness-source-identity-converge"],
        )
        self.assertIn("source-identity convergence", routing["summary"])
        self.assertEqual(routing["source_identity_only_artifact_count"], 1)
        self.assertEqual(routing["source_identity_only_issue_count"], 2)
        self.assertEqual(routing["execution_blocking_artifact_count"], 0)
        self.assertEqual(
            routing["source_identity_owner_routes"],
            [
                {
                    "route_id": "ops_reports_public_check_summary",
                    "owner_surface": "ops_reports",
                    "artifact_count": 1,
                    "issue_count": 2,
                    "artifact_kinds": ["public_check_summary"],
                    "recommended_lane": "public-check-summary-current-or-refresh",
                    "recommended_targets": ["public-check-summary-current-or-refresh"],
                    "reason_ids": ["public_check_summary_source_identity"],
                    "sample_paths": ["ops/reports/public-check-summary.json"],
                    "summary": (
                        "1 ops_reports source-identity artifact(s) route to "
                        "public-check-summary-current-or-refresh."
                    ),
                }
            ],
        )

    def test_source_identity_route_fallback_keeps_legacy_records_safe(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/legacy-report.json",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                }
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        route = routing["source_identity_owner_routes"][0]
        self.assertEqual(route["route_id"], "ops_reports_source_identity_resettle")
        self.assertEqual(route["recommended_lane"], "freshness-source-identity-converge")
        self.assertEqual(
            route["recommended_targets"],
            ["freshness-source-identity-converge"],
        )

    def test_source_identity_route_points_release_finality_kind_to_current_or_refresh(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/generated-artifact-index.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "generated_artifact_index_report",
                    "issues": ["source_tree_fingerprint_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                }
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        route = routing["source_identity_owner_routes"][0]
        self.assertEqual(route["route_id"], "ops_reports_release_finality")
        self.assertEqual(route["recommended_lane"], "release-finality-resettle-current-or-refresh")
        self.assertEqual(route["recommended_targets"], ["release-finality-resettle-current-or-refresh"])
        self.assertIn("release finality readback/resettle", route["summary"])

    def test_source_identity_route_requires_completed_goal_run_for_goal_runtime(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/goal-runtime-certificate.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "goal_runtime_certificate",
                    "issues": ["source_revision_mismatch"],
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
        self.assertEqual(
            routing["recommended_lane"],
            "goal-runtime-completed-run-evidence",
        )
        self.assertEqual(
            routing["recommended_targets"],
            [
                "GOAL_RUN_ID=<completed-run-id> make goal-runtime-publish-snapshot",
                "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate",
            ],
        )
        self.assertIn(
            "goal_runtime_completed_run_evidence_required",
            routing["reason_ids"],
        )
        self.assertIn("completed run evidence", routing["summary"])
        self.assertIn("generic freshness refresh", routing["summary"])

        route = routing["source_identity_owner_routes"][0]
        self.assertEqual(route["route_id"], "ops_reports_goal_runtime")
        self.assertEqual(route["recommended_lane"], "goal-runtime-completed-run-evidence")
        self.assertEqual(
            route["recommended_targets"],
            [
                "GOAL_RUN_ID=<completed-run-id> make goal-runtime-publish-snapshot",
                "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate",
            ],
        )
        self.assertEqual(route["reason_ids"], ["goal_runtime_completed_run_evidence_required"])
        self.assertIn("completed goal-run evidence", route["summary"])
        self.assertIn("GOAL_RUN_ID=<completed-run-id>", route["summary"])

    def test_source_identity_route_points_supply_chain_kind_to_supply_chain_lane(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/sigstore-bundle-verification.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "sigstore_bundle_verification",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                }
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        route = routing["source_identity_owner_routes"][0]
        self.assertEqual(route["route_id"], "ops_reports_supply_chain")
        self.assertEqual(route["recommended_lane"], "supply-chain-artifacts-cached")
        self.assertEqual(route["recommended_targets"], ["supply-chain-artifacts-cached"])
        self.assertEqual(route["artifact_kinds"], ["sigstore_bundle_verification"])

    def test_source_identity_route_points_mechanism_kind_to_mechanism_lane(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/mutation-proposals.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "mutation_proposals_report",
                    "issues": ["source_tree_fingerprint_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                }
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        route = routing["source_identity_owner_routes"][0]
        self.assertEqual(route["route_id"], "ops_reports_mutation_proposal")
        self.assertEqual(route["recommended_lane"], "mutation-proposal")
        self.assertEqual(route["recommended_targets"], ["mutation-proposal"])

    def test_source_identity_route_splits_release_smoke_from_source_package(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "ops/reports/release-smoke-report.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "release_smoke_report",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                },
                {
                    "path": "ops/reports/release-smoke-report-fast.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "release_smoke_report",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                },
                {
                    "path": "ops/reports/source-package-clean-extract.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "source_package_clean_extract",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                },
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        routes = {item["route_id"]: item for item in routing["source_identity_owner_routes"]}
        self.assertEqual(
            routes["ops_reports_release_smoke_full_reuse"]["recommended_targets"],
            ["release-smoke-full-reuse"],
        )
        self.assertEqual(
            routes["ops_reports_release_smoke_fast_refresh_check"]["recommended_targets"],
            ["release-smoke-fast-refresh-check"],
        )
        self.assertEqual(
            routes["ops_reports_release_source_package"]["recommended_targets"],
            ["release-source-package-check"],
        )

    def test_source_identity_routes_split_mixed_owner_surfaces(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": "external-reports/report-reference-manifest.json",
                    "owner_surface": "external_reports",
                    "artifact_kind": "external_report_reference_manifest",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "blocks_promotion",
                },
                {
                    "path": "ops/reports/test-execution-summary-full.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "test_execution_summary",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                },
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        self.assertEqual(routing["classification"], "source_identity_only")
        routes = {item["route_id"]: item for item in routing["source_identity_owner_routes"]}
        self.assertEqual(
            routes["external_reports_reference_manifest"]["recommended_lane"],
            "external-report-reference-manifest-settle",
        )
        self.assertEqual(
            routes["ops_reports_test_execution_summary_full_current_or_refresh"]["recommended_lane"],
            "test-execution-summary-full-current-or-refresh",
        )
        self.assertEqual(
            routes["ops_reports_test_execution_summary_full_current_or_refresh"][
                "recommended_targets"
            ],
            ["test-execution-summary-full-current-or-refresh"],
        )

    def test_source_identity_route_sample_paths_are_capped(self) -> None:
        routing = stale_routing(
            [
                {
                    "path": f"ops/reports/supply-chain-{index}.json",
                    "owner_surface": "ops_reports",
                    "artifact_kind": "supply_chain_gate_report",
                    "issues": ["source_revision_mismatch"],
                    "stable_contract_issues": [],
                    "mtime_sensitive_issues": [],
                    "schema_validation_status": "pass",
                    "gate_effect": "claim_blocker",
                }
                for index in range(12)
            ],
            root_ephemeral_count=0,
            non_utf8_count=0,
        )

        route = routing["source_identity_owner_routes"][0]
        self.assertEqual(route["artifact_count"], 12)
        self.assertEqual(len(route["sample_paths"]), 8)

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
