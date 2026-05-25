from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.policy_runtime import report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import WIKI_EVAL_COVERAGE_SCHEMA_PATH
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from .wiki_snapshot_runtime import WikiRuntimeSnapshot, build_wiki_runtime_snapshot
from .wiki_stage2_runtime import (
    broad_wiki_synthesis_metrics,
    inbound_page_linkers,
    stable_wiki_inbound_linkers,
)

WIKI_EVAL_COVERAGE_SCHEMA = WIKI_EVAL_COVERAGE_SCHEMA_PATH
PRODUCER = "ops.scripts.wiki_eval_coverage_runtime"
SOURCE_COMMAND = "python -m ops.scripts.wiki_eval_coverage"


@dataclass(frozen=True)
class CoveragePageContext:
    stem: str
    path: Path
    relative_path: str
    text: str
    frontmatter: dict | None


CoveragePredicate = Callable[[dict, CoveragePageContext, dict], bool]
CoverageEnabled = Callable[[dict], bool]


@dataclass(frozen=True)
class CoverageRuleSpec:
    rule_id: str
    stage: str
    enabled: CoverageEnabled
    covers_page: CoveragePredicate


def _always_enabled(_: dict) -> bool:
    return True


def _rule_source_page_substance(
    policy: dict,
    page: CoveragePageContext,
    context: dict,
) -> bool:
    del policy, context
    return page.stem.startswith("source--")


def _rule_decisionability(
    policy: dict,
    page: CoveragePageContext,
    context: dict,
) -> bool:
    del policy, context
    return page.stem.startswith("synthesis--") or page.stem.startswith("query--")


def _source_count_consistency_enabled(policy: dict) -> bool:
    return bool(policy["stage2_eval"]["source_count_consistency_enabled"])


def _rule_declared_source_count_matches_evidence(
    policy: dict,
    page: CoveragePageContext,
    context: dict,
) -> bool:
    del context
    return _source_count_consistency_enabled(policy) and page.stem.startswith("synthesis--")


def _central_research_anchor_enabled(policy: dict) -> bool:
    return bool(policy["stage2_eval"]["central_research_anchor_enabled"])


def _rule_central_research_source_has_anchor_layer(
    policy: dict,
    page: CoveragePageContext,
    context: dict,
) -> bool:
    if not _central_research_anchor_enabled(policy):
        return False
    if not page.relative_path.startswith("wiki/source--"):
        return False
    if not isinstance(page.frontmatter, dict) or page.frontmatter.get("source_type") != "domain-research-paper":
        return False
    inbound_sources = context["inbound_sources"]
    inbound_linkers = sorted(inbound_sources.get(page.stem, set()))
    threshold = policy["content_promotion_review"]["research_anchor_min_inbound_links"]
    return len(inbound_linkers) >= threshold


def _seed_source_absorption_enabled(policy: dict) -> bool:
    return bool(policy["stage2_eval"]["seed_source_absorption_enabled"])


def _rule_seed_source_has_absorption_hint(
    policy: dict,
    page: CoveragePageContext,
    context: dict,
) -> bool:
    if not _seed_source_absorption_enabled(policy):
        return False
    if not page.relative_path.startswith("wiki/source--"):
        return False
    if not isinstance(page.frontmatter, dict):
        return False
    if page.frontmatter.get("source_type") == "domain-research-paper":
        return False
    inbound_sources = context["inbound_sources"]
    inbound_linkers = sorted(inbound_sources.get(page.stem, set()))
    return not stable_wiki_inbound_linkers(inbound_linkers)


def _broad_synthesis_boundary_enabled(policy: dict) -> bool:
    return bool(policy["stage2_eval"]["broad_synthesis_boundary_enabled"])


def _rule_broad_synthesis_has_boundary_sections(
    policy: dict,
    page: CoveragePageContext,
    context: dict,
) -> bool:
    if not _broad_synthesis_boundary_enabled(policy):
        return False
    if not page.relative_path.startswith("wiki/synthesis--"):
        return False
    content_promotion_review = policy["content_promotion_review"]
    evidence_source_stems = sorted(
        target
        for target in context["evidence_links"].get(page.stem, set())
        if target.startswith("source--")
    )
    return broad_wiki_synthesis_metrics(
        page.text,
        evidence_source_stems,
        content_promotion_review,
    )["applies"]


