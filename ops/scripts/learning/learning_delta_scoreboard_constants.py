from __future__ import annotations

DEFAULT_OUT = "ops/reports/learning-delta-scoreboard.json"
LEARNING_CLAIM_UNLOCK_REVIEW_PATH = "ops/reports/learning-claim-unlock-review.json"
PRODUCER = "ops.scripts.learning_delta_scoreboard"
SCHEMA_PATH = "ops/schemas/learning-delta-scoreboard.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.learning_delta_scoreboard --vault ."

EVIDENCE_SCOPE_SPECS = [
    ("report_contract_subset", "ops/reports/test-execution-summary.json", "diagnostic"),
    ("full_suite", "ops/reports/test-execution-summary-full.json", "blocking"),
    ("learning_loop", "ops/reports/auto-improve-readiness.json", "blocking"),
    ("learning_loop", "ops/reports/outcome-metrics.json", "diagnostic"),
    ("release_provenance", "external-reports/report-reference-manifest.json", "blocking"),
]
SAME_EVAL_REASON_CODES = {
    "candidate_eval_improved",
    "telemetry_discoverability_improved",
    "behavior_delta_digest_added",
    "same_eval_no_secondary_improvement",
    "noop_mutation",
    "insufficient_benchmark_resolution",
    "unknown",
}
SAME_EVAL_PROPOSAL_FAILURE_MODES = {
    "repeated_same_eval_or_discard",
    "repeated_same_eval_after_promote",
    "repeated_discard_runs",
}
REQUIRED_LEARNING_CLAIM_REVIEW_ITEMS = [
    "release_evidence_dashboard.placeholder_audit_status == pass",
    "auto_improve_readiness.learning_readiness reviewed after coverage refresh",
    "same_eval_evidence strict-secondary axes reviewed against promotion artifacts",
    "external report provenance and behavior_delta_digest evidence reviewed",
]
SCOREBOARD_SOURCE_PATHS = [
    "ops/scripts/learning/learning_delta_scoreboard.py",
    "ops/scripts/learning/learning_delta_scoreboard_constants.py",
    "ops/scripts/learning/learning_delta_scoreboard_unlock_runtime.py",
    "ops/scripts/learning/learning_delta_scoreboard_anti_slop_runtime.py",
    "ops/scripts/mechanism/auto_improve_iteration_telemetry_runtime.py",
]
