#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter
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
    from ops.scripts.core.frontmatter_runtime import parse_frontmatter
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.source_page_substance_runtime import (
        evaluate_source_page_substance,
    )
    from ops.scripts.eval.wiki_quality_runtime import resolved_wikilink_targets
    from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.frontmatter_runtime import parse_frontmatter
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.source_page_substance_runtime import (
        evaluate_source_page_substance,
    )
    from ops.scripts.eval.wiki_quality_runtime import resolved_wikilink_targets
    from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot

DEFAULT_OUT = "ops/reports/source-substance-cohort-classification.json"
SCHEMA_PATH = "ops/schemas/source-substance-cohort-classification.schema.json"
PRODUCER = "ops.scripts.registry.source_substance_cohort_classify"
SOURCE_COMMAND = (
    "python -m ops.scripts.registry.source_substance_cohort_classify --vault ."
)
FILENAME_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})\.md$")
TEXT_RAW_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".text", ".rst"})
REMEDIATION_ROUTES = (
    "no_action",
    "recover_from_text_raw",
    "recover_from_pdf_raw",
    "retained_operator_review",
    "operator_review",
)


def _source_pages(vault: Path) -> list[tuple[str, Path]]:
    pages: list[tuple[str, Path]] = []
    for corpus in ("wiki", "system"):
        root = vault / corpus
        if root.is_dir():
            pages.extend((corpus, path) for path in root.rglob("source--*.md"))
    return sorted(pages, key=lambda item: report_path(vault, item[1]))


def _synthesis_pages(vault: Path) -> list[Path]:
    pages: list[Path] = []
    for corpus in ("wiki", "system"):
        root = vault / corpus
        if root.is_dir():
            pages.extend(root.rglob("synthesis--*.md"))
    return sorted(pages, key=lambda path: report_path(vault, path))


def _frontmatter_text(frontmatter: dict[str, Any] | None, field: str) -> str | None:
    if not isinstance(frontmatter, dict):
        return None
    value = frontmatter.get(field)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _filename_date(path: Path) -> str | None:
    match = FILENAME_DATE_RE.search(path.name)
    return match.group(1) if match else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_source_raw_path(
    vault: Path, raw_path_value: Any
) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path_value, str) or not raw_path_value.strip():
        return None, "raw_path_missing_frontmatter"
    relative = Path(raw_path_value.strip())
    if relative.is_absolute():
        return None, "raw_path_outside_vault"
    vault_root = vault.resolve()
    resolved = (vault_root / relative).resolve()
    if not resolved.is_relative_to(vault_root):
        return None, "raw_path_outside_vault"
    if not resolved.is_file():
        return None, "raw_path_not_file"
    return resolved, None


def _raw_metadata(path: Path | None) -> tuple[bool, str, str | None]:
    if path is None:
        return False, "missing", None
    resolved = path
    suffix = resolved.suffix.lower()
    if suffix in TEXT_RAW_SUFFIXES:
        return True, "text", _sha256_file(resolved)
    if suffix == ".pdf":
        return True, "pdf", _sha256_file(resolved)
    return True, "other", _sha256_file(resolved)


def _synthesis_linkage(
    *,
    vault: Path,
    source_stem: str,
    source_text: str,
    page_lookup: dict[str, str],
    synthesis_by_stem: dict[str, list[Path]],
    inverse_targets: dict[Path, set[str]],
) -> dict[str, Any]:
    direct_stems = {
        stem
        for stem in resolved_wikilink_targets(source_text, page_lookup)
        if stem.startswith("synthesis--")
    }
    direct_links = sorted(
        {
            report_path(vault, path)
            for stem in direct_stems
            for path in synthesis_by_stem.get(stem, [])
        }
    )
    inverse_links = sorted(
        report_path(vault, path)
        for path, targets in inverse_targets.items()
        if source_stem in targets
    )
    linked_pages = set(direct_links) | set(inverse_links)
    return {
        "linked": bool(linked_pages),
        "linkage_count": len(linked_pages),
        "direct_links": direct_links,
        "inverse_links": inverse_links,
    }


def _remediation_route(
    *,
    substance_pass: bool,
    linked: bool,
    raw_exists: bool,
    raw_media_class: str,
) -> str:
    if substance_pass:
        return "no_action"
    if not raw_exists or raw_media_class == "other":
        return "operator_review"
    if not linked:
        return "retained_operator_review"
    if raw_media_class == "text":
        return "recover_from_text_raw"
    if raw_media_class == "pdf":
        return "recover_from_pdf_raw"
    return "operator_review"


