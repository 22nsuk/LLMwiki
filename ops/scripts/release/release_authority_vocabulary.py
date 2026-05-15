from __future__ import annotations

from typing import Any


OPERATOR_SUMMARY_PARSER_ID = "release_authority_operator_summary_v1"

RELEASE_AUTHORITY_CLEAN_PASS = "clean_pass"
RELEASE_AUTHORITY_CONDITIONAL_PASS = "conditional_pass"
RELEASE_AUTHORITY_BLOCKED = "blocked"
RELEASE_AUTHORITY_UNKNOWN = "unknown"

SEALED_RELEASE_CLEAN_PASS = "sealed_clean_pass"
SEALED_RELEASE_CONDITIONAL_PASS = "sealed_conditional_pass"

REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS = "release_authority_not_clean_pass"
REASON_MACHINE_RELEASE_NOT_ALLOWED = "machine_release_not_allowed"
REASON_SEALED_RELEASE_NOT_CLEAN_PASS = "sealed_release_not_clean_pass"
REASON_DISTRIBUTION_PACKAGE_NOT_MATERIALIZED = "distribution_package_not_materialized"
REASON_ARTIFACT_INVENTORY_NOT_CURRENT = "artifact_inventory_not_current"

LEGACY_SEALED_REHEARSAL_FAILURE_REASONS = {
    "batch_release_authority_not_clean_pass": REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS,
    "batch_sealed_release_not_clean_pass": REASON_SEALED_RELEASE_NOT_CLEAN_PASS,
}

OPERATOR_SUMMARY_FIELDS = (
    "release_authority_status",
    "semantic_release_status",
    "sealed_release_status",
    "machine_release_allowed",
    "clean_release_ready",
    "batch_integrity_status",
    "distribution_package_status",
    "authority_reason_ids",
    "sealed_reason_ids",
    "blocker_reason_ids",
)
OPERATOR_SUMMARY_BOOL_FIELDS = {
    "machine_release_allowed",
    "clean_release_ready",
}
OPERATOR_SUMMARY_LIST_FIELDS = {
    "authority_reason_ids",
    "sealed_reason_ids",
    "blocker_reason_ids",
}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def release_authority_reason_ids(
    *,
    release_authority_status: str,
    machine_release_allowed: bool,
) -> list[str]:
    reasons: list[str] = []
    if release_authority_status != RELEASE_AUTHORITY_CLEAN_PASS:
        reasons.append(REASON_RELEASE_AUTHORITY_NOT_CLEAN_PASS)
    if not machine_release_allowed:
        reasons.append(REASON_MACHINE_RELEASE_NOT_ALLOWED)
    return _unique(reasons)


def sealed_release_reason_ids(
    *,
    sealed_release_status: str,
    distribution_package_status: str,
    batch_integrity_status: str,
) -> list[str]:
    reasons: list[str] = []
    if sealed_release_status != SEALED_RELEASE_CLEAN_PASS:
        reasons.append(REASON_SEALED_RELEASE_NOT_CLEAN_PASS)
    if distribution_package_status != "materialized":
        reasons.append(REASON_DISTRIBUTION_PACKAGE_NOT_MATERIALIZED)
    if batch_integrity_status != "pass":
        reasons.append(REASON_ARTIFACT_INVENTORY_NOT_CURRENT)
    return _unique(reasons)


def _format_summary_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        values = [str(item) for item in value if str(item)]
        return ",".join(values) if values else "none"
    return str(value)


