from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEXTUAL_RAW_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm"}


@dataclass(frozen=True)
class IntakeFile:
    status: str
    text: str = ""
    sha256: str = ""


def read_intake_file(vault: Path, value: str) -> IntakeFile:
    if not value:
        return IntakeFile("missing_path")
    try:
        path = Path(value)
        resolved = (vault / path).resolve()
        if path.is_absolute() or not resolved.is_relative_to(vault.resolve()):
            return IntakeFile("invalid_path")
        if not resolved.exists():
            return IntakeFile("missing_file")
        if not resolved.is_file():
            return IntakeFile("not_file")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        with resolved.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                if path.suffix.lower() in TEXTUAL_RAW_SUFFIXES:
                    chunks.append(chunk)
        # Preserve read_text's universal-newline behavior while hashing original bytes.
        text = b"".join(chunks).decode("utf-8", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return IntakeFile("present", text, digest.hexdigest())
    except (OSError, ValueError):
        return IntakeFile("unreadable")


def read_intake_inputs(vault: Path, entries: list[dict[str, Any]]) -> dict[str, IntakeFile]:
    paths = {
        str(entry.get(field) or "").strip()
        for entry in entries
        for field in ("raw_path", "source_page")
    }
    return {path: read_intake_file(vault, path) for path in sorted(paths)}


def intake_content_inputs(
    entries: list[dict[str, Any]], inputs: dict[str, IntakeFile]
) -> dict[str, str]:
    # Hash the same bytes used by the checks, including absent/unreadable inputs.
    # File-set identity is independent of matrix row order and duplicate routes.
    result = {}
    for name, field in (("raw_files", "raw_path"), ("source_pages", "source_page")):
        paths = sorted({str(entry.get(field) or "").strip() for entry in entries})
        manifest = [
            {"path": path, "status": inputs[path].status, "sha256": inputs[path].sha256}
            for path in paths
        ]
        result[name] = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    return result
