from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.filesystem_runtime import atomic_write_json
    from ops.scripts.public.export_public_repo import (
        DEFAULT_PUBLIC_OUT,
        export_public_repo,
    )
else:
    from ops.scripts.core.filesystem_runtime import atomic_write_json

    from .export_public_repo import DEFAULT_PUBLIC_OUT, export_public_repo


CBM_MANIFEST_NAME = "CBM-EXPORT-MANIFEST.json"
PUBLIC_MANIFEST_NAME = "PUBLIC-EXPORT-MANIFEST.json"
DEFAULT_CBMIGNORE_TEMPLATE = "ops/templates/codebase-memory-mcp.cbmignore"

CBM_FORBIDDEN_PREFIXES = (
    "raw/",
    "wiki/",
    "system/",
    "runs/",
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
)
CBM_FORBIDDEN_SEGMENTS = (".codebase-memory",)
CBM_PRUNED_PUBLIC_EXPORT_PATHS = (
    "ops/operator",
    "ops/reports",
    PUBLIC_MANIFEST_NAME,
)


class CbmPublicExportError(RuntimeError):
    pass


def _is_same_or_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_cbm_local_paths(
    vault: Path,
    public_out: Path,
    *,
    cache_dir: Path,
    cache_root: Path,
) -> None:
    resolved_vault = vault.resolve()
    resolved_public_out = public_out.expanduser().resolve()
    resolved_cache_dir = cache_dir.expanduser().resolve()
    resolved_cache_root = cache_root.expanduser().resolve()

    if resolved_cache_root == Path(resolved_cache_root.anchor):
        raise CbmPublicExportError(f"refusing unsafe CBM_CACHE_ROOT={resolved_cache_root}")
    if _is_same_or_child(resolved_cache_root, resolved_vault) or _is_same_or_child(
        resolved_vault, resolved_cache_root
    ):
        raise CbmPublicExportError(
            f"refusing CBM_CACHE_ROOT that overlaps vault: {resolved_cache_root}"
        )

    guarded_paths = {
        "CBM_PUBLIC_OUT": resolved_public_out,
        "CBM_CACHE_DIR": resolved_cache_dir,
    }
    for label, path in guarded_paths.items():
        if path == Path(path.anchor):
            raise CbmPublicExportError(f"refusing unsafe {label}={path}")
        if not _is_same_or_child(path, resolved_cache_root):
            raise CbmPublicExportError(f"{label} must be under CBM_CACHE_ROOT={resolved_cache_root}")
        if _is_same_or_child(path, resolved_vault) or _is_same_or_child(resolved_vault, path):
            raise CbmPublicExportError(f"refusing {label} that overlaps vault: {path}")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _relative_file_paths(out_dir: Path, *, exclude: set[str] | None = None) -> list[str]:
    excluded = exclude or set()
    files: list[str] = []
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(out_dir).as_posix()
        if rel_path in excluded:
            continue
        files.append(rel_path)
    return files


def _forbidden_index_paths(out_dir: Path) -> list[str]:
    forbidden: list[str] = []
    for rel_path in _relative_file_paths(out_dir):
        parts = Path(rel_path).parts
        if any(rel_path.startswith(prefix) for prefix in CBM_FORBIDDEN_PREFIXES):
            forbidden.append(rel_path)
            continue
        if any(segment in parts for segment in CBM_FORBIDDEN_SEGMENTS):
            forbidden.append(rel_path)
    return forbidden


def build_cbm_public_export(
    vault: Path,
    out_dir: Path,
    *,
    cbmignore_template: Path,
    clean: bool = True,
) -> dict[str, Any]:
    public_manifest = export_public_repo(vault, out_dir, clean=clean)
    for rel_path in CBM_PRUNED_PUBLIC_EXPORT_PATHS:
        _remove_path(out_dir / rel_path)

    if not cbmignore_template.is_file():
        raise CbmPublicExportError(f"missing .cbmignore template: {cbmignore_template}")
    shutil.copy2(cbmignore_template, out_dir / ".cbmignore")

    forbidden_paths = _forbidden_index_paths(out_dir)
    if forbidden_paths:
        raise CbmPublicExportError(
            "codebase-memory-mcp public export boundary violation: "
            + ", ".join(forbidden_paths[:10])
        )

    files = _relative_file_paths(out_dir, exclude={CBM_MANIFEST_NAME})
    manifest: dict[str, Any] = {
        "source_vault": ".",
        "output_dir": ".",
        "manifest_file": CBM_MANIFEST_NAME,
        "source_public_manifest_file": PUBLIC_MANIFEST_NAME,
        "source_public_file_count": public_manifest["source_file_count"],
        "source_file_count": len(files),
        "file_count": len(files) + 1,
        "files": files,
        "index_policy": "codebase_memory_mcp_public_export",
        "cbmignore_file": ".cbmignore",
        "cbmignore_template": cbmignore_template.relative_to(vault).as_posix()
        if cbmignore_template.is_relative_to(vault)
        else cbmignore_template.as_posix(),
        "forbidden_prefixes": list(CBM_FORBIDDEN_PREFIXES),
        "forbidden_segments": list(CBM_FORBIDDEN_SEGMENTS),
        "pruned_public_export_paths": list(CBM_PRUNED_PUBLIC_EXPORT_PATHS),
    }
    atomic_write_json(out_dir / CBM_MANIFEST_NAME, manifest)
    return manifest


def format_cbm_export_summary(manifest: dict[str, Any]) -> str:
    pruned = ",".join(manifest["pruned_public_export_paths"])
    return "\n".join(
        (
            "cbm_public_export=ok",
            f"manifest={manifest['manifest_file']}",
            f"source_public_files={manifest['source_public_file_count']}",
            f"index_files={manifest['source_file_count']}",
            f"total_files={manifest['file_count']}",
            f"pruned={pruned}",
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a public-safe codebase-memory-mcp index source export."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=str(Path(DEFAULT_PUBLIC_OUT).with_name("llmwiki-cbm-surface")))
    parser.add_argument("--cbmignore-template", default=DEFAULT_CBMIGNORE_TEMPLATE)
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument("--cache-dir")
    parser.add_argument("--cache-root")
    parser.add_argument("--check-local-paths", action="store_true")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact export summary instead of the full manifest file list.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    vault = Path(args.vault).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (vault / out_dir).resolve()
    if args.cache_dir or args.cache_root or args.check_local_paths:
        if not args.cache_dir or not args.cache_root:
            parser.error("--cache-dir and --cache-root must be provided together")
        validate_cbm_local_paths(
            vault,
            out_dir,
            cache_dir=Path(args.cache_dir),
            cache_root=Path(args.cache_root),
        )
        if args.check_local_paths:
            print("cbm_local_paths=ok")
            return 0
    cbmignore_template = Path(args.cbmignore_template)
    if not cbmignore_template.is_absolute():
        cbmignore_template = (vault / cbmignore_template).resolve()
    try:
        manifest = build_cbm_public_export(
            vault,
            out_dir,
            cbmignore_template=cbmignore_template,
            clean=not args.no_clean,
        )
    except CbmPublicExportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.summary:
        print(format_cbm_export_summary(manifest))
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
