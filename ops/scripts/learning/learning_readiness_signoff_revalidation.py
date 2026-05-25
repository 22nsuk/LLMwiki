#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import (
    build_canonical_report_envelope,
    canonical_report_loading_issue,
)
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.release.release_authority_vocabulary import (
    REASON_MACHINE_RELEASE_NOT_ALLOWED,
)
from ops.scripts.release.release_status_v2 import (
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    LEARNING_READINESS_SIGNOFF_REVALIDATION_SCHEMA_PATH,
    LEARNING_READINESS_SIGNOFF_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)
from ops.scripts.source_tree_fingerprint_runtime import producer_input_fingerprint

from .learning_readiness_vocabulary import (
    LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
    is_signoff_supported_learning_blocker_id,
    learning_release_blocker_ids_from_report,
)

DEFAULT_OUT = "ops/reports/learning-readiness-signoff-revalidation.json"
SIGNOFF_PATH = "ops/reports/learning-readiness-signoff.json"
RELEASE_CLOSEOUT_PATH = "ops/reports/release-closeout-summary.json"
AUTO_IMPROVE_READINESS_PATH = "ops/reports/auto-improve-readiness.json"
SUPPORTED_BLOCKER_ID = LEARNING_REVIEW_REQUIRED_BLOCKER_ID
SIGNOFF_ARTIFACT_KIND = "learning_readiness_signoff"
ARTIFACT_KIND = "learning_readiness_signoff_revalidation"
PRODUCER = "ops.scripts.learning_readiness_signoff_revalidation"
DEFAULT_REQUIRED_COMMAND = "make release-evidence-converge PYTHON=.venv/bin/python"
DEFAULT_REQUIRED_ENVIRONMENT = ".venv clean release-builder"


@dataclass(frozen=True)
class RevalidationFacts:
    window_ends_at: str
    seconds_until_expiry: int
    blocker_present: bool
    signoff_supported_blocker_present: bool
    unsupported_blocker_ids: list[str]
    likely_to_learn: bool
    signoff_active: bool
    signoff_status: str
    expires_at: str
    closeout_evidence_present: bool
    release_effect_summary: str


@dataclass(frozen=True)
class RevalidationDecision:
    revalidation_status: str
    report_status: str
    clean_closeout_required: bool
    status_reason: str


