from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_MODE = "self_improvement_loop"
RUNTIME_MODES = (DEFAULT_RUNTIME_MODE,)
DEFAULT_RUNTIME_SECONDS = 21600
FULL_GATE_EVIDENCE_IDS = (
    "auto_improve_readiness",
    "goal_run_status",
    "session_synopsis",
    "remediation_backlog",
    "source_package_clean_extract",
    "public_check_summary",
    "release_authority",
    "goal_worktree_guard",
)
SESSION_REQUIREMENTS: dict[str, Any] = {
    "accepted_stop_reasons": ["time_budget_exhausted", "proposal_budget_exhausted"],
    "minimum_iteration_count": 1,
    "minimum_successful_iteration_count": 1,
    "requires_success_then_followup": False,
    "requires_meaningful_maintenance": True,
}


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _list_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _runtime_config(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping_value(contract, "runtime")


def runtime_mode(contract: Mapping[str, Any], fallback: str = DEFAULT_RUNTIME_MODE) -> str:
    runtime = _runtime_config(contract)
    mode = str(runtime.get("mode", "")).strip()
    return mode or fallback


def runtime_duration_seconds(contract: Mapping[str, Any]) -> int:
    runtime = _runtime_config(contract)
    budgets = _mapping_value(contract, "budgets")
    value = runtime.get("duration_seconds")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        value = runtime.get("max_unattended_seconds")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        value = budgets.get("max_wall_clock_seconds")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else DEFAULT_RUNTIME_SECONDS


def runtime_certificate_status(contract: Mapping[str, Any]) -> str:
    runtime = _runtime_config(contract)
    status = str(runtime.get("certificate_status", "")).strip()
    return status if status in {"unverified", "verified"} else "unverified"


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


def required_evidence_paths(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    paths: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in contract.get("required_evidence", []):
        if not isinstance(item, Mapping) or not bool(item.get("required_for_promotion", False)):
            continue
        evidence_id = str(item.get("evidence_id", "")).strip()
        path = str(item.get("path", "")).strip()
        if not path or path in seen:
            continue
        paths.append({"evidence_id": evidence_id, "path": path})
        seen.add(path)
    return paths


def evidence_statuses(vault: Path, contract: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for item in required_evidence_paths(contract):
        absolute_path = vault / item["path"]
        status = {
            **item,
            "status": "present" if absolute_path.is_file() else "missing",
        }
        status.update(_report_status_fields(absolute_path))
        evidence.append(status)
    return evidence


def build_runtime_certificate(
    vault: Path,
    *,
    contract: Mapping[str, Any],
    run_mode: str,
) -> dict[str, Any]:
    promotion_guard = _mapping_value(contract, "promotion_guard")
    configured_mode = runtime_mode(contract, fallback=run_mode)
    evidence = evidence_statuses(vault, contract)
    missing_evidence = [item for item in evidence if item.get("status") != "present"]
    promotion_blockers = _list_text(promotion_guard.get("promotion_blockers"))
    can_promote_result = bool(promotion_guard.get("can_promote_result", False))
    sealed_authority_clean = bool(promotion_guard.get("sealed_authority_clean", False))
    certificate_status = runtime_certificate_status(contract)
    mode_consistent = run_mode == configured_mode
    full_gate_clean = (
        not missing_evidence
        and can_promote_result
        and sealed_authority_clean
        and not promotion_blockers
    )
    if not mode_consistent:
        status = "inconsistent"
    elif certificate_status == "verified" and full_gate_clean:
        status = "complete"
    else:
        status = "pending"
    return {
        "status": status,
        "mode": configured_mode,
        "run_mode": run_mode,
        "duration_seconds": runtime_duration_seconds(contract),
        "certificate_status": certificate_status,
        "mode_consistent": mode_consistent,
        "full_gate_clean": full_gate_clean,
        "can_promote_result": can_promote_result,
        "sealed_authority_clean": sealed_authority_clean,
        "promotion_blockers": promotion_blockers,
        "required_evidence": evidence,
        "missing_evidence": missing_evidence,
    }


def runtime_certificate_blockers(certificate: Mapping[str, Any]) -> list[str]:
    if certificate.get("status") == "inconsistent":
        return ["self-improvement loop certificate inconsistent"]
    if certificate.get("status") != "complete":
        return ["self-improvement loop certificate incomplete"]
    return []
