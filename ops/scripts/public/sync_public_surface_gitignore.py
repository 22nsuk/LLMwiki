from __future__ import annotations
import sys

import argparse
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.public_surface_policy import (
        PUBLIC_GITIGNORE_END,
        PUBLIC_GITIGNORE_START,
        render_public_gitignore_block,
    )
else:
    from .public_surface_policy import (
        PUBLIC_GITIGNORE_END,
        PUBLIC_GITIGNORE_START,
        render_public_gitignore_block,
    )


def sync_gitignore(gitignore_path: Path) -> bool:
    original = gitignore_path.read_text(encoding="utf-8")
    start = original.index(PUBLIC_GITIGNORE_START)
    end = original.index(PUBLIC_GITIGNORE_END) + len(PUBLIC_GITIGNORE_END)
    updated = original[:start] + render_public_gitignore_block().rstrip("\n") + original[end:]
    if updated == original:
        return False
    gitignore_path.write_text(updated, encoding="utf-8")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync the public surface block in .gitignore.")
    parser.add_argument("--gitignore", default=".gitignore")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    gitignore_path = Path(args.gitignore).resolve()
    changed = sync_gitignore(gitignore_path)
    print(f"sync_public_surface_gitignore: {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
