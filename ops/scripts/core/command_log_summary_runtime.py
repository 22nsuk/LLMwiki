from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifact_io_runtime import (
    load_optional_json_object,
    write_vault_schema_validated_json,
)
from .executor_noop_runtime import text_has_executor_noop_mutation_failure
from .observability_artifacts_shared_runtime import run_dir_candidates
from .output_runtime import write_output_text
from .runtime_context import RuntimeContext
from .schema_constants_runtime import COMMAND_LOG_SUMMARY_SCHEMA_PATH

COMMAND_LOG_SUMMARY_SCHEMA = COMMAND_LOG_SUMMARY_SCHEMA_PATH
COMMAND_LOG_SUMMARY_FILENAME = "command-log-summary.json"
PRODUCER = "ops.scripts.command_log_summary_runtime"
DEFAULT_HEAD_BYTES = 16 * 1024
DEFAULT_TAIL_BYTES = 16 * 1024
USAGE_LIMIT_RE = re.compile(
    r"(you(?:'ve| have) hit your usage limit|usage limit\b|upgrade to pro\b|try again at\b)",
    flags=re.IGNORECASE,
)


def run_rel(run_id: str, filename: str) -> str:
    return f"runs/{run_id}/{filename}"


def _run_root_rel(run_id: str, run_root_rel: str | None = None) -> str:
    root = str(run_root_rel or "").strip().strip("/")
    return root or f"runs/{run_id}"


def command_log_summary_rel(run_id: str, *, run_root_rel: str | None = None) -> str:
    return f"{_run_root_rel(run_id, run_root_rel)}/{COMMAND_LOG_SUMMARY_FILENAME}"


def command_log_trace_rel(
    run_id: str,
    prefix: str,
    stream: str,
    *,
    run_root_rel: str | None = None,
) -> str:
    return f"{_run_root_rel(run_id, run_root_rel)}/{prefix}.{stream}-trace.txt"


