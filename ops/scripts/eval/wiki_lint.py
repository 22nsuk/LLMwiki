#!/usr/bin/env python3
from __future__ import annotations
import sys

import argparse
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Dict

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.wiki_doc_audit_runtime import (
        documentation_markdown_surfaces,
        external_report_reference_issues,
        router_summary_count_issues,
    )
    from ops.scripts.wiki_lint_page_runtime import PageLintContext, lint_page, orphan_issues
    from ops.scripts.policy_runtime import load_policy, report_path, required_sections_from_policy
    from ops.scripts.python_function_budget_runtime import python_function_budget_candidates
    from ops.scripts.raw_markdown_runtime import raw_markdown_quality_pass
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import LINT_REPORT_SCHEMA_PATH
    from ops.scripts.wiki_eval_coverage_runtime import build_report as build_eval_coverage_report
    from ops.scripts.wiki_lint_registry_runtime import lint_registry_contract, registry_review_exempt_paths
    from ops.scripts.wiki_lint_review_runtime import (
        active_source_missing_concept_candidates,
        concept_carryover_continuity_candidates,
        content_promotion_candidates,
        research_source_anchor_candidates,
        synthesis_analysis_template_candidates,
        synthesis_follow_up_split_candidates,
        wiki_synthesis_multi_question_candidates,
    )
    from ops.scripts.wiki_snapshot_runtime import WikiRuntimeSnapshot, build_wiki_runtime_snapshot
    from ops.scripts.wiki_page_runtime import required_sections_for_page
else:
    from .wiki_doc_audit_runtime import (
        documentation_markdown_surfaces,
        external_report_reference_issues,
        router_summary_count_issues,
    )
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from .wiki_lint_page_runtime import PageLintContext, lint_page, orphan_issues
    from ops.scripts.policy_runtime import load_policy, report_path, required_sections_from_policy
    from ops.scripts.python_function_budget_runtime import python_function_budget_candidates
    from ops.scripts.raw_markdown_runtime import raw_markdown_quality_pass
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import LINT_REPORT_SCHEMA_PATH
    from .wiki_eval_coverage_runtime import build_report as build_eval_coverage_report
    from .wiki_lint_registry_runtime import lint_registry_contract, registry_review_exempt_paths
    from .wiki_lint_review_runtime import (
        active_source_missing_concept_candidates,
        concept_carryover_continuity_candidates,
        content_promotion_candidates,
        research_source_anchor_candidates,
        synthesis_analysis_template_candidates,
        synthesis_follow_up_split_candidates,
        wiki_synthesis_multi_question_candidates,
    )
    from .wiki_snapshot_runtime import WikiRuntimeSnapshot, build_wiki_runtime_snapshot
    from .wiki_page_runtime import required_sections_for_page


@dataclass(frozen=True)
class _LintRuntimeContext:
    vault: Path
    policy: dict
    resolved_policy_path: Path
    runtime_snapshot: WikiRuntimeSnapshot

    @cached_property
    def page_relative_paths(self) -> dict[str, str]:
        return {
            stem: report_path(self.vault, path)
            for stem, path in self.runtime_snapshot.pages.items()
        }

    @cached_property
    def documentation_surfaces(self) -> list[tuple[str, Path]]:
        return documentation_markdown_surfaces(self.vault)

    @cached_property
    def vault_report_path(self) -> str:
        return report_path(self.vault, self.vault)

    @cached_property
    def policy_report_path(self) -> str:
        return report_path(self.vault, self.resolved_policy_path)


@dataclass(frozen=True)
class _LintPolicyConfig:
    required_sections: dict
    lint_thresholds: dict
    readiness_gate: dict
    refactor_triggers: dict
    content_promotion_review: dict
    doc_audit: dict
    system_refactor_policy: dict
    python_function_review: dict
    registry_contract: dict
    raw_markdown_contract: dict
    corpus_routing: dict
    frontmatter_contract: dict
    source_page_slug_review: dict
    schema_versioning: dict | None
    registry_review_exempt: set[str]


@dataclass
class _LintAccumulator:
    errors: list[dict]
    warnings: list[dict]
    review_candidates: list[dict]
    link_inbound: dict[str, int]
    page_links: Dict[str, set[str]]
    related_links: Dict[str, set[str]]
    evidence_links: Dict[str, set[str]]
    frontmatters: Dict[str, dict | None]

    @classmethod
    def for_pages(cls, pages: dict[str, Path]) -> "_LintAccumulator":
        return cls(
            errors=[],
            warnings=[],
            review_candidates=[],
            link_inbound={name: 0 for name in pages},
            page_links={},
            related_links={},
            evidence_links={},
            frontmatters={},
        )