COVERAGE_RULES: dict[str, CoverageRuleSpec] = {
    "source_page_substance": CoverageRuleSpec(
        rule_id="source_page_substance",
        stage="stage1",
        enabled=_always_enabled,
        covers_page=_rule_source_page_substance,
    ),
    "decisionability": CoverageRuleSpec(
        rule_id="decisionability",
        stage="stage1",
        enabled=_always_enabled,
        covers_page=_rule_decisionability,
    ),
    "declared_source_count_matches_evidence": CoverageRuleSpec(
        rule_id="declared_source_count_matches_evidence",
        stage="stage2",
        enabled=_source_count_consistency_enabled,
        covers_page=_rule_declared_source_count_matches_evidence,
    ),
    "central_research_source_has_anchor_layer": CoverageRuleSpec(
        rule_id="central_research_source_has_anchor_layer",
        stage="stage2",
        enabled=_central_research_anchor_enabled,
        covers_page=_rule_central_research_source_has_anchor_layer,
    ),
    "seed_source_has_absorption_hint": CoverageRuleSpec(
        rule_id="seed_source_has_absorption_hint",
        stage="stage2",
        enabled=_seed_source_absorption_enabled,
        covers_page=_rule_seed_source_has_absorption_hint,
    ),
    "broad_synthesis_has_boundary_sections": CoverageRuleSpec(
        rule_id="broad_synthesis_has_boundary_sections",
        stage="stage2",
        enabled=_broad_synthesis_boundary_enabled,
        covers_page=_rule_broad_synthesis_has_boundary_sections,
    ),
}


def _validate_coverage_contract(policy: dict) -> None:
    for cohort in policy["eval_coverage_review"]["cohorts"]:
        stage = cohort["stage"]
        for rule_id in cohort["coverage_rules"]:
            spec = COVERAGE_RULES[rule_id]
            if spec.stage != stage:
                raise ValueError(
                    "eval coverage contract stage mismatch: "
                    f"cohort={cohort['cohort_id']} stage={stage} rule={rule_id} rule_stage={spec.stage}"
                )


def _page_contexts(vault: Path, snapshot: WikiRuntimeSnapshot) -> list[CoveragePageContext]:
    return [
        CoveragePageContext(
            stem=stem,
            path=path,
            relative_path=report_path(vault, path),
            text=snapshot.texts[stem],
            frontmatter=snapshot.frontmatters.get(stem),
        )
        for stem, path in sorted(snapshot.pages.items())
    ]


def _matches_frontmatter(frontmatter: dict | None, expected: dict[str, str] | None, negated: bool) -> bool:
    if not expected:
        return True
    if not isinstance(frontmatter, dict):
        return False
    for key, value in expected.items():
        actual = frontmatter.get(key)
        if negated:
            if str(actual) == value:
                return False
        elif str(actual) != value:
            return False
    return True


def _matching_pages(cohort: dict, pages: list[CoveragePageContext]) -> list[CoveragePageContext]:
    path_prefixes = tuple(cohort["path_prefixes"])
    frontmatter_equals = cohort.get("frontmatter_equals")
    frontmatter_not_equals = cohort.get("frontmatter_not_equals")
    matched: list[CoveragePageContext] = []
    for page in pages:
        if not any(page.relative_path.startswith(prefix) for prefix in path_prefixes):
            continue
        if not _matches_frontmatter(page.frontmatter, frontmatter_equals, negated=False):
            continue
        if not _matches_frontmatter(page.frontmatter, frontmatter_not_equals, negated=True):
            continue
        matched.append(page)
    return matched


def _coverage_context(policy: dict, snapshot: WikiRuntimeSnapshot) -> dict:
    inbound_sources = inbound_page_linkers(snapshot.page_links, snapshot.pages)
    return {
        "inbound_sources": inbound_sources,
        "page_lookup": snapshot.page_lookup,
        "evidence_links": snapshot.evidence_links,
        "content_promotion_review": policy["content_promotion_review"],
    }


def _base_report(
    vault: Path,
    *,
    policy: dict,
    policy_path: Path,
    runtime_snapshot: WikiRuntimeSnapshot,
    context: RuntimeContext,
) -> dict:
    generated_at = context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="wiki_eval_coverage_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=policy_path,
            schema_path=WIKI_EVAL_COVERAGE_SCHEMA,
            source_paths=["ops/scripts/wiki_eval_coverage_runtime.py"],
            path_group_inputs={
                "pages": sorted(report_path(vault, path) for path in runtime_snapshot.pages.values()),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, policy_path),
            "version": policy.get("version"),
        },
    }


