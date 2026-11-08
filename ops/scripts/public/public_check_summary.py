#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_envelope_runtime import (
        local_corpus_policy_is_current,
    )
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        promote_schema_validated_json,
        write_schema_backed_report,
    )
    from ops.scripts.core.command_runtime import (
        ProcessCleanupError,
        TimedProcessResult,
        run_with_timeout,
    )
    from ops.scripts.core.output_runtime import (
        display_path,
        resolve_repo_output_path,
        sanitize_report_text,
    )
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.public.export_public_repo import (
        _export_roots,
        _output_lock,
        iter_public_files,
        public_export_session,
    )
    from ops.scripts.public.public_surface_policy import (
        PUBLIC_INCLUDED_REPORT_FILES,
        find_public_local_path_leaks,
        is_public_excluded_path,
    )
    from ops.scripts.public.public_toolchain_runtime import (
        public_check_environment,
        public_python_launcher,
        public_toolchain_fingerprint,
    )
    from ops.scripts.public.source_history_scan_runtime import (
        scan_source_history,
        source_history_state_fingerprint,
    )
    from ops.scripts.test.test_execution_summary import parse_pytest_counts
else:
    from ops.scripts.core.artifact_envelope_runtime import (
        local_corpus_policy_is_current,
    )
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        promote_schema_validated_json,
        write_schema_backed_report,
    )
    from ops.scripts.core.command_runtime import (
        ProcessCleanupError,
        TimedProcessResult,
        run_with_timeout,
    )
    from ops.scripts.core.output_runtime import (
        display_path,
        resolve_repo_output_path,
        sanitize_report_text,
    )
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
    from ops.scripts.test.test_execution_summary import parse_pytest_counts

    from .export_public_repo import (
        _export_roots,
        _output_lock,
        iter_public_files,
        public_export_session,
    )
    from .public_surface_policy import (
        PUBLIC_INCLUDED_REPORT_FILES,
        find_public_local_path_leaks,
        is_public_excluded_path,
    )
    from .public_toolchain_runtime import (
        public_check_environment,
        public_python_launcher,
        public_toolchain_fingerprint,
    )
    from .source_history_scan_runtime import (
        scan_source_history,
        source_history_state_fingerprint,
    )


DEFAULT_OUT = "ops/reports/public-check-summary.json"
PRODUCER = "ops.scripts.public_check_summary"
SCHEMA_PATH = "ops/schemas/public-check-summary.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.public_check_summary --vault ."
FULL_SOURCE_COMMAND = "python -m ops.scripts.public_check_summary --vault . --mode full"
DEFAULT_TIMEOUT_SECONDS = 5400
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
TAIL_LINE_COUNT = 80
PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH = "ops/reports/test-execution-summary-public.json"
PUBLIC_PYTEST_SUMMARY_CACHE_DIRNAME = "tmp-public-check-summary-cache"
PUBLIC_CHECK_CONFIG_FINGERPRINT_KEY = "public_check_config"
PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY = "public_export_source"
SOURCE_HISTORY_STATE_FINGERPRINT_KEY = "source_history_state"
PUBLIC_TOOLCHAIN_FINGERPRINT_KEY = "public_python_toolchain"
CommandRunner = Callable[[Sequence[str], Path, int], TimedProcessResult]


@dataclass(frozen=True)
class PublicCheckRequest:
    mode: str = "default"
    public_out: str = ""
    public_python: str = sys.executable
    ruff_targets: str = "ops/scripts tests tools"
    mypy_targets: str = "ops/scripts"
    pytest_mark_expr: str | None = None
    pytest_flags: str = ""
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    source_history_scan: bool = True

    def __post_init__(self) -> None:
        pytest_mark_expr = self.pytest_mark_expr
        if pytest_mark_expr is None:
            pytest_mark_expr = "" if self.mode == "full" else "public"
        if self.mode == "full" and pytest_mark_expr.strip():
            raise ValueError("full mode requires an empty pytest marker expression")
        object.__setattr__(self, "pytest_mark_expr", pytest_mark_expr)

    @property
    def effective_pytest_mark_expr(self) -> str:
        value = self.pytest_mark_expr
        assert value is not None
        return value


