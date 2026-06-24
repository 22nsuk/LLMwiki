from __future__ import annotations

import re
from pathlib import Path


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _all_evidence_status(existing_count: int, expected_count: int) -> str | None:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return None


def operator_entrypoint_index_status(vault: Path, existing_count: int, expected_count: int) -> str:
    status = _all_evidence_status(existing_count, expected_count)
    if status:
        return status
    make_surface = "\n".join(
        _read_text_or_empty(vault / rel_path)
        for rel_path in ("Makefile", "mk/core.mk")
    )
    docs_text = _read_text_or_empty(vault / "docs/development.md")
    if (
        re.search(r"(?m)^help:", make_surface)
        and "make help" in docs_text
        and all(token in make_surface for token in ("release", "public", "mechanism", "report-contract"))
    ):
        return "implemented"
    return "requires_release_run_verification"