def _cohort_report(
    vault: Path,
    policy: dict,
    cohort: dict,
    pages: list[CoveragePageContext],
    context: dict,
    *,
    policy_path: Path,
) -> tuple[dict, dict | None]:
    matched_pages = _matching_pages(cohort, pages)
    active_rules = [
        rule_id
        for rule_id in cohort["coverage_rules"]
        if COVERAGE_RULES[rule_id].enabled(policy)
    ]
    inactive_rules = [
        rule_id for rule_id in cohort["coverage_rules"] if rule_id not in active_rules
    ]

    covered_pages: dict[str, CoveragePageContext] = {}
    for page in matched_pages:
        for rule_id in active_rules:
            if COVERAGE_RULES[rule_id].covers_page(policy, page, context):
                covered_pages[page.relative_path] = page
                break

    gap_reasons: list[str] = []
    min_matching_pages = int(cohort["min_matching_pages"])
    require_nonzero_covered_pages = bool(cohort["require_nonzero_covered_pages"])
    if len(matched_pages) >= min_matching_pages and not active_rules:
        gap_reasons.append("no_active_rules")
    if (
        require_nonzero_covered_pages
        and len(matched_pages) >= min_matching_pages
        and not covered_pages
    ):
        gap_reasons.append("no_pages_covered")

    cohort_payload = {
        "cohort_id": cohort["cohort_id"],
        "stage": cohort["stage"],
        "coverage_rules": list(cohort["coverage_rules"]),
        "inactive_rules": inactive_rules,
        "matching_page_count": len(matched_pages),
        "covered_page_count": len(covered_pages),
        "configured_rule_count": len(cohort["coverage_rules"]),
        "active_rule_count": len(active_rules),
        "gap_reasons": gap_reasons,
        "matching_pages_sample": [page.relative_path for page in matched_pages[:5]],
        "covered_pages_sample": sorted(covered_pages)[:5],
    }

    if not gap_reasons:
        return cohort_payload, None

    candidate = {
        "type": "eval_coverage_gap_candidate",
        "page": report_path(vault, policy_path),
        "cohort_id": cohort["cohort_id"],
        "stage": cohort["stage"],
        "value": {
            "matching_page_count": len(matched_pages),
            "covered_page_count": len(covered_pages),
            "active_rule_count": len(active_rules),
        },
        "threshold": {
            "min_matching_pages": min_matching_pages,
            "require_nonzero_covered_pages": require_nonzero_covered_pages,
        },
        "coverage_rules": list(cohort["coverage_rules"]),
        "inactive_rules": inactive_rules,
        "gap_reasons": gap_reasons,
        "supporting_pages": [page.relative_path for page in matched_pages[:5]],
        "suggested_action": cohort["suggested_action"],
        "reason": (
            f"{cohort['stage']} coverage cohort `{cohort['cohort_id']}` has a structural eval coverage gap"
        ),
    }
    return cohort_payload, candidate


def build_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    snapshot: WikiRuntimeSnapshot | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    _validate_coverage_contract(policy)
    runtime_context = context or RuntimeContext.from_policy(policy)
    runtime_snapshot = snapshot or build_wiki_runtime_snapshot(
        vault,
        registry_contract=policy["registry_contract"],
        include_frontmatter=True,
        include_page_links=True,
        include_related_links=False,
        include_evidence_links=True,
    )

    if runtime_snapshot.duplicate_stems:
        report = {
            **_base_report(
                vault,
                policy=policy,
                policy_path=policy_path,
                runtime_snapshot=runtime_snapshot,
                context=runtime_context,
            ),
            "status": "fail",
            "summary": {
                "cohorts_evaluated": 0,
                "cohorts_with_matching_pages": 0,
                "coverage_gap_count": 0,
            },
            "cohorts": [],
            "review_candidates": [],
            "errors": [
                {
                    "type": "duplicate_page_stem",
                    "detail": {
                        stem: [report_path(vault, path) for path in paths]
                        for stem, paths in sorted(runtime_snapshot.duplicate_stems.items())
                    },
                }
            ],
        }
        schema = load_schema(vault / WIKI_EVAL_COVERAGE_SCHEMA)
        errors = validate_with_schema(report, schema)
        if errors:
            raise ValueError(f"wiki eval coverage report schema validation failed: {errors[0]}")
        return report

    pages = _page_contexts(vault, runtime_snapshot)
    coverage_context = _coverage_context(policy, runtime_snapshot)
    cohorts: list[dict] = []
    review_candidates: list[dict] = []
    cohorts_with_matching_pages = 0
    for cohort in policy["eval_coverage_review"]["cohorts"]:
        cohort_payload, candidate = _cohort_report(
            vault,
            policy,
            cohort,
            pages,
            coverage_context,
            policy_path=policy_path,
        )
        cohorts.append(cohort_payload)
        if cohort_payload["matching_page_count"] > 0:
            cohorts_with_matching_pages += 1
        if candidate is not None:
            review_candidates.append(candidate)

    status = "warn" if review_candidates else "pass"
    report = {
        **_base_report(
            vault,
            policy=policy,
            policy_path=policy_path,
            runtime_snapshot=runtime_snapshot,
            context=runtime_context,
        ),
        "status": status,
        "summary": {
            "cohorts_evaluated": len(cohorts),
            "cohorts_with_matching_pages": cohorts_with_matching_pages,
            "coverage_gap_count": len(review_candidates),
        },
        "cohorts": cohorts,
        "review_candidates": review_candidates,
    }
    schema = load_schema(vault / WIKI_EVAL_COVERAGE_SCHEMA)
    errors = validate_with_schema(report, schema)
    if errors:
        raise ValueError(f"wiki eval coverage report schema validation failed: {errors[0]}")
    return report
