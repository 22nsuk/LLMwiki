from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.schema_constants_runtime import (
    RAW_INTAKE_ABSORPTION_MATRIX_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema

TEXTUAL_RAW_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm"}


class IntakeMatrixError(ValueError):
    """The batch cannot be admitted; no per-source checks have run."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntakeMatrixError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise IntakeMatrixError(f"invalid JSON constant: {value}")


def load_intake_matrix(matrix_path: Path) -> dict[str, Any]:
    try:
        matrix = json.loads(
            matrix_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntakeMatrixError(f"cannot read JSON matrix: {exc}") from exc
    # Use the shipped contract, not a schema selected by the input document.
    schema_path = Path(__file__).resolve().parents[3] / RAW_INTAKE_ABSORPTION_MATRIX_SCHEMA_PATH
    errors = validate_with_schema(matrix, load_schema(schema_path))
    if errors:
        raise IntakeMatrixError("invalid intake matrix: " + "; ".join(errors))
    entries = matrix["matrix"]
    if matrix["source_count"] != len(entries):
        errors.append("source_count must equal the number of matrix rows")
    ids = Counter(entry["registry_id"] for entry in entries)
    if any(count > 1 for count in ids.values()):
        errors.append("registry_id must be unique across matrix rows")
    for name, field in (("action_counts", "proposed_action"), ("confidence_counts", "confidence"), ("target_counts", "target")):
        expected = dict(Counter(entry[field].strip() for entry in entries))
        if matrix[name] != expected:
            errors.append(f"{name} must exactly match matrix row counts (trimmed {field})")
    if errors:
        raise IntakeMatrixError("invalid intake matrix: " + "; ".join(errors))
    return matrix


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
