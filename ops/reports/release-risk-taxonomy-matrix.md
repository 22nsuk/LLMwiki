# Release Risk Taxonomy Matrix

- Generated at: 2026-05-23T08:47:22Z
- Taxonomy: ops/policies/release-risk-taxonomy.json
- Taxonomy version: 1
- Risk codes: 45
- Clean-lane blockers: 30
- Learning-claim blockers: 16
- Advisory lifecycle backlog: 3

| Risk code | Primary lane | Clean | Conditional | Learning | Advisory | Surface |
| --- | --- | --- | --- | --- | --- | --- |
| artifact_freshness_attention | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | artifact freshness |
| artifact_freshness_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | artifact freshness |
| auto_improve_execution_not_ready | learning_claim_blocker | does_not_block_clean_lane | not_applicable | blocks_learning_claim | not_applicable | auto-improve readiness |
| auto_improve_release_blocker | learning_claim_blocker | does_not_block_clean_lane | not_applicable | blocks_learning_claim | not_applicable | auto-improve readiness |
| bootstrap_preflight_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | bootstrap preflight |
| execution_blocked_by_no_runnable_proposal | learning_claim_blocker | does_not_block_clean_lane | not_applicable | blocks_learning_claim | not_applicable | auto-improve readiness |
| external_report_reference_manifest_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | external report provenance |
| external_report_strict_unavailable | advisory_lifecycle_backlog | does_not_block_clean_lane | operator_review_required | not_applicable | review_backlog | external report provenance |
| generated_index_archive_advisory | advisory_lifecycle_backlog | does_not_block_clean_lane | not_applicable | not_applicable | review_backlog | generated artifact archive lifecycle |
| generated_index_unknown_status | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | generated artifact index |
| learning_blocked_by_execution_not_runnable | learning_claim_blocker | does_not_block_clean_lane | not_applicable | blocks_learning_claim | not_applicable | learning claim readiness |
| learning_blocked_by_review_required | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | learning claim readiness |
| live_make_check_nodeid_outcome_mismatch | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | live full-suite release gate |
| live_make_check_not_full_suite | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | live full-suite release gate |
| live_make_check_not_pass | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | live full-suite release gate |
| live_make_check_report_missing | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | live full-suite release gate |
| live_make_check_toolchain_not_eligible | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | live full-suite release gate |
| promotion_blocked_by_artifact_contract_failure | clean_lane_blocker | blocks_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_artifact_finalization_failure | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_goal_worktree_guard_failure | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve worktree guard |
| promotion_blocked_by_release_authority_preflight_failure | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_release_batch_manifest_failure | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_release_closeout_summary_failure | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_release_finality_failure | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_release_lineage_mismatch | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_remediation_backlog_open | learning_claim_blocker | does_not_block_clean_lane | operator_review_required | blocks_learning_claim | review_backlog | auto-improve remediation backlog |
| promotion_blocked_by_selected_contract_failure | clean_lane_blocker | blocks_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| promotion_blocked_by_source_package_failure | clean_lane_blocker | blocks_clean_lane | operator_review_required | blocks_learning_claim | not_applicable | auto-improve release gate |
| raw_registry_preflight_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | raw registry preflight |
| raw_registry_preflight_warnings | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | raw registry preflight |
| release_risk_taxonomy_unregistered_code | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | release risk taxonomy coverage |
| release_smoke_boundedness_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | release smoke archive budget |
| release_smoke_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | release smoke |
| sbom_readiness_gate_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | sbom readiness |
| source_package_clean_extract_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | source package clean extract |
| source_tree_coherence_attention | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | source-tree coherence |
| source_tree_coherence_missing_fingerprint | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | source-tree coherence |
| supply_chain_gate_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | supply-chain gate |
| test_deselection_acceptance_incomplete | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
| test_deselection_accepted_risk | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
| test_deselection_lifecycle_failed | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
| test_deselection_lifecycle_missing | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
| test_deselection_not_expected_to_pass_after_refresh | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
| test_deselection_release_blocking | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
| test_summary_not_pass | clean_lane_blocker | blocks_clean_lane | operator_review_required | not_applicable | not_applicable | full-suite evidence |
