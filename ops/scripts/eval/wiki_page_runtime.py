from __future__ import annotations

import re
from pathlib import Path

from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.source_trace_runtime import extract_source_trace_refs

PAGE_ROOTS = ("wiki", "system")
SPECIAL_PAGES = {"AGENTS"}
INDEXISH_PAGES = {"index", "system-index", "system-log"}
OPEN_QUESTION_SEVERITY_RE = re.compile(r"^\s*[-*]\s+\[(high|medium)\](?:\s|$)", re.IGNORECASE)
RequiredSections = dict[str, list[str] | dict[str, list[str]]]


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def line_count(path: Path) -> int:
    return len(load_text(path).splitlines())


def discover_pages(vault: Path) -> tuple[dict[str, Path], dict[str, list[Path]]]:
    pages: dict[str, Path] = {}
    duplicates: dict[str, list[Path]] = {}
    for root_name in PAGE_ROOTS:
        root = vault / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            existing = pages.get(path.stem)
            if existing is None:
                pages[path.stem] = path
                continue
            duplicates.setdefault(path.stem, [existing]).append(path)
    return pages, duplicates


def section_exists(text: str, heading: str) -> bool:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def heading_body(text: str, heading: str, level: int = 2) -> str | None:
    pattern = rf"^{'#' * level}\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    start = match.end()
    next_heading = re.search(rf"^#{{1,{level}}}\s+", text[start:], flags=re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def section_body(text: str, heading: str) -> str | None:
    return heading_body(text, heading, level=2)


def source_trace_item_count(source_trace: str | None) -> int:
    if not source_trace:
        return 0
    refs = extract_source_trace_refs(source_trace)
    if refs:
        return len(refs)
    return sum(1 for line in source_trace.splitlines() if line.strip().startswith("- "))


def open_question_severity_counts(open_questions: str | None) -> dict[str, int]:
    counts = {
        "high": 0,
        "medium": 0,
    }
    if not open_questions:
        return counts
    for line in open_questions.splitlines():
        match = OPEN_QUESTION_SEVERITY_RE.match(line)
        if not match:
            continue
        counts[match.group(1).lower()] += 1
    return counts


def page_prefix(stem: str, required_sections: RequiredSections) -> str | None:
    for prefix in required_sections:
        if prefix == "special_pages":
            continue
        if stem.startswith(prefix):
            return prefix
    return None


def required_sections_for_page(
    vault: Path,
    path: Path,
    stem: str,
    required_sections: RequiredSections,
) -> list[str]:
    relative_path = report_path(vault, path)
    special_pages = required_sections.get("special_pages", {})
    if isinstance(special_pages, dict) and relative_path in special_pages:
        return special_pages[relative_path]
    prefix = page_prefix(stem, required_sections)
    if prefix:
        sections = required_sections[prefix]
        if isinstance(sections, list):
            return sections
    return []
