from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import load_optional_json_object, write_schema_validated_json
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema


DEFAULT_READINESS_REPORT = "ops/reports/auto-improve-readiness.json"
DEFAULT_GOAL_AUDIT_LOG = "ops/reports/goal-audit-log.jsonl"
DEFAULT_OUT = "ops/reports/remediation-backlog.json"
SCHEMA_PATH = "ops/schemas/remediation-backlog.schema.json"
POLICY_PATH = "ops/policies/wiki-maintainer-policy.yaml"
REPEATED_BLOCKER_THRESHOLD = 2
CANONICAL_REPEATED_BLOCKERS = {"recent_log_overlap", "fallback_target_history_depth"}


def _artifact_envelope(
    vault: Path,
    *,
    generated_at: str,
    readiness_report: str,
    goal_audit_log: str,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, POLICY_PATH)
    file_inputs = {"readiness_report": readiness_report}
    if goal_audit_log and (vault / goal_audit_log).is_file():
        file_inputs["goal_audit_log"] = goal_audit_log
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="remediation_backlog",
        producer="ops.scripts.remediation_backlog",
        source_command="python -m ops.scripts.remediation_backlog",
        resolved_policy_path=resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=[
            "ops/scripts/mechanism/remediation_backlog.py",
            SCHEMA_PATH,
        ],
        file_inputs=file_inputs,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _item_id(prefix: str, value: str, index: int) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.lower())
    return f"{prefix}-{normalized or index}"


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _audit_blocker_code(event: dict[str, Any]) -> str:
    event_name = str(event.get("event", "")).strip()
    status = str(event.get("status", "")).strip()
    reason = str(event.get("reason", "")).strip()
    if event_name == "goal_run_executor_backoff":
        return "executor_usage_limited"
    if status != "blocked" and not event_name.endswith("_blocked"):
        return ""
    for part in reason.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key in {"stop_reason", "failure_mode", "blocker"} and value.strip():
            return value.strip()
    if "readiness blockers are present" in reason:
        return "auto_improve_readiness_blockers_present"
    if "failure_budget_exhausted" in reason:
        return "failure_budget_exhausted"
    if "executor_usage_limited" in reason:
        return "executor_usage_limited"
    return reason


def _items_from_goal_audit_log(vault: Path, goal_audit_log: str) -> list[dict[str, Any]]:
    records = _read_jsonl_objects(vault / goal_audit_log)
    blocker_codes = [_audit_blocker_code(record) for record in records]
    counts = Counter(code for code in blocker_codes if code)
    items: list[dict[str, Any]] = []
    for index, (blocker, count) in enumerate(sorted(counts.items()), start=1):
        if count < REPEATED_BLOCKER_THRESHOLD:
            continue
        items.append(
            {
                "id": _item_id("goal-audit-repeated", blocker, index),
                "source": "goal_audit_log.repeated_blocker",
                "blocker": blocker,
                "blocker_kind": "goal_runtime_audit",
                "status": "open",
                "remediation_code": "convert_repeated_goal_runtime_blocker",
                "recommended_next_step": (
                    "Convert the repeated goal runtime blocker into explicit remediation "
                    "evidence before resuming or escalating the sustained profile."
                ),
                "minimum_evidence": [
                    goal_audit_log,
                    "ops/reports/goal-run-status.json",
                    DEFAULT_OUT,
                ],
            }
        )
    return items


def _items_from_remediations(remediations: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, remediation in enumerate(remediations, start=1):
        if not isinstance(remediation, dict):
            continue
        blocker = str(remediation.get("blocker", "")).strip()
        items.append(
            {
                "id": _item_id("remediation", blocker, index),
                "source": "readiness.remediations",
                "blocker": blocker,
                "blocker_kind": str(remediation.get("blocker_kind", "")).strip(),
                "status": "open",
                "remediation_code": str(remediation.get("remediation_code", "")).strip(),
                "recommended_next_step": str(
                    remediation.get("retry_condition")
                    or remediation.get("recommended_next_step")
                    or ""
                ).strip(),
                "minimum_evidence": _string_list(remediation.get("minimum_evidence")),
            }
        )
    return items


def _items_from_blockers(blockers: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, blocker in enumerate(blockers, start=1):
        if not isinstance(blocker, dict):
            continue
        blocker_id = str(blocker.get("id", "")).strip()
        items.append(
            {
                "id": _item_id("blocker", blocker_id, index),
                "source": "readiness.blockers",
                "blocker": blocker_id,
                "blocker_kind": str(blocker.get("scope", "")).strip(),
                "status": "open",
                "remediation_code": "resolve_readiness_blocker",
                "recommended_next_step": str(blocker.get("recommended_next_step", "")).strip(),
                "minimum_evidence": _string_list(blocker.get("required_evidence")),
            }
        )
    return items


def build_report(
    vault: Path,
    *,
    readiness_report: str = DEFAULT_READINESS_REPORT,
    goal_audit_log: str = DEFAULT_GOAL_AUDIT_LOG,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    readiness = load_optional_json_object(vault / readiness_report)
    remediations = readiness.get("remediations", [])
    blockers = readiness.get("blockers", [])
    items = _items_from_remediations(remediations if isinstance(remediations, list) else [])
    seen = {item["blocker"] for item in items}
    for item in _items_from_blockers(blockers if isinstance(blockers, list) else []):
        if item["blocker"] not in seen:
            items.append(item)
            seen.add(item["blocker"])
    for item in _items_from_goal_audit_log(vault, goal_audit_log):
        if item["blocker"] not in seen:
            items.append(item)
            seen.add(item["blocker"])
    repeated = [
        item
        for item in items
        if item["blocker"] in CANONICAL_REPEATED_BLOCKERS
        or item["source"] == "goal_audit_log.repeated_blocker"
    ]
    generated_at = runtime_context.isoformat_z()
    report = {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "remediation_backlog",
        "generated_at": generated_at,
        "producer": "ops.scripts.remediation_backlog",
        "status": "attention" if items else "pass",
        "source_readiness_report": readiness_report,
        "summary": {
            "open_item_count": len(items),
            "repeated_blocker_count": len(repeated),
        },
        "items": items,
    }
    report.update(
        _artifact_envelope(
            vault,
            generated_at=generated_at,
            readiness_report=readiness_report,
            goal_audit_log=goal_audit_log,
        )
    )
    return report


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_validated_json(
        vault / out_path,
        report,
        load_schema(vault / SCHEMA_PATH),
        context="remediation backlog schema validation failed",
        trailing_newline=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build auto-improve remediation backlog.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--readiness-report", default=DEFAULT_READINESS_REPORT)
    parser.add_argument("--goal-audit-log", default=DEFAULT_GOAL_AUDIT_LOG)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        readiness_report=args.readiness_report,
        goal_audit_log=args.goal_audit_log,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