def _parse_iso_z(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _format_iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _empty_signoff(load_status: str, summary: str) -> dict[str, Any]:
    signoff_status = "missing" if load_status == "missing" else "invalid"
    if load_status == "template_only":
        signoff_status = "template_only"
    return {
        "path": SIGNOFF_PATH,
        "load_status": load_status,
        "signoff_status": signoff_status,
        "active": False,
        "linked_blocker_id": "",
        "accepted_by": "",
        "accepted_at": "",
        "expires_at": "",
        "seconds_until_expiry": 0,
        "days_until_expiry": 0.0,
        "risk_owner": "",
        "revalidation_condition": "",
        "rollback_trigger": "",
        "summary": summary,
    }


def _template_marker(payload: dict[str, Any]) -> str:
    if str(payload.get("source_revision", "")).strip() == "template":
        return "source_revision=template"
    if str(payload.get("artifact_status", "")).strip() == "template_only":
        return "artifact_status=template_only"
    if str(payload.get("retention_policy", "")).strip() == "template":
        return "retention_policy=template"
    return ""


def _load_signoff(vault: Path, *, now: dt.datetime) -> dict[str, Any]:
    path = vault / SIGNOFF_PATH
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return _empty_signoff(load_status, str(diagnostics.get("message", load_status)))

    template_marker = _template_marker(payload)
    if template_marker:
        return _empty_signoff("template_only", f"{SIGNOFF_PATH} is template-only ({template_marker})")

    loading_issue = canonical_report_loading_issue(path, payload)
    if loading_issue is not None:
        return _empty_signoff("unusable", f"{SIGNOFF_PATH} is not usable: {loading_issue}")

    schema = load_schema_with_vault_override(vault, LEARNING_READINESS_SIGNOFF_SCHEMA_PATH)
    schema_errors = validate_with_schema(payload, schema)
    if schema_errors:
        return _empty_signoff("schema_invalid", f"{SIGNOFF_PATH} schema errors: {'; '.join(schema_errors[:3])}")

    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if artifact_kind != SIGNOFF_ARTIFACT_KIND:
        return _empty_signoff("kind_mismatch", f"{SIGNOFF_PATH} declares artifact_kind={artifact_kind or '<missing>'}")

    linked_blocker_id = str(payload.get("linked_blocker_id", "")).strip()
    expires_at = str(payload.get("expires_at", "")).strip()
    expires_at_dt = _parse_iso_z(expires_at)
    seconds_until_expiry = 0
    signoff_status = "invalid"
    if expires_at_dt is not None:
        seconds_until_expiry = int((expires_at_dt - now).total_seconds())
        signoff_status = "active" if seconds_until_expiry > 0 else "expired"
    active = signoff_status == "active" and linked_blocker_id == SUPPORTED_BLOCKER_ID
    return {
        "path": SIGNOFF_PATH,
        "load_status": "ok",
        "signoff_status": signoff_status,
        "active": active,
        "linked_blocker_id": linked_blocker_id,
        "accepted_by": str(payload.get("accepted_by", "")).strip(),
        "accepted_at": str(payload.get("accepted_at", "")).strip(),
        "expires_at": expires_at,
        "seconds_until_expiry": seconds_until_expiry,
        "days_until_expiry": round(seconds_until_expiry / 86400, 4),
        "risk_owner": str(payload.get("risk_owner", "")).strip(),
        "revalidation_condition": str(payload.get("revalidation_condition", "")).strip(),
        "rollback_trigger": str(payload.get("rollback_trigger", "")).strip(),
        "summary": f"{SIGNOFF_PATH} {signoff_status} for linked_blocker_id={linked_blocker_id or '<missing>'}",
    }


def _load_closeout(vault: Path) -> dict[str, Any]:
    path = vault / RELEASE_CLOSEOUT_PATH
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return {
            "path": RELEASE_CLOSEOUT_PATH,
            "load_status": load_status,
            "generated_at": "",
            "checked_in_release_ready": False,
            "release_readiness_state": "blocked",
            "release_authority_status": "blocked",
            "semantic_release_status": "blocked",
            "sealed_release_status": "unknown",
            "status_v2_blocker_reason_ids": [],
            "status_v2_used_legacy_fallback_fields": [],
            "machine_release_allowed": False,
            "operator_release_allowed": False,
            "requires_accepted_risk_review": False,
            "status": "unknown",
            "accepted_learning_risk": False,
            "learning_blocker_active": False,
            "source_tree_fingerprint": "",
            "producer_input_fingerprint": "",
            "currentness_status": "unknown",
            "summary": str(diagnostics.get("message", load_status)),
        }

    loading_issue = canonical_report_loading_issue(path, payload)
    raw_currentness = payload.get("currentness")
    currentness: dict[str, Any] = raw_currentness if isinstance(raw_currentness, dict) else {}
    raw_blockers = payload.get("blockers")
    blockers: list[Any] = raw_blockers if isinstance(raw_blockers, list) else []
    raw_accepted_risks = payload.get("accepted_risks")
    accepted_risks: list[Any] = raw_accepted_risks if isinstance(raw_accepted_risks, list) else []
    learning_blocker_active = any(
        isinstance(item, dict) and str(item.get("code", item.get("id", ""))).strip() == SUPPORTED_BLOCKER_ID
        for item in blockers
    )
    accepted_learning_risk = any(
        isinstance(item, dict) and str(item.get("code", item.get("id", ""))).strip() == SUPPORTED_BLOCKER_ID
        for item in accepted_risks
    )
    state = str(payload.get("release_readiness_state", "")).strip()
    checked_in_release_ready = bool(payload.get("checked_in_release_ready"))
    conditional_release_ready = bool(payload.get("conditional_release_ready"))
    clean_release_ready = bool(payload.get("clean_release_ready"))
    if not state:
        if clean_release_ready:
            state = "clean_pass"
        elif conditional_release_ready:
            state = "conditional_pass"
        elif checked_in_release_ready:
            state = "unknown"
        else:
            state = "blocked"
    closeout_status_view = release_status_v2_view_with_readiness_fallback(
        {**payload, "release_readiness_state": state}
    )
    release_authority_status = str(closeout_status_view["release_authority_status"])
    semantic_release_status = str(closeout_status_view["semantic_release_status"])
    sealed_release_status = str(closeout_status_view["sealed_release_status"])
    blocker_reason_ids = [str(reason) for reason in closeout_status_view["blocker_reason_ids"]]
    fallback_fields = [str(field) for field in closeout_status_view["used_legacy_fallback_fields"]]
    if release_authority_status in {"clean_pass", "conditional_pass", "blocked"}:
        state = release_authority_status
    elif state not in {"clean_pass", "conditional_pass", "blocked"}:
        state = "unknown"
    machine_release_allowed = (
        release_authority_status == "clean_pass"
        and REASON_MACHINE_RELEASE_NOT_ALLOWED not in set(blocker_reason_ids)
    )
    operator_release_allowed = release_authority_status in {"clean_pass", "conditional_pass"}
    requires_accepted_risk_review = release_authority_status == "conditional_pass"
    return {
        "path": RELEASE_CLOSEOUT_PATH,
        "load_status": "unusable" if loading_issue else "ok",
        "generated_at": str(payload.get("generated_at", "")).strip(),
        "checked_in_release_ready": checked_in_release_ready,
        "release_readiness_state": state,
        "release_authority_status": release_authority_status,
        "semantic_release_status": semantic_release_status,
        "sealed_release_status": sealed_release_status,
        "status_v2_blocker_reason_ids": blocker_reason_ids,
        "status_v2_used_legacy_fallback_fields": fallback_fields,
        "machine_release_allowed": machine_release_allowed,
        "operator_release_allowed": operator_release_allowed,
        "requires_accepted_risk_review": requires_accepted_risk_review,
        "status": str(payload.get("status", "unknown")).strip() or "unknown",
        "accepted_learning_risk": accepted_learning_risk,
        "learning_blocker_active": learning_blocker_active,
        "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")).strip(),
        "producer_input_fingerprint": producer_input_fingerprint(payload),
        "currentness_status": str(currentness.get("status", "unknown")).strip() or "unknown",
        "summary": (
            loading_issue
            or (
                f"release_authority_status={release_authority_status}; "
                f"release_readiness_state={state}; machine_release_allowed={machine_release_allowed}; "
                f"operator_release_allowed={operator_release_allowed}; "
                f"requires_accepted_risk_review={requires_accepted_risk_review}"
            )
        ),
    }


