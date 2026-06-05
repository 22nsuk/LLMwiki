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
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        ARTIFACT_RELOCATION_AUDIT_SCHEMA_PATH,
    )
else:
    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import ARTIFACT_RELOCATION_AUDIT_SCHEMA_PATH


DEFAULT_OUT = "ops/operator/artifact-relocation-audit.json"
PRODUCER = "ops.scripts.artifact_relocation_audit"
SOURCE_COMMAND = (
    "python -m ops.scripts.artifact_relocation_audit "
    "--vault . --out ops/operator/artifact-relocation-audit.json"
)
DEPENDENCY_ROOTS = ("ops", "tests", "mk", "docs", ".github")
ROOT_DEPENDENCY_FILES = (
    "Makefile",
    "README.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
)
EXCLUDED_SCAN_PREFIXES = (
    "ops/reports/",
    "ops/operator/",
    "tmp/",
    "build/",
    "runs/",
    "raw/",
    "wiki/",
    "system/",
    "external-reports/",
)
EXCLUDED_SCAN_PATHS = {
    "ops/scripts/core/artifact_relocation_audit.py",
}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".mk",
    ".py",
    ".pyi",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
DEFAULT_RELOCATION_CANDIDATES = [
    {
        "artifact_name": "operator-release-summary.json",
        "classification": "operator_only",
        "old_path": "ops/reports/operator-release-summary.json",
        "new_path": "ops/operator/operator-release-summary.json",
        "reason": "Operator-readable summary is intentionally outside release authority sealing inventory.",
    }
]


def _dependency_file_paths(vault: Path) -> list[Path]:
    paths: list[Path] = []
    for rel_path in ROOT_DEPENDENCY_FILES:
        path = vault / rel_path
        if path.is_file():
            paths.append(path)
    for root in DEPENDENCY_ROOTS:
        root_path = vault / root
        if not root_path.exists():
            continue
        paths.extend(path for path in root_path.rglob("*") if path.is_file())
    unique: dict[str, Path] = {}
    for path in paths:
        rel_path = report_path(vault, path)
        if rel_path in EXCLUDED_SCAN_PATHS:
            continue
        if rel_path.startswith(EXCLUDED_SCAN_PREFIXES):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        unique[rel_path] = path
    return [unique[key] for key in sorted(unique)]


