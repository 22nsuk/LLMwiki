from __future__ import annotations

from typing import Any

from ops.scripts.release.release_authority_vocabulary import (
    REASON_MACHINE_RELEASE_NOT_ALLOWED,
)
from ops.scripts.release.release_evidence_dashboard_render_runtime import (
    CLOSEOUT_PATH,
)
from ops.scripts.release.release_status_v2 import (
    release_status_v2_view_with_readiness_fallback,
)

RELEASE_STATE_CLEAN_PASS = "clean_pass"
RELEASE_STATE_CONDITIONAL_PASS = "conditional_pass"
RELEASE_STATE_BLOCKED = "blocked"
RELEASE_STATE_UNKNOWN = "unknown"


def closeout_input_status(payload: dict[str, Any], load_status: str) -> dict[str, Any]:
    status_view = release_status_v2_view_with_readiness_fallback(payload)
    status = (
        str(status_view["compatibility_status_value"]).strip()
        if load_status == "ok"
        else "unknown"
    )
    release_authority_status = (
        str(status_view["release_authority_status"]).strip() or "unknown"
    )
    semantic_release_status = (
        str(status_view["semantic_release_status"]).strip() or "unknown"
    )
    sealed_release_status = (
        str(status_view["sealed_release_status"]).strip() or "unknown"
    )
    blocker_reason_ids = [str(reason) for reason in status_view["blocker_reason_ids"]]
    used_legacy_fallback_fields = [
        str(field) for field in status_view["used_legacy_fallback_fields"]
    ]
    checked_in_release_ready = bool(payload.get("checked_in_release_ready"))
    conditional_release_ready = bool(payload.get("conditional_release_ready"))
    clean_release_ready = bool(payload.get("clean_release_ready"))
    live_make_check = payload.get("live_make_check")
    live_make_check = live_make_check if isinstance(live_make_check, dict) else {}
    live_make_check_status = (
        str(live_make_check.get("status", "unknown")).strip() or "unknown"
    )
    live_make_check_ready = bool(live_make_check.get("ready", False))
    live_make_check_blocking = bool(
        live_make_check.get("blocking", load_status == "ok")
    )

    if load_status != "ok":
        release_authority_status = RELEASE_STATE_BLOCKED
        semantic_release_status = RELEASE_STATE_BLOCKED
        sealed_release_status = "unknown"
        blocker_reason_ids = []
        used_legacy_fallback_fields = []
        machine_release_allowed = False
        operator_release_allowed = False
        requires_accepted_risk_review = False
    else:
        if release_authority_status == RELEASE_STATE_UNKNOWN:
            if clean_release_ready:
                release_authority_status = RELEASE_STATE_CLEAN_PASS
                semantic_release_status = RELEASE_STATE_CLEAN_PASS
            elif conditional_release_ready:
                release_authority_status = RELEASE_STATE_CONDITIONAL_PASS
                semantic_release_status = RELEASE_STATE_CONDITIONAL_PASS
            elif checked_in_release_ready:
                release_authority_status = RELEASE_STATE_UNKNOWN
            else:
                release_authority_status = RELEASE_STATE_BLOCKED
                semantic_release_status = RELEASE_STATE_BLOCKED
        machine_release_allowed = (
            release_authority_status == RELEASE_STATE_CLEAN_PASS
            and REASON_MACHINE_RELEASE_NOT_ALLOWED not in blocker_reason_ids
        )
        operator_release_allowed = release_authority_status in {
            RELEASE_STATE_CLEAN_PASS,
            RELEASE_STATE_CONDITIONAL_PASS,
        }
        requires_accepted_risk_review = (
            release_authority_status == RELEASE_STATE_CONDITIONAL_PASS
        )

    return {
        "path": CLOSEOUT_PATH,
        "load_status": load_status,
        "status": status,
        "release_readiness_state": release_authority_status,
        "release_authority_status": release_authority_status,
        "semantic_release_status": semantic_release_status,
        "sealed_release_status": sealed_release_status,
        "status_v2_blocker_reason_ids": blocker_reason_ids,
        "status_v2_used_legacy_fallback_fields": used_legacy_fallback_fields,
        "machine_release_allowed": bool(machine_release_allowed),
        "operator_release_allowed": bool(operator_release_allowed),
        "requires_accepted_risk_review": bool(requires_accepted_risk_review),
        "live_make_check_status": live_make_check_status,
        "live_make_check_ready": live_make_check_ready,
        "live_make_check_blocking": live_make_check_blocking,
        "summary": (
            f"release_authority_status={release_authority_status}; "
            f"sealed_release_status={sealed_release_status}; "
            f"machine_release_allowed={bool(machine_release_allowed)}; "
            f"operator_release_allowed={bool(operator_release_allowed)}; "
            f"requires_accepted_risk_review={bool(requires_accepted_risk_review)}; "
            f"live_make_check_status={live_make_check_status}"
        ),
    }


