#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ENVELOPE_REQUIRED_FIELDS = [
    "$schema",
    "artifact_kind",
    "generated_at",
    "producer",
    "source_command",
    "source_revision",
    "source_tree_fingerprint",
    "input_fingerprints",
    "schema_version",
    "artifact_status",
    "retention_policy",
    "encoding",
    "currentness",
]
EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY = "urn:openai:artifact-envelope"


def artifact_metadata_properties(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return []
    properties = metadata.get("properties")
    if not isinstance(properties, list):
        return []
    return [item for item in properties if isinstance(item, dict)]


def embed_artifact_envelope_metadata(payload: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    properties = normalized_metadata.get("properties")
    normalized_properties = [
        item
        for item in properties
        if isinstance(item, dict) and str(item.get("name", "")).strip() != EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
    ] if isinstance(properties, list) else []
    normalized_properties.append(
        {
            "name": EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
            "value": json.dumps(envelope, ensure_ascii=False, sort_keys=True),
        }
    )
    normalized_metadata["properties"] = sorted(
        normalized_properties,
        key=lambda item: str(item.get("name", "")),
    )
    normalized = dict(payload)
    normalized["metadata"] = normalized_metadata
    return normalized


def embedded_artifact_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    for item in artifact_metadata_properties(payload):
        name = str(item.get("name", "")).strip()
        if name != EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY:
            continue
        value = item.get("value")
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def envelope_field_missing(field: str, value: Any) -> bool:
    if value is None:
        return True
    if field in {"currentness", "input_fingerprints"}:
        return not isinstance(value, dict)
    return not str(value).strip()


def normalized_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return payload
    embedded_envelope = embedded_artifact_envelope(payload)
    if not embedded_envelope:
        return payload
    normalized = dict(payload)
    for envelope_field in ENVELOPE_REQUIRED_FIELDS:
        if envelope_field not in embedded_envelope:
            continue
        if envelope_field_missing(envelope_field, normalized.get(envelope_field)):
            normalized[envelope_field] = embedded_envelope[envelope_field]
    return normalized


def canonical_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return normalized_artifact_payload(payload)


def currentness_status(payload: dict[str, Any]) -> str:
    normalized_payload = normalized_artifact_payload(payload)
    currentness = normalized_payload.get("currentness")
    if not isinstance(currentness, dict):
        return "unknown"
    status = str(currentness.get("status", "")).strip()
    return status or "unknown"


def computed_currentness_status(
    *,
    declared_currentness_status: str,
    source_tree_fingerprint_status: str,
    source_revision_status: str = "not_applicable",
) -> str:
    if declared_currentness_status != "current":
        return declared_currentness_status
    if source_tree_fingerprint_status in {"stale", "unknown"}:
        return source_tree_fingerprint_status
    if source_revision_status in {"stale", "unknown"}:
        return source_revision_status
    return declared_currentness_status


def has_artifact_envelope(payload: dict[str, Any]) -> bool:
    normalized_payload = normalized_artifact_payload(payload)
    if not all(field in normalized_payload for field in ENVELOPE_REQUIRED_FIELDS):
        return False
    currentness = normalized_payload.get("currentness")
    input_fingerprints = normalized_payload.get("input_fingerprints")
    return isinstance(currentness, dict) and isinstance(input_fingerprints, dict)


def canonical_report_loading_issue(path: Path, payload: dict[str, Any]) -> str | None:
    if not has_artifact_envelope(payload):
        return "missing_artifact_envelope"

    normalized_payload = normalized_artifact_payload(payload)

    artifact_status = str(normalized_payload.get("artifact_status", "")).strip() or "unknown"
    if artifact_status != "current":
        return f"artifact_status={artifact_status}"

    currentness = currentness_status(normalized_payload)
    if currentness != "current":
        return f"currentness_status={currentness}"

    # File mtime drift is reported separately as freshness attention, but it is not a
    # hard loading blocker for otherwise valid canonical reports. Cross-platform file
    # copies and checkout behavior can legitimately produce an mtime one second newer
    # than generated_at, and downstream loaders should still consume the report.
    del path

    return None
