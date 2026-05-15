#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.output_runtime import resolve_output_path, write_output_text
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.raw_intake_promotion_runtime import suggest_bridge_sources_for_family
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
        SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
    )
    from ops.scripts.source_page_naming_runtime import source_slug_validation_detail, source_stem_slug_and_date
else:
    from .output_runtime import resolve_output_path, write_output_text
    from .policy_runtime import load_policy
    from ops.scripts.raw_intake_promotion_runtime import suggest_bridge_sources_for_family
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import (
        SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
        SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
    )
    from .source_page_naming_runtime import source_slug_validation_detail, source_stem_slug_and_date


def _matrix_entries(matrix_path: Path) -> list[dict]:
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix = payload.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("matrix artifact must contain a top-level 'matrix' list")
    return matrix


def scaffold_manifest(
    matrix_path: Path,
    *,
    vault: Path | None = None,
    bridge_limit: int = 3,
    context: RuntimeContext | None = None,
) -> dict:
    entries = _matrix_entries(matrix_path)
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    target_to_source_stems: dict[str, list[str]] = {}
    for entry in entries:
        target = entry.get("target")
        source_page = entry.get("source_page")
        if not isinstance(target, str) or not target.strip() or not isinstance(source_page, str):
            continue
        target_to_source_stems.setdefault(target.strip(), []).append(Path(source_page).stem)

    bridge_candidate_cache: dict[str, list[dict]] = {}
    scaffold_entries: list[dict] = []
    for entry in entries:
        source_page = entry.get("source_page")
        if not isinstance(source_page, str):
            continue
        stem = Path(source_page).stem
        current_slug, date_suffix = source_stem_slug_and_date(stem)
        scaffold_entry = {
            "registry_id": entry.get("registry_id"),
            "title": entry.get("title"),
            "raw_path": entry.get("raw_path"),
            "source_page": source_page,
            "current_slug": current_slug,
            "date_suffix": date_suffix,
            "curated_english_slug": "",
        }
        proposed_action = entry.get("proposed_action")
        target = entry.get("target")
        if isinstance(proposed_action, str) and proposed_action.strip():
            scaffold_entry["proposed_action"] = proposed_action.strip()
        if isinstance(target, str) and target.strip():
            normalized_target = target.strip()
            scaffold_entry["target"] = normalized_target
            if vault is not None and proposed_action == "create_new_synthesis_family":
                if normalized_target not in bridge_candidate_cache:
                    bridge_candidate_cache[normalized_target] = suggest_bridge_sources_for_family(
                        vault,
                        normalized_target,
                        exclude_source_stems=target_to_source_stems.get(normalized_target, []),
                        limit=bridge_limit,
                    )
                scaffold_entry["family_bridge_candidates"] = bridge_candidate_cache[normalized_target]
        scaffold_entries.append(scaffold_entry)
    return {
        "$schema": SOURCE_SLUG_CURATION_MANIFEST_SCHEMA_PATH,
        "generated_at": runtime_context.isoformat_z(),
        "scope": matrix_path.name,
        "source_count": len(scaffold_entries),
        "instructions": (
            "Fill curated_english_slug with a human-authored lowercase English summary slug. "
            "Keep it ASCII-only and hyphen-separated so source pages resolve as source--<slug>-<date>. "
            "When proposed_action is create_new_synthesis_family, review family_bridge_candidates during "
            "source registration so the later promotion profile can integrate older bridge context directly "
            "into mature synthesis/concept prose."
        ),
        "entries": scaffold_entries,
    }


def validate_manifest(manifest_path: Path) -> dict:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("manifest must contain an 'entries' list")

    errors: list[dict] = []
    seen: dict[str, str] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            errors.append({"type": "invalid_entry", "detail": entry})
            continue
        registry_id = entry.get("registry_id")
        date_suffix = entry.get("date_suffix")
        curated_slug = entry.get("curated_english_slug")
        if not isinstance(curated_slug, str) or not curated_slug.strip():
            errors.append(
                {
                    "type": "missing_curated_english_slug",
                    "registry_id": registry_id,
                }
            )
            continue
        candidate_stem = f"source--{curated_slug.strip()}"
        if isinstance(date_suffix, str) and date_suffix:
            candidate_stem = f"{candidate_stem}-{date_suffix}"
        detail = source_slug_validation_detail(
            candidate_stem,
            {
                "ascii_summary_slug_pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                "disallowed_slug_substrings": ["intake-w-"],
            },
        )
        if detail is not None:
            errors.append(
                {
                    "type": "invalid_curated_english_slug",
                    "registry_id": registry_id,
                    "detail": detail,
                }
            )
            continue
        if curated_slug in seen:
            errors.append(
                {
                    "type": "duplicate_curated_english_slug",
                    "registry_id": registry_id,
                    "detail": {
                        "curated_english_slug": curated_slug,
                        "first_registry_id": seen[curated_slug],
                    },
                }
            )
            continue
        seen[curated_slug] = str(registry_id)

    return {
        "$schema": SOURCE_SLUG_CURATION_VALIDATION_REPORT_SCHEMA_PATH,
        "manifest": manifest_path.as_posix(),
        "status": "fail" if errors else "pass",
        "error_count": len(errors),
        "errors": errors,
        "source_count": len(raw_entries),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold_parser = subparsers.add_parser("scaffold")
    scaffold_parser.add_argument("--matrix", required=True)
    scaffold_parser.add_argument("--out", required=True)
    scaffold_parser.add_argument("--vault", default=".")
    scaffold_parser.add_argument("--bridge-limit", type=int, default=3)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", required=True)
    validate_parser.add_argument("--out")

    args = parser.parse_args()

    if args.command == "scaffold":
        vault = Path(args.vault).resolve()
        policy, _ = load_policy(vault)
        manifest = scaffold_manifest(
            Path(args.matrix),
            vault=vault,
            bridge_limit=args.bridge_limit,
            context=RuntimeContext.from_policy(policy),
        )
        destination = resolve_output_path(Path("."), args.out)
        write_output_text(destination, json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    report = validate_manifest(Path(args.manifest))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        destination = resolve_output_path(Path("."), args.out)
        write_output_text(destination, text)
    else:
        print(text)
    raise SystemExit(1 if report["status"] == "fail" else 0)


if __name__ == "__main__":
    main()
