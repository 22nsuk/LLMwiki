from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ops.scripts.frontmatter_runtime import (
    parse_frontmatter,
    validate_frontmatter,
    validate_frontmatter_metadata,
    validate_frontmatter_pending_required_fields,
)
from ops.scripts.source_trace_runtime import extract_source_trace_refs
from .wiki_lint_review_runtime import review_candidates_for
from .wiki_page_runtime import INDEXISH_PAGES, SPECIAL_PAGES, section_body, source_trace_item_count
from .wiki_quality_runtime import (
    broken_wikilinks,
    has_placeholder,
    missing_required_sections,
    open_question_budget_status,
    resolved_wikilink_targets,
    source_trace_targets_blocking_profile,
)


@dataclass(frozen=True)
class PageLintContext:
    vault: Path
    path: Path
    stem: str
    text: str
    page_lookup: dict[str, str]
    required_headings: list[str]
    lint_thresholds: dict[str, str]
    readiness_gate: dict
    frontmatter_contract: dict
    schema_versioning: dict | None
    source_trace_resolution_map: dict
    refactor_triggers: dict
    system_refactor_policy: dict
    registry_review_exempt: set[str]
    frontmatter: dict | None = None
    frontmatter_error: str | None = None
    page_links: set[str] | None = None
    related_links: set[str] | None = None
    evidence_links: set[str] | None = None
    snapshot_loaded: bool = False
    release_archive_profile: bool = False


@dataclass(frozen=True)
class PageLintResult:
    frontmatter: dict | None
    issues: list[tuple[dict, str]]
    page_links: set[str]
    related_links: set[str]
    evidence_links: set[str]
    review_candidates: list[dict]


def _page_issue(path: Path, issue_type: str, detail=None) -> dict:
    issue = {
        "type": issue_type,
        "page": path.as_posix(),
    }
    if detail is not None:
        issue["detail"] = detail
    return issue


def _frontmatter_issues(
    ctx: PageLintContext,
    frontmatter: dict | None,
) -> list[tuple[dict, str]]:
    issues: list[tuple[dict, str]] = []
    if frontmatter is None:
        issues.append(
            (
                _page_issue(ctx.path, "missing_frontmatter"),
                ctx.lint_thresholds["missing_frontmatter"],
            )
        )
        return issues

    for frontmatter_issue in validate_frontmatter(
        ctx.vault,
        ctx.path,
        ctx.stem,
        frontmatter,
        ctx.frontmatter_contract,
    ):
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    frontmatter_issue["type"],
                    frontmatter_issue["detail"],
                ),
                ctx.lint_thresholds[frontmatter_issue["type"]],
            )
        )
    for metadata_issue in validate_frontmatter_metadata(
        frontmatter,
        ctx.stem,
        ctx.frontmatter_contract,
    ):
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    metadata_issue["type"],
                    metadata_issue["detail"],
                ),
                ctx.lint_thresholds[metadata_issue["type"]],
            )
        )
    for pending_issue in validate_frontmatter_pending_required_fields(
        frontmatter,
        ctx.schema_versioning,
    ):
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    pending_issue["type"],
                    pending_issue["detail"],
                ),
                ctx.lint_thresholds[pending_issue["type"]],
            )
        )
    return issues


def _required_section_and_placeholder_issues(ctx: PageLintContext) -> list[tuple[dict, str]]:
    issues: list[tuple[dict, str]] = []
    for heading in missing_required_sections(ctx.text, ctx.required_headings):
        issues.append(
            (
                _page_issue(ctx.path, "missing_required_section", heading),
                ctx.lint_thresholds["missing_required_section"],
            )
        )
    if ctx.stem not in INDEXISH_PAGES and has_placeholder(ctx.text):
        issues.append(
            (
                _page_issue(ctx.path, "todo_placeholder_outside_index"),
                ctx.lint_thresholds["todo_placeholder_outside_index"],
            )
        )
    return issues