PRODUCER = "ops.scripts.wiki_lint"
SOURCE_COMMAND = "python -m ops.scripts.wiki_lint"
DEFAULT_OUT = "ops/reports/wiki-lint-report.json"


def _source_command(release_archive_profile: bool) -> str:
    if release_archive_profile:
        return f"{SOURCE_COMMAND} --release-archive-profile"
    return SOURCE_COMMAND


def _lint_policy_config(policy: dict) -> _LintPolicyConfig:
    system_refactor_policy = policy["system_refactor_policy"]
    registry_contract = policy["registry_contract"]
    return _LintPolicyConfig(
        required_sections=required_sections_from_policy(policy),
        lint_thresholds=policy["lint_thresholds"],
        readiness_gate=policy["readiness_gate"],
        refactor_triggers=policy["refactor_triggers"],
        content_promotion_review=policy["content_promotion_review"],
        doc_audit=policy["doc_audit"],
        system_refactor_policy=system_refactor_policy,
        python_function_review=system_refactor_policy["python_function_review"],
        registry_contract=registry_contract,
        raw_markdown_contract=policy["raw_markdown_normalization_contract"],
        corpus_routing=policy["corpus_routing"],
        frontmatter_contract=policy["frontmatter_contract"],
        source_page_slug_review=policy["frontmatter_contract"]["metadata_review"].get(
            "source_page_slug",
            {},
        ),
        schema_versioning=policy.get("schema_versioning"),
        registry_review_exempt=registry_review_exempt_paths(registry_contract),
    )


def _build_lint_runtime_context(
    vault: Path,
    policy_path: str | None,
    snapshot: WikiRuntimeSnapshot | None,
) -> _LintRuntimeContext:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    registry_contract = policy["registry_contract"]
    runtime_snapshot = snapshot or build_wiki_runtime_snapshot(vault, registry_contract=registry_contract)
    return _LintRuntimeContext(
        vault=vault,
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_snapshot=runtime_snapshot,
    )


def add_issue(issue: dict, severity: str, errors: list, warnings: list) -> None:
    if severity == "fail":
        errors.append(issue)
        return
    if severity == "warn":
        warnings.append(issue)
        return
    raise ValueError(f"unsupported lint severity: {severity}")


def _emit_duplicate_stem_issues(
    runtime_context: _LintRuntimeContext,
    config: _LintPolicyConfig,
    acc: _LintAccumulator,
) -> None:
    for stem, paths in sorted(runtime_context.runtime_snapshot.duplicate_stems.items()):
        add_issue(
            {
                "type": "duplicate_page_stem",
                "page": paths[0].as_posix(),
                "detail": {
                    "stem": stem,
                    "paths": [path.as_posix() for path in paths],
                },
            },
            config.lint_thresholds["duplicate_page_stem"],
            acc.errors,
            acc.warnings,
        )


def _emit_source_trace_resolution_issues(
    runtime_context: _LintRuntimeContext,
    config: _LintPolicyConfig,
    acc: _LintAccumulator,
) -> None:
    vault = runtime_context.vault
    snapshot = runtime_context.runtime_snapshot
    for diagnostic in snapshot.source_trace_resolution_state["warnings"]:
        add_issue(
            {
                "type": "raw_registry_source_trace_resolution_warning",
                "page": report_path(vault, vault / diagnostic["path"]),
                "detail": {
                    "diagnostic_category": diagnostic["type"],
                    "diagnostic_type": diagnostic.get("diagnostic_type", diagnostic["type"]),
                    "message": diagnostic["detail"],
                },
            },
            config.lint_thresholds["raw_registry_source_trace_resolution_warning"],
            acc.errors,
            acc.warnings,
        )


