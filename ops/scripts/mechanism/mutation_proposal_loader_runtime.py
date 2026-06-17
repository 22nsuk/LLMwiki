from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.artifact_freshness_runtime import (
    canonical_artifact_payload,
    canonical_report_loading_issue,
)
from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import MECHANISM_REVIEW_SCHEMA_PATH
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from .auto_improve_next_run_decision_runtime import normalize_next_run_decisions
from .next_run_repair_queue_runtime import SOURCE_SESSION_REPORT_DECISION_KEY

MECHANISM_REVIEW_SCHEMA = MECHANISM_REVIEW_SCHEMA_PATH
DEFAULT_AUTO_IMPROVE_SESSIONS_DIR = "ops/reports/auto-improve-sessions"
DEFAULT_MECHANISM_REVIEW_REPORT = "ops/reports/mechanism-review-candidates.json"
DEFAULT_OUTCOME_METRICS_REPORT = "ops/reports/outcome-metrics.json"
DEFAULT_REMEDIATION_BACKLOG_REPORT = "ops/reports/remediation-backlog.json"
DEFAULT_SYSTEM_LOG = "system/system-log.md"


@dataclass(frozen=True)
class RecentLogSection:
    heading: str
    text: str
    source_order: int


@dataclass(frozen=True)
class MutationReportInputs:
    runtime_context: RuntimeContext
    effective_policy: dict
    mutation_policy: dict
    mechanism_review_path: Path
    mechanism_review_report: dict
    outcome_metrics_path: Path
    outcome_metrics_report: dict
    remediation_backlog_path: Path
    remediation_backlog_report: dict
    auto_improve_session_report_paths: list[str]
    consumed_next_run_decision_ids: list[str]
    next_run_decisions: list[dict]
    system_log: Path
    recent_log_sections: list[RecentLogSection]
    recent_log_section_ordering: str


@dataclass(frozen=True)
class NextRunDecisionQueueInputs:
    auto_improve_session_report_paths: list[str]
    consumed_next_run_decision_ids: list[str]
    next_run_decisions: list[dict]


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


def load_next_run_decision_queue_inputs(vault: Path) -> NextRunDecisionQueueInputs:
    session_report_paths = _auto_improve_session_report_paths(vault)
    next_run_decisions = _load_next_run_decisions(vault, session_report_paths)
    consumed_next_run_decision_ids = _load_consumed_next_run_decision_ids(
        vault,
        session_report_paths,
        next_run_decisions,
    )
    return NextRunDecisionQueueInputs(
        auto_improve_session_report_paths=session_report_paths,
        consumed_next_run_decision_ids=consumed_next_run_decision_ids,
        next_run_decisions=next_run_decisions,
    )


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


def _effective_mutation_policy(
    policy: dict,
    *,
    max_proposals: int | None,
    dedupe_window: int | None,
) -> tuple[dict, dict]:
    mutation_policy = dict(policy["mutation_proposal"])
    if max_proposals is not None:
        mutation_policy["max_proposals"] = max_proposals
    if dedupe_window is not None:
        mutation_policy["dedupe_window"] = dedupe_window
    effective_policy = dict(policy)
    effective_policy["mutation_proposal"] = mutation_policy
    return effective_policy, mutation_policy


def _load_current_mechanism_review_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    mechanism_review_report_path: str | None,
) -> tuple[Path, dict]:
    mechanism_review_path = (
        vault / (mechanism_review_report_path or DEFAULT_MECHANISM_REVIEW_REPORT)
    ).resolve()
    if not mechanism_review_path.exists():
        raise FileNotFoundError(
            f"missing mechanism review report: {report_path(vault, mechanism_review_path)}"
        )
    mechanism_review_report = _load_mechanism_review_report(vault, mechanism_review_path)
    review_policy = mechanism_review_report.get("policy", {})
    if review_policy.get("path") != report_path(vault, policy_path):
        raise ValueError(
            "mechanism review report policy.path does not match current policy: "
            f"{review_policy.get('path')}"
        )
    if review_policy.get("version") != policy["version"]:
        raise ValueError(
            "mechanism review report policy.version does not match current policy: "
            f"{review_policy.get('version')}"
        )
    return mechanism_review_path, mechanism_review_report


def load_mutation_report_inputs(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    mechanism_review_report_path: str | None,
    system_log_path: str | None,
    max_proposals: int | None,
    dedupe_window: int | None,
    context: RuntimeContext | None,
) -> MutationReportInputs:
    runtime_context = context or RuntimeContext.from_policy(policy)
    effective_policy, mutation_policy = _effective_mutation_policy(
        policy,
        max_proposals=max_proposals,
        dedupe_window=dedupe_window,
    )
    mechanism_review_path, mechanism_review_report = _load_current_mechanism_review_report(
        vault,
        policy,
        policy_path,
        mechanism_review_report_path,
    )
    outcome_metrics_path = (vault / DEFAULT_OUTCOME_METRICS_REPORT).resolve()
    outcome_metrics_report = _read_optional_report(outcome_metrics_path)
    remediation_backlog_path = (vault / DEFAULT_REMEDIATION_BACKLOG_REPORT).resolve()
    remediation_backlog_report = _read_optional_report(remediation_backlog_path)
    next_run_decision_inputs = load_next_run_decision_queue_inputs(vault)
    system_log = (vault / (system_log_path or DEFAULT_SYSTEM_LOG)).resolve()
    recent_log_sections, recent_log_section_ordering = _read_log_sections(
        system_log,
        max_entries=mutation_policy["dedupe_window"],
        max_age_days=int(mutation_policy["recent_log_overlap_max_age_days"]),
        runtime_context=runtime_context,
    )
    return MutationReportInputs(
        runtime_context=runtime_context,
        effective_policy=effective_policy,
        mutation_policy=mutation_policy,
        mechanism_review_path=mechanism_review_path,
        mechanism_review_report=mechanism_review_report,
        outcome_metrics_path=outcome_metrics_path,
        outcome_metrics_report=outcome_metrics_report,
        remediation_backlog_path=remediation_backlog_path,
        remediation_backlog_report=remediation_backlog_report,
        auto_improve_session_report_paths=next_run_decision_inputs.auto_improve_session_report_paths,
        consumed_next_run_decision_ids=next_run_decision_inputs.consumed_next_run_decision_ids,
        next_run_decisions=next_run_decision_inputs.next_run_decisions,
        system_log=system_log,
        recent_log_sections=recent_log_sections,
        recent_log_section_ordering=recent_log_section_ordering,
    )
