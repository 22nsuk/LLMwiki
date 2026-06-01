from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .policy_runtime import report_path
from .source_revision_runtime import resolve_source_revision
from .source_tree_fingerprint_runtime import release_source_tree_fingerprint

ARTIFACT_ENVELOPE_SCHEMA_PATH = "ops/schemas/artifact-envelope.schema.json"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def _fingerprint_paths(vault: Path, rel_paths: list[str]) -> str:
    digest = hashlib.sha256()
    for rel_path in sorted(rel_paths):
        path = vault / rel_path
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_source_path(vault: Path, rel_path: str) -> str:
    normalized = Path(rel_path).as_posix()
    if (vault / normalized).exists():
        return normalized
    parts = normalized.split("/")
    if len(parts) == 3 and parts[:2] == ["ops", "scripts"] and parts[2].endswith(".py"):
        matches = sorted((vault / "ops" / "scripts").glob(f"*/{parts[2]}"))
        if len(matches) == 1:
            return report_path(vault, matches[0])
    return normalized


def _canonical_source_paths(vault: Path, rel_paths: Sequence[str]) -> list[str]:
    canonical: dict[str, None] = {}
    for rel_path in rel_paths:
        normalized = str(rel_path).strip()
        if not normalized:
            continue
        canonical[_canonical_source_path(vault, normalized)] = None
    return sorted(canonical)


def resolve_artifact_path(vault: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return (vault / resolved).resolve()


@dataclass(frozen=True)
class CanonicalReportEnvelopeRequest:
    vault: Path
    generated_at: str
    artifact_kind: str
    producer: str
    source_command: str
    resolved_policy_path: Path
    schema_path: str
    source_paths: list[str]
    file_inputs: Mapping[str, str | Path] | None = None
    path_group_inputs: Mapping[str, list[str]] | None = None
    text_inputs: Mapping[str, str] | None = None
    source_tree_excluded_files: tuple[str, ...] = ()
    source_tree_included_prefixes: tuple[str, ...] = ()

    @classmethod
    def from_legacy_args(
        cls,
        vault: Path,
        **legacy_kwargs: Any,
    ) -> CanonicalReportEnvelopeRequest:
        required_keys = {
            "generated_at",
            "artifact_kind",
            "producer",
            "source_command",
            "resolved_policy_path",
            "schema_path",
            "source_paths",
        }
        optional_keys = {
            "file_inputs",
            "path_group_inputs",
            "text_inputs",
            "source_tree_excluded_files",
            "source_tree_included_prefixes",
        }
        missing = sorted(required_keys - legacy_kwargs.keys())
        unexpected = sorted(set(legacy_kwargs) - required_keys - optional_keys)
        if missing:
            raise TypeError(f"missing legacy envelope arguments: {', '.join(missing)}")
        if unexpected:
            raise TypeError(f"unexpected legacy envelope arguments: {', '.join(unexpected)}")
        return cls(
            vault=vault,
            generated_at=str(legacy_kwargs["generated_at"]),
            artifact_kind=str(legacy_kwargs["artifact_kind"]),
            producer=str(legacy_kwargs["producer"]),
            source_command=str(legacy_kwargs["source_command"]),
            resolved_policy_path=Path(legacy_kwargs["resolved_policy_path"]),
            schema_path=str(legacy_kwargs["schema_path"]),
            source_paths=[str(path) for path in legacy_kwargs["source_paths"]],
            file_inputs=legacy_kwargs.get("file_inputs"),
            path_group_inputs=legacy_kwargs.get("path_group_inputs"),
            text_inputs=legacy_kwargs.get("text_inputs"),
            source_tree_excluded_files=tuple(legacy_kwargs.get("source_tree_excluded_files", ())),
            source_tree_included_prefixes=tuple(
                legacy_kwargs.get("source_tree_included_prefixes", ())
            ),
        )


def _coerce_canonical_report_envelope_request(
    request: CanonicalReportEnvelopeRequest | Path,
    **legacy_kwargs: Any,
) -> CanonicalReportEnvelopeRequest:
    if isinstance(request, CanonicalReportEnvelopeRequest):
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"unexpected legacy envelope arguments with request object: {unexpected}")
        return request
    return CanonicalReportEnvelopeRequest.from_legacy_args(Path(request), **legacy_kwargs)


def artifact_input_fingerprints(
    vault: Path,
    *,
    resolved_policy_path: Path,
    schema_path: str,
    source_paths: Sequence[str] | None = None,
    file_inputs: Mapping[str, str | Path] | None = None,
    path_group_inputs: Mapping[str, list[str]] | None = None,
    text_inputs: Mapping[str, str] | None = None,
) -> dict[str, str]:
    fingerprints = {
        "policy": _sha256_file(resolved_policy_path),
        "schema": _sha256_file(vault / schema_path),
        "artifact_envelope_schema": _sha256_file(vault / ARTIFACT_ENVELOPE_SCHEMA_PATH),
    }
    if source_paths is not None:
        fingerprints["source_paths"] = _fingerprint_paths(
            vault,
            _canonical_source_paths(vault, source_paths),
        )
    for name, path in sorted((file_inputs or {}).items()):
        fingerprints[str(name)] = _sha256_file(resolve_artifact_path(vault, path))
    for name, rel_paths in sorted((path_group_inputs or {}).items()):
        fingerprints[str(name)] = _fingerprint_paths(vault, [str(item) for item in rel_paths])
    for name, text in sorted((text_inputs or {}).items()):
        fingerprints[str(name)] = _sha256_text(str(text))
    return fingerprints


def build_canonical_report_envelope(
    request: CanonicalReportEnvelopeRequest | Path,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    envelope_request = _coerce_canonical_report_envelope_request(request, **legacy_kwargs)
    source_revision = resolve_source_revision(envelope_request.vault)
    return {
        "$schema": envelope_request.schema_path,
        "artifact_kind": envelope_request.artifact_kind,
        "generated_at": envelope_request.generated_at,
        "producer": envelope_request.producer,
        "source_command": envelope_request.source_command,
        "source_revision": source_revision.revision,
        "source_tree_fingerprint": release_source_tree_fingerprint(
            envelope_request.vault,
            extra_excluded_files=envelope_request.source_tree_excluded_files,
            included_prefixes=envelope_request.source_tree_included_prefixes,
        ),
        "input_fingerprints": artifact_input_fingerprints(
            envelope_request.vault,
            resolved_policy_path=envelope_request.resolved_policy_path,
            schema_path=envelope_request.schema_path,
            source_paths=envelope_request.source_paths,
            file_inputs=envelope_request.file_inputs,
            path_group_inputs=envelope_request.path_group_inputs,
            text_inputs=envelope_request.text_inputs,
        ),
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": envelope_request.generated_at,
        },
    }
