from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import load_optional_json_object, write_schema_validated_json
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema


DEFAULT_READINESS_REPORT = "ops/reports/auto-improve-readiness.json"
DEFAULT_OUT = "ops/reports/remediation-backlog.json"
SCHEMA_PATH = "ops/schemas/remediation-backlog.schema.json"
POLICY_PATH = "ops/policies/wiki-maintainer-policy.yaml"


def _artifact_envelope(
    vault: Path,
    *,
    generated_at: str,
    readiness_report: str,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, POLICY_PATH)
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
        file_inputs={"readiness_report": readiness_report},
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _item_id(prefix: str, value: str, index: int) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.lower())
    return f"{prefix}-{normalized or index}"


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
    repeated = [
        item
        for item in items
        if item["blocker"] in {"recent_log_overlap", "fallback_target_history_depth"}
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
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, readiness_report=args.readiness_report)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
