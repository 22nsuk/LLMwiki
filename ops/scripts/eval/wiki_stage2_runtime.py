from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .wiki_page_runtime import heading_body, section_body
from .wiki_quality_runtime import missing_required_sections, resolved_wikilink_targets


def evidence_source_links(text: str, page_lookup: dict[str, str]) -> list[str]:
    return sorted(
        target
        for target in resolved_wikilink_targets(section_body(text, "Evidence considered"), page_lookup)
        if target.startswith("source--")
    )


def broad_wiki_synthesis_metrics(
    text: str,
    evidence_source_stems: Iterable[str],
    content_promotion_review: dict,
) -> dict:
    evidence_source_stems = list(evidence_source_stems)
    source_links = len(evidence_source_stems)
    analysis = section_body(text, "Analysis") or ""
    analysis_subsections = sum(1 for line in analysis.splitlines() if line.startswith("### "))
    line_count = len(text.splitlines())
    threshold = {
        "source_links": content_promotion_review["wiki_multi_question_min_source_links"],
        "analysis_subsections": content_promotion_review["wiki_multi_question_min_analysis_subsections"],
        "line_count": content_promotion_review["wiki_multi_question_min_lines"],
    }
    value = {
        "source_links": source_links,
        "analysis_subsections": analysis_subsections,
        "line_count": line_count,
    }
    return {
        "value": value,
        "threshold": threshold,
        "applies": (
            value["source_links"] >= threshold["source_links"]
            and value["analysis_subsections"] >= threshold["analysis_subsections"]
            and value["line_count"] >= threshold["line_count"]
        ),
    }


def broad_synthesis_boundary_missing_sections(text: str) -> list[str]:
    return missing_required_sections(
        text,
        [
            "What this synthesis excludes",
            "Tensions / contradictions",
            "Implications for future ingest",
        ],
    )


BACKTICK_AXIS_RE = re.compile(r"`([^`\n]{1,120})`")
CONTENT_QUALITY_HEADING_RE = re.compile(r"^#{2,6}\s+(.+?)\s*$", re.MULTILINE)


def _backticked_axes(body: str | None) -> list[str]:
    if not body:
        return []
    axes: list[str] = []
    seen: set[str] = set()
    for match in BACKTICK_AXIS_RE.finditer(body):
        value = match.group(1).strip()
        if not value or value in seen:
            continue
        axes.append(value)
        seen.add(value)
    return axes


def broad_synthesis_watch_advisory(text: str) -> dict:
    exclusions = section_body(text, "What this synthesis excludes")
    tensions = section_body(text, "Tensions / contradictions")
    implications = section_body(text, "Implications for future ingest")
    return {
        "boundary_sections_present": [
            heading
            for heading, body in (
                ("What this synthesis excludes", exclusions),
                ("Tensions / contradictions", tensions),
                ("Implications for future ingest", implications),
            )
            if body is not None
        ],
        "exclusion_axes": _backticked_axes(exclusions),
        "tension_axes": _backticked_axes(tensions),
        "future_ingest_axes": _backticked_axes(implications),
    }


def inbound_page_linkers(page_links: dict[str, set[str]], pages: dict[str, Path]) -> dict[str, set[str]]:
    inbound_sources: dict[str, set[str]] = defaultdict(set)
    for source_stem, targets in page_links.items():
        for target_stem in targets:
            if target_stem in pages:
                inbound_sources[target_stem].add(source_stem)
    return inbound_sources


def research_anchor_missing_sections(text: str, required_sections: list[str]) -> list[str]:
    return missing_required_sections(text, required_sections)


def stable_wiki_inbound_linkers(inbound_linkers: Iterable[str]) -> list[str]:
    return sorted(
        linker
        for linker in inbound_linkers
        if linker.startswith(("concept--", "synthesis--"))
    )


def seed_source_missing_sections(text: str) -> list[str]:
    return missing_required_sections(
        text,
        [
            "Why this is source-only for now",
            "What future cluster would absorb this",
        ],
    )


def content_quality_scaffold_missing_sections(text: str, recommended_headings: list[str]) -> list[str]:
    headings = {match.group(1).strip() for match in CONTENT_QUALITY_HEADING_RE.finditer(text)}
    return [heading for heading in recommended_headings if heading not in headings]


def _content_quality_heading_body(text: str, heading: str) -> str | None:
    for level in range(2, 7):
        body = heading_body(text, heading, level=level)
        if body is not None:
            return body
    return None


def content_quality_scaffold_body_issues(
    text: str,
    recommended_headings: list[str],
    *,
    min_section_chars: int = 40,
) -> list[dict]:
    issues: list[dict] = []
    for heading in recommended_headings:
        body = _content_quality_heading_body(text, heading)
        if body is None:
            continue
        stripped = body.strip()
        if len(stripped) < min_section_chars:
            issues.append(
                {
                    "heading": heading,
                    "issue": "section_body_too_thin",
                    "value": len(stripped),
                    "threshold": min_section_chars,
                }
            )

    evidence_ladder = _content_quality_heading_body(text, "Evidence ladder") or ""
    lowered_ladder = evidence_ladder.lower()
    has_strong = "강한" in evidence_ladder or "strong" in lowered_ladder
    has_weak = any(
        marker in evidence_ladder or marker in lowered_ladder
        for marker in (
            "약한",
            "약하",
            "중간 evidence",
            "보조 evidence",
            "primary evidence가 아니다",
            "weak",
            "secondary evidence",
            "supporting evidence",
        )
    )
    if evidence_ladder.strip() and not (has_strong and has_weak):
        issues.append(
            {
                "heading": "Evidence ladder",
                "issue": "missing_strength_tiers",
                "required_markers": ["strong/강한", "weak/약한"],
            }
        )

    boundary_parts = [
        _content_quality_heading_body(text, "Boundary") or "",
        section_body(text, "Scope boundaries") or "",
        section_body(text, "Examples and non-examples") or "",
        section_body(text, "What this synthesis excludes") or "",
    ]
    boundary = "\n".join(part for part in boundary_parts if part.strip())
    lowered_boundary = boundary.lower()
    if boundary.strip() and not any(
        marker in boundary or marker in lowered_boundary
        for marker in (
            "아니다",
            "아니라",
            "않는다",
            "범위 밖",
            "흡수하지",
            "제외",
            "비예시",
            "not",
            "exclude",
            "non-example",
        )
    ):
        issues.append(
            {
                "heading": "Boundary",
                "issue": "missing_exclusion_language",
            }
        )

    return issues
