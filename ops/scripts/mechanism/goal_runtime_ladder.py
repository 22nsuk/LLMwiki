from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PENDING_CHECKPOINT = "__pending_checkpoint__"
PROFILE_EVIDENCE_STATUSES = {
    "pending",
    "running",
    "incomplete",
    "sampled",
    "verified",
    "blocked",
}


def ladder_order(contract: Mapping[str, Any]) -> list[str]:
    order: list[str] = []
    for item in contract.get("execution_ladder", []):
        if not isinstance(item, Mapping):
            continue
        profile = str(item.get("profile", "")).strip()
        if profile and profile not in order:
            order.append(profile)
    return order


def _default_evidence(profile: str) -> dict[str, str]:
    return {
        "profile": profile,
        "status": "pending",
        "started_at": "",
        "verified_at": "",
        "checkpoint": "",
        "session_report": "",
        "stop_reason": "",
        "detail": "",
    }


def _normalized_evidence(profile: str, value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return _default_evidence(profile)
    record = _default_evidence(profile)
    status = str(value.get("status", "")).strip()
    if status in PROFILE_EVIDENCE_STATUSES:
        record["status"] = status
    for key in (
        "started_at",
        "verified_at",
        "checkpoint",
        "session_report",
        "stop_reason",
        "detail",
    ):
        record[key] = str(value.get(key, "")).strip()
    return record


def _existing_evidence(existing_status: Mapping[str, Any] | None) -> Mapping[str, object]:
    if not isinstance(existing_status, Mapping):
        return {}
    verification = existing_status.get("profile_verification")
    if not isinstance(verification, Mapping):
        return {}
    evidence = verification.get("evidence")
    if not isinstance(evidence, Mapping):
        return {}
    return evidence


def _refresh_summary(verification: dict[str, Any]) -> dict[str, Any]:
    order = [str(item) for item in verification.get("ladder_order", []) if str(item)]
    active_profile = str(verification.get("active_profile", "")).strip()
    evidence = verification.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
        verification["evidence"] = evidence
    for profile in order:
        evidence[profile] = _normalized_evidence(profile, evidence.get(profile))

    if active_profile and active_profile not in order:
        order.append(active_profile)
        evidence[active_profile] = _normalized_evidence(
            active_profile,
            evidence.get(active_profile),
        )
        verification["ladder_order"] = order

    active_index = order.index(active_profile) if active_profile in order else len(order)
    required_predecessors = order[:active_index]
    missing_predecessors = [
        profile
        for profile in required_predecessors
        if evidence.get(profile, {}).get("status") != "verified"
    ]
    verified_profiles = [
        profile for profile in order if evidence.get(profile, {}).get("status") == "verified"
    ]
    sustained_profile = order[-1] if order else active_profile
    sustained_profile_verified = (
        bool(sustained_profile)
        and evidence.get(sustained_profile, {}).get("status") == "verified"
    )
    current_profile_verified = (
        bool(active_profile)
        and evidence.get(active_profile, {}).get("status") == "verified"
    )
    verification.update(
        {
            "required_predecessors": required_predecessors,
            "missing_predecessors": missing_predecessors,
            "required_predecessors_verified": not missing_predecessors,
            "verified_profiles": verified_profiles,
            "sustained_profile": sustained_profile,
            "sustained_profile_verified": sustained_profile_verified,
            "current_profile_verified": current_profile_verified,
            "sustainability_claim_allowed": sustained_profile_verified,
            "claim_blocker": ""
            if sustained_profile_verified
            else (
                f"{sustained_profile} profile has not been verified by full-duration evidence"
                if sustained_profile
                else "goal execution ladder is empty"
            ),
        }
    )
    return verification


def build_profile_verification(
    contract: Mapping[str, Any],
    *,
    active_profile: str,
    existing_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    order = ladder_order(contract)
    if active_profile and active_profile not in order:
        order.append(active_profile)
    existing = _existing_evidence(existing_status)
    evidence = {
        profile: _normalized_evidence(profile, existing.get(profile))
        for profile in order
    }
    return _refresh_summary(
        {
            "active_profile": active_profile,
            "ladder_order": order,
            "required_predecessors": [],
            "missing_predecessors": [],
            "required_predecessors_verified": False,
            "verified_profiles": [],
            "sustained_profile": order[-1] if order else active_profile,
            "sustained_profile_verified": False,
            "current_profile_verified": False,
            "sustainability_claim_allowed": False,
            "claim_blocker": "",
            "evidence": evidence,
        }
    )


def mark_profile_running(
    verification: dict[str, Any],
    *,
    active_profile: str,
    started_at: str,
) -> dict[str, Any]:
    evidence = verification.setdefault("evidence", {})
    record = _normalized_evidence(active_profile, evidence.get(active_profile))
    if record["status"] != "verified":
        record["status"] = "running"
        record["started_at"] = started_at
        record["detail"] = "profile execution started; full-duration evidence is not complete"
    evidence[active_profile] = record
    verification["active_profile"] = active_profile
    return _refresh_summary(verification)


def mark_profile_result(
    verification: dict[str, Any],
    *,
    active_profile: str,
    status: str,
    observed_at: str,
    checkpoint: str,
    session_report: str,
    stop_reason: str,
    detail: str,
) -> dict[str, Any]:
    if status not in PROFILE_EVIDENCE_STATUSES:
        raise ValueError(f"unknown profile evidence status: {status}")
    evidence = verification.setdefault("evidence", {})
    record = _normalized_evidence(active_profile, evidence.get(active_profile))
    record["status"] = status
    if status == "verified":
        record["verified_at"] = observed_at
    elif status == "running":
        record["started_at"] = observed_at
    record["checkpoint"] = checkpoint
    record["session_report"] = session_report
    record["stop_reason"] = stop_reason
    record["detail"] = detail
    evidence[active_profile] = record
    verification["active_profile"] = active_profile
    return _refresh_summary(verification)


def profile_prerequisite_blocker(verification: Mapping[str, Any]) -> str | None:
    if bool(verification.get("required_predecessors_verified", False)):
        return None
    active_profile = str(verification.get("active_profile", "")).strip() or "unknown"
    missing = [
        str(item)
        for item in verification.get("missing_predecessors", [])
        if str(item).strip()
    ]
    if not missing:
        return f"profile={active_profile} has unverified predecessor evidence"
    return (
        f"profile={active_profile} requires verified predecessor profile(s): "
        + ", ".join(missing)
    )


def attach_pending_checkpoint(verification: dict[str, Any], checkpoint: str) -> dict[str, Any]:
    evidence = verification.get("evidence")
    if not isinstance(evidence, dict):
        return verification
    for record in evidence.values():
        if isinstance(record, dict) and record.get("checkpoint") == PENDING_CHECKPOINT:
            record["checkpoint"] = checkpoint
    return verification
