from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_envelope_runtime import build_canonical_report_envelope
from .artifact_freshness_payload_runtime import (
    ENVELOPE_REQUIRED_FIELDS,
    embed_artifact_envelope_metadata,
)
from .backfill_archived_run_artifacts import (
    derive_run_artifact_generated_at,
    run_artifact_spec_for_filename,
)
from .policy_runtime import load_policy

PRODUCER = "ops.scripts.run_artifact_envelope_runtime"
HELPER_SOURCE_PATH = "ops/scripts/core/run_artifact_envelope_runtime.py"
BACKFILL_SOURCE_BASENAME = "backfill_archived_run_artifacts.py"


def _normalized_rel_path(rel_path: str | Path) -> str:
    return Path(str(rel_path).replace("\\", "/")).as_posix()


def _is_supported_run_artifact_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return normalized.startswith("runs/") and "/tmp/" not in normalized


def _writer_source_paths(spec_source_paths: tuple[str, ...]) -> list[str]:
    source_paths = [
        path
        for path in spec_source_paths
        if Path(path).name != BACKFILL_SOURCE_BASENAME
    ]
    if HELPER_SOURCE_PATH not in source_paths:
        source_paths.append(HELPER_SOURCE_PATH)
    return source_paths


def _has_top_level_artifact_envelope(payload: dict[str, Any]) -> bool:
    return all(field in payload for field in ENVELOPE_REQUIRED_FIELDS)


def _canonical_payload_text(payload: dict[str, Any]) -> str:
    normalized = dict(payload)
    metadata = normalized.get("metadata")
    if isinstance(metadata, dict):
        normalized_metadata = dict(metadata)
        properties = [
            item
            for item in normalized_metadata.get("properties", [])
            if not (
                isinstance(item, dict)
                and str(item.get("name", "")).strip() == "urn:openai:artifact-envelope"
            )
        ]
        if properties:
            normalized_metadata["properties"] = properties
        else:
            normalized_metadata.pop("properties", None)
        if normalized_metadata:
            normalized["metadata"] = normalized_metadata
        else:
            normalized.pop("metadata", None)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def maybe_embed_run_artifact_envelope(
    vault: Path,
    rel_path: str | Path,
    payload: dict[str, Any],
    *,
    schema_path: str,
    policy_path: str | None = None,
) -> dict[str, Any]:
    normalized_rel_path = _normalized_rel_path(rel_path)
    if not _is_supported_run_artifact_path(normalized_rel_path):
        return payload
    if _has_top_level_artifact_envelope(payload):
        return payload

    spec = run_artifact_spec_for_filename(Path(normalized_rel_path).name)
    if spec is None or spec.schema_path != schema_path:
        return payload

    artifact_path = vault / normalized_rel_path
    generated_at, generated_at_source = derive_run_artifact_generated_at(
        vault,
        artifact_path,
        normalized_rel_path,
        payload,
        spec=spec,
    )

    try:
        _policy, resolved_policy_path = load_policy(vault, policy_path)
    except FileNotFoundError:
        return payload
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=spec.artifact_kind,
        producer=PRODUCER,
        source_command=f"schema-backed run artifact writer: {normalized_rel_path}",
        resolved_policy_path=resolved_policy_path,
        schema_path=spec.schema_path,
        source_paths=_writer_source_paths(spec.source_paths),
        text_inputs={
            "run_artifact_payload_before_envelope": _canonical_payload_text(payload),
            "run_artifact_path": normalized_rel_path,
            "generated_at_source": generated_at_source,
            "envelope_mode": "metadata.properties",
        },
    )
    envelope["artifact_status"] = "archived"
    envelope["retention_policy"] = "archive"
    envelope["currentness"] = {
        "status": "current",
        "checked_at": generated_at,
    }
    return embed_artifact_envelope_metadata(payload, envelope)
