from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadinessRemediation:
    blocker: str
    remediation_code: str
    blocker_kind: str
    unblock_action_type: str
    minimum_evidence: list[str]
    retry_condition: str
    affected_proposal_count: int
    proposal_ids: list[str]

    def to_wire(self) -> dict[str, Any]:
        return {
            "blocker": self.blocker,
            "remediation_code": self.remediation_code,
            "blocker_kind": self.blocker_kind,
            "unblock_action_type": self.unblock_action_type,
            "minimum_evidence": self.minimum_evidence,
            "retry_condition": self.retry_condition,
            "affected_proposal_count": self.affected_proposal_count,
            "proposal_ids": self.proposal_ids,
        }


@dataclass(frozen=True)
class ReadinessQueue:
    ready: bool
    proposals_emitted: int
    runnable_proposal_count: int
    runnable_proposal_ids: list[str]
    blocked_proposal_count: int
    blocked_reason_counts: list[dict[str, Any]]
    source_candidates_read: int
    candidates_emitted: int
    attempts_considered: int
    session_reports_considered: int
    queue_pressure_summary: str
    review_bootstrap_summary: str
    evidence_gaps: list[str]

    def to_wire(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "proposals_emitted": self.proposals_emitted,
            "runnable_proposal_count": self.runnable_proposal_count,
            "runnable_proposal_ids": self.runnable_proposal_ids,
            "blocked_proposal_count": self.blocked_proposal_count,
            "blocked_reason_counts": self.blocked_reason_counts,
            "source_candidates_read": self.source_candidates_read,
            "candidates_emitted": self.candidates_emitted,
            "attempts_considered": self.attempts_considered,
            "session_reports_considered": self.session_reports_considered,
            "queue_pressure_summary": self.queue_pressure_summary,
            "review_bootstrap_summary": self.review_bootstrap_summary,
            "evidence_gaps": self.evidence_gaps,
        }


@dataclass(frozen=True)
class ReadinessQueueState:
    outcome_summary: dict[str, Any]
    review_summary: dict[str, Any]
    proposal_summary: dict[str, Any]
    proposal_diagnostics: dict[str, Any]
    loop_health_summary: dict[str, Any]
    same_eval_telemetry_summary: dict[str, Any]
    queue_evidence_gaps: list[str]
    proposals_emitted: int
    runnable_proposal_ids: list[str]
    blocked_proposal_count: int
    blocked_reason_counts: dict[str, int]
    blocked_proposal_ids: dict[str, list[str]]
    blocked_reasons: list[str]
    queue_ready: bool
    seed_runs: list[str]
    history_requirement: int
    additional_runs_needed: int


@dataclass(frozen=True)
class ReadinessExecutionFields:
    status: str
    gate_effect: str
    can_run: bool
    reasons: list[str]
    runnable_proposal_count: int
    blocked_proposal_count: int
    recommended_next_step: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "gate_effect": self.gate_effect,
            "can_run": self.can_run,
            "reasons": self.reasons,
            "runnable_proposal_count": self.runnable_proposal_count,
            "blocked_proposal_count": self.blocked_proposal_count,
            "recommended_next_step": self.recommended_next_step,
        }


@dataclass(frozen=True)
class ReadinessQueuePayloads:
    queue: ReadinessQueue
    fallback: dict[str, Any]
    checks: list[dict[str, Any]]
    remediations: list[dict[str, Any]]
