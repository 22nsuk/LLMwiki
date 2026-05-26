from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ops.scripts.raw_registry_runtime import (
    build_raw_sha256_index,
    build_registry_locator_groups,
    enrich_registry_entries_with_inventory,
    entry_existing_registered_paths,
    load_exported_registry_enrichment,
    parse_raw_registry_pages,
    parse_raw_registry_summary_counts,
    registry_entry_page_corpus_map,
    registry_entry_page_paths,
    registry_inventory_resolution_stats,
    registry_summary_page_path,
)

from .policy_runtime import report_path
from .registry_exceptions_runtime import (
    RawRegistryRuntimeError,
    raw_registry_exception_detail,
)
from .source_page_naming_runtime import source_slug_validation_detail


def _add_issue(issue: dict, severity: str, errors: list, warnings: list) -> None:
    if severity == "fail":
        errors.append(issue)
        return
    if severity == "warn":
        warnings.append(issue)
        return
    raise ValueError(f"unsupported lint severity: {severity}")


@dataclass
class RegistryDiagnosticEmitter:
    lint_thresholds: dict
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    review_candidates: list[dict] = field(default_factory=list)

    def issue(self, issue: dict, threshold_key: str) -> None:
        _add_issue(
            issue,
            self.lint_thresholds[threshold_key],
            self.errors,
            self.warnings,
        )

    def review_candidate(self, candidate: dict) -> None:
        self.review_candidates.append(candidate)


@dataclass(frozen=True)
class RegistryPaths:
    raw_registry_path: Path
    raw_registry_entry_pages: list[Path]


@dataclass
class RegistryInventoryContext:
    registry_entries: list[dict]
    registered_raw_paths: set[str]
    entries_by_page: dict[str, list[dict]]
    corpus_counts: dict[str, int]
    total_entry_count: int
    shard_corpus_by_page: dict[str, str]
    registry_id_to_entries: dict[str, list[dict]]
    registry_id_to_entry: dict[str, dict]
    locator_groups: dict[str, list[dict]]
    raw_sha256_index: dict | None
    resolution_stats: dict
    corpus_roots: dict[str, str]
    type_to_corpus: dict[str, str]
    default_corpus: str
    route_overrides: dict


def registry_diagnostic_paths(vault: Path, registry_contract: dict) -> RegistryPaths:
    return RegistryPaths(
        raw_registry_path=registry_summary_page_path(vault, registry_contract),
        raw_registry_entry_pages=registry_entry_page_paths(vault, registry_contract),
    )


def registry_page_presence_pass(
    vault: Path,
    paths: RegistryPaths,
    *,
    registry_contract: dict,
    emitter: RegistryDiagnosticEmitter,
    summary_detail_mode: str = "contract",
) -> bool:
    if not paths.raw_registry_path.exists():
        detail = (
            registry_contract["raw_registry_page"]
            if summary_detail_mode == "contract"
            else report_path(vault, paths.raw_registry_path)
        )
        emitter.issue(
            {
                "type": "missing_raw_registry_page",
                "page": report_path(vault, paths.raw_registry_path),
                "detail": detail,
            },
            "missing_raw_registry_page",
        )

    for entry_page in paths.raw_registry_entry_pages:
        if entry_page.exists():
            continue
        emitter.issue(
            {
                "type": "missing_raw_registry_shard_page",
                "page": report_path(vault, entry_page),
                "detail": report_path(vault, entry_page),
            },
            "missing_raw_registry_shard_page",
        )

    return paths.raw_registry_path.exists() and all(
        page.exists() for page in paths.raw_registry_entry_pages
    )


