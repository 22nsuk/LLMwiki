#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import WIKI_STAGE2_EVAL_SCHEMA_PATH
    from ops.scripts.wiki_snapshot_runtime import (
        WikiRuntimeSnapshot,
        build_wiki_runtime_snapshot,
    )
    from ops.scripts.wiki_stage2_runtime import (
        broad_synthesis_boundary_missing_sections,
        broad_wiki_synthesis_metrics,
        content_quality_scaffold_missing_sections,
        evidence_source_links,
        inbound_page_linkers,
        research_anchor_missing_sections,
        seed_source_missing_sections,
        stable_wiki_inbound_linkers,
    )
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import WIKI_STAGE2_EVAL_SCHEMA_PATH

    from .wiki_snapshot_runtime import WikiRuntimeSnapshot, build_wiki_runtime_snapshot
    from .wiki_stage2_runtime import (
        broad_synthesis_boundary_missing_sections,
        broad_wiki_synthesis_metrics,
        content_quality_scaffold_missing_sections,
        evidence_source_links,
        inbound_page_linkers,
        research_anchor_missing_sections,
        seed_source_missing_sections,
        stable_wiki_inbound_linkers,
    )


@dataclass(frozen=True)
class _Stage2EvalContext:
    vault: Path
    pages: dict
    page_lookup: dict
    texts: dict
    frontmatters: dict
    stage2_eval_policy: dict
    content_promotion_review: dict
    frontmatter_contract: dict
    inbound_sources: dict
    research_anchor_required_sections: list
    research_anchor_min_inbound_links: int


PRODUCER = "ops.scripts.wiki_stage2_eval"
SOURCE_COMMAND = "python -m ops.scripts.wiki_stage2_eval"
DEFAULT_OUT = "ops/reports/wiki-stage2-eval-report.json"


def _policy_report(vault: Path, resolved_policy_path: Path, policy: dict) -> dict:
    return {
        "path": report_path(vault, resolved_policy_path),
        "version": policy.get("version"),
    }


def _base_report(
    vault: Path,
    *,
    resolved_policy_path: Path,
    policy: dict,
    runtime_snapshot: WikiRuntimeSnapshot,
    context: RuntimeContext,
) -> dict:
    generated_at = context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="wiki_stage2_eval_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=WIKI_STAGE2_EVAL_SCHEMA_PATH,
            source_paths=["ops/scripts/wiki_stage2_eval.py"],
            path_group_inputs={
                "pages": sorted(report_path(vault, path) for path in runtime_snapshot.pages.values()),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": _policy_report(vault, resolved_policy_path, policy),
    }


def _duplicate_stem_failure_report(
    vault: Path,
    *,
    resolved_policy_path: Path,
    policy: dict,
    runtime_snapshot: WikiRuntimeSnapshot,
    duplicate_stems: dict,
    context: RuntimeContext,
) -> dict:
    return {
        **_base_report(
            vault,
            resolved_policy_path=resolved_policy_path,
            policy=policy,
            runtime_snapshot=runtime_snapshot,
            context=context,
        ),
        "status": "fail",
        "max_score": 0,
        "total_score": 0,
        "pages": [],
        "errors": [
            {
                "type": "duplicate_page_stem",
                "detail": {
                    stem: [report_path(vault, path) for path in paths]
                    for stem, paths in sorted(duplicate_stems.items())
                },
            }
        ],
    }


def _stage2_context(vault: Path, policy: dict, runtime_snapshot: WikiRuntimeSnapshot) -> _Stage2EvalContext:
    content_promotion_review = policy["content_promotion_review"]
    return _Stage2EvalContext(
        vault=vault,
        pages=runtime_snapshot.pages,
        page_lookup=runtime_snapshot.page_lookup,
        texts=runtime_snapshot.texts,
        frontmatters=runtime_snapshot.frontmatters,
        stage2_eval_policy=policy["stage2_eval"],
        content_promotion_review=content_promotion_review,
        frontmatter_contract=policy["frontmatter_contract"],
        inbound_sources=inbound_page_linkers(runtime_snapshot.page_links, runtime_snapshot.pages),
        research_anchor_required_sections=content_promotion_review["research_anchor_required_sections"],
        research_anchor_min_inbound_links=content_promotion_review["research_anchor_min_inbound_links"],
    )