def closeout_decision_gate(closeout_input: dict[str, Any]) -> dict[str, Any]:
    load_status = str(closeout_input.get("load_status", "unknown")).strip() or "unknown"
    state = (
        str(
            closeout_input.get("release_readiness_state", RELEASE_STATE_BLOCKED)
        ).strip()
        or RELEASE_STATE_BLOCKED
    )
    machine_release_allowed = bool(closeout_input.get("machine_release_allowed"))
    operator_release_allowed = bool(closeout_input.get("operator_release_allowed"))
    requires_accepted_risk_review = bool(
        closeout_input.get("requires_accepted_risk_review")
    )
    summary = str(closeout_input.get("summary", "")).strip()
    release_authority_status = str(
        closeout_input.get("release_authority_status", state)
    ).strip() or state
    sealed_release_status = str(
        closeout_input.get("sealed_release_status", "unknown")
    ).strip() or "unknown"

    if load_status != "ok":
        checked_in_state = "fail"
        live_rerun_state = {
            "status": "fail",
            "reason": f"release closeout load_status={load_status}",
        }
        claim_label = "diagnostic_workspace_only"
        next_action = (
            "Regenerate the release closeout summary before relying on the dashboard."
        )
    elif machine_release_allowed:
        checked_in_state = "pass"
        live_rerun_state = {
            "status": "pass",
            "reason": "release closeout machine gate allows release",
        }
        claim_label = "checked_in_json_confirmed"
        next_action = "none"
    elif operator_release_allowed and requires_accepted_risk_review:
        checked_in_state = "attention"
        live_rerun_state = {
            "status": "attention",
            "reason": "release closeout requires accepted-risk operator review before release",
        }
        claim_label = "checked_in_json_confirmed"
        next_action = "Review accepted_risks before operator release signoff."
    else:
        checked_in_state = "fail"
        live_rerun_state = {
            "status": "fail",
            "reason": summary or f"release closeout state is {state}",
        }
        claim_label = "checked_in_json_confirmed"
        next_action = "Resolve release closeout blockers before release."

    return {
        "gate_id": "release_closeout_decision",
        "source_path": CLOSEOUT_PATH,
        "checked_in_state": checked_in_state,
        "live_rerun_state": live_rerun_state,
        "authoritative_for_release": load_status == "ok" and machine_release_allowed,
        "accepted_risk": {"count": 0, "codes": []},
        "owner": "runtime-maintainer",
        "expiry": "",
        "next_action": next_action,
        "required_evidence": [next_action] if next_action != "none" else [],
        "claims": [
            {
                "claim": (
                    "release closeout authoritative decision is "
                    f"release_authority_status={release_authority_status}; "
                    f"sealed_release_status={sealed_release_status}"
                ),
                "provenance_label": claim_label,
            },
            {
                "claim": (
                    "release closeout machine/operator decision is "
                    f"machine_release_allowed={machine_release_allowed}, "
                    f"operator_release_allowed={operator_release_allowed}, "
                    f"requires_accepted_risk_review={requires_accepted_risk_review}"
                ),
                "provenance_label": claim_label,
            },
        ],
    }