def registry_inventory_context_pass(
    vault: Path,
    paths: RegistryPaths,
    *,
    registry_contract: dict,
    corpus_routing: dict,
    emitter: RegistryDiagnosticEmitter,
) -> RegistryInventoryContext | None:
    try:
        export_path = vault / registry_contract["raw_registry_export"]
        parsed_registry_entries = parse_raw_registry_pages(paths.raw_registry_entry_pages)
        exported_enrichment = load_exported_registry_enrichment(export_path)
        registry_entries = enrich_registry_entries_with_inventory(
            vault,
            parsed_registry_entries,
            exported_enrichment=exported_enrichment,
        )
        resolution_stats = registry_inventory_resolution_stats(
            vault,
            parsed_registry_entries,
            exported_enrichment=exported_enrichment,
        )
    except RawRegistryRuntimeError as exc:
        emitter.issue(
            {
                "type": "raw_registry_parse_error",
                "page": report_path(vault, paths.raw_registry_path),
                "detail": raw_registry_exception_detail(exc),
            },
            "raw_registry_parse_error",
        )
        return None

    entries_by_page: dict[str, list[dict]] = defaultdict(list)
    for entry in registry_entries:
        entries_by_page[entry.get("_registry_page", paths.raw_registry_path.as_posix())].append(entry)

    corpus_counts: dict[str, int] = {}
    for entry in registry_entries:
        corpus = entry.get("corpus")
        if corpus is None:
            continue
        corpus_counts[corpus] = corpus_counts.get(corpus, 0) + 1

    registry_id_to_entries: dict[str, list[dict]] = {}
    registry_id_to_entry: dict[str, dict] = {}
    for entry in registry_entries:
        registry_id = entry.get("registry_id")
        if registry_id:
            registry_id_to_entries.setdefault(registry_id, []).append(entry)
            registry_id_to_entry.setdefault(registry_id, entry)

    locator_groups = build_registry_locator_groups(registry_entries)
    return RegistryInventoryContext(
        registry_entries=registry_entries,
        registered_raw_paths=set(locator_groups),
        entries_by_page=entries_by_page,
        corpus_counts=corpus_counts,
        total_entry_count=len(registry_entries),
        shard_corpus_by_page=registry_entry_page_corpus_map(vault, registry_contract),
        registry_id_to_entries=registry_id_to_entries,
        registry_id_to_entry=registry_id_to_entry,
        locator_groups=locator_groups,
        raw_sha256_index=build_raw_sha256_index(vault) if registry_entries else None,
        resolution_stats=resolution_stats,
        corpus_roots=registry_contract.get("corpus_roots", {}),
        type_to_corpus=corpus_routing.get("type_to_corpus", {}),
        default_corpus=corpus_routing.get("default_corpus", "system"),
        route_overrides=corpus_routing.get("route_overrides", {}),
    )


def registry_summary_consistency_pass(
    vault: Path,
    paths: RegistryPaths,
    *,
    context: RegistryInventoryContext,
    emitter: RegistryDiagnosticEmitter,
) -> None:
    try:
        summary_counts = parse_raw_registry_summary_counts(paths.raw_registry_path)
    except RawRegistryRuntimeError as exc:
        emitter.issue(
            {
                "type": "raw_registry_parse_error",
                "page": report_path(vault, paths.raw_registry_path),
                "detail": raw_registry_exception_detail(exc),
            },
            "raw_registry_parse_error",
        )
        return
    expected_summary_counts = {
        "total registered paths": context.total_entry_count,
        "system corpus entries": context.corpus_counts.get("system", 0),
        "wiki corpus entries": context.corpus_counts.get("wiki", 0),
        "ingested": sum(
            1 for entry in context.registry_entries if entry.get("status") == "ingested"
        ),
        "registered-not-ingested": sum(
            1
            for entry in context.registry_entries
            if entry.get("status") == "registered-not-ingested"
        ),
    }
    mismatches = {}
    for label, expected_value in expected_summary_counts.items():
        actual_value = summary_counts.get(label)
        if actual_value != expected_value:
            mismatches[label] = {
                "expected": expected_value,
                "actual": actual_value,
            }
    if mismatches:
        emitter.issue(
            {
                "type": "raw_registry_summary_mismatch",
                "page": report_path(vault, paths.raw_registry_path),
                "detail": mismatches,
            },
            "raw_registry_summary_mismatch",
        )


