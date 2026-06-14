from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import MUTATION_PROPOSAL_SCHEMA_PATH
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from .auto_improve_next_run_decision_runtime import NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
from .mutation_proposal_bootstrap_runtime import (
    bootstrap_proposal_models_from_review as _bootstrap_proposal_models_from_review,
)
from .mutation_proposal_candidate_runtime import (
    CandidateSuppressedByClosedRemediation,
    MutationProposal,
    PriorityBreakdown,
    fixed_priority_breakdown as _fixed_priority_breakdown,
    generated_must_change_tests as _generated_must_change_tests,
    must_change_test_paths as _must_change_test_paths,
    must_not_expand_apply_roots as _must_not_expand_apply_roots,
    proposal_blast_radius_score as _proposal_blast_radius_score,
    proposal_from_candidate as _proposal_from_candidate,
    required_artifacts as _required_artifacts,
    resolve_must_change_tests as _resolve_must_change_tests,
    with_generated_supporting_targets as _with_generated_supporting_targets,
)
from .mutation_proposal_loader_runtime import (
    MutationReportInputs as _MutationReportInputs,
    RecentLogSection,
    _log_heading_summary,
    load_mutation_report_inputs as _load_mutation_report_inputs,
)
from .mutation_proposal_promotion_runtime import (
    empty_queue_blockers as _empty_queue_blockers,
    report_status as _report_status,
    reported_blocked_proposal_count as _reported_blocked_proposal_count,
    source_evidence_gaps as _source_evidence_gaps,
)
from .mutation_proposal_queue_runtime import (
    queue_pressure_summary as _queue_pressure_summary,
    queue_selection_diagnostics as _queue_selection_diagnostics,
    select_report_proposals as _select_report_proposals,
)
from .mutation_proposal_recent_log_overlap_runtime import (
    RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
    RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
    recent_log_overlap_queue_unblock_proposal as _recent_log_overlap_queue_unblock_proposal,
)
from .next_run_repair_queue_runtime import (
    NextRunRepairProposalDependencies,
    next_run_decision_queue_diagnostics,
    next_run_repair_proposal_models,
)
from .structural_complexity_scope_runtime import (
    proposal_declares_structural_complexity_repair,
    source_targets_within_structural_complexity_budget,
    structural_complexity_source_targets,
)

MUTATION_PROPOSAL_SCHEMA = MUTATION_PROPOSAL_SCHEMA_PATH
STRUCTURAL_COMPLEXITY_BUDGET_BLOCKER = "structural_complexity_budget"
PRODUCER = "ops.scripts.mutation_proposal_runtime"
SOURCE_COMMAND = (
    "python -m ops.scripts.mutation_proposal "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)
MUTATION_PROPOSAL_SOURCE_PATHS = [
    "ops/scripts/mechanism/mutation_proposal_runtime.py",
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
class _MutationProposalAssembly:
    available_proposal_models: list[MutationProposal]
    proposal_models: list[MutationProposal]
    available_proposals: list[dict]
    proposals: list[dict]
    skipped_candidates: list[dict]


@dataclass(frozen=True)
class _MutationDiagnosticsAssembly:
    family_session_calibration: dict
    next_run_decision_queue: dict
    source_evidence_gaps: list[str]
    empty_queue_blockers: list[dict]
    reported_blocked_proposals: int
    status: str
    diagnostics: dict


def _next_run_repair_priority_breakdown() -> PriorityBreakdown:
    return _fixed_priority_breakdown(100)


def _next_run_repair_dependencies() -> NextRunRepairProposalDependencies:
    return NextRunRepairProposalDependencies(
        with_generated_supporting_targets=_with_generated_supporting_targets,
        must_change_test_paths=_must_change_test_paths,
        generated_must_change_tests=_generated_must_change_tests,
        resolve_must_change_tests=_resolve_must_change_tests,
        proposal_blast_radius_score=_proposal_blast_radius_score,
        must_not_expand_apply_roots=_must_not_expand_apply_roots,
        required_artifacts=_required_artifacts,
        proposal_factory=MutationProposal,
        priority_breakdown_factory=_next_run_repair_priority_breakdown,
    )


def _priority_sort_key(proposal: MutationProposal) -> tuple[int, str]:
    return (-proposal.priority, proposal.proposal_id)


def _proposal_target_paths(proposal: MutationProposal) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *proposal.primary_targets,
                *proposal.supporting_targets,
            ]
        )
    )