def _load_learning_readiness(vault: Path) -> dict[str, Any]:
    path = vault / AUTO_IMPROVE_READINESS_PATH
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return {
            "path": AUTO_IMPROVE_READINESS_PATH,
            "load_status": load_status,
            "status": "unknown",
            "likely_to_learn": False,
            "blocker_present": False,
            "signoff_supported_blocker_present": False,
            "signoff_unsupported_blocker_ids": [],
            "blocker_ids": [],
            "signal_ids": [],
            "signals": [],
            "metrics": {},
            "summary": str(diagnostics.get("message", load_status)),
        }

    learning = payload.get("learning_readiness")
    learning_obj: dict[str, Any] = learning if isinstance(learning, dict) else {}
    blocker_ids = learning_release_blocker_ids_from_report(payload)
    unsupported_blocker_ids = [
        blocker_id
        for blocker_id in blocker_ids
        if not is_signoff_supported_learning_blocker_id(blocker_id)
    ]
    raw_signals = learning_obj.get("signals")
    signals: list[Any] = raw_signals if isinstance(raw_signals, list) else []
    signal_ids = [
        str(item.get("id", "")).strip()
        for item in signals
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    ]
    signal_contracts = [dict(item) for item in signals if isinstance(item, dict)]
    metrics = learning_obj.get("metrics") if isinstance(learning_obj.get("metrics"), dict) else {}
    likely_to_learn = bool(learning_obj.get("likely_to_learn"))
    status = str(learning_obj.get("status", "unknown")).strip() or "unknown"
    return {
        "path": AUTO_IMPROVE_READINESS_PATH,
        "load_status": "ok",
        "status": status,
        "likely_to_learn": likely_to_learn,
        "blocker_present": bool(blocker_ids),
        "signoff_supported_blocker_present": any(
            is_signoff_supported_learning_blocker_id(blocker_id)
            for blocker_id in blocker_ids
        ),
        "signoff_unsupported_blocker_ids": unsupported_blocker_ids,
        "blocker_ids": blocker_ids,
        "signal_ids": signal_ids,
        "signals": signal_contracts,
        "metrics": metrics,
        "summary": f"likely_to_learn={likely_to_learn}; blocker_ids={','.join(blocker_ids) or '<none>'}",
    }


