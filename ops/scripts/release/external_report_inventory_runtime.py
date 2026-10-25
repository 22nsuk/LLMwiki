#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ops.scripts.core.policy_runtime import report_path

from .external_report_action_catalog import ACTION_CATALOG

REFERENCE_MANIFEST = "external-reports/report-reference-manifest.json"
LOCAL_REPORT_LINE_DIGESTS = "external-reports/report-line-action-digests.json"
REFERENCE_MANIFEST_EXTENSIONS = {".md", ".pdf", ".docx"}
REPORT_EXTENSIONS = REFERENCE_MANIFEST_EXTENSIONS
NARRATIVE_REPORT_EXTENSIONS = {".md"}
BINARY_REPORT_EXTENSIONS = REPORT_EXTENSIONS - NARRATIVE_REPORT_EXTENSIONS
RECOMMENDATION_INTAKE_STATUSES = (
    "reviewed",
    "legacy",
    "missing",
    "stale",
    "invalid",
    "not_applicable",
    "unreadable",
)

ARCHIVE_STATUS_RE = re.compile(
    r"(?im)^\s*(?:archive_status|lifecycle_status|report_status)\s*[:=]\s*"
    r"`?(closed|superseded|archived)`?\s*$"
)
SUPERSEDED_BY_RE = re.compile(r"(?im)^\s*(?:superseded_by|replaced_by)\s*[:=]\s*`?([^`\n]+)`?")
HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s")
PRIORITY_NOTATION_META_RE = re.compile(
    r"(?i)(?:"
    r"우선순위\s*표기|"
    r"priority\s*notation|"
    r"정식\s*CVSS|"
    r"not\s+a\s+cvss"
    r")"
)
SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")

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


def as_str_tuple(value: Any) -> tuple[str, ...]:
    return tuple(item for item in as_list(value) if isinstance(item, str))


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
        if not path.is_file() or path.suffix.lower() not in extensions:
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


def archived_report_paths(vault: Path) -> list[Path]:
    archive = vault / "external-reports" / "archive"
    if not archive.is_dir():
        return []
    return sorted(
        path
        for path in archive.iterdir()
        if path.is_file() and path.suffix.lower() in REPORT_EXTENSIONS
    )


def archived_report_count(vault: Path) -> int:
    return len(archived_report_paths(vault))


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


def line_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def report_line_digest_policy(
    vault: Path | None = None,
) -> tuple[dict[str, tuple[str, ...]], frozenset[str]]:
    root = vault if vault is not None else Path.cwd()
    payload = load_json_object(root / LOCAL_REPORT_LINE_DIGESTS)
    action_line_sha256: dict[str, tuple[str, ...]] = {}
    for digest, value in as_dict(payload.get("action_line_sha256")).items():
        if not isinstance(digest, str):
            continue
        action_ids = as_str_tuple(value)
        if action_ids:
            action_line_sha256[digest] = action_ids
    operator_context_line_sha256 = frozenset(
        item
        for item in as_list(payload.get("operator_context_line_sha256"))
        if isinstance(item, str)
    )
    return action_line_sha256, operator_context_line_sha256


def _empty_recommendation_intake(
    status: str,
    *,
    error_codes: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "recommendation_intake_status": status,
        "recommendation_intake_error_codes": list(error_codes),
        "recommendation_candidate_count": 0,
        "recommendation_covered_count": 0,
        "recommendation_unresolved_count": 0,
        "exact_mapped_action_ids": [],
        "unmatched_recommendation_line_sha256": [],
        "matched_action_ids": [],
    }


def _legacy_recommendation_intake(
    text: str,
    *,
    line_action_digests: Mapping[str, tuple[str, ...]],
    operator_context_line_digests: frozenset[str],
) -> dict[str, Any]:
    candidate_digests: set[str] = set()
    covered_digests: set[str] = set()
    unresolved_digests: set[str] = set()
    for line in text.splitlines():
        if not is_recommendation_candidate_line(
            line,
            line_action_digests=line_action_digests,
            operator_context_line_digests=operator_context_line_digests,
        ):
            continue
        digest = line_sha256(line)
        candidate_digests.add(digest)
        if matched_actions(line, line_action_digests=line_action_digests):
            covered_digests.add(digest)
        else:
            unresolved_digests.add(digest)
    return {
        "recommendation_intake_status": "legacy",
        "recommendation_intake_error_codes": [],
        "recommendation_candidate_count": len(candidate_digests),
        "recommendation_covered_count": len(covered_digests),
        "recommendation_unresolved_count": len(unresolved_digests),
        "exact_mapped_action_ids": [],
        "unmatched_recommendation_line_sha256": sorted(unresolved_digests),
        "matched_action_ids": matched_actions(
            text,
            line_action_digests=line_action_digests,
        ),
    }


