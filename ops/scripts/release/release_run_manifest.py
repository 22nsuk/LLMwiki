#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "build/release/release-run-manifest.json"
SCHEMA_PATH = "ops/schemas/release-run-manifest.schema.json"
PRODUCER = "ops.scripts.release_run_manifest"
SOURCE_COMMAND = "python -m ops.scripts.release_run_manifest --vault ."
DEFAULT_DISTRIBUTION_ZIP = "build/release/LLMwiki-source.zip"
DEFAULT_SOURCE_PACKAGE_SMOKE = "build/source-package-smoke/source-package-smoke.json"


def _run_git(vault: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=vault,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_commit(vault: Path) -> str:
    return _run_git(vault, "rev-parse", "HEAD")


def git_clean(vault: Path) -> bool:
    return _run_git(vault, "status", "--porcelain") == ""


def remote_sync(vault: Path) -> dict[str, Any]:
    upstream = _run_git(vault, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        return {"status": "unknown", "upstream": "", "ahead": 0, "behind": 0}
    counts = _run_git(vault, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    ahead = int(counts[0]) if len(counts) == 2 and counts[0].isdigit() else 0
    behind = int(counts[1]) if len(counts) == 2 and counts[1].isdigit() else 0
    return {
        "status": "pass" if ahead == 0 and behind == 0 else "fail",
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def ignored_tracked_file_count(vault: Path) -> int:
    output = _run_git(vault, "ls-files", "-ci", "--exclude-standard")
    return len([line for line in output.splitlines() if line.strip()])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(vault: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (vault / path).resolve()


def _file_identity(vault: Path, path_value: str | Path) -> dict[str, Any]:
    path = _resolve(vault, path_value)
    exists = path.is_file()
    return {
        "path": display_path(vault, path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
    }


def _status_label(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("result", "")).strip()
    return str(value).strip()


def _source_package_smoke(vault: Path, path_value: str) -> dict[str, Any]:
    identity = _file_identity(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path_value))
    if diagnostics.get("status") != "ok":
        payload = {}
    return {
        "path": identity["path"],
        "exists": identity["exists"],
        "status": _status_label(payload.get("status")),
        "sha256": identity["sha256"],
    }


def _unique_failures(failures: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for failure in failures:
        if failure and failure not in seen:
            seen.add(failure)
            result.append(failure)
    return result


def build_manifest(
    vault: Path,
    *,
    expected_source_tree_fingerprint: str,
    steps: list[dict[str, Any]] | None = None,
    distribution_zip: str = DEFAULT_DISTRIBUTION_ZIP,
    source_package_smoke: str = DEFAULT_SOURCE_PACKAGE_SMOKE,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    generated_at = runtime_context.isoformat_z()
    final_fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    clean = git_clean(vault)
    remote = remote_sync(vault)
    ignored_count = ignored_tracked_file_count(vault)
    step_rows = list(steps or [])
    zip_identity = _file_identity(vault, distribution_zip)
    smoke = _source_package_smoke(vault, source_package_smoke)
    failures: list[str] = []
    if expected_source_tree_fingerprint != final_fingerprint:
        failures.append("source_tree_fingerprint_drift")
    if not clean:
        failures.append("git_worktree_dirty")
    if ignored_count != 0:
        failures.append("ignored_tracked_files_present")
    if not zip_identity["exists"]:
        failures.append("distribution_zip_missing")
    if not smoke["exists"] or smoke["status"] != "pass":
        failures.append("source_package_smoke_not_pass")
    failures.extend(
        f"step_failed:{step.get('name', 'unknown')}"
        for step in step_rows
        if step.get("status") != "pass"
    )
    status = "pass" if not failures else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_run_manifest",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": final_fingerprint,
        "input_fingerprints": {
            "distribution_zip": zip_identity["sha256"],
            "source_package_smoke": smoke["sha256"],
        },
        "schema_version": 3,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "expected_source_tree_fingerprint": expected_source_tree_fingerprint,
        "final_source_tree_fingerprint": final_fingerprint,
        "git_commit": commit,
        "git_clean": clean,
        "remote_sync": remote,
        "ignored_tracked_file_count": ignored_count,
        "steps": step_rows,
        "distribution_zip": zip_identity,
        "source_package_smoke": smoke,
        "failures": _unique_failures(failures),
    }


def write_manifest(vault: Path, manifest: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release-run manifest schema validation failed",
        )
    )


def load_steps(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("steps JSON must be an array")
    return [item for item in payload if isinstance(item, dict)]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify the release-run manifest.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--expected-source-tree-fingerprint", default="")
    parser.add_argument("--steps-json")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--distribution-zip", default=DEFAULT_DISTRIBUTION_ZIP)
    parser.add_argument("--source-package-smoke", default=DEFAULT_SOURCE_PACKAGE_SMOKE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.check:
        payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, args.out))
        if diagnostics.get("status") != "ok":
            print(json.dumps({"status": "fail", "reason": diagnostics}, ensure_ascii=False, indent=2))
            return 1
        expected = str(payload.get("expected_source_tree_fingerprint", "")).strip()
        steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    else:
        expected = args.expected_source_tree_fingerprint or release_source_tree_fingerprint(vault)
        steps = load_steps(args.steps_json)
    manifest = build_manifest(
        vault,
        expected_source_tree_fingerprint=expected,
        steps=steps,
        distribution_zip=args.distribution_zip,
        source_package_smoke=args.source_package_smoke,
    )
    path = write_manifest(vault, manifest, args.out)
    print(display_path(vault, path))
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - direct script fallback
    raise SystemExit(main())
