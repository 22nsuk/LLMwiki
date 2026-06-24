#!/usr/bin/env python3
"""Generate the full-vault review surface manifest and scope doc.

The JSON manifest (default ``tmp/review-surface-manifest.json``) is intentionally
ephemeral: it is a regenerable navigation aid, not a canonical report envelope, so
it stays under ``tmp/`` rather than a tracked ``ops/reports`` path. The tracked,
canonical reviewer-facing surface is ``docs/REVIEW_SCOPE.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import display_path, write_output_text
    from ops.scripts.core.path_runtime import normalize_repo_path_text
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.wiki_page_runtime import discover_pages
else:
    from ops.scripts.core.output_runtime import display_path, write_output_text
    from ops.scripts.core.path_runtime import normalize_repo_path_text
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.wiki_page_runtime import discover_pages

CANONICAL_MD_OUT = "docs/REVIEW_SCOPE.md"
EPHEMERAL_JSON_OUT = "tmp/review-surface-manifest.json"
DEFAULT_JSON_OUT = EPHEMERAL_JSON_OUT
DEFAULT_MD_OUT = CANONICAL_MD_OUT
PRODUCER = "ops.scripts.public.review_surface_manifest"
SURFACE_ROOTS = ("wiki", "system", "raw", "runs", "ops", "docs")


class ReviewSurfaceOutputContractError(ValueError):
    """Raised when review-surface output paths violate the canonical contract."""


def validate_review_surface_output_paths(*, json_out: str, md_out: str) -> None:
    json_path = normalize_repo_path_text(json_out)
    md_path = normalize_repo_path_text(md_out)
    if md_path != CANONICAL_MD_OUT:
        raise ReviewSurfaceOutputContractError(
            f"review scope markdown must be written to {CANONICAL_MD_OUT!r}, not {md_out!r}"
        )
    if json_path is None or not json_path.startswith("tmp/"):
        raise ReviewSurfaceOutputContractError(
            "review surface JSON must stay under tmp/ as an ephemeral navigation aid; "
            f"got {json_out!r}"
        )
    if json_path.startswith("ops/reports/"):
        raise ReviewSurfaceOutputContractError(
            "review surface JSON must not be promoted to ops/reports/; "
            f"use {EPHEMERAL_JSON_OUT!r} and keep {CANONICAL_MD_OUT!r} canonical"
        )


def review_surface_output_contract() -> dict[str, str]:
    return {
        "canonical_surface": CANONICAL_MD_OUT,
        "ephemeral_surface": EPHEMERAL_JSON_OUT,
        "canonical_retention": "tracked_generated_doc",
        "ephemeral_retention": "scratch",
    }


def _count_paths(vault: Path, relative_prefix: str) -> tuple[int, int]:
    root = vault / relative_prefix
    if not root.exists():
        return 0, 0
    files = [path for path in root.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def _wiki_page_counts(vault: Path) -> dict[str, int]:
    pages, duplicates = discover_pages(vault)
    counts: dict[str, int] = {"total": len(pages), "duplicate_stems": len(duplicates)}
    for prefix in ("source--", "concept--", "synthesis--"):
        counts[prefix] = sum(1 for stem in pages if stem.startswith(prefix))
    return counts


def _raw_registry_status(vault: Path) -> dict[str, Any]:
    registry_path = vault / "ops/raw-registry.json"
    if not registry_path.is_file():
        return {"status": "missing", "entry_count": 0}
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid", "entry_count": 0}
    entries = registry.get("entries", [])
    entry_count = len(entries) if isinstance(entries, list) else 0
    return {"status": "present", "entry_count": entry_count}


def build_manifest(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    surfaces: dict[str, Any] = {}
    for root in SURFACE_ROOTS:
        file_count, total_bytes = _count_paths(vault, root)
        surfaces[root] = {"file_count": file_count, "total_bytes": total_bytes}
    wiki_counts = _wiki_page_counts(vault)
    raw_status = _raw_registry_status(vault)
    recommended_commands = [
        "make check",
        "make lint",
        "make eval",
        "make public-check",
        "make review-surface-manifest",
        "make release-evidence-converge",
    ]
    if raw_status["status"] == "present":
        recommended_commands.insert(3, "make registry-preflight-check")
    return {
        "artifact_kind": "review_surface_manifest",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "output_contract": review_surface_output_contract(),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "pass",
        "surfaces": surfaces,
        "wiki_page_counts": wiki_counts,
        "raw_registry": raw_status,
        "recommended_commands": recommended_commands,
    }


def render_markdown(manifest: dict[str, Any]) -> str:
    contract = manifest.get("output_contract", review_surface_output_contract())
    lines = [
        "# Review Scope",
        "",
        "Canonical full-vault reviewer-facing inventory.",
        "Regenerate with `make review-surface-manifest`. The companion JSON at",
        f"`{contract['ephemeral_surface']}` is intentionally ephemeral and must not",
        "be promoted to `ops/reports/`.",
        "",
        f"Generated at: `{manifest['generated_at']}`",
        "",
        "## Surface counts",
        "",
        "| Surface | Files | Bytes |",
        "| --- | ---: | ---: |",
    ]
    for name, payload in sorted(manifest["surfaces"].items()):
        lines.append(
            f"| `{name}/` | {payload['file_count']} | {payload['total_bytes']} |"
        )
    wiki = manifest["wiki_page_counts"]
    lines.extend(
        [
            "",
            "## Wiki page families",
            "",
            f"- total pages: {wiki['total']}",
            f"- duplicate stems: {wiki['duplicate_stems']}",
            f"- source pages: {wiki.get('source--', 0)}",
            f"- concept pages: {wiki.get('concept--', 0)}",
            f"- synthesis pages: {wiki.get('synthesis--', 0)}",
            "",
            "## Raw registry",
            "",
            f"- status: `{manifest['raw_registry']['status']}`",
            f"- entries: {manifest['raw_registry']['entry_count']}",
            "",
            "## Recommended commands",
            "",
        ]
    )
    for command in manifest["recommended_commands"]:
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def write_outputs(vault: Path, manifest: dict[str, Any], *, json_out: str, md_out: str) -> tuple[Path, Path]:
    validate_review_surface_output_paths(json_out=json_out, md_out=md_out)
    json_path = vault / json_out
    md_path = vault / md_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    write_output_text(json_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_output_text(md_path, render_markdown(manifest))
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate review surface manifest and scope doc.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--json-out", default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", default=DEFAULT_MD_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    manifest = build_manifest(vault)
    json_path, md_path = write_outputs(vault, manifest, json_out=args.json_out, md_out=args.md_out)
    print(display_path(vault, json_path))
    print(display_path(vault, md_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
