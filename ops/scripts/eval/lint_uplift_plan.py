from __future__ import annotations

import argparse
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
from ops.scripts.schema_constants_runtime import STRICT_LINT_INVENTORY_SCHEMA_PATH

DEFAULT_OUT = "ops/reports/lint-uplift-plan.json"
DEFAULT_TARGETS = "ops/scripts tests tools"
DEFAULT_RUFF_SELECT = "B,SIM,UP,I"
STRICT_PREVIEW_AUDIT_PATH = "tmp/strict-preview-audit.json"
PRODUCER = "ops.scripts.lint_uplift_plan"
SOURCE_COMMAND = "python -m ops.scripts.lint_uplift_plan --vault ."


def parse_targets(value: str) -> list[str]:
    targets = [item.strip() for item in shlex.split(value) if item.strip()]
    if not targets:
        raise ValueError("lint uplift plan requires at least one target")
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


def _read_static_mk(vault: Path) -> str:
    path = vault / "mk" / "static.mk"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _strict_preview_target_mode(static_mk: str) -> str:
    if "--targets" in static_mk and "RUFF_STRICT_PREVIEW_TARGETS" in static_mk:
        return "full_scope_targets"
    if "ruff-strict-preview" in static_mk:
        return "indirect_target_list"
    return "unknown"


def build_report(
    vault: Path,
    *,
    targets: list[str] | None = None,
    ruff_select: str = DEFAULT_RUFF_SELECT,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    target_roots = targets or parse_targets(DEFAULT_TARGETS)
    files = _python_files(resolved_vault, target_roots)
    static_mk = _read_static_mk(resolved_vault)
    target_mode = _strict_preview_target_mode(static_mk)
    audit = load_optional_json_object(resolved_vault / STRICT_PREVIEW_AUDIT_PATH)
    audit_summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    audit_status = str(audit.get("status", "missing")) if audit else "missing"
    status = "pass" if target_mode == "full_scope_targets" and audit_status == "pass" else "attention"
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="strict_lint_inventory",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=STRICT_LINT_INVENTORY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/lint_uplift_plan.py",
                "tools/ruff_strict_preview.py",
                "tools/strict_preview_audit.py",
                "mk/static.mk",
            ],
            path_group_inputs={"full_scope_targets": files},
            text_inputs={
                "target_roots": "\n".join(target_roots),
                "ruff_select": ruff_select,
                "strict_preview_target_mode": target_mode,
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "target_roots": target_roots,
        "strict_rule_families": [item for item in ruff_select.split(",") if item],
        "full_scope": {
            "python_file_count": len(files),
            "sample_paths": files[:20],
        },
        "strict_preview": {
            "target_mode": target_mode,
            "gate_blocks_static": False,
            "audit_path": STRICT_PREVIEW_AUDIT_PATH,
            "audit_status": audit_status,
            "audit_total_error_count": int(audit_summary.get("total_error_count", 0) or 0),
            "audit_ruff_error_count": int(audit_summary.get("ruff_error_count", 0) or 0),
        },
        "target_contract": {
            "strategy": "full_scope_diagnostic_before_gate",
            "preview_full_scope_targets_enforced": target_mode == "full_scope_targets",
            "promotion_gate_impact": "none",
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=STRICT_LINT_INVENTORY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="strict lint inventory schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a full-scope strict lint uplift plan.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
    parser.add_argument("--ruff-select", default=DEFAULT_RUFF_SELECT)
    parser.add_argument("--policy-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        targets=parse_targets(str(args.targets)),
        ruff_select=str(args.ruff_select),
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