def _required_action(action_id: str, *, command: str, environment: str, reason: str, when: str) -> dict[str, str]:
    return {
        "id": action_id,
        "command": command,
        "environment": environment,
        "reason": reason,
        "when": when,
    }


def _decision_option(
    option_id: str,
    *,
    available: bool,
    reason: str,
    required_evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": option_id,
        "available": available,
        "reason": reason,
        "required_evidence": required_evidence,
    }


def _release_effect_summary(closeout: dict[str, Any]) -> str:
    return (
        f"release effect: release_authority_status={closeout.get('release_authority_status')}; "
        f"release_readiness_state={closeout.get('release_readiness_state')}; "
        f"machine_release_allowed={bool(closeout.get('machine_release_allowed'))}; "
        f"operator_release_allowed={bool(closeout.get('operator_release_allowed'))}; "
        f"requires_accepted_risk_review={bool(closeout.get('requires_accepted_risk_review'))}"
    )


def _revalidation_facts(
    *,
    signoff: dict[str, Any],
    closeout: dict[str, Any],
    learning: dict[str, Any],
    window_days: int,
    now: dt.datetime,
) -> RevalidationFacts:
    unsupported_blocker_ids = [
        str(item).strip()
        for item in learning.get("signoff_unsupported_blocker_ids", [])
        if str(item).strip()
    ]
    closeout_evidence_present = (
        str(closeout.get("load_status", "")).strip() == "ok"
        and bool(closeout.get("accepted_learning_risk"))
        and bool(str(closeout.get("generated_at", "")).strip())
    )
    return RevalidationFacts(
        window_ends_at=_format_iso_z(now + dt.timedelta(days=window_days)),
        seconds_until_expiry=int(signoff.get("seconds_until_expiry", 0)),
        blocker_present=bool(learning.get("blocker_present")),
        signoff_supported_blocker_present=bool(learning.get("signoff_supported_blocker_present")),
        unsupported_blocker_ids=unsupported_blocker_ids,
        likely_to_learn=bool(learning.get("likely_to_learn")),
        signoff_active=bool(signoff.get("active")),
        signoff_status=str(signoff.get("signoff_status", "invalid")),
        expires_at=str(signoff.get("expires_at", "")).strip() or "the current signoff expires_at",
        closeout_evidence_present=closeout_evidence_present,
        release_effect_summary=_release_effect_summary(closeout),
    )


