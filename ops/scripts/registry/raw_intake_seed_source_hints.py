#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
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
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
    from ops.scripts.eval.wiki_stage2_runtime import (
        inbound_page_linkers,
        seed_source_missing_sections,
        stable_wiki_inbound_linkers,
    )
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
    from ops.scripts.eval.wiki_stage2_runtime import (
        inbound_page_linkers,
        seed_source_missing_sections,
        stable_wiki_inbound_linkers,
    )


PRODUCER = "ops.scripts.registry.raw_intake_seed_source_hints"
SOURCE_COMMAND = "python -m ops.scripts.registry.raw_intake_seed_source_hints"
SCHEMA_PATH = "ops/schemas/raw-intake-seed-source-hints-report.schema.json"
DEFAULT_OUT = "tmp/raw-intake-seed-source-hints-report.json"
REQUIRED_HINT_SECTIONS = (
    "Why this is source-only for now",
    "What future cluster would absorb this",
)


def _link_or_code(value: str) -> str:
    text = value.strip()
    if not text:
        return "`source-only`"
    if text.startswith(("concept--", "synthesis--", "query--")):
        return f"[[{text}]]"
    return f"`{text}`"


def _frontmatter_text(frontmatter: dict[str, Any], field: str, default: str = "") -> str:
    value = frontmatter.get(field)
    return str(value).strip() if value is not None else default


def _future_cluster(frontmatter: dict[str, Any]) -> str:
    for field in ("route_subtype", "seed_cluster", "primary_concept", "domain"):
        value = _frontmatter_text(frontmatter, field)
        if value and value != "source-only":
            return value
    return "source-only"


def _suggested_hint_sections(frontmatter: dict[str, Any]) -> list[dict[str, str]]:
    authority = _frontmatter_text(frontmatter, "authority_class", "source_only_seed")
    route_decision = _frontmatter_text(frontmatter, "route_decision", "keep_source_only_seed")
    primary_concept = _frontmatter_text(frontmatter, "primary_concept", "source-only")
    primary_lens = _frontmatter_text(
        frontmatter,
        "primary_lens",
        "stable concept/synthesis route가 생길 때까지 원문 provenance를 보존한다.",
    )
    future_cluster = _future_cluster(frontmatter)
    return [
        {
            "heading": "Why this is source-only for now",
            "body": (
                f"이 source는 현재 `{authority}` / `{route_decision}` 상태다. "
                f"안정적인 concept/synthesis inbound link가 생기기 전까지는 "
                f"{_link_or_code(primary_concept)} 후보 축의 provenance seed로 보존한다."
            ),
        },
        {
            "heading": "What future cluster would absorb this",
            "body": (
                f"향후 {_link_or_code(future_cluster)} 축에서 반복 source가 쌓이거나, "
                f"{primary_lens} 이 렌즈가 독립 synthesis의 질문으로 굳어지면 흡수한다."
            ),
        },
    ]


def _is_seed_source_page(relative_path: str, frontmatter: dict[str, Any]) -> bool:
    return (
        relative_path.startswith("wiki/source--")
        and frontmatter.get("source_type") != "domain-research-paper"
    )


def _insert_missing_sections(text: str, sections: list[dict[str, str]]) -> str:
    if not sections:
        return text
    block = "\n\n".join(
        f"## {section['heading']}\n{section['body'].strip()}" for section in sections
    )
    anchor = re.search(
        r"^##\s+(Related pages|Open questions|Source trace)\s*$",
        text,
        flags=re.MULTILINE,
    )
    if not anchor:
        return text.rstrip() + "\n\n" + block + "\n"
    prefix = text[: anchor.start()].rstrip()
    suffix = text[anchor.start() :].lstrip()
    return prefix + "\n\n" + block + "\n\n" + suffix


def _write_missing_sections(path: Path, text: str, missing_sections: list[str], suggested: list[dict[str, str]]) -> bool:
    sections = [section for section in suggested if section["heading"] in set(missing_sections)]
    updated = _insert_missing_sections(text, sections)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def build_report(
    vault: Path,
    *,
    write: bool = False,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    snapshot = build_wiki_runtime_snapshot(vault)
    inbound_sources = inbound_page_linkers(snapshot.page_links, snapshot.pages)

    candidates: list[dict[str, Any]] = []
    write_count = 0
    for stem, path in sorted(snapshot.pages.items()):
        relative_path = report_path(vault, path)
        frontmatter = snapshot.frontmatters.get(stem)
        if not isinstance(frontmatter, dict) or not _is_seed_source_page(relative_path, frontmatter):
            continue
        inbound_linkers = sorted(inbound_sources.get(stem, set()))
        stable_linkers = stable_wiki_inbound_linkers(inbound_linkers)
        if stable_linkers:
            continue
        text = snapshot.texts[stem]
        missing_sections = seed_source_missing_sections(text)
        if not missing_sections:
            continue
        suggested_sections = _suggested_hint_sections(frontmatter)
        written = False
        if write:
            written = _write_missing_sections(path, text, missing_sections, suggested_sections)
            write_count += int(written)
        candidates.append(
            {
                "page": relative_path,
                "stem": stem,
                "missing_sections": missing_sections,
                "all_inbound_linkers": inbound_linkers,
                "suggested_sections": suggested_sections,
                "written": written,
            }
        )

    missing_count = len(candidates)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_intake_seed_source_hints_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/registry/raw_intake_seed_source_hints.py",
                "ops/scripts/eval/wiki_stage2_runtime.py",
            ],
            path_group_inputs={
                "pages": sorted(report_path(vault, path) for path in snapshot.pages.values()),
            },
            text_inputs={"write": str(write).lower()},
        ),
        "vault": report_path(vault, vault),
        "mode": "write" if write else "check",
        "status": "pass" if (missing_count == 0 or write) else "fail",
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "summary": {
            "seed_source_missing_hint_count": missing_count,
            "written_count": write_count,
        },
        "candidates": candidates,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw intake seed source hints report schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check or backfill source-only seed absorption hint sections.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fail-on-missing", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, write=args.write)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.fail_on_missing and report["summary"]["seed_source_missing_hint_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
