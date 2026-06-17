from __future__ import annotations

from typing import Any

from ops.scripts.core.gate_effect_vocabulary import GATE_EFFECT_BLOCKS_PROMOTION
from ops.scripts.core.payload_field_runtime import dict_field


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def remediation_backlog_summary(
    payload: dict[str, Any],
    *,
    remediation_backlog_path: str,
) -> dict[str, Any]:
    if not payload:
        return {
            "path": remediation_backlog_path,
            "expected_artifact_kind": "remediation_backlog",
            "artifact_kind": "",
            "status": "fail",
            "source_status": "missing",
            "release_blocking": True,
            "open_total_count": 0,
            "open_promotion_count": 0,
            "open_repeat_count": 0,
            "active_blocker_count": 0,
            "blocking_item_count": 0,
            "signal_ids": ["remediation_backlog_missing"],
            "summary": "remediation backlog report is missing",
        }

    summary = dict_field(payload, "summary")
    summary_open_total_count = _int_value(summary.get("open_total_count"))
    summary_open_promotion_count = _int_value(summary.get("open_promotion_count"))
    summary_open_repeat_count = _int_value(summary.get("open_repeat_count"))
    summary_active_blocker_count = _int_value(summary.get("active_blocker_count"))

    blocking_signal_ids: list[str] = []
    item_open_total_count = 0
    item_open_promotion_count = 0
    item_open_repeat_count = 0
    items = payload.get("items", [])
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "")).strip() != "open":
                continue
            item_open_total_count += 1
            severity = str(item.get("severity", "")).strip()
            if severity == "blocks_repeat":
                item_open_repeat_count += 1
            if severity != "blocks_promotion":
                continue
            item_open_promotion_count += 1
            blocker_id = str(item.get("blocker_id", "")).strip()
            if blocker_id:
                blocking_signal_ids.append(blocker_id)

    open_total_count = max(summary_open_total_count, item_open_total_count)
    open_promotion_count = max(summary_open_promotion_count, item_open_promotion_count)
    open_repeat_count = max(summary_open_repeat_count, item_open_repeat_count)
    active_blocker_count = max(summary_active_blocker_count, item_open_promotion_count)
    blocking_signal_ids = list(dict.fromkeys(blocking_signal_ids))
    report_status = str(payload.get("status", "")).strip() or "unknown"
    release_blocking = open_promotion_count > 0 or bool(blocking_signal_ids)
    signal_ids = blocking_signal_ids or (
        ["remediation_backlog_open"] if release_blocking else []
    )
    return {
        "path": remediation_backlog_path,
        "expected_artifact_kind": "remediation_backlog",
        "artifact_kind": str(payload.get("artifact_kind", "")).strip(),
        "status": "fail" if release_blocking else "pass",
        "source_status": report_status if release_blocking else "pass",
        "release_blocking": release_blocking,
        "open_total_count": open_total_count,
        "open_promotion_count": open_promotion_count,
        "open_repeat_count": open_repeat_count,
        "active_blocker_count": active_blocker_count,
        "blocking_item_count": len(blocking_signal_ids),
        "signal_ids": signal_ids,
        "currentness_status": str(dict_field(payload, "currentness").get("status", "")).strip(),
        "summary": (
            "remediation backlog "
            f"status={report_status}; open_total_count={open_total_count}; "
            f"open_promotion_count={open_promotion_count}; "
            f"open_repeat_count={open_repeat_count}; "
            f"blocking_item_count={len(blocking_signal_ids)}"
        ),
    }


def remediation_backlog_promotion_blockers(
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    if not bool(summary.get("release_blocking", False)):
        return []
    signal_ids = _string_list(summary.get("signal_ids")) or [
        "remediation_backlog_not_clear"
    ]
    return [
        {
            "id": "promotion_blocked_by_remediation_backlog_open",
            "scope": "remediation_backlog",
            "status": "open",
            "severity": "blocker",
            "accepted_risk": False,
            "gate_effect": GATE_EFFECT_BLOCKS_PROMOTION,
            "source_status": str(summary.get("source_status", "")).strip() or "open",
            "reason": (
                "remediation backlog is not clear for promotion: "
                f"{str(summary.get('summary', '')).strip() or 'summary unavailable'}"
            ),
            "signal_ids": signal_ids,
            "required_evidence": [
                "Run make remediation-backlog and confirm open_promotion_count=0.",
                "Close or explicitly defer blocks_promotion backlog items before promotion.",
                "can_promote_result must stay false while remediation backlog items are open.",
            ],
            "recommended_next_step": (
                "Close or explicitly defer remediation backlog items, rerun make remediation-backlog, "
                "then rerun make auto-improve-readiness."
            ),
        }
    ]