def _due_status_reason(facts: RevalidationFacts) -> str:
    if facts.closeout_evidence_present:
        return (
            "learning readiness signoff expires within the revalidation window; "
            "release closeout evidence is present but metrics still leave the blocker open; "
            f"{facts.release_effect_summary}"
        )
    return (
        "learning readiness signoff expires within the revalidation window; "
        "clean release evidence closeout is required before release or renewal; "
        f"{facts.release_effect_summary}"
    )


def _revalidation_decision(
    facts: RevalidationFacts,
    *,
    window_days: int,
) -> RevalidationDecision:
    if facts.likely_to_learn and not facts.blocker_present:
        return RevalidationDecision(
            revalidation_status="metrics_close_candidate",
            report_status="pass",
            clean_closeout_required=False,
            status_reason="learning readiness metrics are sufficient to close the blocker without renewing signoff",
        )
    if facts.blocker_present and facts.unsupported_blocker_ids:
        return RevalidationDecision(
            revalidation_status="missing_signoff",
            report_status="fail",
            clean_closeout_required=True,
            status_reason=(
                "learning blocker is open but cannot be accepted by learning-readiness signoff: "
                + ", ".join(facts.unsupported_blocker_ids)
            ),
        )
    if facts.signoff_status == "expired":
        return RevalidationDecision(
            revalidation_status="overdue",
            report_status="fail",
            clean_closeout_required=True,
            status_reason="learning readiness signoff has expired",
        )
    if not facts.signoff_active and facts.blocker_present:
        return RevalidationDecision(
            revalidation_status="missing_signoff",
            report_status="fail",
            clean_closeout_required=True,
            status_reason="learning blocker is open and no active signoff can accept it",
        )
    if (
        facts.signoff_active
        and facts.blocker_present
        and facts.signoff_supported_blocker_present
        and facts.seconds_until_expiry <= window_days * 86400
    ):
        return RevalidationDecision(
            revalidation_status="due",
            report_status="attention",
            clean_closeout_required=not facts.closeout_evidence_present,
            status_reason=_due_status_reason(facts),
        )
    if facts.signoff_active and facts.blocker_present and facts.signoff_supported_blocker_present:
        return RevalidationDecision(
            revalidation_status="not_due",
            report_status="pass",
            clean_closeout_required=False,
            status_reason="learning readiness signoff is active outside the revalidation window",
        )
    return RevalidationDecision(
        revalidation_status="not_required",
        report_status="pass",
        clean_closeout_required=False,
        status_reason="learning blocker is not open",
    )


def _required_actions_for_revalidation(
    decision: RevalidationDecision,
    facts: RevalidationFacts,
    *,
    required_command: str,
    required_environment: str,
) -> list[dict[str, str]]:
    if decision.clean_closeout_required:
        return [
            _required_action(
                "rerun_clean_release_evidence_converge",
                command=required_command,
                environment=required_environment,
                reason=decision.status_reason,
                when="before release or signoff expiry",
            )
        ]
    if decision.revalidation_status == "due" and facts.blocker_present:
        return [
            _required_action(
                "decide_learning_signoff_renewal",
                command="make learning-readiness-signoff LEARNING_READINESS_SIGNOFF_ACCEPTED_BY=<operator>",
                environment=required_environment,
                reason=decision.status_reason,
                when=f"before {facts.expires_at}",
            )
        ]
    if decision.revalidation_status == "metrics_close_candidate":
        return [
            _required_action(
                "close_learning_blocker_with_metrics",
                command=required_command,
                environment=required_environment,
                reason=decision.status_reason,
                when="before renewing learning-readiness signoff",
            )
        ]
    return []


