from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import (
    canonical_artifact_payload,
    canonical_report_loading_issue,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import MECHANISM_REVIEW_SCHEMA_PATH
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from .auto_improve_next_run_decision_runtime import normalize_next_run_decisions
from .next_run_repair_queue_runtime import SOURCE_SESSION_REPORT_DECISION_KEY

MECHANISM_REVIEW_SCHEMA = MECHANISM_REVIEW_SCHEMA_PATH
DEFAULT_AUTO_IMPROVE_SESSIONS_DIR = "ops/reports/auto-improve-sessions"


@dataclass(frozen=True)
class RecentLogSection:
    heading: str
    text: str
    source_order: int


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_report(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"expected object report at {path}")
    return payload


def _auto_improve_session_report_paths(vault: Path) -> list[str]:
    session_dir = vault / DEFAULT_AUTO_IMPROVE_SESSIONS_DIR
    if not session_dir.is_dir():
        return []
    return sorted(
        path.relative_to(vault).as_posix()
        for path in session_dir.glob("*.json")
        if path.is_file()
    )


def _parse_iso_timestamp(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _session_report_loading_issue(path: Path, session_report: dict) -> str | None:
    issue = canonical_report_loading_issue(path, session_report)
    if issue == "missing_artifact_envelope":
        return None
    return issue


def _session_report_evidence_time(session_report: dict) -> dt.datetime | None:
    canonical = canonical_artifact_payload(session_report)
    times = [_parse_iso_timestamp(canonical.get("generated_at"))]
    currentness = canonical.get("currentness")
    if isinstance(currentness, dict):
        times.append(_parse_iso_timestamp(currentness.get("checked_at")))
    parsed_times = [timestamp for timestamp in times if timestamp is not None]
    if not parsed_times:
        return None
    return min(parsed_times)


def _session_report_fresh_for_observed_at(session_report: dict, observed_at: object) -> bool:
    observed = _parse_iso_timestamp(observed_at)
    if observed is None:
        return True
    evidence_time = _session_report_evidence_time(session_report)
    if evidence_time is None:
        return True
    return evidence_time >= observed


def _load_next_run_decisions(
    vault: Path,
    session_report_paths: list[str],
) -> list[dict]:
    decisions: list[dict] = []
    for rel_path in session_report_paths:
        try:
            session_report = _read_json(vault / rel_path)
        except (OSError, json.JSONDecodeError):
            continue
        if _session_report_loading_issue(vault / rel_path, session_report):
            continue
        for decision in normalize_next_run_decisions(session_report.get("next_run_decisions")):
            if _session_report_fresh_for_observed_at(session_report, decision.get("observed_at")):
                decisions.append({**decision, SOURCE_SESSION_REPORT_DECISION_KEY: rel_path})
    return sorted(
        decisions,
        key=lambda item: (
            str(item.get("observed_at", "")),
            str(item.get("session_id", "")),
            int(item.get("iteration", 0) or 0),
            str(item.get("source_run_id", "")),
            str(item.get("decision_id", "")),
        ),
    )


def _load_consumed_next_run_decision_ids(
    vault: Path,
    session_report_paths: list[str],
    next_run_decisions: list[dict],
) -> list[str]:
    consumed: set[str] = set()
    decision_observed_at = {
        str(decision.get("decision_id", "")).strip(): str(decision.get("observed_at", "")).strip()
        for decision in next_run_decisions
        if str(decision.get("decision_id", "")).strip()
    }
    for rel_path in session_report_paths:
        try:
            session_report = _read_json(vault / rel_path)
        except (OSError, json.JSONDecodeError):
            continue
        if _session_report_loading_issue(vault / rel_path, session_report):
            continue
        iterations = session_report.get("iterations", [])
        if not isinstance(iterations, list):
            continue
        for iteration in iterations:
            if not isinstance(iteration, dict):
                continue
            source_candidate_id = str(iteration.get("source_candidate_id", "")).strip()
            if (
                source_candidate_id.startswith("next-run-decision:")
                and _session_report_fresh_for_observed_at(
                    session_report,
                    decision_observed_at.get(source_candidate_id, ""),
                )
            ):
                consumed.add(source_candidate_id)
    return sorted(consumed)


def _parse_log_heading_timestamp(heading: str) -> tuple[int, int, int, int, int] | None:
    matched = re.match(r"\[(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})(?: [A-Z]+)?\]", heading)
    if not matched:
        return None
    year, month, day, hour, minute = matched.groups()
    return (int(year), int(month), int(day), int(hour), int(minute))


def _log_heading_datetime(
    heading: str,
    *,
    display_timezone: dt.tzinfo,
) -> dt.datetime | None:
    timestamp = _parse_log_heading_timestamp(heading)
    if timestamp is None:
        return None
    year, month, day, hour, minute = timestamp
    return dt.datetime(year, month, day, hour, minute, tzinfo=display_timezone)


def _filter_recent_log_sections_by_age(
    sections: list[RecentLogSection],
    *,
    runtime_context: RuntimeContext,
    max_age_days: int,
    section_ordering: str,
) -> list[RecentLogSection]:
    if max_age_days <= 0 or section_ordering != "timestamp":
        return sections
    cutoff = runtime_context.utcnow() - dt.timedelta(days=max_age_days)
    filtered: list[RecentLogSection] = []
    for section in sections:
        heading_time = _log_heading_datetime(
            section.heading,
            display_timezone=runtime_context.display_timezone,
        )
        if heading_time is None or heading_time.astimezone(dt.UTC) >= cutoff:
            filtered.append(section)
    return filtered


def _read_log_sections(
    path: Path,
    *,
    max_entries: int,
    max_age_days: int,
    runtime_context: RuntimeContext,
) -> tuple[list[RecentLogSection], str]:
    if max_entries <= 0 or not path.exists():
        return [], "file_order_fallback"

    text = path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", text)
    entries: list[RecentLogSection] = []
    for index, entry in enumerate(section.strip() for section in sections[1:] if section.strip()):
        heading = entry.splitlines()[0].strip() if entry.splitlines() else ""
        entries.append(RecentLogSection(heading=heading, text=entry, source_order=index))
    if not entries:
        return [], "file_order_fallback"

    timestamped = [
        (_parse_log_heading_timestamp(entry.heading), entry.source_order, entry)
        for entry in entries
    ]
    parsed_entries = [
        (timestamp, source_order, entry)
        for timestamp, source_order, entry in timestamped
        if timestamp is not None
    ]
    if len(parsed_entries) == len(entries) or len(parsed_entries) >= max_entries:
        ordered = [
            item
            for _, _, item in sorted(
                parsed_entries,
                key=lambda item: (item[0], item[1]),
            )
        ]
        recent_entries = ordered[-max_entries:]
        return (
            _filter_recent_log_sections_by_age(
                recent_entries,
                runtime_context=runtime_context,
                max_age_days=max_age_days,
                section_ordering="timestamp",
            ),
            "timestamp",
        )
    return (
        _filter_recent_log_sections_by_age(
            entries[-max_entries:],
            runtime_context=runtime_context,
            max_age_days=max_age_days,
            section_ordering="file_order_fallback",
        ),
        "file_order_fallback",
    )


def _log_heading_summary(recent_log_sections: list[RecentLogSection]) -> list[str]:
    return [section.heading for section in recent_log_sections if section.heading]


def _load_mechanism_review_report(vault: Path, path: Path) -> dict:
    schema = load_schema_with_vault_override(vault, MECHANISM_REVIEW_SCHEMA)
    report = _read_json(path)
    loading_issue = canonical_report_loading_issue(path, report)
    if loading_issue:
        raise ValueError(
            "mechanism review report is not current primary evidence: "
            f"{loading_issue}"
        )
    errors = validate_with_schema(report, schema)
    if errors:
        raise ValueError(
            "mechanism review report schema validation failed: "
            f"{errors[0]}"
        )
    return report
