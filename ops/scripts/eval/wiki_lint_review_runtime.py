from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.policy_runtime import report_path

from .wiki_page_runtime import load_text, section_body
from .wiki_stage2_runtime import (
    broad_synthesis_boundary_missing_sections,
    broad_synthesis_watch_advisory,
    broad_wiki_synthesis_metrics,
    content_quality_scaffold_missing_sections,
    inbound_page_linkers,
    research_anchor_missing_sections,
)

SYNTHESIS_ANALYSIS_TEMPLATE_MARKERS = (
    "이 묶음이 새로 더하는 것",
    "source 신호",
    "라우팅 기준",
    "이 route를 다시 쓰는 법",
)
SYNTHESIS_FOLLOW_UP_SPLIT_MARKERS = (
    "### 2026-04-21 후속 근거",
    "follow-up는",
    "기록된 후속 intake 판단을 이미 반영했다",
)
CONCEPT_CONTINUITY_MARKERS = (
    "보강",
    "확장",
    "연결",
    "함께",
    "겹치",
    "묶",
    "더 분명",
    "더 선명",
    "보여 줬",
)
CONCEPT_SPLIT_CONTINUITY_MARKERS = (
    "기존 corpus와 이번 intake",
    "older/newer",
    "old/new",
)


def review_candidates_for(
    vault: Path,
    path: Path,
    text: str,
    refactor_triggers: dict,
    system_refactor_policy: dict,
    registry_review_exempt: set[str],
) -> list[dict]:
    candidates = []
    relative_path = path.relative_to(vault).as_posix()
    exempt_paths = set(system_refactor_policy.get("exempt_from_generic_review_candidates", []))
    exempt_paths.update(registry_review_exempt)

    if relative_path == "system/system-index.md":
        page_line_count = len(text.splitlines())
        if page_line_count > system_refactor_policy["index_max_lines_before_review"]:
            candidates.append(
                {
                    "type": "index_lines_over_threshold",
                    "page": path.as_posix(),
                    "value": page_line_count,
                    "threshold": system_refactor_policy["index_max_lines_before_review"],
                    "suggested_action": "review_index_compaction_or_catalog_split",
                }
            )

    if relative_path in exempt_paths:
        return candidates

    page_line_count = len(text.splitlines())
    if page_line_count > refactor_triggers["max_page_lines_before_review"]:
        candidates.append(
            {
                "type": "page_lines_over_threshold",
                "page": path.as_posix(),
                "value": page_line_count,
                "threshold": refactor_triggers["max_page_lines_before_review"],
                "suggested_action": "review_for_split_or_restructure",
            }
        )

    heading_count = sum(1 for line in text.splitlines() if line.startswith("## "))
    if heading_count > refactor_triggers["max_heading_count_before_review"]:
        candidates.append(
            {
                "type": "heading_count_over_threshold",
                "page": path.as_posix(),
                "value": heading_count,
                "threshold": refactor_triggers["max_heading_count_before_review"],
                "suggested_action": "review_for_section_compaction_or_split",
            }
        )

    return candidates