def _proposal_primary_target_paths(proposal: MutationProposal) -> list[str]:
    primary_targets = list(dict.fromkeys(proposal.primary_targets))
    return primary_targets or _proposal_target_paths(proposal)


def _with_start_admission_blockers(
    vault: Path,
    proposal: MutationProposal,
    *,
    context: RuntimeContext,
) -> MutationProposal:
    if proposal.failure_mode != NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE:
        return proposal
    target_paths = _proposal_primary_target_paths(proposal)
    source_targets = structural_complexity_source_targets(target_paths)
    if not source_targets:
        return proposal
    if proposal_declares_structural_complexity_repair(proposal.to_wire()):
        return proposal
    if source_targets_within_structural_complexity_budget(
        vault,
        source_targets,
        context=context,
    ):
        return proposal
    blocked_by = list(
        dict.fromkeys(
            [
                *proposal.blocked_by,
                STRUCTURAL_COMPLEXITY_BUDGET_BLOCKER,
            ]
        )
    )
    return replace(proposal, blocked_by=blocked_by)


def _recent_log_overlap_diagnostics(
    proposal_models: list[MutationProposal],
    *,
    dedupe_window: int,
    max_age_days: int,
    section_ordering: str,
    recent_log_sections: list[RecentLogSection],
) -> dict:
    return {
        "dedupe_window": dedupe_window,
        "max_age_days": max_age_days,
        "section_ordering": section_ordering,
        "scanned_log_headings": _log_heading_summary(recent_log_sections),
        "matches": [
            match.to_wire(
                proposal_id=proposal.proposal_id,
                source_candidate_id=proposal.source_candidate_id,
            )
            for proposal in proposal_models
            for match in proposal.recent_log_overlap_matches
        ],
    }


def _family_session_calibration_diagnostics(
    mechanism_review_report: dict,
    proposals: list[dict],
) -> dict:
    source_summary = (
        mechanism_review_report.get("diagnostics", {}).get("session_calibration", {})
    )
    enabled = bool(source_summary.get("enabled", True)) if isinstance(source_summary, dict) else True
    source_by_family = {}
    if isinstance(source_summary, dict):
        for item in source_summary.get("by_family", []):
            if not isinstance(item, dict):
                continue
            family = str(item.get("family", "")).strip()
            if family:
                source_by_family[family] = item

    proposal_count_by_family: dict[str, int] = {}
    blocked_count_by_family: dict[str, int] = {}
    for proposal in proposals:
        family = str(proposal.get("family", "")).strip()
        if not family:
            continue
        proposal_count_by_family[family] = proposal_count_by_family.get(family, 0) + 1
        if proposal.get("blocked_by"):
            blocked_count_by_family[family] = blocked_count_by_family.get(family, 0) + 1

    families = sorted(proposal_count_by_family)
    if not proposals:
        status = "no_proposals"
    elif not enabled:
        status = "disabled"
    else:
        status = str(source_summary.get("status", "")).strip() if isinstance(source_summary, dict) else ""
        if status not in {"active", "no_session_context", "disabled"}:
            status = "active"

    by_family = []
    for family in families:
        source_family = source_by_family.get(family, {})
        by_family.append(
            {
                "family": family,
                "proposal_count": proposal_count_by_family.get(family, 0),
                "blocked_proposal_count": blocked_count_by_family.get(family, 0),
                "session_priority_delta": int(source_family.get("total_priority_delta", 0)),
                "boosted_candidates": int(source_family.get("boosted_candidates", 0)),
                "lowered_candidates": int(source_family.get("lowered_candidates", 0)),
                "unchanged_candidates": int(source_family.get("unchanged_candidates", 0)),
                "validation_blocked_sessions": int(source_family.get("validation_blocked_sessions", 0)),
                "review_blocked_sessions": int(source_family.get("review_blocked_sessions", 0)),
                "mutation_failed_sessions": int(source_family.get("mutation_failed_sessions", 0)),
                "validator_dispatch_sessions": int(source_family.get("validator_dispatch_sessions", 0)),
                "reviewer_dispatch_sessions": int(source_family.get("reviewer_dispatch_sessions", 0)),
                "high_risk_routing_sessions": int(source_family.get("high_risk_routing_sessions", 0)),
            }
        )

    return {
        "enabled": enabled,
        "status": status,
        "proposal_count": len(proposals),
        "blocked_proposal_count": sum(1 for proposal in proposals if proposal.get("blocked_by")),
        "by_family": by_family,
    }


