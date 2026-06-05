from __future__ import annotations

import argparse
import shlex
import tomllib
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
DEFAULT_RUFF_SELECT = "PTH201"
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


def _read_enforced_select(vault: Path) -> list[str]:
    path = vault / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    tool = payload.get("tool")
    if not isinstance(tool, dict):
        return []
    ruff = tool.get("ruff")
    if not isinstance(ruff, dict):
        return []
    lint = ruff.get("lint")
    if not isinstance(lint, dict):
        return []
    select = lint.get("select")
    if not isinstance(select, list):
        return []
    return [str(item).strip() for item in select if str(item).strip()]


def _audit_rule_family_counts(audit: dict[str, Any], strict_rule_families: list[str]) -> dict[str, int]:
    family_counts = dict.fromkeys(strict_rule_families, 0)
    ruff = audit.get("ruff")
    if not isinstance(ruff, dict):
        return family_counts
    rule_counts = ruff.get("rule_counts")
    if not isinstance(rule_counts, dict):
        return family_counts
    ordered_families = sorted(strict_rule_families, key=len, reverse=True)
    for rule, count in rule_counts.items():
        rule_text = str(rule).strip()
        matched_family = next(
            (
                family
                for family in ordered_families
                if rule_text == family or rule_text.startswith(family)
            ),
            None,
        )
        if matched_family is None:
            continue
        family_counts[matched_family] += int(count)
    return family_counts


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
    strict_rule_families = [item for item in ruff_select.split(",") if item]
    files = _python_files(resolved_vault, target_roots)
    static_mk = _read_static_mk(resolved_vault)
    target_mode = _strict_preview_target_mode(static_mk)
    audit = load_optional_json_object(resolved_vault / STRICT_PREVIEW_AUDIT_PATH)
    enforced_select = _read_enforced_select(resolved_vault)
    enforced_rule_families = [family for family in strict_rule_families if family in enforced_select]
    family_counts = _audit_rule_family_counts(audit, strict_rule_families)
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
                "pyproject.toml",
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
        "strict_rule_families": strict_rule_families,
        "enforced_rule_families": enforced_rule_families,
        "remaining_violations": {
            family: family_counts[family]
            for family in strict_rule_families
            if family not in enforced_rule_families
        },
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