@dataclass(frozen=True)
class _PublicExportSnapshot:
    public_out_path: Path
    manifest: dict[str, Any]
    negative_assertions: dict[str, Any]
    boundary_status: dict[str, str]
    export_root_fingerprint: str
    manifest_path: Path


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_text(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


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


def _expanduser_preserving_unresolved_home(value: str) -> str:
    if not value.startswith("~"):
        return value
    try:
        return str(Path(value).expanduser())
    except RuntimeError:
        return value


def _resolve_public_python(vault: Path, public_python: str) -> str:
    expanded = os.path.expandvars(_expanduser_preserving_unresolved_home(public_python))
    if "/" not in expanded and "\\" not in expanded:
        return expanded
    path = Path(expanded)
    if path.is_absolute():
        return str(path)
    return str((vault / path).absolute())


def _export_file_records(
    public_out: Path, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
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


def _export_inventory_is_current(public_out: Path, manifest: dict[str, Any]) -> bool:
    """Check physical entries, including those omitted by the source export filter."""
    expected_files = {
        *manifest["files"],
        str(manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json")),
    }
    expected_dirs = {
        parent.as_posix()
        for relative in expected_files
        for parent in Path(relative).parents
    }
    # The temporary pytest summary is removed after collection, leaving its parents.
    summary_dirs = {
        parent.as_posix() for parent in Path(PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH).parents
    }
    allowed_dirs = expected_dirs | summary_dirs
    root_caches = {".ruff_cache", ".mypy_cache", ".pytest_cache", ".hypothesis"}
    seen_files: set[str] = set()
    pending = [(public_out, False)]
    try:
        while pending:
            directory, in_cache = pending.pop()
            for path in directory.iterdir():
                relative = path.relative_to(public_out).as_posix()
                mode = path.lstat().st_mode
                if stat.S_ISDIR(mode):
                    cache = (
                        in_cache
                        or relative in root_caches
                        or (
                            path.name == "__pycache__"
                            and path.parent.relative_to(public_out).as_posix() in expected_dirs
                        )
                    )
                    if not cache and relative not in allowed_dirs:
                        return False
                    pending.append((path, cache))
                elif stat.S_ISREG(mode):
                    if relative in expected_files:
                        seen_files.add(relative)
                    elif not in_cache:
                        return False
                else:
                    # No links (even within caches), sockets, or other special files.
                    return False
    except OSError:
        return False
    return seen_files == expected_files


def _read_public_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _public_pytest_summary_path(public_out: Path) -> Path:
    return public_out / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH


def _public_export_source_inputs(vault: Path) -> str:
    # Release manifests deliberately omit some public inputs, including generated
    # registries. Use the exporter's selection and fail if selected bytes cannot be read.
    return _canonical_json_text({
        relative: hashlib.sha256((vault / relative).read_bytes()).hexdigest()
        for relative in iter_public_files(vault)
    })


def _public_pytest_summary_cache_path(
    vault: Path, request: PublicCheckRequest, *, toolchain: str | None = None,
    source_identity: str | None = None, public_source_inputs: str | None = None,
) -> Path:
    if toolchain is None:
        with _toolchain_workspace(vault, request) as output:
            toolchain = _export_toolchain_fingerprint(vault, request, output)
    if source_identity is None:
        source_identity = release_source_tree_fingerprint(vault)
    if public_source_inputs is None:
        public_source_inputs = _public_export_source_inputs(vault)
    key = _canonical_sha256({
        "source": str(vault.resolve()),
        "tree": source_identity,
        PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY: public_source_inputs,
        "config": _public_check_config_payload(vault, request),
        PUBLIC_TOOLCHAIN_FINGERPRINT_KEY: toolchain,
    })
    return (
        Path(tempfile.gettempdir())
        / PUBLIC_PYTEST_SUMMARY_CACHE_DIRNAME
        / key
        / Path(PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH).name
    )


def _persist_public_pytest_summary(payload: bytes | None, cache_path: Path) -> None:
    if payload is None:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # Writers using the same input key must never expose a partial cache file.
    fd, staged = tempfile.mkstemp(dir=cache_path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        Path(staged).replace(cache_path)
    finally:
        Path(staged).unlink(missing_ok=True)


def _remove_optional_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _pytest_public_summary_suite(pytest_mark_expr: str) -> str:
    return "public" if pytest_mark_expr.strip() == "public" else "pytest"


def _public_check_config_payload(
    vault: Path, request: PublicCheckRequest
) -> dict[str, Any]:
    resolved_public_out = _resolve_out_dir(vault, request.public_out).resolve()
    resolved_vault = vault.resolve()
    try:
        public_out_relative_to_vault = resolved_public_out.relative_to(
            resolved_vault
        ).as_posix()
        public_out_boundary = "inside_source_vault"
    except ValueError:
        public_out_relative_to_vault = ""
        public_out_boundary = "outside_source_vault"
    output_config = {
        "boundary": public_out_boundary,
        "relative_to_vault": public_out_relative_to_vault,
        "resolved_path": resolved_public_out.as_posix(),
    } if request.public_out else {"boundary": "invocation_private", "relative_to_vault": "", "resolved_path": ""}
    return {
        "version": 3,
        "mode": request.mode,
        "source_command": _public_check_source_command(request),
        "public_out": output_config,
        "public_python": {
            "identity": _resolve_public_python(vault, request.public_python),
        },
        "ruff": {
            "targets": shlex.split(request.ruff_targets),
        },
        "mypy": {
            "targets": shlex.split(request.mypy_targets),
        },
        "pytest": {
            "flags": shlex.split(request.pytest_flags),
            "mark_expr": request.effective_pytest_mark_expr,
            "summary_suite": _pytest_public_summary_suite(
                request.effective_pytest_mark_expr
            ),
        },
        "timeout_seconds": request.timeout_seconds,
        "heartbeat_interval_seconds": request.heartbeat_interval_seconds,
        "source_history": {
            "requested": request.source_history_scan,
            "ref_scope": "all_refs_and_head" if request.source_history_scan else "none",
        },
    }


def _public_check_config_text(vault: Path, request: PublicCheckRequest) -> str:
    return _canonical_json_text(_public_check_config_payload(vault, request))


def _public_check_config_fingerprint(vault: Path, request: PublicCheckRequest) -> str:
    return _canonical_sha256(_public_check_config_payload(vault, request))


def _public_check_source_command(request: PublicCheckRequest) -> str:
    return FULL_SOURCE_COMMAND if request.mode == "full" else SOURCE_COMMAND


def _pytest_public_summary_command(
    *,
    public_python: str,
    request: PublicCheckRequest,
    reuse_from: Path,
) -> tuple[list[str], Path]:
    pytest_command = [public_python, "-m", "pytest"]
    pytest_mark_expr = request.effective_pytest_mark_expr
    if pytest_mark_expr.strip():
        pytest_command.extend(["-m", pytest_mark_expr])
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
            _pytest_public_summary_suite(pytest_mark_expr),
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
    for key in (
        "passed",
        "failed",
        "errors",
        "skipped",
        "xfailed",
        "xpassed",
        "warnings",
    ):
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
        if path not in policy_report_exceptions and is_public_excluded_path(path)
    )
    source_vault_marker = source_vault.resolve().as_posix()
    local_path_violations: list[str] = []
    for path in exported_paths:
        text = _read_public_text(public_out / path)
        if find_public_local_path_leaks(
            text,
            rel_path=path,
            source_root=source_vault_marker,
        ):
            local_path_violations.append(path)
    local_path_violations.sort()

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
) -> dict[str, str]:
    manifest_file = str(manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json"))
    try:
        public_out.resolve().relative_to(vault.resolve())
        outside_source_vault = False
    except ValueError:
        outside_source_vault = True
    materialized = public_out.is_dir() and (public_out / manifest_file).is_file()
    has_git_history = (public_out / ".git").exists()
    return {
        "physical_repo_split_status": "pass"
        if materialized and outside_source_vault
        else "fail",
        "export_git_metadata_absence_status": "pass"
        if materialized and not has_git_history
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
    heartbeat_callback = (lambda _event: None) if heartbeat_interval_seconds else None
    return run_with_timeout(
        argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        env=public_check_environment(public_python),
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
        "command": shlex.join(
            [sanitize_report_text(display_vault, str(arg)) for arg in argv]
        ),
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
    return (
        "pass" if all(command["status"] == "pass" for command in commands) else "fail"
    )


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


def _collect_public_export_snapshot(
    vault: Path, public_out_path: Path, manifest: dict[str, Any]
) -> _PublicExportSnapshot:
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
    )
    manifest_path = public_out_path / str(
        manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json")
    )
    return _PublicExportSnapshot(
        public_out_path=public_out_path,
        manifest=manifest,
        negative_assertions=negative_assertions,
        boundary_status=boundary_status,
        export_root_fingerprint=_canonical_sha256(export_records),
        manifest_path=manifest_path,
    )


def _public_check_command_specs(
    *,
    public_python: str,
    request: PublicCheckRequest,
    public_out_path: Path,
    pytest_summary_cache_path: Path,
) -> list[tuple[str, list[str], Path | None]]:
    pytest_summary_command, pytest_summary_relative_path = (
        _pytest_public_summary_command(
            public_python=public_python,
            request=request,
            reuse_from=pytest_summary_cache_path,
        )
    )
    return [
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


def _run_public_check_commands(
    vault: Path,
    request: PublicCheckRequest,
    public_out_path: Path,
    command_runner: CommandRunner | None,
    pytest_summary_cache_path: Path,
    *, public_python: str,
) -> tuple[list[dict[str, Any]], bytes | None]:
    pytest_summary_path = _public_pytest_summary_path(public_out_path)
    runner = command_runner or (
        lambda argv, cwd, timeout_seconds: _default_command_runner(
            argv,
            cwd,
            timeout_seconds,
            public_python=public_python,
            heartbeat_interval_seconds=request.heartbeat_interval_seconds,
        )
    )
    commands = [
        _command_record(
            command_id=command_id,
            argv=argv,
            cwd=public_out_path,
            display_vault=vault,
            timeout_seconds=request.timeout_seconds,
            command_runner=runner,
            pytest_summary_path=summary_path,
        )
        for command_id, argv, summary_path in _public_check_command_specs(
            public_python=public_python,
            request=request,
            public_out_path=public_out_path,
            pytest_summary_cache_path=pytest_summary_cache_path,
        )
    ]
    try:
        pytest_summary = pytest_summary_path.read_bytes()
    except OSError:
        pytest_summary = None
    _remove_optional_file(pytest_summary_path)
    return commands, pytest_summary


def _public_check_status(
    commands: list[dict[str, Any]], negative_assertions: dict[str, Any]
) -> str:
    command_status = _overall_status(commands)
    assertion_status = _negative_assertion_status(negative_assertions)
    return command_status if command_status != "pass" else assertion_status


def _public_check_failure_causes(
    commands: list[dict[str, Any]],
    negative_assertions: dict[str, Any],
) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    for command in commands:
        if command.get("status") == "pass":
            continue
        command_id = str(command.get("id") or "unknown")
        cause: dict[str, Any] = {
            "severity": "error",
            "kind": "command_failure",
            "id": f"command:{command_id}",
            "message": f"public check command {command_id} failed",
            "command_id": command_id,
            "status": str(command.get("status") or "unknown"),
            "returncode": int(command.get("returncode", 0) or 0),
            "timed_out": bool(command.get("timed_out", False)),
            "termination_reason": str(command.get("termination_reason") or "unknown"),
        }
        pytest_counts = command.get("pytest_counts")
        if isinstance(pytest_counts, dict) and pytest_counts:
            cause["pytest_counts"] = {
                str(key): int(value or 0)
                for key, value in pytest_counts.items()
                if isinstance(value, int)
            }
        for tail_key in ("stdout_tail", "stderr_tail"):
            tail = str(command.get(tail_key) or "").strip()
            if tail:
                cause[tail_key] = tail
        causes.append(cause)

    for assertion_id, assertion in sorted(negative_assertions.items()):
        if not isinstance(assertion, dict) or assertion.get("status") == "pass":
            continue
        violations = [str(item) for item in assertion.get("violations", [])]
        causes.append(
            {
                "severity": "error",
                "kind": "negative_assertion_failure",
                "id": f"negative_assertion:{assertion_id}",
                "message": f"public export negative assertion {assertion_id} failed",
                "assertion_id": str(assertion_id),
                "status": str(assertion.get("status") or "unknown"),
                "violation_count": int(
                    assertion.get("violation_count", len(violations)) or 0
                ),
                "violations": violations,
            }
        )
    return causes


def _summary_payload(
    vault: Path,
    export: _PublicExportSnapshot,
    source_history: dict[str, Any],
    commands: list[dict[str, Any]],
    status: str,
    public_check_config_fingerprint: str,
) -> dict[str, Any]:
    pytest_counts = commands[-1].get("pytest_counts", {})
    public_pytest_command = _public_pytest_command(commands)
    return {
        "public_export_status": "pass",
        "public_check_status": status,
        "export_file_count": _int_value(export.manifest.get("file_count", 0)),
        "export_source_file_count": _int_value(
            export.manifest.get("source_file_count", 0)
        ),
        "export_root_fingerprint": export.export_root_fingerprint,
        "public_export_manifest_sha256": _sha256_file(export.manifest_path),
        "public_surface_policy_sha256": _sha256_file(
            vault / "ops/scripts/public/public_surface_policy.py"
        ),
        "public_check_config_fingerprint": public_check_config_fingerprint,
        "command_count": len(commands),
        "command_fail_count": sum(
            1 for command in commands if command["status"] != "pass"
        ),
        "negative_assertion_fail_count": sum(
            1
            for assertion in export.negative_assertions.values()
            if isinstance(assertion, dict) and assertion.get("status") != "pass"
        ),
        **export.boundary_status,
        "source_history_evaluation_status": str(source_history["evaluation_status"]),
        "source_history_status": str(source_history["status"]),
        "source_history_violation_count": int(source_history["violation_count"]),
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
        "public_pytest_heartbeat_count": int(
            public_pytest_command.get("heartbeat_count", 0) or 0
        ),
        "public_pytest_quiet_seconds": int(
            public_pytest_command.get("quiet_seconds", 0) or 0
        ),
        "public_pytest_termination_reason": str(
            public_pytest_command.get("termination_reason", "not_run")
        ),
        "public_pytest_signal_sent": str(
            public_pytest_command.get("signal_sent", "none")
        ),
        "public_pytest_final_state_observed": str(
            public_pytest_command.get("final_state_observed", "not_run")
        ),
    }


def _public_export_payload(
    vault: Path, export: _PublicExportSnapshot
) -> dict[str, Any]:
    return {
        "output_dir": _display_external_path(export.public_out_path, vault),
        "manifest_file": str(
            export.manifest.get("manifest_file", "PUBLIC-EXPORT-MANIFEST.json")
        ),
        "file_count": _int_value(export.manifest.get("file_count", 0)),
        "source_file_count": _int_value(export.manifest.get("source_file_count", 0)),
        "export_root_fingerprint": export.export_root_fingerprint,
        "manifest_sha256": _sha256_file(export.manifest_path),
        "git_metadata_present": (export.public_out_path / ".git").exists(),
    }


def _render_public_check_report(
    vault: Path,
    policy: dict[str, Any],
    resolved_policy_path: Path,
    runtime_context: RuntimeContext,
    export: _PublicExportSnapshot,
    source_history: dict[str, Any],
    commands: list[dict[str, Any]],
    request: PublicCheckRequest,
    public_source_inputs: str,
    toolchain: str,
) -> dict[str, Any]:
    status = _public_check_status(commands, export.negative_assertions)
    source_paths = [
        "Makefile",
        "ops/scripts/public/public_check_summary.py",
        "ops/scripts/public/public_toolchain_runtime.py",
        "ops/scripts/public/export_public_repo.py",
        "ops/scripts/public/public_surface_policy.py",
        "ops/scripts/public/source_history_scan_runtime.py",
        "ops/scripts/test/test_execution_summary.py",
    ]
    public_check_config_text = _public_check_config_text(vault, request)
    public_check_config_fingerprint = _public_check_config_fingerprint(vault, request)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="public_check_summary",
            producer=PRODUCER,
            source_command=_public_check_source_command(request),
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=source_paths,
            path_group_inputs={
                "public_check_summary_inputs": [
                    "Makefile",
                    "ops/scripts/public/export_public_repo.py",
                    "ops/scripts/public/public_surface_policy.py",
                    "ops/scripts/public/source_history_scan_runtime.py",
                ]
            },
            text_inputs={
                PUBLIC_CHECK_CONFIG_FINGERPRINT_KEY: public_check_config_text,
                PUBLIC_TOOLCHAIN_FINGERPRINT_KEY: toolchain,
                PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY: public_source_inputs,
                SOURCE_HISTORY_STATE_FINGERPRINT_KEY: str(
                    source_history["history_state_fingerprint"]
                ),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "summary": _summary_payload(
            vault,
            export,
            source_history,
            commands,
            status,
            public_check_config_fingerprint,
        ),
        "public_export": _public_export_payload(vault, export),
        "source_history_scan": source_history,
        "public_export_negative_assertions": export.negative_assertions,
        "failure_causes": _public_check_failure_causes(
            commands, export.negative_assertions
        ),
        "commands": commands,
    }


def build_report(
    vault: Path,
    request: PublicCheckRequest | None = None,
    *,
    context: RuntimeContext | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    request = request or PublicCheckRequest()
    with _public_check_output(vault, request) as output:
        return _check_export(vault, output, request, context=context, command_runner=command_runner)


@contextmanager
def _public_check_output(vault: Path, request: PublicCheckRequest) -> Iterator[Path]:
    if request.public_out:
        yield _resolve_out_dir(vault, request.public_out).resolve()
    else:
        with tempfile.TemporaryDirectory(prefix="llm-wiki-public-check-") as temp:
            yield Path(temp) / "export"


@contextmanager
def _toolchain_workspace(vault: Path, request: PublicCheckRequest) -> Iterator[Path]:
    """Inspect retained output under its lock; reconstruct only private exports."""
    with _public_check_output(vault, request) as output:
        if request.public_out:
            _export_roots(vault, output)
            if not output.is_dir():
                raise ValueError("retained public export is unavailable")
            with _output_lock(output):
                yield output
        else:
            with public_export_session(vault, output) as manifest:
                snapshot = _canonical_sha256(_export_file_records(output, manifest))
                yield output
                if (
                    not _export_inventory_is_current(output, manifest)
                    or snapshot != _canonical_sha256(_export_file_records(output, manifest))
                ):
                    raise ValueError("public export changed during toolchain probe")


def _export_toolchain_fingerprint(vault: Path, request: PublicCheckRequest, output: Path) -> str:
    return public_toolchain_fingerprint(
        _resolve_public_python(vault, request.public_python),
        cwd=output, private_workspace=not request.public_out,
    )


def _check_export(
    vault: Path, output: Path, request: PublicCheckRequest, *,
    context: RuntimeContext | None, command_runner: CommandRunner | None,
) -> dict[str, Any]:
    source_identity = release_source_tree_fingerprint(vault)
    public_source_inputs = _public_export_source_inputs(vault)
    with public_export_session(vault, output) as manifest:
        return _validate_export(
            vault, output, request, manifest, source_identity, public_source_inputs,
            context=context, command_runner=command_runner,
        )


def _validate_export(
    vault: Path, output: Path, request: PublicCheckRequest, manifest: dict[str, Any],
    source_identity: str, public_source_inputs: str, *,
    context: RuntimeContext | None, command_runner: CommandRunner | None,
) -> dict[str, Any]:
    """Validate an export while its caller owns the output lock and lifetime."""
    policy, resolved_policy_path = load_policy(vault, None)
    runtime_context = context or RuntimeContext.from_policy(policy)
    export = _collect_public_export_snapshot(vault, output, manifest)
    public_python = public_python_launcher(_resolve_public_python(vault, request.public_python), cwd=output)
    toolchain = _export_toolchain_fingerprint(vault, request, output)
    pytest_summary_cache_path = _public_pytest_summary_cache_path(
        vault, request, toolchain=toolchain,
        source_identity=source_identity, public_source_inputs=public_source_inputs,
    )
    source_history = scan_source_history(vault, requested=request.source_history_scan)
    commands, pytest_summary = _run_public_check_commands(
        vault, request, output, command_runner, pytest_summary_cache_path,
        public_python=public_python,
    )
    if (
        toolchain != _export_toolchain_fingerprint(vault, request, output)
        or source_identity != release_source_tree_fingerprint(vault)
        or public_source_inputs != _public_export_source_inputs(vault)
        or not _export_inventory_is_current(output, manifest)
        or export.export_root_fingerprint != _canonical_sha256(_export_file_records(output, manifest))
        or source_history["history_state_fingerprint"] != source_history_state_fingerprint(vault, requested=request.source_history_scan)
    ):
        raise ValueError("public check source, toolchain or exported inputs changed during validation")
    report = _render_public_check_report(
        vault, policy, resolved_policy_path, runtime_context,
        export, source_history, commands, request, public_source_inputs, toolchain,
    )
    _persist_public_pytest_summary(pytest_summary, pytest_summary_cache_path)
    if not request.public_out:
        report["public_export"]["output_dir"] = "<tmp>/invocation-private/export"
    return report


def write_report(
    vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT
) -> Path:
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


def _retained_export_is_current(output: Path, payload: dict[str, Any]) -> bool:
    """Caller holds the export lock for this check and the live toolchain probe."""
    metadata = payload.get("public_export", {})
    if not isinstance(metadata, dict):
        return False
    try:
        manifest_path = output / "PUBLIC-EXPORT-MANIFEST.json"
        if _sha256_file(manifest_path) != metadata.get("manifest_sha256"):
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return (
            _export_inventory_is_current(output, manifest)
            and _canonical_sha256(_export_file_records(output, manifest)) == metadata.get("export_root_fingerprint")
        )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return False


def _not_current_summary(
    diagnostics: dict[str, Any], checks: dict[str, bool], comparisons: dict[str, Any],
) -> dict[str, Any]:
    # Only evaluated checks are reported; deferred work cannot establish currentness.
    failed = [name for name, passed in checks.items() if not passed]
    return {
        **diagnostics,
        "reason": f"not_current:{','.join(failed)}",
        "checks": checks,
        **comparisons,
    }


def reusable_summary_diagnostics(
    vault: Path,
    path_value: str | Path,
    request: PublicCheckRequest | None = None,
) -> dict[str, Any]:
    return _reusable_summary_diagnostics(vault, path_value, request)


def _reusable_summary_diagnostics(
    vault: Path, path_value: str | Path, request: PublicCheckRequest | None,
    *, session: _PublicCheckSession | None = None,
) -> dict[str, Any]:
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
    if not isinstance(payload, dict):
        diagnostics["reason"] = "summary_invalid:not_object"
        return diagnostics
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    input_fingerprints = payload.get("input_fingerprints")
    input_fingerprints = (
        input_fingerprints if isinstance(input_fingerprints, dict) else {}
    )
    checks = {
        "artifact_kind": payload.get("artifact_kind") == "public_check_summary",
        "producer": payload.get("producer") == PRODUCER,
        "status": payload.get("status") == "pass",
        "public_check_status": summary.get("public_check_status") == "pass",
        "local_corpus_policy": local_corpus_policy_is_current(vault, payload),
    }
    comparisons: dict[str, Any] = {
        "observed_source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
    }
    required_fingerprints = {
        "source_tree_fingerprint": payload.get("source_tree_fingerprint"),
        PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY: input_fingerprints.get(PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY),
        PUBLIC_TOOLCHAIN_FINGERPRINT_KEY: input_fingerprints.get(PUBLIC_TOOLCHAIN_FINGERPRINT_KEY),
    }
    if request is not None:
        required_fingerprints[SOURCE_HISTORY_STATE_FINGERPRINT_KEY] = input_fingerprints.get(SOURCE_HISTORY_STATE_FINGERPRINT_KEY)
        expected_source_command = _public_check_source_command(request)
        observed_source_command = str(payload.get("source_command", ""))
        checks["source_command"] = observed_source_command == expected_source_command
        expected_config = _public_check_config_fingerprint(vault, request)
        observed_config = str(input_fingerprints.get(PUBLIC_CHECK_CONFIG_FINGERPRINT_KEY, ""))
        checks[PUBLIC_CHECK_CONFIG_FINGERPRINT_KEY] = observed_config == expected_config
        comparisons.update({
            "expected_public_check_config_fingerprint": expected_config,
            "observed_public_check_config_fingerprint": observed_config,
            "expected_source_command": expected_source_command,
            "observed_source_command": observed_source_command,
        })
    for name, value in required_fingerprints.items():
        if not isinstance(value, str) or not value:
            checks[name] = False
    if not all(checks.values()):
        return _not_current_summary(diagnostics, checks, comparisons)

    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    try:
        current_public_source_inputs = _public_export_source_inputs(vault)
        current_public_source_fingerprint = hashlib.sha256(
            current_public_source_inputs.encode("utf-8")
        ).hexdigest()
    except OSError as exc:
        diagnostics["reason"] = f"public_export_source_unavailable:{type(exc).__name__}"
        return diagnostics
    comparisons["current_source_tree_fingerprint"] = current_source_tree_fingerprint
    checks["source_tree_fingerprint"] = payload.get("source_tree_fingerprint") == current_source_tree_fingerprint
    checks[PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY] = (
        input_fingerprints.get(PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY) == current_public_source_fingerprint
    )
    if not all(checks.values()):
        return _not_current_summary(diagnostics, checks, comparisons)

    try:
        effective_request = request or PublicCheckRequest()
        if effective_request.public_out:
            checks["retained_export"] = False
        workspace = (
            session.probe_workspace(current_source_tree_fingerprint, current_public_source_inputs)
            if session is not None and not effective_request.public_out
            else _toolchain_workspace(vault, effective_request)
        )
        with workspace as output:
            if effective_request.public_out:
                checks["retained_export"] = _retained_export_is_current(output, payload)
            checks[PUBLIC_TOOLCHAIN_FINGERPRINT_KEY] = False
            if checks.get("retained_export", True):
                toolchain = _export_toolchain_fingerprint(vault, effective_request, output)
                checks[PUBLIC_TOOLCHAIN_FINGERPRINT_KEY] = input_fingerprints.get(
                    PUBLIC_TOOLCHAIN_FINGERPRINT_KEY
                ) == hashlib.sha256(toolchain.encode()).hexdigest()
                if effective_request.public_out:
                    checks["retained_export"] = _retained_export_is_current(output, payload)
        checks["source_tree_fingerprint"] = checks["source_tree_fingerprint"] and (
            current_source_tree_fingerprint == release_source_tree_fingerprint(vault)
        )
        checks[PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY] = checks[PUBLIC_EXPORT_SOURCE_FINGERPRINT_KEY] and (
            current_public_source_fingerprint == hashlib.sha256(_public_export_source_inputs(vault).encode("utf-8")).hexdigest()
        )
    except ProcessCleanupError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        checks[PUBLIC_TOOLCHAIN_FINGERPRINT_KEY] = False
        diagnostics["toolchain_error"] = sanitize_report_text(vault, str(exc))
    if not all(checks.values()):
        return _not_current_summary(diagnostics, checks, comparisons)

    if request is not None:
        expected_source_history_state_fingerprint = hashlib.sha256(
            source_history_state_fingerprint(
                vault,
                requested=request.source_history_scan,
            ).encode("utf-8")
        ).hexdigest()
        observed_source_history_state_fingerprint = str(
            input_fingerprints.get(SOURCE_HISTORY_STATE_FINGERPRINT_KEY, "")
        )
        checks[SOURCE_HISTORY_STATE_FINGERPRINT_KEY] = (
            observed_source_history_state_fingerprint
            == expected_source_history_state_fingerprint
        )
        comparisons.update({
            "expected_source_history_state_fingerprint": expected_source_history_state_fingerprint,
            "observed_source_history_state_fingerprint": observed_source_history_state_fingerprint,
        })
    if not all(checks.values()):
        return _not_current_summary(diagnostics, checks, comparisons)
    diagnostics.update(
        {
            "reusable": True,
            "reason": "current_passing_public_check_summary",
            "generated_at": str(payload.get("generated_at", "")),
            "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")),
            "public_check_config_fingerprint": str(
                input_fingerprints.get(PUBLIC_CHECK_CONFIG_FINGERPRINT_KEY, "")
            ),
            "source_history_state_fingerprint": str(
                input_fingerprints.get(SOURCE_HISTORY_STATE_FINGERPRINT_KEY, "")
            ),
        }
    )
    return diagnostics


@dataclass(frozen=True)
class _PreparedPublicExport:
    output: Path
    manifest: dict[str, Any]
    fingerprint: str
    source_identity: str
    public_source_inputs: str

    def is_current(self) -> bool:
        return (
            _export_inventory_is_current(self.output, self.manifest)
            and self.fingerprint == _canonical_sha256(_export_file_records(self.output, self.manifest))
        )


class _PublicCheckSession:
    """Keep one private export locked between reuse diagnosis and validation."""

    def __init__(self, vault: Path, request: PublicCheckRequest) -> None:
        self.vault = vault
        self.request = request
        self.stack = ExitStack()
        self.prepared: _PreparedPublicExport | None = None

    def close(self) -> None:
        self.prepared = None
        self.stack.close()

    @contextmanager
    def probe_workspace(self, source_identity: str, public_source_inputs: str) -> Iterator[Path]:
        valid = False
        try:
            output = self.stack.enter_context(_public_check_output(self.vault, self.request))
            manifest = self.stack.enter_context(public_export_session(self.vault, output))
            self.prepared = _PreparedPublicExport(
                output, manifest, _canonical_sha256(_export_file_records(output, manifest)),
                source_identity, public_source_inputs,
            )
            yield output
            if not self.prepared.is_current():
                raise ValueError("public export changed during toolchain probe")
            valid = True
        finally:
            if not valid:
                self.prepared = None
            # The invocation closes even rejected workspaces outside the diagnostic
            # exception handler, so cleanup errors cannot become ordinary misses.

    def build_report(self) -> dict[str, Any]:
        prepared = self.prepared
        if (
            prepared is not None
            and prepared.source_identity == release_source_tree_fingerprint(self.vault)
            and prepared.public_source_inputs == _public_export_source_inputs(self.vault)
            and prepared.is_current()
        ):
            return _validate_export(
                self.vault, prepared.output, self.request, prepared.manifest,
                prepared.source_identity, prepared.public_source_inputs,
                context=None, command_runner=None,
            )
        self.close()
        return build_report(self.vault, self.request)


def _public_check_cli_failure_summary(
    vault: Path,
    report: dict[str, Any],
    destination: Path,
) -> dict[str, Any]:
    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    causes = report.get("failure_causes")
    return {
        "summary_mode": "executed",
        "status": str(report.get("status") or "unknown"),
        "report": display_path(vault, destination),
        "public_check_status": str(summary.get("public_check_status") or "unknown"),
        "command_fail_count": int(summary.get("command_fail_count", 0) or 0),
        "negative_assertion_fail_count": int(
            summary.get("negative_assertion_fail_count", 0) or 0
        ),
        "failure_causes": causes if isinstance(causes, list) else [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run public mirror checks and write a canonical summary."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=("default", "full"), default="default")
    parser.add_argument("--public-out", default="", help="Explicit locked export directory; default uses a disposable per-invocation directory.")
    parser.add_argument("--public-python", default=sys.executable)
    parser.add_argument("--ruff-targets", default="ops/scripts tests tools")
    parser.add_argument("--mypy-targets", default="ops/scripts")
    parser.add_argument("--pytest-mark-expr")
    parser.add_argument("--pytest-flags", default="")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--skip-source-history-scan",
        action="store_true",
        help="Record source history as not_requested instead of scanning all refs and HEAD.",
    )
    parser.add_argument("--reuse-if-current", action="store_true")
    parser.add_argument("--reuse-from")
    parser.add_argument(
        "--promote-to", help="Promote the candidate only after fresh validation passes; reuse leaves it untouched.",
    )
    parser.add_argument(
        "--reuse-only",
        action="store_true",
        help="With --reuse-if-current, fail instead of rerunning when the public-check summary is stale.",
    )
    args = parser.parse_args(argv)
    if args.pytest_mark_expr is None:
        args.pytest_mark_expr = "" if args.mode == "full" else "public"
    elif args.mode == "full" and args.pytest_mark_expr.strip():
        parser.error("--mode full requires an empty --pytest-mark-expr")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.reuse_only:
        args.reuse_if_current = True
    vault = Path(args.vault).resolve()
    promotion_path = resolve_repo_output_path(vault, args.promote_to) if args.promote_to else None
    if promotion_path is not None and promotion_path == resolve_repo_output_path(vault, args.out):
        raise ValueError("public check candidate and promotion destination must differ")
    request = PublicCheckRequest(
        mode=args.mode,
        public_out=args.public_out,
        public_python=args.public_python,
        ruff_targets=args.ruff_targets,
        mypy_targets=args.mypy_targets,
        pytest_mark_expr=args.pytest_mark_expr,
        pytest_flags=args.pytest_flags,
        timeout_seconds=args.timeout_seconds,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        source_history_scan=not args.skip_source_history_scan,
    )
    diagnostics: dict[str, Any] = {}
    with closing(_PublicCheckSession(vault, request)) as session:
        if args.reuse_if_current:
            diagnostics = _reusable_summary_diagnostics(
                vault, args.reuse_from or args.out, request, session=session
            )
            if not diagnostics["reusable"]:
                print(json.dumps(
                    {"summary_mode": "executed", "reuse_diagnostics": diagnostics},
                    ensure_ascii=False, indent=2,
                ))
                if args.reuse_only:
                    return 1
        report = None if diagnostics.get("reusable") else session.build_report()
    if report is None:
        print(json.dumps({"summary_mode": "reused", **diagnostics}, ensure_ascii=False, indent=2))
        return 0
    destination = write_report(vault, report, args.out)
    if report["status"] == "pass" and promotion_path is not None:
        destination = promote_schema_validated_json(
            vault, candidate_path=destination,
            destination_path=promotion_path,
            schema_path=SCHEMA_PATH, expected_artifact_kind="public_check_summary",
            expected_producer=PRODUCER, context="public check summary promotion failed",
        )
    print(display_path(vault, destination))
    if report["status"] != "pass":
        print(
            json.dumps(
                _public_check_cli_failure_summary(vault, report, destination),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