def _candidate_blocker_count(mechanism_review_report: dict) -> int:
    diagnostics = mechanism_review_report.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return 0
    blockers = diagnostics.get("candidate_blockers", [])
    if not isinstance(blockers, list):
        return 0
    return sum(1 for blocker in blockers if isinstance(blocker, dict))


def _proposal_models_from_candidates(
    vault: Path,
    effective_policy: dict,
    mechanism_review_report: dict,
    *,
    recent_log_sections: list[RecentLogSection],
    outcome_metrics_report: dict,
    remediation_backlog_report: dict,
    next_run_decisions: list[dict],
    consumed_next_run_decision_ids: list[str],
) -> tuple[list[MutationProposal], list[dict]]:
    available_proposal_models: list[MutationProposal] = []
    skipped_candidates: list[dict] = []
    if not effective_policy["mutation_proposal"]["enabled"]:
        return available_proposal_models, skipped_candidates

    for candidate in mechanism_review_report["candidates"]:
        try:
            proposal_model = _proposal_from_candidate(
                vault,
                effective_policy,
                candidate,
                remediation_backlog_report=remediation_backlog_report,
                recent_log_sections=recent_log_sections,
                skipped_candidates=skipped_candidates,
            )
        except CandidateSuppressedByClosedRemediation as exc:
            skipped_candidates.append(
                {
                    "candidate_id": candidate.get("candidate_id", "<unknown>"),
                    "reason": "closed_remediation_backlog_resolution",
                    "detail": exc.detail,
                }
            )
            continue
        except ValueError as exc:
            skipped_candidates.append(
                {
                    "candidate_id": candidate.get("candidate_id", "<unknown>"),
                    "reason": "candidate_mapping_error",
                    "detail": str(exc),
                }
            )
            continue
        if proposal_model is None:
            skipped_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "reason": "failure_mode_not_allowed",
                    "detail": candidate["candidate_type"],
                }
            )
            continue
        available_proposal_models.append(proposal_model)
    available_proposal_models.extend(
        _bootstrap_proposal_models_from_review(vault, effective_policy, mechanism_review_report)
    )
    recent_log_overlap_unblock = _recent_log_overlap_queue_unblock_proposal(
        vault,
        effective_policy,
        available_proposal_models,
        recent_log_sections=recent_log_sections,
        outcome_metrics_report=outcome_metrics_report,
    )
    if recent_log_overlap_unblock is not None:
        available_proposal_models.append(recent_log_overlap_unblock)
    current_runnable_proposal_ids = {
        proposal.proposal_id
        for proposal in available_proposal_models
        if proposal.proposal_id and not proposal.blocked_by
    }
    available_proposal_models.extend(
        next_run_repair_proposal_models(
            vault,
            effective_policy,
            next_run_decisions,
            consumed_decision_ids=set(consumed_next_run_decision_ids),
            current_proposal_ids=current_runnable_proposal_ids,
            dependencies=_next_run_repair_dependencies(),
            recent_log_overlap_unblock_failure_mode=RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
            recent_log_overlap_unblock_family=RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
        )
    )
    return available_proposal_models, skipped_candidates


