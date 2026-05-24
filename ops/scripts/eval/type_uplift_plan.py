from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import STRICT_TYPE_INVENTORY_SCHEMA_PATH


DEFAULT_OUT = "ops/reports/type-uplift-plan.json"
DEFAULT_TARGETS = "ops/scripts tests tools"
STRICT_PREVIEW_AUDIT_PATH = "tmp/strict-preview-audit.json"
PRODUCER = "ops.scripts.type_uplift_plan"
SOURCE_COMMAND = "python -m ops.scripts.type_uplift_plan --vault ."
ASSIGNMENT_RE = re.compile(r"^(?P<name>[A-Z0-9_]+)\s*\?=\s*(?P<value>.+)$", re.MULTILINE)


def parse_targets(value: str) -> list[str]:
    targets = [item.strip() for item in shlex.split(value) if item.strip()]
    if not targets:
        raise ValueError("type uplift plan requires at least one target")
    return targets


def _python_files(vault: Path, targets: list[str]) -> list[str]:
    paths: list[str] = []
    for target in targets:
        root = vault / target
        if root.is_file() and root.suffix == ".py":
            paths.append(report_path(vault, root))
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or any(part.startswith(".") for part in path.parts):
                continue
            paths.append(report_path(vault, path))
    return sorted(set(paths))


def _read_static_assignments(vault: Path) -> dict[str, str]:
    path = vault / "mk" / "static.mk"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {match.group("name"): match.group("value").strip() for match in ASSIGNMENT_RE.finditer(text)}


def _target_mode(value: str) -> str:
    if value.startswith("@"):
        return "legacy_target_list"
    if value:
        return "full_scope_targets"
    return "unknown"


def build_report(
    vault: Path,
    *,
    targets: list[str] | None = None,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    target_roots = targets or parse_targets(DEFAULT_TARGETS)
    files = _python_files(resolved_vault, target_roots)
    assignments = _read_static_assignments(resolved_vault)
    default_targets = assignments.get("MYPY_TARGETS", "")
    strict_targets = assignments.get("MYPY_STRICT_PREVIEW_TARGETS", "")
    default_mode = _target_mode(default_targets)
    strict_mode = _target_mode(strict_targets)
    audit = load_optional_json_object(resolved_vault / STRICT_PREVIEW_AUDIT_PATH)
    audit_summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    audit_status = str(audit.get("status", "missing")) if audit else "missing"
    status = "pass" if default_mode == strict_mode == "full_scope_targets" and audit_status == "pass" else "attention"
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="strict_type_inventory",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=STRICT_TYPE_INVENTORY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/type_uplift_plan.py",
                "mk/static.mk",
            ],
            path_group_inputs={"full_scope_targets": files},
            text_inputs={
                "target_roots": "\n".join(target_roots),
                "default_targets": default_targets,
                "strict_targets": strict_targets,
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "target_roots": target_roots,
        "full_scope": {
            "python_file_count": len(files),
            "sample_paths": files[:20],
        },
        "default_mypy": {
            "targets": default_targets,
            "target_mode": default_mode,
            "uses_legacy_target_list": default_mode == "legacy_target_list",
        },
        "strict_preview": {
            "targets": strict_targets,
            "target_mode": strict_mode,
            "uses_legacy_target_list": strict_mode == "legacy_target_list",
            "audit_path": STRICT_PREVIEW_AUDIT_PATH,
            "audit_status": audit_status,
            "audit_total_error_count": int(audit_summary.get("total_error_count", 0) or 0),
            "audit_mypy_error_count": int(audit_summary.get("mypy_error_count", 0) or 0),
        },
        "migration": {
            "strategy": "full_scope_diagnostic_before_gate",
            "allowlist_removed_from_default_target": default_mode == "full_scope_targets",
            "allowlist_removed_from_strict_preview_target": strict_mode == "full_scope_targets",
            "promotion_gate_impact": "none",
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=STRICT_TYPE_INVENTORY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="strict type inventory schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a full-scope strict type uplift plan.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--policy-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        targets=parse_targets(str(args.targets)),
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