def wiki_synthesis_multi_question_candidates(
    vault: Path,
    pages: dict[str, Path],
    evidence_links: dict[str, set[str]],
    content_promotion_review: dict,
    refactor_triggers: dict,
) -> list[dict]:
    if not refactor_triggers.get("require_split_if_multi_question_synthesis", False):
        return []

    candidates: list[dict] = []
    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/synthesis--"):
            continue

        text = load_text(path)
        source_links = sorted(
            link for link in evidence_links.get(stem, set()) if link.startswith("source--")
        )
        metrics = broad_wiki_synthesis_metrics(text, source_links, content_promotion_review)

        if not metrics["applies"]:
            continue

        missing_sections = broad_synthesis_boundary_missing_sections(text)
        if missing_sections:
            candidate_type = "wiki_synthesis_multi_question_candidate"
            reason = (
                "wiki synthesis aggregates many source pages across many analysis subsections "
                "and lacks explicit boundary sections, so it may need a scope split or subsynthesis"
            )
            suggested_action = "review_for_scope_split_or_subsynthesis_extraction"
        else:
            candidate_type = "wiki_synthesis_multi_question_watch_candidate"
            reason = (
                "wiki synthesis is broad enough to watch for future scope creep, but it already "
                "declares exclusion, tension, and future-ingest boundaries"
            )
            suggested_action = "watch_scope_boundary_and_future_ingest_routes"

        candidate = {
            "type": candidate_type,
            "page": path.as_posix(),
            "value": metrics["value"],
            "threshold": metrics["threshold"],
            "missing_boundary_sections": missing_sections,
            "supporting_pages": [
                report_path(vault, pages[source_stem])
                for source_stem in source_links
                if source_stem in pages
            ],
            "reason": reason,
            "suggested_action": suggested_action,
        }
        if candidate_type == "wiki_synthesis_multi_question_watch_candidate":
            candidate["advisory"] = broad_synthesis_watch_advisory(text)
        candidates.append(candidate)

    return candidates


def synthesis_analysis_template_candidates(
    vault: Path,
    pages: dict[str, Path],
    refactor_triggers: dict,
) -> list[dict]:
    candidates: list[dict] = []
    max_candidates = max(1, int(refactor_triggers.get("max_candidates_per_family", 1)))

    for _stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/synthesis--"):
            continue

        analysis = section_body(load_text(path), "Analysis") or ""
        template_markers = [
            marker for marker in SYNTHESIS_ANALYSIS_TEMPLATE_MARKERS if marker in analysis
        ]
        if not template_markers:
            continue

        candidates.append(
            {
                "type": "synthesis_analysis_template_drift_candidate",
                "page": path.as_posix(),
                "value": len(template_markers),
                "threshold": 0,
                "template_markers": template_markers,
                "reason": (
                    "synthesis Analysis section still reads like a promotion memo or routing note "
                    "instead of cross-source analysis"
                ),
                "suggested_action": "rewrite_analysis_as_cross_source_synthesis",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["page"]))
    return candidates[:max_candidates]


def synthesis_follow_up_split_candidates(
    vault: Path,
    pages: dict[str, Path],
    refactor_triggers: dict,
) -> list[dict]:
    candidates: list[dict] = []
    max_candidates = max(1, int(refactor_triggers.get("max_candidates_per_family", 1)))

    for _stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/synthesis--"):
            continue

        text = load_text(path)
        evidence = section_body(text, "Evidence considered") or ""
        analysis = section_body(text, "Analysis") or ""
        markers = [
            marker
            for marker in SYNTHESIS_FOLLOW_UP_SPLIT_MARKERS
            if marker in evidence or marker in analysis or marker in text
        ]
        if not markers:
            continue

        candidates.append(
            {
                "type": "synthesis_follow_up_split_candidate",
                "page": path.as_posix(),
                "value": len(markers),
                "threshold": 0,
                "markers": markers,
                "reason": (
                    "synthesis still presents absorbed follow-up evidence as a dated split block "
                    "instead of merging it into the main evidence and analysis flow"
                ),
                "suggested_action": "rewrite_refresh_as_integrated_synthesis_update",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["page"]))
    return candidates[:max_candidates]