def _source_count_result(ctx: _Stage2EvalContext, stem: str, text: str, frontmatter: dict) -> dict | None:
    if not (ctx.stage2_eval_policy["source_count_consistency_enabled"] and stem.startswith("synthesis--")):
        return None
    declared_source_count = frontmatter.get("source_count") if isinstance(frontmatter, dict) else None
    supporting_source_links = evidence_source_links(text, ctx.page_lookup)
    return {
        "eval": "declared_source_count_matches_evidence",
        "pass": (
            isinstance(declared_source_count, int)
            and declared_source_count == len(supporting_source_links)
        ),
        "detail": {
            "declared_source_count": declared_source_count,
            "evidence_source_count": len(supporting_source_links),
            "evidence_source_links": supporting_source_links,
        },
    }


def _central_research_result(
    ctx: _Stage2EvalContext,
    *,
    stem: str,
    relative_path: str,
    text: str,
    frontmatter: dict,
) -> dict | None:
    if not (
        ctx.stage2_eval_policy["central_research_anchor_enabled"]
        and relative_path.startswith("wiki/source--")
        and isinstance(frontmatter, dict)
        and frontmatter.get("source_type") == "domain-research-paper"
    ):
        return None
    inbound_linkers = sorted(ctx.inbound_sources.get(stem, set()))
    if len(inbound_linkers) < ctx.research_anchor_min_inbound_links:
        return None
    missing_sections = research_anchor_missing_sections(text, ctx.research_anchor_required_sections)
    return {
        "eval": "central_research_source_has_anchor_layer",
        "pass": not missing_sections,
        "detail": {
            "inbound_links": len(inbound_linkers),
            "threshold": ctx.research_anchor_min_inbound_links,
            "missing_sections": missing_sections,
            "supporting_pages": [
                report_path(ctx.vault, ctx.pages[source_stem])
                for source_stem in inbound_linkers
                if source_stem in ctx.pages
            ],
        },
    }


def _seed_source_result(
    ctx: _Stage2EvalContext,
    *,
    stem: str,
    relative_path: str,
    text: str,
    frontmatter: dict,
) -> dict | None:
    if not (
        ctx.stage2_eval_policy["seed_source_absorption_enabled"]
        and relative_path.startswith("wiki/source--")
        and isinstance(frontmatter, dict)
        and frontmatter.get("source_type") != "domain-research-paper"
    ):
        return None
    inbound_linkers = sorted(ctx.inbound_sources.get(stem, set()))
    stable_inbound_linkers = stable_wiki_inbound_linkers(inbound_linkers)
    if stable_inbound_linkers:
        return None
    missing_sections = seed_source_missing_sections(text)
    return {
        "eval": "seed_source_has_absorption_hint",
        "pass": not missing_sections,
        "detail": {
            "stable_inbound_linkers": stable_inbound_linkers,
            "all_inbound_linkers": inbound_linkers,
            "missing_sections": missing_sections,
        },
    }


def _broad_synthesis_result(ctx: _Stage2EvalContext, *, relative_path: str, text: str) -> dict | None:
    if not (
        ctx.stage2_eval_policy["broad_synthesis_boundary_enabled"]
        and relative_path.startswith("wiki/synthesis--")
    ):
        return None
    supporting_source_links = evidence_source_links(text, ctx.page_lookup)
    broadness = broad_wiki_synthesis_metrics(
        text,
        supporting_source_links,
        ctx.content_promotion_review,
    )
    if not broadness["applies"]:
        return None
    missing_sections = broad_synthesis_boundary_missing_sections(text)
    return {
        "eval": "broad_synthesis_has_boundary_sections",
        "pass": not missing_sections,
        "detail": {
            "value": broadness["value"],
            "threshold": broadness["threshold"],
            "missing_sections": missing_sections,
            "evidence_source_links": supporting_source_links,
        },
    }


