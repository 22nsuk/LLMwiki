#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.source_page_substance_runtime import (
        evaluate_source_page_substance,
    )
    from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
    from ops.scripts.mechanism.finalize_run_log_runtime import (
        log_text_with_appended_entry,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.source_page_substance_runtime import (
        evaluate_source_page_substance,
    )
    from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
    from ops.scripts.mechanism.finalize_run_log_runtime import (
        log_text_with_appended_entry,
    )

DEFAULT_OUT = "ops/reports/source-substance-cohort-classification.json"
SYSTEM_LOG_PATH = "system/system-log.md"
PRODUCER = "ops.scripts.registry.source_substance_cohort_classify"
COHORT_DATES = ("2026-05-29", "2026-06-17")
DATE_RE = re.compile(r"source--.*-(2026-\d{2}-\d{2})\.md$")


def _cohort_date(path: Path) -> str | None:
    match = DATE_RE.search(path.name)
    if match is None:
        return None
    date = match.group(1)
    return date if date in COHORT_DATES else None


def _synthesis_links(related: set[str], evidence: set[str], page_links: set[str]) -> list[str]:
    combined = related | evidence | page_links
    return sorted(link for link in combined if link.startswith("synthesis--"))


def _classify_page(
    *,
    rel_path: str,
    cohort_date: str,
    substance: dict[str, Any],
    synthesis_links: list[str],
) -> str:
    substance_pass = bool(substance.get("pass"))
    if substance_pass and synthesis_links:
        return "recover"
    if substance_pass:
        return "hold"
    if synthesis_links:
        return "hold"
    return "registry_only_demote"


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    snapshot = build_wiki_runtime_snapshot(vault)
    entries: list[dict[str, Any]] = []
    counts = {"recover": 0, "hold": 0, "registry_only_demote": 0}

    for stem, path in sorted(snapshot.pages.items()):
        rel_path = report_path(vault, path)
        if not rel_path.startswith("wiki/source--"):
            continue
        cohort_date = _cohort_date(path)
        if cohort_date is None:
            continue
        text = snapshot.texts[stem]
        substance = evaluate_source_page_substance(text)
        synthesis = _synthesis_links(
            snapshot.related_links.get(stem, set()),
            snapshot.evidence_links.get(stem, set()),
            snapshot.page_links.get(stem, set()),
        )
        classification = _classify_page(
            rel_path=rel_path,
            cohort_date=cohort_date,
            substance=substance,
            synthesis_links=synthesis,
        )
        counts[classification] += 1
        entries.append(
            {
                "page": rel_path,
                "cohort_date": cohort_date,
                "classification": classification,
                "substance_pass": bool(substance.get("pass")),
                "substance_failures": list(substance.get("failures", [])),
                "synthesis_link_count": len(synthesis),
                "synthesis_links": synthesis,
            }
        )

    status = "attention" if counts["registry_only_demote"] else "pass"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="source_substance_cohort_classification",
            producer=PRODUCER,
            source_command="python -m ops.scripts.registry.source_substance_cohort_classify --vault .",
            resolved_policy_path=resolved_policy_path,
            schema_path="",
            source_paths=[
                "ops/scripts/registry/source_substance_cohort_classify.py",
                "ops/scripts/eval/source_page_substance_runtime.py",
            ],
            file_inputs={},
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "cohort_dates": list(COHORT_DATES),
        "summary": {
            "page_count": len(entries),
            **counts,
        },
        "entries": entries,
    }


def append_system_log_entry(vault: Path, report: dict[str, Any], *, context: RuntimeContext) -> Path:
    log_path = vault / SYSTEM_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    summary = report["summary"]
    heading = f"Source substance cohort classification {context.local_heading_timestamp()}"
    entry = (
        f"# {heading}\n\n"
        f"- artifact: {DEFAULT_OUT}\n"
        f"- status: {report['status']}\n"
        f"- recover: {summary['recover']}\n"
        f"- hold: {summary['hold']}\n"
        f"- registry_only_demote: {summary['registry_only_demote']}\n"
        f"- command: python -m ops.scripts.registry.source_substance_cohort_classify --vault .\n"
    )
    log_path.write_text(log_text_with_appended_entry(existing, entry), encoding="utf-8")
    return log_path


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = vault / out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify dated source-page cohorts by substance and synthesis linkage."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--skip-system-log", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    policy, _ = load_policy(vault)
    context = RuntimeContext.from_policy(policy)
    report = build_report(vault, context=context)
    path = write_report(vault, report, args.out)
    if not args.skip_system_log:
        append_system_log_entry(vault, report, context=context)
    print(display_path(vault, path))
    return 0 if report["status"] != "fail" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