def _source_trace_issues(ctx: PageLintContext) -> list[tuple[dict, str]]:
    issues: list[tuple[dict, str]] = []
    source_trace = section_body(ctx.text, "Source trace")
    if source_trace_item_count(source_trace) < ctx.readiness_gate["min_source_trace_items"]:
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    "missing_source_trace",
                    f"expected at least {ctx.readiness_gate['min_source_trace_items']} trace item(s)",
                ),
                ctx.lint_thresholds["missing_source_trace"],
            )
        )
    if not source_trace:
        return issues

    wildcard_refs = sorted(
        {
            ref
            for ref in extract_source_trace_refs(source_trace)
            if any(ch in ref for ch in "*?[")
        }
    )
    for ref in wildcard_refs:
        issues.append(
            (
                _page_issue(ctx.path, "wildcard_source_trace", ref),
                ctx.lint_thresholds["wildcard_source_trace"],
            )
        )
    missing_targets = source_trace_targets_blocking_profile(
        ctx.vault,
        source_trace,
        ctx.source_trace_resolution_map,
        release_archive_profile=ctx.release_archive_profile,
    )
    if missing_targets:
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    "source_trace_target_missing",
                    {
                        "profile": "release_archive" if ctx.release_archive_profile else "strict",
                        "missing_targets": missing_targets,
                    },
                ),
                ctx.lint_thresholds["source_trace_target_missing"],
            )
        )
    return issues


def _open_question_issues(ctx: PageLintContext) -> list[tuple[dict, str]]:
    issues: list[tuple[dict, str]] = []
    open_question_budget = open_question_budget_status(
        section_body(ctx.text, "Open questions"),
        ctx.readiness_gate,
    )
    if open_question_budget["high_overflow"]:
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    "high_severity_open_question_overflow",
                    (
                        f"high={open_question_budget['counts']['high']} exceeds "
                        f"max={open_question_budget['high_max']}"
                    ),
                ),
                "fail",
            )
        )
    if open_question_budget["medium_overflow"]:
        issues.append(
            (
                _page_issue(
                    ctx.path,
                    "medium_severity_open_question_overflow",
                    (
                        f"medium={open_question_budget['counts']['medium']} exceeds "
                        f"max={open_question_budget['medium_max']}"
                    ),
                ),
                open_question_budget["medium_overflow_severity"],
            )
        )
    return issues


def _broken_wikilink_issues(ctx: PageLintContext) -> list[tuple[dict, str]]:
    issues: list[tuple[dict, str]] = []
    for target in broken_wikilinks(ctx.text, ctx.page_lookup, SPECIAL_PAGES):
        issues.append(
            (
                _page_issue(ctx.path, "broken_wikilink", target),
                ctx.lint_thresholds["broken_wikilink"],
            )
        )
    return issues


def lint_page(ctx: PageLintContext) -> PageLintResult:
    issues: list[tuple[dict, str]] = []
    if ctx.snapshot_loaded:
        frontmatter = ctx.frontmatter
        if ctx.frontmatter_error is not None:
            issues.append(
                (
                    _page_issue(ctx.path, "invalid_frontmatter", ctx.frontmatter_error),
                    ctx.lint_thresholds["invalid_frontmatter"],
                )
            )
            frontmatter = None
        page_links = ctx.page_links or set()
        related_links = ctx.related_links or set()
        evidence_links = ctx.evidence_links or set()
    else:
        try:
            frontmatter = parse_frontmatter(ctx.text)
        except ValueError as exc:
            issues.append(
                (
                    _page_issue(ctx.path, "invalid_frontmatter", str(exc)),
                    ctx.lint_thresholds["invalid_frontmatter"],
                )
            )
            frontmatter = None
        page_links = resolved_wikilink_targets(ctx.text, ctx.page_lookup)
        related_links = resolved_wikilink_targets(section_body(ctx.text, "Related pages"), ctx.page_lookup)
        evidence_links = resolved_wikilink_targets(section_body(ctx.text, "Evidence considered"), ctx.page_lookup)

    issues.extend(_frontmatter_issues(ctx, frontmatter))
    review_candidates = review_candidates_for(
        ctx.vault,
        ctx.path,
        ctx.text,
        ctx.refactor_triggers,
        ctx.system_refactor_policy,
        ctx.registry_review_exempt,
    )

    issues.extend(_required_section_and_placeholder_issues(ctx))
    issues.extend(_source_trace_issues(ctx))
    issues.extend(_open_question_issues(ctx))
    issues.extend(_broken_wikilink_issues(ctx))

    return PageLintResult(
        frontmatter=frontmatter,
        issues=issues,
        page_links=page_links,
        related_links=related_links,
        evidence_links=evidence_links,
        review_candidates=review_candidates,
    )


def orphan_issues(
    link_inbound: dict[str, int],
    pages: dict[str, Path],
    severity: str,
) -> list[tuple[dict, str]]:
    issues: list[tuple[dict, str]] = []
    for target, count in link_inbound.items():
        if target in INDEXISH_PAGES or count != 0:
            continue
        issues.append(
            (
                _page_issue(pages[target], "orphan_page"),
                severity,
            )
        )
    return issues
