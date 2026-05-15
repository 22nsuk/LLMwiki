from __future__ import annotations

READINESS_REPORT_REL_PATH = "ops/reports/auto-improve-readiness.json"
OUTCOME_METRICS_REPORT_REL_PATH = "ops/reports/outcome-metrics.json"
MECHANISM_REVIEW_REPORT_REL_PATH = "ops/reports/mechanism-review-candidates.json"
MUTATION_PROPOSAL_REPORT_REL_PATH = "ops/reports/mutation-proposals.json"
ARTIFACT_FRESHNESS_REPORT_REL_PATH = "ops/reports/artifact-freshness-report.json"
SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH = "ops/reports/test-execution-summary.json"
SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH = "ops/reports/source-package-clean-extract.json"
RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH = "ops/reports/release-closeout-summary.json"
RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH = "ops/reports/release-closeout-batch-manifest.json"
RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH = "ops/reports/release-closeout-finality-attestation.json"
RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH = "ops/reports/release-evidence-cohort.json"
RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH = "tmp/release-closeout-post-check-finalizer.json"
RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH = (
    "build/release/release-closeout-sealed-rehearsal-check.json"
)
RELEASE_AUTHORITY_PREFLIGHT_FALLBACK_REPORT_REL_PATH = (
    "tmp/release-closeout-sealed-dry-run/release-closeout-sealed-rehearsal-check.json"
)
RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATHS = (
    RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATH,
    RELEASE_AUTHORITY_PREFLIGHT_FALLBACK_REPORT_REL_PATH,
)
ROUTING_PROVENANCE_AGGREGATE_DIR = "ops/reports/routing-provenance-aggregates"
READINESS_REPORT_PRODUCER = "ops.scripts.auto_improve_readiness_runtime"
READINESS_REPORT_SOURCE_COMMAND = (
    "python -m ops.scripts.mechanism.auto_improve_readiness "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)
READINESS_SOURCE_PATHS = [
    "ops/scripts/mechanism/auto_improve_readiness_runtime.py",
    "ops/scripts/mechanism/auto_improve_readiness_constants_runtime.py",
    "ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py",
    "ops/scripts/mechanism/auto_improve_readiness_learning_runtime.py",
    "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
]
FALLBACK_PRIMARY_TARGETS = ["ops/scripts/auto_improve_iteration_persistence_runtime.py"]
FALLBACK_SUPPORTING_TARGETS = ["ops/schemas/run-telemetry.schema.json"]
FALLBACK_TEST_FILES = ["tests/test_auto_improve_iteration_runtime.py"]
DEFAULT_MIN_ATTEMPTS_CONSIDERED = 10
DEFAULT_HOLD_OR_DISCARD_MOVING_AVERAGE = 0.25
DEFAULT_HIGH_REWORK_COUNT = 1
DEFAULT_DEFECT_ESCAPE_PAIR_COUNT = 1
REFRESH_GENERATED_TARGET = "make refresh-generated-core"
READINESS_TARGET = "make auto-improve-readiness"
AUTO_IMPROVE_LOOP_COMMAND = (
    ".venv/bin/python -m ops.scripts.mechanism.auto_improve_loop "
    "--vault . "
    "--policy ops/policies/wiki-maintainer-policy.yaml "
    "--max-proposals 1 "
    "--max-minutes 30 "
    "--max-consecutive-failures 1 "
    "--executor codex_exec"
)
AUTO_IMPROVE_LOOP_ALLOW_LEARNING_UNCERTAIN_COMMAND = (
    f"{AUTO_IMPROVE_LOOP_COMMAND} --allow-learning-uncertain"
)
SAME_EVAL_PROPOSAL_FAILURE_MODES = {
    "repeated_same_eval_or_discard",
    "repeated_same_eval_after_promote",
    "repeated_discard_runs",
}
RECENT_LOG_OVERLAP_REMEDIATION = {
    "remediation_code": "wait_for_recent_log_overlap_to_clear",
    "blocker_kind": "hard",
    "unblock_action_type": "chronology_advance_or_target_rotation",
    "minimum_evidence": [
        "A refreshed mutation proposal report no longer lists recent_log_overlap in blocked_by for every emitted proposal.",
        "auto-improve readiness reports queue.runnable_proposal_count greater than 0.",
        "The recent overlapping target chronology has advanced or the proposal target set no longer overlaps the recent run log.",
    ],
    "retry_condition": (
        "Rerun make auto-improve-readiness after make refresh-generated-core observes a newer chronology "
        "or a non-overlapping runnable proposal."
    ),
}
