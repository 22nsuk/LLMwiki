#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import MANUAL_MUTATE_DEFECT_REGISTRY_SCHEMA_PATH
else:
    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import MANUAL_MUTATE_DEFECT_REGISTRY_SCHEMA_PATH


DEFAULT_OUT = "ops/reports/manual-mutate-defect-registry.json"
PRODUCER = "ops.scripts.manual_mutate_defect_registry"
SOURCE_COMMAND = "python -m ops.scripts.manual_mutate_defect_registry"
ARTIFACT_KIND = "manual_mutate_defect_registry"
MANUAL_MUTATE_GLOB = "manual_mutate_*.py"

DEFECT_REGISTRY_INPUTS: dict[str, dict[str, Any]] = {
    "tools/manual_mutate_auto_improve_decision_record_fallback.py": {
        "defect_id": "decision_record_promotion_report_absorption_gap",
        "defect_class": "decision_provenance_loss",
        "target_paths": ["ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"],
        "canonical_fix_refs": [
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py::_iteration_decision_record",
            "ops/scripts/core/promotion_decision_registry_runtime.py::decision_record_from_report",
        ],
        "regression_tests": [
            "tests/test_auto_improve_iteration_runtime.py::test_write_iteration_telemetry_recovers_decision_record_from_promotion_report_path"
        ],
        "fix_markers": {
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py": [
                "def _iteration_decision_record(",
                "decision_record_from_report",
                "promotion_report",
            ]
        },
        "notes": "Recover decision_record from explicit promotion_report payload/path or runs/<run-id>/promotion-report.json.",
    },
    "tools/manual_mutate_auto_improve_timeout_telemetry.py": {
        "defect_id": "run_telemetry_timeout_merge_loss",
        "defect_class": "timeout_telemetry_loss",
        "target_paths": ["ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"],
        "canonical_fix_refs": [
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py::_iteration_command_timeouts",
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py::_iteration_timeout_failure_artifacts",
        ],
        "regression_tests": [
            "tests/test_auto_improve_iteration_runtime.py::test_write_iteration_telemetry_merges_nested_timeout_fields_from_result"
        ],
        "fix_markers": {
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py": [
                "def _iteration_command_timeouts(vault: Path, run_id: str, result: dict | None)",
                "result.get(\"command_timeouts\", {})",
                "def _iteration_timeout_failure_artifacts(vault: Path, run_id: str, result: dict | None)",
                "result.get(\"timeout_failure_artifacts\", [])",
            ]
        },
        "notes": "Merge timeout fields from nested result.command_timeouts, top-level timeout result fields, existing telemetry, and run artifacts.",
    },
    "tools/manual_mutate_auto_improve_existing_telemetry_inline.py": {
        "defect_id": "run_telemetry_existing_report_helper_indirection",
        "defect_class": "telemetry_merge_simplification",
        "target_paths": ["ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"],
        "canonical_fix_refs": [
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py::write_iteration_telemetry",
        ],
        "regression_tests": [
            "tests/test_auto_improve_iteration_runtime.py::test_write_iteration_telemetry_preserves_existing_workspace_apply_fields"
        ],
        "fix_markers": {
            "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py": [
                "loaded_existing_report = load_optional_json(",
                "existing_report = loaded_existing_report if isinstance(loaded_existing_report, dict) else {}",
            ],
            "tests/test_auto_improve_iteration_runtime.py": [
                "self.assertNotIn(\"_existing_run_telemetry\", runtime_source)",
            ],
        },
        "notes": (
            "Inline existing run-telemetry loading in write_iteration_telemetry and keep a focused "
            "regression assertion that the helper indirection stays removed."
        ),
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _script_paths(vault: Path) -> list[Path]:
    tools_dir = vault / "tools"
    if not tools_dir.exists():
        return []
    return sorted(path for path in tools_dir.glob(MANUAL_MUTATE_GLOB) if path.is_file())


def _markers_present(vault: Path, marker_map: dict[str, list[str]]) -> tuple[str, list[dict[str, Any]]]:
    evidence = []
    all_present = True
    any_present = False
    for rel_path, markers in sorted(marker_map.items()):
        path = vault / rel_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = [marker for marker in markers if marker not in text]
        present = [marker for marker in markers if marker in text]
        all_present = all_present and not missing and path.exists()
        any_present = any_present or bool(present)
        evidence.append(
            {
                "path": rel_path,
                "present_markers": present,
                "missing_markers": missing,
            }
        )
    if all_present:
        return "fixed", evidence
    if any_present:
        return "partial", evidence
    return "unresolved", evidence


def _test_exists(vault: Path, test_ref: str) -> bool:
    rel_path, _, test_name = test_ref.partition("::")
    path = vault / rel_path
    if not path.exists():
        return False
    if not test_name:
        return True
    return f"def {test_name}(" in path.read_text(encoding="utf-8")


def _regression_status(vault: Path, tests: list[str]) -> str:
    if not tests:
        return "missing"
    existing = [test_ref for test_ref in tests if _test_exists(vault, test_ref)]
    if len(existing) == len(tests):
        return "covered"
    if existing:
        return "partial"
    return "missing"


def _entry_for_script(vault: Path, script_path: Path) -> dict[str, Any]:
    rel_path = report_path(vault, script_path)
    metadata = DEFECT_REGISTRY_INPUTS.get(rel_path)
    if metadata is None:
        script_hash = _sha256(script_path)
        return {
            "defect_id": Path(rel_path).stem,
            "script_path": rel_path,
            "script_sha256": script_hash,
            "defect_class": "unclassified_manual_mutation",
            "target_paths": [],
            "canonical_fix_status": "unresolved",
            "regression_status": "missing",
            "canonical_fix_refs": [],
            "regression_tests": [],
            "evidence": [],
            "notes": "No registry metadata is defined for this manual mutate script.",
        }

    fix_status, evidence = _markers_present(vault, metadata.get("fix_markers", {}))
    tests = [str(item) for item in metadata.get("regression_tests", [])]
    return {
        "defect_id": str(metadata["defect_id"]),
        "script_path": rel_path,
        "script_sha256": _sha256(script_path),
        "defect_class": str(metadata["defect_class"]),
        "target_paths": list(metadata.get("target_paths", [])),
        "canonical_fix_status": fix_status,
        "regression_status": _regression_status(vault, tests),
        "canonical_fix_refs": list(metadata.get("canonical_fix_refs", [])),
        "regression_tests": tests,
        "evidence": evidence,
        "notes": str(metadata.get("notes", "")),
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    script_paths = _script_paths(vault)
    entries = [_entry_for_script(vault, path) for path in script_paths]
    unresolved = [
        entry
        for entry in entries
        if entry["canonical_fix_status"] != "fixed" or entry["regression_status"] != "covered"
    ]
    generated_at = runtime_context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind=ARTIFACT_KIND,
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=MANUAL_MUTATE_DEFECT_REGISTRY_SCHEMA_PATH,
            source_paths=["ops/scripts/core/manual_mutate_defect_registry.py"],
            path_group_inputs={
                "manual_mutate_scripts": [report_path(vault, path) for path in script_paths],
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "attention" if unresolved else "pass",
        "summary": {
            "manual_mutate_script_count": len(entries),
            "registered_defect_count": sum(
                1 for entry in entries if entry["defect_class"] != "unclassified_manual_mutation"
            ),
            "fixed_defect_count": sum(1 for entry in entries if entry["canonical_fix_status"] == "fixed"),
            "covered_regression_count": sum(1 for entry in entries if entry["regression_status"] == "covered"),
            "unresolved_or_uncovered_count": len(unresolved),
        },
        "defects": entries,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=MANUAL_MUTATE_DEFECT_REGISTRY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="manual mutate defect registry schema validation failed",
            trailing_newline=False,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a defect registry from manual mutate scripts")
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
