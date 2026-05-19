from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any


PROFILE_ORDER = ("30m_trial", "6h_ramp", "2d_candidate", "5d_sustained")
PROFILE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "30m_trial": {
        "minimum_elapsed_seconds": 1800,
        "minimum_iterations": 1,
        "minimum_successful_iterations": 1,
        "requires_success_then_followup": False,
        "requires_meaningful_maintenance": True,
        "accepted_stop_reasons": ["time_budget_exhausted", "proposal_budget_exhausted"],
        "evidence_paths": [
            "ops/reports/goal-run-status.json",
            "ops/reports/session-synopsis.json",
            "ops/reports/auto-improve-readiness.json",
        ],
        "required_before_next_profile": (
            "bounded 30m one-proposal trial session with repeated runtime maintenance work, "
            "status, audit, synopsis, readiness, and no promotion claim"
        ),
    },
    "6h_ramp": {
        "minimum_elapsed_seconds": 21600,
        "minimum_iterations": 2,
        "minimum_successful_iterations": 1,
        "requires_success_then_followup": True,
        "accepted_stop_reasons": ["time_budget_exhausted"],
        "evidence_paths": [
            "ops/reports/goal-run-status.json",
            "ops/reports/session-synopsis.json",
            "ops/reports/auto-improve-readiness.json",
            "ops/reports/source-package-clean-extract.json",
        ],
        "required_before_next_profile": (
            "30m trial evidence plus repeated 6h improvement session, periodic checkpoint, "
            "and source package replay"
        ),
    },
    "2d_candidate": {
        "minimum_elapsed_seconds": 172800,
        "minimum_iterations": 2,
        "minimum_successful_iterations": 1,
        "requires_success_then_followup": True,
        "accepted_stop_reasons": ["time_budget_exhausted"],
        "evidence_paths": [
            "ops/reports/goal-run-status.json",
            "ops/reports/remediation-backlog.json",
            "ops/reports/source-package-clean-extract.json",
            "ops/reports/public-check-summary.json",
        ],
        "required_before_next_profile": (
            "6h ramp evidence plus repeated 2d improvement session, resume, backoff, "
            "repeated-blocker, and public replay evidence"
        ),
    },
    "5d_sustained": {
        "minimum_elapsed_seconds": 432000,
        "minimum_iterations": 2,
        "minimum_successful_iterations": 1,
        "requires_success_then_followup": True,
        "accepted_stop_reasons": ["time_budget_exhausted"],
        "evidence_paths": [
            "ops/reports/goal-run-status.json",
            "ops/reports/public-check-summary.json",
            "ops/reports/release-closeout-summary.json",
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
        ],
        "required_before_next_profile": (
            "2d candidate evidence plus repeated 5d improvement session and sealed authority clean pass"
        ),
    },
}


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _contract_ladder_descriptions(contract: Mapping[str, Any]) -> dict[str, str]:
    budgets = _mapping_value(contract, "budgets")
    descriptions: dict[str, str] = {}
    for item in budgets.get("profile_ladder", []):
        if not isinstance(item, Mapping):
            continue
        profile = str(item.get("profile", "")).strip()
        description = str(item.get("required_before_next_profile", "")).strip()
        if profile in PROFILE_REQUIREMENTS and description:
            descriptions[profile] = description
    return descriptions


def _verified_profiles(contract: Mapping[str, Any]) -> list[str]:
    runtime_profile = _mapping_value(contract, "runtime_profile")
    seen: set[str] = set()
    verified: list[str] = []
    for profile in _list_text(runtime_profile.get("verified_profiles")):
        if profile in PROFILE_REQUIREMENTS and profile not in seen:
            verified.append(profile)
            seen.add(profile)
    return verified


def _highest_verified_profile(verified_profiles: Sequence[str]) -> str:
    highest = "unverified"
    for profile in PROFILE_ORDER:
        if profile in verified_profiles:
            highest = profile
    return highest


