#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path, write_output_text
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.raw_registry_runtime import (
        build_raw_registry_export,
        enrich_registry_entries_with_inventory,
        load_exported_registry_enrichment,
        parse_raw_registry_pages,
        registry_entry_page_paths,
        registry_summary_page_path,
    )
    from ops.scripts.registry_exceptions_runtime import RawRegistryRuntimeError
    from ops.scripts.schema_constants_runtime import RAW_REGISTRY_EXPORT_SCHEMA_PATH
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path, write_output_text
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.schema_constants_runtime import RAW_REGISTRY_EXPORT_SCHEMA_PATH

    from .raw_registry_runtime import (
        build_raw_registry_export,
        enrich_registry_entries_with_inventory,
        load_exported_registry_enrichment,
        parse_raw_registry_pages,
        registry_entry_page_paths,
        registry_summary_page_path,
    )
    from ops.scripts.registry_exceptions_runtime import RawRegistryRuntimeError

DEFAULT_POLICY = "ops/policies/wiki-maintainer-policy.yaml"


def _serialized_export(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_stored_export(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "decode_error"
    except (OSError, UnicodeError):
        return {}, "read_error"
    if not isinstance(payload, dict):
        return {}, "type_error"
    return payload, "ok"


def build_current_raw_registry_export(
    vault: Path,
    policy_path: str | None = None,
    *,
    out_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    policy, _ = load_policy(vault, policy_path or DEFAULT_POLICY)
    registry_contract = policy["registry_contract"]
    summary_page = registry_summary_page_path(vault, registry_contract)
    entry_pages = registry_entry_page_paths(vault, registry_contract)
    destination = resolve_schema_backed_report_output_path(
        vault,
        out_path,
        default_relative_path=registry_contract["raw_registry_export"],
    )

    entries = enrich_registry_entries_with_inventory(
        vault,
        parse_raw_registry_pages(entry_pages),
        exported_enrichment=load_exported_registry_enrichment(destination),
    )
    export = build_raw_registry_export(
        entries,
        summary_page.relative_to(vault).as_posix(),
        [page.relative_to(vault).as_posix() for page in entry_pages],
    )
    return export, destination


def raw_registry_export_check(
    vault: Path,
    policy_path: str | None = None,
    *,
    out_path: str | Path | None = None,
) -> dict[str, Any]:
    if not any((vault / surface).exists() for surface in ("raw", "wiki", "system")):
        return {
            "status": "pass",
            "check_status": "not_applicable",
            "path": "",
            "reason": "corpus registry surfaces are absent",
        }

    try:
        candidate_export, destination = build_current_raw_registry_export(
            vault,
            policy_path,
            out_path=out_path,
        )
    except (KeyError, OSError, UnicodeError, ValueError, RawRegistryRuntimeError) as exc:
        return {
            "status": "fail",
            "check_status": "candidate_unavailable",
            "path": "",
            "reason": f"{exc.__class__.__name__}: {exc}",
        }

    stored_text = ""
    stored_load_status = "missing"
    if destination.exists():
        try:
            stored_text = destination.read_text(encoding="utf-8")
            stored_load_status = "ok"
        except (OSError, UnicodeError):
            stored_load_status = "read_error"

    candidate_text = _serialized_export(candidate_export)
    stored_payload, parsed_status = _load_stored_export(destination)
    if stored_load_status == "ok" and parsed_status != "ok":
        stored_load_status = parsed_status

    if stored_load_status == "ok" and stored_text == candidate_text:
        check_status = "match"
    elif stored_load_status == "ok" and stored_payload == candidate_export:
        check_status = "format_mismatch"
    else:
        check_status = stored_load_status if stored_load_status != "ok" else "mismatch"

    stored_entries = stored_payload.get("entries") if isinstance(stored_payload, dict) else []
    return {
        "status": "pass" if check_status == "match" else "fail",
        "check_status": check_status,
        "path": display_path(vault, destination),
        "candidate": {
            "entry_count": int(candidate_export.get("entry_count", 0)),
            "sha256": _sha256_text(candidate_text),
        },
        "stored": {
            "load_status": stored_load_status,
            "entry_count": len(stored_entries) if isinstance(stored_entries, list) else None,
            "sha256": _sha256_text(stored_text) if stored_text else "",
        },
    }


def write_raw_registry_export_check_report(
    vault: Path,
    report: dict[str, Any],
    out_path: str | Path,
) -> Path:
    destination = vault / out_path if not Path(out_path).is_absolute() else Path(out_path)
    return write_output_text(destination, json.dumps(report, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default=DEFAULT_POLICY)
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--check-out")
    args = ap.parse_args(argv)

    vault = Path(args.vault)
    if args.check:
        report = raw_registry_export_check(vault, args.policy, out_path=args.out)
        if args.check_out:
            destination = write_raw_registry_export_check_report(vault, report, args.check_out)
            print(display_path(vault, destination))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["status"] == "pass" else 1)

    policy, _ = load_policy(vault, args.policy)
    registry_contract = policy["registry_contract"]
    export, _destination = build_current_raw_registry_export(
        vault,
        args.policy,
        out_path=args.out,
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