def _repo_rel_path(vault: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(vault.resolve()).as_posix()
    except ValueError:
        return ""


def _summary_rel_candidates(
    vault: Path,
    run_id: str,
    *,
    run_root_rel: str | None = None,
) -> list[str]:
    if run_root_rel:
        return [command_log_summary_rel(run_id, run_root_rel=run_root_rel)]
    candidates: list[str] = []
    seen: set[str] = set()
    for run_dir in run_dir_candidates(vault, run_id):
        rel_path = _repo_rel_path(vault, run_dir / COMMAND_LOG_SUMMARY_FILENAME)
        if rel_path and rel_path not in seen:
            candidates.append(rel_path)
            seen.add(rel_path)
    fallback = command_log_summary_rel(run_id)
    if fallback not in seen:
        candidates.append(fallback)
    return candidates


def _context_or_default(context: RuntimeContext | None) -> RuntimeContext:
    if context is not None:
        return context
    return RuntimeContext(display_timezone=dt.UTC)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _int_value(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _argv_value(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    return []


def _trace_text(
    data: bytes,
    *,
    original_sha256: str,
    head_bytes: int,
    tail_bytes: int,
) -> tuple[str, bool, int, int]:
    if len(data) <= head_bytes + tail_bytes:
        return data.decode("utf-8", errors="replace"), False, len(data), 0
    head = data[:head_bytes]
    tail = data[-tail_bytes:] if tail_bytes else b""
    omitted_bytes = len(data) - len(head) - len(tail)
    marker = (
        "\n\n"
        "[... command log truncated: "
        f"original_size_bytes={len(data)}; omitted_bytes={omitted_bytes}; "
        f"original_sha256={original_sha256} ...]"
        "\n\n"
    )
    return (
        head.decode("utf-8", errors="replace")
        + marker
        + tail.decode("utf-8", errors="replace"),
        True,
        len(head),
        len(tail),
    )


def _diagnostic_flags(stream: str, text: str) -> list[str]:
    flags: list[str] = []
    if stream == "stderr" and text_has_executor_noop_mutation_failure(text):
        flags.append("executor_noop_mutation_failure")
    if stream == "stderr" and USAGE_LIMIT_RE.search(text):
        flags.append("executor_usage_limited")
    return flags


def _existing_streams(
    vault: Path,
    run_id: str,
    *,
    run_root_rel: str | None = None,
) -> list[dict[str, Any]]:
    path = vault / command_log_summary_rel(run_id, run_root_rel=run_root_rel)
    payload = load_optional_json_object(path)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return []
    return [item for item in streams if isinstance(item, dict)]


def _summary_from_streams(
    run_id: str,
    streams: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "$schema": COMMAND_LOG_SUMMARY_SCHEMA,
        "artifact_kind": "command_log_summary",
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": generated_at,
        "producer": PRODUCER,
        "summary": {
            "stream_count": len(streams),
            "truncated_stream_count": sum(1 for item in streams if item.get("truncated")),
            "original_total_bytes": sum(_int_value(item.get("original_size_bytes")) for item in streams),
            "trace_total_bytes": sum(_int_value(item.get("trace_size_bytes")) for item in streams),
        },
        "streams": streams,
    }


def _merge_streams(
    existing: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {
        (
            str(item.get("prefix", "")),
            str(item.get("stream", "")),
            str(item.get("original_path", "")),
        ): item
        for item in existing
    }
    for item in updates:
        key = (
            str(item.get("prefix", "")),
            str(item.get("stream", "")),
            str(item.get("original_path", "")),
        )
        by_key[key] = item
    return sorted(by_key.values(), key=lambda item: (str(item["prefix"]), str(item["stream"])))


def write_command_log_summary(
    vault: Path,
    run_id: str,
    prefix: str,
    result: Mapping[str, Any],
    *,
    raw_paths: Mapping[str, str],
    context: RuntimeContext | None = None,
    command_argv: Sequence[str] | None = None,
    head_bytes: int = DEFAULT_HEAD_BYTES,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
    run_root_rel: str | None = None,
) -> str:
    runtime_context = _context_or_default(context)
    generated_at = runtime_context.isoformat_z()
    command = str(result.get("command", "")).strip()
    argv = [str(item) for item in command_argv] if command_argv is not None else _argv_value(result.get("argv"))
    updates: list[dict[str, Any]] = []
    for stream in ("stdout", "stderr"):
        raw_rel = str(raw_paths.get(stream, "")).strip()
        if not raw_rel:
            continue
        raw_path = vault / raw_rel
        try:
            raw_bytes = raw_path.read_bytes()
        except OSError:
            continue
        original_sha256 = _sha256_bytes(raw_bytes)
        trace_rel = command_log_trace_rel(
            run_id,
            prefix,
            stream,
            run_root_rel=run_root_rel,
        )
        trace_text, truncated, head_retained, tail_retained = _trace_text(
            raw_bytes,
            original_sha256=original_sha256,
            head_bytes=head_bytes,
            tail_bytes=tail_bytes,
        )
        write_output_text(vault / trace_rel, trace_text)
        trace_path = vault / trace_rel
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        updates.append(
            {
                "prefix": prefix,
                "stream": stream,
                "original_path": raw_rel,
                "original_size_bytes": len(raw_bytes),
                "original_sha256": original_sha256,
                "trace_path": trace_rel,
                "trace_size_bytes": trace_path.stat().st_size,
                "trace_sha256": _sha256_file(trace_path),
                "head_limit_bytes": head_bytes,
                "tail_limit_bytes": tail_bytes,
                "head_retained_bytes": head_retained,
                "tail_retained_bytes": tail_retained,
                "truncated": truncated,
                "command": command,
                "argv": argv,
                "returncode": _int_value(result.get("returncode")),
                "timed_out": bool(result.get("timed_out", False)),
                "timeout_seconds": _int_value(result.get("timeout_seconds")),
                "termination_reason": str(result.get("termination_reason", "")).strip(),
                "diagnostic_flags": _diagnostic_flags(stream, raw_text),
                "generated_at": generated_at,
            }
        )
    streams = _merge_streams(
        _existing_streams(vault, run_id, run_root_rel=run_root_rel),
        updates,
    )
    payload = _summary_from_streams(run_id, streams, generated_at=generated_at)
    rel_path = command_log_summary_rel(run_id, run_root_rel=run_root_rel)
    write_vault_schema_validated_json(
        vault,
        rel_path,
        payload,
        COMMAND_LOG_SUMMARY_SCHEMA,
        context=f"schema validation failed for {rel_path}",
    )
    return rel_path


def load_command_log_summary(
    vault: Path,
    run_id: str,
    *,
    run_root_rel: str | None = None,
) -> dict[str, Any]:
    for rel_path in _summary_rel_candidates(vault, run_id, run_root_rel=run_root_rel):
        payload = load_optional_json_object(vault / rel_path)
        if payload:
            return payload
    return {}


def command_log_summary_stream(
    vault: Path,
    run_id: str,
    *,
    prefix: str,
    stream: str,
    run_root_rel: str | None = None,
) -> dict[str, Any] | None:
    payload = load_command_log_summary(vault, run_id, run_root_rel=run_root_rel)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return None
    for item in streams:
        if not isinstance(item, dict):
            continue
        if item.get("prefix") == prefix and item.get("stream") == stream:
            return item
    return None


def command_log_stream_has_flag(
    vault: Path,
    run_id: str,
    *,
    prefix: str,
    stream: str,
    flag: str,
    run_root_rel: str | None = None,
) -> bool:
    item = command_log_summary_stream(
        vault,
        run_id,
        prefix=prefix,
        stream=stream,
        run_root_rel=run_root_rel,
    )
    flags = item.get("diagnostic_flags") if isinstance(item, dict) else None
    return isinstance(flags, list) and flag in flags


def command_log_stream_text(
    vault: Path,
    run_id: str,
    *,
    prefix: str,
    stream: str,
    run_root_rel: str | None = None,
) -> str:
    item = command_log_summary_stream(
        vault,
        run_id,
        prefix=prefix,
        stream=stream,
        run_root_rel=run_root_rel,
    )
    if isinstance(item, dict):
        trace_rel = str(item.get("trace_path", "")).strip()
        trace_path = vault / trace_rel
        try:
            return trace_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    raw_path = vault / _run_root_rel(run_id, run_root_rel) / f"{prefix}.{stream}.txt"
    try:
        return raw_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def usage_limit_flag_for_artifact(vault: Path, rel_path: str) -> bool:
    parts = Path(rel_path).parts
    if len(parts) < 3 or parts[0] != "runs":
        return False
    if len(parts) >= 4 and parts[1] == "archive":
        run_id = parts[2]
        run_root_rel = f"runs/archive/{run_id}"
    else:
        run_id = parts[1]
        run_root_rel = f"runs/{run_id}"
    filename = parts[-1]
    suffix = ".stderr-trace.txt"
    if not filename.endswith(suffix):
        return False
    prefix = filename[: -len(suffix)]
    return command_log_stream_has_flag(
        vault,
        run_id,
        prefix=prefix,
        stream="stderr",
        flag="executor_usage_limited",
        run_root_rel=run_root_rel,
    )