def _assemble_mutation_proposals(
    vault: Path,
    inputs: _MutationReportInputs,
) -> _MutationProposalAssembly:
    available_proposal_models, skipped_candidates = _proposal_models_from_candidates(
        vault,
        inputs.effective_policy,
        inputs.mechanism_review_report,
        recent_log_sections=inputs.recent_log_sections,
        outcome_metrics_report=inputs.outcome_metrics_report,
        remediation_backlog_report=inputs.remediation_backlog_report,
        next_run_decisions=inputs.next_run_decisions,
        consumed_next_run_decision_ids=inputs.consumed_next_run_decision_ids,
    )
    available_proposal_models = [
        _with_start_admission_blockers(
            vault,
            proposal,
            context=inputs.runtime_context,
        )
        for proposal in available_proposal_models
    ]
    proposal_models = _select_report_proposals(
        available_proposal_models,
        max_proposals=int(inputs.mutation_policy["max_proposals"]),
    )
    return _MutationProposalAssembly(
        available_proposal_models=available_proposal_models,
        proposal_models=proposal_models,
        available_proposals=[proposal.to_wire() for proposal in available_proposal_models],
        proposals=[proposal.to_wire() for proposal in proposal_models],
        skipped_candidates=skipped_candidates,
    )


def _assemble_mutation_diagnostics(
    vault: Path,
    inputs: _MutationReportInputs,
    proposal_assembly: _MutationProposalAssembly,
) -> _MutationDiagnosticsAssembly:
    family_session_calibration = _family_session_calibration_diagnostics(
        inputs.mechanism_review_report,
        proposal_assembly.proposals,
    )
    next_run_decision_queue = next_run_decision_queue_diagnostics(
        inputs.next_run_decisions,
        proposal_assembly.proposals,
        vault=vault,
        session_report_paths=inputs.auto_improve_session_report_paths,
        consumed_decision_ids=set(inputs.consumed_next_run_decision_ids),
        recent_log_overlap_unblock_failure_mode=RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
        recent_log_overlap_unblock_family=RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
    )
    source_evidence_gaps = _source_evidence_gaps(
        inputs.mechanism_review_report,
        proposal_assembly.proposals,
    )
    empty_queue_blockers = _empty_queue_blockers(
        mutation_enabled=bool(inputs.mutation_policy["enabled"]),
        mechanism_review_report=inputs.mechanism_review_report,
        available_proposals=proposal_assembly.available_proposals,
        proposals=proposal_assembly.proposals,
        skipped_candidates=proposal_assembly.skipped_candidates,
        evidence_gaps=source_evidence_gaps,
    )
    reported_blocked_proposals = _reported_blocked_proposal_count(
        proposal_assembly.proposals,
        empty_queue_blockers,
    )
    status = _report_status(
        enabled=bool(inputs.mutation_policy["enabled"]),
        proposals=proposal_assembly.proposals,
    )
    return _MutationDiagnosticsAssembly(
        family_session_calibration=family_session_calibration,
        next_run_decision_queue=next_run_decision_queue,
        source_evidence_gaps=source_evidence_gaps,
        empty_queue_blockers=empty_queue_blockers,
        reported_blocked_proposals=reported_blocked_proposals,
        status=status,
        diagnostics={
            "source_mechanism_review_report": "",
            "skipped_candidates": proposal_assembly.skipped_candidates,
            "evidence_gaps": source_evidence_gaps,
            "empty_queue_blockers": empty_queue_blockers,
            "family_session_calibration": family_session_calibration,
            "next_run_decision_queue": next_run_decision_queue,
            "queue_selection": _queue_selection_diagnostics(
                proposal_assembly.available_proposals,
                proposal_assembly.proposals,
            ),
            "recent_log_overlap": _recent_log_overlap_diagnostics(
                proposal_assembly.available_proposal_models,
                dedupe_window=int(inputs.mutation_policy["dedupe_window"]),
                max_age_days=int(inputs.mutation_policy["recent_log_overlap_max_age_days"]),
                section_ordering=inputs.recent_log_section_ordering,
                recent_log_sections=inputs.recent_log_sections,
            ),
        },
    )