def _line_matches(path: Path, needle: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return matches
    for line_number, line in enumerate(text.splitlines(), start=1):
        if needle not in line:
            continue
        matches.append(
            {
                "line": line_number,
                "excerpt": line.strip()[:240],
            }
        )
    return matches


def _references(vault: Path, dependency_paths: list[Path], needle: str) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for path in dependency_paths:
        matches = _line_matches(path, needle)
        if not matches:
            continue
        references.append(
            {
                "path": report_path(vault, path),
                "match_count": len(matches),
                "matches": matches,
            }
        )
    return references


def _candidate_status(
    *,
    old_path_exists: bool,
    new_path_exists: bool,
    blocking_reference_count: int,
) -> tuple[str, str, str]:
    if blocking_reference_count:
        return (
            "fail",
            "old_path_references_block_relocation",
            "migrate_or_remove_old_path_references_before_relocation",
        )
    if old_path_exists and new_path_exists:
        return (
            "fail",
            "old_and_new_paths_both_exist",
            "remove_duplicate_old_path_after_validating_new_operator_artifact",
        )
    if old_path_exists:
        return ("attention", "move_ready", "move_artifact_to_declared_operator_path")
    if not new_path_exists:
        return ("attention", "artifact_missing", "generate_or_restore_declared_operator_artifact")
    return ("pass", "relocated", "none")


def _candidate_record(
    vault: Path,
    candidate: dict[str, str],
    dependency_paths: list[Path],
) -> dict[str, Any]:
    old_path = str(candidate["old_path"])
    new_path = str(candidate["new_path"])
    old_references = _references(vault, dependency_paths, old_path)
    new_references = _references(vault, dependency_paths, new_path)
    blocking_reference_count = sum(int(item["match_count"]) for item in old_references)
    status, relocation_status, recommended_next_action = _candidate_status(
        old_path_exists=(vault / old_path).exists(),
        new_path_exists=(vault / new_path).exists(),
        blocking_reference_count=blocking_reference_count,
    )
    return {
        "artifact_name": str(candidate["artifact_name"]),
        "classification": str(candidate["classification"]),
        "old_path": old_path,
        "new_path": new_path,
        "reason": str(candidate["reason"]),
        "status": status,
        "relocation_status": relocation_status,
        "recommended_next_action": recommended_next_action,
        "old_path_exists": (vault / old_path).exists(),
        "new_path_exists": (vault / new_path).exists(),
        "old_reference_count": blocking_reference_count,
        "new_reference_count": sum(int(item["match_count"]) for item in new_references),
        "blocking_references": old_references,
        "new_path_references": new_references,
    }


def _summary(candidate_records: list[dict[str, Any]], dependency_paths: list[Path]) -> dict[str, int]:
    return {
        "candidate_count": len(candidate_records),
        "relocated_count": sum(1 for item in candidate_records if item["relocation_status"] == "relocated"),
        "move_ready_count": sum(1 for item in candidate_records if item["relocation_status"] == "move_ready"),
        "blocking_candidate_count": sum(1 for item in candidate_records if item["status"] == "fail"),
        "old_reference_count": sum(int(item["old_reference_count"]) for item in candidate_records),
        "new_reference_count": sum(int(item["new_reference_count"]) for item in candidate_records),
        "dependency_file_count": len(dependency_paths),
    }


def _status(candidate_records: list[dict[str, Any]]) -> str:
    if any(item["status"] == "fail" for item in candidate_records):
        return "fail"
    if any(item["status"] == "attention" for item in candidate_records):
        return "attention"
    return "pass"


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    candidates: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    dependency_paths = _dependency_file_paths(vault)
    active_candidates = candidates or DEFAULT_RELOCATION_CANDIDATES
    candidate_records = [
        _candidate_record(vault, candidate, dependency_paths)
        for candidate in active_candidates
    ]
    summary = _summary(candidate_records, dependency_paths)
    status = _status(candidate_records)
    generated_at = runtime_context.isoformat_z()
    dependency_rel_paths = [report_path(vault, path) for path in dependency_paths]
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="artifact_relocation_audit",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=ARTIFACT_RELOCATION_AUDIT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/artifact_relocation_audit.py",
                "ops/schemas/artifact-relocation-audit.schema.json",
            ],
            text_inputs={
                "candidate_spec": json.dumps(active_candidates, sort_keys=True),
                "dependency_paths": "\n".join(dependency_rel_paths),
                "dependency_roots": "\n".join([*ROOT_DEPENDENCY_FILES, *DEPENDENCY_ROOTS]),
                "excluded_scan_prefixes": "\n".join(EXCLUDED_SCAN_PREFIXES),
                "excluded_scan_paths": "\n".join(sorted(EXCLUDED_SCAN_PATHS)),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "recommended_next_action": (
            "none"
            if status == "pass"
            else "migrate_or_remove_old_path_references_before_relocation"
            if status == "fail"
            else "complete_ready_operator_artifact_moves"
        ),
        "relocation_rules": [
            {
                "rule_id": "old_path_reference_free",
                "description": "A moved operator-only artifact must have zero references to its old ops/reports path in dependency surfaces.",
                "gate_effect": "blocking",
            },
            {
                "rule_id": "single_declared_location",
                "description": "An audited artifact must not exist in both the old and new locations.",
                "gate_effect": "blocking",
            },
        ],
        "dependency_scan": {
            "roots": [*ROOT_DEPENDENCY_FILES, *DEPENDENCY_ROOTS],
            "excluded_prefixes": list(EXCLUDED_SCAN_PREFIXES),
            "file_count": len(dependency_paths),
            "files": dependency_rel_paths,
        },
        "summary": summary,
        "candidates": candidate_records,
        "blocking_references": [
            {
                "candidate": item["artifact_name"],
                "old_path": item["old_path"],
                "references": item["blocking_references"],
            }
            for item in candidate_records
            if item["blocking_references"]
        ],
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=ARTIFACT_RELOCATION_AUDIT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="artifact relocation audit schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit generated artifact relocations before operator-surface moves")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--fail-on-fail", action="store_true")
    parser.add_argument("--fail-on-attention", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.fail_on_attention and report["status"] != "pass":
        return 1
    if args.fail_on_fail and report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