def _content_quality_scaffold_result(
    ctx: _Stage2EvalContext,
    *,
    relative_path: str,
    text: str,
    frontmatter: dict,
) -> dict | None:
    if not (
        ctx.stage2_eval_policy["content_quality_scaffold_enabled"]
        and (
            relative_path.startswith(("wiki/concept--", "wiki/synthesis--"))
        )
        and isinstance(frontmatter, dict)
    ):
        return None

    advisory = (
        ctx.frontmatter_contract.get("metadata_review", {})
        .get("content_quality_advisory", {})
    )
    if not advisory.get("enabled", False):
        return None
    applies_to = set(advisory.get("applies_to_page_types", ["concept", "synthesis"]))
    if frontmatter.get("page_type") not in applies_to:
        return None

    recommended_headings = list(advisory.get("recommended_headings", []))
    missing_sections = content_quality_scaffold_missing_sections(text, recommended_headings)
    return {
        "eval": "content_quality_scaffold_present",
        "pass": not missing_sections,
        "detail": {
            "recommended_headings": recommended_headings,
            "missing_sections": missing_sections,
        },
    }


def _page_results(ctx: _Stage2EvalContext, stem: str, path: Path) -> list[dict]:
    relative_path = report_path(ctx.vault, path)
    text = ctx.texts[stem]
    frontmatter = ctx.frontmatters[stem]
    candidates = [
        _source_count_result(ctx, stem, text, frontmatter),
        _central_research_result(
            ctx,
            stem=stem,
            relative_path=relative_path,
            text=text,
            frontmatter=frontmatter,
        ),
        _seed_source_result(
            ctx,
            stem=stem,
            relative_path=relative_path,
            text=text,
            frontmatter=frontmatter,
        ),
        _broad_synthesis_result(ctx, relative_path=relative_path, text=text),
        _content_quality_scaffold_result(
            ctx,
            relative_path=relative_path,
            text=text,
            frontmatter=frontmatter,
        ),
    ]
    return [result for result in candidates if result is not None]


def _report_pages(ctx: _Stage2EvalContext) -> tuple[list[dict], int, int]:
    report_pages = []
    total_score = 0
    max_score = 0
    for stem, path in sorted(ctx.pages.items()):
        results = _page_results(ctx, stem, path)
        if not results:
            continue
        score = sum(1 for result in results if result["pass"])
        page_max = len(results)
        total_score += score
        max_score += page_max
        report_pages.append(
            {
                "page": report_path(ctx.vault, path),
                "score": score,
                "max_score": page_max,
                "results": results,
            }
        )
    return report_pages, total_score, max_score


def evaluate(
    vault: Path,
    policy_path: str | None = None,
    snapshot: WikiRuntimeSnapshot | None = None,
    *,
    context: RuntimeContext | None = None,
) -> dict:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    runtime_snapshot = snapshot or build_wiki_runtime_snapshot(
        vault,
        include_frontmatter=True,
        include_page_links=True,
        include_related_links=False,
        include_evidence_links=False,
    )
    duplicate_stems = runtime_snapshot.duplicate_stems

    if duplicate_stems:
        return _duplicate_stem_failure_report(
            vault,
            resolved_policy_path=resolved_policy_path,
            policy=policy,
            runtime_snapshot=runtime_snapshot,
            duplicate_stems=duplicate_stems,
            context=runtime_context,
        )

    report_pages, total_score, max_score = _report_pages(_stage2_context(vault, policy, runtime_snapshot))
    status = "pass" if total_score == max_score else "fail"
    return {
        **_base_report(
            vault,
            resolved_policy_path=resolved_policy_path,
            policy=policy,
            runtime_snapshot=runtime_snapshot,
            context=runtime_context,
        ),
        "status": status,
        "max_score": max_score,
        "total_score": total_score,
        "pages": report_pages,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--require-max-score", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    vault = Path(args.vault)
    report = evaluate(vault, args.policy)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=WIKI_STAGE2_EVAL_SCHEMA_PATH,
                out_path=args.out,
                default_relative_path=DEFAULT_OUT,
                context="wiki stage2 eval report schema validation failed",
                trailing_newline=False,
            )
        )
    else:
        print(text)
    raise SystemExit(1 if args.require_max_score and report["status"] != "pass" else 0)


if __name__ == "__main__":
    main()