def _lint_pages(
    runtime_context: _LintRuntimeContext,
    config: _LintPolicyConfig,
    acc: _LintAccumulator,
    *,
    release_archive_profile: bool,
) -> None:
    vault = runtime_context.vault
    snapshot = runtime_context.runtime_snapshot
    pages = snapshot.pages
    for stem, path in pages.items():
        text = snapshot.texts[stem]
        page_result = lint_page(
            PageLintContext(
                vault=vault,
                path=path,
                stem=stem,
                text=text,
                page_lookup=snapshot.page_lookup,
                required_headings=required_sections_for_page(vault, path, stem, config.required_sections),
                lint_thresholds=config.lint_thresholds,
                readiness_gate=config.readiness_gate,
                frontmatter_contract=config.frontmatter_contract,
                schema_versioning=config.schema_versioning,
                source_trace_resolution_map=snapshot.source_trace_resolution_map,
                refactor_triggers=config.refactor_triggers,
                system_refactor_policy=config.system_refactor_policy,
                registry_review_exempt=config.registry_review_exempt,
                frontmatter=snapshot.frontmatters.get(stem),
                frontmatter_error=snapshot.frontmatter_errors.get(stem),
                page_links=snapshot.page_links.get(stem),
                related_links=snapshot.related_links.get(stem),
                evidence_links=snapshot.evidence_links.get(stem),
                snapshot_loaded=True,
                release_archive_profile=release_archive_profile,
            )
        )

        acc.frontmatters[stem] = page_result.frontmatter
        acc.page_links[stem] = page_result.page_links
        acc.related_links[stem] = page_result.related_links
        acc.evidence_links[stem] = page_result.evidence_links
        acc.review_candidates.extend(page_result.review_candidates)
        for issue, severity in page_result.issues:
            add_issue(issue, severity, acc.errors, acc.warnings)

        for target in page_result.page_links:
            if target in pages:
                acc.link_inbound[target] += 1


def _emit_orphan_issues(
    runtime_context: _LintRuntimeContext,
    config: _LintPolicyConfig,
    acc: _LintAccumulator,
) -> None:
    for issue, severity in orphan_issues(
        acc.link_inbound,
        runtime_context.runtime_snapshot.pages,
        config.lint_thresholds["orphan_page"],
    ):
        add_issue(issue, severity, acc.errors, acc.warnings)


def _run_page_lint_pass(
    runtime_context: _LintRuntimeContext,
    config: _LintPolicyConfig,
    acc: _LintAccumulator,
    *,
    release_archive_profile: bool,
) -> None:
    _emit_duplicate_stem_issues(runtime_context, config, acc)
    _emit_source_trace_resolution_issues(runtime_context, config, acc)
    _lint_pages(runtime_context, config, acc, release_archive_profile=release_archive_profile)
    _emit_orphan_issues(runtime_context, config, acc)


def _run_registry_and_review_passes(
    runtime_context: _LintRuntimeContext,
    policy: dict,
    config: _LintPolicyConfig,
    acc: _LintAccumulator,
    *,
    context: RuntimeContext,
) -> dict:
    vault = runtime_context.vault
    pages = runtime_context.runtime_snapshot.pages
    registry_result = lint_registry_contract(
        vault,
        pages,
        acc.frontmatters,
        config.frontmatter_contract,
        config.lint_thresholds,
        config.system_refactor_policy,
        config.registry_contract,
        config.corpus_routing,
        config.source_page_slug_review,
        context=context,
    )
    acc.errors.extend(registry_result["errors"])
    acc.warnings.extend(registry_result["warnings"])
    acc.review_candidates.extend(registry_result["review_candidates"])

    eval_coverage_report = build_eval_coverage_report(
        vault,
        policy,
        runtime_context.resolved_policy_path,
        snapshot=runtime_context.runtime_snapshot,
        context=context,
    )
    acc.review_candidates.extend(eval_coverage_report["review_candidates"])
    acc.review_candidates.extend(
        synthesis_analysis_template_candidates(
            vault,
            pages,
            config.refactor_triggers,
        )
    )
    acc.review_candidates.extend(
        synthesis_follow_up_split_candidates(
            vault,
            pages,
            config.refactor_triggers,
        )
    )
    acc.review_candidates.extend(
        content_promotion_candidates(
            vault,
            pages,
            acc.related_links,
            acc.evidence_links,
            registry_result["registry_entries"],
            config.refactor_triggers,
            config.content_promotion_review,
        )
    )
    acc.review_candidates.extend(
        wiki_synthesis_multi_question_candidates(
            vault,
            pages,
            acc.evidence_links,
            config.content_promotion_review,
            config.refactor_triggers,
        )
    )
    acc.review_candidates.extend(
        research_source_anchor_candidates(
            vault,
            pages,
            acc.page_links,
            acc.frontmatters,
            config.refactor_triggers,
            config.content_promotion_review,
        )
    )
    acc.review_candidates.extend(
        active_source_missing_concept_candidates(
            vault,
            pages,
            acc.related_links,
            acc.frontmatters,
        )
    )
    acc.review_candidates.extend(
        concept_carryover_continuity_candidates(
            vault,
            pages,
            acc.related_links,
            config.refactor_triggers,
        )
    )
    acc.review_candidates.extend(
        python_function_budget_candidates(
            vault,
            config.python_function_review,
        )
    )
    return registry_result


