#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_io_runtime import resolve_repo_artifact_path
    from ops.scripts.output_runtime import resolve_output_path, write_output_text
    from ops.scripts.raw_intake_promotion_runtime import (
        render_family_pages,
        scaffold_profile_bundle,
        validate_profile_bundle,
    )
    from ops.scripts.schema_constants_runtime import RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH
else:
    from ops.scripts.artifact_io_runtime import resolve_repo_artifact_path
    from ops.scripts.output_runtime import resolve_output_path, write_output_text
    from .raw_intake_promotion_runtime import (
        render_family_pages,
        scaffold_profile_bundle,
        validate_profile_bundle,
    )
    from ops.scripts.schema_constants_runtime import RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold_parser = subparsers.add_parser("scaffold")
    scaffold_parser.add_argument("--matrix", required=True)
    scaffold_parser.add_argument("--out", required=True)
    scaffold_parser.add_argument("--page-date")
    scaffold_parser.add_argument("--vault", default=".")
    scaffold_parser.add_argument("--bridge-limit", type=int, default=3)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", required=True)
    validate_parser.add_argument("--out")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--manifest", required=True)
    render_parser.add_argument("--vault", default=".")
    render_parser.add_argument("--out")

    args = parser.parse_args()

    if args.command == "scaffold":
        manifest = scaffold_profile_bundle(
            Path(args.matrix),
            page_date=args.page_date,
            vault=Path(args.vault).resolve(),
            bridge_limit=args.bridge_limit,
        )
        destination = resolve_output_path(Path("."), args.out)
        write_output_text(destination, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return

    if args.command == "validate":
        report = validate_profile_bundle(Path(args.manifest))
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            destination = resolve_output_path(Path("."), args.out)
            write_output_text(destination, text + "\n")
        else:
            print(text)
        raise SystemExit(1 if report["status"] == "fail" else 0)

    manifest_path = Path(args.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rendered = render_family_pages(payload)
    vault = Path(args.vault).resolve()
    for relative_path, text in rendered.items():
        destination = resolve_repo_artifact_path(vault, relative_path, default_relative_path=relative_path)
        write_output_text(destination, text)

    report = {
        "$schema": RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        "status": "pass",
        "manifest": manifest_path.as_posix(),
        "family_count": len(payload.get("families", [])) if isinstance(payload.get("families"), list) else 0,
        "refresh_count": len(payload.get("refreshes", [])) if isinstance(payload.get("refreshes"), list) else 0,
        "written_file_count": len(rendered),
        "written_files": sorted(rendered),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        destination = resolve_repo_artifact_path(vault, args.out, default_relative_path=args.out)
        write_output_text(destination, text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
