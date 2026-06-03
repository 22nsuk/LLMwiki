#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import TimedProcessResult, run_with_timeout
    from ops.scripts.export_public_repo import DEFAULT_PUBLIC_OUT, export_public_repo
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.public_surface_policy import PUBLIC_INCLUDED_REPORT_FILES
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.test_execution_summary import parse_pytest_counts
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.command_runtime import TimedProcessResult, run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.test_execution_summary import parse_pytest_counts

    from .export_public_repo import DEFAULT_PUBLIC_OUT, export_public_repo
    from .public_surface_policy import PUBLIC_INCLUDED_REPORT_FILES


DEFAULT_OUT = "ops/reports/public-check-summary.json"
PRODUCER = "ops.scripts.public_check_summary"
SCHEMA_PATH = "ops/schemas/public-check-summary.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.public_check_summary --vault ."
DEFAULT_TIMEOUT_SECONDS = 5400
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
TAIL_LINE_COUNT = 80
PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH = "ops/reports/test-execution-summary-public.json"
PUBLIC_PYTEST_SUMMARY_CACHE_DIRNAME = "tmp-public-check-summary-cache"
CommandRunner = Callable[[Sequence[str], Path, int], TimedProcessResult]
PRIVATE_EXPORT_PATTERNS = (
    "raw/",
    "wiki/",
    "system/",
    "runs/",
    "external-reports/",
    "AGENTS.local.md",
    "ops/manifest.json",
    "ops/operator/",
    "ops/raw-registry.json",
    "ops/reports/",
)


@dataclass(frozen=True)
class PublicCheckRequest:
    public_out: str = DEFAULT_PUBLIC_OUT
    public_python: str = sys.executable
    ruff_targets: str = "ops/scripts tests tools"
    mypy_targets: str = "ops/scripts"
    pytest_mark_expr: str = "public"
    pytest_flags: str = ""
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _tail_text(text: str, max_lines: int = TAIL_LINE_COUNT) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def _display_external_path(path: Path, vault: Path) -> str:
    resolved = path.resolve()
    try:
        resolved.relative_to(vault.resolve())
    except ValueError:
        temp_root = Path(tempfile.gettempdir()).resolve()
        try:
            rel = resolved.relative_to(temp_root)
            return str(Path("<tmp>") / rel)
        except ValueError:
            return f"<external>/{resolved.name}"
    return report_path(vault, resolved)


def _resolve_out_dir(vault: Path, out_dir: str) -> Path:
    path = Path(out_dir)
    if path.is_absolute():
        return path
    return (vault / path).resolve()


def _resolve_public_python(vault: Path, public_python: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(public_python))
    if "/" not in expanded and "\\" not in expanded:
        return expanded
    path = Path(expanded)
    if path.is_absolute():
        return str(path)
    return str((vault / path).absolute())