def concept_carryover_continuity_candidates(
    vault: Path,
    pages: dict[str, Path],
    related_links: dict[str, set[str]],
    refactor_triggers: dict,
) -> list[dict]:
    candidates: list[dict] = []
    max_candidates = max(1, int(refactor_triggers.get("max_candidates_per_family", 1)))

    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/concept--"):
            continue

        source_links = sorted(link for link in related_links.get(stem, set()) if link.startswith("source--"))
        if not source_links:
            continue
        has_recent_intake = any("-2026-04-21" in source_stem for source_stem in source_links)
        has_older_context = any("-2026-04-21" not in source_stem for source_stem in source_links)
        if not (has_recent_intake and has_older_context):
            continue

        text = load_text(path)
        continuity_surface = "\n".join(
            [
                section_body(text, "Summary") or "",
                section_body(text, "Main body") or "",
                section_body(text, "How to reuse this concept") or "",
            ]
        )
        split_markers = [
            marker for marker in CONCEPT_SPLIT_CONTINUITY_MARKERS if marker in continuity_surface
        ]
        if split_markers:
            candidates.append(
                {
                    "type": "concept_carryover_split_candidate",
                    "page": path.as_posix(),
                    "value": len(split_markers),
                    "threshold": 0,
                    "markers": split_markers,
                    "supporting_pages": [
                        report_path(vault, pages[source_stem])
                        for source_stem in source_links
                        if source_stem in pages
                    ],
                    "reason": (
                        "concept still presents bridge context as a separate temporal continuity "
                        "block instead of integrating it into the normal concept body"
                    ),
                    "suggested_action": "merge_bridge_context_into_concept_main_body",
                }
            )
            continue
        if any(marker in continuity_surface for marker in CONCEPT_CONTINUITY_MARKERS):
            continue

        candidates.append(
            {
                "type": "concept_carryover_continuity_missing_candidate",
                "page": path.as_posix(),
                "value": len(source_links),
                "threshold": 0,
                "supporting_pages": [
                    report_path(vault, pages[source_stem])
                    for source_stem in source_links
                    if source_stem in pages
                ],
                "reason": (
                    "concept links both older bridge sources and newer intake sources, but its prose "
                    "still does not integrate the bridge relationship between them"
                ),
                "suggested_action": "merge_bridge_context_into_concept_main_body",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["page"]))
    return candidates[:max_candidates]


def concept_taxonomy_advisory_candidates(
    vault: Path,
    pages: dict[str, Path],
    frontmatters: dict[str, dict | None],
    frontmatter_contract: dict,
) -> list[dict]:
    advisory = (
        frontmatter_contract.get("metadata_review", {})
        .get("concept_taxonomy_advisory", {})
    )
    if not advisory.get("enabled", False):
        return []

    applies_to = set(advisory.get("applies_to_page_types", ["concept"]))
    recommended_fields = list(advisory.get("recommended_fields", []))
    allowed_roles = list(advisory.get("allowed_concept_roles", []))
    pages_with_missing_fields: list[dict] = []
    pages_with_invalid_roles: list[dict] = []

    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/concept--"):
            continue

        frontmatter = frontmatters.get(stem) or {}
        if frontmatter.get("page_type") not in applies_to:
            continue

        missing_fields = [field for field in recommended_fields if field not in frontmatter]
        if missing_fields:
            pages_with_missing_fields.append(
                {
                    "page": relative_path,
                    "missing_fields": missing_fields,
                }
            )

        concept_role = frontmatter.get("concept_role")
        if concept_role is not None and allowed_roles and concept_role not in allowed_roles:
            pages_with_invalid_roles.append(
                {
                    "page": relative_path,
                    "field": "concept_role",
                    "actual": concept_role,
                    "expected_one_of": allowed_roles,
                }
            )

    if not pages_with_missing_fields and not pages_with_invalid_roles:
        return []

    return [
        {
            "type": "concept_taxonomy_frontmatter_advisory",
            "page": "wiki/concept--*.md",
            "value": {
                "missing_field_page_count": len(pages_with_missing_fields),
                "invalid_role_page_count": len(pages_with_invalid_roles),
            },
            "threshold": {
                "missing_field_page_count": 0,
                "invalid_role_page_count": 0,
            },
            "recommended_fields": recommended_fields,
            "allowed_concept_roles": allowed_roles,
            "pages_with_missing_fields": pages_with_missing_fields,
            "pages_with_invalid_roles": pages_with_invalid_roles,
            "reason": (
                "concept taxonomy fields are optional during rollout, but missing or invalid "
                "taxonomy metadata weakens routing, Obsidian filtering, and source intake decisions"
            ),
            "suggested_action": "backfill_concept_taxonomy_frontmatter_after_taxonomy_review",
        }
    ]


