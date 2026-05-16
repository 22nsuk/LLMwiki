from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import read_json_object
from ops.scripts.runtime_context import RuntimeContext


_RETRY_AFTER_RE = re.compile(r"retry_after=([^\n\r;]+)", re.IGNORECASE)
_ORDINAL_DAY_SUFFIX_RE = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)


def isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_isoformat_z(value: str) -> dt.datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_retry_after_utc(value: str, context: RuntimeContext) -> dt.datetime | None:
    parsed = parse_isoformat_z(value)
    if parsed is not None:
        return parsed
    normalized = _ORDINAL_DAY_SUFFIX_RE.sub(r"\1", value.strip())
    for fmt in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p"):
        try:
            parsed = dt.datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=context.display_timezone).astimezone(dt.timezone.utc)
    return None


def retry_after_text_from_text(text: str) -> str:
    match = _RETRY_AFTER_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def rel_to_vault(vault: Path, path: Path) -> str:
    try:
        return path.relative_to(vault).as_posix()
    except ValueError:
        return path.as_posix()


def executor_report_paths(vault: Path, result: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    run_ids = result.get("run_ids", [])
    if not isinstance(run_ids, list):
        return paths
    for item in run_ids:
        run_id = str(item).strip()
        if not run_id:
            continue
        run_dir = vault / "runs" / run_id
        if run_dir.is_dir():
            paths.extend(sorted(run_dir.glob("*-executor-report.json")))
    return paths


def retry_after_from_executor_report(vault: Path, report_path: Path) -> str:
    try:
        report = read_json_object(report_path)
    except (OSError, ValueError, TypeError):
        return ""
    texts: list[str] = []
    diagnostics = report.get("diagnostics")
    if isinstance(diagnostics, dict):
        notes = diagnostics.get("notes")
        if isinstance(notes, list):
            texts.extend(str(item) for item in notes)
    artifacts = report.get("artifacts")
    if isinstance(artifacts, dict):
        stderr_rel = str(artifacts.get("stderr", "")).strip()
        if stderr_rel:
            stderr_artifact = Path(stderr_rel)
            stderr_path = vault / stderr_artifact
            if not stderr_artifact.is_absolute() and stderr_path.is_file():
                texts.append(stderr_path.read_text(encoding="utf-8", errors="replace"))
    for text in texts:
        retry_after = retry_after_text_from_text(text)
        if retry_after:
            return retry_after
    return ""


def usage_limit_backoff_from_result(
    vault: Path,
    result: dict[str, Any],
    context: RuntimeContext,
) -> dict[str, Any] | None:
    if str(result.get("stop_reason", "")).strip() != "executor_usage_limited":
        return None
    for report_path in executor_report_paths(vault, result):
        retry_after = retry_after_from_executor_report(vault, report_path)
        if not retry_after:
            continue
        parsed = parse_retry_after_utc(retry_after, context)
        return {
            "active": True,
            "reason": "executor_usage_limited",
            "retry_after": retry_after,
            "retry_after_utc": isoformat_z(parsed) if parsed is not None else "",
            "source": rel_to_vault(vault, report_path),
            "last_observed_at": context.isoformat_z(),
        }
    return None


def executor_backoff_wait_seconds(
    backoff: dict[str, Any],
    context: RuntimeContext,
) -> float | None:
    retry_after_utc = str(backoff.get("retry_after_utc", "")).strip()
    if not retry_after_utc:
        retry_after = str(backoff.get("retry_after", "")).strip()
        parsed = parse_retry_after_utc(retry_after, context) if retry_after else None
    else:
        parsed = parse_isoformat_z(retry_after_utc)
    if parsed is None:
        return None
    return max(0.0, (parsed - context.utcnow()).total_seconds())


def active_executor_backoff_from_status(
    vault: Path,
    status_path: str,
    context: RuntimeContext,
) -> dict[str, Any] | None:
    path = vault / status_path
    if not path.is_file():
        return None
    try:
        status = read_json_object(path)
    except (OSError, ValueError, TypeError):
        return None
    backoff = status.get("executor_backoff")
    if not isinstance(backoff, dict) or not bool(backoff.get("active", False)):
        return None
    if str(backoff.get("reason", "")) != "executor_usage_limited":
        return None
    wait_seconds = executor_backoff_wait_seconds(backoff, context)
    if wait_seconds is None or wait_seconds <= 0:
        return None
    return dict(backoff)
