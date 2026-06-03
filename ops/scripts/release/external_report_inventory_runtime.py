#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import report_path

from .external_report_action_catalog import ACTION_CATALOG

REFERENCE_MANIFEST = "external-reports/report-reference-manifest.json"
REFERENCE_MANIFEST_EXTENSIONS = {".md", ".pdf", ".docx"}
REPORT_EXTENSIONS = REFERENCE_MANIFEST_EXTENSIONS
NARRATIVE_REPORT_EXTENSIONS = {".md"}
BINARY_REPORT_EXTENSIONS = REPORT_EXTENSIONS - NARRATIVE_REPORT_EXTENSIONS

ARCHIVE_STATUS_RE = re.compile(
    r"(?im)^\s*(?:archive_status|lifecycle_status|report_status)\s*[:=]\s*"
    r"`?(closed|superseded|archived)`?\s*$"
)
SUPERSEDED_BY_RE = re.compile(r"(?im)^\s*(?:superseded_by|replaced_by)\s*[:=]\s*`?([^`\n]+)`?")
COVERAGE_MARKER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("actual_file_crosscheck", r"actual[-_ ]file|실제\s*파일|파일\s*대조"),
    ("integrated_review", r"integrated|consolidated|통합\s*리뷰|통합\s*검토|종합\s*검토"),
    ("final_conclusion", r"final\s+conclusion|최종\s*결론|최종\s*권고|최종\s*판정"),
    ("live_reverification", r"live\s+truth|재검증|직접\s*재실행|실제\s*재검증"),
)


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _external_report_paths(vault: Path, *, extensions: set[str]) -> list[Path]:
    root = vault / "external-reports"
    if not root.is_dir():
        return []
    manifest_path = (vault / REFERENCE_MANIFEST).resolve()
    paths: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in REPORT_EXTENSIONS:
            continue
        if path.resolve() == manifest_path:
            continue
        if path.parent.name in {"archive", "archived"}:
            continue
        paths.append(path)
    return paths


def active_report_paths(vault: Path) -> list[Path]:
    return _external_report_paths(vault, extensions=REPORT_EXTENSIONS)


def active_reference_report_paths(vault: Path) -> list[Path]:
    return _external_report_paths(vault, extensions=REFERENCE_MANIFEST_EXTENSIONS)


def report_type_for_path(path: Path) -> str:
    if path.name == Path(REFERENCE_MANIFEST).name:
        return "reference_manifest"
    if path.suffix.lower() in NARRATIVE_REPORT_EXTENSIONS:
        return "narrative_report"
    if path.suffix.lower() in BINARY_REPORT_EXTENSIONS:
        return "binary_report"
    return "unknown_report"


def is_binary_report_path(path: Path) -> bool:
    return report_type_for_path(path) == "binary_report"


def reference_manifest_alignment(vault: Path) -> dict[str, Any]:
    manifest_path = vault / REFERENCE_MANIFEST
    expected_paths = sorted(report_path(vault, path) for path in active_reference_report_paths(vault))
    if not manifest_path.is_file():
        return {
            "status": "missing_manifest",
            "expected_reference_paths": expected_paths,
            "manifest_reference_paths": [],
            "missing_active_report_paths": expected_paths,
            "stale_reference_paths": [],
        }
    manifest = load_json_object(manifest_path)
    references = as_list(manifest.get("references"))
    manifest_paths = sorted(
        str(item.get("path"))
        for item in references
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    )
    if len(manifest_paths) != len(references):
        status = "unreadable_manifest"
    else:
        missing = sorted(set(expected_paths) - set(manifest_paths))
        stale = sorted(set(manifest_paths) - set(expected_paths))
        status = "current" if not missing and not stale else "drift"
    missing_paths = sorted(set(expected_paths) - set(manifest_paths))
    stale_paths = sorted(set(manifest_paths) - set(expected_paths))
    return {
        "status": status,
        "expected_reference_paths": expected_paths,
        "manifest_reference_paths": manifest_paths,
        "missing_active_report_paths": missing_paths,
        "stale_reference_paths": stale_paths,
    }


def archived_report_count(vault: Path) -> int:
    archive = vault / "external-reports" / "archive"
    if not archive.is_dir():
        return 0
    return sum(
        1
        for path in archive.iterdir()
        if path.is_file() and path.suffix.lower() in REPORT_EXTENSIONS
    )


def report_text(path: Path) -> str:
    if path.suffix.lower() not in NARRATIVE_REPORT_EXTENSIONS:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def content_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def priority_counts(text: str) -> dict[str, int]:
    return {
        priority: len(re.findall(rf"\b{priority}\b", text))
        for priority in ("P0", "P1", "P2")
    }


def matched_actions(text: str) -> list[str]:
    matches: list[str] = []
    for action in ACTION_CATALOG:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in action["patterns"]):
            matches.append(str(action["action_id"]))
    return matches


def coverage_markers(path: Path, text: str) -> list[str]:
    haystack = f"{path.name}\n{text}"
    return [
        marker
        for marker, pattern in COVERAGE_MARKER_PATTERNS
        if re.search(pattern, haystack, flags=re.IGNORECASE)
    ]
