from __future__ import annotations

from typing import Any

from ops.scripts.core.payload_field_runtime import dict_field
from ops.scripts.gate_effect_vocabulary import GATE_EFFECT_BLOCKS_PROMOTION

from .auto_improve_readiness_constants_runtime import (
    GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _goal_worktree_guard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "path": GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
            "artifact_kind": "",
            "status": "not_run",
            "requested_mode": "unknown",
            "detected_mode": "unknown",
            "can_execute_goal_runtime": False,
            "can_promote_result": False,
            "zip_mode_replay_only": False,
            "dirty_entry_count": 0,
            "fatal_blockers": ["goal_worktree_guard_missing"],
            "promotion_blockers": ["goal_worktree_guard_missing"],
            "summary": "goal worktree guard report is missing or unusable",
        }

    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if artifact_kind != "goal_worktree_guard":
        return {
            "path": GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
            "artifact_kind": artifact_kind,
            "status": "fail",
            "requested_mode": str(payload.get("requested_mode", "")).strip() or "unknown",
            "detected_mode": str(payload.get("detected_mode", "")).strip() or "unknown",
            "can_execute_goal_runtime": False,
            "can_promote_result": False,
            "zip_mode_replay_only": False,
            "dirty_entry_count": 0,
            "fatal_blockers": ["goal_worktree_guard_invalid"],
            "promotion_blockers": ["goal_worktree_guard_invalid"],
            "summary": (
                "goal worktree guard artifact_kind="
                f"{artifact_kind or '<missing>'}; expected goal_worktree_guard"
            ),
        }

    decisions = dict_field(payload, "decisions")
    git = dict_field(payload, "git")
    status = str(payload.get("status", "")).strip() or "unknown"
    requested_mode = str(payload.get("requested_mode", "")).strip() or "unknown"
    detected_mode = str(payload.get("detected_mode", "")).strip() or "unknown"
    fatal_blockers = _string_list(decisions.get("fatal_blockers"))
    promotion_blockers = _string_list(decisions.get("promotion_blockers"))
    dirty_entry_count = int(git.get("dirty_entry_count", 0) or 0)
    can_execute = bool(decisions.get("can_execute_goal_runtime", False))
    can_promote = bool(decisions.get("can_promote_result", False))
    return {
        "path": GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
        "artifact_kind": artifact_kind,
        "status": status,
        "requested_mode": requested_mode,
        "detected_mode": detected_mode,
        "can_execute_goal_runtime": can_execute,
        "can_promote_result": can_promote,
        "zip_mode_replay_only": bool(decisions.get("zip_mode_replay_only", False)),
        "dirty_entry_count": dirty_entry_count,
        "fatal_blockers": fatal_blockers,
        "promotion_blockers": promotion_blockers,
        "summary": (
            "goal worktree guard "
            f"status={status}; requested_mode={requested_mode}; detected_mode={detected_mode}; "
            f"can_execute_goal_runtime={str(can_execute).lower()}; "
            f"can_promote_result={str(can_promote).lower()}; "
            f"dirty_entry_count={dirty_entry_count}"
        ),
    }


def _goal_worktree_guard_promotion_blockers(
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    status = str(summary.get("status", "not_run")).strip() or "not_run"
    can_promote = bool(summary.get("can_promote_result", False))
    if status == "pass" and can_promote:
        return []

    signal_ids = [
        item
        for item in [
            *_string_list(summary.get("fatal_blockers")),
            *_string_list(summary.get("promotion_blockers")),
        ]
        if item
    ]
    if not signal_ids:
        signal_ids = ["goal_worktree_guard_not_clean"]
    source_status = status if status != "pass" else "fail"
    return [
        {
            "id": "promotion_blocked_by_goal_worktree_guard_failure",
            "scope": "worktree_guard",
            "status": "open",
            "severity": "blocker",
            "accepted_risk": False,
            "gate_effect": GATE_EFFECT_BLOCKS_PROMOTION,
            "source_status": source_status,
            "reason": (
                "goal worktree guard is not promotable: "
                f"{str(summary.get('summary', '')).strip() or 'summary unavailable'}"
            ),
            "signal_ids": signal_ids,
            "required_evidence": [
                "Run make auto-improve-goal-preflight and confirm goal worktree guard status=pass.",
                "Use Git checkout mode for unattended mutation; ZIP/source extract mode is replay-only.",
                "can_promote_result must stay false while the worktree guard is missing, dirty, replay-only, or fatal.",
            ],
            "recommended_next_step": (
                "Refresh goal worktree guard evidence, clean the Git worktree if needed, "
                "then rerun make auto-improve-readiness."
            ),
        }
    ]
