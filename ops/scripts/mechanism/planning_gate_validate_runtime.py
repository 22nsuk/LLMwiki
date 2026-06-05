from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.schema_constants_runtime import (
    PLANNING_GATE_VALIDATION_REPORT_SCHEMA_PATH,
)
from ops.scripts.starter_bundle_runtime import (
    DEFAULT_STARTER_BUNDLE,
    starter_bundle_path,
)

from . import (
    planning_gate_artifact_runtime as planning_gate_artifact_runtime,
    planning_gate_report_runtime as planning_gate_report_runtime,
)

ARTIFACT_SCHEMAS = planning_gate_artifact_runtime.ARTIFACT_SCHEMAS
OPTIONAL_ARTIFACT_SCHEMAS = planning_gate_artifact_runtime.OPTIONAL_ARTIFACT_SCHEMAS
DEFAULT_OUT = "ops/reports/planning-gate-validation-report.json"
PlanningArtifactError = planning_gate_artifact_runtime.PlanningArtifactError
ArtifactLoadError = planning_gate_artifact_runtime.ArtifactLoadError
load_artifact = planning_gate_artifact_runtime.load_artifact
validate_artifact = planning_gate_artifact_runtime.validate_artifact
validate_optional_artifact = planning_gate_artifact_runtime.validate_optional_artifact
validate_run_dir = planning_gate_report_runtime.validate_run_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--artifact-dir")
    ap.add_argument("--out")
    return ap.parse_args(argv)


def write_report(vault: Path, report: Mapping[str, Any], out_path: str) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=PLANNING_GATE_VALIDATION_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="planning gate validation report schema validation failed",
            trailing_newline=False,
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault)
    policy, _ = load_policy(vault)
    if args.artifact_dir:
        artifact_dir = Path(args.artifact_dir)
        if not artifact_dir.is_absolute():
            artifact_dir = vault / artifact_dir
    else:
        artifact_dir = starter_bundle_path(vault, policy, DEFAULT_STARTER_BUNDLE)

    report = validate_run_dir(vault, artifact_dir, policy=policy)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_report(vault, report, args.out)
    else:
        print(text)
    raise SystemExit(1 if report["status"] == "fail" else 0)