def registry_shared_inventory_diagnostics_pass(
    vault: Path,
    paths: RegistryPaths,
    *,
    context: RegistryInventoryContext,
    emitter: RegistryDiagnosticEmitter,
    registered_raw_path_detail_key: str = "path",
) -> None:
    for registry_id, grouped_entries in sorted(context.registry_id_to_entries.items()):
        if len(grouped_entries) < 2:
            continue
        emitter.issue(
            {
                "type": "duplicate_registry_id",
                "page": report_path(vault, paths.raw_registry_path),
                "detail": {
                    "registry_id": registry_id,
                    "count": len(grouped_entries),
                    "paths": [entry.get("storage_path") for entry in grouped_entries],
                },
            },
            "duplicate_registry_id",
        )

    for raw_path, grouped_entries in sorted(context.locator_groups.items()):
        if len(grouped_entries) < 2:
            continue
        emitter.issue(
            {
                "type": "duplicate_registered_raw_path",
                "page": report_path(vault, paths.raw_registry_path),
                "detail": {
                    registered_raw_path_detail_key: raw_path,
                    "count": len(grouped_entries),
                    "registry_ids": [entry.get("registry_id") for entry in grouped_entries],
                },
            },
            "duplicate_registered_raw_path",
        )

    for entry in context.registry_entries:
        entry_page = entry.get("_registry_page", paths.raw_registry_path.as_posix())
        entry_page_report = report_path(vault, Path(entry_page))
        missing_fields = [
            field
            for field in ("storage_path", "display_path", "type", "target_page", "status", "corpus")
            if field not in entry
        ]
        if missing_fields:
            emitter.issue(
                {
                    "type": "missing_registry_field",
                    "page": entry_page_report,
                    "detail": {
                        "registry_id": entry.get("registry_id"),
                        "missing_fields": missing_fields,
                    },
                },
                "missing_registry_field",
            )
            continue

        expected_shard_corpus = context.shard_corpus_by_page.get(entry_page)
        if expected_shard_corpus is not None and entry["corpus"] != expected_shard_corpus:
            emitter.issue(
                {
                    "type": "registry_shard_corpus_mismatch",
                    "page": entry_page_report,
                    "detail": {
                        "registry_id": entry.get("registry_id"),
                        "storage_path": entry["storage_path"],
                        "corpus": entry["corpus"],
                        "expected_corpus": expected_shard_corpus,
                    },
                },
                "registry_shard_corpus_mismatch",
            )


def registry_raw_inventory_consistency_pass(
    vault: Path,
    paths: RegistryPaths,
    *,
    context: RegistryInventoryContext,
    emitter: RegistryDiagnosticEmitter,
) -> None:
    resolved_inventory_paths: set[str] = set()
    for entry in context.registry_entries:
        resolved_paths = entry_existing_registered_paths(vault, entry, context.raw_sha256_index)
        if resolved_paths:
            resolved_inventory_paths.update(resolved_paths)
            continue
        entry_page = entry.get("_registry_page", paths.raw_registry_path.as_posix())
        emitter.issue(
            {
                "type": "raw_path_mismatch",
                "page": report_path(vault, Path(entry_page)),
                "detail": {
                    "storage_path": entry.get("storage_path"),
                    "path_aliases": entry.get("path_aliases", []),
                    "content_sha256": entry.get("content_sha256"),
                },
            },
            "raw_path_mismatch",
        )

    raw_root = vault / "raw"
    if not raw_root.exists():
        return
    for raw_file in sorted(raw_root.rglob("*")):
        if not raw_file.is_file():
            continue
        rel_path = raw_file.relative_to(vault).as_posix()
        if rel_path in context.registered_raw_paths or rel_path in resolved_inventory_paths:
            continue
        emitter.issue(
            {
                "type": "unregistered_raw_file",
                "page": report_path(vault, raw_file),
                "detail": rel_path,
            },
            "unregistered_raw_file",
        )


def registry_source_target_page_naming_pass(
    vault: Path,
    paths: RegistryPaths,
    *,
    context: RegistryInventoryContext,
    source_page_slug_review: dict,
    emitter: RegistryDiagnosticEmitter,
) -> None:
    for entry in context.registry_entries:
        target_page = entry.get("target_page")
        if not isinstance(target_page, str) or not target_page.startswith("source--"):
            continue
        detail = source_slug_validation_detail(target_page, source_page_slug_review)
        if detail is None:
            continue
        entry_page = entry.get("_registry_page", paths.raw_registry_path.as_posix())
        emitter.issue(
            {
                "type": "noncanonical_source_target_page",
                "page": report_path(vault, Path(entry_page)),
                "detail": {
                    "registry_id": entry.get("registry_id"),
                    "target_page": target_page,
                    **detail,
                },
            },
            "noncanonical_source_target_page",
        )
