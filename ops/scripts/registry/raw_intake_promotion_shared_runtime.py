from __future__ import annotations

import json
import re
from pathlib import Path

from ops.scripts.eval.wiki_page_runtime import section_body

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_SUBHEADING_RE = re.compile(r"^###\s+(.+?)\s*$", flags=re.MULTILINE)
_WORD_ACRONYMS = {
    "ai": "AI",
    "api": "API",
    "eu": "EU",
    "imf": "IMF",
    "it": "IT",
    "korea": "Korea",
    "uk": "UK",
    "us": "US",
}
SYNTHESIS_ANALYSIS_SCAFFOLD = (
    ("Core model", "core-model"),
    ("Common misread", "common-misread"),
    ("Key variables", "key-variables"),
    ("Mechanism", "mechanism"),
    ("How the evidence changes the answer", "evidence-changes-answer"),
    ("Evidence ladder", "evidence-ladder"),
    ("Concrete examples", "concrete-examples"),
    ("Tensions / counterevidence", "tensions-counterevidence"),
    ("What would change the answer", "answer-change-conditions"),
    ("Boundary", "boundary"),
)
SYNTHESIS_ANALYSIS_SCAFFOLD_HEADINGS = tuple(
    heading for heading, _purpose in SYNTHESIS_ANALYSIS_SCAFFOLD
)
CONCEPT_ANALYSIS_SCAFFOLD = (
    ("Core model", "core-model"),
    ("Common misread", "common-misread"),
    ("Key variables", "key-variables"),
    ("Mechanism", "mechanism"),
    ("Evidence ladder", "evidence-ladder"),
    ("Concrete examples", "concrete-examples"),
    ("Boundary", "boundary"),
)
CONCEPT_ANALYSIS_SCAFFOLD_HEADINGS = tuple(
    heading for heading, _purpose in CONCEPT_ANALYSIS_SCAFFOLD
)
EVIDENCE_MAP_COLUMNS = (
    ("channel", "Channel"),
    ("sources", "Sources"),
    ("what_they_show", "What they show"),
    ("caveat", "Caveat"),
    ("implication", "Implication"),
)
_EVIDENCE_MAP_ALIASES = {
    "channel": ("channel", "source_cluster", "cluster"),
    "sources": ("sources", "source_stems", "source_refs"),
    "what_they_show": ("what_they_show", "what_it_shows", "what_it_adds", "what_they_add"),
    "caveat": ("caveat", "limitations", "limitation"),
    "implication": ("implication", "implications"),
}


def _json_load_object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json root must be an object")
    return payload


def _titleize_slug(slug: str) -> str:
    words = [item for item in slug.replace("_", "-").split("-") if item]
    normalized = []
    for word in words:
        lowered = word.lower()
        normalized.append(_WORD_ACRONYMS.get(lowered, lowered.capitalize()))
    return " ".join(normalized)


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _wikilink_if_source(value: str) -> str:
    if value.startswith("source--") and "[[" not in value:
        return f"[[{value}]]"
    return value


def _evidence_map_cell(value: object) -> str:
    if isinstance(value, list):
        return "<br>".join(
            _wikilink_if_source(item.strip())
            for item in value
            if isinstance(item, str) and item.strip()
        )
    if isinstance(value, str):
        return _wikilink_if_source(value.strip())
    return ""


def _evidence_map_value(row: dict, canonical_key: str) -> str:
    for key in _EVIDENCE_MAP_ALIASES[canonical_key]:
        value = _evidence_map_cell(row.get(key))
        if value:
            return value
    return ""


def _evidence_map_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        row = {
            canonical_key: _evidence_map_value(item, canonical_key)
            for canonical_key, _label in EVIDENCE_MAP_COLUMNS
        }
        if any(row.values()):
            rows.append(row)
    return rows


def _combined_source_stems(payload: dict) -> list[str]:
    return _dedupe(
        _string_list(payload.get("bridge_source_stems")) + _string_list(payload.get("source_stems"))
    )


def _frontmatter_value(text: str, field: str) -> str:
    pattern = rf'^{re.escape(field)}:\s*(?:"([^"]*)"|\'([^\']*)\'|([^\n#]+))\s*$'
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    for group in match.groups():
        if group is not None:
            return group.strip().strip('"').strip("'")
    return ""


def _section_links(text: str, heading: str) -> list[str]:
    body = section_body(text, heading) or ""
    return [match.group(1).strip() for match in _WIKILINK_RE.finditer(body)]


def _split_subheading_blocks(text: str) -> list[dict]:
    body = text.strip()
    if not body:
        return []

    matches = list(_SUBHEADING_RE.finditer(body))
    if not matches:
        return [{"heading": "Integrated analysis", "body": body}]

    blocks: list[dict] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        blocks.append(
            {
                "heading": match.group(1).strip(),
                "body": body[start:end].strip(),
            }
        )
    return blocks


def _section_items(text: str, heading: str) -> list[str]:
    body = section_body(text, heading) or ""
    lines = [line.strip() for line in body.splitlines()]
    bullet_items = [line[2:].strip() for line in lines if line.startswith("- ")]
    if bullet_items:
        return [item.strip("`") for item in bullet_items if item]

    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", body) if item.strip()]
    return [paragraph for paragraph in paragraphs if paragraph]


def _normalize_table_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _section_evidence_map_rows(text: str, heading: str = "Evidence map") -> list[dict[str, str]]:
    body = section_body(text, heading) or ""
    table_lines = [line for line in body.splitlines() if line.strip().startswith("|")]
    if len(table_lines) < 2:
        return []
    headers = [_normalize_table_header(cell) for cell in _split_table_row(table_lines[0])]
    if not headers:
        return []
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _split_table_row(line)
        if not cells:
            continue
        raw_row = dict(zip(headers, cells, strict=False))
        rows.append(
            {
                canonical_key: _evidence_map_value(raw_row, canonical_key)
                for canonical_key, _label in EVIDENCE_MAP_COLUMNS
            }
        )
    return [row for row in rows if any(row.values())]
