#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.runtime_context import RuntimeContext
else:
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/doc-graph-integrity.json"
DEFAULT_ALLOWLIST = "ops/doc-graph-orphan-allowlist.json"
PRODUCER = "ops.scripts.doc_graph_integrity"
SCHEMA_PATH = "ops/schemas/doc-graph-integrity.schema.json"
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\((?P<target>[^)]+)\)")
DOC_ROOTS = ("docs", ".codex/agents", ".github", "ops/evals", "ops/templates")
ROOT_DOCS = ("README.md", "ARCHITECTURE.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md")
ENTRYPOINTS = {"README.md", "docs/README.md"}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _doc_files(vault: Path) -> list[Path]:
    docs = [vault / path for path in ROOT_DOCS if (vault / path).is_file()]
    for root in DOC_ROOTS:
        root_path = vault / root
        if root_path.exists():
            docs.extend(path for path in root_path.rglob("*.md") if path.is_file())
    return sorted(set(docs))


def _allowlisted_orphans(allowlist: dict[str, Any]) -> set[str]:
    entries = allowlist.get("allowed_orphans", [])
    if not isinstance(entries, list):
        return set()
    return {
        str(item.get("path", "")).strip()
        for item in entries
        if isinstance(item, dict) and str(item.get("path", "")).strip()
    }


def _normalize_link_target(source: Path, target: str) -> str:
    clean = target.split("#", 1)[0].strip()
    if not clean or "://" in clean or clean.startswith(("mailto:", "#")):
        return ""
    return (source.parent / clean).resolve().as_posix()


def _links(vault: Path, docs: list[Path]) -> tuple[list[dict[str, str]], set[str]]:
    missing: list[dict[str, str]] = []
    inbound: set[str] = set()
    for path in docs:
        rel_source = path.relative_to(vault).as_posix()
        for match in LINK_RE.finditer(_read_text(path)):
            normalized = _normalize_link_target(path, match.group("target"))
            if not normalized:
                continue
            target_path = Path(normalized)
            if target_path.exists():
                with suppress(ValueError):
                    inbound.add(target_path.relative_to(vault).as_posix())
            else:
                missing.append({"source": rel_source, "target": match.group("target")})
    return missing, inbound


def build_report(
    vault: Path,
    *,
    allowlist_path: str = DEFAULT_ALLOWLIST,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    docs = _doc_files(resolved_vault)
    doc_paths = {path.relative_to(resolved_vault).as_posix() for path in docs}
    missing_links, inbound = _links(resolved_vault, docs)
    allowlist = _read_json(resolved_vault / allowlist_path)
    allowed_orphans = _allowlisted_orphans(allowlist)
    orphan_docs = sorted(doc_paths - inbound - ENTRYPOINTS)
    unallowed_orphans = [path for path in orphan_docs if path not in allowed_orphans]
    stale_allowlist = sorted(allowed_orphans - doc_paths)
    status = "pass" if not missing_links and not unallowed_orphans and not stale_allowlist else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "doc_graph_integrity",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": status,
        "allowlist_path": allowlist_path,
        "summary": {
            "doc_count": len(doc_paths),
            "missing_link_count": len(missing_links),
            "orphan_doc_count": len(orphan_docs),
            "unallowed_orphan_count": len(unallowed_orphans),
            "stale_allowlist_count": len(stale_allowlist),
        },
        "docs": sorted(doc_paths),
        "missing_links": missing_links,
        "orphan_docs": orphan_docs,
        "unallowed_orphans": unallowed_orphans,
        "stale_allowlist": stale_allowlist,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint public markdown graph links and orphan exceptions.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--allowlist", default=DEFAULT_ALLOWLIST)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, allowlist_path=args.allowlist)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
