from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    read_json_object,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_or_raise


DEFAULT_OUT = "ops/reports/remediation-backlog.json"
PRODUCER = "ops.scripts.remediation_backlog"
SCHEMA_PATH = "ops/schemas/remediation-backlog.schema.json"
STATUS_OVERRIDES_SCHEMA_PATH = "ops/schemas/remediation-backlog-status-overrides.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.remediation_backlog --vault ."
NEGATIVE_LESSONS_PATH = "ops/reports/self-improvement-negative-lessons.json"
SESSION_SYNOPSIS_PATH = "ops/reports/session-synopsis.json"
ACTIVATION_REPORT_PATH = "ops/reports/learning_claim_activation_report.json"
AUTO_IMPROVE_SESSIONS_DIR = "ops/reports/auto-improve-sessions"
STATUS_OVERRIDES_PATH = "ops/policies/remediation-backlog-status-overrides.json"
SOURCE_PATHS = [
    "ops/scripts/learning/remediation_backlog.py",
    "ops/scripts/learning/self_improvement_negative_lessons.py",
    "ops/scripts/learning/session_synopsis.py",
    "ops/scripts/mechanism/auto_improve_runtime.py",
]
SAFE_ID_RE = re.compile(r"[^a-z0-9_]+")


def _safe_id(value: str) -> str:
    text = SAFE_ID_RE.sub("_", value.lower()).strip("_")
    return text or "unknown"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _evidence_paths_from_digests(value: object) -> list[str]:
    return [
        str(item.get("path", "")).strip()
        for item in _dict_list(value)
        if str(item.get("path", "")).strip()
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _status_overrides(vault: Path) -> dict[str, dict[str, Any]]:
    path = vault / STATUS_OVERRIDES_PATH
    if not path.exists():
        return {}
    payload = read_json_object(path, context=STATUS_OVERRIDES_PATH)
    schema = load_schema_with_vault_override(vault, STATUS_OVERRIDES_SCHEMA_PATH)
    validate_or_raise(
        payload,
        schema,
        context="remediation backlog status overrides schema validation failed",
    )
    overrides: dict[str, dict[str, Any]] = {}
    for override in _dict_list(payload.get("overrides")):
        item_id = _safe_id(str(override.get("item_id", "")).strip())
        status = str(override.get("status", "")).strip()
        if not item_id or status not in {"closed", "deferred"}:
            continue
        overrides[item_id] = {
            "status": status,
            "reason": str(override.get("reason", "")).strip(),
            "evidence_paths": _string_list(override.get("evidence_paths")),
        }
    return overrides


def _apply_status_override(item: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if override is None:
        return item
    updated = dict(item)
    updated["status"] = override["status"]
    reason = str(override.get("reason", "")).strip()
    if reason:
        updated["next_action"] = reason
    evidence_paths = set(_string_list(updated.get("evidence_paths")))
    evidence_paths.update(_string_list(override.get("evidence_paths")))
    updated["evidence_paths"] = sorted(evidence_paths)
    return updated


def _item_from_lesson(lesson: dict[str, Any]) -> dict[str, Any] | None:
    lesson_id = str(lesson.get("lesson_id", "")).strip()
    if not lesson_id:
        return None
    occurrence_count = int(lesson.get("occurrence_count", 0) or 0)
    if occurrence_count < 2 and not bool(lesson.get("backlog_candidate", False)):
        return None
    repair_target = str(lesson.get("repair_target", "")).strip()
    return {
        "item_id": f"negative_lesson_{_safe_id(lesson_id)}",
        "blocker_id": _safe_id(lesson_id),
        "source": "self_improvement_negative_lessons.lessons",
        "item_type": "repeated_negative_lesson",
        "status": "open",
        "severity": "blocks_repeat",
        "occurrence_count": max(2, occurrence_count),
        "evidence_paths": _evidence_paths_from_digests(lesson.get("evidence_digests")),
        "repair_target": repair_target,
        "next_action": repair_target or "Close the repeated negative lesson before rerunning this shape.",
    }


def _item_from_blocker(blocker: dict[str, Any]) -> dict[str, Any] | None:
    blocker_id = str(blocker.get("id", "")).strip()
    if not blocker_id:
        return None
    repair_target = str(blocker.get("repair_target", "")).strip()
    return {
        "item_id": f"active_blocker_{_safe_id(blocker_id)}",
        "blocker_id": _safe_id(blocker_id),
        "source": str(blocker.get("source", "session_synopsis.recent_blockers")).strip()
        or "session_synopsis.recent_blockers",
        "item_type": "active_blocker",
        "status": "open",
        "severity": "blocks_promotion",
        "occurrence_count": 1,
        "evidence_paths": [SESSION_SYNOPSIS_PATH],
        "repair_target": repair_target,
        "next_action": repair_target or "Resolve or explicitly defer this active blocker.",
    }


def _item_from_auto_improve_session(session: dict[str, Any], rel_path: str) -> dict[str, Any] | None:
    loop_state = session.get("loop_state")
    if not isinstance(loop_state, dict):
        return None
    if not bool(loop_state.get("repeated_blocker_stop", False)):
        return None
    blocker_reason = str(loop_state.get("repeated_blocker_reason", "")).strip()
    if not blocker_reason:
        return None
    counts = loop_state.get("blocking_reason_counts")
    occurrence_count = 2
    if isinstance(counts, dict):
        raw_count = counts.get(blocker_reason, 0)
        if isinstance(raw_count, int) and not isinstance(raw_count, bool):
            occurrence_count = max(2, raw_count)
    session_id = str(session.get("session_id", "")).strip() or Path(rel_path).stem
    safe_reason = _safe_id(blocker_reason)
    return {
        "item_id": f"auto_session_repeated_blocker_{_safe_id(session_id)}_{safe_reason}",
        "blocker_id": safe_reason,
        "source": "auto_improve_session.loop_state",
        "item_type": "repeated_auto_improve_blocker",
        "status": "open",
        "severity": "blocks_repeat",
        "occurrence_count": occurrence_count,
        "evidence_paths": [rel_path],
        "repair_target": f"Resolve repeated auto-improve blocker '{blocker_reason}'.",
        "next_action": "Close this backlog item before rerunning the same auto-improve blocker shape.",
    }


def _auto_improve_session_backlog_items(vault: Path) -> list[dict[str, Any]]:
    sessions_dir = vault / AUTO_IMPROVE_SESSIONS_DIR
    if not sessions_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(sessions_dir.glob("*.json")):
        rel_path = path.relative_to(vault).as_posix()
        payload = load_optional_json_object(path)
        item = _item_from_auto_improve_session(payload, rel_path)
        if item is not None:
            items.append(item)
    return items


def _auto_improve_session_report_paths(vault: Path) -> list[str]:
    sessions_dir = vault / AUTO_IMPROVE_SESSIONS_DIR
    if not sessions_dir.is_dir():
        return []
    return [path.relative_to(vault).as_posix() for path in sorted(sessions_dir.glob("*.json"))]


def collect_backlog_items(vault: Path) -> list[dict[str, Any]]:
    negative_lessons = load_optional_json_object(vault / NEGATIVE_LESSONS_PATH)
    synopsis = load_optional_json_object(vault / SESSION_SYNOPSIS_PATH)
    status_overrides = _status_overrides(vault)
    items_by_id: dict[str, dict[str, Any]] = {}
    for lesson in _dict_list(negative_lessons.get("lessons")):
        item = _item_from_lesson(lesson)
        if item is not None:
            items_by_id[item["item_id"]] = item
    for blocker in _dict_list(synopsis.get("recent_blockers")):
        item = _item_from_blocker(blocker)
        if item is not None:
            items_by_id.setdefault(item["item_id"], item)
    for item in _auto_improve_session_backlog_items(vault):
        items_by_id.setdefault(item["item_id"], item)
    items = (
        _apply_status_override(item, status_overrides.get(item["item_id"]))
        for item in items_by_id.values()
    )
    return sorted(items, key=lambda item: item["item_id"])


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    repeated_count = sum(1 for item in items if item["item_type"] == "repeated_negative_lesson")
    repeated_runtime_count = sum(
        1 for item in items if item["item_type"] == "repeated_auto_improve_blocker"
    )
    active_count = sum(1 for item in items if item["item_type"] == "active_blocker")
    open_count = sum(1 for item in items if item["status"] == "open")
    return {
        "backlog_item_count": len(items),
        "repeated_blocker_count": repeated_count + repeated_runtime_count,
        "active_blocker_count": active_count,
        "open_item_count": open_count,
        "promotion_policy": "do_not_retry_repeated_blockers_until_backlog_item_closed",
        "next_action": "Close or explicitly defer remediation backlog items before promotion."
        if open_count
        else "No remediation backlog items detected.",
    }


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    items = collect_backlog_items(vault)
    summary = _summary(items)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="remediation_backlog",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=SOURCE_PATHS,
            file_inputs={
                "self_improvement_negative_lessons": NEGATIVE_LESSONS_PATH,
                "session_synopsis": SESSION_SYNOPSIS_PATH,
                "learning_claim_activation": ACTIVATION_REPORT_PATH,
                "status_overrides": STATUS_OVERRIDES_PATH,
            },
            path_group_inputs={
                "auto_improve_sessions": _auto_improve_session_report_paths(vault),
            },
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "attention" if summary["open_item_count"] else "pass",
        "summary": summary,
        "items": items,
        "inputs": {
            "self_improvement_negative_lessons": NEGATIVE_LESSONS_PATH,
            "session_synopsis": SESSION_SYNOPSIS_PATH,
            "learning_claim_activation": ACTIVATION_REPORT_PATH,
            "auto_improve_sessions": AUTO_IMPROVE_SESSIONS_DIR,
            "status_overrides": STATUS_OVERRIDES_PATH,
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="remediation backlog schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build remediation backlog report.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
