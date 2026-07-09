from __future__ import annotations

import re
from pathlib import Path

from ops.scripts.core.source_trace_profile_runtime import (
    RELEASE_ARCHIVE_PROFILE,
    STRICT_PROFILE,
    blocking_source_trace_targets_for_profile,
    classify_source_trace_targets,
)
from ops.scripts.core.source_trace_runtime import missing_source_trace_targets

from .wiki_manifest import classify_release_manifest_path
from .wiki_page_runtime import open_question_severity_counts, section_exists
from .wikilink_runtime import extract_wikilinks, resolve_wikilink_target

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|fill later)\b", re.I)


def missing_required_sections(text: str, headings: list[str]) -> list[str]:
    return [heading for heading in headings if not section_exists(text, heading)]


def resolved_wikilink_targets(text: str | None, page_lookup: dict[str, str]) -> set[str]:
    resolved_targets: set[str] = set()
    for target in extract_wikilinks(text):
        resolved_target = resolve_wikilink_target(target, page_lookup)
        if resolved_target is not None:
            resolved_targets.add(resolved_target)
    return resolved_targets


def broken_wikilinks(text: str, page_lookup: dict[str, str], special_pages: set[str]) -> list[str]:
    broken: list[str] = []
    for target in extract_wikilinks(text):
        if resolve_wikilink_target(target, page_lookup) is not None or target in special_pages:
            continue
        broken.append(target)
    return broken


def source_trace_targets_missing(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
) -> list[dict[str, str]]:
    return missing_source_trace_targets(vault, source_trace, resolution_map)


def source_trace_targets_for_profile(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
    *,
    release_archive_profile: bool = False,
) -> list[dict]:
    profile = RELEASE_ARCHIVE_PROFILE if release_archive_profile else STRICT_PROFILE
    return classify_source_trace_targets(
        vault,
        source_trace,
        resolution_map,
        profile=profile,
    )


def source_trace_targets_blocking_profile(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
    *,
    release_archive_profile: bool = False,
) -> list[dict]:
    profile = RELEASE_ARCHIVE_PROFILE if release_archive_profile else STRICT_PROFILE
    return blocking_source_trace_targets_for_profile(
        vault,
        source_trace,
        resolution_map,
        profile=profile,
    )


def source_trace_target_is_release_excluded(target: dict[str, str]) -> bool:
    return any(
        classify_release_manifest_path(target.get(key)).excluded
        for key in ("ref", "resolved_path")
    )


def filter_release_excluded_source_trace_targets(
    missing_targets: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        target
        for target in missing_targets
        if not source_trace_target_is_release_excluded(target)
    ]


def has_placeholder(text: str) -> bool:
    return PLACEHOLDER_RE.search(text) is not None


def open_question_budget_status(open_questions: str | None, readiness_gate: dict) -> dict:
    counts = open_question_severity_counts(open_questions)
    high_max = readiness_gate["max_high_severity_open_questions"]
    medium_max = readiness_gate["max_medium_severity_open_questions"]
    medium_severity = "warn" if readiness_gate["allow_warn_for_medium_question_overflow"] else "fail"
    return {
        "counts": counts,
        "high_overflow": counts["high"] > high_max,
        "medium_overflow": counts["medium"] > medium_max,
        "high_max": high_max,
        "medium_max": medium_max,
        "medium_overflow_severity": medium_severity,
    }
