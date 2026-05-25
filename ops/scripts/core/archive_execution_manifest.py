#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        read_json_object,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        ARCHIVE_EXECUTION_MANIFEST_SCHEMA_PATH,
    )
else:
    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        read_json_object,
        write_schema_backed_report,
    )
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import ARCHIVE_EXECUTION_MANIFEST_SCHEMA_PATH


DEFAULT_OUT = "tmp/archive-execution-manifest.json"
DEFAULT_INDEX_PATH = "ops/reports/generated-artifact-index.json"
PRODUCER = "ops.scripts.archive_execution_manifest"
APPLY_CONFIRMATION = "CONFIRM_ARCHIVE_EXECUTION"
ROLLBACK_CONFIRMATION = "CONFIRM_ARCHIVE_ROLLBACK"


def _move_type(path: Path) -> str:
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    if not path.exists():
        return "missing"
    return "unknown"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda candidate: candidate.relative_to(path).as_posix()):
        relative = item.relative_to(path).as_posix()
        if item.is_dir():
            digest.update(f"dir:{relative}\n".encode())
            continue
        if item.is_file():
            digest.update(f"file:{relative}:".encode())
            digest.update(_file_digest(item).encode("ascii"))
            digest.update(b"\n")
            continue
        digest.update(f"unknown:{relative}\n".encode())
    return digest.hexdigest()


def _path_digest(path: Path, move_type: str) -> str:
    if move_type == "file":
        return _file_digest(path)
    if move_type == "directory":
        return _directory_digest(path)
    return ""


def _path_evidence(vault: Path, label: str, path: Path) -> str:
    move_type = _move_type(path)
    digest = _path_digest(path, move_type)
    digest_fragment = f" sha256={digest}" if digest else ""
    return f"{label}: path={report_path(vault, path)} type={move_type}{digest_fragment}"


