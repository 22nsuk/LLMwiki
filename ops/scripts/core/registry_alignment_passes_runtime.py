from __future__ import annotations

from pathlib import Path

from .frontmatter_runtime import validate_source_frontmatter_against_registry
from .policy_runtime import report_path
from .registry_diagnostics_runtime import (
    RegistryDiagnosticEmitter as RegistryLintEmitter,
)
from .registry_diagnostics_runtime import (
    RegistryInventoryContext,
)
from .registry_diagnostics_runtime import (
    RegistryPaths as RegistryLintPaths,
)


def _registry_frontmatter_alignment_pass(
    vault: Path,
    *,
    pages: dict[str, Path],
    frontmatters: dict[str, dict | None],
    frontmatter_contract: dict,
    inventory_context: RegistryInventoryContext,
    emitter: RegistryLintEmitter,
) -> None:
    for stem, path in pages.items():
        relative_path = report_path(vault, path)
        if not (
            relative_path.startswith("wiki/source--")
            or relative_path.startswith("system/source--")
        ):
            continue
        frontmatter = frontmatters.get(stem)
        if frontmatter is None:
            continue
        registry_id = frontmatter.get("registry_id")
        if not isinstance(registry_id, str):
            continue
        registry_entry = inventory_context.registry_id_to_entry.get(registry_id)
        if registry_entry is None:
            emitter.issue(
                {
                    "type": "source_frontmatter_registry_missing_entry",
                    "page": report_path(vault, path),
                    "detail": {
                        "registry_id": registry_id,
                        "expected_target_page": stem,
                    },
                },
                "source_frontmatter_registry_missing_entry",
            )
            continue
        for metadata_issue in validate_source_frontmatter_against_registry(
            stem,
            frontmatter,
            registry_entry,
            frontmatter_contract,
        ):
            emitter.issue(
                {
                    "type": metadata_issue["type"],
                    "page": report_path(vault, path),
                    "detail": metadata_issue["detail"],
                },
                metadata_issue["type"],
            )


def _locator_raw_path_corpus_consistency_pass(
    vault: Path,
    paths: RegistryLintPaths,
    *,
    inventory_context: RegistryInventoryContext,
    emitter: RegistryLintEmitter,
) -> None:
    for entry in inventory_context.registry_entries:
        entry_page = entry.get("_registry_page", paths.raw_registry_path.as_posix())
        entry_page_report = report_path(vault, Path(entry_page))
        missing_fields = [
            field
            for field in ("storage_path", "display_path", "type", "target_page", "status", "corpus")
            if field not in entry
        ]
        if missing_fields:
            continue

        corpus = entry["corpus"]
        storage_path = entry["storage_path"]
        source_type = entry["type"]
        target_page = entry["target_page"]
        status = entry["status"]
        root_name = inventory_context.corpus_roots.get(corpus)
        expected_corpus = inventory_context.type_to_corpus.get(
            source_type,
            inventory_context.default_corpus,
        )
        if corpus != expected_corpus:
            emitter.issue(
                {
                    "type": "corpus_routing_mismatch",
                    "page": entry_page_report,
                    "detail": {
                        "registry_id": entry.get("registry_id"),
                        "storage_path": storage_path,
                        "type": source_type,
                        "corpus": corpus,
                        "expected_corpus": expected_corpus,
                    },
                },
                "corpus_routing_mismatch",
            )
        if root_name is None:
            emitter.issue(
                {
                    "type": "corpus_target_mismatch",
                    "page": entry_page_report,
                    "detail": {
                        "registry_id": entry.get("registry_id"),
                        "corpus": corpus,
                        "target_page": target_page,
                        "reason": "unknown_corpus",
                    },
                },
                "corpus_target_mismatch",
            )
            continue

        if status == "ingested":
            expected_page = vault / root_name / f"{target_page}.md"
            if not expected_page.exists():
                emitter.issue(
                    {
                        "type": "corpus_target_mismatch",
                        "page": entry_page_report,
                        "detail": {
                            "registry_id": entry.get("registry_id"),
                            "corpus": corpus,
                            "target_page": target_page,
                            "expected_path": report_path(vault, expected_page),
                        },
                    },
                    "corpus_target_mismatch",
                )
        elif status == "registered-not-ingested" and corpus == "wiki":
            emitter.issue(
                {
                    "type": "pending_wiki_ingest",
                    "page": entry_page_report,
                    "detail": {
                        "registry_id": entry.get("registry_id"),
                        "storage_path": storage_path,
                        "target_page": target_page,
                    },
                },
                "pending_wiki_ingest",
            )


registry_frontmatter_alignment_pass = _registry_frontmatter_alignment_pass
locator_raw_path_corpus_consistency_pass = _locator_raw_path_corpus_consistency_pass


__all__ = [
    "_registry_frontmatter_alignment_pass",
    "_locator_raw_path_corpus_consistency_pass",
    "registry_frontmatter_alignment_pass",
    "locator_raw_path_corpus_consistency_pass",
]
