from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict


class PromotionDecisionConfig(TypedDict):
    precedence: int
    is_terminal: bool
    default_finalizable: bool
    ledger_event_type: str
    outcome: str


PROMOTION_DECISION_REGISTRY: dict[str, PromotionDecisionConfig] = {
    "PROMOTE": {
        "precedence": 10,
        "is_terminal": True,
        "default_finalizable": True,
        "ledger_event_type": "promotion_evaluated",
        "outcome": "promoted",
    },
    "HOLD": {
        "precedence": 50,
        "is_terminal": False,
        "default_finalizable": False,
        "ledger_event_type": "promotion_evaluated",
        "outcome": "hold",
    },
    "DISCARD": {
        "precedence": 100,
        "is_terminal": True,
        "default_finalizable": True,
        "ledger_event_type": "promotion_evaluated",
        "outcome": "discarded",
    },
}

PROMOTION_DECISION_VALUES = tuple(PROMOTION_DECISION_REGISTRY)
DECISION_REDUCER_KEY = "promotion_decision_registry_v1"
DECISION_STAGE = "promotion_gate"
TELEMETRY_EMPTY_DECISION = ""
TELEMETRY_SKIPPED_DECISION = "SKIPPED"
DEFAULT_SOURCE_RULE = "default_promote"
DEFAULT_REASON_CODE = "no_blocking_rule_triggered"
LEGACY_SOURCE_RULE = "legacy_top_level_decision"
LEGACY_REASON_CODE = "legacy_promotion_report"
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


class PromotionDecisionRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class PromotionDecisionProposal:
    subject_id: str
    subject_kind: str
    decision: str
    policy_version: int | None = None
    source_rule: str = DEFAULT_SOURCE_RULE
    source_pass: str = "promotion_gate"
    actor: str = "promotion_gate"
    reason_code: str = DEFAULT_REASON_CODE
    reason_detail: str = ""
    evidence_refs: tuple[str, ...] = ()
    decided_at: str = ""
    effective_at: str = ""


@dataclass(frozen=True)
class PromotionDecisionProposalRequest:
    subject_id: str
    subject_kind: str
    decision: str
    policy_version: int | None
    source_rule: str
    source_pass: str
    reason_code: str
    actor: str = "promotion_gate"
    reason_detail: str = ""
    evidence_refs: list[str] | tuple[str, ...] | None = None
    decided_at: str = ""
    effective_at: str = ""


def promotion_decision_values() -> tuple[str, ...]:
    return PROMOTION_DECISION_VALUES


def telemetry_decision_values() -> tuple[str, ...]:
    return (
        TELEMETRY_EMPTY_DECISION,
        *PROMOTION_DECISION_VALUES,
        TELEMETRY_SKIPPED_DECISION,
    )


def validate_promotion_decision(decision: Any) -> str:
    normalized = str(decision).strip() if isinstance(decision, str) else ""
    if normalized not in PROMOTION_DECISION_REGISTRY:
        raise PromotionDecisionRegistryError(
            f"unsupported promotion decision: {decision!r}; "
            f"expected one of {list(PROMOTION_DECISION_VALUES)}"
        )
    return normalized


def decision_config(decision: str) -> PromotionDecisionConfig:
    return PROMOTION_DECISION_REGISTRY[validate_promotion_decision(decision)]


def decision_precedence(decision: str) -> int:
    return int(decision_config(decision)["precedence"])


def decision_outcome(decision: str) -> str:
    return str(decision_config(decision)["outcome"])


def decision_is_terminal(decision: str) -> bool:
    return bool(decision_config(decision)["is_terminal"])


def decision_is_finalizable_by_default(decision: str) -> bool:
    return bool(decision_config(decision)["default_finalizable"])


def decision_ledger_event_type(decision: str) -> str:
    return str(decision_config(decision)["ledger_event_type"])


def terminal_promotion_decisions() -> frozenset[str]:
    return frozenset(
        decision for decision in PROMOTION_DECISION_VALUES if decision_is_terminal(decision)
    )


def finalizable_promotion_decisions() -> frozenset[str]:
    return frozenset(
        decision
        for decision in PROMOTION_DECISION_VALUES
        if decision_is_finalizable_by_default(decision)
    )


TERMINAL_DECISIONS = terminal_promotion_decisions()
FINALIZABLE_DECISIONS = finalizable_promotion_decisions()


def _clean_token(value: str) -> str:
    token = _SLUG_RE.sub("-", value.strip()).strip("-")
    return token or "unknown"