def _operation_status(
    *,
    vault: Path,
    apply: bool,
    source: Path,
    destination: Path,
    move_type: str,
    operator_confirmation: str,
) -> tuple[str, list[str]]:
    if not apply:
        return "planned", ["dry-run only; no filesystem changes were made"]
    if operator_confirmation != APPLY_CONFIRMATION:
        return (
            "blocked",
            [
                f"operator confirmation must equal {APPLY_CONFIRMATION}",
                _path_evidence(vault, "source_before_apply", source),
                _path_evidence(vault, "destination_before_apply", destination),
            ],
        )
    if move_type == "missing":
        return (
            "blocked",
            [
                "source path is missing",
                _path_evidence(vault, "source_before_apply", source),
                _path_evidence(vault, "destination_before_apply", destination),
            ],
        )
    if move_type == "unknown":
        return (
            "blocked",
            [
                "source path is neither a file nor a directory",
                _path_evidence(vault, "source_before_apply", source),
                _path_evidence(vault, "destination_before_apply", destination),
            ],
        )
    if destination.exists():
        return (
            "blocked",
            [
                "destination path already exists",
                _path_evidence(vault, "source_before_apply", source),
                _path_evidence(vault, "destination_before_apply", destination),
            ],
        )
    evidence = [
        _path_evidence(vault, "source_before_apply", source),
        _path_evidence(vault, "destination_before_apply", destination),
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.move(source.as_posix(), destination.as_posix())
    else:
        shutil.move(source.as_posix(), destination.as_posix())
    evidence.extend(
        [
            "filesystem move completed",
            _path_evidence(vault, "source_after_apply", source),
            _path_evidence(vault, "destination_after_apply", destination),
        ]
    )
    return "applied", evidence


def _defer_status(*, vault: Path, source: Path, destination: Path) -> tuple[str, list[str]]:
    return (
        "deferred",
        [
            "operator deferred archive move; no filesystem changes were made",
            _path_evidence(vault, "source_at_defer", source),
            _path_evidence(vault, "destination_at_defer", destination),
        ],
    )


def _rollback_status(
    *,
    vault: Path,
    previous_status: str,
    rollback_available: bool,
    destination: Path,
    rollback_destination: Path,
    operator_confirmation: str,
) -> tuple[str, list[str]]:
    if previous_status != "applied" or not rollback_available:
        return "skipped", ["rollback not available for non-applied move"]
    if operator_confirmation != ROLLBACK_CONFIRMATION:
        return (
            "blocked",
            [
                f"operator confirmation must equal {ROLLBACK_CONFIRMATION}",
                _path_evidence(vault, "destination_before_rollback", destination),
                _path_evidence(vault, "rollback_path_before_rollback", rollback_destination),
            ],
        )

    destination_type = _move_type(destination)
    rollback_destination_type = _move_type(rollback_destination)
    evidence = [
        _path_evidence(vault, "destination_before_rollback", destination),
        _path_evidence(vault, "rollback_path_before_rollback", rollback_destination),
    ]
    if destination_type == "missing" and rollback_destination_type in {"file", "directory"}:
        return "skipped", [*evidence, "rollback already completed"]
    if destination_type == "missing":
        return "blocked", [*evidence, "destination path is missing"]
    if destination_type == "unknown":
        return "blocked", [*evidence, "destination path is neither a file nor a directory"]
    if rollback_destination_type != "missing":
        return "blocked", [*evidence, "rollback path already exists"]

    rollback_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(destination.as_posix(), rollback_destination.as_posix())
    evidence.extend(
        [
            "filesystem rollback move completed",
            _path_evidence(vault, "destination_after_rollback", destination),
            _path_evidence(vault, "rollback_path_after_rollback", rollback_destination),
        ]
    )
    return "rolled_back", evidence


def _move_record(
    vault: Path,
    candidate: dict[str, Any],
    *,
    candidate_index: int,
    apply: bool,
    defer: bool,
    operator_confirmation: str,
) -> dict[str, Any]:
    source_rel = str(candidate.get("path", "")).strip()
    destination_rel = str(candidate.get("suggested_archive_path", "")).strip()
    source = vault / source_rel
    destination = vault / destination_rel
    move_type = _move_type(source)
    if defer:
        execution_status, evidence = _defer_status(vault=vault, source=source, destination=destination)
    else:
        execution_status, evidence = _operation_status(
            vault=vault,
            apply=apply,
            source=source,
            destination=destination,
            move_type=move_type,
            operator_confirmation=operator_confirmation,
        )
    rollback_available = execution_status == "applied" and destination.exists()
    rollback_path = source_rel if rollback_available else ""
    return {
        "candidate_index": candidate_index,
        "surface": str(candidate.get("surface", "")).strip(),
        "family": str(candidate.get("family", "")).strip(),
        "source_path": source_rel,
        "destination_path": destination_rel,
        "move_type": move_type,
        "execution_status": execution_status,
        "reason": str(candidate.get("reason", "")).strip(),
        "decision_relevance": str(candidate.get("decision_relevance", "")).strip(),
        "rollback_path": rollback_path,
        "rollback_available": rollback_available,
        "evidence": evidence,
    }


def _rollback_record(
    vault: Path,
    move: dict[str, Any],
    *,
    candidate_index: int,
    operator_confirmation: str,
) -> dict[str, Any]:
    source_rel = str(move.get("source_path", "")).strip()
    destination_rel = str(move.get("destination_path", "")).strip()
    rollback_rel = str(move.get("rollback_path", "")).strip() or source_rel
    destination = vault / destination_rel
    rollback_destination = vault / rollback_rel
    execution_status, evidence = _rollback_status(
        vault=vault,
        previous_status=str(move.get("execution_status", "")).strip(),
        rollback_available=bool(move.get("rollback_available")),
        destination=destination,
        rollback_destination=rollback_destination,
        operator_confirmation=operator_confirmation,
    )
    rollback_available = (
        str(move.get("execution_status", "")).strip() == "applied"
        and bool(move.get("rollback_available"))
        and destination.exists()
        and not rollback_destination.exists()
    )
    return {
        "candidate_index": int(move.get("candidate_index", candidate_index)),
        "surface": str(move.get("surface", "")).strip(),
        "family": str(move.get("family", "")).strip(),
        "source_path": source_rel,
        "destination_path": destination_rel,
        "move_type": str(move.get("move_type", "")).strip() or _move_type(destination),
        "execution_status": execution_status,
        "reason": str(move.get("reason", "")).strip(),
        "decision_relevance": str(move.get("decision_relevance", "")).strip(),
        "rollback_path": rollback_rel,
        "rollback_available": rollback_available,
        "evidence": evidence,
    }


def _status(moves: list[dict[str, Any]]) -> str:
    if any(item["execution_status"] == "blocked" for item in moves):
        return "fail"
    if any(item["execution_status"] == "planned" for item in moves):
        return "attention"
    return "pass"


def build_report(
    vault: Path,
    *,
    index_path: str = DEFAULT_INDEX_PATH,
    manifest_path: str = DEFAULT_OUT,
    apply: bool = False,
    defer: bool = False,
    rollback: bool = False,
    operator_confirmation: str = "",
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    mode = "rollback" if rollback else "deferred" if defer else "applied" if apply else "dry_run"
    if rollback:
        manifest = read_json_object(vault / manifest_path, context=manifest_path)
        candidates = [item for item in manifest.get("moves", []) if isinstance(item, dict)]
        moves = [
            _rollback_record(
                vault,
                move,
                candidate_index=index,
                operator_confirmation=operator_confirmation,
            )
            for index, move in enumerate(candidates)
        ]
        file_inputs = {"source_manifest": manifest_path}
    else:
        index = read_json_object(vault / index_path, context=index_path)
        candidates = [item for item in index.get("archive_candidates", []) if isinstance(item, dict)]
        moves = [
            _move_record(
                vault,
                candidate,
                candidate_index=index,
                apply=apply,
                defer=defer,
                operator_confirmation=operator_confirmation,
            )
            for index, candidate in enumerate(candidates)
        ]
        file_inputs = {"generated_artifact_index": index_path}
    planned_count = sum(1 for item in moves if item["execution_status"] == "planned")
    applied_count = sum(1 for item in moves if item["execution_status"] == "applied")
    deferred_count = sum(1 for item in moves if item["execution_status"] == "deferred")
    blocked_count = sum(1 for item in moves if item["execution_status"] == "blocked")
    rollback_count = sum(1 for item in moves if item["rollback_available"])
    if rollback:
        source_command = (
            "python -m ops.scripts.archive_execution_manifest --vault . "
            f"--manifest-path {manifest_path} --mode {mode}"
        )
    else:
        source_command = (
            "python -m ops.scripts.archive_execution_manifest --vault . "
            f"--index-path {index_path} --mode {mode}"
        )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="archive_execution_manifest",
            producer=PRODUCER,
            source_command=source_command,
            resolved_policy_path=resolved_policy_path,
            schema_path=ARCHIVE_EXECUTION_MANIFEST_SCHEMA_PATH,
            source_paths=["ops/scripts/archive_execution_manifest.py"],
            file_inputs=file_inputs,
            text_inputs={
                "mode": mode,
                "operator_confirmation_present": "yes" if operator_confirmation else "no",
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": _status(moves),
        "mode": mode,
        "operator_confirmation": operator_confirmation if apply or rollback else "",
        "source_index_path": index_path,
        "summary": {
            "candidate_count": len(candidates),
            "planned_move_count": planned_count,
            "applied_move_count": applied_count,
            "deferred_move_count": deferred_count,
            "blocked_move_count": blocked_count,
            "rollback_available_count": rollback_count,
        },
        "moves": moves,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=ARCHIVE_EXECUTION_MANIFEST_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="archive execution manifest schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an archive execution manifest from archive candidates")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--index-path", default=DEFAULT_INDEX_PATH)
    parser.add_argument("--manifest-path", default=DEFAULT_OUT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=["dry_run", "applied", "deferred", "rollback"], default="dry_run")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operator-confirmation", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    apply = bool(args.apply or args.mode == "applied")
    defer = args.mode == "deferred"
    rollback = args.mode == "rollback"
    report = build_report(
        vault,
        index_path=args.index_path,
        manifest_path=args.manifest_path,
        apply=apply,
        defer=defer,
        rollback=rollback,
        operator_confirmation=args.operator_confirmation,
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
