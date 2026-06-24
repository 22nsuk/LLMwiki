#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.frontmatter_runtime import validate_frontmatter
    from ops.scripts.core.policy_runtime import (
        load_policy,
        report_path,
        required_sections_from_policy,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import EVAL_REPORT_SCHEMA_PATH
    from ops.scripts.core.source_trace_profile_runtime import (
        source_trace_profile_summary,
    )
    from ops.scripts.eval.source_page_substance_runtime import (
        evaluate_source_page_substance,
    )
    from ops.scripts.eval.wiki_page_runtime import (
        INDEXISH_PAGES,
        SPECIAL_PAGES,
        page_prefix,
        required_sections_for_page,
        section_body,
        section_exists,
        source_trace_item_count,
    )
    from ops.scripts.eval.wiki_quality_runtime import (
        broken_wikilinks,
        has_placeholder,
        open_question_budget_status,
        source_trace_targets_blocking_profile,
        source_trace_targets_for_profile,
    )
    from ops.scripts.eval.wiki_snapshot_runtime import (
        WikiRuntimeSnapshot,
        build_wiki_runtime_snapshot,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.frontmatter_runtime import validate_frontmatter
    from ops.scripts.core.policy_runtime import (
        load_policy,
        report_path,
        required_sections_from_policy,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import EVAL_REPORT_SCHEMA_PATH
    from ops.scripts.core.source_trace_profile_runtime import (
        source_trace_profile_summary,
    )

    from .source_page_substance_runtime import evaluate_source_page_substance
    from .wiki_page_runtime import (
        INDEXISH_PAGES,
        SPECIAL_PAGES,
        page_prefix,
        required_sections_for_page,
        section_body,
        section_exists,
        source_trace_item_count,
    )
    from .wiki_quality_runtime import (
        broken_wikilinks,
        has_placeholder,
        open_question_budget_status,
        source_trace_targets_blocking_profile,
        source_trace_targets_for_profile,
    )
    from .wiki_snapshot_runtime import WikiRuntimeSnapshot, build_wiki_runtime_snapshot


@dataclass(frozen=True)
class EvalInputs:
    policy: dict[str, Any]
    resolved_policy_path: Path
    runtime_context: RuntimeContext
    required_sections: dict[str, Any]
    readiness_gate: dict[str, Any]
    frontmatter_contract: dict[str, Any]
    runtime_snapshot: WikiRuntimeSnapshot
    release_archive_profile: bool = False


@dataclass(frozen=True)
class PageEvalReport:
    page: dict[str, Any]
    score: int
    max_score: int


PRODUCER = "ops.scripts.wiki_eval"
SOURCE_COMMAND = "python -m ops.scripts.wiki_eval"
DEFAULT_OUT = "ops/reports/wiki-eval-report.json"


def _source_command(release_archive_profile: bool) -> str:
    if release_archive_profile:
        return f"{SOURCE_COMMAND} --release-archive-profile"
    return SOURCE_COMMAND


def _load_eval_inputs(
    vault: Path,
    policy_path: str | None,
    snapshot: WikiRuntimeSnapshot | None,
    context: RuntimeContext | None,
    *,
    release_archive_profile: bool = False,
) -> EvalInputs:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    runtime_snapshot = snapshot or build_wiki_runtime_snapshot(
        vault,
        registry_contract=policy["registry_contract"],
        include_frontmatter=True,
        include_related_links=True,
        include_page_links=False,
        include_evidence_links=False,
    )
    return EvalInputs(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        runtime_context=runtime_context,
        required_sections=required_sections_from_policy(policy),
        readiness_gate=policy["readiness_gate"],
        frontmatter_contract=policy["frontmatter_contract"],
        runtime_snapshot=runtime_snapshot,
        release_archive_profile=release_archive_profile,
    )


def _base_report(vault: Path, inputs: EvalInputs) -> dict[str, Any]:
    generated_at = inputs.runtime_context.isoformat_z()
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="wiki_eval_report",
            producer=PRODUCER,
            source_command=_source_command(inputs.release_archive_profile),
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=EVAL_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/eval/wiki_eval.py",
                "ops/scripts/eval/wiki_quality_runtime.py",
                "ops/scripts/core/source_trace_profile_runtime.py",
                "ops/scripts/core/source_trace_runtime.py",
            ],
            path_group_inputs={
                "pages": sorted(
                    report_path(vault, path) for path in inputs.runtime_snapshot.pages.values()
                ),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
    }


def _duplicate_stem_report(vault: Path, inputs: EvalInputs) -> dict[str, Any]:
    duplicate_stems = inputs.runtime_snapshot.duplicate_stems
    return {
        **_base_report(vault, inputs),
        "status": "fail",
        "max_score": 0,
        "total_score": 0,
        "pages": [],
        "errors": [
            {
                "type": "duplicate_page_stem",
                "detail": {
                    stem: [path.as_posix() for path in paths]
                    for stem, paths in sorted(duplicate_stems.items())
                },
            }
        ],
    }


def _frontmatter_result(vault: Path, path: Path, stem: str, inputs: EvalInputs) -> dict[str, Any]:
    frontmatter = inputs.runtime_snapshot.frontmatters.get(stem)
    frontmatter_ok = False
    if frontmatter is not None:
        frontmatter_ok = not validate_frontmatter(
            vault,
            path,
            stem,
            frontmatter,
            inputs.frontmatter_contract,
        )
    return {"eval": "frontmatter_contract", "pass": frontmatter_ok}


def _required_sections_result(vault: Path, path: Path, stem: str, text: str, inputs: EvalInputs) -> dict[str, Any]:
    page_required_sections = required_sections_for_page(vault, path, stem, inputs.required_sections)
    if page_required_sections:
        ok = all(section_exists(text, heading) for heading in page_required_sections)
    else:
        ok = True
    return {"eval": "required_sections_present", "pass": ok}


def _source_trace_results(vault: Path, text: str, inputs: EvalInputs) -> list[dict[str, Any]]:
    source_trace = section_body(text, "Source trace")
    profile_targets = source_trace_targets_for_profile(
        vault,
        source_trace,
        inputs.runtime_snapshot.source_trace_resolution_map,
        release_archive_profile=inputs.release_archive_profile,
    )
    missing_targets = source_trace_targets_blocking_profile(
        vault,
        source_trace,
        inputs.runtime_snapshot.source_trace_resolution_map,
        release_archive_profile=inputs.release_archive_profile,
    )
    classified_missing_targets = [
        target
        for target in profile_targets
        if target.get("classification") != "present"
    ]
    target_result: dict[str, Any] = {
        "eval": "source_trace_targets_exist",
        "pass": len(missing_targets) == 0,
    }
    if classified_missing_targets:
        target_result["detail"] = {
            "profile": "release_archive" if inputs.release_archive_profile else "strict",
            "summary": source_trace_profile_summary(profile_targets),
            "blocking_missing_targets": missing_targets,
            "classified_missing_targets": classified_missing_targets,
        }
    return [
        {
            "eval": "source_trace_present",
            "pass": source_trace_item_count(source_trace) >= inputs.readiness_gate["min_source_trace_items"],
        },
        target_result,
    ]


def _link_integration_result(stem: str, inputs: EvalInputs) -> dict[str, Any]:
    valid_links = inputs.runtime_snapshot.related_links.get(stem, set())
    return {
        "eval": "link_integration",
        "pass": len(valid_links) >= inputs.readiness_gate["min_related_links"],
    }


def _open_question_results(text: str, inputs: EvalInputs) -> list[dict[str, Any]]:
    open_question_budget = open_question_budget_status(
        section_body(text, "Open questions"),
        inputs.readiness_gate,
    )
    return [
        {
            "eval": "high_severity_open_questions_within_budget",
            "pass": not open_question_budget["high_overflow"],
        },
        {
            "eval": "medium_severity_open_questions_within_budget",
            "pass": (
                not open_question_budget["medium_overflow"]
                or inputs.readiness_gate["allow_warn_for_medium_question_overflow"]
            ),
        },
    ]


def _broken_link_result(text: str, inputs: EvalInputs) -> dict[str, Any]:
    broken = broken_wikilinks(text, inputs.runtime_snapshot.page_lookup, SPECIAL_PAGES)
    return {"eval": "broken_link_free", "pass": len(broken) == 0}


def _placeholder_result(stem: str, text: str) -> dict[str, Any]:
    placeholder = False
    if stem not in INDEXISH_PAGES:
        placeholder = has_placeholder(text)
    return {"eval": "placeholder_discipline", "pass": not placeholder}


def _source_page_substance_result(text: str) -> dict[str, Any]:
    return evaluate_source_page_substance(text)


def _decisionability_result(text: str) -> dict[str, Any]:
    return {
        "eval": "decisionability",
        "pass": section_exists(text, "Decision / takeaway"),
    }


def _page_results(vault: Path, path: Path, stem: str, text: str, inputs: EvalInputs) -> list[dict[str, Any]]:
    prefix = page_prefix(stem, inputs.required_sections)
    results = [
        _frontmatter_result(vault, path, stem, inputs),
        _required_sections_result(vault, path, stem, text, inputs),
        *_source_trace_results(vault, text, inputs),
        _link_integration_result(stem, inputs),
        *_open_question_results(text, inputs),
        _broken_link_result(text, inputs),
        _placeholder_result(stem, text),
    ]
    if prefix == "source--":
        results.append(_source_page_substance_result(text))
    if prefix in {"synthesis--", "query--"}:
        results.append(_decisionability_result(text))
    return results


def _evaluate_page(vault: Path, stem: str, path: Path, inputs: EvalInputs) -> PageEvalReport:
    text = inputs.runtime_snapshot.texts[stem]
    results = _page_results(vault, path, stem, text, inputs)
    score = sum(1 for result in results if result["pass"])
    page_max = len(results)
    return PageEvalReport(
        page={
            "page": path.as_posix(),
            "score": score,
            "max_score": page_max,
            "results": results,
        },
        score=score,
        max_score=page_max,
    )


def _build_page_reports(vault: Path, inputs: EvalInputs) -> tuple[list[dict[str, Any]], int, int]:
    report_pages = []
    total_score = 0
    max_score = 0
    for stem, path in sorted(inputs.runtime_snapshot.pages.items()):
        page_report = _evaluate_page(vault, stem, path, inputs)
        total_score += page_report.score
        max_score += page_report.max_score
        report_pages.append(page_report.page)
    return report_pages, total_score, max_score


def evaluate(
    vault: Path,
    policy_path: str | None = None,
    snapshot: WikiRuntimeSnapshot | None = None,
    *,
    context: RuntimeContext | None = None,
    release_archive_profile: bool = False,
) -> dict:
    inputs = _load_eval_inputs(
        vault,
        policy_path,
        snapshot,
        context,
        release_archive_profile=release_archive_profile,
    )
    if inputs.runtime_snapshot.duplicate_stems:
        return _duplicate_stem_report(vault, inputs)

    report_pages, total_score, max_score = _build_page_reports(vault, inputs)
    status = "pass" if total_score == max_score else "fail"
    return {
        **_base_report(vault, inputs),
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
    ap.add_argument("--release-archive-profile", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    vault = Path(args.vault)
    report = evaluate(vault, args.policy, release_archive_profile=args.release_archive_profile)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=EVAL_REPORT_SCHEMA_PATH,
                out_path=args.out,
                default_relative_path=DEFAULT_OUT,
                context="wiki eval report schema validation failed",
                trailing_newline=False,
            )
        )
    else:
        print(text)
    raise SystemExit(1 if args.require_max_score and report["status"] != "pass" else 0)


if __name__ == "__main__":
    main()