def _decision_id(
    *,
    subject_id: str,
    subject_kind: str,
    decision: str,
    source_rule: str,
    source_pass: str,
    reason_code: str,
) -> str:
    raw = "|".join([subject_id, subject_kind, decision, source_rule, source_pass, reason_code])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"decision:{_clean_token(subject_id)}:{digest}"


def _precedence_key(decision: str) -> str:
    return f"{decision_precedence(decision):04d}:{decision}"


def _dedupe_key(subject_id: str, decision_stage: str = DECISION_STAGE) -> str:
    return f"{subject_id}:{decision_stage}"


def _partition_key(subject_id: str) -> str:
    return subject_id


def _finalize_blockers(decision: str, signoff: dict | None) -> list[str]:
    blockers: list[str] = []
    if not decision_is_finalizable_by_default(decision):
        blockers.append("decision_not_finalizable")
    if isinstance(signoff, dict) and signoff.get("required") and signoff.get("status") != "approved":
        blockers.append("required_signoff_not_approved")
    return blockers


def make_decision_proposal(request: PromotionDecisionProposalRequest) -> PromotionDecisionProposal:
    return PromotionDecisionProposal(
        subject_id=request.subject_id,
        subject_kind=request.subject_kind,
        decision=validate_promotion_decision(request.decision),
        policy_version=request.policy_version,
        source_rule=request.source_rule,
        source_pass=request.source_pass,
        actor=request.actor,
        reason_code=request.reason_code,
        reason_detail=request.reason_detail,
        evidence_refs=tuple(str(item) for item in (request.evidence_refs or ()) if str(item)),
        decided_at=request.decided_at,
        effective_at=request.effective_at,
    )


def _proposal_from_mapping(
    item: Mapping[str, Any],
    *,
    subject_id: str,
    subject_kind: str,
    policy_version: int | None,
    source_pass: str,
) -> PromotionDecisionProposal:
    decision = validate_promotion_decision(item.get("decision"))
    rule_id = str(item.get("rule_id") or item.get("source_rule") or DEFAULT_SOURCE_RULE)
    reason_code = str(item.get("reason_code") or rule_id or DEFAULT_REASON_CODE)
    reason_detail = str(item.get("reason_detail") or item.get("detail") or "")
    raw_refs = item.get("evidence_refs", [])
    evidence_refs = raw_refs if isinstance(raw_refs, list | tuple) else []
    return make_decision_proposal(
        PromotionDecisionProposalRequest(
            subject_id=subject_id,
            subject_kind=subject_kind,
            decision=decision,
            policy_version=policy_version,
            source_rule=rule_id,
            source_pass=str(item.get("source_pass") or source_pass),
            actor=str(item.get("actor") or "promotion_gate"),
            reason_code=reason_code,
            reason_detail=reason_detail,
            evidence_refs=evidence_refs,
            decided_at=str(item.get("decided_at") or ""),
            effective_at=str(item.get("effective_at") or ""),
        )
    )


def _record_from_proposal(
    proposal: PromotionDecisionProposal,
    *,
    signoff: dict | None,
    supersedes: list[str] | None = None,
) -> dict:
    decision = validate_promotion_decision(proposal.decision)
    registry_row = PROMOTION_DECISION_REGISTRY[decision]
    blockers = _finalize_blockers(decision, signoff)
    decision_id = _decision_id(
        subject_id=proposal.subject_id,
        subject_kind=proposal.subject_kind,
        decision=decision,
        source_rule=proposal.source_rule,
        source_pass=proposal.source_pass,
        reason_code=proposal.reason_code,
    )
    return {
        "decision_id": decision_id,
        "subject_id": proposal.subject_id,
        "subject_kind": proposal.subject_kind,
        "decision": decision,
        "decision_stage": DECISION_STAGE,
        "is_terminal": bool(registry_row["is_terminal"]),
        "policy_version": proposal.policy_version if proposal.policy_version is not None else 0,
        "source_rule": proposal.source_rule,
        "source_pass": proposal.source_pass,
        "actor": proposal.actor,
        "reason_code": proposal.reason_code,
        "reason_detail": proposal.reason_detail,
        "evidence_refs": list(proposal.evidence_refs),
        "decided_at": proposal.decided_at,
        "effective_at": proposal.effective_at,
        "supersedes": list(supersedes or []),
        "reducer_key": DECISION_REDUCER_KEY,
        "precedence_key": _precedence_key(decision),
        "dedupe_key": _dedupe_key(proposal.subject_id),
        "finalizable": not blockers,
        "finalize_blockers": blockers,
        "ledger_event_type": str(registry_row["ledger_event_type"]),
        "ledger_partition_key": _partition_key(proposal.subject_id),
    }


