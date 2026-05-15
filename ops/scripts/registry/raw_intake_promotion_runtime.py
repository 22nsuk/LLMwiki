from __future__ import annotations

from .raw_intake_promotion_bridge_runtime import suggest_bridge_sources_for_family
from .raw_intake_promotion_scaffold_runtime import scaffold_profile_bundle
from .raw_intake_promotion_shared_runtime import (
    _combined_source_stems,
    _dedupe,
    _quote,
    _string_list,
)
from .raw_intake_promotion_validation_runtime import (
    validate_profile_bundle,
    validate_profile_bundle_data,
)

__all__ = [
    "render_concept_page",
    "render_family_pages",
    "render_refresh_synthesis_page",
    "render_synthesis_page",
    "scaffold_profile_bundle",
    "suggest_bridge_sources_for_family",
    "validate_profile_bundle",
]


def render_family_pages(payload: dict) -> dict[str, str]:
    report = validate_profile_bundle_data(payload)
    if report["status"] == "fail":
        raise ValueError(f"profile bundle validation failed: {report['errors']}")

    rendered: dict[str, str] = {}
    for family in payload.get("families", []):
        assert isinstance(family, dict)
        synthesis = family["synthesis"]
        concept = family["concept"]
        rendered[f"wiki/{synthesis['stem']}.md"] = render_synthesis_page(family)
        rendered[f"wiki/{concept['stem']}.md"] = render_concept_page(family)
    for refresh in payload.get("refreshes", []):
        assert isinstance(refresh, dict)
        synthesis = refresh["synthesis"]
        rendered[f"wiki/{synthesis['stem']}.md"] = render_refresh_synthesis_page(refresh)
    return rendered


def render_synthesis_page(family: dict) -> str:
    synthesis = family["synthesis"]
    concept = family["concept"]
    stem = synthesis["stem"]
    combined_sources = _combined_source_stems(synthesis)
    related_pages = _dedupe(
        [
            "index",
            concept["stem"],
            *_string_list(synthesis.get("related_pages")),
            *combined_sources,
        ]
    )
    analysis_blocks = synthesis.get("analysis_blocks", [])

    lines = [
        "---",
        f"title: {_quote(synthesis['title'])}",
        'page_type: "synthesis"',
        'corpus: "wiki"',
        f"source_count: {len(combined_sources)}",
        f"created: {_quote(synthesis['created'])}",
        "aliases:",
        f"  - {_quote(stem)}",
        "tags:",
        '  - "corpus/wiki"',
        '  - "type/synthesis"',
        "---",
        "",
        f"# {stem}",
        "",
        "## Question",
        synthesis["question"].strip(),
        "",
        "## Short answer",
        synthesis["short_answer"].strip(),
        "",
        "## Evidence considered",
    ]
    for source_stem in combined_sources:
        lines.append(f"- [[{source_stem}]]")
    lines.extend(["", "## Analysis"])
    integration_note = synthesis.get("integration_note")
    if isinstance(integration_note, str) and integration_note.strip():
        lines.extend([integration_note.strip(), ""])
    for block in analysis_blocks:
        lines.extend(
            [
                f"### {block['heading'].strip()}",
                block["body"].strip(),
                "",
            ]
        )
    lines.append("## What this synthesis excludes")
    for paragraph in _string_list(synthesis.get("what_this_synthesis_excludes")):
        lines.extend([paragraph, ""])
    lines.append("## Tensions / contradictions")
    for paragraph in _string_list(synthesis.get("tensions_and_contradictions")):
        lines.extend([paragraph, ""])
    lines.append("## Implications for future ingest")
    for paragraph in _string_list(synthesis.get("implications_for_future_ingest")):
        lines.extend([paragraph, ""])
    lines.extend(
        [
            "## Decision / takeaway",
            synthesis["decision_or_takeaway"].strip(),
            "",
            "## Follow-up questions",
        ]
    )
    for question in _string_list(synthesis.get("follow_up_questions")):
        lines.append(f"- {question}")
    lines.extend(["", "## Related pages"])
    for page in related_pages:
        if page and page != "__placeholder__":
            lines.append(f"- [[{page}]]")
    lines.extend(["", "## Source trace"])
    for item in _string_list(synthesis.get("source_trace")):
        lines.append(f"- `{item}`")
    return "\n".join(lines).rstrip() + "\n"


def render_refresh_synthesis_page(refresh: dict) -> str:
    synthesis = refresh["synthesis"]
    concept_stem = ""
    for page in _string_list(synthesis.get("related_pages")):
        if page.startswith("concept--"):
            concept_stem = page
            break
    return render_synthesis_page(
        {
            "synthesis": synthesis,
            "concept": {"stem": concept_stem or "__placeholder__"},
        }
    )


def render_concept_page(family: dict) -> str:
    synthesis = family["synthesis"]
    concept = family["concept"]
    stem = concept["stem"]
    related_pages = _dedupe(
        [
            "index",
            synthesis["stem"],
            *_string_list(concept.get("related_pages")),
            *_string_list(concept.get("focus_source_stems")),
            *_string_list(concept.get("bridge_source_stems")),
        ]
    )

    lines = [
        "---",
        f"title: {_quote(concept['title'])}",
        'page_type: "concept"',
        'corpus: "wiki"',
        "canonical: true",
        f"created: {_quote(concept['created'])}",
        "aliases:",
        f"  - {_quote(stem)}",
        "tags:",
        '  - "corpus/wiki"',
        '  - "type/concept"',
        "---",
        "",
        f"# {stem}",
        "",
        "## Summary",
        concept["summary"].strip(),
        "",
        "## Why it matters here",
        concept["why_it_matters_here"].strip(),
        "",
        "## Main body",
    ]
    for block in concept.get("main_body_blocks", []):
        lines.extend(
            [
                f"### {block['heading'].strip()}",
                block["body"].strip(),
                "",
            ]
        )
    lines.append("## Scope boundaries")
    for paragraph in _string_list(concept.get("scope_boundaries")):
        lines.extend([paragraph, ""])
    lines.append("## Examples and non-examples")
    for paragraph in _string_list(concept.get("examples_and_non_examples")):
        lines.extend([paragraph, ""])
    lines.append("## How to reuse this concept")
    for paragraph in _string_list(concept.get("how_to_reuse_this_concept")):
        lines.extend([paragraph, ""])
    lines.extend(["## Related pages"])
    for page in related_pages:
        lines.append(f"- [[{page}]]")
    lines.extend(["", "## Open questions"])
    for question in _string_list(concept.get("open_questions")):
        lines.append(f"- {question}")
    lines.extend(["", "## Source trace"])
    for item in _string_list(concept.get("source_trace")):
        lines.append(f"- `{item}`")
    return "\n".join(lines).rstrip() + "\n"