def build_report(
    vault: Path, *, context: RuntimeContext | None = None
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    snapshot = build_wiki_runtime_snapshot(vault)
    source_pages = _source_pages(vault)
    synthesis_pages = _synthesis_pages(vault)
    synthesis_by_stem: dict[str, list[Path]] = {}
    inverse_targets: dict[Path, set[str]] = {}
    for path in synthesis_pages:
        synthesis_by_stem.setdefault(path.stem, []).append(path)
        inverse_targets[path] = resolved_wikilink_targets(
            path.read_text(encoding="utf-8"), snapshot.page_lookup
        )

    entries: list[dict[str, Any]] = []
    route_counts: Counter[str] = Counter()
    failing_by_corpus: Counter[str] = Counter()
    failure_reason_counts: Counter[str] = Counter()
    passing_count = 0

    for corpus, path in source_pages:
        text = path.read_text(encoding="utf-8")
        try:
            frontmatter = parse_frontmatter(text)
        except ValueError:
            frontmatter = None
        substance = evaluate_source_page_substance(text)
        substance_pass = bool(substance.get("pass"))
        linkage = _synthesis_linkage(
            vault=vault,
            source_stem=path.stem,
            source_text=text,
            page_lookup=snapshot.page_lookup,
            synthesis_by_stem=synthesis_by_stem,
            inverse_targets=inverse_targets,
        )
        raw_path_value = _frontmatter_text(frontmatter, "raw_path")
        resolved_raw_path, _ = resolve_source_raw_path(vault, raw_path_value)
        raw_path = (
            resolved_raw_path.relative_to(vault.resolve()).as_posix()
            if resolved_raw_path is not None
            else None
        )
        raw_exists, raw_media_class, raw_sha256 = _raw_metadata(resolved_raw_path)
        remediation_route = _remediation_route(
            substance_pass=substance_pass,
            linked=bool(linkage["linked"]),
            raw_exists=raw_exists,
            raw_media_class=raw_media_class,
        )
        route_counts[remediation_route] += 1
        if substance_pass:
            passing_count += 1
        else:
            failing_by_corpus[corpus] += 1
            failure_reason_counts.update(
                str(reason) for reason in substance.get("failures", [])
            )
        entries.append(
            {
                "page": report_path(vault, path),
                "page_sha256": _sha256_file(path),
                "corpus": corpus,
                "registry_id": _frontmatter_text(frontmatter, "registry_id"),
                "created": _frontmatter_text(frontmatter, "created"),
                "filename_date": _filename_date(path),
                "ingest_cohort": None,
                "substance_pass": substance_pass,
                "substance_failure_reasons": list(substance.get("failures", [])),
                "substance_metrics": dict(substance.get("metrics", {})),
                "raw_path": raw_path,
                "raw_exists": raw_exists,
                "raw_media_class": raw_media_class,
                "raw_sha256": raw_sha256,
                "route_decision": _frontmatter_text(frontmatter, "route_decision"),
                "synthesis_linkage": linkage,
                "remediation_route": remediation_route,
            }
        )

    total_source_count = len(entries)
    failing_count = total_source_count - passing_count
    generated_at = runtime_context.isoformat_z()
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="source_substance_cohort_classification",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=[
            "ops/scripts/registry/source_substance_cohort_classify.py",
            "ops/scripts/eval/source_page_substance_runtime.py",
        ],
        path_group_inputs={
            "source_pages": [report_path(vault, path) for _, path in source_pages],
            "synthesis_pages": [report_path(vault, path) for path in synthesis_pages],
        },
    )
    envelope["schema_version"] = 2
    return {
        **envelope,
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "attention" if failing_count else "pass",
        "summary": {
            "total_source_count": total_source_count,
            "passing_count": passing_count,
            "failing_count": failing_count,
            "remediation_route_counts": {
                route: route_counts[route] for route in REMEDIATION_ROUTES
            },
            "failing_by_corpus": {
                "wiki": failing_by_corpus["wiki"],
                "system": failing_by_corpus["system"],
            },
            "failure_reason_counts": dict(sorted(failure_reason_counts.items())),
        },
        "entries": entries,
    }


def write_report(
    vault: Path, report: dict[str, Any], out_path: str | None = None
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="source substance cohort classification schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify all wiki and system source pages by current substance and recovery evidence."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