def _export_file_records(public_out: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rel_paths = [str(path) for path in manifest.get("files", []) if str(path).strip()]
    manifest_file = str(manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json"))
    records = []
    for rel_path in [*rel_paths, manifest_file]:
        path = public_out / rel_path
        records.append(
            {
                "path": rel_path,
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": _sha256_file(path) if path.is_file() else "",
            }
        )
    return records


def _read_public_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _public_pytest_summary_path(public_out: Path) -> Path:
    return public_out / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH


def _public_pytest_summary_cache_path() -> Path:
    return Path(tempfile.gettempdir()) / PUBLIC_PYTEST_SUMMARY_CACHE_DIRNAME / Path(
        PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH
    ).name


def _persist_public_pytest_summary(temp_summary_path: Path, cache_path: Path) -> None:
    try:
        payload = temp_summary_path.read_bytes()
    except OSError:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(payload)


def _remove_optional_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _pytest_public_summary_suite(pytest_mark_expr: str) -> str:
    return "public" if pytest_mark_expr.strip() == "public" else "pytest"


def _pytest_public_summary_command(
    *,
    public_python: str,
    request: PublicCheckRequest,
    reuse_from: Path,
) -> tuple[list[str], Path]:
    pytest_command = [public_python, "-m", "pytest"]
    if request.pytest_mark_expr.strip():
        pytest_command.extend(["-m", request.pytest_mark_expr])
    pytest_command.extend(shlex.split(request.pytest_flags))
    summary_rel_path = Path(PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH)
    return (
        [
            public_python,
            "-m",
            "ops.scripts.test_execution_summary",
            "--vault",
            ".",
            "--out",
            summary_rel_path.as_posix(),
            "--suite",
            _pytest_public_summary_suite(request.pytest_mark_expr),
            "--timeout-seconds",
            str(request.timeout_seconds),
            "--reuse-if-current",
            "--reuse-from",
            reuse_from.as_posix(),
            "--",
            *pytest_command,
        ],
        summary_rel_path,
    )


def _pytest_public_summary_counts(summary_path: Path | None) -> dict[str, int]:
    if summary_path is None:
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        return {}
    normalized: dict[str, int] = {}
    for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed", "warnings"):
        try:
            normalized[key] = int(counts.get(key, 0) or 0)
        except (TypeError, ValueError):
            normalized[key] = 0
    return normalized


def _public_export_negative_assertions(
    public_out: Path,
    manifest: dict[str, Any],
    file_records: list[dict[str, Any]],
    *,
    source_vault: Path,
) -> dict[str, Any]:
    exported_paths = [str(record["path"]) for record in file_records]
    excluded_prefixes = tuple(
        str(prefix)
        for prefix in manifest.get("excluded_prefixes", [])
        if str(prefix).strip()
    )
    excluded_files = {
        str(path)
        for path in manifest.get("excluded_files", [])
        if str(path).strip()
    }
    policy_report_exceptions = {
        str(path)
        for path in manifest.get("included_report_files", PUBLIC_INCLUDED_REPORT_FILES)
        if str(path).strip()
    }
    excluded_prefix_violations = sorted(
        path
        for path in exported_paths
        if path not in policy_report_exceptions
        and any(path.startswith(prefix) for prefix in excluded_prefixes)
    )
    private_pattern_violations = sorted(
        path
        for path in exported_paths
        if path not in policy_report_exceptions
        and (path in excluded_files or any(path.startswith(pattern) for pattern in PRIVATE_EXPORT_PATTERNS))
    )
    source_vault_marker = source_vault.resolve().as_posix()
    local_path_violations = sorted(
        path
        for path in exported_paths
        if source_vault_marker and source_vault_marker in _read_public_text(public_out / path)
    )

    def assertion_payload(violations: list[str]) -> dict[str, Any]:
        return {
            "status": "pass" if not violations else "fail",
            "violation_count": len(violations),
            "violations": violations,
        }

    return {
        "excluded_prefix_absence": assertion_payload(excluded_prefix_violations),
        "local_path_absence": assertion_payload(local_path_violations),
        "private_pattern_absence": assertion_payload(private_pattern_violations),
    }


def _public_export_boundary_status(
    vault: Path,
    public_out: Path,
    manifest: dict[str, Any],
    negative_assertions: dict[str, Any],
) -> dict[str, str]:
    manifest_file = str(manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json"))
    try:
        public_out.resolve().relative_to(vault.resolve())
        outside_source_vault = False
    except ValueError:
        outside_source_vault = True
    materialized = public_out.is_dir() and (public_out / manifest_file).is_file()
    has_git_history = (public_out / ".git").exists()
    negative_clean = _negative_assertion_status(negative_assertions) == "pass"
    return {
        "physical_repo_split_status": "pass"
        if materialized and outside_source_vault
        else "fail",
        "private_surface_history_absence_status": "pass"
        if materialized and not has_git_history and negative_clean
        else "fail",
    }


def _default_command_runner(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: int,
    *,
    public_python: str,
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> TimedProcessResult:
    env = dict(os.environ)
    env["PYTHON"] = public_python
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    heartbeat_callback = (lambda _event: None) if heartbeat_interval_seconds else None
    return run_with_timeout(
        argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        env=env,
        heartbeat_interval_seconds=heartbeat_interval_seconds or None,
        heartbeat_callback=heartbeat_callback,
    )


def _command_record(
    *,
    command_id: str,
    argv: list[str],
    cwd: Path,
    display_vault: Path,
    timeout_seconds: int,
    command_runner: CommandRunner,
    pytest_summary_path: Path | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = command_runner(argv, cwd, timeout_seconds)
    duration_ms = int((time.perf_counter() - started) * 1000)
    counts = {}
    if command_id == "pytest_public":
        counts = _pytest_public_summary_counts(pytest_summary_path)
        if not counts:
            counts = parse_pytest_counts(result.stdout, result.stderr)
    return {
        "id": command_id,
        "command": shlex.join([sanitize_report_text(display_vault, str(arg)) for arg in argv]),
        "cwd": ".",
        "status": "pass" if result.returncode == 0 and not result.timed_out else "fail",
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "timeout_seconds": result.timeout_seconds,
        "termination_reason": result.termination_reason,
        "signal_sent": result.signal_sent or "none",
        "final_state_observed": result.final_state_observed or "unknown",
        "duration_ms": duration_ms,
        "heartbeat_count": result.heartbeat_count,
        "heartbeat_interval_seconds": result.heartbeat_interval_seconds,
        "quiet_seconds": result.quiet_seconds,
        "observation_mode": result.observation_mode,
        "stdout_tail": sanitize_report_text(display_vault, _tail_text(result.stdout)),
        "stderr_tail": sanitize_report_text(display_vault, _tail_text(result.stderr)),
        "pytest_counts": counts,
    }


def _overall_status(commands: list[dict[str, Any]]) -> str:
    if any(command["timed_out"] for command in commands):
        return "timeout"
    if any(command["returncode"] in {130, -2} for command in commands):
        return "interrupted"
    return "pass" if all(command["status"] == "pass" for command in commands) else "fail"


def _negative_assertion_status(assertions: dict[str, Any]) -> str:
    for assertion in assertions.values():
        if isinstance(assertion, dict) and assertion.get("status") != "pass":
            return "fail"
    return "pass"


def _public_pytest_command(commands: list[dict[str, Any]]) -> dict[str, Any]:
    for command in commands:
        if command.get("id") == "pytest_public":
            return command
    return {}


def build_report(
    vault: Path,
    request: PublicCheckRequest | None = None,
    *,
    context: RuntimeContext | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    request = request or PublicCheckRequest()
    policy, resolved_policy_path = load_policy(vault, None)
    runtime_context = context or RuntimeContext.from_policy(policy)
    public_out_path = _resolve_out_dir(vault, request.public_out)
    manifest = export_public_repo(vault, public_out_path)
    export_records = _export_file_records(public_out_path, manifest)
    negative_assertions = _public_export_negative_assertions(
        public_out_path,
        manifest,
        export_records,
        source_vault=vault,
    )
    boundary_status = _public_export_boundary_status(
        vault,
        public_out_path,
        manifest,
        negative_assertions,
    )
    export_root_fingerprint = _canonical_sha256(export_records)
    manifest_path = public_out_path / str(manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json"))
    pytest_summary_path = _public_pytest_summary_path(public_out_path)
    pytest_summary_cache_path = _public_pytest_summary_cache_path()
    runner = command_runner or (
        lambda argv, cwd, timeout_seconds: _default_command_runner(
            argv,
            cwd,
            timeout_seconds,
            public_python=public_python,
            heartbeat_interval_seconds=request.heartbeat_interval_seconds,
        )
    )
    public_python = _resolve_public_python(vault, request.public_python)
    pytest_summary_command, pytest_summary_relative_path = _pytest_public_summary_command(
        public_python=public_python,
        request=request,
        reuse_from=pytest_summary_cache_path,
    )
    commands_to_run: list[tuple[str, list[str], Path | None]] = [
        (
            "ruff",
            [public_python, "-m", "ruff", "check", *shlex.split(request.ruff_targets)],
            None,
        ),
        (
            "mypy",
            [public_python, "-m", "mypy", *shlex.split(request.mypy_targets)],
            None,
        ),
        (
            "pytest_public",
            pytest_summary_command,
            public_out_path / pytest_summary_relative_path,
        ),
    ]
    commands = [
        _command_record(
            command_id=command_id,
            argv=argv,
            cwd=public_out_path,
            display_vault=vault,
            timeout_seconds=request.timeout_seconds,
            command_runner=runner,
            pytest_summary_path=pytest_summary_path,
        )
        for command_id, argv, pytest_summary_path in commands_to_run
    ]
    _persist_public_pytest_summary(pytest_summary_path, pytest_summary_cache_path)
    _remove_optional_file(pytest_summary_path)
    command_status = _overall_status(commands)
    assertion_status = _negative_assertion_status(negative_assertions)
    status = command_status if command_status != "pass" else assertion_status
    pytest_counts = commands[-1].get("pytest_counts", {})
    public_pytest_command = _public_pytest_command(commands)
    source_paths = [
        "Makefile",
        "ops/scripts/public/public_check_summary.py",
        "ops/scripts/public/export_public_repo.py",
        "ops/scripts/public/public_surface_policy.py",
        "ops/scripts/test_execution_summary.py",
    ]
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="public_check_summary",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=source_paths,
            path_group_inputs={
                "public_check_summary_inputs": [
                    "Makefile",
                    "ops/scripts/public/export_public_repo.py",
                    "ops/scripts/public/public_surface_policy.py",
                ]
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": status,
        "summary": {
            "public_export_status": "pass",
            "public_check_status": status,
            "export_file_count": _int_value(manifest.get("file_count", 0)),
            "export_source_file_count": _int_value(manifest.get("source_file_count", 0)),
            "export_root_fingerprint": export_root_fingerprint,
            "public_export_manifest_sha256": _sha256_file(manifest_path),
            "public_surface_policy_sha256": _sha256_file(vault / "ops/scripts/public/public_surface_policy.py"),
            "command_count": len(commands),
            "command_fail_count": sum(1 for command in commands if command["status"] != "pass"),
            "negative_assertion_fail_count": sum(
                1
                for assertion in negative_assertions.values()
                if isinstance(assertion, dict) and assertion.get("status") != "pass"
            ),
            **boundary_status,
            "pytest_passed": int(pytest_counts.get("passed", 0) or 0),
            "pytest_failed": int(pytest_counts.get("failed", 0) or 0),
            "pytest_errors": int(pytest_counts.get("errors", 0) or 0),
            "pytest_skipped": int(pytest_counts.get("skipped", 0) or 0),
            "timeout_command_count": sum(1 for command in commands if command["timed_out"]),
            "max_command_heartbeat_count": max(
                (int(command.get("heartbeat_count", 0) or 0) for command in commands),
                default=0,
            ),
            "max_command_quiet_seconds": max(
                (int(command.get("quiet_seconds", 0) or 0) for command in commands),
                default=0,
            ),
            "public_pytest_heartbeat_count": int(public_pytest_command.get("heartbeat_count", 0) or 0),
            "public_pytest_quiet_seconds": int(public_pytest_command.get("quiet_seconds", 0) or 0),
            "public_pytest_termination_reason": str(
                public_pytest_command.get("termination_reason", "not_run")
            ),
            "public_pytest_signal_sent": str(public_pytest_command.get("signal_sent", "none")),
            "public_pytest_final_state_observed": str(
                public_pytest_command.get("final_state_observed", "not_run")
            ),
        },
        "public_export": {
            "output_dir": _display_external_path(public_out_path, vault),
            "manifest_file": str(manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json")),
            "file_count": _int_value(manifest.get("file_count", 0)),
            "source_file_count": _int_value(manifest.get("source_file_count", 0)),
            "export_root_fingerprint": export_root_fingerprint,
            "manifest_sha256": _sha256_file(manifest_path),
        },
        "public_export_negative_assertions": negative_assertions,
        "commands": commands,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="public check summary schema validation failed",
        )
    )


def reusable_summary_diagnostics(vault: Path, path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = vault / path
    diagnostics: dict[str, Any] = {
        "reusable": False,
        "path": report_path(vault, path),
        "reason": "",
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        diagnostics["reason"] = f"summary_unavailable:{type(exc).__name__}"
        return diagnostics
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    checks = {
        "artifact_kind": payload.get("artifact_kind") == "public_check_summary",
        "producer": payload.get("producer") == PRODUCER,
        "status": payload.get("status") == "pass",
        "public_check_status": summary.get("public_check_status") == "pass",
        "source_tree_fingerprint": payload.get("source_tree_fingerprint") == current_source_tree_fingerprint,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        diagnostics["reason"] = f"not_current:{','.join(failed)}"
        diagnostics["checks"] = checks
        diagnostics["current_source_tree_fingerprint"] = current_source_tree_fingerprint
        diagnostics["observed_source_tree_fingerprint"] = str(payload.get("source_tree_fingerprint", ""))
        return diagnostics
    diagnostics.update(
        {
            "reusable": True,
            "reason": "current_passing_public_check_summary",
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
        }
    )
    return diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run public mirror checks and write a canonical summary.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--public-out", default=DEFAULT_PUBLIC_OUT)
    parser.add_argument("--public-python", default=sys.executable)
    parser.add_argument("--ruff-targets", default="ops/scripts tests tools")
    parser.add_argument("--mypy-targets", default="ops/scripts")
    parser.add_argument("--pytest-mark-expr", default="public")
    parser.add_argument("--pytest-flags", default="")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
    parser.add_argument("--reuse-if-current", action="store_true")
    parser.add_argument("--reuse-from")
    parser.add_argument(
        "--reuse-only",
        action="store_true",
        help="With --reuse-if-current, fail instead of rerunning when the public-check summary is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.reuse_only:
        args.reuse_if_current = True
    vault = Path(args.vault).resolve()
    if args.reuse_if_current:
        diagnostics = reusable_summary_diagnostics(vault, args.reuse_from or args.out)
        if diagnostics["reusable"]:
            print(json.dumps({"summary_mode": "reused", **diagnostics}, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({"summary_mode": "executed", "reuse_diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        if args.reuse_only:
            return 1
    report = build_report(
        vault,
        PublicCheckRequest(
            public_out=args.public_out,
            public_python=args.public_python,
            ruff_targets=args.ruff_targets,
            mypy_targets=args.mypy_targets,
            pytest_mark_expr=args.pytest_mark_expr,
            pytest_flags=args.pytest_flags,
            timeout_seconds=args.timeout_seconds,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        ),
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