def _run_documentation_and_raw_passes(
    runtime_context: _LintRuntimeContext,
    config: _LintPolicyConfig,
    registry_result: dict,
    acc: _LintAccumulator,
) -> None:
    vault = runtime_context.vault
    pages = runtime_context.runtime_snapshot.pages
    for issue in router_summary_count_issues(
        vault,
        pages,
        runtime_context.runtime_snapshot.page_lookup,
        registry_result["registry_entries"],
        config.doc_audit,
        relative_paths=runtime_context.page_relative_paths,
    ):
        add_issue(
            issue,
            config.lint_thresholds["router_summary_count_drift"],
            acc.errors,
            acc.warnings,
        )
    for issue in external_report_reference_issues(
        vault,
        pages,
        doc_audit_policy=config.doc_audit,
        relative_paths=runtime_context.page_relative_paths,
        documentation_surfaces=runtime_context.documentation_surfaces,
    ):
        add_issue(
            issue,
            config.lint_thresholds["external_report_reference_mismatch"],
            acc.errors,
            acc.warnings,
        )

    class _RawMarkdownEmitter:
        def issue(self, issue: dict, threshold_key: str) -> None:
            add_issue(issue, config.lint_thresholds[threshold_key], acc.errors, acc.warnings)

    raw_markdown_quality_pass(
        vault,
        emitter=_RawMarkdownEmitter(),
        raw_markdown_contract=config.raw_markdown_contract,
    )


def _lint_status(errors: list[dict], warnings: list[dict]) -> str:
    if errors:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def _build_lint_report(
    runtime_context: _LintRuntimeContext,
    acc: _LintAccumulator,
    *,
    context: RuntimeContext,
    release_archive_profile: bool,
) -> dict:
    pages = runtime_context.runtime_snapshot.pages
    generated_at = context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            runtime_context.vault,
            generated_at=generated_at,
            artifact_kind="wiki_lint_report",
            producer=PRODUCER,
            source_command=_source_command(release_archive_profile),
            resolved_policy_path=runtime_context.resolved_policy_path,
            schema_path=LINT_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/wiki_lint.py",
                "ops/scripts/wiki_lint_page_runtime.py",
                "ops/scripts/wiki_quality_runtime.py",
                "ops/scripts/source_trace_profile_runtime.py",
                "ops/scripts/source_trace_runtime.py",
            ],
            path_group_inputs={
                "pages": sorted(runtime_context.page_relative_paths.values()),
                "documentation_surfaces": sorted(
                    report_path(runtime_context.vault, path)
                    for _, path in runtime_context.documentation_surfaces
                ),
            },
        ),
        "vault": runtime_context.vault_report_path,
        "policy": {
            "path": runtime_context.policy_report_path,
            "version": runtime_context.policy.get("version"),
        },
        "status": _lint_status(acc.errors, acc.warnings),
        "errors": acc.errors,
        "warnings": acc.warnings,
        "review_candidates": acc.review_candidates,
        "stats": {
            "page_count": len(pages),
            "error_count": len(acc.errors),
            "warning_count": len(acc.warnings),
            "review_candidate_count": len(acc.review_candidates),
        },
    }


def lint(
    vault: Path,
    policy_path: str | None = None,
    snapshot: WikiRuntimeSnapshot | None = None,
    *,
    context: RuntimeContext | None = None,
    release_archive_profile: bool = False,
) -> dict:
    runtime_context = _build_lint_runtime_context(vault, policy_path, snapshot)
    policy = runtime_context.policy
    clock_context = context or RuntimeContext.from_policy(policy)
    config = _lint_policy_config(policy)
    acc = _LintAccumulator.for_pages(runtime_context.runtime_snapshot.pages)
    _run_page_lint_pass(
        runtime_context,
        config,
        acc,
        release_archive_profile=release_archive_profile,
    )
    registry_result = _run_registry_and_review_passes(
        runtime_context,
        policy,
        config,
        acc,
        context=clock_context,
    )
    _run_documentation_and_raw_passes(runtime_context, config, registry_result, acc)
    return _build_lint_report(
        runtime_context,
        acc,
        context=clock_context,
        release_archive_profile=release_archive_profile,
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--release-archive-profile", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    vault = Path(args.vault)
    report = lint(vault, args.policy, release_archive_profile=args.release_archive_profile)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=LINT_REPORT_SCHEMA_PATH,
                out_path=args.out,
                default_relative_path=DEFAULT_OUT,
                context="wiki lint report schema validation failed",
                trailing_newline=False,
            )
        )
    else:
        print(text)
    raise SystemExit(1 if report["status"] == "fail" else 0)


if __name__ == "__main__":
    main()
