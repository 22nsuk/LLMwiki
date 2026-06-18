#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.command_runtime import run_with_timeout
    from ops.scripts.core.output_runtime import display_path, sanitize_report_text
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.core.command_runtime import run_with_timeout
    from ops.scripts.core.output_runtime import display_path, sanitize_report_text
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
    from ops.scripts.core.source_revision_runtime import resolve_source_revision
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "build/source-package-smoke/source-package-smoke.json"
DEFAULT_EXTRACT_PARENT = "build/source-package-smoke/extract"
DEFAULT_SOURCE_ZIP = "build/release/LLMwiki-source.zip"
SCHEMA_PATH = "ops/schemas/source-package-smoke.schema.json"
PRODUCER = "ops.scripts.source_package_smoke"
SOURCE_COMMAND = "python -m ops.scripts.source_package_smoke --vault ."
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(vault: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (vault / path).resolve()


def _file_identity(vault: Path, path: Path) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": display_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
    }


def _archive_root_name(source_zip: Path) -> str:
    with zipfile.ZipFile(source_zip) as archive:
        roots = set()
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/").lstrip("/")
            if "/" in normalized:
                roots.add(normalized.split("/", 1)[0])
            if normalized.endswith(f"/{ARCHIVE_SELF_DESCRIPTION_PATH}"):
                payload = json.loads(archive.read(info.filename).decode("utf-8"))
                root = str(payload.get("archive_root_name", "")).strip()
                if root:
                    return root
        if len(roots) == 1:
            return next(iter(roots))
    return "LLMwiki"


def _extract(source_zip: Path, extract_parent: Path) -> tuple[Path, str]:
    root_name = _archive_root_name(source_zip)
    if extract_parent.exists():
        shutil.rmtree(extract_parent)
    extract_parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_zip) as archive:
        archive.extractall(extract_parent)
    return extract_parent / root_name, root_name


