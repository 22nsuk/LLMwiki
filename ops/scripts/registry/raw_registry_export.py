#!/usr/bin/env python3
from __future__ import annotations
import sys

import argparse
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.raw_registry_runtime import (
        build_raw_registry_export,
        enrich_registry_entries_with_inventory,
        load_exported_registry_enrichment,
        parse_raw_registry_pages,
        registry_entry_page_paths,
        registry_summary_page_path,
    )
    from ops.scripts.schema_constants_runtime import RAW_REGISTRY_EXPORT_SCHEMA_PATH
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from .raw_registry_runtime import (
        build_raw_registry_export,
        enrich_registry_entries_with_inventory,
        load_exported_registry_enrichment,
        parse_raw_registry_pages,
        registry_entry_page_paths,
        registry_summary_page_path,
    )
    from ops.scripts.schema_constants_runtime import RAW_REGISTRY_EXPORT_SCHEMA_PATH


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    vault = Path(args.vault)
    policy, _ = load_policy(vault, args.policy)
    registry_contract = policy["registry_contract"]
    summary_page = registry_summary_page_path(vault, registry_contract)
    entry_pages = registry_entry_page_paths(vault, registry_contract)
    out_path = resolve_schema_backed_report_output_path(
        vault,
        args.out,
        default_relative_path=registry_contract["raw_registry_export"],
    )

    entries = enrich_registry_entries_with_inventory(
        vault,
        parse_raw_registry_pages(entry_pages),
        exported_enrichment=load_exported_registry_enrichment(out_path),
    )
    export = build_raw_registry_export(
        entries,
        summary_page.relative_to(vault).as_posix(),
        [page.relative_to(vault).as_posix() for page in entry_pages],
    )
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=export,
            schema_path=RAW_REGISTRY_EXPORT_SCHEMA_PATH,
            out_path=args.out,
            default_relative_path=registry_contract["raw_registry_export"],
            context="raw registry export schema validation failed",
            trailing_newline=False,
        )
    )
    print(display_path(vault, destination))


if __name__ == "__main__":
    main()
