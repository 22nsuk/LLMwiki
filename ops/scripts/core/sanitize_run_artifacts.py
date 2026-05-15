from __future__ import annotations
import sys

import argparse
import re
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.filesystem_runtime import atomic_write_text
else:
    from .filesystem_runtime import atomic_write_text


TEXT_SUFFIXES = {".json", ".txt", ".md", ".yaml", ".yml"}
TEMP_VAULT_PREFIX_RE = re.compile(
    r"/mnt/c/Users/[^/\s]+/AppData/Local/Temp/[^/\s]+/vault/"
)
TEMP_VAULT_ROOT_RE = re.compile(
    r"/mnt/c/Users/[^/\s]+/AppData/Local/Temp/[^/\s]+/vault\b"
)


def _sanitize_root_strings(*roots: Path) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for root in roots:
        variants: list[str] = []
        for candidate in (root, root.absolute()):
            candidate_text = candidate.as_posix().rstrip("/")
            if candidate_text:
                variants.append(candidate_text)
        try:
            resolved_text = root.resolve().as_posix().rstrip("/")
        except OSError:
            resolved_text = ""
        if resolved_text:
            variants.append(resolved_text)
        for root_text in variants:
            key = root_text.casefold()
            if not root_text or key in seen:
                continue
            seen.add(key)
            normalized.append(root_text)
    normalized.sort(key=len, reverse=True)
    return normalized


def sanitize_run_text(text: str, *, repo_root: Path) -> str:
    sanitized = text.replace("\\", "/")
    for root_text in _sanitize_root_strings(repo_root):
        sanitized = re.sub(re.escape(f"{root_text}/"), "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(re.escape(root_text), ".", sanitized, flags=re.IGNORECASE)
    sanitized = TEMP_VAULT_PREFIX_RE.sub("", sanitized)
    sanitized = TEMP_VAULT_ROOT_RE.sub(".", sanitized)
    return sanitized


def _iter_run_files(runs_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in runs_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "README.md":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        candidates.append(path)
    return sorted(candidates)


def sanitize_run_artifacts(*, repo_root: Path, runs_root: Path | None = None) -> list[str]:
    effective_runs_root = runs_root or repo_root / "runs"
    changed: list[str] = []
    for artifact_path in _iter_run_files(effective_runs_root):
        original = artifact_path.read_text(encoding="utf-8")
        sanitized = sanitize_run_text(original, repo_root=repo_root)
        if sanitized == original:
            continue
        atomic_write_text(artifact_path, sanitized)
        changed.append(artifact_path.relative_to(repo_root).as_posix())
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sanitize repo-local run artifacts for sharing.")
    parser.add_argument("--vault", default=".", help="Repository root containing runs/")
    parser.add_argument("--runs-root", default="runs", help="Runs directory relative to --vault")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file output")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path(args.vault).resolve()
    runs_root = (repo_root / args.runs_root).resolve()
    changed = sanitize_run_artifacts(repo_root=repo_root, runs_root=runs_root)
    if not args.quiet:
        for rel_path in changed:
            print(rel_path)
    print(f"sanitized_files={len(changed)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
