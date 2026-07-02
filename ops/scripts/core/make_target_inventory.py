#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.anti_slop_admission_runtime import (
        evaluate_anti_slop_admission,
    )
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.make_target_operator_surface_runtime import (
        internal_make_targets,
        validate_operator_inventory_surface,
    )
    from ops.scripts.core.makefile_runtime import load_makefile_text
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        MAKE_TARGET_INVENTORY_SCHEMA_PATH,
    )
else:
    from .anti_slop_admission_runtime import evaluate_anti_slop_admission
    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from .make_target_operator_surface_runtime import (
        internal_make_targets,
        validate_operator_inventory_surface,
    )
    from .makefile_runtime import load_makefile_text
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import MAKE_TARGET_INVENTORY_SCHEMA_PATH


DEFAULT_OUT = "tmp/make-target-inventory.json"
PRODUCER = "ops.scripts.make_target_inventory"
TARGET_RE = re.compile(r"^([A-Za-z0-9_.%/@-][A-Za-z0-9_.%/@ -]*):(?:\s|$)")
SCRIPT_MODULE_RE = re.compile(
    r"-m\s+(ops\.scripts\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\b"
)


def _parse_makefile(content: str) -> tuple[list[str], list[dict[str, Any]]]:
    phony: list[str] = []
    targets: list[dict[str, Any]] = []
    current_targets: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(".PHONY:"):
            phony.extend(item for item in stripped.split(":", 1)[1].split() if item)
            continue
        if line.startswith(("\t", " ")):
            module_invocations = SCRIPT_MODULE_RE.findall(line)
            if module_invocations:
                for target in current_targets:
                    target["module_invocations"].extend(module_invocations)
            continue
        if "?=" in line or ":=" in line or "+=" in line or (line.count("=") == 1 and ":" not in line):
            continue
        match = TARGET_RE.match(line)
        if match is None:
            current_targets = []
            continue
        names = [item.strip() for item in match.group(1).split() if item.strip()]
        current_targets = []
        for name in names:
            target = {
                "name": name,
                "line": line_number,
                "phony": name in phony,
                "module_invocations": [],
            }
            targets.append(target)
            current_targets.append(target)
    for target in targets:
        target["module_invocations"] = sorted(set(target["module_invocations"]))
    return sorted(set(phony)), targets


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    content, makefile_sources = load_makefile_text(vault)
    phony, targets = _parse_makefile(content)
    target_names = sorted({str(item["name"]) for item in targets})
    target_name_set = set(target_names)
    missing_phony_definitions = sorted(set(phony) - target_name_set)
    non_phony_targets = sorted(target_name_set - set(phony))
    operator_inventory_path = vault / "ops" / "make-target-inventory-operator.json"
    operator_inventory: dict[str, Any] = {}
    if operator_inventory_path.is_file():
        loaded = json.loads(operator_inventory_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            operator_inventory = loaded
    operator_surface_violations = validate_operator_inventory_surface(
        operator_inventory,
        makefile_targets=target_name_set,
    )
    internal_targets = internal_make_targets(target_name_set)
    anti_slop_admission = evaluate_anti_slop_admission(
        vault.resolve(),
        makefile_targets=target_name_set,
        context=runtime_context,
    )
    anti_slop_violation_count = len(anti_slop_admission["violations"])
    operator_surface_violation_count = len(operator_surface_violations)
    if (
        missing_phony_definitions
        or anti_slop_admission["status"] == "fail"
        or operator_surface_violations
    ):
        status = "fail"
    elif non_phony_targets:
        status = "attention"
    else:
        status = "pass"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="make_target_inventory",
            producer=PRODUCER,
            source_command="python -m ops.scripts.make_target_inventory --vault . --out tmp/make-target-inventory.json",
            resolved_policy_path=resolved_policy_path,
            schema_path=MAKE_TARGET_INVENTORY_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/core/make_target_inventory.py",
                "ops/scripts/core/anti_slop_admission_runtime.py",
                "ops/scripts/core/make_target_operator_surface_runtime.py",
                "ops/make-target-inventory-operator.json",
                "ops/script-lifecycle-policy.json",
                "Makefile",
                *[path for path in makefile_sources if path != "Makefile"],
            ],
            file_inputs={
                path: path
                for path in (
                    *makefile_sources,
                    "ops/make-target-inventory-operator.json",
                    "ops/script-lifecycle-policy.json",
                )
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "makefile_path": "Makefile",
        "summary": {
            "target_count": len(target_names),
            "phony_count": len(phony),
            "module_invocation_count": sum(len(item["module_invocations"]) for item in targets),
            "missing_phony_definition_count": len(missing_phony_definitions),
            "non_phony_target_count": len(non_phony_targets),
            "anti_slop_violation_count": anti_slop_violation_count,
            "internal_target_count": len(internal_targets),
            "operator_surface_violation_count": operator_surface_violation_count,
        },
        "phony_targets": phony,
        "targets": targets,
        "missing_phony_definitions": missing_phony_definitions,
        "non_phony_targets": non_phony_targets,
        "internal_targets": internal_targets,
        "operator_surface": {
            "status": "fail" if operator_surface_violations else "pass",
            "violations": operator_surface_violations,
        },
        "anti_slop_admission": anti_slop_admission,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=MAKE_TARGET_INVENTORY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="Make target inventory schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a schema-backed Make target inventory")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the live Make target inventory without writing the diagnostic report",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    if args.check:
        print(f"make_target_inventory: status={report['status']}")
    else:
        destination = write_report(vault, report, args.out)
        print(display_path(vault, destination))
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