def _default_proposal(
    *,
    subject_id: str,
    subject_kind: str,
    policy_version: int | None,
    source_pass: str,
    default: str,
) -> PromotionDecisionProposal:
    return make_decision_proposal(
        PromotionDecisionProposalRequest(
            subject_id=subject_id,
            subject_kind=subject_kind,
            decision=default,
            policy_version=policy_version,
            source_rule=DEFAULT_SOURCE_RULE,
            source_pass=source_pass,
            reason_code=DEFAULT_REASON_CODE,
            reason_detail="No blocking promotion rule emitted HOLD or DISCARD.",
            evidence_refs=[],
        )
    )


def reduce_decision_proposals(
    proposals: Sequence[PromotionDecisionProposal | Mapping[str, Any]],
    *,
    subject_id: str,
    subject_kind: str,
    policy_version: int | None,
    source_pass: str,
    signoff: dict | None = None,
    default: str = "PROMOTE",
) -> dict:
    validate_promotion_decision(default)
    normalized: list[PromotionDecisionProposal] = [
        _proposal_from_mapping(
            proposal,
            subject_id=subject_id,
            subject_kind=subject_kind,
            policy_version=policy_version,
            source_pass=source_pass,
        )
        if isinstance(proposal, Mapping)
        else proposal
        for proposal in proposals
    ]
    if not normalized:
        normalized.append(
            _default_proposal(
                subject_id=subject_id,
                subject_kind=subject_kind,
                policy_version=policy_version,
                source_pass=source_pass,
                default=default,
            )
        )
    proposal_records = [
        _record_from_proposal(proposal, signoff=signoff)
        for proposal in normalized
    ]
    winner = max(
        proposal_records,
        key=lambda record: (decision_precedence(record["decision"]), record["decision_id"]),
    )
    losing_ids = [
        record["decision_id"]
        for record in proposal_records
        if record["decision_id"] != winner["decision_id"]
    ]
    decision_record = dict(winner)
    decision_record["supersedes"] = losing_ids
    reduction = {
        "reducer_key": DECISION_REDUCER_KEY,
        "selected_decision_id": decision_record["decision_id"],
        "proposal_count": len(proposal_records),
        "proposals": proposal_records,
    }
    return {
        "decision": decision_record["decision"],
        "decision_record": decision_record,
        "decision_reduction": reduction,
    }


def validate_decision_record(record: Any) -> dict:
    if not isinstance(record, dict):
        raise PromotionDecisionRegistryError("decision_record must be an object")
    required_fields = (
        "decision_id",
        "subject_id",
        "subject_kind",
        "decision",
        "decision_stage",
        "is_terminal",
        "policy_version",
        "source_rule",
        "source_pass",
        "actor",
        "reason_code",
        "reason_detail",
        "evidence_refs",
        "decided_at",
        "effective_at",
        "supersedes",
        "reducer_key",
        "precedence_key",
        "dedupe_key",
        "finalizable",
        "finalize_blockers",
        "ledger_event_type",
        "ledger_partition_key",
    )
    missing = [field for field in required_fields if field not in record]
    if missing:
        raise PromotionDecisionRegistryError(
            f"decision_record is missing required fields: {missing}"
        )
    decision = validate_promotion_decision(record["decision"])
    if record["decision_stage"] != DECISION_STAGE:
        raise PromotionDecisionRegistryError(
            f"unsupported decision_record.decision_stage: {record['decision_stage']!r}"
        )
    if record["reducer_key"] != DECISION_REDUCER_KEY:
        raise PromotionDecisionRegistryError(
            f"unsupported decision_record.reducer_key: {record['reducer_key']!r}"
        )
    if record["precedence_key"] != _precedence_key(decision):
        raise PromotionDecisionRegistryError("decision_record.precedence_key does not match decision")
    expected_terminal = decision_is_terminal(decision)
    if bool(record["is_terminal"]) != expected_terminal:
        raise PromotionDecisionRegistryError("decision_record.is_terminal does not match registry")
    expected_event_type = decision_ledger_event_type(decision)
    if record["ledger_event_type"] != expected_event_type:
        raise PromotionDecisionRegistryError("decision_record.ledger_event_type does not match registry")
    if not isinstance(record["evidence_refs"], list):
        raise PromotionDecisionRegistryError("decision_record.evidence_refs must be a list")
    if not isinstance(record["supersedes"], list):
        raise PromotionDecisionRegistryError("decision_record.supersedes must be a list")
    if not isinstance(record["finalize_blockers"], list):
        raise PromotionDecisionRegistryError("decision_record.finalize_blockers must be a list")
    if bool(record["finalizable"]) and not decision_is_finalizable_by_default(decision):
        raise PromotionDecisionRegistryError("decision_record.finalizable does not match registry")
    if bool(record["finalizable"]) and record["finalize_blockers"]:
        raise PromotionDecisionRegistryError("decision_record.finalizable conflicts with finalize_blockers")
    return record


