from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ops.scripts.promotion_gate_common_runtime import PromotionGatePolicyError

from .promotion_decision_registry_runtime import (
    reduce_decision_proposals,
    validate_promotion_decision,
)

RuleDecision = str | None


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    build_checks: Callable[[], list[dict]]
    reduce_decision: Callable[[list[dict]], RuleDecision] | None = None
    metadata: RuleMetadata | None = None


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    artifact_dependencies: tuple[str, ...]
    reducer: str
    severity: str
    summary_template: str


def single_check_rule(
    rule_id: str,
    build_check: Callable[[], dict],
    *,
    reduce_decision: Callable[[list[dict]], RuleDecision] | None = None,
    metadata: RuleMetadata | None = None,
) -> RuleSpec:
    return RuleSpec(
        rule_id=rule_id,
        build_checks=lambda: [build_check()],
        reduce_decision=reduce_decision,
        metadata=metadata,
    )


def status_rule_reducer(
    *,
    fail: RuleDecision = None,
    warn: RuleDecision = None,
    ok: RuleDecision = None,
) -> Callable[[list[dict]], RuleDecision]:
    def reducer(checks: list[dict]) -> RuleDecision:
        statuses = {check.get("status") for check in checks}
        if "FAIL" in statuses:
            return fail
        if "WARN" in statuses:
            return warn
        return ok

    return reducer


def configured_rule_ids(policy: dict, registry_name: str) -> list[str]:
    try:
        configured = policy["promotion_policy"]["rule_registry"][registry_name]
    except KeyError as exc:
        raise PromotionGatePolicyError(
            f"missing promotion rule registry configuration: {registry_name}"
        ) from exc
    if not isinstance(configured, list) or not configured:
        raise PromotionGatePolicyError(
            f"promotion rule registry '{registry_name}' must be a non-empty list"
        )

    ordered: list[str] = []
    seen: set[str] = set()
    for raw_rule_id in configured:
        if not isinstance(raw_rule_id, str) or not raw_rule_id.strip():
            raise PromotionGatePolicyError(
                f"promotion rule registry '{registry_name}' contains an invalid rule id"
            )
        rule_id = raw_rule_id.strip()
        if rule_id in seen:
            continue
        seen.add(rule_id)
        ordered.append(rule_id)
    return ordered


def configured_rule_metadata(policy: dict, registry_name: str) -> dict[str, RuleMetadata]:
    raw_metadata = (
        policy.get("promotion_policy", {})
        .get("rule_metadata", {})
        .get(registry_name, {})
    )
    if not isinstance(raw_metadata, dict):
        raise PromotionGatePolicyError(
            f"promotion rule metadata '{registry_name}' must be a mapping"
        )

    metadata: dict[str, RuleMetadata] = {}
    for rule_id, item in raw_metadata.items():
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise PromotionGatePolicyError(
                f"promotion rule metadata '{registry_name}' contains an invalid rule id"
            )
        if not isinstance(item, dict):
            raise PromotionGatePolicyError(
                f"promotion rule metadata '{registry_name}.{rule_id}' must be a mapping"
            )
        metadata[rule_id] = RuleMetadata(
            rule_id=rule_id,
            artifact_dependencies=tuple(str(dep) for dep in item["artifact_dependencies"]),
            reducer=str(item["reducer"]),
            severity=str(item["severity"]),
            summary_template=str(item["summary_template"]),
        )
    return metadata


def _check_evidence_ref(check: dict, fallback: str) -> str:
    return str(check.get("id") or check.get("check") or fallback)


def _default_rule_summary(rule_id: str, checks: list[dict]) -> str:
    return "; ".join(
        f"{check.get('id', rule_id)}={check.get('status', '')}: {check.get('detail', '')}"
        for check in checks
        if isinstance(check, dict)
    )


def _metadata_rule_summary(metadata: RuleMetadata, checks: list[dict]) -> str:
    evidence_refs = [
        _check_evidence_ref(check, metadata.rule_id)
        for check in checks
        if isinstance(check, dict)
    ]
    statuses = ", ".join(
        str(check.get("status", ""))
        for check in checks
        if isinstance(check, dict)
    )
    details = "; ".join(
        f"{_check_evidence_ref(check, metadata.rule_id)}={check.get('status', '')}: "
        f"{check.get('detail', '')}"
        for check in checks
        if isinstance(check, dict)
    )
    try:
        return metadata.summary_template.format(
            rule_id=metadata.rule_id,
            severity=metadata.severity,
            reducer=metadata.reducer,
            artifact_dependencies=", ".join(metadata.artifact_dependencies),
            evidence_refs=", ".join(evidence_refs),
            statuses=statuses,
            details=details,
        )
    except (KeyError, IndexError, ValueError):
        return _default_rule_summary(metadata.rule_id, checks)


def evaluate_rule_registry(
    rule_ids: list[str],
    registry: dict[str, RuleSpec],
) -> tuple[list[dict], list[dict]]:
    checks: list[dict] = []
    triggered_decisions: list[dict] = []
    for rule_id in rule_ids:
        spec = registry.get(rule_id)
        if spec is None:
            raise PromotionGatePolicyError(
                f"promotion rule registry references unknown rule id: {rule_id}"
            )
        rule_checks = spec.build_checks()
        if not isinstance(rule_checks, list) or not rule_checks:
            raise PromotionGatePolicyError(
                f"promotion rule '{rule_id}' must emit at least one check"
            )
        checks.extend(rule_checks)
        if spec.reduce_decision is None:
            continue
        decision = spec.reduce_decision(rule_checks)
        if decision is None:
            continue
        try:
            decision = validate_promotion_decision(decision)
        except ValueError as exc:
            raise PromotionGatePolicyError(
                f"promotion rule '{rule_id}' returned unsupported decision: {decision}"
            ) from exc
        evidence_refs = [
            _check_evidence_ref(check, rule_id)
            for check in rule_checks
            if isinstance(check, dict) and _check_evidence_ref(check, rule_id)
        ]
        reason_detail = (
            _metadata_rule_summary(spec.metadata, rule_checks)
            if spec.metadata is not None
            else _default_rule_summary(rule_id, rule_checks)
        )
        triggered_decisions.append(
            {
                "rule_id": rule_id,
                "decision": decision,
                "source_rule": rule_id,
                "reason_code": rule_id,
                "reason_detail": reason_detail,
                "evidence_refs": evidence_refs,
            }
        )
    return checks, triggered_decisions


def collapse_rule_decision_contract(
    triggered_decisions: list[dict],
    *,
    subject_id: str,
    subject_kind: str,
    policy_version: int | None,
    source_pass: str,
    signoff: dict | None = None,
    default: str = "PROMOTE",
) -> dict:
    return reduce_decision_proposals(
        triggered_decisions,
        subject_id=subject_id,
        subject_kind=subject_kind,
        policy_version=policy_version,
        source_pass=source_pass,
        signoff=signoff,
        default=default,
    )


def collapse_rule_decisions(
    triggered_decisions: list[dict],
    *,
    default: str = "PROMOTE",
) -> str:
    contract = collapse_rule_decision_contract(
        triggered_decisions,
        subject_id="compat",
        subject_kind="unknown",
        policy_version=0,
        source_pass="compat",
        default=default,
    )
    return str(contract["decision"])
