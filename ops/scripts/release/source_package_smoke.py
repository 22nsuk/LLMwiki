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
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "build/source-package-smoke/source-package-smoke.json"
DEFAULT_EXTRACT_PARENT = "build/source-package-smoke/extract"
DEFAULT_SOURCE_ZIP = "build/release/LLMwiki-source.zip"
SCHEMA_PATH = "ops/schemas/source-package-smoke.schema.json"
PRODUCER = "ops.scripts.source_package_smoke"
SOURCE_COMMAND = "python -m ops.scripts.source_package_smoke --vault ."
ARCHIVE_SELF_DESCRIPTION_PATH = "release-archive-self-description.json"


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
        "duration_ms": int(round((time.monotonic() - started) * 1000)),
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
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "source_package_smoke",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": "",
        "source_tree_fingerprint": release_source_tree_fingerprint(vault),
        "input_fingerprints": {"source_zip": _file_identity(vault, source_zip_path)["sha256"]},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_evidence",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "source_zip": _file_identity(vault, source_zip_path),
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
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
