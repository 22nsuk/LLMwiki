from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ops.scripts.frontmatter_runtime import parse_frontmatter
from ops.scripts.raw_registry_runtime import load_registry_source_trace_resolution_state
from .wiki_page_runtime import discover_pages, load_text, section_body
from .wiki_quality_runtime import resolved_wikilink_targets
from .wikilink_runtime import build_page_lookup


@dataclass(frozen=True)
class WikiRuntimeSnapshot:
    vault: Path
    pages: dict[str, Path]
    duplicate_stems: dict[str, list[Path]]
    texts: dict[str, str]
    frontmatters: dict[str, dict | None]
    frontmatter_errors: dict[str, str]
    page_lookup: dict[str, str]
    page_links: dict[str, set[str]]
    related_links: dict[str, set[str]]
    evidence_links: dict[str, set[str]]
    source_trace_resolution_state: dict

    @property
    def source_trace_resolution_map(self) -> dict[str, list[str]]:
        return self.source_trace_resolution_state["resolution_map"]


def build_wiki_runtime_snapshot(
    vault: Path,
    *,
    registry_contract: dict | None = None,
    include_frontmatter: bool = True,
    include_page_links: bool = True,
    include_related_links: bool = True,
    include_evidence_links: bool = True,
) -> WikiRuntimeSnapshot:
    pages, duplicate_stems = discover_pages(vault)
    page_lookup = build_page_lookup(vault, pages)

    texts: dict[str, str] = {}
    frontmatters: dict[str, dict | None] = {}
    frontmatter_errors: dict[str, str] = {}
    page_links: dict[str, set[str]] = {}
    related_links: dict[str, set[str]] = {}
    evidence_links: dict[str, set[str]] = {}

    for stem, path in pages.items():
        text = load_text(path)
        texts[stem] = text
        if include_frontmatter:
            try:
                frontmatters[stem] = parse_frontmatter(text)
            except ValueError as exc:
                frontmatter_errors[stem] = str(exc)
                frontmatters[stem] = None
        if include_page_links:
            page_links[stem] = resolved_wikilink_targets(text, page_lookup)
        if include_related_links:
            related_links[stem] = resolved_wikilink_targets(section_body(text, "Related pages"), page_lookup)
        if include_evidence_links:
            evidence_links[stem] = resolved_wikilink_targets(section_body(text, "Evidence considered"), page_lookup)

    source_trace_resolution_state = (
        load_registry_source_trace_resolution_state(vault, registry_contract)
        if registry_contract is not None
        else {"resolution_map": {}, "warnings": []}
    )

    return WikiRuntimeSnapshot(
        vault=vault,
        pages=pages,
        duplicate_stems=duplicate_stems,
        texts=texts,
        frontmatters=frontmatters,
        frontmatter_errors=frontmatter_errors,
        page_lookup=page_lookup,
        page_links=page_links,
        related_links=related_links,
        evidence_links=evidence_links,
        source_trace_resolution_state=source_trace_resolution_state,
    )