def _tail(text: str, *, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    display_vault: Path,
    temp_roots: list[Path],
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    result = run_with_timeout(command, cwd=cwd, timeout_seconds=timeout_seconds)
    return {
        "name": name,
        "command": [sanitize_report_text(display_vault, item, temp_roots=temp_roots) for item in command],
        "returncode": result.returncode,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "status": "pass" if result.returncode == 0 and not result.timed_out else "fail",
        "stdout_tail": sanitize_report_text(display_vault, _tail(result.stdout), temp_roots=temp_roots),
        "stderr_tail": sanitize_report_text(display_vault, _tail(result.stderr), temp_roots=temp_roots),
    }


def _smoke_commands(python_bin: str, ruff_targets: str, mypy_targets: str) -> list[tuple[str, list[str]]]:
    return [
        (
            "import-runtime",
            [
                python_bin,
                "-c",
                "import ops.scripts.release.release_smoke; import ops.scripts.public.export_public_repo",
            ],
        ),
        ("ruff", [python_bin, "-m", "ruff", "check", *ruff_targets.split()]),
        ("mypy", [python_bin, "-m", "mypy", *mypy_targets.split()]),
        (
            "fast-smoke",
            [
                python_bin,
                "-m",
                "pytest",
                "-q",
                "tests/test_release_run_manifest.py",
                "tests/test_source_tree_fingerprint_runtime.py",
            ],
        ),
    ]


def build_report(
    vault: Path,
    *,
    source_zip: str,
    extract_parent: str,
    source_python: str,
    ruff_targets: str,
    mypy_targets: str,
    timeout_seconds: int,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    source_zip_path = _resolve(vault, source_zip)
    extract_parent_path = _resolve(vault, extract_parent)
    source_revision = resolve_source_revision(vault).revision
    failures: list[str] = []
    commands: list[dict[str, Any]] = []
    extract_root = extract_parent_path / "LLMwiki"
    archive_root_name = "LLMwiki"
    extract_status = "fail"
    if not source_zip_path.is_file():
        failures.append("source_zip_missing")
    else:
        try:
            extract_root, archive_root_name = _extract(source_zip_path, extract_parent_path)
            extract_status = "pass" if extract_root.is_dir() else "fail"
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            failures.append(f"extract_failed:{type(exc).__name__}")
    if extract_status == "pass":
        for name, command in _smoke_commands(source_python, ruff_targets, mypy_targets):
            result = _run_command(
                name=name,
                command=command,
                cwd=extract_root,
                display_vault=vault,
                temp_roots=[extract_parent_path],
                timeout_seconds=timeout_seconds,
            )
            commands.append(result)
            if result["status"] != "pass":
                failures.append(f"command_failed:{name}")
    status = "pass" if not failures else "fail"
    source_zip_identity = _file_identity(vault, source_zip_path)
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "source_package_smoke",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": source_revision,
        "source_tree_fingerprint": release_source_tree_fingerprint(vault),
        "input_fingerprints": {
            "source_zip": source_zip_identity["sha256"],
            "extract_parent": _sha256_text(display_path(vault, extract_parent_path)),
            "source_python": _sha256_text(source_python),
            "ruff_targets": _sha256_text(ruff_targets),
            "mypy_targets": _sha256_text(mypy_targets),
            "timeout_seconds": _sha256_text(str(timeout_seconds)),
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_evidence",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "source_zip": source_zip_identity,
        "extract": {
            "parent": display_path(vault, extract_parent_path),
            "root": display_path(vault, extract_root),
            "archive_root_name": archive_root_name,
            "status": extract_status,
        },
        "commands": commands,
        "failures": failures,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="source-package smoke schema validation failed",
        )
    )


def reusable_report_diagnostics(
    vault: Path,
    path_value: str | Path,
    *,
    source_zip: str,
    extract_parent: str,
    source_python: str,
    ruff_targets: str,
    mypy_targets: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    path = _resolve(vault, path_value)
    diagnostics: dict[str, Any] = {
        "reusable": False,
        "path": display_path(vault, path),
        "reason": "",
    }
    payload, load_diagnostics = load_optional_json_object_with_diagnostics(path)
    if load_diagnostics.get("status") != "ok":
        diagnostics["reason"] = f"report_unavailable:{load_diagnostics.get('status', 'unknown')}"
        return diagnostics
    schema_errors = validate_with_schema(payload, load_schema(vault / SCHEMA_PATH))
    if schema_errors:
        diagnostics["reason"] = f"schema_invalid:{schema_errors[0]}"
        return diagnostics
    source_zip_path = _resolve(vault, source_zip)
    current_source_revision = resolve_source_revision(vault).revision
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    current_source_zip = _file_identity(vault, source_zip_path)
    extract_parent_path = _resolve(vault, extract_parent)
    expected_input_fingerprints = {
        "source_zip": current_source_zip["sha256"],
        "extract_parent": _sha256_text(display_path(vault, extract_parent_path)),
        "source_python": _sha256_text(source_python),
        "ruff_targets": _sha256_text(ruff_targets),
        "mypy_targets": _sha256_text(mypy_targets),
        "timeout_seconds": _sha256_text(str(timeout_seconds)),
    }
    checks = {
        "artifact_kind": payload.get("artifact_kind") == "source_package_smoke",
        "producer": payload.get("producer") == PRODUCER,
        "status": payload.get("status") == "pass",
        "currentness": isinstance(payload.get("currentness"), dict)
        and payload["currentness"].get("status") == "current",
        "source_revision": payload.get("source_revision") == current_source_revision,
        "source_tree_fingerprint": payload.get("source_tree_fingerprint") == current_source_tree_fingerprint,
        "source_zip_exists": isinstance(payload.get("source_zip"), dict)
        and payload["source_zip"].get("exists") is True,
        "source_zip_sha256": isinstance(payload.get("source_zip"), dict)
        and payload["source_zip"].get("sha256") == current_source_zip["sha256"],
        "input_fingerprints": payload.get("input_fingerprints") == expected_input_fingerprints,
        "extract_parent": isinstance(payload.get("extract"), dict)
        and payload["extract"].get("parent") == display_path(vault, extract_parent_path),
        "source_command": payload.get("source_command") == SOURCE_COMMAND,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        diagnostics["reason"] = f"not_current:{','.join(failed)}"
        diagnostics["checks"] = checks
        diagnostics["semantic_inputs"] = {
            "source_python": source_python,
            "ruff_targets": ruff_targets,
            "mypy_targets": mypy_targets,
            "timeout_seconds": int(timeout_seconds),
            "extract_parent": display_path(vault, extract_parent_path),
        }
        return diagnostics
    diagnostics.update(
        {
            "reusable": True,
            "reason": "current_passing_source_package_smoke",
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
        }
    )
    return diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a clean release source package extract.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--source-zip", default=DEFAULT_SOURCE_ZIP)
    parser.add_argument("--extract-parent", default=DEFAULT_EXTRACT_PARENT)
    parser.add_argument("--source-python", default="python3")
    parser.add_argument("--ruff-targets", default="ops/scripts tests tools")
    parser.add_argument("--mypy-targets", default="ops/scripts")
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--reuse-if-current", action="store_true")
    parser.add_argument("--reuse-from")
    parser.add_argument(
        "--reuse-only",
        action="store_true",
        help="With --reuse-if-current, fail instead of rerunning when source-package smoke evidence is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.reuse_if_current:
        diagnostics = reusable_report_diagnostics(
            vault,
            args.reuse_from or args.out,
            source_zip=args.source_zip,
            extract_parent=args.extract_parent,
            source_python=args.source_python,
            ruff_targets=args.ruff_targets,
            mypy_targets=args.mypy_targets,
            timeout_seconds=args.timeout_seconds,
        )
        if diagnostics["reusable"]:
            print(json.dumps({"summary_mode": "reused", **diagnostics}, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({"summary_mode": "executed", "reuse_diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        if args.reuse_only:
            return 1
    report = build_report(
        vault,
        source_zip=args.source_zip,
        extract_parent=args.extract_parent,
        source_python=args.source_python,
        ruff_targets=args.ruff_targets,
        mypy_targets=args.mypy_targets,
        timeout_seconds=args.timeout_seconds,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - direct script fallback
    raise SystemExit(main())