def _decision_options_for_revalidation(
    facts: RevalidationFacts,
    *,
    required_command: str,
) -> list[dict[str, Any]]:
    signoff_renewal_available = (
        facts.blocker_present
        and facts.signoff_active
        and facts.signoff_supported_blocker_present
        and not facts.unsupported_blocker_ids
    )
    unsupported_blocker_summary = ", ".join(facts.unsupported_blocker_ids)
    return [
        _decision_option(
            "close_blocker_with_metric_improvement",
            available=facts.likely_to_learn and not facts.blocker_present,
            reason="Use this when auto-improve readiness shows learning_readiness.likely_to_learn=true and no open learning blocker.",
            required_evidence=[
                f"{AUTO_IMPROVE_READINESS_PATH} learning_readiness.likely_to_learn=true",
                f"{RELEASE_CLOSEOUT_PATH} has no active {SUPPORTED_BLOCKER_ID} blocker",
            ],
        ),
        _decision_option(
            "renew_signoff_after_clean_closeout",
            available=signoff_renewal_available,
            reason=(
                "Use this only for signoff-supported learning review blockers after rerunning the full "
                "release evidence closeout in the required clean builder context."
            ),
            required_evidence=[
                required_command,
                f"{AUTO_IMPROVE_READINESS_PATH} still shows {SUPPORTED_BLOCKER_ID}",
                f"{SIGNOFF_PATH} renewed with a fresh expires_at",
            ],
        ),
        _decision_option(
            "restore_runnable_proposal_queue",
            available=bool(facts.unsupported_blocker_ids),
            reason=(
                "Use this when learning readiness is blocked by execution not being runnable; "
                "learning-readiness signoff cannot accept this blocker."
            ),
            required_evidence=[
                f"{AUTO_IMPROVE_READINESS_PATH} execution_readiness.can_run == true",
                (
                    f"{AUTO_IMPROVE_READINESS_PATH} has no open signoff-unsupported learning blockers"
                    + (f": {unsupported_blocker_summary}" if unsupported_blocker_summary else "")
                ),
                required_command,
            ],
        ),
        _decision_option(
            "let_signoff_expire_and_block_release",
            available=facts.blocker_present and facts.signoff_supported_blocker_present,
            reason="Use this when a signoff-supported learning review risk is no longer accepted; release closeout should keep the learning blocker active.",
            required_evidence=[
                f"{RELEASE_CLOSEOUT_PATH} contains active blocker {SUPPORTED_BLOCKER_ID}",
            ],
        ),
    ]


def _revalidation_payload(
    facts: RevalidationFacts,
    decision: RevalidationDecision,
    *,
    window_days: int,
) -> dict[str, Any]:
    return {
        "status": decision.revalidation_status,
        "window_days": window_days,
        "window_ends_at": facts.window_ends_at,
        "clean_closeout_required": decision.clean_closeout_required,
        "status_reason": decision.status_reason,
    }


def _classify_revalidation(
    *,
    signoff: dict[str, Any],
    closeout: dict[str, Any],
    learning: dict[str, Any],
    window_days: int,
    now: dt.datetime,
    required_command: str,
    required_environment: str,
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, Any]], str]:
    facts = _revalidation_facts(
        signoff=signoff,
        closeout=closeout,
        learning=learning,
        window_days=window_days,
        now=now,
    )
    decision = _revalidation_decision(facts, window_days=window_days)
    return (
        _revalidation_payload(facts, decision, window_days=window_days),
        _required_actions_for_revalidation(
            decision,
            facts,
            required_command=required_command,
            required_environment=required_environment,
        ),
        _decision_options_for_revalidation(facts, required_command=required_command),
        decision.report_status,
    )