def _parse_summary_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _parse_summary_list(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped or stripped == "none":
        return []
    return [item.strip() for item in stripped.split(",") if item.strip()]


def _release_authority_decision_fields(
    *,
    release_authority_status: str,
    semantic_release_status: str,
    sealed_release_status: str,
    machine_release_allowed: bool,
    clean_release_ready: bool,
    batch_integrity_status: str,
    distribution_package_status: str,
    authority_reason_ids: list[str],
    sealed_reason_ids: list[str],
    blocker_reason_ids: list[str],
) -> dict[str, Any]:
    return {
        "release_authority_status": release_authority_status,
        "semantic_release_status": semantic_release_status,
        "sealed_release_status": sealed_release_status,
        "machine_release_allowed": machine_release_allowed,
        "clean_release_ready": clean_release_ready,
        "batch_integrity_status": batch_integrity_status,
        "distribution_package_status": distribution_package_status,
        "authority_reason_ids": authority_reason_ids,
        "sealed_reason_ids": sealed_reason_ids,
        "blocker_reason_ids": blocker_reason_ids,
    }


def release_authority_operator_summary(decision_fields: dict[str, Any]) -> str:
    return "; ".join(
        f"{field}={_format_summary_value(decision_fields.get(field, ''))}"
        for field in OPERATOR_SUMMARY_FIELDS
    )


def parse_release_authority_operator_summary(summary: str) -> dict[str, Any]:
    raw_fields: dict[str, str] = {}
    for segment in summary.split(";"):
        token = segment.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        raw_fields[key.strip()] = value.strip()

    parsed: dict[str, Any] = {}
    for field in OPERATOR_SUMMARY_FIELDS:
        raw_value = raw_fields.get(field, "")
        if field in OPERATOR_SUMMARY_BOOL_FIELDS:
            parsed[field] = _parse_summary_bool(raw_value)
        elif field in OPERATOR_SUMMARY_LIST_FIELDS:
            parsed[field] = _parse_summary_list(raw_value)
        else:
            parsed[field] = raw_value
    return parsed


def release_authority_operator_summary_round_trip(
    *,
    operator_summary: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    parsed = parse_release_authority_operator_summary(operator_summary)
    mismatches: list[dict[str, str]] = []
    for field in OPERATOR_SUMMARY_FIELDS:
        expected_value = expected.get(field)
        parsed_value = parsed.get(field)
        if parsed_value != expected_value:
            mismatches.append(
                {
                    "field": field,
                    "expected": _format_summary_value(expected_value),
                    "actual": _format_summary_value(parsed_value),
                }
            )

    return {
        "status": "pass" if not mismatches else "fail",
        "parser": OPERATOR_SUMMARY_PARSER_ID,
        "expected": expected,
        "parsed": parsed,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def release_authority_vocabulary_payload(
    *,
    release_authority_status: str,
    semantic_release_status: str,
    sealed_release_status: str,
    machine_release_allowed: bool,
    clean_release_ready: bool,
    batch_integrity_status: str,
    distribution_package: dict[str, Any],
) -> dict[str, Any]:
    distribution_status = str(distribution_package.get("status", "")).strip() or "unknown"
    authority_reasons = release_authority_reason_ids(
        release_authority_status=release_authority_status,
        machine_release_allowed=machine_release_allowed,
    )
    sealed_reasons = sealed_release_reason_ids(
        sealed_release_status=sealed_release_status,
        distribution_package_status=distribution_status,
        batch_integrity_status=batch_integrity_status,
    )
    blocker_reasons = _unique([*authority_reasons, *sealed_reasons])
    decision_fields = _release_authority_decision_fields(
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        machine_release_allowed=machine_release_allowed,
        clean_release_ready=clean_release_ready,
        batch_integrity_status=batch_integrity_status,
        distribution_package_status=distribution_status,
        authority_reason_ids=authority_reasons,
        sealed_reason_ids=sealed_reasons,
        blocker_reason_ids=blocker_reasons,
    )
    operator_summary = release_authority_operator_summary(decision_fields)
    return {
        "schema_version": 1,
        "release_authority_status": release_authority_status,
        "semantic_release_status": semantic_release_status,
        "sealed_release_status": sealed_release_status,
        "machine_release_allowed": machine_release_allowed,
        "clean_release_ready": clean_release_ready,
        "batch_integrity_status": batch_integrity_status,
        "distribution_package_status": distribution_status,
        "authority_reason_ids": authority_reasons,
        "sealed_reason_ids": sealed_reasons,
        "blocker_reason_ids": blocker_reasons,
        "operator_summary": operator_summary,
        "operator_summary_round_trip": release_authority_operator_summary_round_trip(
            operator_summary=operator_summary,
            expected=decision_fields,
        ),
        "summary": (
            "release authority and sealed distribution use shared reason ids; "
            f"blocker_reason_count={len(blocker_reasons)}"
        ),
    }


def legacy_sealed_rehearsal_reason_id(failure_id: str) -> str:
    return LEGACY_SEALED_REHEARSAL_FAILURE_REASONS.get(failure_id, failure_id)