def content_quality_advisory_candidates(
    vault: Path,
    pages: dict[str, Path],
    frontmatters: dict[str, dict | None],
    frontmatter_contract: dict,
) -> list[dict]:
    advisory = (
        frontmatter_contract.get("metadata_review", {})
        .get("content_quality_advisory", {})
    )
    if not advisory.get("enabled", False):
        return []

    applies_to = set(advisory.get("applies_to_page_types", ["concept", "synthesis"]))
    recommended_headings = list(advisory.get("recommended_headings", []))
    pages_with_missing_headings: list[dict] = []

    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not (
            relative_path.startswith("wiki/concept--")
            or relative_path.startswith("wiki/synthesis--")
        ):
            continue

        frontmatter = frontmatters.get(stem) or {}
        if frontmatter.get("page_type") not in applies_to:
            continue

        created = str(frontmatter.get("created", "")).strip()

        text = load_text(path)
        missing_headings = content_quality_scaffold_missing_sections(text, recommended_headings)
        if missing_headings:
            pages_with_missing_headings.append(
                {
                    "page": relative_path,
                    "created": created,
                    "missing_headings": missing_headings,
                }
            )

    if not pages_with_missing_headings:
        return []

    return [
        {
            "type": "content_quality_scaffold_advisory",
            "page": "wiki/{concept,synthesis}--*.md",
            "value": {
                "page_count": len(pages_with_missing_headings),
            },
            "threshold": {
                "page_count": 0,
            },
            "recommended_headings": recommended_headings,
            "pages_with_missing_headings": pages_with_missing_headings,
            "reason": (
                "concept/synthesis pages should carry wiki-substance scaffolding "
                "before routing tables or source aggregation dominate the page"
            ),
            "suggested_action": "rewrite_concept_or_synthesis_with_substance_scaffold",
        }
    ]


def source_route_advisory_candidates(
    vault: Path,
    pages: dict[str, Path],
    frontmatters: dict[str, dict | None],
    frontmatter_contract: dict,
) -> list[dict]:
    advisory = (
        frontmatter_contract.get("metadata_review", {})
        .get("source_route_advisory", {})
    )
    if not advisory.get("enabled", False):
        return []

    applies_to = set(advisory.get("applies_to_page_types", ["source"]))
    recommended_fields = list(advisory.get("recommended_fields", []))
    allowed_authority_classes = list(advisory.get("allowed_authority_classes", []))
    allowed_route_decisions = list(advisory.get("allowed_route_decisions", []))
    pages_with_missing_fields: list[dict] = []
    pages_with_invalid_values: list[dict] = []

    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/source--"):
            continue

        frontmatter = frontmatters.get(stem) or {}
        if frontmatter.get("page_type") not in applies_to:
            continue

        missing_fields = [field for field in recommended_fields if field not in frontmatter]
        if missing_fields:
            pages_with_missing_fields.append(
                {
                    "page": relative_path,
                    "missing_fields": missing_fields,
                }
            )

        authority_class = frontmatter.get("authority_class")
        if (
            authority_class is not None
            and allowed_authority_classes
            and authority_class not in allowed_authority_classes
        ):
            pages_with_invalid_values.append(
                {
                    "page": relative_path,
                    "field": "authority_class",
                    "actual": authority_class,
                    "expected_one_of": allowed_authority_classes,
                }
            )

        route_decision = frontmatter.get("route_decision")
        if (
            route_decision is not None
            and allowed_route_decisions
            and route_decision not in allowed_route_decisions
        ):
            pages_with_invalid_values.append(
                {
                    "page": relative_path,
                    "field": "route_decision",
                    "actual": route_decision,
                    "expected_one_of": allowed_route_decisions,
                }
            )

    if not pages_with_missing_fields and not pages_with_invalid_values:
        return []

    return [
        {
            "type": "source_route_frontmatter_advisory",
            "page": "wiki/source--*.md",
            "value": {
                "missing_field_page_count": len(pages_with_missing_fields),
                "invalid_value_count": len(pages_with_invalid_values),
            },
            "threshold": {
                "missing_field_page_count": 0,
                "invalid_value_count": 0,
            },
            "recommended_fields": recommended_fields,
            "allowed_authority_classes": allowed_authority_classes,
            "allowed_route_decisions": allowed_route_decisions,
            "pages_with_missing_fields": pages_with_missing_fields,
            "pages_with_invalid_values": pages_with_invalid_values,
            "reason": (
                "source route fields are optional during rollout, but missing or invalid "
                "metadata weakens raw intake triage, concept absorption, and source-only "
                "seed promotion decisions"
            ),
            "suggested_action": "backfill_source_route_frontmatter_during_source_template_rollout",
        }
    ]


