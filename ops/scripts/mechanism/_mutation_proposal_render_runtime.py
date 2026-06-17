from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.schema_constants_runtime import MUTATION_PROPOSAL_SCHEMA_PATH

PRODUCER = "ops.scripts.mutation_proposal_runtime"
SOURCE_COMMAND = (
    "python -m ops.scripts.mutation_proposal "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)
MUTATION_PROPOSAL_SOURCE_PATHS = [
    "ops/scripts/mechanism/mutation_proposal_runtime.py",
    "ops/scripts/mechanism/_mutation_proposal_next_run_repair_runtime.py",
    "ops/scripts/mechanism/_mutation_proposal_render_runtime.py",
    "ops/scripts/mechanism/mutation_proposal_bootstrap_runtime.py",
    "ops/scripts/mechanism/mutation_proposal_candidate_runtime.py",
    "ops/scripts/mechanism/mutation_proposal_loader_runtime.py",
    "ops/scripts/mechanism/mutation_proposal_promotion_runtime.py",
    "ops/scripts/mechanism/mutation_proposal_queue_runtime.py",
    "ops/scripts/mechanism/mutation_proposal_recent_log_overlap_runtime.py",
    "ops/scripts/mechanism/auto_improve_next_run_decision_runtime.py",
    "ops/scripts/mechanism/current_target_path_runtime.py",
    "ops/scripts/mechanism/next_run_repair_queue_runtime.py",
    "ops/scripts/mechanism/noop_repair_classifier_runtime.py",
    "ops/scripts/mechanism/structural_complexity_scope_runtime.py",
]


@dataclass(frozen=True)
class MutationReportRenderInputs:
    vault: Path
    policy: dict[str, Any]
    policy_path: Path
    generated_at: str
    mechanism_review_path: Path
    outcome_metrics_path: Path
    remediation_backlog_path: Path
    system_log: Path
    auto_improve_session_report_paths: list[str]
    mutation_policy: dict[str, Any]
    source_candidate_count: int
    recent_log_count: int
    proposals: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    status: str
    blocked_proposal_count: int
    candidate_blocker_count: int
    proposal_blocker_count: int
    next_run_repair_proposals: int
    queue_pressure_summary: str


def mutation_report_payload(inputs: MutationReportRenderInputs) -> dict[str, Any]:
    diagnostics = dict(inputs.diagnostics)
    diagnostics["source_mechanism_review_report"] = report_path(
        inputs.vault, inputs.mechanism_review_path
    )
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.generated_at,
            artifact_kind="mutation_proposals_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=inputs.policy_path,
            schema_path=MUTATION_PROPOSAL_SCHEMA_PATH,
            source_paths=MUTATION_PROPOSAL_SOURCE_PATHS,
            file_inputs={
                "mechanism_review_report": report_path(
                    inputs.vault, inputs.mechanism_review_path
                ),
                "outcome_metrics": report_path(inputs.vault, inputs.outcome_metrics_path),
                "remediation_backlog": report_path(
                    inputs.vault, inputs.remediation_backlog_path
                ),
                "system_log": report_path(inputs.vault, inputs.system_log),
            },
            path_group_inputs={
                "auto_improve_session_reports": inputs.auto_improve_session_report_paths,
            },
            text_inputs={
                "mutation_max_proposals": str(inputs.mutation_policy["max_proposals"]),
                "mutation_dedupe_window": str(inputs.mutation_policy["dedupe_window"]),
                "mutation_recent_log_overlap_max_age_days": str(
                    inputs.mutation_policy["recent_log_overlap_max_age_days"]
                ),
            },
        ),
        "vault": display_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.policy_path),
            "version": inputs.policy["version"],
        },
        "status": inputs.status,
        "summary": {
            "source_candidates_read": inputs.source_candidate_count,
            "log_entries_scanned": inputs.recent_log_count,
            "proposals_emitted": len(inputs.proposals),
            "blocked_proposals": inputs.blocked_proposal_count,
            "candidate_blocker_count": inputs.candidate_blocker_count,
            "proposal_blocker_count": inputs.proposal_blocker_count,
            "next_run_repair_proposals": inputs.next_run_repair_proposals,
            "queue_pressure_summary": inputs.queue_pressure_summary,
        },
        "diagnostics": diagnostics,
        "proposals": inputs.proposals,
    }
