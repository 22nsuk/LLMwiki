from __future__ import annotations

import json
import re
from pathlib import Path

from ops.scripts.wiki_page_runtime import section_body

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
