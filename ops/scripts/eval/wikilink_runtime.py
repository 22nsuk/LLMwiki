from __future__ import annotations

import re
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")


def extract_wikilinks(text: str | None) -> list[str]:
    if not text:
        return []
    return WIKILINK_RE.findall(text)


def build_page_lookup(vault: Path, page_map: dict[str, Path]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for stem, path in page_map.items():
        lookup.setdefault(stem, stem)

        try:
            relative_path = path.relative_to(vault)
            relative_to_vault = relative_path.with_suffix("").as_posix()
            lookup.setdefault(relative_to_vault, stem)

            parts = relative_path.parts
            if parts:
                relative_to_root = Path(*parts[1:]).with_suffix("").as_posix()
                if relative_to_root and relative_to_root != ".":
                    lookup.setdefault(relative_to_root, stem)
        except ValueError:
            pass

    return lookup


def resolve_wikilink_target(target: str, page_lookup: dict[str, str]) -> str | None:
    return page_lookup.get(target)
