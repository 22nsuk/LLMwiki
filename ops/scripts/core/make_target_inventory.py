#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,  # noqa: PLC0415
    )
    from ops.scripts.artifact_io_runtime import (  # noqa: PLC0415
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.makefile_runtime import load_makefile_text  # noqa: PLC0415
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.policy_runtime import load_policy, report_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
    from ops.scripts.schema_constants_runtime import (
        MAKE_TARGET_INVENTORY_SCHEMA_PATH,  # noqa: PLC0415
    )
else:
    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
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
        if "?=" in line or ":=" in line or "+=" in line or line.count("=") == 1 and ":" not in line:
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
    missing_phony_definitions = sorted(set(phony) - set(target_names))
    non_phony_targets = sorted(set(target_names) - set(phony))
    status = "fail" if missing_phony_definitions else "attention" if non_phony_targets else "pass"
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
                "ops/scripts/make_target_inventory.py",
                "Makefile",
                *[path for path in makefile_sources if path != "Makefile"],
            ],
            file_inputs={path: path for path in makefile_sources},
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
        },
        "phony_targets": phony,
        "targets": targets,
        "missing_phony_definitions": missing_phony_definitions,
        "non_phony_targets": non_phony_targets,
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
