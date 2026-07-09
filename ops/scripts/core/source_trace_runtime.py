from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .path_runtime import normalize_repo_path_text, stable_report_path

SOURCE_TRACE_REF_RE = re.compile(r"`([^`]+)`")
URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass(frozen=True)
class SourceTraceRef:
    raw_ref: str
    normalized_ref: str


def _flat_script_relocation(vault: Path, normalized_ref: str) -> Path | None:
    path = Path(normalized_ref)
    if path.parts[:2] != ("ops", "scripts") or len(path.parts) != 3 or path.suffix != ".py":
        return None

    matches = sorted((vault / "ops" / "scripts").glob(f"*/{path.name}"))
    if len(matches) == 1 and matches[0].is_file():
        return matches[0]
    return None


def normalize_source_trace_ref(ref: str) -> str:
    normalized = ref.strip()
    if not normalized:
        return ""
    if URL_SCHEME_RE.match(normalized):
        return normalized
    return normalize_repo_path_text(normalized) or ""


def extract_source_trace_refs(source_trace: str | None) -> list[str]:
    return [record.normalized_ref for record in extract_source_trace_ref_records(source_trace)]


def extract_source_trace_ref_records(source_trace: str | None) -> list[SourceTraceRef]:
    if not source_trace:
        return []

    refs: list[SourceTraceRef] = []
    seen: set[str] = set()
    for ref in SOURCE_TRACE_REF_RE.findall(source_trace):
        normalized = normalize_source_trace_ref(ref)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        refs.append(SourceTraceRef(raw_ref=ref, normalized_ref=normalized))
    return refs


def resolve_source_trace_ref(
    vault: Path,
    ref: str,
    resolution_map: dict[str, list[str]] | None = None,
) -> Path | None:
    normalized_ref = normalize_source_trace_ref(ref)
    if not normalized_ref or URL_SCHEME_RE.match(normalized_ref):
        return None

    if resolution_map and normalized_ref in resolution_map:
        candidate_locators = resolution_map[normalized_ref]
        for locator in candidate_locators:
            candidate_path = vault / locator
            if candidate_path.exists():
                return candidate_path
        return vault / candidate_locators[0]

    path = Path(normalized_ref)
    if path.is_absolute():
        return path
    relocated = _flat_script_relocation(vault, normalized_ref)
    if relocated is not None:
        return relocated
    return vault / path


def report_source_trace_path(vault: Path, path: Path) -> str:
    return stable_report_path(vault, path)


def missing_source_trace_targets(
    vault: Path,
    source_trace: str | None,
    resolution_map: dict[str, list[str]] | None = None,
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for ref in extract_source_trace_refs(source_trace):
        resolved = resolve_source_trace_ref(vault, ref, resolution_map)
        if resolved is None or resolved.exists():
            continue
        missing.append(
            {
                "ref": ref,
                "resolved_path": report_source_trace_path(vault, resolved),
            }
        )
    return missing
