from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.filesystem_runtime import atomic_write_json
    from ops.scripts.public.public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
        PUBLIC_INCLUDE_FILES,
        PUBLIC_INCLUDE_PREFIXES,
        PUBLIC_INCLUDED_REPORT_FILES,
        is_public_excluded_path,
        render_public_gitignore_block,
    )
else:
    from ops.scripts.core.filesystem_runtime import atomic_write_json

    from .public_surface_policy import (
        PUBLIC_EXCLUDED_FILES,
        PUBLIC_EXCLUDED_PREFIXES,
        PUBLIC_INCLUDE_FILES,
        PUBLIC_INCLUDE_PREFIXES,
        PUBLIC_INCLUDED_REPORT_FILES,
        is_public_excluded_path,
        render_public_gitignore_block,
    )


DEFAULT_PUBLIC_OUT = str(Path(tempfile.gettempdir()) / "llm-wiki-public-repo")


def should_export_public(rel_path: str) -> bool:
    if rel_path in PUBLIC_INCLUDED_REPORT_FILES:
        return True
    if is_public_excluded_path(rel_path):
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


def _export_roots(vault: Path, out_dir: Path) -> tuple[Path, Path]:
    source, output = vault.resolve(), out_dir.resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("public export source and output must not overlap")
    if not source.is_dir():
        raise ValueError("public export source must be an existing directory")
    if output.exists() and not output.is_dir():
        raise ValueError("public export output must be a directory")
    return source, output


@contextmanager
def _output_lock(output: Path) -> Iterator[None]:
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / f".{output.name}.export.lock"
    if lock.is_symlink():
        raise ValueError("public export lock must not be a symlink")
    # Keep the inode after release so another process cannot lock a replacement
    # while a waiter still holds the old inode. The OS releases locks on exit.
    with lock.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("cannot acquire public export output lock") from exc
        yield


def _populate_export(vault: Path, out_dir: Path) -> dict[str, object]:
    vault_root = vault.resolve()
    copied: list[str] = []
    for rel_path in iter_public_files(vault):
        source = vault / rel_path
        if not _is_safe_export_file(vault_root, source):
            continue
        destination = out_dir / rel_path
        if any(parent.is_symlink() for parent in destination.parents if parent.is_relative_to(out_dir)):
            raise ValueError("public export destination contains a symlink directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            destination.unlink()
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


def _publish_export(staged: Path, output: Path) -> None:
    backup: Path | None = None
    if output.exists():
        backup = Path(tempfile.mkdtemp(prefix=f".{output.name}.previous-", dir=output.parent))
        backup.rmdir()
        output.replace(backup)
    try:
        staged.replace(output)
    except OSError:
        if backup is not None:
            backup.replace(output)
        raise
    if backup is not None:
        shutil.rmtree(backup)


@contextmanager
def public_export_session(
    vault: Path, out_dir: Path, *, clean: bool = True
) -> Iterator[dict[str, object]]:
    source, output = _export_roots(vault, out_dir)
    with _output_lock(output):
        with tempfile.TemporaryDirectory(prefix=f".{output.name}.stage-", dir=output.parent) as temp:
            staged = Path(temp) / "export"
            if not clean and output.exists():
                shutil.copytree(output, staged, symlinks=True)
            else:
                staged.mkdir()
            manifest = _populate_export(source, staged)
            _publish_export(staged, output)
        yield manifest


def export_public_repo(
    vault: Path, out_dir: Path, *, clean: bool = True
) -> dict[str, object]:
    with public_export_session(vault, out_dir, clean=clean) as manifest:
        return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export the public code/ops mirror of this vault."
    )
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