def _release_effect(revalidation: dict[str, Any], closeout: dict[str, Any]) -> dict[str, Any]:
    release_readiness_state = str(closeout.get("release_readiness_state", "unknown")).strip() or "unknown"
    release_authority_status = str(closeout.get("release_authority_status", release_readiness_state)).strip() or "unknown"
    machine_release_allowed = bool(closeout.get("machine_release_allowed"))
    operator_release_allowed = bool(closeout.get("operator_release_allowed"))
    requires_accepted_risk_review = bool(closeout.get("requires_accepted_risk_review"))
    revalidation_status = str(revalidation.get("status", "unknown")).strip() or "unknown"
    if machine_release_allowed and release_authority_status == "clean_pass":
        clean_release_effect = "clean_allowed"
    elif operator_release_allowed and requires_accepted_risk_review:
        clean_release_effect = "conditional_operator_accepted"
    else:
        clean_release_effect = "blocks_clean_release"
    return {
        "clean_release_effect": clean_release_effect,
        "release_readiness_state": release_readiness_state,
        "release_authority_status": release_authority_status,
        "machine_release_allowed": machine_release_allowed,
        "operator_release_allowed": operator_release_allowed,
        "requires_accepted_risk_review": requires_accepted_risk_review,
        "operator_summary": (
            f"learning revalidation={revalidation_status}; release_authority_status={release_authority_status}; "
            f"release_readiness_state={release_readiness_state}; "
            f"machine_release_allowed={machine_release_allowed}; operator_release_allowed={operator_release_allowed}"
        ),
    }


def build_revalidation_report(
    vault: Path,
    *,
    window_days: int = 7,
    required_command: str = DEFAULT_REQUIRED_COMMAND,
    required_environment: str = DEFAULT_REQUIRED_ENVIRONMENT,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    if window_days < 0:
        raise ValueError("window_days must be zero or greater")
    if not required_command.strip():
        raise ValueError("required_command must not be empty")
    if not required_environment.strip():
        raise ValueError("required_environment must not be empty")

    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    now = _parse_iso_z(generated_at)
    if now is None:
        raise ValueError("runtime context generated_at must be an ISO-8601 timestamp")

    signoff = _load_signoff(vault, now=now)
    closeout = _load_closeout(vault)
    learning = _load_learning_readiness(vault)
    revalidation, required_actions, decision_options, status = _classify_revalidation(
        signoff=signoff,
        closeout=closeout,
        learning=learning,
        window_days=window_days,
        now=now,
        required_command=required_command.strip(),
        required_environment=required_environment.strip(),
    )

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind=ARTIFACT_KIND,
            producer=PRODUCER,
            source_command=(
                "python -m ops.scripts.learning_readiness_signoff_revalidation "
                f"--vault . --window-days {window_days}"
            ),
            resolved_policy_path=resolved_policy_path,
            schema_path=LEARNING_READINESS_SIGNOFF_REVALIDATION_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/learning/learning_readiness_signoff_revalidation.py",
                "ops/scripts/learning/learning_readiness_vocabulary.py",
            ],
            file_inputs={
                "learning_readiness_signoff": SIGNOFF_PATH,
                "release_closeout_summary": RELEASE_CLOSEOUT_PATH,
                "auto_improve_readiness": AUTO_IMPROVE_READINESS_PATH,
            },
            text_inputs={
                "window_days": str(window_days),
                "required_command": required_command.strip(),
                "required_environment": required_environment.strip(),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "signoff": signoff,
        "closeout": closeout,
        "learning_readiness": learning,
        "revalidation": revalidation,
        "release_effect": _release_effect(revalidation, closeout),
        "required_actions": required_actions,
        "decision_options": decision_options,
    }


def write_revalidation_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=LEARNING_READINESS_SIGNOFF_REVALIDATION_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="learning readiness signoff revalidation schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Revalidate learning readiness signoff expiry and closeout options")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--required-command", default=DEFAULT_REQUIRED_COMMAND)
    parser.add_argument("--required-environment", default=DEFAULT_REQUIRED_ENVIRONMENT)
    parser.add_argument("--fail-on-due", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_revalidation_report(
        vault,
        window_days=args.window_days,
        required_command=args.required_command,
        required_environment=args.required_environment,
        policy_path=args.policy_path,
    )
    destination = write_revalidation_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.fail_on_due and report["revalidation"]["status"] in {"due", "overdue", "missing_signoff"}:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