def _next_profile_required(verified_profiles: Sequence[str]) -> str:
    for profile in PROFILE_ORDER:
        if profile not in verified_profiles:
            return profile
    return "none"


def _evidence_paths(vault: Path, profile: str) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for path in PROFILE_REQUIREMENTS[profile]["evidence_paths"]:
        absolute_path = vault / path
        item = {
            "path": path,
            "status": "present" if absolute_path.is_file() else "missing",
        }
        item.update(_report_status_fields(absolute_path))
        evidence.append(item)
    return evidence


def _report_status_fields(path: Path) -> dict[str, str]:
    if not path.is_file() or path.suffix.lower() != ".json":
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"report_status": "unreadable"}
    if not isinstance(payload, Mapping):
        return {"report_status": "unreadable"}
    fields: dict[str, str] = {}
    status = str(payload.get("status", "")).strip()
    if status:
        fields["report_status"] = status
    for key in (
        "preflight_status",
        "distribution_binding_status",
        "authority_preflight_status",
    ):
        value = str(payload.get(key, "")).strip()
        if value:
            fields[key] = value
    return fields


def _profile_verified_by_guard_is_consistent(
    *,
    profile_verified: str,
    verified_profiles: Sequence[str],
) -> bool:
    if profile_verified == "unverified":
        return not verified_profiles
    return profile_verified in verified_profiles


def build_profile_ladder(
    vault: Path,
    *,
    contract: Mapping[str, Any],
    run_profile: str,
) -> dict[str, Any]:
    runtime_profile = _mapping_value(contract, "runtime_profile")
    promotion_guard = _mapping_value(contract, "promotion_guard")
    descriptions = _contract_ladder_descriptions(contract)
    verified_profiles = _verified_profiles(contract)
    verified_set = set(verified_profiles)
    highest_verified = _highest_verified_profile(verified_profiles)
    profile_verified = str(promotion_guard.get("profile_verified", "unverified")).strip() or "unverified"
    profile_guard_consistent = _profile_verified_by_guard_is_consistent(
        profile_verified=profile_verified,
        verified_profiles=verified_profiles,
    )
    profiles = [
        {
            "profile": profile,
            "minimum_elapsed_seconds": int(PROFILE_REQUIREMENTS[profile]["minimum_elapsed_seconds"]),
            "verified": profile in verified_set,
            "active": profile == run_profile,
            "required_before_next_profile": descriptions.get(
                profile,
                str(PROFILE_REQUIREMENTS[profile]["required_before_next_profile"]),
            ),
            "evidence_paths": _evidence_paths(vault, profile),
        }
        for profile in PROFILE_ORDER
    ]
    complete = all(item["verified"] for item in profiles)
    sealed_authority_clean = bool(promotion_guard.get("sealed_authority_clean", False))
    can_promote_result = bool(promotion_guard.get("can_promote_result", False))
    sustained_claim_allowed = (
        complete
        and profile_verified == "5d_sustained"
        and sealed_authority_clean
        and can_promote_result
    )
    if not profile_guard_consistent:
        status = "inconsistent"
    elif complete:
        status = "complete"
    else:
        status = "incomplete"
    return {
        "status": status,
        "current_profile": str(runtime_profile.get("current_profile") or run_profile),
        "run_profile": run_profile,
        "verified_profiles": verified_profiles,
        "highest_verified_profile": highest_verified,
        "next_profile_required": _next_profile_required(verified_profiles),
        "profile_verified_by_promotion_guard": profile_verified,
        "profile_guard_consistent": profile_guard_consistent,
        "sustained_claim_allowed": sustained_claim_allowed,
        "profiles": profiles,
    }


def profile_ladder_blockers(profile_ladder: Mapping[str, Any]) -> list[str]:
    if profile_ladder.get("status") == "inconsistent":
        return ["profile ladder inconsistent"]
    if profile_ladder.get("status") != "complete":
        return ["profile ladder incomplete"]
    if not bool(profile_ladder.get("sustained_claim_allowed", False)):
        return ["sustained runtime claim not allowed"]
    return []
