from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .auto_improve_readiness_runtime import learning_review_required
from .auto_improve_value_runtime import _mapping_value


@dataclass(frozen=True)
class LearningPreflightDecision:
    review_required: bool
    blocked: bool
    learning_mode: dict[str, object]
    recommended_next_step: str


def _learning_uncertain_policy_authorization(learning_policy: Mapping[str, Any]) -> dict[str, object]:
    source = str(learning_policy.get("authorization_source", "")).strip()
    allowed = (
        learning_policy.get("allow_bounded_trial") is True
        and learning_policy.get("requires_explicit_authorization") is True
        and source == "codex_goal_contract"
    )
    return {
        "allowed": allowed,
        "authorization_source": source if allowed else "",
        "command_flag": str(learning_policy.get("command_flag", "")).strip(),
    }


def _learning_uncertain_execution_policy_authorization(
    execution_policy: Mapping[str, Any],
) -> dict[str, object]:
    return _learning_uncertain_policy_authorization(
        _mapping_value(execution_policy, "learning_uncertain")
    )


def goal_contract_authorizes_learning_uncertain(contract: Mapping[str, Any]) -> bool:
    return bool(
        _learning_uncertain_execution_policy_authorization(
            _mapping_value(contract, "execution_policy")
        )["allowed"]
    )


def _learning_uncertain_contract_authorization(session: Mapping[str, Any]) -> dict[str, object]:
    goal_contract = _mapping_value(session, "goal_contract")
    execution_policy = _mapping_value(goal_contract, "execution_policy")
    return _learning_uncertain_execution_policy_authorization(execution_policy)


def _learning_review_required_message(readiness_report: Mapping[str, Any]) -> str:
    learning = readiness_report.get("learning_readiness")
    if isinstance(learning, Mapping):
        recommended_next_step = str(learning.get("recommended_next_step", "")).strip()
        if recommended_next_step:
            return recommended_next_step
    return (
        "Auto-improve learning readiness requires explicit review before execution. "
        "Rerun with --allow-learning-uncertain only for a bounded trial."
    )


def build_learning_preflight_decision(
    session: Mapping[str, Any],
    readiness_report: dict[str, Any],
    *,
    allow_learning_uncertain: bool,
) -> LearningPreflightDecision:
    review_required = learning_review_required(readiness_report)
    contract_authorization = _learning_uncertain_contract_authorization(session)
    contract_authorized = bool(contract_authorization["allowed"])
    effective_allow_learning_uncertain = bool(
        allow_learning_uncertain or contract_authorized
    )
    authorization_source = (
        "command_flag"
        if allow_learning_uncertain
        else str(contract_authorization["authorization_source"])
    )
    learning_mode = {
        "allow_learning_uncertain": effective_allow_learning_uncertain,
        "bounded_trial": bool(review_required and effective_allow_learning_uncertain),
        "authorization_source": authorization_source,
        "contract_authorized": contract_authorized,
        "command_flag": str(contract_authorization["command_flag"])
        or ("--allow-learning-uncertain" if allow_learning_uncertain else ""),
    }
    blocked = bool(review_required and not effective_allow_learning_uncertain)
    return LearningPreflightDecision(
        review_required=review_required,
        blocked=blocked,
        learning_mode=learning_mode,
        recommended_next_step=(
            _learning_review_required_message(readiness_report) if blocked else ""
        ),
    )


def apply_learning_preflight_session_fields(
    session: dict[str, Any],
    decision: LearningPreflightDecision,
    *,
    queue_snapshot: list[str],
    pre_run_readiness: dict[str, object],
) -> None:
    session["status"] = "blocked" if decision.blocked else "running"
    session["stop_reason"] = "learning_review_required" if decision.blocked else "running"
    session["queue_snapshot"] = queue_snapshot
    session["learning_mode"] = decision.learning_mode
    session["pre_run_readiness"] = pre_run_readiness
