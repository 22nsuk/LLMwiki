from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.public_surface_policy import (
        PUBLIC_GITIGNORE_END,
        PUBLIC_GITIGNORE_START,
        PUBLIC_GITIGNORE_TEMPLATE,
        render_public_gitignore_block,
    )
else:
    from .public_surface_policy import (
        PUBLIC_GITIGNORE_END,
        PUBLIC_GITIGNORE_START,
        PUBLIC_GITIGNORE_TEMPLATE,
        render_public_gitignore_block,
    )


def synced_gitignore_text(original: str) -> str:
    start = original.index(PUBLIC_GITIGNORE_START)
    end = original.index(PUBLIC_GITIGNORE_END) + len(PUBLIC_GITIGNORE_END)
    return original[:start] + render_public_gitignore_block().rstrip("\n") + original[end:]


def sync_gitignore(gitignore_path: Path) -> bool:
    original = gitignore_path.read_text(encoding="utf-8")
    updated = synced_gitignore_text(original)
    if updated == original:
        return False
    gitignore_path.write_text(updated, encoding="utf-8")
    return True


def gitignore_is_synced(gitignore_path: Path) -> bool:
    original = gitignore_path.read_text(encoding="utf-8")
    return synced_gitignore_text(original) == original


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync the generated public mirror .gitignore template.")
    parser.add_argument("--gitignore", default=PUBLIC_GITIGNORE_TEMPLATE)
    parser.add_argument("--check", action="store_true", help="Fail if .gitignore would be updated.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    gitignore_path = Path(args.gitignore).resolve()
    if args.check:
        synced = gitignore_is_synced(gitignore_path)
        print(f"sync_public_surface_gitignore: {'unchanged' if synced else 'would_update'}")
        return 0 if synced else 1
    changed = sync_gitignore(gitignore_path)
    print(f"sync_public_surface_gitignore: {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
