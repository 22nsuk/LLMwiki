from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ops.scripts.core.path_portability_runtime import infozip_c_locale_escape_path
from ops.scripts.core.path_runtime import normalize_repo_path_text
from ops.scripts.core.registry_exceptions_runtime import (
    RawRegistryEntryNoFieldsError,
    RawRegistryExportInvalidJsonError,
    RawRegistryExportReadError,
    RawRegistryExportShapeError,
    RawRegistryInvalidContinuationLineError,
    RawRegistryInvalidFieldLineError,
    RawRegistryInvalidPathAliasesError,
    RawRegistryLegacyCompactEntryError,
    RawRegistryPageReadError,
    RawRegistryRawFileReadError,
    RawRegistryRuntimeError,
    RawRegistryYamlParseError,
    raw_registry_exception_detail,
)
from ops.scripts.core.yaml_runtime import parse_simple_yaml

ENTRY_ID_RE = re.compile(r"^####\s+([A-Z]-\d+(?:-[A-Z]-\d+)?)\s*$")
FIELD_LINE_RE = re.compile(r"^- ([^:]+):\s*(.*)$")
SUMMARY_COUNT_RE = re.compile(r"^- ([^:]+):\s*`?(\d+)`?\s*$")
PATH_ALIAS_RESOLUTION_MODE = (
    "canonical_storage_path_then_manual_exported_environment_aliases_then_unique_content_sha256"
)
ALIAS_POLICY_VERSION = "raw_registry_alias_resolution_v1"


