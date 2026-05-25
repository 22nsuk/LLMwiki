from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.filesystem_runtime import atomic_write_json
    from ops.scripts.public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
        PUBLIC_EXCLUDED_SEGMENTS,
        PUBLIC_INCLUDE_FILES,
        PUBLIC_INCLUDE_PREFIXES,
        PUBLIC_INCLUDED_REPORT_FILES,
        render_public_gitignore_block,
    )
else:
    from ops.scripts.filesystem_runtime import atomic_write_json

    from .public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
        PUBLIC_EXCLUDED_SEGMENTS,
        PUBLIC_INCLUDE_FILES,
        PUBLIC_INCLUDE_PREFIXES,
        PUBLIC_INCLUDED_REPORT_FILES,
        render_public_gitignore_block,
    )


DEFAULT_PUBLIC_OUT = str(Path(tempfile.gettempdir()) / "llm-wiki-public-repo")


def should_export_public(rel_path: str) -> bool:
    if rel_path in PUBLIC_EXCLUDED_FILES:
        return False
    if rel_path in PUBLIC_INCLUDED_REPORT_FILES:
        return True
    if any(rel_path.startswith(prefix) for prefix in PUBLIC_EXCLUDED_PREFIXES):
        return False
    if any(segment in PUBLIC_EXCLUDED_SEGMENTS for segment in Path(rel_path).parts):
        return False
    return rel_path in PUBLIC_INCLUDE_FILES or any(
        rel_path.startswith(prefix) for prefix in PUBLIC_INCLUDE_PREFIXES
    )


def _is_safe_export_file(vault_root: Path, path: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
        resolved = path.resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(vault_root)
    except ValueError:
        return False
    return True


def iter_public_files(vault: Path) -> list[str]:
    files: list[str] = []
    vault_root = vault.resolve()
    for path in sorted(vault.rglob("*")):
        rel_path = path.relative_to(vault).as_posix()
        if not should_export_public(rel_path):
            continue
        if not _is_safe_export_file(vault_root, path):
            continue
        files.append(rel_path)
    return files


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    target = path
    tombstone = path.parent / f".{path.name}.delete-{os.getpid()}"
    suffix = 0
    while tombstone.exists():
        suffix += 1
        tombstone = path.parent / f".{path.name}.delete-{os.getpid()}-{suffix}"
    try:
        path.replace(tombstone)
        target = tombstone
    except FileNotFoundError:
        return
    except OSError:
        target = path
    try:
        shutil.rmtree(target)
    except FileNotFoundError:
        return


def export_public_repo(vault: Path, out_dir: Path, *, clean: bool = True) -> dict[str, object]:
    if clean and out_dir.exists():
        _remove_tree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    vault_root = vault.resolve()
    copied: list[str] = []
    for rel_path in iter_public_files(vault):
        source = vault / rel_path
        if not _is_safe_export_file(vault_root, source):
            continue
        destination = out_dir / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if rel_path == ".gitignore":
            destination.write_text(render_public_gitignore_block(), encoding="utf-8")
        else:
            shutil.copy2(source, destination)
        copied.append(rel_path)

    manifest = {
        "source_vault": ".",
        "output_dir": ".",
        "file_count": len(copied) + 1,
        "source_file_count": len(copied),
        "manifest_file": "PUBLIC-EXPORT-MANIFEST.json",
        "files": copied,
        "excluded_prefixes": list(PUBLIC_EXCLUDED_PREFIXES),
        "excluded_files": sorted(PUBLIC_EXCLUDED_FILES),
        "included_report_files": sorted(PUBLIC_INCLUDED_REPORT_FILES),
    }
    atomic_write_json(out_dir / "PUBLIC-EXPORT-MANIFEST.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the public code/ops mirror of this vault.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_PUBLIC_OUT)
    parser.add_argument("--no-clean", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    vault = Path(args.vault).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (vault / out_dir).resolve()
    manifest = export_public_repo(vault, out_dir, clean=not args.no_clean)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
