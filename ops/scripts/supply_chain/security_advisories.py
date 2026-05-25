#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import SECURITY_ADVISORIES_SCHEMA_PATH
else:
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import SECURITY_ADVISORIES_SCHEMA_PATH


DEFAULT_SOURCE = "ops/advisories.json"
DEFAULT_OUT = "ops/reports/security-advisories.json"
TOOL_NAME = "ops.scripts.security_advisories"
ARTIFACT_KIND = "security_advisories_report"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.security_advisories"


def _resolve_source(vault: Path, source_ref: str) -> Path:
    path = Path(source_ref)
    if path.is_absolute():
        return path
    return (vault / path).resolve()


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        text = _string(item)
        if text:
            normalized.append(text)
    return sorted(set(normalized))


def _validate_advisory_rules(advisory: dict[str, Any]) -> None:
    analysis = advisory["analysis"]
    state = analysis["state"]
    justification = analysis["justification"].strip()
    action_statement = analysis["action_statement"].strip()
    resolved_version = analysis["resolved_version"].strip()

    if state == "not_affected" and not justification:
        raise ValueError(f"advisory {advisory['id']} must include justification for not_affected")
    if state in {"affected", "under_investigation"} and not action_statement:
        raise ValueError(f"advisory {advisory['id']} must include action_statement for {state}")
    if state == "fixed":
        if not action_statement:
            raise ValueError(f"advisory {advisory['id']} must include action_statement for fixed")
        if not resolved_version:
            raise ValueError(f"advisory {advisory['id']} must include resolved_version for fixed")


def _normalize_advisory(item: dict[str, Any]) -> dict[str, Any]:
    advisory = {
        "id": _string(item.get("id")),
        "aliases": _string_list(item.get("aliases")),
        "package": _string(item.get("package")),
        "version_range": _string(item.get("version_range")),
        "summary": _string(item.get("summary")),
        "reference_urls": _string_list(item.get("reference_urls")),
        "analysis": {
            "state": _string(item.get("analysis", {}).get("state")),
            "justification": _string(item.get("analysis", {}).get("justification")),
            "action_statement": _string(item.get("analysis", {}).get("action_statement")),
            "resolved_version": _string(item.get("analysis", {}).get("resolved_version")),
            "note": _string(item.get("analysis", {}).get("note")),
        },
    }
    if not advisory["id"]:
        raise ValueError("security advisory is missing id")
    if not advisory["package"]:
        raise ValueError(f"advisory {advisory['id']} is missing package")
    _validate_advisory_rules(advisory)
    return advisory


def _load_source_payload(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("advisories", [])
    else:
        raise ValueError("security advisory source must be a list or an object with advisories")
    if not isinstance(items, list):
        raise ValueError("security advisory advisories payload must be a list")
    return [_normalize_advisory(item) for item in items if isinstance(item, dict)]


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    source_ref: str = DEFAULT_SOURCE,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    source_path = _resolve_source(vault, source_ref)
    advisories: list[dict[str, Any]] = []
    status = "empty"
    if source_path.exists():
        advisories = _load_source_payload(source_path)
        status = "present" if advisories else "empty"

    report = {
        "$schema": SECURITY_ADVISORIES_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "source_ref": report_path(vault, source_path) if source_path.exists() else source_ref,
        "status": status,
        "advisory_count": len(advisories),
        "advisories": advisories,
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=runtime_context.isoformat_z(),
        artifact_kind=ARTIFACT_KIND,
        producer=TOOL_NAME,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=SECURITY_ADVISORIES_SCHEMA_PATH,
        source_paths=["ops/scripts/security_advisories.py"],
        file_inputs={"security_advisory_source": source_path} if source_path.exists() else None,
        text_inputs={"source_ref": source_ref, "advisory_count": str(len(advisories))},
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SECURITY_ADVISORIES_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="Security advisories schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize repo-native security advisories for OpenVEX authoring")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path, source_ref=args.source)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