def normalize_field(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "*":
        return value[1:-1]
    return value


def append_entry(entries: list[dict], current_entry: dict | None) -> None:
    if current_entry is None:
        return
    if len(current_entry) == 1 and "registry_id" in current_entry:
        raise RawRegistryEntryNoFieldsError(current_entry["registry_id"])
    entries.append(current_entry)


def _field_key(raw_key: str) -> str:
    return raw_key.strip().lower().replace(" ", "_")


def _field_fragment(line: str) -> str:
    match = FIELD_LINE_RE.match(line)
    if not match:
        raise RawRegistryInvalidFieldLineError("(unknown)", line)

    key, value = match.groups()
    normalized_key = _field_key(key)
    stripped_value = value.strip()
    if stripped_value == "":
        return f"{normalized_key}:"
    if stripped_value in {"|", ">"}:
        return f"{normalized_key}: {stripped_value}"
    return f"{normalized_key}: {json.dumps(normalize_field(stripped_value), ensure_ascii=False)}"


def normalize_registry_locator(value: str | None) -> str | None:
    return normalize_repo_path_text(value)


def normalize_display_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().replace("\\", "/")
    return normalized or None


def normalize_content_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def registry_entry_path_aliases(entry: dict) -> list[str]:
    raw_aliases = entry.get("path_aliases")
    if raw_aliases is None:
        return []
    if isinstance(raw_aliases, str):
        normalized = normalize_registry_locator(raw_aliases)
        return [normalized] if normalized else []
    if not isinstance(raw_aliases, list):
        raise RawRegistryInvalidPathAliasesError()

    aliases: list[str] = []
    seen: set[str] = set()
    for item in raw_aliases:
        normalized = normalize_registry_locator(str(item))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(normalized)
    return aliases


def registry_entry_locators(entry: dict) -> list[str]:
    locators: list[str] = []
    seen: set[str] = set()
    for candidate in [entry.get("storage_path"), *registry_entry_path_aliases(entry)]:
        normalized = normalize_registry_locator(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        locators.append(normalized)
    return locators


def _environment_locator_aliases(canonical_storage_path: str | None) -> list[str]:
    if canonical_storage_path is None:
        return []
    escaped_locator = normalize_registry_locator(
        infozip_c_locale_escape_path(canonical_storage_path)
    )
    if not escaped_locator or escaped_locator == canonical_storage_path:
        return []
    return [escaped_locator]


def build_registry_locator_groups(entries: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        for locator in registry_entry_locators(entry):
            groups.setdefault(locator, []).append(entry)
    return groups


def build_registry_source_trace_resolution_map(entries: list[dict]) -> dict[str, list[str]]:
    locator_groups = build_registry_locator_groups(entries)
    resolution_map: dict[str, list[str]] = {}
    for locator, grouped_entries in locator_groups.items():
        if len(grouped_entries) != 1:
            continue
        locators = registry_entry_locators(grouped_entries[0])
        resolution_map[locator] = [locator] + [candidate for candidate in locators if candidate != locator]
    return resolution_map


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RawRegistryRawFileReadError(path, str(exc)) from exc
    return digest.hexdigest()


def build_raw_sha256_index(vault: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    raw_root = vault / "raw"
    if not raw_root.exists():
        return index
    for raw_file in sorted(raw_root.rglob("*")):
        if not raw_file.is_file():
            continue
        digest = file_sha256(raw_file)
        index.setdefault(digest, []).append(raw_file.relative_to(vault).as_posix())
    return index


def load_exported_registry_enrichment(export_path: Path) -> dict[tuple[str, str], dict]:
    enrichment, _ = load_exported_registry_enrichment_state(export_path)
    return enrichment


def load_exported_registry_enrichment_state(
    export_path: Path,
) -> tuple[dict[tuple[str, str], dict], list[dict]]:
    if not export_path.exists():
        return {}, []
    try:
        data = json.loads(export_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        json_error = RawRegistryExportInvalidJsonError(export_path, exc.msg)
        return (
            {},
            [
                {
                    "type": "raw_registry_export_enrichment_load_failed",
                    "path": export_path.as_posix(),
                    "detail": str(json_error),
                    "diagnostic_type": json_error.diagnostic_type,
                }
            ],
        )
    except (OSError, UnicodeError) as exc:
        read_error = RawRegistryExportReadError(export_path, str(exc))
        return (
            {},
            [
                {
                    "type": "raw_registry_export_enrichment_load_failed",
                    "path": export_path.as_posix(),
                    "detail": str(read_error),
                    "diagnostic_type": read_error.diagnostic_type,
                }
            ],
        )

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        shape_error = RawRegistryExportShapeError(export_path, "export missing entries list")
        return (
            {},
            [
                {
                    "type": "raw_registry_export_enrichment_load_failed",
                    "path": export_path.as_posix(),
                    "detail": str(shape_error),
                    "diagnostic_type": shape_error.diagnostic_type,
                }
            ],
        )

    enrichment: dict[tuple[str, str], dict] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        registry_id = raw_entry.get("registry_id")
        storage_path = normalize_registry_locator(raw_entry.get("storage_path"))
        if not registry_id or not storage_path:
            continue

        entry_enrichment: dict[str, object] = {}
        aliases = registry_entry_path_aliases(raw_entry)
        if aliases:
            entry_enrichment["path_aliases"] = aliases
        content_sha256 = normalize_content_sha256(raw_entry.get("content_sha256"))
        if content_sha256:
            entry_enrichment["content_sha256"] = content_sha256
        if entry_enrichment:
            enrichment[(str(registry_id), storage_path)] = entry_enrichment

    return enrichment, []


def _path_to_digest(raw_sha256_index: dict[str, list[str]]) -> dict[str, str]:
    return {
        path: digest
        for digest, paths in raw_sha256_index.items()
        for path in paths
    }


def _exported_entry_enrichment(
    *,
    exported_enrichment: dict[tuple[str, str], dict] | None,
    registry_id: object,
    canonical_storage_path: str | None,
) -> dict:
    if not registry_id or not canonical_storage_path or exported_enrichment is None:
        return {}
    return exported_enrichment.get((str(registry_id), canonical_storage_path), {})


def _locator_candidates(
    canonical_storage_path: str | None,
    manual_aliases: list[str],
    exported_aliases: list[str],
    environment_aliases: list[str],
) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for locator in [
        canonical_storage_path,
        *manual_aliases,
        *exported_aliases,
        *environment_aliases,
    ]:
        normalized = normalize_registry_locator(locator)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
    return candidates


def _existing_paths(vault: Path, locator_candidates: list[str]) -> list[str]:
    existing_paths: list[str] = []
    seen: set[str] = set()
    for locator in locator_candidates:
        if not (vault / locator).exists() or locator in seen:
            continue
        seen.add(locator)
        existing_paths.append(locator)
    return existing_paths


def _entry_content_sha256(
    *,
    enriched_entry: dict,
    exported_entry_enrichment: dict,
    canonical_storage_path: str | None,
    existing_paths: list[str],
    path_to_digest: dict[str, str],
) -> str | None:
    digest_source_path = None
    if canonical_storage_path and canonical_storage_path in path_to_digest:
        digest_source_path = canonical_storage_path
    elif existing_paths:
        digest_source_path = existing_paths[0]
    if digest_source_path is not None:
        return path_to_digest.get(digest_source_path)

    content_sha256 = normalize_content_sha256(enriched_entry.get("content_sha256"))
    if content_sha256 is None:
        content_sha256 = normalize_content_sha256(exported_entry_enrichment.get("content_sha256"))
    return content_sha256


def _derived_aliases(
    *,
    raw_sha256_index: dict[str, list[str]],
    content_sha256: str | None,
    canonical_storage_path: str | None,
) -> list[str]:
    if content_sha256 is None:
        return []
    return [
        matched_path
        for matched_path in raw_sha256_index.get(content_sha256, [])
        if matched_path != canonical_storage_path
    ]


def _merged_aliases(
    *,
    canonical_storage_path: str | None,
    manual_aliases: list[str],
    exported_aliases: list[str],
    derived_aliases: list[str],
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for candidate in [*manual_aliases, *exported_aliases, *derived_aliases]:
        normalized = normalize_registry_locator(candidate)
        if not normalized or normalized == canonical_storage_path or normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(normalized)
    return aliases


def enrich_registry_entries_with_inventory(
    vault: Path,
    entries: list[dict],
    exported_enrichment: dict[tuple[str, str], dict] | None = None,
) -> list[dict]:
    raw_sha256_index = build_raw_sha256_index(vault)
    path_to_digest = _path_to_digest(raw_sha256_index)

    enriched_entries: list[dict] = []
    for entry in entries:
        enriched_entry = dict(entry)
        canonical_storage_path = normalize_registry_locator(enriched_entry.get("storage_path"))
        if canonical_storage_path is not None:
            enriched_entry["storage_path"] = canonical_storage_path

        registry_id = enriched_entry.get("registry_id")
        exported_entry_enrichment = _exported_entry_enrichment(
            exported_enrichment=exported_enrichment,
            registry_id=registry_id,
            canonical_storage_path=canonical_storage_path,
        )
        manual_aliases = registry_entry_path_aliases(enriched_entry)
        exported_aliases = registry_entry_path_aliases(exported_entry_enrichment)
        environment_aliases = _environment_locator_aliases(canonical_storage_path)
        existing_paths = _existing_paths(
            vault,
            _locator_candidates(
                canonical_storage_path,
                manual_aliases,
                exported_aliases,
                environment_aliases,
            ),
        )
        content_sha256 = _entry_content_sha256(
            enriched_entry=enriched_entry,
            exported_entry_enrichment=exported_entry_enrichment,
            canonical_storage_path=canonical_storage_path,
            existing_paths=existing_paths,
            path_to_digest=path_to_digest,
        )
        if content_sha256 is not None:
            enriched_entry["content_sha256"] = content_sha256

        aliases = _merged_aliases(
            canonical_storage_path=canonical_storage_path,
            manual_aliases=manual_aliases,
            exported_aliases=exported_aliases,
            derived_aliases=[
                *existing_paths,
                *_derived_aliases(
                    raw_sha256_index=raw_sha256_index,
                    content_sha256=content_sha256,
                    canonical_storage_path=canonical_storage_path,
                ),
            ],
        )
        if aliases:
            enriched_entry["path_aliases"] = aliases
        else:
            enriched_entry.pop("path_aliases", None)

        enriched_entries.append(enriched_entry)

    return enriched_entries


def entry_existing_registered_paths(
    vault: Path,
    entry: dict,
    raw_sha256_index: dict[str, list[str]] | None = None,
) -> list[str]:
    existing_paths: list[str] = []
    seen: set[str] = set()
    canonical_storage_path = normalize_registry_locator(entry.get("storage_path"))
    for locator in _locator_candidates(
        canonical_storage_path,
        registry_entry_path_aliases(entry),
        [],
        _environment_locator_aliases(canonical_storage_path),
    ):
        if (vault / locator).exists() and locator not in seen:
            seen.add(locator)
            existing_paths.append(locator)
    if existing_paths:
        return existing_paths

    digest = normalize_content_sha256(entry.get("content_sha256"))
    if not digest or raw_sha256_index is None:
        return []
    matches = raw_sha256_index.get(digest, [])
    if len(matches) == 1:
        return matches
    return []


def registry_inventory_resolution_stats(
    vault: Path,
    entries: list[dict],
    exported_enrichment: dict[tuple[str, str], dict] | None = None,
) -> dict[str, int | bool | str]:
    raw_sha256_index = build_raw_sha256_index(vault)
    path_to_digest = _path_to_digest(raw_sha256_index)
    path_alias_match_count = 0
    content_hash_fallback_count = 0

    for entry in entries:
        canonical_storage_path = normalize_registry_locator(entry.get("storage_path"))
        if canonical_storage_path is None:
            continue
        if (vault / canonical_storage_path).exists():
            continue

        exported_entry_enrichment = _exported_entry_enrichment(
            exported_enrichment=exported_enrichment,
            registry_id=entry.get("registry_id"),
            canonical_storage_path=canonical_storage_path,
        )
        manual_aliases = registry_entry_path_aliases(entry)
        exported_aliases = registry_entry_path_aliases(exported_entry_enrichment)
        environment_aliases = _environment_locator_aliases(canonical_storage_path)
        alias_candidates = _locator_candidates(
            None,
            manual_aliases,
            exported_aliases,
            environment_aliases,
        )
        existing_aliases = _existing_paths(vault, alias_candidates)
        if existing_aliases:
            path_alias_match_count += 1
            continue

        content_sha256 = _entry_content_sha256(
            enriched_entry=entry,
            exported_entry_enrichment=exported_entry_enrichment,
            canonical_storage_path=canonical_storage_path,
            existing_paths=[],
            path_to_digest=path_to_digest,
        )
        matches = raw_sha256_index.get(content_sha256, []) if content_sha256 is not None else []
        if len(matches) == 1 and matches[0] != canonical_storage_path:
            content_hash_fallback_count += 1

    return {
        "path_alias_match_count": path_alias_match_count,
        "content_hash_fallback_count": content_hash_fallback_count,
        "unsupported_environment": False,
    }


def parse_registry_entry_lines(registry_id: str, entry_lines: list[str]) -> dict:
    if not entry_lines:
        raise RawRegistryEntryNoFieldsError(registry_id)

    yaml_lines: list[str] = []
    for line in entry_lines:
        if not line.strip():
            yaml_lines.append("")
            continue
        if line.startswith("- "):
            if "; " in line:
                raise RawRegistryLegacyCompactEntryError(registry_id)
            try:
                yaml_lines.append(_field_fragment(line))
            except RawRegistryInvalidFieldLineError as exc:
                raise RawRegistryInvalidFieldLineError(registry_id, exc.line) from exc
            continue
        if not line.startswith("  "):
            raise RawRegistryInvalidContinuationLineError(registry_id, line)
        if line.startswith("  - "):
            yaml_lines.append(
                f"  - {json.dumps(normalize_field(line[4:].strip()), ensure_ascii=False)}"
            )
            continue
        yaml_lines.append(line)

    try:
        entry = parse_simple_yaml("\n".join(yaml_lines))
    except ValueError as exc:
        raise RawRegistryYamlParseError(registry_id, str(exc)) from exc
    if "storage_path" in entry:
        entry["storage_path"] = normalize_registry_locator(entry["storage_path"])
    if "display_path" in entry:
        entry["display_path"] = normalize_display_path(entry["display_path"])
    if "path_aliases" in entry:
        entry["path_aliases"] = registry_entry_path_aliases(entry)
    if "content_sha256" in entry:
        entry["content_sha256"] = normalize_content_sha256(entry["content_sha256"])
    entry["registry_id"] = registry_id
    return entry


def registry_summary_page_path(vault: Path, registry_contract: dict) -> Path:
    return vault / registry_contract["raw_registry_page"]


def registry_entry_page_paths(vault: Path, registry_contract: dict) -> list[Path]:
    return [
        vault / relative_path
        for relative_path in registry_contract.get("raw_registry_shard_pages", [])
    ]


def registry_entry_page_corpus_map(vault: Path, registry_contract: dict) -> dict[str, str]:
    explicit_map = registry_contract.get("raw_registry_entry_page_corpus", {})
    if explicit_map:
        return {
            (vault / relative_path).as_posix(): corpus
            for relative_path, corpus in explicit_map.items()
        }
    return {
        (vault / relative_path).as_posix(): corpus
        for corpus, relative_path in registry_contract.get("raw_registry_shard_by_corpus", {}).items()
    }


def load_registry_source_trace_resolution_state(vault: Path, registry_contract: dict) -> dict:
    entry_pages = registry_entry_page_paths(vault, registry_contract)
    if not entry_pages or not all(page.exists() for page in entry_pages):
        return {"resolution_map": {}, "warnings": []}
    try:
        export_path = vault / registry_contract["raw_registry_export"]
        exported_enrichment, warnings = load_exported_registry_enrichment_state(export_path)
        entries = enrich_registry_entries_with_inventory(
            vault,
            parse_raw_registry_pages(entry_pages),
            exported_enrichment=exported_enrichment,
        )
    except RawRegistryRuntimeError as exc:
        return {
            "resolution_map": {},
            "warnings": [
                {
                    "type": "raw_registry_source_trace_resolution_failed",
                    "path": registry_summary_page_path(vault, registry_contract).as_posix(),
                    "detail": str(exc),
                    "diagnostic_type": raw_registry_exception_detail(exc)["diagnostic_type"],
                }
            ],
        }
    return {
        "resolution_map": build_registry_source_trace_resolution_map(entries),
        "warnings": warnings,
    }


def load_registry_source_trace_resolution_map(vault: Path, registry_contract: dict) -> dict[str, list[str]]:
    return load_registry_source_trace_resolution_state(vault, registry_contract)["resolution_map"]


def parse_raw_registry_page(page_path: Path) -> list[dict]:
    try:
        lines = page_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RawRegistryPageReadError(page_path, operation="read", reason=str(exc)) from exc
    entries: list[dict] = []
    current_registry_id: str | None = None
    current_entry_lines: list[str] = []
    current_entry_start_line: int | None = None

    def finalize_current_entry(end_line: int) -> None:
        nonlocal current_registry_id, current_entry_lines, current_entry_start_line
        if current_registry_id is None or current_entry_start_line is None:
            return
        entry = parse_registry_entry_lines(current_registry_id, current_entry_lines)
        entry["_entry_start_line"] = current_entry_start_line
        entry["_entry_end_line"] = end_line
        append_entry(entries, entry)
        current_registry_id = None
        current_entry_lines = []
        current_entry_start_line = None

    for line_number, line in enumerate(lines, start=1):
        heading_match = ENTRY_ID_RE.match(line.strip())
        if heading_match:
            if current_registry_id is not None:
                finalize_current_entry(line_number - 1)
            current_registry_id = heading_match.group(1)
            current_entry_lines = []
            current_entry_start_line = line_number
            continue

        if current_registry_id is not None and line.startswith("## "):
            finalize_current_entry(line_number - 1)
            continue

        if current_registry_id is None:
            continue

        if not line.strip():
            continue

        if line.startswith("### "):
            finalize_current_entry(line_number - 1)
            continue

        current_entry_lines.append(line)

    if current_registry_id is not None:
        finalize_current_entry(len(lines))
    return entries


def parse_raw_registry_pages(page_paths: list[Path]) -> list[dict]:
    entries: list[dict] = []
    for page_path in page_paths:
        for entry in parse_raw_registry_page(page_path):
            enriched_entry = dict(entry)
            enriched_entry["_registry_page"] = page_path.as_posix()
            entries.append(enriched_entry)
    return entries


def parse_raw_registry_summary_counts(page_path: Path) -> dict[str, int]:
    try:
        lines = page_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RawRegistryPageReadError(page_path, operation="read", reason=str(exc)) from exc
    counts: dict[str, int] = {}
    in_summary = False

    for line in lines:
        stripped = line.strip()
        if stripped == "## Summary":
            in_summary = True
            continue
        if in_summary and stripped.startswith("## "):
            break
        if not in_summary:
            continue
        match = SUMMARY_COUNT_RE.match(stripped)
        if not match:
            continue
        key, value = match.groups()
        counts[key.strip()] = int(value)

    return counts


def exportable_registry_entries(entries: list[dict]) -> list[dict]:
    return [
        {
            key: value
            for key, value in entry.items()
            if not key.startswith("_")
        }
        for entry in entries
    ]


def build_raw_registry_export(entries: list[dict], summary_page: str, entry_pages: list[str]) -> dict:
    return {
        "summary_page": summary_page,
        "entry_pages": entry_pages,
        "entry_count": len(entries),
        "entries": exportable_registry_entries(entries),
    }