def _mutation_report_payload(
    vault: Path,
    policy: dict,
    policy_path: Path,
    inputs: _MutationReportInputs,
    proposal_assembly: _MutationProposalAssembly,
    diagnostics_assembly: _MutationDiagnosticsAssembly,
) -> dict:
    diagnostics = dict(diagnostics_assembly.diagnostics)
    diagnostics["source_mechanism_review_report"] = report_path(vault, inputs.mechanism_review_path)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=inputs.runtime_context.isoformat_z(),
            artifact_kind="mutation_proposals_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=policy_path,
            schema_path=MUTATION_PROPOSAL_SCHEMA,
            source_paths=MUTATION_PROPOSAL_SOURCE_PATHS,
            file_inputs={
                "mechanism_review_report": report_path(vault, inputs.mechanism_review_path),
                "outcome_metrics": report_path(vault, inputs.outcome_metrics_path),
                "remediation_backlog": report_path(vault, inputs.remediation_backlog_path),
                "system_log": report_path(vault, inputs.system_log),
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
        "vault": display_path(vault, vault),
        "policy": {
            "path": report_path(vault, policy_path),
            "version": policy["version"],
        },
        "status": diagnostics_assembly.status,
        "summary": {
            "source_candidates_read": len(inputs.mechanism_review_report["candidates"]),
            "log_entries_scanned": len(inputs.recent_log_sections),
            "proposals_emitted": len(proposal_assembly.proposals),
            "blocked_proposals": diagnostics_assembly.reported_blocked_proposals,
            "candidate_blocker_count": _candidate_blocker_count(inputs.mechanism_review_report),
            "proposal_blocker_count": len(diagnostics_assembly.empty_queue_blockers),
            "next_run_repair_proposals": diagnostics_assembly.next_run_decision_queue[
                "repair_proposals_emitted"
            ],
            "queue_pressure_summary": _queue_pressure_summary(
                diagnostics_assembly.family_session_calibration,
                evidence_gaps=diagnostics_assembly.source_evidence_gaps,
            ),
        },
        "diagnostics": diagnostics,
        "proposals": proposal_assembly.proposals,
    }


def _validate_and_finalize_mutation_report(
    vault: Path,
    report: dict,
    runtime_context: RuntimeContext,
) -> dict:
    schema = load_schema_with_vault_override(vault, MUTATION_PROPOSAL_SCHEMA)
    errors = validate_with_schema(report, schema)
    if errors:
        raise ValueError(f"mutation proposal report schema validation failed: {errors[0]}")

    finalized_generated_at = runtime_context.isoformat_z()
    report["generated_at"] = finalized_generated_at
    currentness = report.get("currentness")
    if isinstance(currentness, dict):
        currentness["checked_at"] = finalized_generated_at
    return report


def build_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    mechanism_review_report_path: str | None = None,
    system_log_path: str | None = None,
    max_proposals: int | None = None,
    dedupe_window: int | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    inputs = _load_mutation_report_inputs(
        vault,
        policy,
        policy_path,
        mechanism_review_report_path=mechanism_review_report_path,
        system_log_path=system_log_path,
        max_proposals=max_proposals,
        dedupe_window=dedupe_window,
        context=context,
    )
    proposal_assembly = _assemble_mutation_proposals(vault, inputs)
    diagnostics_assembly = _assemble_mutation_diagnostics(vault, inputs, proposal_assembly)
    report = _mutation_report_payload(
        vault,
        policy,
        policy_path,
        inputs,
        proposal_assembly,
        diagnostics_assembly,
    )
    return _validate_and_finalize_mutation_report(vault, report, inputs.runtime_context)