def _uses_archived_report_namespace(vault: Path, path: Path) -> bool:
    try:
        rel_path = path.resolve().relative_to((vault / "external-reports").resolve())
    except ValueError:
        return False
    return bool(rel_path.parts) and rel_path.parts[0] in {"archive", "archived"}


def report_recommendation_intake(
    vault: Path,
    *,
    path: Path,
    text: str,
    report_content_sha256: str,
) -> dict[str, Any]:
    payload = load_json_object(vault / LOCAL_REPORT_LINE_DIGESTS)
    if "report_intakes" not in payload:
        line_action_digests, operator_context_line_digests = report_line_digest_policy(
            vault
        )
        return _legacy_recommendation_intake(
            text,
            line_action_digests=line_action_digests,
            operator_context_line_digests=operator_context_line_digests,
        )

    raw_intakes = payload.get("report_intakes")
    if not isinstance(raw_intakes, dict):
        return _empty_recommendation_intake(
            "invalid",
            error_codes=("invalid_report_intake_registry",),
        )
    rel_path = report_path(vault, path)
    raw_record = raw_intakes.get(rel_path)
    if raw_record is None:
        if _uses_archived_report_namespace(vault, path):
            line_action_digests, operator_context_line_digests = (
                report_line_digest_policy(vault)
            )
            return _legacy_recommendation_intake(
                text,
                line_action_digests=line_action_digests,
                operator_context_line_digests=operator_context_line_digests,
            )
        return _empty_recommendation_intake(
            "missing",
            error_codes=("missing_report_intake",),
        )
    if not isinstance(raw_record, dict):
        return _empty_recommendation_intake(
            "invalid",
            error_codes=("invalid_report_intake_record",),
        )
    if raw_record.get("content_sha256") != report_content_sha256:
        return _empty_recommendation_intake(
            "stale",
            error_codes=("report_content_sha256_mismatch",),
        )

    errors: list[str] = []
    catalog_action_ids = {str(action["action_id"]) for action in ACTION_CATALOG}
    raw_action_lines = raw_record.get("action_line_sha256")
    action_lines: dict[str, tuple[str, ...]] = {}
    if not isinstance(raw_action_lines, dict):
        errors.append("invalid_action_line_mapping")
    else:
        for digest, raw_action_ids in raw_action_lines.items():
            action_ids = as_str_tuple(raw_action_ids)
            if not isinstance(digest, str) or not SHA256_HEX_RE.fullmatch(digest):
                errors.append("invalid_line_sha256")
                continue
            if not action_ids or any(
                action_id not in catalog_action_ids for action_id in action_ids
            ):
                errors.append("invalid_action_id")
                continue
            action_lines[digest] = tuple(dict.fromkeys(action_ids))

    def digest_set(field: str) -> set[str]:
        raw_value = raw_record.get(field)
        if not isinstance(raw_value, list):
            errors.append(f"invalid_{field}")
            return set()
        values = {item for item in raw_value if isinstance(item, str)}
        if len(values) != len(raw_value) or any(
            not SHA256_HEX_RE.fullmatch(item) for item in values
        ):
            errors.append("invalid_line_sha256")
        return {item for item in values if SHA256_HEX_RE.fullmatch(item)}

    operator_context_digests = digest_set("operator_context_line_sha256")
    unresolved_digests = digest_set("unmatched_recommendation_line_sha256")
    action_digests = set(action_lines)
    if (
        action_digests.intersection(operator_context_digests)
        or action_digests.intersection(unresolved_digests)
        or operator_context_digests.intersection(unresolved_digests)
    ):
        errors.append("overlapping_line_classification")
    report_line_digests = {line_sha256(line) for line in text.splitlines()}
    classified_digests = action_digests | operator_context_digests | unresolved_digests
    if classified_digests - report_line_digests:
        errors.append("line_digest_not_in_report")
    if errors:
        return _empty_recommendation_intake(
            "invalid",
            error_codes=tuple(dict.fromkeys(errors)),
        )

    exact_action_ids = [
        str(action["action_id"])
        for action in ACTION_CATALOG
        if any(
            str(action["action_id"]) in action_ids
            for action_ids in action_lines.values()
        )
    ]
    return {
        "recommendation_intake_status": "reviewed",
        "recommendation_intake_error_codes": [],
        "recommendation_candidate_count": len(action_digests | unresolved_digests),
        "recommendation_covered_count": len(action_digests),
        "recommendation_unresolved_count": len(unresolved_digests),
        "exact_mapped_action_ids": exact_action_ids,
        "unmatched_recommendation_line_sha256": sorted(unresolved_digests),
        "matched_action_ids": exact_action_ids,
    }