def legacy_decision_record_from_report(report: dict) -> dict:
    decision = validate_promotion_decision(report.get("decision"))
    run_id = str(report.get("run_id") or "")
    artifact_class = str(report.get("artifact_class") or "")
    proposal = make_decision_proposal(
        PromotionDecisionProposalRequest(
            subject_id=run_id,
            subject_kind=artifact_class,
            decision=decision,
            policy_version=0,
            source_rule=LEGACY_SOURCE_RULE,
            source_pass="legacy_promotion_report",
            actor="legacy_promotion_report",
            reason_code=LEGACY_REASON_CODE,
            reason_detail="Synthesized from legacy top-level promotion_report.decision.",
            evidence_refs=[],
        )
    )
    return _record_from_proposal(proposal, signoff=report.get("signoff"))


def decision_record_from_report(report: dict, *, require_record: bool = False) -> dict:
    record = report.get("decision_record")
    if record is None:
        if require_record:
            raise PromotionDecisionRegistryError("promotion report is missing canonical decision_record")
        record = legacy_decision_record_from_report(report)
    validated = validate_decision_record(record)
    mirror = report.get("decision")
    if isinstance(mirror, str) and mirror.strip() and mirror.strip() != validated["decision"]:
        raise PromotionDecisionRegistryError(
            "promotion report decision mirror does not match decision_record.decision"
        )
    return validated


def decision_from_report(report: dict, *, require_record: bool = False) -> str:
    return str(decision_record_from_report(report, require_record=require_record)["decision"])


def decision_record_from_payload(payload: dict, *, require_record: bool = False) -> dict:
    if "decision_record" in payload:
        return validate_decision_record(payload["decision_record"])
    if "promotion_report" in payload and isinstance(payload["promotion_report"], dict):
        return decision_record_from_report(payload["promotion_report"], require_record=require_record)
    if require_record:
        raise PromotionDecisionRegistryError("payload is missing canonical decision_record")
    return legacy_decision_record_from_report(payload)


def decision_from_payload(payload: dict, *, require_record: bool = False) -> str:
    return str(decision_record_from_payload(payload, require_record=require_record)["decision"])


def decision_event_from_record(
    record: dict,
    *,
    ledger_event_type: str | None = None,
    effective_at: str | None = None,
) -> dict:
    validated = validate_decision_record(record)
    return {
        "decision_id": validated["decision_id"],
        "decision": validated["decision"],
        "reason_code": validated["reason_code"],
        "policy_version": validated["policy_version"],
        "source_rule": validated["source_rule"],
        "source_pass": validated["source_pass"],
        "effective_at": effective_at if effective_at is not None else validated["effective_at"],
        "ledger_event_type": ledger_event_type or validated["ledger_event_type"],
    }


def attach_decision_contract(
    report: dict,
    triggered_decisions: list[dict],
    *,
    subject_id: str,
    subject_kind: str,
    policy_version: int | None,
    source_pass: str,
    signoff: dict | None = None,
    default: str = "PROMOTE",
) -> dict:
    contract = reduce_decision_proposals(
        triggered_decisions,
        subject_id=subject_id,
        subject_kind=subject_kind,
        policy_version=policy_version,
        source_pass=source_pass,
        signoff=signoff,
        default=default,
    )
    if report.get("decision") not in (None, "", contract["decision"]):
        raise PromotionDecisionRegistryError(
            "promotion report decision mirror does not match reduced canonical decision"
        )
    updated = dict(report)
    updated["decision"] = contract["decision"]
    updated["decision_record"] = contract["decision_record"]
    updated["decision_reduction"] = contract["decision_reduction"]
    return updated
