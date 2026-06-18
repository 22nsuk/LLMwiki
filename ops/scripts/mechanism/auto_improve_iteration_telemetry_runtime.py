from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

SAME_EVAL_REASON_CODES = {
    "candidate_eval_improved",
    "telemetry_discoverability_improved",
    "behavior_delta_digest_added",
    "same_eval_no_secondary_improvement",
    "noop_mutation",
    "insufficient_benchmark_resolution",
    "unknown",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def iteration_behavior_delta_digest(vault: Path, rel_path: str, existing_report: dict[str, Any]) -> str:
    if rel_path:
        path = Path(rel_path)
        if not path.is_absolute():
            digest = sha256_file(vault / path)
            if digest:
                return digest
    existing_digest = existing_report.get("behavior_delta_digest")
    return str(existing_digest).strip() if isinstance(existing_digest, str) else ""


def iteration_same_eval_reason(result: dict[str, Any] | None, existing_report: dict[str, Any]) -> str:
    if isinstance(result, dict):
        for key in ("same_eval_reason", "equal_score_reason"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        decision_record = result.get("decision_record")
        if isinstance(decision_record, dict):
            reason = decision_record.get("same_eval_reason")
            if isinstance(reason, str) and reason.strip():
                return reason.strip()
    existing = existing_report.get("same_eval_reason")
    return str(existing).strip() if isinstance(existing, str) else ""


def _same_eval_contract_source(result: dict[str, Any] | None, existing_report: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        same_eval = result.get("same_eval")
        if isinstance(same_eval, dict):
            return same_eval
    existing = existing_report.get("same_eval")
    return existing if isinstance(existing, dict) else {}


def _normalize_same_eval_reason_code(value: object) -> str:
    text = str(value).strip()
    return text if text in SAME_EVAL_REASON_CODES else "unknown"


def _infer_same_eval_reason_code(
    result: dict[str, Any] | None,
    existing_report: dict[str, Any],
    *,
    reason: str,
    behavior_delta_digest: str,
) -> str:
    contract = _same_eval_contract_source(result, existing_report)
    for source in (contract, result, existing_report):
        if not isinstance(source, dict):
            continue
        code = _normalize_same_eval_reason_code(source.get("same_eval_reason_code"))
        if code != "unknown":
            return code
    if not reason:
        return _normalize_same_eval_reason_code(existing_report.get("same_eval_reason_code"))
    lowered = reason.lower()
    if "noop" in lowered or "no-op" in lowered:
        return "noop_mutation"
    if behavior_delta_digest and ("digest" in lowered or "behavior" in lowered):
        return "behavior_delta_digest_added"
    if "insufficient" in lowered or "resolution" in lowered:
        return "insufficient_benchmark_resolution"
    return "telemetry_discoverability_improved" if behavior_delta_digest else "unknown"


def _secondary_axes_from_text(value: str) -> list[str]:
    for key in ("improved_axes", "selected_axes"):
        marker = f"{key}="
        if marker not in value:
            continue
        tail = value.split(marker, 1)[1].strip()
        if tail.startswith("[") and "]" in tail:
            tail = tail[1 : tail.index("]")]
        else:
            tail = tail.split(",", 1)[0].strip()
        return [
            item.strip().strip("'\"")
            for item in tail.strip("[](){}").split(",")
            if item.strip().strip("'\"")
        ]
    return []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_checks(source: object) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        return []
    checks = source.get("checks")
    if isinstance(checks, list):
        return [item for item in checks if isinstance(item, dict)]
    promotion_report = source.get("promotion_report")
    if isinstance(promotion_report, dict):
        return _extract_checks(promotion_report)
    return []


def _detail_bool_token_present(detail: str, key: str) -> bool:
    return f"{key}=true" in detail.lower()


def _equal_score_secondary_check_is_eligible(check: dict[str, Any]) -> bool:
    status = str(check.get("status", "")).strip().upper()
    if status:
        return status == "PASS"
    detail = str(check.get("detail", ""))
    return all(
        _detail_bool_token_present(detail, key)
        for key in (
            "allowed",
            "score_equal",
            "selected_non_regression",
            "selected_any_improvement",
        )
    )


def _infer_secondary_improvement_axes(
    result: dict[str, Any] | None,
    existing_report: dict[str, Any],
) -> list[str]:
    contract = _same_eval_contract_source(result, existing_report)
    for source in (contract, result, existing_report):
        axes = _string_list(source.get("secondary_improvement_axes")) if isinstance(source, dict) else []
        if axes:
            return axes
    for source in (result, existing_report):
        for check in _extract_checks(source):
            if check.get("id") != "equal_score_secondary_eligibility":
                continue
            detail = str(check.get("detail", ""))
            axes = _secondary_axes_from_text(detail)
            if _equal_score_secondary_check_is_eligible(check) and axes:
                return axes
    return []


def _infer_strict_secondary_improvement_present(
    result: dict[str, Any] | None,
    existing_report: dict[str, Any],
    axes: list[str],
) -> bool:
    contract = _same_eval_contract_source(result, existing_report)
    for source in (contract, result, existing_report):
        if isinstance(source, dict) and isinstance(source.get("strict_secondary_improvement_present"), bool):
            return bool(source["strict_secondary_improvement_present"])
    return bool(axes)


def iteration_same_eval_contract(
    result: dict[str, Any] | None,
    existing_report: dict[str, Any],
    *,
    same_eval_reason: str,
    behavior_delta_digest: str,
) -> dict[str, Any]:
    axes = _infer_secondary_improvement_axes(result, existing_report)
    strict_secondary = _infer_strict_secondary_improvement_present(result, existing_report, axes)
    reason_code = _infer_same_eval_reason_code(
        result,
        existing_report,
        reason=same_eval_reason,
        behavior_delta_digest=behavior_delta_digest,
    )
    return {
        "same_eval_reason_code": reason_code,
        "strict_secondary_improvement_present": strict_secondary,
        "secondary_improvement_axes": axes,
    }
