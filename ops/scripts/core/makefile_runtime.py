from __future__ import annotations

import re
from pathlib import Path

INCLUDE_RE = re.compile(r"^include\s+(?P<paths>.+)$")


def _include_tokens(line: str) -> list[str]:
    match = INCLUDE_RE.match(line.strip())
    if match is None:
        return []
    tokens: list[str] = []
    for token in match.group("paths").split():
        if not token or "$" in token or "*" in token:
            continue
        tokens.append(token)
    return tokens


def makefile_source_paths(vault: Path, root: str = "Makefile") -> list[str]:
    resolved_vault = vault.resolve()
    seen: set[str] = set()
    ordered: list[str] = []

    def visit(rel_path: str) -> None:
        normalized = Path(rel_path).as_posix()
        if normalized in seen:
            return
        path = resolved_vault / normalized
        if not path.is_file():
            return
        seen.add(normalized)
        ordered.append(normalized)
        for line in path.read_text(encoding="utf-8").splitlines():
            for include_path in _include_tokens(line):
                visit(include_path)

    visit(root)
    return ordered


def load_makefile_text(vault: Path, root: str = "Makefile") -> tuple[str, list[str]]:
    source_paths = makefile_source_paths(vault, root=root)
    resolved_vault = vault.resolve()
    chunks: list[str] = []
    for rel_path in source_paths:
        chunks.append(f"# source: {rel_path}")
        chunks.append((resolved_vault / rel_path).read_text(encoding="utf-8"))
    return "\n".join(chunks), source_paths