def _append_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def matched_actions(
    text: str,
    *,
    line_action_digests: Mapping[str, tuple[str, ...]] | None = None,
) -> list[str]:
    if line_action_digests is None:
        line_action_digests, _ = report_line_digest_policy()
    matches: list[str] = []
    for action in ACTION_CATALOG:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in action["patterns"]):
            _append_unique(matches, str(action["action_id"]))
    lines = text.splitlines() or [text]
    for line in lines:
        for action_id in line_action_digests.get(line_sha256(line), ()):
            _append_unique(matches, action_id)
    return matches


def is_recommendation_candidate_line(
    line: str,
    *,
    line_action_digests: Mapping[str, tuple[str, ...]] | None = None,
    operator_context_line_digests: frozenset[str] | None = None,
) -> bool:
    if line_action_digests is None or operator_context_line_digests is None:
        default_line_action_digests, default_operator_context_line_digests = (
            report_line_digest_policy()
        )
        if line_action_digests is None:
            line_action_digests = default_line_action_digests
        if operator_context_line_digests is None:
            operator_context_line_digests = default_operator_context_line_digests
    stripped = line.strip()
    if not stripped:
        return False
    digest = line_sha256(line)
    if digest in operator_context_line_digests:
        return False
    if digest in line_action_digests:
        return True
    if not re.search(r"\bP[0-2]\b", line):
        return False
    if HEADING_LINE_RE.match(line):
        return False
    return not PRIORITY_NOTATION_META_RE.search(line)


def is_unmatched_recommendation_line(
    line: str,
    *,
    line_action_digests: Mapping[str, tuple[str, ...]] | None = None,
    operator_context_line_digests: frozenset[str] | None = None,
) -> bool:
    if line_action_digests is None or operator_context_line_digests is None:
        default_line_action_digests, default_operator_context_line_digests = (
            report_line_digest_policy()
        )
        if line_action_digests is None:
            line_action_digests = default_line_action_digests
        if operator_context_line_digests is None:
            operator_context_line_digests = default_operator_context_line_digests
    if not is_recommendation_candidate_line(
        line,
        line_action_digests=line_action_digests,
        operator_context_line_digests=operator_context_line_digests,
    ):
        return False
    return not matched_actions(line, line_action_digests=line_action_digests)


def unmatched_recommendation_count(
    text: str,
    *,
    line_action_digests: Mapping[str, tuple[str, ...]] | None = None,
    operator_context_line_digests: frozenset[str] | None = None,
) -> int:
    if line_action_digests is None or operator_context_line_digests is None:
        default_line_action_digests, default_operator_context_line_digests = (
            report_line_digest_policy()
        )
        if line_action_digests is None:
            line_action_digests = default_line_action_digests
        if operator_context_line_digests is None:
            operator_context_line_digests = default_operator_context_line_digests
    return sum(
        1
        for line in text.splitlines()
        if is_unmatched_recommendation_line(
            line,
            line_action_digests=line_action_digests,
            operator_context_line_digests=operator_context_line_digests,
        )
    )


def coverage_markers(path: Path, text: str) -> list[str]:
    haystack = f"{path.name}\n{text}"
    return [
        marker
        for marker, pattern in COVERAGE_MARKER_PATTERNS
        if re.search(pattern, haystack, flags=re.IGNORECASE)
    ]
