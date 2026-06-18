from __future__ import annotations

from ops.scripts.core.rule_registry_runtime import (
    RuleSpec,
    collapse_rule_decision_contract,
    configured_rule_ids,
    evaluate_rule_registry,
)

from .promotion_gate_mechanism_report_runtime import assemble_mechanism_promotion_report
from .promotion_gate_mechanism_state_runtime import MechanismGateInputs


def finalize_mechanism_promotion_report(
    *,
    run_id: str,
    artifact_class: str,
    policy: dict,
    primary_targets: list[str],
    supporting_targets: list[str],
    signoff: dict,
    log: dict,
    inputs: MechanismGateInputs,
    available_rules: dict[str, RuleSpec],
) -> dict:
    ordered_rule_ids = configured_rule_ids(policy, "system_mechanism")
    checks, triggered_decisions = evaluate_rule_registry(ordered_rule_ids, available_rules)
    decision_contract = collapse_rule_decision_contract(
        triggered_decisions,
        subject_id=run_id,
        subject_kind=artifact_class,
        policy_version=policy.get("version"),
        source_pass="system_mechanism",
        signoff=signoff,
    )
    return assemble_mechanism_promotion_report(
        run_id=run_id,
        artifact_class=artifact_class,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        signoff=signoff,
        log=log,
        inputs=inputs,
        checks=checks,
        decision=decision_contract["decision"],
        decision_record=decision_contract["decision_record"],
        decision_reduction=decision_contract["decision_reduction"],
    )