@dataclass(frozen=True)
class _ContentPromotionContext:
    vault: Path
    pages: dict[str, Path]
    related_links: dict[str, set[str]]
    evidence_links: dict[str, set[str]]
    content_promotion_review: dict
    max_candidates: int


def _stems_for_relative_prefix(relative_paths: dict[str, str], prefix: str) -> set[str]:
    return {
        stem
        for stem, relative_path in relative_paths.items()
        if relative_path.startswith(prefix)
    }


def _wiki_domain_source_index(
    registry_entries: list[dict],
    wiki_source_stems: set[str],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    wiki_domain_to_sources: dict[str, set[str]] = defaultdict(set)
    domain_by_source_stem: dict[str, str] = {}
    for entry in registry_entries:
        if entry.get("corpus") != "wiki" or entry.get("status") != "ingested":
            continue
        domain = entry.get("domain")
        target_page = entry.get("target_page")
        if not domain or not target_page or target_page not in wiki_source_stems:
            continue
        domain_by_source_stem[target_page] = domain
        wiki_domain_to_sources[domain].add(target_page)
    return wiki_domain_to_sources, domain_by_source_stem


def _wiki_missing_concept_candidates(
    context: _ContentPromotionContext,
    wiki_synthesis_stems: set[str],
    wiki_source_stems: set[str],
    wiki_concept_stems: set[str],
    domain_by_source_stem: dict[str, str],
) -> list[dict]:
    candidates = []
    min_source_links = context.content_promotion_review["wiki_missing_concept_min_source_links"]
    for stem in sorted(wiki_synthesis_stems):
        source_links = sorted(context.evidence_links.get(stem, set()) & wiki_source_stems)
        concept_links = sorted(context.related_links.get(stem, set()) & wiki_concept_stems)
        if len(source_links) < min_source_links or concept_links:
            continue
        domains = sorted(
            {
                domain_by_source_stem[source_stem]
                for source_stem in source_links
                if source_stem in domain_by_source_stem
            }
        )
        candidates.append(
            {
                "type": "wiki_missing_concept_candidate",
                "page": context.pages[stem].as_posix(),
                "value": len(source_links),
                "threshold": min_source_links,
                "supporting_pages": [
                    report_path(context.vault, context.pages[source_stem])
                    for source_stem in source_links
                ],
                "domains": domains,
                "reason": "wiki synthesis aggregates multiple source pages without linking a canonical concept page",
                "suggested_action": "review_for_canonical_concept_creation_or_linkage",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["page"]))
    return candidates[: context.max_candidates]


def _wiki_missing_synthesis_candidates(
    context: _ContentPromotionContext,
    wiki_domain_to_sources: dict[str, set[str]],
    wiki_synthesis_stems: set[str],
) -> list[dict]:
    candidates = []
    review = context.content_promotion_review
    min_sources = review["wiki_missing_synthesis_min_sources"]
    overlap_threshold = review["synthesis_source_overlap_for_coverage"]
    for domain, source_stems in sorted(wiki_domain_to_sources.items()):
        if len(source_stems) < min_sources:
            continue
        covering_syntheses = [
            synthesis_stem
            for synthesis_stem in wiki_synthesis_stems
            if len(context.evidence_links.get(synthesis_stem, set()) & source_stems)
            >= overlap_threshold
        ]
        if covering_syntheses:
            continue
        candidates.append(
            {
                "type": "wiki_missing_synthesis_candidate",
                "page": (context.vault / "wiki" / "index.md").as_posix(),
                "value": len(source_stems),
                "threshold": min_sources,
                "domain": domain,
                "supporting_pages": [
                    report_path(context.vault, context.pages[source_stem])
                    for source_stem in sorted(source_stems)
                ],
                "reason": "wiki source cluster has no synthesis page that aggregates multiple cluster members",
                "suggested_action": "review_for_cluster_synthesis_creation",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["domain"]))
    return candidates[: context.max_candidates]


def _system_missing_concept_candidates(
    context: _ContentPromotionContext,
    system_candidate_stems: set[str],
    system_source_stems: set[str],
    system_concept_stems: set[str],
) -> list[dict]:
    candidates = []
    min_source_links = context.content_promotion_review["system_missing_concept_min_source_links"]
    for stem in sorted(system_candidate_stems):
        source_links = sorted(context.evidence_links.get(stem, set()) & system_source_stems)
        concept_links = sorted(context.related_links.get(stem, set()) & system_concept_stems)
        if len(source_links) < min_source_links or concept_links:
            continue
        candidates.append(
            {
                "type": "system_missing_concept_candidate",
                "page": context.pages[stem].as_posix(),
                "value": len(source_links),
                "threshold": min_source_links,
                "supporting_pages": [
                    report_path(context.vault, context.pages[source_stem])
                    for source_stem in source_links
                ],
                "reason": "system synthesis or query aggregates multiple system sources without linking a canonical concept page",
                "suggested_action": "review_for_canonical_system_concept_creation_or_linkage",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["page"]))
    return candidates[: context.max_candidates]


def content_promotion_candidates(
    vault: Path,
    pages: dict[str, Path],
    related_links: dict[str, set[str]],
    evidence_links: dict[str, set[str]],
    registry_entries: list[dict],
    refactor_triggers: dict,
    content_promotion_review: dict,
) -> list[dict]:
    relative_paths = {stem: report_path(vault, path) for stem, path in pages.items()}
    max_candidates = max(1, int(refactor_triggers.get("max_candidates_per_family", 1)))

    wiki_source_stems = _stems_for_relative_prefix(relative_paths, "wiki/source--")
    wiki_concept_stems = _stems_for_relative_prefix(relative_paths, "wiki/concept--")
    wiki_synthesis_stems = _stems_for_relative_prefix(relative_paths, "wiki/synthesis--")
    system_source_stems = _stems_for_relative_prefix(relative_paths, "system/source--")
    system_concept_stems = _stems_for_relative_prefix(relative_paths, "system/concept--")
    system_candidate_stems = _stems_for_relative_prefix(
        relative_paths,
        "system/synthesis--",
    ) | _stems_for_relative_prefix(relative_paths, "system/query--")
    wiki_domain_to_sources, domain_by_source_stem = _wiki_domain_source_index(
        registry_entries,
        wiki_source_stems,
    )
    context = _ContentPromotionContext(
        vault=vault,
        pages=pages,
        related_links=related_links,
        evidence_links=evidence_links,
        content_promotion_review=content_promotion_review,
        max_candidates=max_candidates,
    )

    candidates: list[dict] = []
    candidates.extend(
        _wiki_missing_concept_candidates(
            context,
            wiki_synthesis_stems,
            wiki_source_stems,
            wiki_concept_stems,
            domain_by_source_stem,
        )
    )
    candidates.extend(
        _wiki_missing_synthesis_candidates(
            context,
            wiki_domain_to_sources,
            wiki_synthesis_stems,
        )
    )
    candidates.extend(
        _system_missing_concept_candidates(
            context,
            system_candidate_stems,
            system_source_stems,
            system_concept_stems,
        )
    )
    return candidates


def active_source_missing_concept_candidates(
    vault: Path,
    pages: dict[str, Path],
    related_links: dict[str, set[str]],
    frontmatters: dict[str, dict | None],
) -> list[dict]:
    candidates: list[dict] = []
    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/source--"):
            continue

        related = related_links.get(stem, set())
        synthesis_links = sorted(link for link in related if link.startswith("synthesis--"))
        if not synthesis_links:
            continue
        source_frontmatter = frontmatters.get(stem) or {}
        source_created = source_frontmatter.get("created")
        if not source_created:
            continue

        supporting_pages = []
        linked_older_synthesis = False
        for synthesis_stem in synthesis_links:
            synthesis_frontmatter = frontmatters.get(synthesis_stem) or {}
            synthesis_created = synthesis_frontmatter.get("created")
            if not synthesis_created or source_created <= synthesis_created:
                continue
            linked_older_synthesis = True
            if synthesis_stem in pages:
                supporting_pages.append(report_path(vault, pages[synthesis_stem]))
        if not linked_older_synthesis:
            continue

        concept_links = sorted(link for link in related if link.startswith("concept--"))
        if concept_links:
            continue

        candidates.append(
            {
                "type": "active_source_missing_concept_link_candidate",
                "page": path.as_posix(),
                "value": len(synthesis_links),
                "threshold": 1,
                "supporting_pages": supporting_pages,
                "reason": (
                    "newer follow-up source page routes to an older synthesis page but still "
                    "lacks a canonical concept link in Related pages"
                ),
                "suggested_action": "review_for_active_source_concept_linkage",
            }
        )

    candidates.sort(key=lambda item: (-item["value"], item["page"]))
    return candidates


def research_source_anchor_candidates(
    vault: Path,
    pages: dict[str, Path],
    page_links: dict[str, set[str]],
    frontmatters: dict[str, dict | None],
    refactor_triggers: dict,
    content_promotion_review: dict,
) -> list[dict]:
    candidates: list[dict] = []
    max_candidates = max(1, int(refactor_triggers.get("max_candidates_per_family", 1)))
    min_inbound_links = content_promotion_review["research_anchor_min_inbound_links"]
    required_sections = content_promotion_review["research_anchor_required_sections"]

    inbound_sources = inbound_page_linkers(page_links, pages)

    for stem, path in sorted(pages.items()):
        relative_path = report_path(vault, path)
        if not relative_path.startswith("wiki/source--"):
            continue
        frontmatter = frontmatters.get(stem)
        if frontmatter is None:
            continue
        if frontmatter.get("source_type") != "domain-research-paper":
            continue

        inbound_linkers = sorted(inbound_sources.get(stem, set()))
        if len(inbound_linkers) < min_inbound_links:
            continue

        text = load_text(path)
        missing_sections = research_anchor_missing_sections(text, required_sections)
        if not missing_sections:
            continue

        candidates.append(
            {
                "type": "research_source_missing_anchor_layer_candidate",
                "page": path.as_posix(),
                "value": {
                    "inbound_links": len(inbound_linkers),
                    "missing_sections": missing_sections,
                    "research_mode": frontmatter.get("research_mode"),
                },
                "threshold": {
                    "inbound_links": min_inbound_links,
                },
                "supporting_pages": [
                    report_path(vault, pages[source_stem])
                    for source_stem in inbound_linkers
                    if source_stem in pages
                ],
                "reason": "central research source is reused across the corpus but still lacks some anchor-layer sections",
                "suggested_action": "review_for_research_anchor_layer_completion",
            }
        )

    candidates.sort(
        key=lambda item: (
            -len(item["value"]["missing_sections"]),
            -item["value"]["inbound_links"],
            item["page"],
        )
    )
    return candidates[:max_candidates]
